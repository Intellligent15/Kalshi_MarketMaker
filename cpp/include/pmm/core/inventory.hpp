#pragma once

#include <cstdint>
#include <map>
#include <optional>

#include "pmm/core/execution.hpp"

namespace pmm::core {

class Position {
 public:
  [[nodiscard]] static Position flat(TraderId trader_id, ContractId contract_id);

  [[nodiscard]] const TraderId& trader_id() const {
    return trader_id_;
  }
  [[nodiscard]] const ContractId& contract_id() const {
    return contract_id_;
  }
  [[nodiscard]] std::int64_t net_quantity() const {
    return net_quantity_;
  }
  [[nodiscard]] const std::optional<Timestamp>& updated_at() const {
    return updated_at_;
  }
  [[nodiscard]] const std::optional<SequenceNumber>& update_sequence() const {
    return update_sequence_;
  }

  [[nodiscard]] Result<void> apply_fill(const Fill& fill);

 private:
  Position(TraderId trader_id, ContractId contract_id, std::int64_t net_quantity,
           std::optional<Timestamp> updated_at, std::optional<SequenceNumber> update_sequence)
      : trader_id_(trader_id),
        contract_id_(contract_id),
        net_quantity_(net_quantity),
        updated_at_(updated_at),
        update_sequence_(update_sequence) {}

  TraderId trader_id_;
  ContractId contract_id_;
  std::int64_t net_quantity_;
  std::optional<Timestamp> updated_at_;
  std::optional<SequenceNumber> update_sequence_;
};

class Inventory {
 public:
  [[nodiscard]] static Inventory create(TraderId trader_id);

  [[nodiscard]] const TraderId& trader_id() const {
    return trader_id_;
  }
  [[nodiscard]] const Position* find_position(ContractId contract_id) const;
  [[nodiscard]] const std::map<ContractId, Position>& positions() const {
    return positions_;
  }
  [[nodiscard]] Result<void> apply_fill(const Fill& fill);

 private:
  explicit Inventory(TraderId trader_id) : trader_id_(trader_id) {}

  TraderId trader_id_;
  std::map<ContractId, Position> positions_;
};

}  // namespace pmm::core
