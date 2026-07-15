#include "risk_checkpoint_fixture.hpp"

#include <algorithm>
#include <cctype>
#include <set>
#include <string_view>
#include <type_traits>

namespace pmm::risk_conformance {
namespace {

constexpr std::string_view kCheckpointSchema = "pmm.risk_checkpoint.v1";
constexpr std::string_view kFixtureSchema = "pmm.risk_checkpoint_conformance_fixture.v1";
constexpr std::string_view kTraceSchema = "pmm.risk_checkpoint_conformance_expected_trace.v1";
constexpr std::string_view kManifestSchema = "pmm.risk_checkpoint_conformance_fixture_manifest.v1";

[[nodiscard]] Limits ParseRequiredLimits(const Json& object, const std::string& location) {
  CheckKeys(object,
            {"maximum_order_quantity_contracts", "maximum_absolute_position_contracts",
             "maximum_buy_exposure_contracts", "maximum_sell_exposure_contracts",
             "maximum_pending_exposure_contracts", "maximum_active_orders"},
            {}, location);
  Limits limits;
  const auto read_limit = [&object, &location](const char* key, std::int64_t* destination) {
    *destination = NonnegativeInt64(object, key, location);
    if (*destination == 0) {
      Fail(location + "." + key, "must be positive");
    }
  };
  read_limit("maximum_order_quantity_contracts", &limits.maximum_order_quantity);
  read_limit("maximum_absolute_position_contracts", &limits.maximum_absolute_position);
  read_limit("maximum_buy_exposure_contracts", &limits.maximum_buy_exposure);
  read_limit("maximum_sell_exposure_contracts", &limits.maximum_sell_exposure);
  read_limit("maximum_pending_exposure_contracts", &limits.maximum_pending_exposure);
  const Json& active = object.at("maximum_active_orders");
  if (!active.is_number_unsigned() || active.get<std::uint64_t>() == 0) {
    Fail(location + ".maximum_active_orders", "must be a positive unsigned JSON integer");
  }
  limits.maximum_active_orders = static_cast<std::size_t>(active.get<std::uint64_t>());
  return limits;
}

[[nodiscard]] bool SameLimits(const Limits& left, const Limits& right) {
  return left.maximum_order_quantity == right.maximum_order_quantity &&
         left.maximum_absolute_position == right.maximum_absolute_position &&
         left.maximum_buy_exposure == right.maximum_buy_exposure &&
         left.maximum_sell_exposure == right.maximum_sell_exposure &&
         left.maximum_pending_exposure == right.maximum_pending_exposure &&
         left.maximum_active_orders == right.maximum_active_orders;
}

// `strict` marks a reviewed expected capture: strictly sorted records, positive quantities,
// post-only intents, and nonzero ingress.  Input documents stay deliberately lax so semantic
// defects reach AccountRiskProjection::restore instead of being masked by the reader.
[[nodiscard]] CheckpointDocument ParseCheckpointDocument(const Json& document,
                                                         const std::string& location, bool strict) {
  CheckKeys(document,
            {"account_id", "contract_id", "event_watermark", "kill_switch_active", "limits",
             "live_orders", "net_position_contracts", "pending_orders", "schema", "strategy_id",
             "trader_id"},
            {}, location);
  if (StringField(document, "schema", location) != kCheckpointSchema) {
    Fail(location + ".schema", "must be the pmm.risk_checkpoint.v1 schema");
  }
  if (!document.at("kill_switch_active").is_boolean() || !document.at("live_orders").is_array() ||
      !document.at("pending_orders").is_array()) {
    Fail(location, "has invalid checkpoint container types");
  }
  CheckpointDocument parsed{UnsignedDecimal(document, "account_id", location),
                            UnsignedDecimal(document, "strategy_id", location),
                            UnsignedDecimal(document, "trader_id", location),
                            UnsignedDecimal(document, "contract_id", location),
                            ParseRequiredLimits(document.at("limits"), location + ".limits"),
                            UnsignedDecimal(document, "event_watermark", location),
                            SignedDecimal(document, "net_position_contracts", location),
                            document.at("kill_switch_active").get<bool>(),
                            {},
                            {},
                            document};
  RequirePositive(parsed.account_id, location + ".account_id");
  RequirePositive(parsed.strategy_id, location + ".strategy_id");
  RequirePositive(parsed.trader_id, location + ".trader_id");
  RequirePositive(parsed.contract_id, location + ".contract_id");
  std::uint64_t prior_order = 0;
  for (std::size_t index = 0; index < document.at("live_orders").size(); ++index) {
    const Json& order = document.at("live_orders").at(index);
    const std::string item_location = location + ".live_orders[" + std::to_string(index) + "]";
    CheckKeys(order,
              {"acknowledged_at_utc_ns", "limit_price_cents", "order_id",
               "remaining_quantity_contracts", "side"},
              {}, item_location);
    const std::uint64_t order_id = UnsignedDecimal(order, "order_id", item_location);
    RequirePositive(order_id, item_location + ".order_id");
    if (index != 0 && (strict ? order_id <= prior_order : order_id < prior_order)) {
      Fail(item_location + ".order_id", "must be canonically identifier-sorted");
    }
    prior_order = order_id;
    const std::int64_t quantity =
        NonnegativeInt64(order, "remaining_quantity_contracts", item_location);
    if (strict && quantity == 0) {
      Fail(item_location + ".remaining_quantity_contracts",
           "must be positive in a captured checkpoint");
    }
    parsed.live_orders.push_back(
        CheckpointLiveOrder{order_id, SideField(order, "side", item_location),
                            NonnegativeInt64(order, "limit_price_cents", item_location), quantity,
                            SignedDecimal(order, "acknowledged_at_utc_ns", item_location)});
  }
  std::uint64_t prior_client = 0;
  for (std::size_t index = 0; index < document.at("pending_orders").size(); ++index) {
    const Json& order = document.at("pending_orders").at(index);
    const std::string item_location = location + ".pending_orders[" + std::to_string(index) + "]";
    CheckKeys(order,
              {"client_intent_id", "contract_id", "ingress_sequence", "limit_price_cents",
               "post_only", "quantity_contracts", "side"},
              {}, item_location);
    const std::uint64_t client = UnsignedDecimal(order, "client_intent_id", item_location);
    const std::uint64_t contract = UnsignedDecimal(order, "contract_id", item_location);
    RequirePositive(client, item_location + ".client_intent_id");
    RequirePositive(contract, item_location + ".contract_id");
    if (index != 0 && (strict ? client <= prior_client : client < prior_client)) {
      Fail(item_location + ".client_intent_id", "must be canonically identifier-sorted");
    }
    prior_client = client;
    if (!order.at("post_only").is_boolean()) {
      Fail(item_location + ".post_only", "must be a boolean");
    }
    const bool post_only = order.at("post_only").get<bool>();
    if (strict && !post_only) {
      Fail(item_location + ".post_only", "must be true in a captured checkpoint");
    }
    std::optional<std::uint64_t> ingress;
    if (!order.at("ingress_sequence").is_null()) {
      ingress = UnsignedDecimal(order, "ingress_sequence", item_location);
      if (strict && *ingress == 0) {
        Fail(item_location + ".ingress_sequence", "must be positive in a captured checkpoint");
      }
    }
    const std::int64_t quantity = NonnegativeInt64(order, "quantity_contracts", item_location);
    if (strict && quantity == 0) {
      Fail(item_location + ".quantity_contracts", "must be positive in a captured checkpoint");
    }
    parsed.pending_orders.push_back(CheckpointPendingOrder{
        client, contract, ingress, SideField(order, "side", item_location),
        NonnegativeInt64(order, "limit_price_cents", item_location), quantity, post_only});
  }
  return parsed;
}

[[nodiscard]] std::vector<CheckpointStep> ParseSteps(const Json& operations,
                                                     CheckpointFixtureKind kind,
                                                     const std::string& location) {
  if (!operations.is_array()) {
    Fail(location, "must be an operation array");
  }
  std::vector<CheckpointStep> steps;
  bool saw_capture = false;
  for (std::size_t index = 0; index < operations.size(); ++index) {
    const Json& operation = operations.at(index);
    const std::string item_location = location + "[" + std::to_string(index) + "]";
    if (!operation.is_object() || !operation.contains("operation")) {
      Fail(item_location, "must be an operation object with an operation field");
    }
    const std::string name = StringField(operation, "operation", item_location);
    if (name == "checkpoint" || name == "restore") {
      if (kind != CheckpointFixtureKind::Roundtrip) {
        Fail(item_location + ".operation",
             "is only valid inside a roundtrip fixture operation list");
      }
      CheckKeys(operation, {"operation"}, {}, item_location);
      if (name == "checkpoint") {
        saw_capture = true;
        steps.emplace_back(CaptureStep{});
      } else {
        if (steps.empty() || !std::holds_alternative<CaptureStep>(steps.back())) {
          Fail(item_location + ".operation", "must immediately follow a checkpoint operation");
        }
        steps.emplace_back(RestoreStep{});
      }
      continue;
    }
    steps.emplace_back(ParseOperation(operation, item_location));
  }
  if (kind == CheckpointFixtureKind::Roundtrip && !saw_capture) {
    Fail(location, "must contain at least one checkpoint operation");
  }
  return steps;
}

void ParseRoundtripTrace(const Json& trace, CheckpointFixture& fixture,
                         const std::string& location) {
  const Json& transitions = trace.at("transitions");
  if (transitions.size() != fixture.steps.size()) {
    Fail(location, "must have one transition for every fixture operation");
  }
  for (std::size_t index = 0; index < transitions.size(); ++index) {
    const Json& transition = transitions.at(index);
    const std::string item_location = location + ".transitions[" + std::to_string(index) + "]";
    CheckpointTransition parsed{};
    if (std::holds_alternative<CaptureStep>(fixture.steps[index])) {
      CheckKeys(transition, {"checkpoint", "result", "state"}, {}, item_location);
      if (StringField(transition, "result", item_location) != "captured") {
        Fail(item_location + ".result", "must be 'captured' for a checkpoint operation");
      }
      CheckpointDocument document =
          ParseCheckpointDocument(transition.at("checkpoint"), item_location + ".checkpoint", true);
      if (document.account_id != 1 || document.strategy_id != 1 || document.trader_id != 1 ||
          document.contract_id != fixture.contract_id) {
        Fail(item_location + ".checkpoint", "must carry the fixture account identity");
      }
      if (!SameLimits(document.limits, fixture.limits)) {
        Fail(item_location + ".checkpoint.limits", "must equal the fixture limits");
      }
      parsed.result = "captured";
      parsed.checkpoint = std::move(document);
    } else if (std::holds_alternative<RestoreStep>(fixture.steps[index])) {
      CheckKeys(transition, {"result", "state"}, {}, item_location);
      if (StringField(transition, "result", item_location) != "restored") {
        Fail(item_location + ".result", "must be 'restored' for a restore operation");
      }
      parsed.result = "restored";
    } else {
      CheckKeys(transition, {"result", "state"}, {}, item_location);
      parsed.result = StringField(transition, "result", item_location);
      if (!LifecycleResults().contains(parsed.result)) {
        Fail(item_location + ".result", "is not a known fixture result");
      }
    }
    parsed.state = ParseState(transition.at("state"), item_location + ".state");
    fixture.transitions.push_back(std::move(parsed));
  }
}

void ParseDocumentRestoreTrace(const Json& trace, CheckpointFixture& fixture,
                               const std::string& location) {
  const Json& transitions = trace.at("transitions");
  if (transitions.size() != fixture.steps.size() + 1U) {
    Fail(location, "must have a restore transition plus one per continuation operation");
  }
  const Json& restore_transition = transitions.at(0);
  const std::string restore_location = location + ".transitions[0]";
  CheckpointTransition parsed{};
  parsed.result = StringField(restore_transition, "result", restore_location);
  if (CheckpointRejectionResults().contains(parsed.result)) {
    CheckKeys(restore_transition, {"result"}, {}, restore_location);
    if (!fixture.steps.empty()) {
      Fail(location, "must not continue after a rejected restore");
    }
    fixture.transitions.push_back(std::move(parsed));
    return;
  }
  if (parsed.result != "restored") {
    Fail(restore_location + ".result", "must be 'restored' or a checkpoint rejection");
  }
  CheckKeys(restore_transition, {"result", "state"}, {}, restore_location);
  parsed.state = ParseState(restore_transition.at("state"), restore_location + ".state");
  fixture.transitions.push_back(std::move(parsed));
  for (std::size_t index = 1; index < transitions.size(); ++index) {
    const Json& transition = transitions.at(index);
    const std::string item_location = location + ".transitions[" + std::to_string(index) + "]";
    CheckKeys(transition, {"result", "state"}, {}, item_location);
    CheckpointTransition continuation{};
    continuation.result = StringField(transition, "result", item_location);
    if (!LifecycleResults().contains(continuation.result)) {
      Fail(item_location + ".result", "is not a known fixture result");
    }
    continuation.state = ParseState(transition.at("state"), item_location + ".state");
    fixture.transitions.push_back(std::move(continuation));
  }
}

[[nodiscard]] CheckpointFixture ParseCheckpointFixture(const Json& document, const Json& trace,
                                                       const std::string& filename,
                                                       const std::string& expected_filename) {
  CheckKeys(document, {"fixture_id", "kind", "schema"},
            {"checkpoint", "contract_id", "executors", "limits", "operations"}, filename);
  if (StringField(document, "schema", filename) != kFixtureSchema) {
    Fail(filename, "has an invalid checkpoint fixture schema");
  }
  CheckpointFixture fixture{};
  fixture.fixture_id = StringField(document, "fixture_id", filename);
  fixture.contract_id = 1;
  if (fixture.fixture_id.empty() ||
      !std::all_of(
          fixture.fixture_id.begin(), fixture.fixture_id.end(), [](unsigned char character) {
            return std::islower(character) != 0 || std::isdigit(character) != 0 || character == '_';
          })) {
    Fail(filename + ".fixture_id", "must use lowercase letters, digits, and underscores");
  }
  if (filename != fixture.fixture_id + ".json" ||
      expected_filename != fixture.fixture_id + ".expected.json") {
    Fail(filename, "member names must match the fixture identifier");
  }
  const std::string kind = StringField(document, "kind", filename);
  if (kind == "roundtrip") {
    fixture.kind = CheckpointFixtureKind::Roundtrip;
    if (document.contains("checkpoint")) {
      Fail(filename + ".checkpoint", "is only valid in a document_restore fixture");
    }
    if (!document.contains("operations")) {
      Fail(filename, "is missing required field 'operations'");
    }
    if (document.contains("contract_id")) {
      fixture.contract_id = UnsignedDecimal(document, "contract_id", filename);
      RequirePositive(fixture.contract_id, filename + ".contract_id");
    }
    fixture.limits = ParseLimits(document, filename);
  } else if (kind == "document_restore") {
    fixture.kind = CheckpointFixtureKind::DocumentRestore;
    if (document.contains("contract_id") || document.contains("limits")) {
      Fail(filename, "must take identity and limits from its checkpoint document");
    }
    if (!document.contains("checkpoint")) {
      Fail(filename, "is missing required field 'checkpoint'");
    }
    fixture.checkpoint =
        ParseCheckpointDocument(document.at("checkpoint"), filename + ".checkpoint", false);
    fixture.contract_id = fixture.checkpoint->contract_id;
    fixture.limits = fixture.checkpoint->limits;
  } else {
    Fail(filename + ".kind", "must be 'roundtrip' or 'document_restore'");
  }
  static const std::set<std::string> kExecutors{"direct_cpp", "python_reference"};
  if (document.contains("executors")) {
    if (!document.at("executors").is_array() || document.at("executors").empty()) {
      Fail(filename + ".executors", "must be a non-empty executor array");
    }
    std::set<std::string> seen_executors;
    for (const Json& executor : document.at("executors")) {
      if (!executor.is_string() || !kExecutors.contains(executor.get<std::string>()) ||
          !seen_executors.insert(executor.get<std::string>()).second) {
        Fail(filename + ".executors",
             "must contain unique checkpoint executor names; the V1 oracle is frozen");
      }
      fixture.executors.push_back(executor.get<std::string>());
    }
  } else {
    fixture.executors = {"direct_cpp", "python_reference"};
  }
  if (document.contains("operations")) {
    fixture.steps = ParseSteps(document.at("operations"), fixture.kind, filename + ".operations");
    if (fixture.kind == CheckpointFixtureKind::Roundtrip && fixture.steps.empty()) {
      Fail(filename + ".operations", "must not be empty");
    }
  }

  CheckKeys(trace, {"fixture_id", "schema", "transitions"}, {}, expected_filename);
  if (StringField(trace, "schema", expected_filename) != kTraceSchema ||
      StringField(trace, "fixture_id", expected_filename) != fixture.fixture_id ||
      !trace.at("transitions").is_array()) {
    Fail(expected_filename, "has an invalid expected-trace identity or transitions field");
  }
  if (fixture.kind == CheckpointFixtureKind::Roundtrip) {
    ParseRoundtripTrace(trace, fixture, expected_filename);
  } else {
    ParseDocumentRestoreTrace(trace, fixture, expected_filename);
  }
  return fixture;
}

}  // namespace

std::filesystem::path CheckpointFixtureRoot() {
  return std::filesystem::path(PMM_SOURCE_DIR) / "python" / "tests" / "fixtures" /
         "risk_conformance" / "checkpoint_v1";
}

std::vector<CheckpointFixture> LoadCheckpointCorpus(const std::filesystem::path& root) {
  std::vector<CheckpointFixture> fixtures;
  for (const ManifestEntry& entry : LoadManifestEntries(root, std::string(kManifestSchema))) {
    fixtures.push_back(ParseCheckpointFixture(entry.fixture_document, entry.trace_document,
                                              entry.fixture_name, entry.trace_name));
  }
  return fixtures;
}

bool HasCheckpointExecutor(const CheckpointFixture& fixture, const std::string& executor) {
  return std::find(fixture.executors.begin(), fixture.executors.end(), executor) !=
         fixture.executors.end();
}

std::string CheckpointStepName(const CheckpointStep& step) {
  return std::visit(
      [](const auto& value) -> std::string {
        using T = std::decay_t<decltype(value)>;
        if constexpr (std::is_same_v<T, CaptureStep>) {
          return "checkpoint";
        } else if constexpr (std::is_same_v<T, RestoreStep>) {
          return "restore";
        } else {
          return OperationName(value);
        }
      },
      step);
}

const std::set<std::string>& CheckpointRejectionResults() {
  static const std::set<std::string> kResults{
      "checkpoint_active_order_limit",     "checkpoint_buy_exposure_limit",
      "checkpoint_contract_mismatch",      "checkpoint_duplicate_client_intent",
      "checkpoint_duplicate_ingress",      "checkpoint_duplicate_order_id",
      "checkpoint_non_post_only",          "checkpoint_order_quantity_limit",
      "checkpoint_pending_exposure_limit", "checkpoint_position_limit",
      "checkpoint_sell_exposure_limit",    "checkpoint_zero_ingress",
      "checkpoint_zero_live_quantity",     "checkpoint_zero_pending_quantity"};
  return kResults;
}

}  // namespace pmm::risk_conformance
