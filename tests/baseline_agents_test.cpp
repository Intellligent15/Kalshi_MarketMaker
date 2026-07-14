#include "pmm/agents/baseline_agents.hpp"

#include <gtest/gtest.h>

#include <variant>

namespace pmm::agents {
namespace {

template <typename T>
T Require(core::Result<T> result) {
  EXPECT_TRUE(result.has_value()) << result.error().message;
  return std::move(result).value();
}

void Require(core::Result<void> result) {
  EXPECT_TRUE(result.has_value()) << result.error().message;
}

core::Market MakeMarket() {
  const auto market_id = Require(core::MarketId::from_value(1));
  const auto contract_id = Require(core::ContractId::from_value(10));
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

AgentConfig Config(std::uint64_t agent_id, std::uint64_t trader_id, core::ContractId contract_id,
                   AgentKind kind, std::int64_t first_time = 10) {
  return AgentConfig{Require(AgentId::from_value(agent_id)),
                     Require(core::TraderId::from_value(trader_id)),
                     contract_id,
                     kind,
                     core::Timestamp::from_unix_nanoseconds(first_time),
                     10,
                     Require(core::Quantity::from_units(1)),
                     Require(core::Price::from_units(60)),
                     1};
}

sim::SubmitOrderRequest LimitRequest(std::uint64_t trader_id, core::ContractId contract_id,
                                     core::Side side, std::int64_t price) {
  return sim::SubmitOrderRequest{Require(core::TraderId::from_value(trader_id)),
                                 contract_id,
                                 side,
                                 core::OrderType::Limit,
                                 Require(core::Quantity::from_units(5)),
                                 Require(core::Price::from_units(price)),
                                 core::Timestamp::from_unix_nanoseconds(1)};
}

TEST(BaselineAgents, SameSeedProducesTheSameDecisionsAndEventStream) {
  const core::Market market = MakeMarket();
  const std::vector<AgentConfig> configs{
      Config(1, 101, market.contract().id(), AgentKind::Noise),
      Config(2, 102, market.contract().id(), AgentKind::LiquidityTaker)};
  SimulationCoordinator first = Require(SimulationCoordinator::create({market}, configs, 42));
  SimulationCoordinator second = Require(SimulationCoordinator::create({market}, configs, 42));

  for (SimulationCoordinator* coordinator : {&first, &second}) {
    Require(coordinator->enqueue_external(
        LimitRequest(900, market.contract().id(), core::Side::Buy, 50),
        core::Timestamp::from_unix_nanoseconds(10)));
    Require(coordinator->enqueue_external(
        LimitRequest(901, market.contract().id(), core::Side::Sell, 60),
        core::Timestamp::from_unix_nanoseconds(10)));
    Require(coordinator->run_until(core::Timestamp::from_unix_nanoseconds(30)));
  }

  ASSERT_EQ(first.decisions().size(), second.decisions().size());
  for (std::size_t index = 0; index < first.decisions().size(); ++index) {
    const AgentDecisionRecord& expected = first.decisions()[index];
    const AgentDecisionRecord& actual = second.decisions()[index];
    EXPECT_EQ(actual.agent_id, expected.agent_id);
    EXPECT_EQ(actual.decision_time, expected.decision_time);
    EXPECT_EQ(actual.event_watermark, expected.event_watermark);
    ASSERT_EQ(actual.intents.size(), expected.intents.size());
    if (!actual.intents.empty()) {
      EXPECT_EQ(actual.intents[0].request.side, expected.intents[0].request.side);
      EXPECT_EQ(actual.intents[0].request.trader_id, expected.intents[0].request.trader_id);
    }
  }
  ASSERT_EQ(first.exchange().events().size(), second.exchange().events().size());
  for (std::size_t index = 0; index < first.exchange().events().size(); ++index) {
    EXPECT_EQ(first.exchange().events()[index].sequence,
              second.exchange().events()[index].sequence);
    EXPECT_EQ(first.exchange().events()[index].occurred_at,
              second.exchange().events()[index].occurred_at);
    EXPECT_EQ(first.exchange().events()[index].payload.index(),
              second.exchange().events()[index].payload.index());
  }
}

TEST(BaselineAgents, SameTimeAgentsSeeOneStableEventWatermarkBeforeTheirCommands) {
  const core::Market market = MakeMarket();
  const std::vector<AgentConfig> configs{Config(2, 102, market.contract().id(), AgentKind::Noise),
                                         Config(1, 101, market.contract().id(), AgentKind::Noise)};
  SimulationCoordinator coordinator = Require(SimulationCoordinator::create({market}, configs, 7));
  Require(
      coordinator.enqueue_external(LimitRequest(900, market.contract().id(), core::Side::Sell, 60),
                                   core::Timestamp::from_unix_nanoseconds(10)));
  Require(coordinator.run_until(core::Timestamp::from_unix_nanoseconds(10)));

  ASSERT_EQ(coordinator.decisions().size(), 2U);
  EXPECT_EQ(coordinator.decisions()[0].agent_id.value(), 1U);
  EXPECT_EQ(coordinator.decisions()[1].agent_id.value(), 2U);
  EXPECT_EQ(coordinator.decisions()[0].event_watermark, coordinator.decisions()[1].event_watermark);
  EXPECT_LT(coordinator.decisions()[0].event_watermark,
            coordinator.exchange().events().back().sequence.value());
}

TEST(BaselineAgents, CheckpointRestoresAgentScheduleRandomStateAndProjection) {
  const core::Market market = MakeMarket();
  const std::vector<AgentConfig> configs{Config(1, 101, market.contract().id(), AgentKind::Noise)};
  SimulationCoordinator original = Require(SimulationCoordinator::create({market}, configs, 19));
  Require(original.run_until(core::Timestamp::from_unix_nanoseconds(10)));
  const SimulationCheckpoint checkpoint = original.checkpoint();
  const std::size_t event_count = original.exchange().events().size();
  Require(original.run_until(core::Timestamp::from_unix_nanoseconds(20)));

  SimulationCoordinator restored = Require(SimulationCoordinator::restore(checkpoint, configs, 19));
  Require(restored.run_until(core::Timestamp::from_unix_nanoseconds(20)));
  ASSERT_EQ(restored.decisions().size(), 1U);
  ASSERT_EQ(original.decisions().size(), 2U);
  ASSERT_EQ(restored.decisions()[0].intents.size(), original.decisions()[1].intents.size());
  EXPECT_EQ(restored.decisions()[0].intents[0].request.side,
            original.decisions()[1].intents[0].request.side);
  ASSERT_EQ(restored.exchange().events().size(), original.exchange().events().size() - event_count);
  for (std::size_t index = 0; index < restored.exchange().events().size(); ++index) {
    EXPECT_EQ(restored.exchange().events()[index].sequence,
              original.exchange().events()[event_count + index].sequence);
    EXPECT_EQ(restored.exchange().events()[index].payload.index(),
              original.exchange().events()[event_count + index].payload.index());
  }
}

TEST(BaselineAgents, SignalAgentsUseOnlyThePulledMarketProjection) {
  const core::Market market = MakeMarket();
  const std::vector<AgentConfig> configs{
      Config(1, 101, market.contract().id(), AgentKind::Informed),
      Config(2, 102, market.contract().id(), AgentKind::MeanReversion),
      Config(3, 103, market.contract().id(), AgentKind::LiquidityTaker),
      Config(4, 104, market.contract().id(), AgentKind::Momentum)};
  SimulationCoordinator coordinator = Require(SimulationCoordinator::create({market}, configs, 1));
  Require(
      coordinator.enqueue_external(LimitRequest(900, market.contract().id(), core::Side::Buy, 50),
                                   core::Timestamp::from_unix_nanoseconds(10)));
  Require(
      coordinator.enqueue_external(LimitRequest(901, market.contract().id(), core::Side::Sell, 59),
                                   core::Timestamp::from_unix_nanoseconds(10)));
  Require(coordinator.run_until(core::Timestamp::from_unix_nanoseconds(10)));

  ASSERT_EQ(coordinator.decisions().size(), 4U);
  EXPECT_EQ(coordinator.decisions()[0].intents[0].request.side, core::Side::Buy);
  EXPECT_EQ(coordinator.decisions()[1].intents[0].request.side, core::Side::Buy);
  EXPECT_TRUE(coordinator.decisions()[2].intents.empty());
  EXPECT_TRUE(coordinator.decisions()[3].intents.empty());
}

TEST(BaselineAgents, MomentumUsesASequencedTradeRatherThanWallClockState) {
  const core::Market market = MakeMarket();
  const std::vector<AgentConfig> configs{
      Config(1, 101, market.contract().id(), AgentKind::Momentum, 20)};
  SimulationCoordinator coordinator = Require(SimulationCoordinator::create({market}, configs, 1));
  Require(
      coordinator.enqueue_external(LimitRequest(900, market.contract().id(), core::Side::Sell, 62),
                                   core::Timestamp::from_unix_nanoseconds(10)));
  Require(
      coordinator.enqueue_external(LimitRequest(901, market.contract().id(), core::Side::Buy, 62),
                                   core::Timestamp::from_unix_nanoseconds(11)));
  Require(coordinator.run_until(core::Timestamp::from_unix_nanoseconds(20)));

  ASSERT_EQ(coordinator.decisions().size(), 1U);
  ASSERT_EQ(coordinator.decisions()[0].intents.size(), 1U);
  EXPECT_EQ(coordinator.decisions()[0].intents[0].request.side, core::Side::Buy);
}

}  // namespace
}  // namespace pmm::agents
