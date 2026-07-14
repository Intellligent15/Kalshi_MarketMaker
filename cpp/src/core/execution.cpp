#include "pmm/core/execution.hpp"

namespace pmm::core {

Result<Trade> Trade::create(TradeId id, ContractId contract_id, OrderId buyer_order_id,
                            OrderId seller_order_id, TraderId buyer_trader_id,
                            TraderId seller_trader_id, Price price, Quantity quantity,
                            Timestamp executed_at, SequenceNumber sequence,
                            std::optional<Side> aggressor_side, const Contract& contract) {
  if (contract_id != contract.id()) {
    return DomainError{DomainErrorCode::InvalidTrade,
                       "trade contract identifier does not match validation contract"};
  }
  if (buyer_order_id == seller_order_id) {
    return DomainError{DomainErrorCode::InvalidTrade, "buyer and seller orders must differ"};
  }
  if (buyer_trader_id == seller_trader_id) {
    return DomainError{DomainErrorCode::InvalidTrade, "buyer and seller traders must differ"};
  }
  const Result<void> price_validation = contract.validate_price(price);
  if (!price_validation) {
    return price_validation.error();
  }
  const Result<void> quantity_validation = contract.validate_quantity(quantity);
  if (!quantity_validation) {
    return quantity_validation.error();
  }
  return Trade(id, contract_id, buyer_order_id, seller_order_id, buyer_trader_id, seller_trader_id,
               price, quantity, executed_at, sequence, aggressor_side);
}

Fill Fill::for_buyer(const Trade& trade) {
  return Fill(trade.id(), trade.buyer_order_id(), trade.buyer_trader_id(), trade.contract_id(),
              Side::Buy, trade.price(), trade.quantity(), trade.executed_at(), trade.sequence());
}

Fill Fill::for_seller(const Trade& trade) {
  return Fill(trade.id(), trade.seller_order_id(), trade.seller_trader_id(), trade.contract_id(),
              Side::Sell, trade.price(), trade.quantity(), trade.executed_at(), trade.sequence());
}

}  // namespace pmm::core
