#include "pmm/market_maker/market_maker.hpp"

#include <gtest/gtest.h>

namespace pmm::market_maker {
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
  const auto grid = Require(core::PriceGrid::create(Require(core::Price::from_units(1)),
                                                    Require(core::Price::from_units(99)),
                                                    Require(core::Price::from_units(1))));
  const auto contract =
      Require(core::Contract::create(contract_id, market_id, Require(core::Price::from_units(100)),
                                     grid, Require(core::LotSize::from_units(1))));
  return Require(core::Market::create(market_id, "Question", contract));
}

MarketMakerConfig Config(core::ContractId contract_id) {
  return MarketMakerConfig{
      risk::AccountBinding{Require(risk::AccountId::from_value(1)),
                           Require(risk::StrategyId::from_value(2)),
                           Require(core::TraderId::from_value(3)), contract_id},
      risk::RiskLimits{
          Require(core::Quantity::from_units(2)), Require(core::Quantity::from_units(4)),
          Require(core::Quantity::from_units(4)), Require(core::Quantity::from_units(4)),
          Require(core::Quantity::from_units(4)), 4},
      core::Timestamp::from_unix_nanoseconds(10),
      10,
      Require(core::Quantity::from_units(1)),
      Require(core::Price::from_units(50)),
      ReferencePriceSource::Configured,
      2,
      2,
      2};
}

TEST(MarketMaker, ProducesTwoPassiveFixedSpreadQuotesThroughRiskAdmission) {
  const core::Market market = MakeMarket();
  MarketMakingCoordinator coordinator =
      Require(MarketMakingCoordinator::create({market}, Config(market.contract().id())));
  Require(coordinator.run_until(core::Timestamp::from_unix_nanoseconds(10)));
  ASSERT_EQ(coordinator.decisions().size(), 1U);
  const QuoteDecisionRecord& decision = coordinator.decisions().front();
  ASSERT_TRUE(decision.bid_price.has_value());
  ASSERT_TRUE(decision.ask_price.has_value());
  EXPECT_EQ(decision.bid_price->units(), 48U);
  EXPECT_EQ(decision.ask_price->units(), 52U);
  ASSERT_EQ(decision.admissions.size(), 2U);
  EXPECT_TRUE(decision.admissions[0].approved());
  EXPECT_TRUE(decision.admissions[1].approved());
  EXPECT_EQ(coordinator.risk().live_orders().size(), 2U);
}

TEST(MarketMaker, KillSwitchCancelsProjectedQuotesAndBlocksReplacement) {
  const core::Market market = MakeMarket();
  MarketMakingCoordinator coordinator =
      Require(MarketMakingCoordinator::create({market}, Config(market.contract().id())));
  Require(coordinator.run_until(core::Timestamp::from_unix_nanoseconds(10)));
  coordinator.activate_kill_switch();
  Require(coordinator.run_until(core::Timestamp::from_unix_nanoseconds(20)));
  ASSERT_EQ(coordinator.decisions().size(), 2U);
  EXPECT_EQ(coordinator.decisions()[1].cancellations.size(), 2U);
  EXPECT_TRUE(coordinator.decisions()[1].admissions.empty());
  EXPECT_TRUE(coordinator.risk().live_orders().empty());
}

TEST(MarketMaker, CancelsQuotesThatExceedTheirLogicalAge) {
  const core::Market market = MakeMarket();
  MarketMakerConfig config = Config(market.contract().id());
  config.maximum_quote_age_nanoseconds = 5;
  MarketMakingCoordinator coordinator = Require(MarketMakingCoordinator::create({market}, config));
  Require(coordinator.run_until(core::Timestamp::from_unix_nanoseconds(10)));
  Require(coordinator.run_until(core::Timestamp::from_unix_nanoseconds(20)));
  ASSERT_EQ(coordinator.decisions().size(), 2U);
  EXPECT_EQ(coordinator.decisions()[1].cancellations.size(), 2U);
  ASSERT_EQ(coordinator.decisions()[1].admissions.size(), 2U);
  EXPECT_TRUE(coordinator.decisions()[1].admissions[0].approved());
  EXPECT_TRUE(coordinator.decisions()[1].admissions[1].approved());
  EXPECT_EQ(coordinator.risk().live_orders().size(), 2U);
}

TEST(MarketMaker, InventoryAwareSkewMovesBothDesiredQuotesAfterAFill) {
  const core::Market market = MakeMarket();
  MarketMakerConfig config = Config(market.contract().id());
  config.risk_limits.maximum_absolute_position = Require(core::Quantity::from_units(1));
  MarketMakingCoordinator coordinator = Require(MarketMakingCoordinator::create({market}, config));
  Require(coordinator.run_until(core::Timestamp::from_unix_nanoseconds(10)));
  const sim::SubmitOrderRequest sell{Require(core::TraderId::from_value(9)),
                                     market.contract().id(),
                                     core::Side::Sell,
                                     core::OrderType::Limit,
                                     Require(core::Quantity::from_units(1)),
                                     Require(core::Price::from_units(48)),
                                     core::Timestamp::from_unix_nanoseconds(15)};
  Require(coordinator.enqueue_external(sell, core::Timestamp::from_unix_nanoseconds(15)));
  Require(coordinator.run_until(core::Timestamp::from_unix_nanoseconds(20)));
  ASSERT_EQ(coordinator.decisions().size(), 2U);
  const QuoteDecisionRecord& after_fill = coordinator.decisions()[1];
  EXPECT_EQ(after_fill.risk_view.net_position, 1);
  ASSERT_TRUE(after_fill.bid_price.has_value());
  ASSERT_TRUE(after_fill.ask_price.has_value());
  EXPECT_EQ(after_fill.bid_price->units(), 46U);
  EXPECT_EQ(after_fill.ask_price->units(), 50U);
}

TEST(MarketMaker, CheckpointRestoresRiskAndQuoteContinuation) {
  const core::Market market = MakeMarket();
  const MarketMakerConfig config = Config(market.contract().id());
  MarketMakingCoordinator original = Require(MarketMakingCoordinator::create({market}, config));
  Require(original.run_until(core::Timestamp::from_unix_nanoseconds(10)));
  const MarketMakerCheckpoint checkpoint = original.checkpoint();
  const sim::SubmitOrderRequest sell{Require(core::TraderId::from_value(9)),
                                     market.contract().id(),
                                     core::Side::Sell,
                                     core::OrderType::Limit,
                                     Require(core::Quantity::from_units(1)),
                                     Require(core::Price::from_units(48)),
                                     core::Timestamp::from_unix_nanoseconds(15)};
  Require(original.enqueue_external(sell, core::Timestamp::from_unix_nanoseconds(15)));
  Require(original.run_until(core::Timestamp::from_unix_nanoseconds(20)));

  MarketMakingCoordinator restored = Require(MarketMakingCoordinator::restore(checkpoint, config));
  Require(restored.enqueue_external(sell, core::Timestamp::from_unix_nanoseconds(15)));
  Require(restored.run_until(core::Timestamp::from_unix_nanoseconds(20)));
  ASSERT_EQ(restored.decisions().size(), 1U);
  ASSERT_EQ(original.decisions().size(), 2U);
  EXPECT_EQ(restored.decisions()[0].risk_view.net_position,
            original.decisions()[1].risk_view.net_position);
  EXPECT_EQ(restored.decisions()[0].bid_price, original.decisions()[1].bid_price);
  EXPECT_EQ(restored.decisions()[0].ask_price, original.decisions()[1].ask_price);
  ASSERT_EQ(restored.exchange().events().size(), original.exchange().events().size() - 6U);
  for (std::size_t index = 0; index < restored.exchange().events().size(); ++index) {
    EXPECT_EQ(restored.exchange().events()[index].sequence,
              original.exchange().events()[index + 6U].sequence);
    EXPECT_EQ(restored.exchange().events()[index].ingress_sequence,
              original.exchange().events()[index + 6U].ingress_sequence);
    EXPECT_EQ(restored.exchange().events()[index].payload.index(),
              original.exchange().events()[index + 6U].payload.index());
  }
}

}  // namespace
}  // namespace pmm::market_maker
