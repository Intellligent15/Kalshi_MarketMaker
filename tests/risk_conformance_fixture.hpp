#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>
#include <type_traits>
#include <variant>
#include <vector>

#include "pmm/core/primitives.hpp"

namespace pmm::risk_conformance {

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

struct Fixture {
  std::string fixture_id;
  std::uint64_t contract_id;
  Limits limits;
  std::vector<std::string> executors;
  std::vector<Operation> operations;
  std::vector<ExpectedTransition> transitions;
};

[[nodiscard]] std::filesystem::path FixtureRoot();
[[nodiscard]] std::vector<Fixture> LoadCorpus(const std::filesystem::path& root);
[[nodiscard]] bool HasExecutor(const Fixture& fixture, const std::string& executor);
[[nodiscard]] std::string OperationName(const Operation& operation);

}  // namespace pmm::risk_conformance
