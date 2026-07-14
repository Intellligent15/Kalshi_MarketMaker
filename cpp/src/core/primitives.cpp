#include "pmm/core/primitives.hpp"

namespace pmm::core {

Result<Price> Price::from_units(std::int64_t value) {
  if (value < 0) {
    return DomainError{DomainErrorCode::InvalidPrice, "price cannot be negative"};
  }
  return Price(static_cast<std::uint64_t>(value));
}

Result<Quantity> Quantity::from_units(std::int64_t value) {
  if (value < 0) {
    return DomainError{DomainErrorCode::InvalidQuantity, "quantity cannot be negative"};
  }
  return Quantity(static_cast<std::uint64_t>(value));
}

Result<LotSize> LotSize::from_units(std::int64_t value) {
  if (value <= 0) {
    return DomainError{DomainErrorCode::InvalidLotSize, "lot size must be positive"};
  }
  return LotSize(static_cast<std::uint64_t>(value));
}

Result<PriceGrid> PriceGrid::create(Price minimum, Price maximum, Price increment) {
  if (increment.units() == 0) {
    return DomainError{DomainErrorCode::InvalidPriceGrid, "price increment must be positive"};
  }
  if (minimum > maximum) {
    return DomainError{DomainErrorCode::InvalidPriceGrid,
                       "minimum price cannot exceed maximum price"};
  }
  if ((maximum.units() - minimum.units()) % increment.units() != 0) {
    return DomainError{DomainErrorCode::InvalidPriceGrid,
                       "price range must contain an integral number of increments"};
  }
  return PriceGrid(minimum, maximum, increment);
}

bool PriceGrid::contains(Price price) const {
  if (price < minimum_ || price > maximum_) {
    return false;
  }
  return (price.units() - minimum_.units()) % increment_.units() == 0;
}

}  // namespace pmm::core
