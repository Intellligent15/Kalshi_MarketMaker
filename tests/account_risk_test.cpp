#include "pmm/risk/account_risk.hpp"

#include <gtest/gtest.h>

namespace pmm::risk {
namespace {

template <typename T>
T Require(core::Result<T> result) {
  EXPECT_TRUE(result.has_value()) << result.error().message;
  return std::move(result).value();
}

void Require(core::Result<void> result) {
  EXPECT_TRUE(result.has_value()) << result.error().message;
}

core::Market MakeMarket() {
  const auto market_id = Require(core::MarketId::from_value(1));
  const auto contract_id = Require(core::ContractId::from_value(10));
  const auto grid = Require(core::PriceGrid::create(Require(core::Price::from_units(1)),
                                                    Require(core::Price::from_units(99)),
                                                    Require(core::Price::from_units(1))));
  const auto contract =
      Require(core::Contract::create(contract_id, market_id, Require(core::Price::from_units(100)),
                                     grid, Require(core::LotSize::from_units(1))));
  return Require(core::Market::create(market_id, "Question", contract));
}

AccountBinding Binding(core::ContractId contract_id) {
  return AccountBinding{Require(AccountId::from_value(1)), Require(StrategyId::from_value(2)),
                        Require(core::TraderId::from_value(3)), contract_id};
}

RiskLimits Limits() {
  return RiskLimits{Require(core::Quantity::from_units(5)), Require(core::Quantity::from_units(5)),
                    Require(core::Quantity::from_units(5)), Require(core::Quantity::from_units(5)),
                    Require(core::Quantity::from_units(5)), 4};
}

TEST(AccountRisk, AdmitsBoundIntentAndProjectsAcknowledgedOrderAndFill) {
  const core::Market market = MakeMarket();
  sim::ExchangeSimulator exchange = Require(sim::ExchangeSimulator::create({market}));
  AccountRiskProjection risk =
      Require(AccountRiskProjection::create(Binding(market.contract().id()), Limits()));
  const auto client_id = Require(ClientIntentId::from_value(1));
  const OrderIntent intent{client_id,
                           market.contract().id(),
                           core::Side::Buy,
                           Require(core::Quantity::from_units(2)),
                           Require(core::Price::from_units(50)),
                           true};
  AdmissionDecision decision = risk.admit(intent, core::Timestamp::from_unix_nanoseconds(1));
  ASSERT_TRUE(decision.approved());
  const auto ingress =
      Require(exchange.enqueue(*decision.command, core::Timestamp::from_unix_nanoseconds(1)));
  Require(risk.bind_ingress(client_id, ingress));
  Require(exchange.run_until(core::Timestamp::from_unix_nanoseconds(1)));
  for (const auto& event : exchange.events()) {
    Require(risk.apply(event));
  }
  EXPECT_EQ(risk.view().open_buy_quantity.units(), 2U);
  EXPECT_TRUE(risk.view().pending_buy_quantity.is_zero());

  const sim::SubmitOrderRequest sell{Require(core::TraderId::from_value(9)),
                                     market.contract().id(),
                                     core::Side::Sell,
                                     core::OrderType::Limit,
                                     Require(core::Quantity::from_units(2)),
                                     Require(core::Price::from_units(50)),
                                     core::Timestamp::from_unix_nanoseconds(2)};
  Require(exchange.enqueue(sell, core::Timestamp::from_unix_nanoseconds(2)));
  Require(exchange.run_until(core::Timestamp::from_unix_nanoseconds(2)));
  for (const auto& event : exchange.read_events_after(risk.view().event_watermark, 100)) {
    Require(risk.apply(event));
  }
  EXPECT_EQ(risk.view().net_position, 2);
  EXPECT_TRUE(risk.view().open_buy_quantity.is_zero());
}

TEST(AccountRisk, RejectsExcessExposureWithoutCreatingReservation) {
  const core::Market market = MakeMarket();
  AccountRiskProjection risk =
      Require(AccountRiskProjection::create(Binding(market.contract().id()), Limits()));
  const OrderIntent intent{Require(ClientIntentId::from_value(1)),
                           market.contract().id(),
                           core::Side::Buy,
                           Require(core::Quantity::from_units(6)),
                           Require(core::Price::from_units(50)),
                           true};
  const AdmissionDecision decision = risk.admit(intent, core::Timestamp::from_unix_nanoseconds(1));
  ASSERT_FALSE(decision.approved());
  ASSERT_TRUE(decision.rejection.has_value());
  EXPECT_EQ(decision.rejection->code, AdmissionRejectCode::OrderQuantityLimit);
  EXPECT_TRUE(risk.view().pending_buy_quantity.is_zero());
}

TEST(AccountRisk, ReleasesAReservationWhenTheExchangeRejectsItsPostOnlyCommand) {
  const core::Market market = MakeMarket();
  sim::ExchangeSimulator exchange = Require(sim::ExchangeSimulator::create({market}));
  AccountRiskProjection risk =
      Require(AccountRiskProjection::create(Binding(market.contract().id()), Limits()));
  const auto time = core::Timestamp::from_unix_nanoseconds(1);
  const sim::SubmitOrderRequest offer{Require(core::TraderId::from_value(9)),
                                      market.contract().id(),
                                      core::Side::Sell,
                                      core::OrderType::Limit,
                                      Require(core::Quantity::from_units(1)),
                                      Require(core::Price::from_units(50)),
                                      time};
  Require(exchange.enqueue(offer, time));
  Require(exchange.run_until(time));
  for (const auto& event : exchange.events()) {
    Require(risk.apply(event));
  }

  const auto client_id = Require(ClientIntentId::from_value(1));
  const OrderIntent intent{client_id,
                           market.contract().id(),
                           core::Side::Buy,
                           Require(core::Quantity::from_units(1)),
                           Require(core::Price::from_units(50)),
                           true};
  const AdmissionDecision decision = risk.admit(intent, time);
  ASSERT_TRUE(decision.approved());
  const auto ingress = Require(exchange.enqueue(*decision.command, time));
  Require(risk.bind_ingress(client_id, ingress));
  Require(exchange.run_until(time));
  for (const auto& event : exchange.read_events_after(risk.view().event_watermark, 100)) {
    Require(risk.apply(event));
  }
  EXPECT_TRUE(risk.view().pending_buy_quantity.is_zero());
  EXPECT_TRUE(risk.live_orders().empty());
}

TEST(AccountRisk, AppliesModelDerivedResearchEventsUsingTheSameReservationRules) {
  const core::Market market = MakeMarket();
  AccountRiskProjection risk =
      Require(AccountRiskProjection::create(Binding(market.contract().id()), Limits()));
  const auto client_id = Require(ClientIntentId::from_value(1));
  const auto order_id = Require(core::OrderId::from_value(11));
  const auto price = Require(core::Price::from_units(50));
  const auto quantity = Require(core::Quantity::from_units(2));
  const auto time = core::Timestamp::from_unix_nanoseconds(1);
  ASSERT_TRUE(risk.admit(OrderIntent{client_id, market.contract().id(), core::Side::Buy, quantity,
                                     price, true},
                         time)
                  .approved());
  Require(risk.bind_ingress(client_id, 7));
  Require(risk.apply(AccountEvent{
      Require(core::SequenceNumber::from_value(1)), time, 7, AccountEventTruth::ModelDerived,
      AccountOrderAcknowledged{order_id, Binding(market.contract().id()).trader_id,
                               market.contract().id(), core::Side::Buy, quantity, price}}));
  Require(risk.apply(AccountEvent{
      Require(core::SequenceNumber::from_value(2)), time, 0, AccountEventTruth::ModelDerived,
      AccountFill{order_id, Binding(market.contract().id()).trader_id, market.contract().id(),
                  core::Side::Buy, price, quantity}}));
  EXPECT_EQ(risk.view().net_position, 2);
  EXPECT_TRUE(risk.live_orders().empty());
}

TEST(AccountRisk, RejectsZeroQuantityWithoutCreatingAReservation) {
  const core::Market market = MakeMarket();
  AccountRiskProjection risk =
      Require(AccountRiskProjection::create(Binding(market.contract().id()), Limits()));
  const AdmissionDecision decision =
      risk.admit(OrderIntent{Require(ClientIntentId::from_value(1)), market.contract().id(),
                             core::Side::Buy, Require(core::Quantity::from_units(0)),
                             Require(core::Price::from_units(50)), true},
                 core::Timestamp::from_unix_nanoseconds(1));
  ASSERT_FALSE(decision.approved());
  ASSERT_TRUE(decision.rejection.has_value());
  EXPECT_EQ(decision.rejection->code, AdmissionRejectCode::OrderQuantityLimit);
  EXPECT_TRUE(risk.view().pending_buy_quantity.is_zero());
}

TEST(AccountRisk, RejectsInvalidFillWithoutMutatingPositionOrWatermark) {
  const core::Market market = MakeMarket();
  AccountRiskProjection risk =
      Require(AccountRiskProjection::create(Binding(market.contract().id()), Limits()));
  const auto order_id = Require(core::OrderId::from_value(11));
  const auto result = risk.apply(AccountEvent{
      Require(core::SequenceNumber::from_value(1)), core::Timestamp::from_unix_nanoseconds(1), 0,
      AccountEventTruth::ModelDerived,
      AccountFill{order_id, Binding(market.contract().id()).trader_id, market.contract().id(),
                  core::Side::Buy, Require(core::Price::from_units(50)),
                  Require(core::Quantity::from_units(1))}});
  ASSERT_FALSE(result.has_value());
  EXPECT_EQ(risk.view().net_position, 0);
  EXPECT_EQ(risk.view().event_watermark, 0U);
}

TEST(AccountRisk, RequiresAcknowledgementPriceToMatchReservation) {
  const core::Market market = MakeMarket();
  AccountRiskProjection risk =
      Require(AccountRiskProjection::create(Binding(market.contract().id()), Limits()));
  const auto client_id = Require(ClientIntentId::from_value(1));
  const auto quantity = Require(core::Quantity::from_units(1));
  ASSERT_TRUE(risk.admit(OrderIntent{client_id, market.contract().id(), core::Side::Buy, quantity,
                                     Require(core::Price::from_units(50)), true},
                         core::Timestamp::from_unix_nanoseconds(1))
                  .approved());
  Require(risk.bind_ingress(client_id, 1));
  const auto result = risk.apply(AccountEvent{
      Require(core::SequenceNumber::from_value(1)), core::Timestamp::from_unix_nanoseconds(1), 1,
      AccountEventTruth::ModelDerived,
      AccountOrderAcknowledged{Require(core::OrderId::from_value(11)),
                               Binding(market.contract().id()).trader_id, market.contract().id(),
                               core::Side::Buy, quantity, Require(core::Price::from_units(51))}});
  ASSERT_FALSE(result.has_value());
  EXPECT_EQ(risk.view().event_watermark, 0U);
  EXPECT_EQ(risk.view().pending_buy_quantity.units(), 1U);
}

TEST(AccountRisk, AppliesPartialFillCancellationKillSwitchAndCheckpointContinuation) {
  const core::Market market = MakeMarket();
  const AccountBinding binding = Binding(market.contract().id());
  AccountRiskProjection risk = Require(AccountRiskProjection::create(binding, Limits()));
  const auto client_id = Require(ClientIntentId::from_value(1));
  const auto order_id = Require(core::OrderId::from_value(11));
  const auto price = Require(core::Price::from_units(50));
  const auto quantity = Require(core::Quantity::from_units(2));
  const auto time = core::Timestamp::from_unix_nanoseconds(1);
  ASSERT_TRUE(risk.admit(OrderIntent{client_id, market.contract().id(), core::Side::Buy, quantity,
                                     price, true},
                         time)
                  .approved());
  Require(risk.bind_ingress(client_id, 1));
  Require(risk.apply(AccountEvent{
      Require(core::SequenceNumber::from_value(1)), time, 1, AccountEventTruth::ModelDerived,
      AccountOrderAcknowledged{order_id, binding.trader_id, binding.contract_id, core::Side::Buy,
                               quantity, price}}));
  Require(risk.apply(AccountEvent{
      Require(core::SequenceNumber::from_value(2)), time, 0, AccountEventTruth::ModelDerived,
      AccountFill{order_id, binding.trader_id, binding.contract_id, core::Side::Buy, price,
                  Require(core::Quantity::from_units(1))}}));
  EXPECT_EQ(risk.view().net_position, 1);
  EXPECT_EQ(risk.view().open_buy_quantity.units(), 1U);
  risk.activate_kill_switch();
  const auto blocked =
      risk.admit(OrderIntent{Require(ClientIntentId::from_value(2)), market.contract().id(),
                             core::Side::Sell, Require(core::Quantity::from_units(1)), price, true},
                 time);
  ASSERT_FALSE(blocked.approved());
  ASSERT_TRUE(blocked.rejection.has_value());
  EXPECT_EQ(blocked.rejection->code, AdmissionRejectCode::KillSwitchActive);
  const RiskCheckpoint checkpoint = risk.checkpoint();
  AccountRiskProjection restored =
      Require(AccountRiskProjection::restore(binding, Limits(), checkpoint));
  Require(
      restored.apply(AccountEvent{Require(core::SequenceNumber::from_value(3)), time, 0,
                                  AccountEventTruth::ModelDerived, AccountCancellation{order_id}}));
  EXPECT_EQ(restored.view().net_position, 1);
  EXPECT_TRUE(restored.view().open_buy_quantity.is_zero());
  EXPECT_TRUE(restored.view().kill_switch_active);
}

TEST(AccountRisk, RejectsDuplicateIngressBindingWithoutMutatingReservations) {
  const core::Market market = MakeMarket();
  AccountRiskProjection risk =
      Require(AccountRiskProjection::create(Binding(market.contract().id()), Limits()));
  const auto price = Require(core::Price::from_units(50));
  for (std::uint64_t client = 1; client <= 2; ++client) {
    ASSERT_TRUE(risk.admit(OrderIntent{Require(ClientIntentId::from_value(client)),
                                       market.contract().id(), core::Side::Buy,
                                       Require(core::Quantity::from_units(1)), price, true},
                           core::Timestamp::from_unix_nanoseconds(1))
                    .approved());
  }
  Require(risk.bind_ingress(Require(ClientIntentId::from_value(1)), 7));
  const auto duplicate = risk.bind_ingress(Require(ClientIntentId::from_value(2)), 7);
  EXPECT_FALSE(duplicate.has_value());
  ASSERT_EQ(risk.pending_orders().size(), 2U);
  EXPECT_FALSE(risk.pending_orders()
                   .at(Require(ClientIntentId::from_value(2)))
                   .ingress_sequence.has_value());
}

TEST(AccountRisk, RejectsZeroFillWithoutAdvancingWatermark) {
  const core::Market market = MakeMarket();
  const AccountBinding binding = Binding(market.contract().id());
  AccountRiskProjection risk = Require(AccountRiskProjection::create(binding, Limits()));
  const auto client = Require(ClientIntentId::from_value(1));
  const auto order = Require(core::OrderId::from_value(11));
  const auto price = Require(core::Price::from_units(50));
  ASSERT_TRUE(risk.admit(OrderIntent{client, binding.contract_id, core::Side::Buy,
                                     Require(core::Quantity::from_units(1)), price, true},
                         core::Timestamp::from_unix_nanoseconds(1))
                  .approved());
  Require(risk.bind_ingress(client, 1));
  Require(risk.apply(AccountEvent{
      Require(core::SequenceNumber::from_value(1)), core::Timestamp::from_unix_nanoseconds(1), 1,
      AccountEventTruth::ModelDerived,
      AccountOrderAcknowledged{order, binding.trader_id, binding.contract_id, core::Side::Buy,
                               Require(core::Quantity::from_units(1)), price}}));
  const auto result = risk.apply(
      AccountEvent{Require(core::SequenceNumber::from_value(2)),
                   core::Timestamp::from_unix_nanoseconds(2), 0, AccountEventTruth::ModelDerived,
                   AccountFill{order, binding.trader_id, binding.contract_id, core::Side::Buy,
                               price, Require(core::Quantity::from_units(0))}});
  EXPECT_FALSE(result.has_value());
  EXPECT_EQ(risk.view().event_watermark, 1U);
  EXPECT_EQ(risk.live_orders().at(order).remaining_quantity.units(), 1U);
}

TEST(AccountRisk, RestoreRejectsDuplicateIngressAndExposureViolations) {
  const core::Market market = MakeMarket();
  const AccountBinding binding = Binding(market.contract().id());
  const auto quantity = Require(core::Quantity::from_units(1));
  const auto price = Require(core::Price::from_units(50));
  const OrderIntent first{Require(ClientIntentId::from_value(1)),
                          binding.contract_id,
                          core::Side::Buy,
                          quantity,
                          price,
                          true};
  const OrderIntent second{Require(ClientIntentId::from_value(2)),
                           binding.contract_id,
                           core::Side::Buy,
                           quantity,
                           price,
                           true};
  const RiskCheckpoint duplicate_ingress{0, 0, false, {}, {{first, 7}, {second, 7}}};
  EXPECT_FALSE(AccountRiskProjection::restore(binding, Limits(), duplicate_ingress).has_value());

  const RiskCheckpoint excessive_open{
      0,
      0,
      false,
      {{Require(core::OrderId::from_value(11)), core::Side::Buy, price,
        Require(core::Quantity::from_units(6)), core::Timestamp::from_unix_nanoseconds(1)}},
      {}};
  EXPECT_FALSE(AccountRiskProjection::restore(binding, Limits(), excessive_open).has_value());
}

}  // namespace
}  // namespace pmm::risk
