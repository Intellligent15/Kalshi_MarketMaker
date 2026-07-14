#include <gtest/gtest.h>

#include "pmm/core/core.hpp"

namespace pmm::core {
namespace {

template <typename T>
T Require(Result<T> result) {
  EXPECT_TRUE(result.has_value()) << result.error().message;
  return std::move(result).value();
}

Contract MakeContract() {
  const MarketId market_id = Require(MarketId::from_value(1));
  const ContractId contract_id = Require(ContractId::from_value(10));
  const Price minimum = Require(Price::from_units(1));
  const Price maximum = Require(Price::from_units(99));
  const Price increment = Require(Price::from_units(1));
  const Price payout = Require(Price::from_units(100));
  const PriceGrid price_grid = Require(PriceGrid::create(minimum, maximum, increment));
  const LotSize lot_size = Require(LotSize::from_units(1));
  return Require(Contract::create(contract_id, market_id, payout, price_grid, lot_size));
}

Trade MakeTrade(const Contract& contract) {
  return Require(Trade::create(
      Require(TradeId::from_value(100)), contract.id(), Require(OrderId::from_value(200)),
      Require(OrderId::from_value(201)), Require(TraderId::from_value(300)),
      Require(TraderId::from_value(301)), Require(Price::from_units(63)),
      Require(Quantity::from_units(2)), Timestamp::from_unix_nanoseconds(42),
      Require(SequenceNumber::from_value(1)), Side::Buy, contract));
}

TEST(Identifiers, RejectsZeroAndKeepsTypesDistinct) {
  const auto invalid_id = MarketId::from_value(0);
  EXPECT_FALSE(invalid_id.has_value());
  EXPECT_EQ(invalid_id.error().code, DomainErrorCode::InvalidIdentifier);

  const MarketId market_id = Require(MarketId::from_value(1));
  const ContractId contract_id = Require(ContractId::from_value(1));
  EXPECT_EQ(market_id.value(), contract_id.value());
}

TEST(PriceGrid, EnforcesRangeAndIncrement) {
  const Price minimum = Require(Price::from_units(1));
  const Price maximum = Require(Price::from_units(99));
  const Price increment = Require(Price::from_units(2));
  const PriceGrid grid = Require(PriceGrid::create(minimum, maximum, increment));

  EXPECT_TRUE(grid.contains(Require(Price::from_units(63))));
  EXPECT_FALSE(grid.contains(Require(Price::from_units(62))));
  EXPECT_FALSE(grid.contains(Require(Price::from_units(100))));
  EXPECT_FALSE(Price::from_units(-1).has_value());
  EXPECT_FALSE(PriceGrid::create(minimum, maximum, Require(Price::from_units(0))).has_value());
}

TEST(Market, RequiresAContractToBelongToItsOwningMarket) {
  const Contract contract = MakeContract();
  const auto wrong_market = Market::create(Require(MarketId::from_value(2)), "Question", contract);

  EXPECT_FALSE(wrong_market.has_value());
  EXPECT_EQ(wrong_market.error().code, DomainErrorCode::InvalidMarket);
}

TEST(ContractRules, RejectInvalidPayoutAndLotMisalignment) {
  const MarketId market_id = Require(MarketId::from_value(1));
  const ContractId contract_id = Require(ContractId::from_value(10));
  const Price minimum = Require(Price::from_units(1));
  const Price maximum = Require(Price::from_units(99));
  const PriceGrid price_grid =
      Require(PriceGrid::create(minimum, maximum, Require(Price::from_units(1))));
  const LotSize lot_size = Require(LotSize::from_units(5));

  EXPECT_FALSE(
      Contract::create(contract_id, market_id, Require(Price::from_units(50)), price_grid, lot_size)
          .has_value());

  const Contract contract = Require(Contract::create(
      contract_id, market_id, Require(Price::from_units(100)), price_grid, lot_size));
  EXPECT_FALSE(contract.validate_quantity(Require(Quantity::from_units(0))).has_value());
  EXPECT_FALSE(contract.validate_quantity(Require(Quantity::from_units(3))).has_value());
  EXPECT_TRUE(contract.validate_quantity(Require(Quantity::from_units(5))).has_value());
}

TEST(Order, ValidatesContractRulesAndSeparatesMarketOrders) {
  const Contract contract = MakeContract();
  const OrderId order_id = Require(OrderId::from_value(20));
  const TraderId trader_id = Require(TraderId::from_value(30));
  const Quantity quantity = Require(Quantity::from_units(4));
  const Timestamp submitted_at = Timestamp::from_unix_nanoseconds(100);

  const Order limit_order =
      Require(Order::create_limit(order_id, trader_id, contract.id(), Side::Buy, quantity,
                                  Require(Price::from_units(63)), submitted_at, contract));
  const Order market_order =
      Require(Order::create_market(Require(OrderId::from_value(21)), trader_id, contract.id(),
                                   Side::Sell, quantity, submitted_at, contract));

  EXPECT_EQ(limit_order.type(), OrderType::Limit);
  ASSERT_TRUE(limit_order.limit_price().has_value());
  EXPECT_EQ(limit_order.limit_price()->units(), 63U);
  EXPECT_EQ(market_order.type(), OrderType::Market);
  EXPECT_FALSE(market_order.limit_price().has_value());
  EXPECT_FALSE(Order::create_limit(order_id, trader_id, contract.id(), Side::Buy, quantity,
                                   Require(Price::from_units(100)), submitted_at, contract)
                   .has_value());
}

TEST(TradeAndFill, ProduceComplementaryTraderSpecificEvents) {
  const Contract contract = MakeContract();
  const Trade trade = MakeTrade(contract);
  const Fill buyer_fill = Fill::for_buyer(trade);
  const Fill seller_fill = Fill::for_seller(trade);

  EXPECT_EQ(buyer_fill.trade_id(), seller_fill.trade_id());
  EXPECT_EQ(buyer_fill.side(), Side::Buy);
  EXPECT_EQ(seller_fill.side(), Side::Sell);
  EXPECT_EQ(buyer_fill.quantity(), seller_fill.quantity());
  EXPECT_NE(buyer_fill.trader_id(), seller_fill.trader_id());
}

TEST(Inventory, UpdatesNetPositionFromOwnedFills) {
  const Contract contract = MakeContract();
  const Trade trade = MakeTrade(contract);
  const Fill buyer_fill = Fill::for_buyer(trade);
  const Fill seller_fill = Fill::for_seller(trade);
  Inventory inventory = Inventory::create(buyer_fill.trader_id());

  EXPECT_TRUE(inventory.apply_fill(buyer_fill).has_value());
  const Position* position = inventory.find_position(contract.id());
  ASSERT_NE(position, nullptr);
  EXPECT_EQ(position->net_quantity(), 2);
  ASSERT_TRUE(position->updated_at().has_value());
  ASSERT_TRUE(position->update_sequence().has_value());
  EXPECT_EQ(position->update_sequence()->value(), 1U);

  EXPECT_FALSE(inventory.apply_fill(seller_fill).has_value());
  EXPECT_EQ(position->net_quantity(), 2);

  Inventory seller_inventory = Inventory::create(seller_fill.trader_id());
  EXPECT_TRUE(seller_inventory.apply_fill(seller_fill).has_value());
  const Position* seller_position = seller_inventory.find_position(contract.id());
  ASSERT_NE(seller_position, nullptr);
  EXPECT_EQ(seller_position->net_quantity(), -2);
}

}  // namespace
}  // namespace pmm::core
