#pragma once

#include <cstddef>
#include <cstdint>
#include <map>
#include <memory>
#include <optional>
#include <variant>
#include <vector>

#include "pmm/book/order_book.hpp"

namespace pmm::sim {

struct SubmitOrderRequest {
  core::TraderId trader_id;
  core::ContractId contract_id;
  core::Side side;
  core::OrderType type;
  core::Quantity quantity;
  std::optional<core::Price> limit_price;
  core::Timestamp submitted_at;
  // A post-only order is rejected before matching if it would take displayed liquidity.
  bool post_only = false;
};

struct CancelOrderRequest {
  core::TraderId trader_id;
  core::ContractId contract_id;
  core::OrderId order_id;
};

struct MarketLifecycleCommand {
  core::MarketId market_id;
  core::MarketStatus target_status;
};

using ExchangeCommand =
    std::variant<SubmitOrderRequest, CancelOrderRequest, MarketLifecycleCommand>;

struct ScheduledCommand {
  core::Timestamp scheduled_at;
  std::uint64_t ingress_sequence;
  ExchangeCommand command;
};

struct OrderAcknowledged {
  core::Order order;
};

struct TradeExecuted {
  book::Execution execution;
};

struct OrderOutcome {
  book::OrderUpdate update;
};

struct CancellationAcknowledged {
  book::OrderUpdate update;
};

struct MarketStatusChanged {
  core::MarketId market_id;
  core::MarketStatus previous_status;
  core::MarketStatus current_status;
};

struct PriceLevelDelta {
  core::Side side;
  core::Price price;
  core::Quantity total_quantity;
  std::size_t order_count;
};

struct BookDepthChanged {
  core::ContractId contract_id;
  std::vector<PriceLevelDelta> levels;
};

struct CommandRejected {
  core::DomainError error;
};

using ExchangeEventPayload =
    std::variant<OrderAcknowledged, TradeExecuted, OrderOutcome, CancellationAcknowledged,
                 MarketStatusChanged, BookDepthChanged, CommandRejected>;

struct ExchangeEvent {
  core::SequenceNumber sequence;
  core::Timestamp occurred_at;
  // Exchange-owned correlation for every event emitted by one ingress command.
  std::uint64_t ingress_sequence;
  ExchangeEventPayload payload;
};

struct MarketCheckpoint {
  core::Market market;
  core::MarketStatus status;
  book::BookCheckpoint book;
};

struct ExchangeCheckpoint {
  std::optional<core::Timestamp> current_time;
  std::uint64_t next_order_id;
  std::uint64_t next_trade_id;
  std::uint64_t next_event_sequence;
  std::uint64_t next_ingress_sequence;
  std::vector<MarketCheckpoint> markets;
  std::vector<ScheduledCommand> pending_commands;
};

class ExchangeSimulator final {
 public:
  [[nodiscard]] static core::Result<ExchangeSimulator> create(std::vector<core::Market> markets);
  [[nodiscard]] static core::Result<ExchangeSimulator> restore(ExchangeCheckpoint checkpoint);
  [[nodiscard]] static core::Result<ExchangeSimulator> replay(
      std::vector<core::Market> markets, const std::vector<ScheduledCommand>& commands);

  ExchangeSimulator(ExchangeSimulator&&) noexcept;
  ExchangeSimulator& operator=(ExchangeSimulator&&) noexcept;
  ExchangeSimulator(const ExchangeSimulator&) = delete;
  ExchangeSimulator& operator=(const ExchangeSimulator&) = delete;
  ~ExchangeSimulator();

  [[nodiscard]] core::Result<std::uint64_t> enqueue(ExchangeCommand command,
                                                    core::Timestamp scheduled_at);
  [[nodiscard]] core::Result<void> run_next();
  [[nodiscard]] core::Result<void> run_until(core::Timestamp inclusive_time);

  [[nodiscard]] const std::vector<ExchangeEvent>& events() const {
    return events_;
  }
  [[nodiscard]] std::vector<ExchangeEvent> read_events_after(std::uint64_t sequence,
                                                             std::size_t limit) const;
  [[nodiscard]] const std::vector<ScheduledCommand>& command_journal() const {
    return command_journal_;
  }
  [[nodiscard]] std::optional<core::Timestamp> current_time() const {
    return current_time_;
  }
  [[nodiscard]] core::Result<book::BookSnapshot> snapshot(core::ContractId contract_id,
                                                          std::size_t depth) const;
  [[nodiscard]] ExchangeCheckpoint checkpoint() const;

 private:
  struct MarketRuntime {
    core::Market market;
    core::MarketStatus status;
    std::unique_ptr<book::LimitOrderBook> book;
  };

  class ExchangeSequencer;

  ExchangeSimulator() = default;

  [[nodiscard]] core::Result<void> process(const ExchangeCommand& command,
                                           core::Timestamp occurred_at,
                                           std::uint64_t ingress_sequence);
  [[nodiscard]] core::Result<void> process_submit(const SubmitOrderRequest& request,
                                                  core::Timestamp occurred_at,
                                                  std::uint64_t ingress_sequence);
  [[nodiscard]] core::Result<void> process_cancel(const CancelOrderRequest& request,
                                                  core::Timestamp occurred_at,
                                                  std::uint64_t ingress_sequence);
  [[nodiscard]] core::Result<void> process_lifecycle(const MarketLifecycleCommand& command,
                                                     core::Timestamp occurred_at,
                                                     std::uint64_t ingress_sequence);
  [[nodiscard]] core::Result<core::OrderId> reserve_order_id();
  [[nodiscard]] core::Result<core::SequenceNumber> reserve_event_sequence();
  [[nodiscard]] core::Result<void> append_rejection(core::DomainError error,
                                                    core::Timestamp occurred_at,
                                                    std::uint64_t ingress_sequence);
  void append_event(core::SequenceNumber sequence, core::Timestamp occurred_at,
                    std::uint64_t ingress_sequence, ExchangeEventPayload payload);
  [[nodiscard]] MarketRuntime* find_market_by_contract(core::ContractId contract_id);
  [[nodiscard]] const MarketRuntime* find_market_by_contract(core::ContractId contract_id) const;
  [[nodiscard]] static bool valid_transition(core::MarketStatus from, core::MarketStatus to);
  [[nodiscard]] static std::vector<PriceLevelDelta> depth_delta(const book::BookSnapshot& before,
                                                                const book::BookSnapshot& after);
  [[nodiscard]] static book::BookSnapshot full_snapshot(const book::LimitOrderBook& book);

  std::map<core::MarketId, MarketRuntime> markets_;
  std::map<core::ContractId, core::MarketId> contract_to_market_;
  std::vector<ScheduledCommand> pending_commands_;
  std::vector<ScheduledCommand> command_journal_;
  std::vector<ExchangeEvent> events_;
  std::optional<core::Timestamp> current_time_;
  std::uint64_t next_order_id_ = 1;
  std::unique_ptr<ExchangeSequencer> sequencer_;
  std::uint64_t next_ingress_sequence_ = 1;
};

}  // namespace pmm::sim
