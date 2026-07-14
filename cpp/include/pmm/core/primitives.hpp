#pragma once

#include <compare>
#include <cstdint>

#include "pmm/core/result.hpp"

namespace pmm::core {

class Timestamp {
 public:
  [[nodiscard]] static constexpr Timestamp from_unix_nanoseconds(std::int64_t value) {
    return Timestamp(value);
  }

  [[nodiscard]] constexpr std::int64_t unix_nanoseconds() const {
    return value_;
  }
  [[nodiscard]] constexpr auto operator<=>(const Timestamp&) const = default;

 private:
  explicit constexpr Timestamp(std::int64_t value) : value_(value) {}

  std::int64_t value_;
};

class Price {
 public:
  [[nodiscard]] static Result<Price> from_units(std::int64_t value);

  [[nodiscard]] std::uint64_t units() const {
    return units_;
  }
  [[nodiscard]] auto operator<=>(const Price&) const = default;

 private:
  explicit Price(std::uint64_t units) : units_(units) {}

  std::uint64_t units_;
};

class Quantity {
 public:
  [[nodiscard]] static Result<Quantity> from_units(std::int64_t value);

  [[nodiscard]] std::uint64_t units() const {
    return units_;
  }
  [[nodiscard]] bool is_zero() const {
    return units_ == 0;
  }
  [[nodiscard]] auto operator<=>(const Quantity&) const = default;

 private:
  explicit Quantity(std::uint64_t units) : units_(units) {}

  std::uint64_t units_;
};

class LotSize {
 public:
  [[nodiscard]] static Result<LotSize> from_units(std::int64_t value);

  [[nodiscard]] std::uint64_t units() const {
    return units_;
  }
  [[nodiscard]] auto operator<=>(const LotSize&) const = default;

 private:
  explicit LotSize(std::uint64_t units) : units_(units) {}

  std::uint64_t units_;
};

class PriceGrid {
 public:
  [[nodiscard]] static Result<PriceGrid> create(Price minimum, Price maximum, Price increment);

  [[nodiscard]] const Price& minimum() const {
    return minimum_;
  }
  [[nodiscard]] const Price& maximum() const {
    return maximum_;
  }
  [[nodiscard]] const Price& increment() const {
    return increment_;
  }
  [[nodiscard]] bool contains(Price price) const;

 private:
  PriceGrid(Price minimum, Price maximum, Price increment)
      : minimum_(minimum), maximum_(maximum), increment_(increment) {}

  Price minimum_;
  Price maximum_;
  Price increment_;
};

enum class Side {
  Buy,
  Sell,
};

enum class OrderType {
  Limit,
  Market,
};

}  // namespace pmm::core
