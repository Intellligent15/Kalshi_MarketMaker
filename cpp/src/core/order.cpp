#include "pmm/core/order.hpp"

namespace pmm::core {

namespace {

Result<void> ValidateOrderContract(ContractId contract_id, Quantity quantity,
                                   const Contract& contract) {
  if (contract_id != contract.id()) {
    return DomainError{DomainErrorCode::InvalidOrder,
                       "order contract identifier does not match validation contract"};
  }
  return contract.validate_quantity(quantity);
}

}  // namespace

Result<Order> Order::create_limit(OrderId id, TraderId trader_id, ContractId contract_id, Side side,
                                  Quantity quantity, Price limit_price, Timestamp submitted_at,
                                  const Contract& contract) {
  const Result<void> contract_validation = ValidateOrderContract(contract_id, quantity, contract);
  if (!contract_validation) {
    return contract_validation.error();
  }
  const Result<void> price_validation = contract.validate_price(limit_price);
  if (!price_validation) {
    return price_validation.error();
  }
  return Order(id, trader_id, contract_id, side, OrderType::Limit, quantity, limit_price,
               submitted_at);
}

Result<Order> Order::create_market(OrderId id, TraderId trader_id, ContractId contract_id,
                                   Side side, Quantity quantity, Timestamp submitted_at,
                                   const Contract& contract) {
  const Result<void> contract_validation = ValidateOrderContract(contract_id, quantity, contract);
  if (!contract_validation) {
    return contract_validation.error();
  }
  return Order(id, trader_id, contract_id, side, OrderType::Market, quantity, std::nullopt,
               submitted_at);
}

}  // namespace pmm::core
