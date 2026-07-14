#pragma once

#include <optional>

#include "pmm/core/market.hpp"

namespace pmm::core {

class Order {
 public:
  [[nodiscard]] static Result<Order> create_limit(OrderId id, TraderId trader_id,
                                                  ContractId contract_id, Side side,
                                                  Quantity quantity, Price limit_price,
                                                  Timestamp submitted_at, const Contract& contract);
  [[nodiscard]] static Result<Order> create_market(OrderId id, TraderId trader_id,
                                                   ContractId contract_id, Side side,
                                                   Quantity quantity, Timestamp submitted_at,
                                                   const Contract& contract);

  [[nodiscard]] const OrderId& id() const {
    return id_;
  }
  [[nodiscard]] const TraderId& trader_id() const {
    return trader_id_;
  }
  [[nodiscard]] const ContractId& contract_id() const {
    return contract_id_;
  }
  [[nodiscard]] Side side() const {
    return side_;
  }
  [[nodiscard]] OrderType type() const {
    return type_;
  }
  [[nodiscard]] const Quantity& quantity() const {
    return quantity_;
  }
  [[nodiscard]] const std::optional<Price>& limit_price() const {
    return limit_price_;
  }
  [[nodiscard]] const Timestamp& submitted_at() const {
    return submitted_at_;
  }

 private:
  Order(OrderId id, TraderId trader_id, ContractId contract_id, Side side, OrderType type,
        Quantity quantity, std::optional<Price> limit_price, Timestamp submitted_at)
      : id_(id),
        trader_id_(trader_id),
        contract_id_(contract_id),
        side_(side),
        type_(type),
        quantity_(quantity),
        limit_price_(limit_price),
        submitted_at_(submitted_at) {}

  OrderId id_;
  TraderId trader_id_;
  ContractId contract_id_;
  Side side_;
  OrderType type_;
  Quantity quantity_;
  std::optional<Price> limit_price_;
  Timestamp submitted_at_;
};

}  // namespace pmm::core
