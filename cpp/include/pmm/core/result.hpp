#pragma once

#include <optional>
#include <string>
#include <utility>
#include <variant>

namespace pmm::core {

enum class DomainErrorCode {
  InvalidIdentifier,
  InvalidPrice,
  InvalidQuantity,
  InvalidPriceGrid,
  InvalidLotSize,
  InvalidContract,
  InvalidMarket,
  InvalidOrder,
  InvalidTrade,
  InvalidFill,
  OwnershipMismatch,
  PositionOverflow,
  InvalidBook,
  DuplicateOrder,
  UnknownOrder,
  OrderNotResting,
  IdentifierExhausted,
  IoFailure,
  CorruptJournal,
  InconsistentJournal,
  RecoveryRequired,
};

struct DomainError {
  DomainErrorCode code;
  std::string message;
};

template <typename T>
class Result {
 public:
  Result(T value) : result_(std::move(value)) {}
  Result(DomainError error) : result_(std::move(error)) {}

  [[nodiscard]] bool has_value() const {
    return std::holds_alternative<T>(result_);
  }
  [[nodiscard]] explicit operator bool() const {
    return has_value();
  }

  [[nodiscard]] const T& value() const& {
    return std::get<T>(result_);
  }
  [[nodiscard]] T& value() & {
    return std::get<T>(result_);
  }
  [[nodiscard]] T&& value() && {
    return std::get<T>(std::move(result_));
  }
  [[nodiscard]] const DomainError& error() const {
    return std::get<DomainError>(result_);
  }

 private:
  std::variant<T, DomainError> result_;
};

template <>
class Result<void> {
 public:
  Result() = default;
  Result(DomainError error) : error_(std::move(error)) {}

  [[nodiscard]] bool has_value() const {
    return !error_.has_value();
  }
  [[nodiscard]] explicit operator bool() const {
    return has_value();
  }
  [[nodiscard]] const DomainError& error() const {
    return *error_;
  }

 private:
  std::optional<DomainError> error_;
};

}  // namespace pmm::core
