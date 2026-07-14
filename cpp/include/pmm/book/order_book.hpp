#pragma once

#include <cstddef>
#include <cstdint>
#include <optional>
#include <unordered_map>
#include <utility>
#include <vector>

#include "pmm/core/execution.hpp"

namespace pmm::book {

using core::Contract;
using core::DomainError;
using core::Fill;
using core::IdentifierHash;
using core::Order;
using core::OrderId;
using core::Price;
using core::Quantity;
using core::Result;
using core::SequenceNumber;
using core::Side;
using core::Timestamp;
using core::Trade;
using core::TradeId;
using core::TraderId;

struct ExecutionIdentifiers {
  TradeId trade_id;
  SequenceNumber sequence;
};

class ExecutionIdSource {
 public:
  virtual ~ExecutionIdSource() = default;

  // Reserves identifiers before the book mutates so submission remains atomic if an ID source
  // cannot satisfy a request. Gaps are permitted; uniqueness and monotonicity are required.
  [[nodiscard]] virtual Result<std::vector<ExecutionIdentifiers>> reserve(
      std::size_t execution_count) = 0;
};

class MonotonicExecutionIdSource final : public ExecutionIdSource {
 public:
  [[nodiscard]] static Result<MonotonicExecutionIdSource> create(TradeId first_trade_id,
                                                                 SequenceNumber first_sequence);

  [[nodiscard]] Result<std::vector<ExecutionIdentifiers>> reserve(
      std::size_t execution_count) override;

 private:
  MonotonicExecutionIdSource(std::uint64_t next_trade_id, std::uint64_t next_sequence)
      : next_trade_id_(next_trade_id), next_sequence_(next_sequence) {}

  std::uint64_t next_trade_id_;
  std::uint64_t next_sequence_;
};

struct BookOptions {
  // Prediction-market price grids are normally compact. This guard avoids an accidental dense
  // allocation for a pathological contract; a sparse implementation can be added if warranted.
  std::size_t maximum_price_levels = 4096;
};

enum class OrderStatus {
  Resting,
  PartiallyFilled,
  Filled,
  Cancelled,
  Expired,
};

struct OrderUpdate {
  OrderId order_id;
  OrderStatus status;
  Quantity remaining_quantity;
};

struct Execution {
  Trade trade;
  Fill buyer_fill;
  Fill seller_fill;
};

struct SubmitReport {
  std::vector<Execution> executions;
  std::vector<OrderUpdate> resting_order_updates;
  OrderUpdate incoming_order_update;
  bool self_trade_prevented;
};

struct CancelReport {
  OrderUpdate order_update;
};

struct PriceLevelView {
  Price price;
  Quantity total_quantity;
  std::size_t order_count;
};

struct BookSnapshot {
  std::vector<PriceLevelView> bids;
  std::vector<PriceLevelView> asks;
};

struct LiveOrderView {
  OrderId order_id;
  TraderId trader_id;
  Side side;
  Price price;
  Quantity original_quantity;
  Quantity remaining_quantity;
  SequenceNumber priority_sequence;
};

class LimitOrderBook {
 public:
  [[nodiscard]] static Result<LimitOrderBook> create(Contract contract,
                                                     ExecutionIdSource& execution_id_source,
                                                     BookOptions options = {});

  [[nodiscard]] const Contract& contract() const {
    return contract_;
  }

  [[nodiscard]] Result<SubmitReport> submit(Order order, Timestamp received_at);
  [[nodiscard]] Result<CancelReport> cancel(OrderId order_id);
  [[nodiscard]] std::optional<LiveOrderView> find_live_order(OrderId order_id) const;
  [[nodiscard]] BookSnapshot snapshot(std::size_t depth) const;

 private:
  struct OrderNode;

  struct PriceLevel {
    explicit PriceLevel(Price level_price) : price(level_price) {}

    Price price;
    OrderNode* head = nullptr;
    OrderNode* tail = nullptr;
    std::uint64_t total_quantity = 0;
    std::size_t order_count = 0;
  };

  struct OrderNode {
    Order order;
    std::uint64_t remaining_quantity;
    SequenceNumber priority_sequence;
    PriceLevel* level = nullptr;
    OrderNode* previous = nullptr;
    OrderNode* next = nullptr;
  };

  struct BookSide {
    std::vector<PriceLevel> levels;
    std::vector<std::uint64_t> occupied_words;
  };

  struct PlannedMatch {
    OrderNode* resting_order;
    std::uint64_t quantity;
  };

  struct MatchPlan {
    std::vector<PlannedMatch> matches;
    bool self_trade_prevented;
  };

  LimitOrderBook(Contract contract, ExecutionIdSource& execution_id_source, BookSide bids,
                 BookSide asks, std::uint64_t next_priority_sequence)
      : contract_(std::move(contract)),
        execution_id_source_(execution_id_source),
        bids_(std::move(bids)),
        asks_(std::move(asks)),
        next_priority_sequence_(next_priority_sequence) {}

  [[nodiscard]] Result<MatchPlan> plan_matches(const Order& incoming) const;
  [[nodiscard]] std::optional<std::size_t> best_index(Side side) const;
  [[nodiscard]] std::optional<std::size_t> next_index(Side side, std::size_t index) const;
  [[nodiscard]] bool crosses(const Order& incoming, Price resting_price) const;
  [[nodiscard]] std::size_t price_index(Price price) const;
  [[nodiscard]] BookSide& side_for(Side side);
  [[nodiscard]] const BookSide& side_for(Side side) const;
  [[nodiscard]] Result<void> link_resting_order(OrderNode& order);
  void unlink_resting_order(OrderNode& order);
  void set_occupied(BookSide& side, std::size_t index, bool occupied);
  [[nodiscard]] bool is_occupied(const BookSide& side, std::size_t index) const;
  [[nodiscard]] static Quantity quantity_from_units(std::uint64_t units);
  [[nodiscard]] static OrderStatus status_for_resting(std::uint64_t remaining,
                                                      std::uint64_t original);

  Contract contract_;
  ExecutionIdSource& execution_id_source_;
  BookSide bids_;
  BookSide asks_;
  std::unordered_map<OrderId, OrderNode, IdentifierHash> live_orders_;
  std::uint64_t next_priority_sequence_;
};

}  // namespace pmm::book
