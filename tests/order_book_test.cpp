#include "pmm/book/order_book.hpp"

#include <gtest/gtest.h>

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

}  // namespace
}  // namespace pmm::book
