#include "risk_conformance_fixture.hpp"

#include <gtest/gtest.h>

#include <chrono>
#include <filesystem>
#include <fstream>
#include <string>
#include <utility>

#include "pmm/risk/account_risk.hpp"

namespace pmm::risk_conformance {
namespace {

template <typename T>
T Require(core::Result<T> result) {
  EXPECT_TRUE(result.has_value()) << result.error().message;
  return std::move(result).value();
}

[[nodiscard]] risk::AccountBinding Binding(std::uint64_t contract_value) {
  return risk::AccountBinding{Require(risk::AccountId::from_value(1)),
                              Require(risk::StrategyId::from_value(1)),
                              Require(core::TraderId::from_value(1)),
                              Require(core::ContractId::from_value(contract_value))};
}

[[nodiscard]] risk::RiskLimits ToRiskLimits(const Limits& limits) {
  return risk::RiskLimits{Require(core::Quantity::from_units(limits.maximum_order_quantity)),
                          Require(core::Quantity::from_units(limits.maximum_absolute_position)),
                          Require(core::Quantity::from_units(limits.maximum_buy_exposure)),
                          Require(core::Quantity::from_units(limits.maximum_sell_exposure)),
                          Require(core::Quantity::from_units(limits.maximum_pending_exposure)),
                          limits.maximum_active_orders};
}

[[nodiscard]] std::string RejectionResult(risk::AdmissionRejectCode code) {
  switch (code) {
    case risk::AdmissionRejectCode::KillSwitchActive:
      return "kill_switch_active";
    case risk::AdmissionRejectCode::ContractMismatch:
      return "contract_mismatch";
    case risk::AdmissionRejectCode::OrderQuantityLimit:
      return "order_quantity_limit";
    case risk::AdmissionRejectCode::ActiveOrderLimit:
      return "active_order_limit";
    case risk::AdmissionRejectCode::BuyExposureLimit:
      return "buy_exposure_limit";
    case risk::AdmissionRejectCode::SellExposureLimit:
      return "sell_exposure_limit";
    case risk::AdmissionRejectCode::PendingExposureLimit:
      return "pending_exposure_limit";
    case risk::AdmissionRejectCode::PositionLimit:
      return "position_limit";
    case risk::AdmissionRejectCode::DuplicateClientIntent:
      return "duplicate_client_intent";
  }
  return "unknown_rejection";
}

[[nodiscard]] std::string ApplyOperation(risk::AccountRiskProjection& projection,
                                         const Operation& operation) {
  return std::visit(
      [&projection](const auto& value) -> std::string {
        using T = std::decay_t<decltype(value)>;
        if constexpr (std::is_same_v<T, AdmitOperation>) {
          const risk::AdmissionDecision decision = projection.admit(
              risk::OrderIntent{Require(risk::ClientIntentId::from_value(value.client_intent_id)),
                                Require(core::ContractId::from_value(value.contract_id)),
                                value.side, Require(core::Quantity::from_units(value.quantity)),
                                Require(core::Price::from_units(value.limit_price)), true},
              core::Timestamp::from_unix_nanoseconds(0));
          return decision.approved() ? "approved" : RejectionResult(decision.rejection->code);
        } else if constexpr (std::is_same_v<T, BindIngressOperation>) {
          const auto result = projection.bind_ingress(
              Require(risk::ClientIntentId::from_value(value.client_intent_id)),
              value.ingress_sequence);
          return result ? "applied" : "domain_error";
        } else if constexpr (std::is_same_v<T, AcknowledgeOperation>) {
          const auto binding = projection.binding();
          const auto result = projection.apply(risk::AccountEvent{
              Require(core::SequenceNumber::from_value(value.sequence)),
              core::Timestamp::from_unix_nanoseconds(value.time_utc_ns), value.ingress_sequence,
              risk::AccountEventTruth::ModelDerived,
              risk::AccountOrderAcknowledged{Require(core::OrderId::from_value(value.order_id)),
                                             binding.trader_id, binding.contract_id, value.side,
                                             Require(core::Quantity::from_units(value.quantity)),
                                             Require(core::Price::from_units(value.limit_price))}});
          return result ? "applied" : "domain_error";
        } else if constexpr (std::is_same_v<T, FillOperation>) {
          const auto binding = projection.binding();
          // Fixture V1 carries no fill price.  Keep the frozen V1 oracle's fixed 50-cent value.
          const auto result = projection.apply(risk::AccountEvent{
              Require(core::SequenceNumber::from_value(value.sequence)),
              core::Timestamp::from_unix_nanoseconds(value.time_utc_ns), 0,
              risk::AccountEventTruth::ModelDerived,
              risk::AccountFill{Require(core::OrderId::from_value(value.order_id)),
                                binding.trader_id, binding.contract_id, value.side,
                                Require(core::Price::from_units(50)),
                                Require(core::Quantity::from_units(value.quantity))}});
          return result ? "applied" : "domain_error";
        } else if constexpr (std::is_same_v<T, CancelOperation>) {
          const auto result = projection.apply(risk::AccountEvent{
              Require(core::SequenceNumber::from_value(value.sequence)),
              core::Timestamp::from_unix_nanoseconds(value.time_utc_ns), 0,
              risk::AccountEventTruth::ModelDerived,
              risk::AccountCancellation{Require(core::OrderId::from_value(value.order_id))}});
          return result ? "applied" : "domain_error";
        } else if constexpr (std::is_same_v<T, CommandRejectedOperation>) {
          const auto result = projection.apply(risk::AccountEvent{
              Require(core::SequenceNumber::from_value(value.sequence)),
              core::Timestamp::from_unix_nanoseconds(value.time_utc_ns), value.ingress_sequence,
              risk::AccountEventTruth::ModelDerived, risk::AccountCommandRejected{}});
          return result ? "applied" : "domain_error";
        } else {
          if (value.active) {
            projection.activate_kill_switch();
          } else {
            projection.clear_kill_switch();
          }
          return "applied";
        }
      },
      operation);
}

void ExpectState(const risk::AccountRiskProjection& projection, const ExpectedState& expected) {
  const risk::AccountRiskView view = projection.view();
  EXPECT_EQ(view.event_watermark, expected.event_watermark);
  EXPECT_EQ(view.net_position, expected.net_position);
  EXPECT_EQ(view.open_buy_quantity.units(), static_cast<std::uint64_t>(expected.open_buy_quantity));
  EXPECT_EQ(view.open_sell_quantity.units(),
            static_cast<std::uint64_t>(expected.open_sell_quantity));
  EXPECT_EQ(view.pending_buy_quantity.units(),
            static_cast<std::uint64_t>(expected.pending_buy_quantity));
  EXPECT_EQ(view.pending_sell_quantity.units(),
            static_cast<std::uint64_t>(expected.pending_sell_quantity));
  EXPECT_EQ(view.kill_switch_active, expected.kill_switch_active);

  ASSERT_EQ(projection.live_orders().size(), expected.live_orders.size());
  auto actual_live = projection.live_orders().begin();
  for (const ExpectedLiveOrder& order : expected.live_orders) {
    ASSERT_NE(actual_live, projection.live_orders().end());
    EXPECT_EQ(actual_live->first.value(), order.order_id);
    EXPECT_EQ(actual_live->second.side, order.side);
    EXPECT_EQ(actual_live->second.price.units(), static_cast<std::uint64_t>(order.limit_price));
    EXPECT_EQ(actual_live->second.remaining_quantity.units(),
              static_cast<std::uint64_t>(order.remaining_quantity));
    EXPECT_EQ(actual_live->second.acknowledged_at.unix_nanoseconds(), order.acknowledged_at_utc_ns);
    ++actual_live;
  }

  ASSERT_EQ(projection.pending_orders().size(), expected.pending_orders.size());
  auto actual_pending = projection.pending_orders().begin();
  for (const ExpectedPendingOrder& order : expected.pending_orders) {
    ASSERT_NE(actual_pending, projection.pending_orders().end());
    EXPECT_EQ(actual_pending->first.value(), order.client_intent_id);
    EXPECT_EQ(actual_pending->second.intent.contract_id.value(), order.contract_id);
    EXPECT_EQ(actual_pending->second.ingress_sequence, order.ingress_sequence);
    EXPECT_EQ(actual_pending->second.intent.side, order.side);
    EXPECT_EQ(actual_pending->second.intent.limit_price.units(),
              static_cast<std::uint64_t>(order.limit_price));
    EXPECT_EQ(actual_pending->second.intent.quantity.units(),
              static_cast<std::uint64_t>(order.quantity));
    EXPECT_TRUE(actual_pending->second.intent.post_only);
    ++actual_pending;
  }
}

TEST(RiskConformanceFixture, VerifiesEveryCheckedInDocument) {
  EXPECT_NO_THROW({
    const std::vector<Fixture> fixtures = LoadCorpus(FixtureRoot());
    EXPECT_EQ(fixtures.size(), 16U);
  });
}

TEST(RiskConformanceFixture, RejectsTamperedNoncanonicalMember) {
  const auto nonce = std::chrono::steady_clock::now().time_since_epoch().count();
  const std::filesystem::path temporary =
      std::filesystem::temp_directory_path() / ("pmm-risk-fixture-" + std::to_string(nonce));
  std::filesystem::copy(FixtureRoot(), temporary, std::filesystem::copy_options::recursive);
  const std::filesystem::path fixture = temporary / "lifecycle.json";
  {
    std::ofstream output(fixture, std::ios::app | std::ios::binary);
    ASSERT_TRUE(output.good());
    output << ' ';
  }
  EXPECT_THROW(static_cast<void>(LoadCorpus(temporary)), std::runtime_error);
  std::filesystem::remove_all(temporary);
}

TEST(RiskConformanceFixture, DirectCppMatchesEveryReviewedTransition) {
  for (const Fixture& fixture : LoadCorpus(FixtureRoot())) {
    if (!HasExecutor(fixture, "direct_cpp")) {
      continue;
    }
    SCOPED_TRACE(fixture.fixture_id);
    risk::AccountRiskProjection projection = Require(risk::AccountRiskProjection::create(
        Binding(fixture.contract_id), ToRiskLimits(fixture.limits)));
    for (std::size_t index = 0; index < fixture.operations.size(); ++index) {
      SCOPED_TRACE("transition " + std::to_string(index) + " " +
                   OperationName(fixture.operations[index]));
      EXPECT_EQ(ApplyOperation(projection, fixture.operations[index]),
                fixture.transitions[index].result);
      ExpectState(projection, fixture.transitions[index].state);
    }
  }
}

}  // namespace
}  // namespace pmm::risk_conformance
