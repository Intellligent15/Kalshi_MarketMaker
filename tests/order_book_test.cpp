#include "pmm/book/order_book.hpp"

#include <gtest/gtest.h>

#include <algorithm>
#include <map>
#include <random>
#include <vector>

namespace pmm::book {
namespace {

template <typename T>
T Require(Result<T> result) {
  EXPECT_TRUE(result.has_value()) << result.error().message;
  return std::move(result).value();
}

Contract MakeContract() {
  const auto market_id = Require(core::MarketId::from_value(1));
  const auto contract_id = Require(core::ContractId::from_value(10));
  const auto minimum = Require(Price::from_units(1));
  const auto maximum = Require(Price::from_units(99));
  const auto increment = Require(Price::from_units(1));
  const auto payout = Require(Price::from_units(100));
  const auto grid = Require(core::PriceGrid::create(minimum, maximum, increment));
  const auto lot_size = Require(core::LotSize::from_units(1));
  return Require(Contract::create(contract_id, market_id, payout, grid, lot_size));
}

Order LimitOrder(std::uint64_t order_id, std::uint64_t trader_id, Side side, std::int64_t quantity,
                 std::int64_t price, const Contract& contract) {
  return Require(Order::create_limit(
      Require(OrderId::from_value(order_id)), Require(TraderId::from_value(trader_id)),
      contract.id(), side, Require(Quantity::from_units(quantity)),
      Require(Price::from_units(price)), Timestamp::from_unix_nanoseconds(1), contract));
}

Order MarketOrder(std::uint64_t order_id, std::uint64_t trader_id, Side side, std::int64_t quantity,
                  const Contract& contract) {
  return Require(Order::create_market(Require(OrderId::from_value(order_id)),
                                      Require(TraderId::from_value(trader_id)), contract.id(), side,
                                      Require(Quantity::from_units(quantity)),
                                      Timestamp::from_unix_nanoseconds(1), contract));
}

MonotonicExecutionIdSource MakeIdSource() {
  return Require(MonotonicExecutionIdSource::create(Require(TradeId::from_value(1000)),
                                                    Require(SequenceNumber::from_value(5000))));
}

class RejectingExecutionIdSource final : public ExecutionIdSource {
 public:
  Result<std::vector<ExecutionIdentifiers>> reserve(std::size_t execution_count) override {
    if (execution_count == 0) {
      return std::vector<ExecutionIdentifiers>{};
    }
    return core::DomainError{core::DomainErrorCode::IdentifierExhausted,
                             "test execution ID source rejects the reservation"};
  }
};

TEST(LimitOrderBook, MatchesBestPriceThenFifoAndRetainsPartialRemainder) {
  const Contract contract = MakeContract();
  MonotonicExecutionIdSource ids = MakeIdSource();
  LimitOrderBook book = Require(LimitOrderBook::create(contract, ids));

  EXPECT_EQ(book.submit(LimitOrder(101, 1, Side::Sell, 5, 60, contract),
                        Timestamp::from_unix_nanoseconds(10))
                .value()
                .incoming_order_update.status,
            OrderStatus::Resting);
  EXPECT_EQ(book.submit(LimitOrder(102, 2, Side::Sell, 4, 60, contract),
                        Timestamp::from_unix_nanoseconds(11))
                .value()
                .incoming_order_update.status,
            OrderStatus::Resting);

  const SubmitReport report = Require(book.submit(LimitOrder(201, 3, Side::Buy, 7, 65, contract),
                                                  Timestamp::from_unix_nanoseconds(12)));
  ASSERT_EQ(report.executions.size(), 2U);
  EXPECT_EQ(report.executions[0].trade.seller_order_id().value(), 101U);
  EXPECT_EQ(report.executions[0].trade.quantity().units(), 5U);
  EXPECT_EQ(report.executions[1].trade.seller_order_id().value(), 102U);
  EXPECT_EQ(report.executions[1].trade.quantity().units(), 2U);
  EXPECT_EQ(report.executions[0].trade.price().units(), 60U);
  EXPECT_EQ(report.executions[0].trade.sequence().value(), 5000U);
  EXPECT_EQ(report.executions[1].trade.sequence().value(), 5001U);
  EXPECT_EQ(report.incoming_order_update.status, OrderStatus::Filled);
  ASSERT_EQ(report.resting_order_updates.size(), 2U);
  EXPECT_EQ(report.resting_order_updates[0].status, OrderStatus::Filled);
  EXPECT_EQ(report.resting_order_updates[1].status, OrderStatus::PartiallyFilled);

  const auto remaining = book.find_live_order(Require(OrderId::from_value(102)));
  ASSERT_TRUE(remaining.has_value());
  EXPECT_EQ(remaining->remaining_quantity.units(), 2U);
  const BookSnapshot snapshot = book.snapshot(5);
  EXPECT_TRUE(snapshot.bids.empty());
  ASSERT_EQ(snapshot.asks.size(), 1U);
  EXPECT_EQ(snapshot.asks[0].price.units(), 60U);
  EXPECT_EQ(snapshot.asks[0].total_quantity.units(), 2U);
}

TEST(LimitOrderBook, CancelsInConstantTimeAndRemovesThePriceLevel) {
  const Contract contract = MakeContract();
  MonotonicExecutionIdSource ids = MakeIdSource();
  LimitOrderBook book = Require(LimitOrderBook::create(contract, ids));
  const OrderId order_id = Require(OrderId::from_value(101));

  Require(book.submit(LimitOrder(101, 1, Side::Buy, 4, 45, contract),
                      Timestamp::from_unix_nanoseconds(10)));
  const CancelReport report = Require(book.cancel(order_id));
  EXPECT_EQ(report.order_update.status, OrderStatus::Cancelled);
  EXPECT_EQ(report.order_update.remaining_quantity.units(), 4U);
  EXPECT_FALSE(book.find_live_order(order_id).has_value());
  EXPECT_TRUE(book.snapshot(5).bids.empty());

  const auto repeated_cancel = book.cancel(order_id);
  EXPECT_FALSE(repeated_cancel.has_value());
  EXPECT_EQ(repeated_cancel.error().code, core::DomainErrorCode::UnknownOrder);
}

TEST(LimitOrderBook, WalksPriceLevelsInPricePriorityOrder) {
  const Contract contract = MakeContract();
  MonotonicExecutionIdSource ids = MakeIdSource();
  LimitOrderBook book = Require(LimitOrderBook::create(contract, ids));

  Require(book.submit(LimitOrder(101, 1, Side::Sell, 3, 59, contract),
                      Timestamp::from_unix_nanoseconds(10)));
  Require(book.submit(LimitOrder(102, 2, Side::Sell, 3, 60, contract),
                      Timestamp::from_unix_nanoseconds(11)));
  const SubmitReport buy_report = Require(book.submit(
      LimitOrder(201, 3, Side::Buy, 4, 61, contract), Timestamp::from_unix_nanoseconds(12)));
  ASSERT_EQ(buy_report.executions.size(), 2U);
  EXPECT_EQ(buy_report.executions[0].trade.price().units(), 59U);
  EXPECT_EQ(buy_report.executions[0].trade.quantity().units(), 3U);
  EXPECT_EQ(buy_report.executions[1].trade.price().units(), 60U);
  EXPECT_EQ(buy_report.executions[1].trade.quantity().units(), 1U);

  Require(book.submit(LimitOrder(301, 4, Side::Buy, 3, 55, contract),
                      Timestamp::from_unix_nanoseconds(13)));
  Require(book.submit(LimitOrder(302, 5, Side::Buy, 3, 54, contract),
                      Timestamp::from_unix_nanoseconds(14)));
  const SubmitReport sell_report = Require(book.submit(
      LimitOrder(401, 6, Side::Sell, 4, 53, contract), Timestamp::from_unix_nanoseconds(15)));
  ASSERT_EQ(sell_report.executions.size(), 2U);
  EXPECT_EQ(sell_report.executions[0].trade.price().units(), 55U);
  EXPECT_EQ(sell_report.executions[0].trade.quantity().units(), 3U);
  EXPECT_EQ(sell_report.executions[1].trade.price().units(), 54U);
  EXPECT_EQ(sell_report.executions[1].trade.quantity().units(), 1U);
}

TEST(LimitOrderBook, ExpiresAnUnfilledMarketRemainderAtTheRestingPrice) {
  const Contract contract = MakeContract();
  MonotonicExecutionIdSource ids = MakeIdSource();
  LimitOrderBook book = Require(LimitOrderBook::create(contract, ids));

  Require(book.submit(LimitOrder(101, 1, Side::Buy, 3, 50, contract),
                      Timestamp::from_unix_nanoseconds(10)));
  const SubmitReport report = Require(book.submit(MarketOrder(201, 2, Side::Sell, 5, contract),
                                                  Timestamp::from_unix_nanoseconds(11)));

  ASSERT_EQ(report.executions.size(), 1U);
  EXPECT_EQ(report.executions[0].trade.price().units(), 50U);
  EXPECT_EQ(report.executions[0].trade.quantity().units(), 3U);
  EXPECT_EQ(report.incoming_order_update.status, OrderStatus::Expired);
  EXPECT_EQ(report.incoming_order_update.remaining_quantity.units(), 2U);
  EXPECT_TRUE(book.snapshot(5).bids.empty());
}

TEST(LimitOrderBook, CancelsTheAggressorWhenItWouldSelfTrade) {
  const Contract contract = MakeContract();
  MonotonicExecutionIdSource ids = MakeIdSource();
  LimitOrderBook book = Require(LimitOrderBook::create(contract, ids));

  Require(book.submit(LimitOrder(101, 1, Side::Sell, 3, 60, contract),
                      Timestamp::from_unix_nanoseconds(10)));
  const SubmitReport report = Require(book.submit(LimitOrder(201, 1, Side::Buy, 3, 60, contract),
                                                  Timestamp::from_unix_nanoseconds(11)));

  EXPECT_TRUE(report.self_trade_prevented);
  EXPECT_TRUE(report.executions.empty());
  EXPECT_EQ(report.incoming_order_update.status, OrderStatus::Cancelled);
  EXPECT_EQ(report.incoming_order_update.remaining_quantity.units(), 3U);
  ASSERT_TRUE(book.find_live_order(Require(OrderId::from_value(101))).has_value());
  EXPECT_FALSE(book.find_live_order(Require(OrderId::from_value(201))).has_value());
}

TEST(LimitOrderBook, LeavesTheBookUnchangedWhenExecutionIdentifiersCannotBeReserved) {
  const Contract contract = MakeContract();
  RejectingExecutionIdSource ids;
  LimitOrderBook book = Require(LimitOrderBook::create(contract, ids));

  Require(book.submit(LimitOrder(101, 1, Side::Sell, 3, 60, contract),
                      Timestamp::from_unix_nanoseconds(10)));
  const auto rejected = book.submit(LimitOrder(201, 2, Side::Buy, 3, 60, contract),
                                    Timestamp::from_unix_nanoseconds(11));

  EXPECT_FALSE(rejected.has_value());
  ASSERT_TRUE(book.find_live_order(Require(OrderId::from_value(101))).has_value());
  EXPECT_FALSE(book.find_live_order(Require(OrderId::from_value(201))).has_value());
  const BookSnapshot snapshot = book.snapshot(5);
  ASSERT_EQ(snapshot.asks.size(), 1U);
  EXPECT_EQ(snapshot.asks[0].total_quantity.units(), 3U);
}

TEST(LimitOrderBook, RejectsPriceGridsThatExceedTheDenseLadderLimit) {
  const Contract contract = MakeContract();
  MonotonicExecutionIdSource ids = MakeIdSource();

  const auto book = LimitOrderBook::create(contract, ids, BookOptions{.maximum_price_levels = 10});
  EXPECT_FALSE(book.has_value());
  EXPECT_EQ(book.error().code, core::DomainErrorCode::InvalidBook);
}

TEST(LimitOrderBook, RandomizedCommandsMatchAReferencePriceTimeModel) {
  struct ModelOrder {
    std::uint64_t order_id;
    std::uint64_t trader_id;
    Side side;
    std::uint64_t original_quantity;
    std::uint64_t remaining_quantity;
    std::uint64_t price;
    std::uint64_t priority;
  };
  struct ExpectedMatch {
    std::uint64_t resting_order_id;
    std::uint64_t quantity;
    std::uint64_t price;
  };

  constexpr std::uint64_t kFirstTradeId = 1000;
  constexpr std::uint64_t kFirstSequence = 5000;
  const std::vector<std::uint32_t> seeds{7U, 101U, 2026U, 8675309U};
  for (const std::uint32_t seed : seeds) {
    SCOPED_TRACE(seed);
    const Contract contract = MakeContract();
    MonotonicExecutionIdSource ids = MakeIdSource();
    LimitOrderBook book = Require(LimitOrderBook::create(contract, ids));
    std::mt19937 generator(seed);
    std::vector<ModelOrder> model;
    std::uint64_t next_order_id = 1;
    std::uint64_t next_priority = 1;
    std::uint64_t next_trade_id = kFirstTradeId;
    std::uint64_t next_sequence = kFirstSequence;

    const auto verify_state = [&book, &model]() {
      EXPECT_TRUE(book.validate_invariants().has_value());
      std::map<std::uint64_t, std::pair<std::uint64_t, std::size_t>> bids;
      std::map<std::uint64_t, std::pair<std::uint64_t, std::size_t>> asks;
      for (const ModelOrder& order : model) {
        auto& aggregate = order.side == Side::Buy ? bids[order.price] : asks[order.price];
        aggregate.first += order.remaining_quantity;
        ++aggregate.second;

        const auto live = book.find_live_order(Require(OrderId::from_value(order.order_id)));
        ASSERT_TRUE(live.has_value());
        EXPECT_EQ(live->trader_id.value(), order.trader_id);
        EXPECT_EQ(live->remaining_quantity.units(), order.remaining_quantity);
        EXPECT_EQ(live->priority_sequence.value(), order.priority);
      }

      const BookSnapshot snapshot = book.snapshot(99);
      ASSERT_EQ(snapshot.bids.size(), bids.size());
      ASSERT_EQ(snapshot.asks.size(), asks.size());
      std::size_t bid_index = 0;
      for (auto bid = bids.rbegin(); bid != bids.rend(); ++bid, ++bid_index) {
        EXPECT_EQ(snapshot.bids[bid_index].price.units(), bid->first);
        EXPECT_EQ(snapshot.bids[bid_index].total_quantity.units(), bid->second.first);
        EXPECT_EQ(snapshot.bids[bid_index].order_count, bid->second.second);
      }
      std::size_t ask_index = 0;
      for (const auto& [price, aggregate] : asks) {
        EXPECT_EQ(snapshot.asks[ask_index].price.units(), price);
        EXPECT_EQ(snapshot.asks[ask_index].total_quantity.units(), aggregate.first);
        EXPECT_EQ(snapshot.asks[ask_index].order_count, aggregate.second);
        ++ask_index;
      }
    };

    for (std::size_t step = 0; step < 1500; ++step) {
      SCOPED_TRACE(step);
      const bool cancel = !model.empty() && (generator() % 4U == 0U);
      if (cancel) {
        const std::size_t index = static_cast<std::size_t>(generator() % model.size());
        const std::uint64_t order_id = model[index].order_id;
        const CancelReport report = Require(book.cancel(Require(OrderId::from_value(order_id))));
        EXPECT_EQ(report.order_update.status, OrderStatus::Cancelled);
        EXPECT_EQ(report.order_update.remaining_quantity.units(), model[index].remaining_quantity);
        model.erase(model.begin() + static_cast<std::ptrdiff_t>(index));
        verify_state();
        continue;
      }

      const Side side = generator() % 2U == 0U ? Side::Buy : Side::Sell;
      const core::OrderType type =
          generator() % 4U == 0U ? core::OrderType::Market : core::OrderType::Limit;
      const std::uint64_t quantity = generator() % 5U + 1U;
      const std::uint64_t price = generator() % 99U + 1U;
      const std::uint64_t trader_id = generator() % 5U + 1U;
      const std::uint64_t incoming_order_id = next_order_id++;

      std::uint64_t remaining = quantity;
      bool self_trade_prevented = false;
      std::vector<ExpectedMatch> matches;
      std::vector<OrderStatus> resting_statuses;
      while (remaining != 0) {
        auto best = model.end();
        for (auto candidate = model.begin(); candidate != model.end(); ++candidate) {
          if (candidate->side == side) {
            continue;
          }
          const bool crosses =
              type == core::OrderType::Market ||
              (side == Side::Buy ? price >= candidate->price : price <= candidate->price);
          if (!crosses) {
            continue;
          }
          if (best == model.end() ||
              (side == Side::Buy ? candidate->price < best->price
                                 : candidate->price > best->price) ||
              (candidate->price == best->price && candidate->priority < best->priority)) {
            best = candidate;
          }
        }
        if (best == model.end()) {
          break;
        }
        if (best->trader_id == trader_id) {
          self_trade_prevented = true;
          break;
        }
        const std::uint64_t matched_quantity = std::min(remaining, best->remaining_quantity);
        matches.push_back(ExpectedMatch{best->order_id, matched_quantity, best->price});
        remaining -= matched_quantity;
        best->remaining_quantity -= matched_quantity;
        resting_statuses.push_back(best->remaining_quantity == 0 ? OrderStatus::Filled
                                                                 : OrderStatus::PartiallyFilled);
        if (best->remaining_quantity == 0) {
          model.erase(best);
        }
      }

      Order incoming =
          type == core::OrderType::Limit
              ? LimitOrder(incoming_order_id, trader_id, side, static_cast<std::int64_t>(quantity),
                           static_cast<std::int64_t>(price), contract)
              : MarketOrder(incoming_order_id, trader_id, side, static_cast<std::int64_t>(quantity),
                            contract);
      const SubmitReport report = Require(
          book.submit(std::move(incoming),
                      Timestamp::from_unix_nanoseconds(static_cast<std::int64_t>(step + 1U))));
      ASSERT_EQ(report.executions.size(), matches.size());
      ASSERT_EQ(report.resting_order_updates.size(), resting_statuses.size());
      EXPECT_EQ(report.self_trade_prevented, self_trade_prevented);
      for (std::size_t index = 0; index < matches.size(); ++index) {
        const Execution& execution = report.executions[index];
        EXPECT_EQ(execution.trade.id().value(), next_trade_id + index);
        EXPECT_EQ(execution.trade.sequence().value(), next_sequence + index);
        EXPECT_EQ(execution.trade.price().units(), matches[index].price);
        EXPECT_EQ(execution.trade.quantity().units(), matches[index].quantity);
        const std::uint64_t passive_order_id = side == Side::Buy
                                                   ? execution.trade.seller_order_id().value()
                                                   : execution.trade.buyer_order_id().value();
        EXPECT_EQ(passive_order_id, matches[index].resting_order_id);
        EXPECT_EQ(report.resting_order_updates[index].status, resting_statuses[index]);
      }
      next_trade_id += matches.size();
      next_sequence += matches.size();

      OrderStatus expected_status = OrderStatus::Filled;
      if (self_trade_prevented) {
        expected_status = OrderStatus::Cancelled;
      } else if (remaining != 0 && type == core::OrderType::Market) {
        expected_status = OrderStatus::Expired;
      } else if (remaining != 0) {
        expected_status =
            remaining == quantity ? OrderStatus::Resting : OrderStatus::PartiallyFilled;
        model.push_back(ModelOrder{incoming_order_id, trader_id, side, quantity, remaining, price,
                                   next_priority++});
      }
      EXPECT_EQ(report.incoming_order_update.status, expected_status);
      EXPECT_EQ(report.incoming_order_update.remaining_quantity.units(), remaining);
      verify_state();
    }
  }
}

}  // namespace
}  // namespace pmm::book
