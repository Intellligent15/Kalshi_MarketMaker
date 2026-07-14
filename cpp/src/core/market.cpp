#include "pmm/core/market.hpp"

#include <utility>

namespace pmm::core {

Result<Contract> Contract::create(ContractId id, MarketId market_id, Price payout,
                                  PriceGrid price_grid, LotSize lot_size) {
  if (payout.units() == 0) {
    return DomainError{DomainErrorCode::InvalidContract, "binary contract payout must be positive"};
  }
  if (price_grid.maximum() > payout) {
    return DomainError{DomainErrorCode::InvalidContract,
                       "binary contract price grid cannot exceed its payout"};
  }
  return Contract(id, market_id, payout, price_grid, lot_size);
}

Result<void> Contract::validate_price(Price price) const {
  if (!price_grid_.contains(price)) {
    return DomainError{DomainErrorCode::InvalidPrice,
                       "price does not satisfy the contract price grid"};
  }
  return {};
}

Result<void> Contract::validate_quantity(Quantity quantity) const {
  if (quantity.is_zero()) {
    return DomainError{DomainErrorCode::InvalidQuantity, "order quantity must be positive"};
  }
  if (quantity.units() % lot_size_.units() != 0) {
    return DomainError{DomainErrorCode::InvalidQuantity,
                       "quantity does not satisfy the contract lot size"};
  }
  return {};
}

Result<Market> Market::create(MarketId id, std::string title, Contract contract,
                              MarketStatus status) {
  if (title.empty()) {
    return DomainError{DomainErrorCode::InvalidMarket, "market title cannot be empty"};
  }
  if (contract.market_id() != id) {
    return DomainError{DomainErrorCode::InvalidMarket,
                       "contract must belong to the market that owns it"};
  }
  return Market(id, std::move(title), std::move(contract), status);
}

}  // namespace pmm::core
