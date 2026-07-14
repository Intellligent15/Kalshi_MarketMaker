#pragma once

#include <compare>
#include <cstdint>
#include <functional>
#include <string_view>

#include "pmm/core/result.hpp"

namespace pmm::core {

template <typename Tag>
class Identifier {
 public:
  [[nodiscard]] static Result<Identifier> from_value(std::uint64_t value) {
    if (value == 0) {
      return DomainError{DomainErrorCode::InvalidIdentifier,
                         "identifier values must be greater than zero"};
    }
    return Identifier(value);
  }

  [[nodiscard]] std::uint64_t value() const {
    return value_;
  }
  [[nodiscard]] auto operator<=>(const Identifier&) const = default;

 private:
  explicit Identifier(std::uint64_t value) : value_(value) {}

  std::uint64_t value_;
};

struct MarketIdTag {};
struct ContractIdTag {};
struct OrderIdTag {};
struct TradeIdTag {};
struct TraderIdTag {};
struct SequenceNumberTag {};

using MarketId = Identifier<MarketIdTag>;
using ContractId = Identifier<ContractIdTag>;
using OrderId = Identifier<OrderIdTag>;
using TradeId = Identifier<TradeIdTag>;
using TraderId = Identifier<TraderIdTag>;
using SequenceNumber = Identifier<SequenceNumberTag>;

struct IdentifierHash {
  template <typename Tag>
  [[nodiscard]] std::size_t operator()(const Identifier<Tag>& identifier) const {
    return std::hash<std::uint64_t>{}(identifier.value());
  }
};

}  // namespace pmm::core
