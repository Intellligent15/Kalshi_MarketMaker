#pragma once

#include <filesystem>
#include <optional>
#include <string>
#include <variant>
#include <vector>

#include "risk_conformance_common.hpp"

// Test-only reader for the versioned checkpoint/restore conformance corpus.  The schema is not
// a production serialization format: it exists so serialized risk state has reviewed, hashed,
// dual-implementation evidence.  The frozen V1 whitespace oracle never participates.
namespace pmm::risk_conformance {

struct CheckpointLiveOrder {
  std::uint64_t order_id;
  core::Side side;
  std::int64_t limit_price;
  std::int64_t remaining_quantity;
  std::int64_t acknowledged_at_utc_ns;
};

struct CheckpointPendingOrder {
  std::uint64_t client_intent_id;
  std::uint64_t contract_id;
  std::optional<std::uint64_t> ingress_sequence;
  core::Side side;
  std::int64_t limit_price;
  std::int64_t quantity;
  bool post_only;
};

// A pmm.risk_checkpoint.v1 document.  Input documents are validated for syntax and
// canonicality only: zero quantities, duplicate identifiers, non-post-only intents, and limit
// violations must remain expressible so AccountRiskProjection::restore can be shown to reject
// them.  Expected captured documents are additionally strict.
struct CheckpointDocument {
  std::uint64_t account_id;
  std::uint64_t strategy_id;
  std::uint64_t trader_id;
  std::uint64_t contract_id;
  Limits limits;
  std::uint64_t event_watermark;
  std::int64_t net_position;
  bool kill_switch_active;
  std::vector<CheckpointLiveOrder> live_orders;
  std::vector<CheckpointPendingOrder> pending_orders;
  Json document;
};

struct CaptureStep {};
struct RestoreStep {};
using CheckpointStep = std::variant<Operation, CaptureStep, RestoreStep>;

struct CheckpointTransition {
  std::string result;
  std::optional<CheckpointDocument> checkpoint;
  std::optional<ExpectedState> state;
};

enum class CheckpointFixtureKind { Roundtrip, DocumentRestore };

// Roundtrip fixtures build state through lifecycle operations, capture, restore, and continue
// against both projections.  Document-restore fixtures restore an authored checkpoint document;
// transitions[0] is the restore outcome and the remaining transitions follow `steps`.
struct CheckpointFixture {
  std::string fixture_id;
  CheckpointFixtureKind kind;
  std::uint64_t contract_id;
  Limits limits;
  std::optional<CheckpointDocument> checkpoint;
  std::vector<std::string> executors;
  std::vector<CheckpointStep> steps;
  std::vector<CheckpointTransition> transitions;
};

[[nodiscard]] std::filesystem::path CheckpointFixtureRoot();
[[nodiscard]] std::vector<CheckpointFixture> LoadCheckpointCorpus(
    const std::filesystem::path& root);
[[nodiscard]] bool HasCheckpointExecutor(const CheckpointFixture& fixture,
                                         const std::string& executor);
[[nodiscard]] std::string CheckpointStepName(const CheckpointStep& step);
[[nodiscard]] const std::set<std::string>& CheckpointRejectionResults();

}  // namespace pmm::risk_conformance
