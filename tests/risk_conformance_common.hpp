#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <nlohmann/json.hpp>
#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <variant>
#include <vector>

#include "pmm/core/primitives.hpp"

// Test-only helpers shared by the risk-conformance fixture readers.  They are linked only into
// CTest targets; neither pmm_risk nor the frozen V1 oracle gains a JSON dependency.
namespace pmm::risk_conformance {

using Json = nlohmann::json;

struct Limits {
  std::int64_t maximum_order_quantity = 5;
  std::int64_t maximum_absolute_position = 5;
  std::int64_t maximum_buy_exposure = 5;
  std::int64_t maximum_sell_exposure = 5;
  std::int64_t maximum_pending_exposure = 5;
  std::size_t maximum_active_orders = 4;
};

struct AdmitOperation {
  std::uint64_t client_intent_id;
  std::uint64_t contract_id;
  core::Side side;
  std::int64_t quantity;
  std::int64_t limit_price;
};

struct BindIngressOperation {
  std::uint64_t client_intent_id;
  std::uint64_t ingress_sequence;
};

struct AcknowledgeOperation {
  std::uint64_t sequence;
  std::uint64_t ingress_sequence;
  std::uint64_t order_id;
  core::Side side;
  std::int64_t quantity;
  std::int64_t limit_price;
  std::int64_t time_utc_ns;
};

struct FillOperation {
  std::uint64_t sequence;
  std::uint64_t order_id;
  core::Side side;
  std::int64_t quantity;
  std::int64_t time_utc_ns;
};

struct CancelOperation {
  std::uint64_t sequence;
  std::uint64_t order_id;
  std::int64_t time_utc_ns;
};

struct CommandRejectedOperation {
  std::uint64_t sequence;
  std::uint64_t ingress_sequence;
  std::int64_t time_utc_ns;
};

struct KillSwitchOperation {
  bool active;
};

using Operation =
    std::variant<AdmitOperation, BindIngressOperation, AcknowledgeOperation, FillOperation,
                 CancelOperation, CommandRejectedOperation, KillSwitchOperation>;

struct ExpectedLiveOrder {
  std::uint64_t order_id;
  core::Side side;
  std::int64_t limit_price;
  std::int64_t remaining_quantity;
  std::int64_t acknowledged_at_utc_ns;
};

struct ExpectedPendingOrder {
  std::uint64_t client_intent_id;
  std::uint64_t contract_id;
  std::optional<std::uint64_t> ingress_sequence;
  core::Side side;
  std::int64_t limit_price;
  std::int64_t quantity;
};

struct ExpectedState {
  std::uint64_t event_watermark;
  std::int64_t net_position;
  std::int64_t open_buy_quantity;
  std::int64_t open_sell_quantity;
  std::int64_t pending_buy_quantity;
  std::int64_t pending_sell_quantity;
  bool kill_switch_active;
  std::vector<ExpectedLiveOrder> live_orders;
  std::vector<ExpectedPendingOrder> pending_orders;
};

struct ExpectedTransition {
  std::string result;
  ExpectedState state;
};

[[noreturn]] void Fail(const std::string& location, const std::string& message);
[[nodiscard]] std::string Sha256Hex(std::string_view input);
[[nodiscard]] std::string ReadFile(const std::filesystem::path& path);
[[nodiscard]] Json ReadCanonicalJson(const std::filesystem::path& path);
[[nodiscard]] std::string CanonicalDump(const Json& document);
void CheckKeys(const Json& value, const std::set<std::string>& required,
               const std::set<std::string>& optional, const std::string& location);
[[nodiscard]] std::string StringField(const Json& value, const char* key,
                                      const std::string& location);
[[nodiscard]] std::uint64_t UnsignedDecimal(const Json& value, const char* key,
                                            const std::string& location);
[[nodiscard]] std::int64_t NonnegativeInt64(const Json& value, const char* key,
                                            const std::string& location);
[[nodiscard]] std::int64_t SignedDecimal(const Json& value, const char* key,
                                         const std::string& location);
[[nodiscard]] core::Side SideField(const Json& value, const char* key, const std::string& location);
void RequirePositive(std::uint64_t value, const std::string& location);
[[nodiscard]] std::filesystem::path MemberPath(const std::filesystem::path& root,
                                               const std::string& name,
                                               const std::string& location);
void CheckHash(const std::string& expected, const std::string& bytes, const std::string& location);

[[nodiscard]] Limits ParseLimits(const Json& fixture, const std::string& location);
[[nodiscard]] Operation ParseOperation(const Json& operation, const std::string& location);
[[nodiscard]] ExpectedState ParseState(const Json& state, const std::string& location);
[[nodiscard]] std::string OperationName(const Operation& operation);
[[nodiscard]] const std::set<std::string>& LifecycleResults();

// One verified manifest entry: both member documents are canonical and hash-checked, and the
// corpus directory contains no unreferenced JSON documents.
struct ManifestEntry {
  std::string fixture_name;
  std::string trace_name;
  Json fixture_document;
  Json trace_document;
};

[[nodiscard]] std::vector<ManifestEntry> LoadManifestEntries(const std::filesystem::path& root,
                                                             const std::string& manifest_schema);

}  // namespace pmm::risk_conformance
