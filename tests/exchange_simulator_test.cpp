#include "pmm/sim/exchange_simulator.hpp"

#include <gtest/gtest.h>

#include <type_traits>
#include <variant>

namespace pmm::sim {
namespace {

template <typename T>
T Require(core::Result<T> result) {
  EXPECT_TRUE(result.has_value()) << result.error().message;
  return std::move(result).value();
}

void Require(core::Result<void> result) {
  EXPECT_TRUE(result.has_value()) << result.error().message;
}

core::Market MakeMarket(std::uint64_t market_value = 1, std::uint64_t contract_value = 10) {
  const auto market_id = Require(core::MarketId::from_value(market_value));
  const auto contract_id = Require(core::ContractId::from_value(contract_value));
  const auto minimum = Require(core::Price::from_units(1));
  const auto maximum = Require(core::Price::from_units(99));
  const auto increment = Require(core::Price::from_units(1));
  const auto payout = Require(core::Price::from_units(100));
  const auto grid = Require(core::PriceGrid::create(minimum, maximum, increment));
  const auto lot_size = Require(core::LotSize::from_units(1));
  const auto contract =
      Require(core::Contract::create(contract_id, market_id, payout, grid, lot_size));
  return Require(core::Market::create(market_id, "Question", contract));
}

SubmitOrderRequest LimitRequest(std::uint64_t trader_value, core::ContractId contract_id,
                                core::Side side, std::int64_t quantity, std::int64_t price,
                                std::int64_t submitted_at) {
  return SubmitOrderRequest{Require(core::TraderId::from_value(trader_value)),
                            contract_id,
                            side,
                            core::OrderType::Limit,
                            Require(core::Quantity::from_units(quantity)),
                            Require(core::Price::from_units(price)),
                            core::Timestamp::from_unix_nanoseconds(submitted_at)};
}

void ExpectEqualOrder(const core::Order& actual, const core::Order& expected) {
  EXPECT_EQ(actual.id(), expected.id());
  EXPECT_EQ(actual.trader_id(), expected.trader_id());
  EXPECT_EQ(actual.contract_id(), expected.contract_id());
  EXPECT_EQ(actual.side(), expected.side());
  EXPECT_EQ(actual.type(), expected.type());
  EXPECT_EQ(actual.quantity(), expected.quantity());
  EXPECT_EQ(actual.limit_price(), expected.limit_price());
  EXPECT_EQ(actual.submitted_at(), expected.submitted_at());
}

void ExpectEqualUpdate(const book::OrderUpdate& actual, const book::OrderUpdate& expected) {
  EXPECT_EQ(actual.order_id, expected.order_id);
  EXPECT_EQ(actual.status, expected.status);
  EXPECT_EQ(actual.remaining_quantity, expected.remaining_quantity);
}

void ExpectEqualExecution(const book::Execution& actual, const book::Execution& expected) {
  const core::Trade& actual_trade = actual.trade;
  const core::Trade& expected_trade = expected.trade;
  EXPECT_EQ(actual_trade.id(), expected_trade.id());
  EXPECT_EQ(actual_trade.contract_id(), expected_trade.contract_id());
  EXPECT_EQ(actual_trade.buyer_order_id(), expected_trade.buyer_order_id());
  EXPECT_EQ(actual_trade.seller_order_id(), expected_trade.seller_order_id());
  EXPECT_EQ(actual_trade.buyer_trader_id(), expected_trade.buyer_trader_id());
  EXPECT_EQ(actual_trade.seller_trader_id(), expected_trade.seller_trader_id());
  EXPECT_EQ(actual_trade.price(), expected_trade.price());
  EXPECT_EQ(actual_trade.quantity(), expected_trade.quantity());
  EXPECT_EQ(actual_trade.executed_at(), expected_trade.executed_at());
  EXPECT_EQ(actual_trade.sequence(), expected_trade.sequence());
  EXPECT_EQ(actual_trade.aggressor_side(), expected_trade.aggressor_side());
  const auto expect_fill = [](const core::Fill& actual_fill, const core::Fill& expected_fill) {
    EXPECT_EQ(actual_fill.trade_id(), expected_fill.trade_id());
    EXPECT_EQ(actual_fill.order_id(), expected_fill.order_id());
    EXPECT_EQ(actual_fill.trader_id(), expected_fill.trader_id());
    EXPECT_EQ(actual_fill.contract_id(), expected_fill.contract_id());
    EXPECT_EQ(actual_fill.side(), expected_fill.side());
    EXPECT_EQ(actual_fill.price(), expected_fill.price());
    EXPECT_EQ(actual_fill.quantity(), expected_fill.quantity());
    EXPECT_EQ(actual_fill.executed_at(), expected_fill.executed_at());
    EXPECT_EQ(actual_fill.sequence(), expected_fill.sequence());
  };
  expect_fill(actual.buyer_fill, expected.buyer_fill);
  expect_fill(actual.seller_fill, expected.seller_fill);
}

void ExpectEqualEvent(const ExchangeEvent& actual, const ExchangeEvent& expected) {
  EXPECT_EQ(actual.sequence, expected.sequence);
  EXPECT_EQ(actual.occurred_at, expected.occurred_at);
  EXPECT_EQ(actual.ingress_sequence, expected.ingress_sequence);
  ASSERT_EQ(actual.payload.index(), expected.payload.index());
  std::visit(
      [&actual](const auto& expected_payload) {
        using Payload = std::decay_t<decltype(expected_payload)>;
        const auto* actual_payload = std::get_if<Payload>(&actual.payload);
        ASSERT_NE(actual_payload, nullptr);
        if constexpr (std::is_same_v<Payload, OrderAcknowledged>) {
          ExpectEqualOrder(actual_payload->order, expected_payload.order);
        } else if constexpr (std::is_same_v<Payload, TradeExecuted>) {
          ExpectEqualExecution(actual_payload->execution, expected_payload.execution);
        } else if constexpr (std::is_same_v<Payload, OrderOutcome>) {
          ExpectEqualUpdate(actual_payload->update, expected_payload.update);
        } else if constexpr (std::is_same_v<Payload, CancellationAcknowledged>) {
          ExpectEqualUpdate(actual_payload->update, expected_payload.update);
        } else if constexpr (std::is_same_v<Payload, MarketStatusChanged>) {
          EXPECT_EQ(actual_payload->market_id, expected_payload.market_id);
          EXPECT_EQ(actual_payload->previous_status, expected_payload.previous_status);
          EXPECT_EQ(actual_payload->current_status, expected_payload.current_status);
        } else if constexpr (std::is_same_v<Payload, BookDepthChanged>) {
          EXPECT_EQ(actual_payload->contract_id, expected_payload.contract_id);
          ASSERT_EQ(actual_payload->levels.size(), expected_payload.levels.size());
          for (std::size_t index = 0; index < actual_payload->levels.size(); ++index) {
            EXPECT_EQ(actual_payload->levels[index].side, expected_payload.levels[index].side);
            EXPECT_EQ(actual_payload->levels[index].price, expected_payload.levels[index].price);
            EXPECT_EQ(actual_payload->levels[index].total_quantity,
                      expected_payload.levels[index].total_quantity);
            EXPECT_EQ(actual_payload->levels[index].order_count,
                      expected_payload.levels[index].order_count);
          }
        } else {
          EXPECT_EQ(actual_payload->error.code, expected_payload.error.code);
          EXPECT_EQ(actual_payload->error.message, expected_payload.error.message);
        }
      },
      expected.payload);
}

TEST(ExchangeSimulator, CorrelatesPostOnlyRejectionToTheOriginatingIngressCommand) {
  const core::Market market = MakeMarket();
  ExchangeSimulator simulator = Require(ExchangeSimulator::create({market}));
  const auto time = core::Timestamp::from_unix_nanoseconds(10);
  Require(
      simulator.enqueue(LimitRequest(1, market.contract().id(), core::Side::Sell, 1, 50, 1), time));
  SubmitOrderRequest post_only = LimitRequest(2, market.contract().id(), core::Side::Buy, 1, 50, 2);
  post_only.post_only = true;
  const std::uint64_t ingress = Require(simulator.enqueue(post_only, time));
  Require(simulator.run_until(time));

  ASSERT_EQ(simulator.events().size(), 4U);
  const ExchangeEvent& rejection = simulator.events().back();
  EXPECT_EQ(rejection.ingress_sequence, ingress);
  ASSERT_TRUE(std::holds_alternative<CommandRejected>(rejection.payload));
  EXPECT_TRUE(simulator.snapshot(market.contract().id(), 2).value().asks.size() == 1U);
}

TEST(ExchangeSimulator, GloballySequencesSameTimeCommandsAndTradesAcrossBooks) {
  const core::Market first = MakeMarket(1, 10);
  const core::Market second = MakeMarket(2, 20);
  ExchangeSimulator simulator = Require(ExchangeSimulator::create({first, second}));
  const auto time = core::Timestamp::from_unix_nanoseconds(10);

  Require(
      simulator.enqueue(LimitRequest(1, first.contract().id(), core::Side::Sell, 3, 60, 1), time));
  Require(
      simulator.enqueue(LimitRequest(2, first.contract().id(), core::Side::Buy, 3, 60, 2), time));
  Require(
      simulator.enqueue(LimitRequest(3, second.contract().id(), core::Side::Sell, 2, 50, 3), time));
  Require(simulator.run_until(time));

  const std::vector<ExchangeEvent>& events = simulator.events();
  ASSERT_EQ(events.size(), 10U);
  for (std::size_t index = 0; index < events.size(); ++index) {
    EXPECT_EQ(events[index].sequence.value(), index + 1U);
    EXPECT_EQ(events[index].occurred_at, time);
  }

  const auto* first_ack = std::get_if<OrderAcknowledged>(&events[0].payload);
  ASSERT_NE(first_ack, nullptr);
  EXPECT_EQ(first_ack->order.id().value(), 1U);
  const auto* execution = std::get_if<TradeExecuted>(&events[4].payload);
  ASSERT_NE(execution, nullptr);
  EXPECT_EQ(execution->execution.trade.id().value(), 1U);
  EXPECT_EQ(execution->execution.trade.sequence(), events[4].sequence);
  EXPECT_EQ(execution->execution.trade.contract_id(), first.contract().id());
  const auto* third_ack = std::get_if<OrderAcknowledged>(&events[7].payload);
  ASSERT_NE(third_ack, nullptr);
  EXPECT_EQ(third_ack->order.id().value(), 3U);
}

TEST(ExchangeSimulator, ClosesByCancellingLiveOrdersAndRejectsNewOrders) {
  const core::Market market = MakeMarket();
  ExchangeSimulator simulator = Require(ExchangeSimulator::create({market}));
  const auto first_time = core::Timestamp::from_unix_nanoseconds(1);
  const auto close_time = core::Timestamp::from_unix_nanoseconds(2);

  Require(simulator.enqueue(LimitRequest(1, market.contract().id(), core::Side::Buy, 4, 45, 1),
                            first_time));
  Require(simulator.enqueue(MarketLifecycleCommand{market.id(), core::MarketStatus::Closed},
                            close_time));
  Require(simulator.enqueue(LimitRequest(2, market.contract().id(), core::Side::Sell, 1, 45, 3),
                            core::Timestamp::from_unix_nanoseconds(3)));
  Require(simulator.run_until(core::Timestamp::from_unix_nanoseconds(3)));

  EXPECT_TRUE(simulator.snapshot(market.contract().id(), 5).value().bids.empty());
  ASSERT_GE(simulator.events().size(), 7U);
  EXPECT_TRUE(std::holds_alternative<MarketStatusChanged>(simulator.events()[3].payload));
  EXPECT_TRUE(std::holds_alternative<CancellationAcknowledged>(simulator.events()[4].payload));
  EXPECT_TRUE(std::holds_alternative<BookDepthChanged>(simulator.events()[5].payload));
  EXPECT_TRUE(std::holds_alternative<CommandRejected>(simulator.events()[6].payload));
}

TEST(ExchangeSimulator, RestoresCheckpointAndReplaysTheSameExecution) {
  const core::Market market = MakeMarket();
  ExchangeSimulator simulator = Require(ExchangeSimulator::create({market}));
  const auto first_time = core::Timestamp::from_unix_nanoseconds(10);
  const auto second_time = core::Timestamp::from_unix_nanoseconds(20);

  Require(simulator.enqueue(LimitRequest(1, market.contract().id(), core::Side::Sell, 3, 60, 1),
                            first_time));
  Require(simulator.run_until(first_time));
  const ExchangeCheckpoint checkpoint = simulator.checkpoint();
  const std::size_t snapshot_event_count = simulator.events().size();

  const SubmitOrderRequest buy = LimitRequest(2, market.contract().id(), core::Side::Buy, 3, 60, 2);
  Require(simulator.enqueue(buy, second_time));
  Require(simulator.run_until(second_time));

  ExchangeSimulator restored = Require(ExchangeSimulator::restore(checkpoint));
  Require(restored.enqueue(buy, second_time));
  Require(restored.run_until(second_time));
  ASSERT_EQ(restored.events().size(), simulator.events().size() - snapshot_event_count);
  for (std::size_t index = 0; index < restored.events().size(); ++index) {
    const ExchangeEvent& expected = simulator.events()[snapshot_event_count + index];
    const ExchangeEvent& actual = restored.events()[index];
    ExpectEqualEvent(actual, expected);
  }
  const auto* execution = std::get_if<TradeExecuted>(&restored.events()[1].payload);
  ASSERT_NE(execution, nullptr);
  EXPECT_EQ(execution->execution.trade.id().value(), 1U);
  EXPECT_EQ(execution->execution.trade.sequence().value(), 5U);
}

TEST(ExchangeSimulator, ReplaysTheCommandJournalDeterministically) {
  const core::Market market = MakeMarket();
  ExchangeSimulator simulator = Require(ExchangeSimulator::create({market}));
  Require(simulator.enqueue(LimitRequest(1, market.contract().id(), core::Side::Sell, 2, 61, 1),
                            core::Timestamp::from_unix_nanoseconds(20)));
  Require(simulator.enqueue(LimitRequest(2, market.contract().id(), core::Side::Buy, 2, 61, 2),
                            core::Timestamp::from_unix_nanoseconds(10)));
  Require(simulator.run_until(core::Timestamp::from_unix_nanoseconds(20)));

  ExchangeSimulator replayed =
      Require(ExchangeSimulator::replay({market}, simulator.command_journal()));
  ASSERT_EQ(replayed.events().size(), simulator.events().size());
  for (std::size_t index = 0; index < simulator.events().size(); ++index) {
    ExpectEqualEvent(replayed.events()[index], simulator.events()[index]);
  }
}

}  // namespace
}  // namespace pmm::sim
