#include "pmm/core/inventory.hpp"

#include <limits>

namespace pmm::core {

Position Position::flat(TraderId trader_id, ContractId contract_id) {
  return Position(trader_id, contract_id, 0, std::nullopt, std::nullopt);
}

Result<void> Position::apply_fill(const Fill& fill) {
  if (fill.trader_id() != trader_id_ || fill.contract_id() != contract_id_) {
    return DomainError{DomainErrorCode::OwnershipMismatch, "fill does not belong to this position"};
  }

  if (fill.quantity().units() >
      static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max())) {
    return DomainError{DomainErrorCode::PositionOverflow,
                       "fill quantity cannot be represented by a signed position"};
  }

  const std::int64_t quantity = static_cast<std::int64_t>(fill.quantity().units());
  if (fill.side() == Side::Buy) {
    if (net_quantity_ > std::numeric_limits<std::int64_t>::max() - quantity) {
      return DomainError{DomainErrorCode::PositionOverflow, "position quantity overflow"};
    }
    net_quantity_ += quantity;
  } else {
    if (net_quantity_ < std::numeric_limits<std::int64_t>::min() + quantity) {
      return DomainError{DomainErrorCode::PositionOverflow, "position quantity underflow"};
    }
    net_quantity_ -= quantity;
  }
  updated_at_ = fill.executed_at();
  update_sequence_ = fill.sequence();
  return {};
}

Inventory Inventory::create(TraderId trader_id) {
  return Inventory(trader_id);
}

const Position* Inventory::find_position(ContractId contract_id) const {
  const auto position = positions_.find(contract_id);
  return position == positions_.end() ? nullptr : &position->second;
}

Result<void> Inventory::apply_fill(const Fill& fill) {
  if (fill.trader_id() != trader_id_) {
    return DomainError{DomainErrorCode::OwnershipMismatch,
                       "fill trader does not match inventory trader"};
  }

  auto position = positions_.find(fill.contract_id());
  if (position == positions_.end()) {
    position =
        positions_.emplace(fill.contract_id(), Position::flat(trader_id_, fill.contract_id()))
            .first;
  }
  return position->second.apply_fill(fill);
}

}  // namespace pmm::core
