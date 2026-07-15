#include <gtest/gtest.h>

#include <chrono>
#include <filesystem>
#include <fstream>
#include <functional>
#include <optional>
#include <string>
#include <string_view>
#include <utility>

#include "pmm/risk/account_risk.hpp"
#include "risk_checkpoint_fixture.hpp"
#include "risk_conformance_executor.hpp"

namespace pmm::risk_conformance {
namespace {

using Path = std::filesystem::path;

template <typename T>
T Require(core::Result<T> result) {
  EXPECT_TRUE(result.has_value()) << result.error().message;
  return std::move(result).value();
}

[[nodiscard]] risk::AccountBinding BindingFromDocument(const CheckpointDocument& document) {
  return risk::AccountBinding{Require(risk::AccountId::from_value(document.account_id)),
                              Require(risk::StrategyId::from_value(document.strategy_id)),
                              Require(core::TraderId::from_value(document.trader_id)),
                              Require(core::ContractId::from_value(document.contract_id))};
}

[[nodiscard]] risk::RiskCheckpoint ToRiskCheckpoint(const CheckpointDocument& document) {
  risk::RiskCheckpoint checkpoint{
      document.event_watermark, document.net_position, document.kill_switch_active, {}, {}};
  for (const CheckpointLiveOrder& order : document.live_orders) {
    checkpoint.live_orders.push_back(
        risk::LiveRiskOrder{Require(core::OrderId::from_value(order.order_id)), order.side,
                            Require(core::Price::from_units(order.limit_price)),
                            Require(core::Quantity::from_units(order.remaining_quantity)),
                            core::Timestamp::from_unix_nanoseconds(order.acknowledged_at_utc_ns)});
  }
  for (const CheckpointPendingOrder& pending : document.pending_orders) {
    checkpoint.pending_orders.push_back(risk::PendingRiskOrder{
        risk::OrderIntent{Require(risk::ClientIntentId::from_value(pending.client_intent_id)),
                          Require(core::ContractId::from_value(pending.contract_id)), pending.side,
                          Require(core::Quantity::from_units(pending.quantity)),
                          Require(core::Price::from_units(pending.limit_price)), pending.post_only},
        pending.ingress_sequence});
  }
  return checkpoint;
}

// The canonical test-only serialization of a projection checkpoint.  Captured bytes must equal
// the reviewed pmm.risk_checkpoint.v1 document exactly.
[[nodiscard]] Json SerializeCheckpoint(const risk::AccountBinding& binding, const Limits& limits,
                                       const risk::RiskCheckpoint& checkpoint) {
  Json document;
  document["schema"] = "pmm.risk_checkpoint.v1";
  document["account_id"] = std::to_string(binding.account_id.value());
  document["strategy_id"] = std::to_string(binding.strategy_id.value());
  document["trader_id"] = std::to_string(binding.trader_id.value());
  document["contract_id"] = std::to_string(binding.contract_id.value());
  Json limits_object;
  limits_object["maximum_order_quantity_contracts"] = std::to_string(limits.maximum_order_quantity);
  limits_object["maximum_absolute_position_contracts"] =
      std::to_string(limits.maximum_absolute_position);
  limits_object["maximum_buy_exposure_contracts"] = std::to_string(limits.maximum_buy_exposure);
  limits_object["maximum_sell_exposure_contracts"] = std::to_string(limits.maximum_sell_exposure);
  limits_object["maximum_pending_exposure_contracts"] =
      std::to_string(limits.maximum_pending_exposure);
  limits_object["maximum_active_orders"] = static_cast<std::uint64_t>(limits.maximum_active_orders);
  document["limits"] = std::move(limits_object);
  document["event_watermark"] = std::to_string(checkpoint.event_watermark);
  document["net_position_contracts"] = std::to_string(checkpoint.net_position);
  document["kill_switch_active"] = checkpoint.kill_switch_active;
  document["live_orders"] = Json::array();
  for (const risk::LiveRiskOrder& order : checkpoint.live_orders) {
    Json record;
    record["order_id"] = std::to_string(order.order_id.value());
    record["side"] = order.side == core::Side::Buy ? "buy" : "sell";
    record["limit_price_cents"] = std::to_string(order.price.units());
    record["remaining_quantity_contracts"] = std::to_string(order.remaining_quantity.units());
    record["acknowledged_at_utc_ns"] = std::to_string(order.acknowledged_at.unix_nanoseconds());
    document["live_orders"].push_back(std::move(record));
  }
  document["pending_orders"] = Json::array();
  for (const risk::PendingRiskOrder& pending : checkpoint.pending_orders) {
    Json record;
    record["client_intent_id"] = std::to_string(pending.intent.client_intent_id.value());
    record["contract_id"] = std::to_string(pending.intent.contract_id.value());
    if (pending.ingress_sequence.has_value()) {
      record["ingress_sequence"] = std::to_string(*pending.ingress_sequence);
    } else {
      record["ingress_sequence"] = nullptr;
    }
    record["side"] = pending.intent.side == core::Side::Buy ? "buy" : "sell";
    record["limit_price_cents"] = std::to_string(pending.intent.limit_price.units());
    record["quantity_contracts"] = std::to_string(pending.intent.quantity.units());
    record["post_only"] = pending.intent.post_only;
    document["pending_orders"].push_back(std::move(record));
  }
  return document;
}

[[nodiscard]] std::string SerializedProjection(const risk::AccountRiskProjection& projection,
                                               const Limits& limits) {
  return CanonicalDump(SerializeCheckpoint(projection.binding(), limits, projection.checkpoint()));
}

[[nodiscard]] std::string RunRoundtrip(const CheckpointFixture& fixture) {
  std::string log;
  risk::AccountRiskProjection original = Require(risk::AccountRiskProjection::create(
      MakeBinding(fixture.contract_id), ToRiskLimits(fixture.limits)));
  std::optional<risk::AccountRiskProjection> restored;
  const CheckpointDocument* last_capture = nullptr;
  for (std::size_t index = 0; index < fixture.steps.size(); ++index) {
    SCOPED_TRACE("transition " + std::to_string(index) + " " +
                 CheckpointStepName(fixture.steps[index]));
    const CheckpointTransition& transition = fixture.transitions[index];
    if (std::holds_alternative<CaptureStep>(fixture.steps[index])) {
      const std::string expected_bytes = CanonicalDump(transition.checkpoint->document);
      const std::string original_bytes = SerializedProjection(original, fixture.limits);
      EXPECT_EQ(original_bytes, expected_bytes);
      if (restored.has_value()) {
        EXPECT_EQ(SerializedProjection(*restored, fixture.limits), expected_bytes);
      }
      last_capture = &*transition.checkpoint;
      log += "captured " + original_bytes;
    } else if (std::holds_alternative<RestoreStep>(fixture.steps[index])) {
      if (last_capture == nullptr) {
        ADD_FAILURE() << "restore without a captured checkpoint";
        return log;
      }
      const risk::AccountBinding binding = BindingFromDocument(*last_capture);
      const risk::RiskLimits limits = ToRiskLimits(last_capture->limits);
      const risk::RiskCheckpoint checkpoint = ToRiskCheckpoint(*last_capture);
      EXPECT_FALSE(risk::AccountRiskProjection::validate_checkpoint(binding, limits, checkpoint)
                       .has_value());
      auto result = risk::AccountRiskProjection::restore(binding, limits, checkpoint);
      if (!result.has_value()) {
        ADD_FAILURE() << "restore failed: " << result.error().message;
        return log;
      }
      restored.emplace(std::move(result).value());
      EXPECT_EQ(SerializedProjection(*restored, fixture.limits),
                SerializedProjection(original, fixture.limits));
      log += "restored ";
    } else {
      const Operation& operation = std::get<Operation>(fixture.steps[index]);
      const std::string result = ApplyOperation(original, operation);
      EXPECT_EQ(result, transition.result);
      if (restored.has_value()) {
        EXPECT_EQ(ApplyOperation(*restored, operation), result);
        EXPECT_EQ(SerializedProjection(*restored, fixture.limits),
                  SerializedProjection(original, fixture.limits));
      }
      log += result + " ";
    }
    ExpectState(original, *transition.state);
    if (restored.has_value()) {
      ExpectState(*restored, *transition.state);
    }
  }
  return log;
}

[[nodiscard]] std::string RunDocumentRestore(const CheckpointFixture& fixture) {
  std::string log;
  const CheckpointDocument& document = *fixture.checkpoint;
  const risk::AccountBinding binding = BindingFromDocument(document);
  const risk::RiskLimits limits = ToRiskLimits(document.limits);
  const risk::RiskCheckpoint checkpoint = ToRiskCheckpoint(document);
  const auto rejection =
      risk::AccountRiskProjection::validate_checkpoint(binding, limits, checkpoint);
  auto restored = risk::AccountRiskProjection::restore(binding, limits, checkpoint);
  EXPECT_EQ(restored.has_value(), !rejection.has_value());
  const std::string result =
      rejection.has_value() ? CheckpointRejectionResult(rejection->code) : "restored";
  EXPECT_EQ(result, fixture.transitions[0].result);
  log += result + " ";
  if (rejection.has_value() || !restored.has_value()) {
    return log;
  }
  risk::AccountRiskProjection projection = std::move(restored).value();
  ExpectState(projection, *fixture.transitions[0].state);
  log += SerializedProjection(projection, document.limits);
  for (std::size_t index = 0; index < fixture.steps.size(); ++index) {
    SCOPED_TRACE("transition " + std::to_string(index + 1) + " " +
                 CheckpointStepName(fixture.steps[index]));
    const CheckpointTransition& transition = fixture.transitions[index + 1];
    const std::string continuation =
        ApplyOperation(projection, std::get<Operation>(fixture.steps[index]));
    EXPECT_EQ(continuation, transition.result);
    ExpectState(projection, *transition.state);
    log += " " + continuation;
  }
  return log;
}

[[nodiscard]] std::string RunFixture(const CheckpointFixture& fixture) {
  return fixture.kind == CheckpointFixtureKind::Roundtrip ? RunRoundtrip(fixture)
                                                          : RunDocumentRestore(fixture);
}

TEST(RiskCheckpointConformance, VerifiesEveryCheckedInDocument) {
  EXPECT_NO_THROW({
    const std::vector<CheckpointFixture> fixtures = LoadCheckpointCorpus(CheckpointFixtureRoot());
    EXPECT_EQ(fixtures.size(), 26U);
  });
}

TEST(RiskCheckpointConformance, DirectCppMatchesEveryReviewedTransition) {
  for (const CheckpointFixture& fixture : LoadCheckpointCorpus(CheckpointFixtureRoot())) {
    if (!HasCheckpointExecutor(fixture, "direct_cpp")) {
      continue;
    }
    SCOPED_TRACE(fixture.fixture_id);
    static_cast<void>(RunFixture(fixture));
  }
}

TEST(RiskCheckpointConformance, ReplayIsByteIdentical) {
  for (const CheckpointFixture& fixture : LoadCheckpointCorpus(CheckpointFixtureRoot())) {
    if (!HasCheckpointExecutor(fixture, "direct_cpp")) {
      continue;
    }
    SCOPED_TRACE(fixture.fixture_id);
    EXPECT_EQ(RunFixture(fixture), RunFixture(fixture));
  }
}

// --- Negative matrix -------------------------------------------------------------------------
//
// Each test copies the reviewed corpus to a temporary directory, breaks exactly one declared
// verifier rule, and requires the loader to reject the whole corpus.

class TemporaryCorpus final {
 public:
  TemporaryCorpus() {
    const auto nonce = std::chrono::steady_clock::now().time_since_epoch().count();
    root_ =
        std::filesystem::temp_directory_path() / ("pmm-risk-checkpoint-" + std::to_string(nonce));
    std::filesystem::copy(CheckpointFixtureRoot(), root_, std::filesystem::copy_options::recursive);
  }
  TemporaryCorpus(const TemporaryCorpus&) = delete;
  TemporaryCorpus& operator=(const TemporaryCorpus&) = delete;
  ~TemporaryCorpus() {
    std::error_code error;
    std::filesystem::remove_all(root_, error);
  }

  [[nodiscard]] const Path& root() const {
    return root_;
  }

  [[nodiscard]] Json Load(const std::string& name) const {
    return Json::parse(ReadFile(root_ / name));
  }

  void Write(const std::string& name, const Json& document) const {
    WriteBytes(name, CanonicalDump(document));
  }

  void WriteBytes(const std::string& name, const std::string& bytes) const {
    std::ofstream output(root_ / name, std::ios::binary | std::ios::trunc);
    ASSERT_TRUE(output.good());
    output << bytes;
  }

  // Recompute every member hash and the payload hash after a document mutation.
  void RehashManifest() const {
    Json manifest = Load("manifest.json");
    for (Json& entry : manifest.at("payload").at("entries")) {
      entry["fixture_sha256"] = Sha256Hex(ReadFile(root_ / entry.at("fixture").get<std::string>()));
      entry["expected_trace_sha256"] =
          Sha256Hex(ReadFile(root_ / entry.at("expected_trace").get<std::string>()));
    }
    manifest["payload_sha256"] = Sha256Hex(CanonicalDump(manifest.at("payload")));
    Write("manifest.json", manifest);
  }

  // Recompute only the payload hash so manifest-entry mutations stay internally consistent.
  void RehashPayloadOnly(Json manifest) const {
    manifest["payload_sha256"] = Sha256Hex(CanonicalDump(manifest.at("payload")));
    Write("manifest.json", manifest);
  }

  void ExpectRejected() const {
    EXPECT_THROW(static_cast<void>(LoadCheckpointCorpus(root_)), std::runtime_error);
  }

  void ExpectRejectedAt(std::string_view expected_diagnostic) const {
    try {
      static_cast<void>(LoadCheckpointCorpus(root_));
      ADD_FAILURE() << "expected corpus rejection containing: " << expected_diagnostic;
    } catch (const std::runtime_error& error) {
      EXPECT_NE(std::string(error.what()).find(expected_diagnostic), std::string::npos)
          << "unexpected corpus rejection: " << error.what();
    }
  }

 private:
  Path root_;
};

TEST(RiskCheckpointConformance, RejectsTamperedNoncanonicalMember) {
  TemporaryCorpus corpus;
  std::ofstream output(corpus.root() / "roundtrip_empty_state.json",
                       std::ios::app | std::ios::binary);
  ASSERT_TRUE(output.good());
  output << ' ';
  output.close();
  corpus.ExpectRejected();
}

TEST(RiskCheckpointConformance, RejectsEveryInvalidStrictCapturedCheckpointField) {
  struct Mutation {
    std::string name;
    std::function<void(Json&)> apply;
    std::string expected_diagnostic;
  };
  const std::vector<Mutation> mutations{
      {"account identity", [](Json& checkpoint) { checkpoint["account_id"] = "2"; },
       ".transitions[5].checkpoint: must carry the fixture account identity"},
      {"strategy identity", [](Json& checkpoint) { checkpoint["strategy_id"] = "2"; },
       ".transitions[5].checkpoint: must carry the fixture account identity"},
      {"trader identity", [](Json& checkpoint) { checkpoint["trader_id"] = "2"; },
       ".transitions[5].checkpoint: must carry the fixture account identity"},
      {"contract identity", [](Json& checkpoint) { checkpoint["contract_id"] = "2"; },
       ".transitions[5].checkpoint: must carry the fixture account identity"},
      {"maximum order quantity limit",
       [](Json& checkpoint) { checkpoint["limits"]["maximum_order_quantity_contracts"] = "6"; },
       ".transitions[5].checkpoint.limits: must equal the fixture limits"},
      {"maximum absolute position limit",
       [](Json& checkpoint) { checkpoint["limits"]["maximum_absolute_position_contracts"] = "6"; },
       ".transitions[5].checkpoint.limits: must equal the fixture limits"},
      {"maximum buy exposure limit",
       [](Json& checkpoint) { checkpoint["limits"]["maximum_buy_exposure_contracts"] = "6"; },
       ".transitions[5].checkpoint.limits: must equal the fixture limits"},
      {"maximum sell exposure limit",
       [](Json& checkpoint) { checkpoint["limits"]["maximum_sell_exposure_contracts"] = "6"; },
       ".transitions[5].checkpoint.limits: must equal the fixture limits"},
      {"maximum pending exposure limit",
       [](Json& checkpoint) { checkpoint["limits"]["maximum_pending_exposure_contracts"] = "6"; },
       ".transitions[5].checkpoint.limits: must equal the fixture limits"},
      {"maximum active orders limit",
       [](Json& checkpoint) { checkpoint["limits"]["maximum_active_orders"] = 5; },
       ".transitions[5].checkpoint.limits: must equal the fixture limits"},
      {"strict live order sorting",
       [](Json& checkpoint) { checkpoint["live_orders"].push_back(checkpoint["live_orders"][0]); },
       ".transitions[5].checkpoint.live_orders[1].order_id: must be canonically "
       "identifier-sorted"},
      {"strict pending order sorting",
       [](Json& checkpoint) {
         checkpoint["pending_orders"].push_back(checkpoint["pending_orders"][0]);
       },
       ".transitions[5].checkpoint.pending_orders[1].client_intent_id: must be canonically "
       "identifier-sorted"},
      {"positive live quantity",
       [](Json& checkpoint) { checkpoint["live_orders"][0]["remaining_quantity_contracts"] = "0"; },
       ".transitions[5].checkpoint.live_orders[0].remaining_quantity_contracts: must be positive "
       "in a captured checkpoint"},
      {"positive pending quantity",
       [](Json& checkpoint) { checkpoint["pending_orders"][0]["quantity_contracts"] = "0"; },
       ".transitions[5].checkpoint.pending_orders[0].quantity_contracts: must be positive in a "
       "captured checkpoint"},
      {"post-only pending intent",
       [](Json& checkpoint) { checkpoint["pending_orders"][0]["post_only"] = false; },
       ".transitions[5].checkpoint.pending_orders[0].post_only: must be true in a captured "
       "checkpoint"},
      {"positive bound ingress",
       [](Json& checkpoint) { checkpoint["pending_orders"][0]["ingress_sequence"] = "0"; },
       ".transitions[5].checkpoint.pending_orders[0].ingress_sequence: must be positive in a "
       "captured checkpoint"},
  };

  for (const Mutation& mutation : mutations) {
    SCOPED_TRACE(mutation.name);
    TemporaryCorpus corpus;
    Json trace = corpus.Load("roundtrip_live_and_pending.expected.json");
    mutation.apply(trace["transitions"][5]["checkpoint"]);
    corpus.Write("roundtrip_live_and_pending.expected.json", trace);
    corpus.RehashManifest();
    corpus.ExpectRejectedAt(mutation.expected_diagnostic);
  }
}

TEST(RiskCheckpointConformance, RejectsUnknownFixtureField) {
  TemporaryCorpus corpus;
  Json fixture = corpus.Load("roundtrip_empty_state.json");
  fixture["surprise"] = "1";
  corpus.Write("roundtrip_empty_state.json", fixture);
  corpus.RehashManifest();
  corpus.ExpectRejected();
}

TEST(RiskCheckpointConformance, RejectsMissingKindField) {
  TemporaryCorpus corpus;
  Json fixture = corpus.Load("roundtrip_empty_state.json");
  fixture.erase("kind");
  corpus.Write("roundtrip_empty_state.json", fixture);
  corpus.RehashManifest();
  corpus.ExpectRejected();
}

TEST(RiskCheckpointConformance, RejectsNoncanonicalDecimalValue) {
  TemporaryCorpus corpus;
  Json fixture = corpus.Load("checkpoint_zero_ingress.json");
  fixture["checkpoint"]["event_watermark"] = "01";
  corpus.Write("checkpoint_zero_ingress.json", fixture);
  corpus.RehashManifest();
  corpus.ExpectRejected();
}

TEST(RiskCheckpointConformance, RejectsNumericJsonWhereDecimalStringRequired) {
  TemporaryCorpus corpus;
  Json fixture = corpus.Load("checkpoint_zero_ingress.json");
  fixture["checkpoint"]["net_position_contracts"] = 1;
  corpus.Write("checkpoint_zero_ingress.json", fixture);
  corpus.RehashManifest();
  corpus.ExpectRejected();
}

TEST(RiskCheckpointConformance, RejectsUnknownSide) {
  TemporaryCorpus corpus;
  Json fixture = corpus.Load("checkpoint_buy_exposure_limit.json");
  fixture["checkpoint"]["live_orders"][0]["side"] = "hold";
  corpus.Write("checkpoint_buy_exposure_limit.json", fixture);
  corpus.RehashManifest();
  corpus.ExpectRejected();
}

TEST(RiskCheckpointConformance, RejectsDecreasingCheckpointIdentifiers) {
  TemporaryCorpus corpus;
  Json fixture = corpus.Load("checkpoint_active_order_limit.json");
  Json& orders = fixture["checkpoint"]["live_orders"];
  std::swap(orders[0], orders[1]);
  corpus.Write("checkpoint_active_order_limit.json", fixture);
  corpus.RehashManifest();
  corpus.ExpectRejected();
}

TEST(RiskCheckpointConformance, RejectsWrongCheckpointSchema) {
  TemporaryCorpus corpus;
  Json fixture = corpus.Load("checkpoint_zero_ingress.json");
  fixture["checkpoint"]["schema"] = "pmm.risk_checkpoint.v2";
  corpus.Write("checkpoint_zero_ingress.json", fixture);
  corpus.RehashManifest();
  corpus.ExpectRejected();
}

TEST(RiskCheckpointConformance, RejectsBadMemberHash) {
  TemporaryCorpus corpus;
  Json manifest = corpus.Load("manifest.json");
  manifest["payload"]["entries"][0]["fixture_sha256"] = std::string(64, 'a');
  corpus.RehashPayloadOnly(std::move(manifest));
  corpus.ExpectRejected();
}

TEST(RiskCheckpointConformance, RejectsBadPayloadHash) {
  TemporaryCorpus corpus;
  Json manifest = corpus.Load("manifest.json");
  manifest["payload_sha256"] = std::string(64, 'a');
  corpus.Write("manifest.json", manifest);
  corpus.ExpectRejected();
}

TEST(RiskCheckpointConformance, RejectsUnsafeMemberPath) {
  TemporaryCorpus corpus;
  Json manifest = corpus.Load("manifest.json");
  manifest["payload"]["entries"][0]["fixture"] = "../escape.json";
  corpus.RehashPayloadOnly(std::move(manifest));
  corpus.ExpectRejected();
}

TEST(RiskCheckpointConformance, RejectsSymlinkMember) {
  TemporaryCorpus corpus;
  const Path member = corpus.root() / "roundtrip_empty_state.json";
  const Path hidden = corpus.root() / "real_bytes";
  std::filesystem::rename(member, hidden);
  std::filesystem::create_symlink(hidden, member);
  corpus.ExpectRejected();
}

TEST(RiskCheckpointConformance, RejectsDuplicateManifestMember) {
  TemporaryCorpus corpus;
  Json manifest = corpus.Load("manifest.json");
  Json& entries = manifest["payload"]["entries"];
  ASSERT_GE(entries.size(), 2U);
  entries[1]["expected_trace"] = entries[0]["expected_trace"];
  entries[1]["expected_trace_sha256"] = entries[0]["expected_trace_sha256"];
  corpus.RehashPayloadOnly(std::move(manifest));
  corpus.ExpectRejected();
}

TEST(RiskCheckpointConformance, RejectsUnreferencedJsonDocument) {
  TemporaryCorpus corpus;
  corpus.WriteBytes("extra.json", "{}\n");
  corpus.ExpectRejected();
}

TEST(RiskCheckpointConformance, RejectsRestoreWithoutPrecedingCheckpoint) {
  TemporaryCorpus corpus;
  Json fixture = corpus.Load("roundtrip_empty_state.json");
  Json& operations = fixture["operations"];
  operations.insert(operations.begin(), Json{{"operation", "restore"}});
  corpus.Write("roundtrip_empty_state.json", fixture);
  corpus.RehashManifest();
  corpus.ExpectRejected();
}

TEST(RiskCheckpointConformance, RejectsRejectedRestoreTransitionWithState) {
  TemporaryCorpus corpus;
  const Json donor = corpus.Load("document_restore_unbound_pending.expected.json");
  Json trace = corpus.Load("checkpoint_zero_ingress.expected.json");
  trace["transitions"][0]["state"] = donor["transitions"][0]["state"];
  corpus.Write("checkpoint_zero_ingress.expected.json", trace);
  corpus.RehashManifest();
  corpus.ExpectRejected();
}

TEST(RiskCheckpointConformance, RejectsContinuationAfterRejectedRestore) {
  TemporaryCorpus corpus;
  const Json donor = corpus.Load("document_restore_unbound_pending.expected.json");
  Json fixture = corpus.Load("checkpoint_zero_ingress.json");
  fixture["operations"] = Json::array({Json{{"operation", "kill_switch"}, {"active", true}}});
  Json trace = corpus.Load("checkpoint_zero_ingress.expected.json");
  Json continuation;
  continuation["result"] = "applied";
  continuation["state"] = donor["transitions"][0]["state"];
  trace["transitions"].push_back(std::move(continuation));
  corpus.Write("checkpoint_zero_ingress.json", fixture);
  corpus.Write("checkpoint_zero_ingress.expected.json", trace);
  corpus.RehashManifest();
  corpus.ExpectRejected();
}

TEST(RiskCheckpointConformance, RejectsFrozenV1OracleExecutor) {
  TemporaryCorpus corpus;
  Json fixture = corpus.Load("roundtrip_empty_state.json");
  fixture["executors"] = Json::array({"v1_oracle"});
  corpus.Write("roundtrip_empty_state.json", fixture);
  corpus.RehashManifest();
  corpus.ExpectRejected();
}

}  // namespace
}  // namespace pmm::risk_conformance
