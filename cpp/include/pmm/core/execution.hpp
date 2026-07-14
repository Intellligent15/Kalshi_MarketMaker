#pragma once

#include <optional>

#include "pmm/core/order.hpp"

namespace pmm::core {

class Trade {
 public:
  [[nodiscard]] static Result<Trade> create(TradeId id, ContractId contract_id,
                                            OrderId buyer_order_id, OrderId seller_order_id,
                                            TraderId buyer_trader_id, TraderId seller_trader_id,
                                            Price price, Quantity quantity, Timestamp executed_at,
                                            SequenceNumber sequence,
                                            std::optional<Side> aggressor_side,
                                            const Contract& contract);

  [[nodiscard]] const TradeId& id() const {
    return id_;
  }
  [[nodiscard]] const ContractId& contract_id() const {
    return contract_id_;
  }
  [[nodiscard]] const OrderId& buyer_order_id() const {
    return buyer_order_id_;
  }
  [[nodiscard]] const OrderId& seller_order_id() const {
    return seller_order_id_;
  }
  [[nodiscard]] const TraderId& buyer_trader_id() const {
    return buyer_trader_id_;
  }
  [[nodiscard]] const TraderId& seller_trader_id() const {
    return seller_trader_id_;
  }
  [[nodiscard]] const Price& price() const {
    return price_;
  }
  [[nodiscard]] const Quantity& quantity() const {
    return quantity_;
  }
  [[nodiscard]] const Timestamp& executed_at() const {
    return executed_at_;
  }
  [[nodiscard]] const SequenceNumber& sequence() const {
    return sequence_;
  }
  [[nodiscard]] const std::optional<Side>& aggressor_side() const {
    return aggressor_side_;
  }

 private:
  Trade(TradeId id, ContractId contract_id, OrderId buyer_order_id, OrderId seller_order_id,
        TraderId buyer_trader_id, TraderId seller_trader_id, Price price, Quantity quantity,
        Timestamp executed_at, SequenceNumber sequence, std::optional<Side> aggressor_side)
      : id_(id),
        contract_id_(contract_id),
        buyer_order_id_(buyer_order_id),
        seller_order_id_(seller_order_id),
        buyer_trader_id_(buyer_trader_id),
        seller_trader_id_(seller_trader_id),
        price_(price),
        quantity_(quantity),
        executed_at_(executed_at),
        sequence_(sequence),
        aggressor_side_(aggressor_side) {}

  TradeId id_;
  ContractId contract_id_;
  OrderId buyer_order_id_;
  OrderId seller_order_id_;
  TraderId buyer_trader_id_;
  TraderId seller_trader_id_;
  Price price_;
  Quantity quantity_;
  Timestamp executed_at_;
  SequenceNumber sequence_;
  std::optional<Side> aggressor_side_;
};

class Fill {
 public:
  [[nodiscard]] static Fill for_buyer(const Trade& trade);
  [[nodiscard]] static Fill for_seller(const Trade& trade);

  [[nodiscard]] const TradeId& trade_id() const {
    return trade_id_;
  }
  [[nodiscard]] const OrderId& order_id() const {
    return order_id_;
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
  [[nodiscard]] const Price& price() const {
    return price_;
  }
  [[nodiscard]] const Quantity& quantity() const {
    return quantity_;
  }
  [[nodiscard]] const Timestamp& executed_at() const {
    return executed_at_;
  }
  [[nodiscard]] const SequenceNumber& sequence() const {
    return sequence_;
  }

 private:
  Fill(TradeId trade_id, OrderId order_id, TraderId trader_id, ContractId contract_id, Side side,
       Price price, Quantity quantity, Timestamp executed_at, SequenceNumber sequence)
      : trade_id_(trade_id),
        order_id_(order_id),
        trader_id_(trader_id),
        contract_id_(contract_id),
        side_(side),
        price_(price),
        quantity_(quantity),
        executed_at_(executed_at),
        sequence_(sequence) {}

  TradeId trade_id_;
  OrderId order_id_;
  TraderId trader_id_;
  ContractId contract_id_;
  Side side_;
  Price price_;
  Quantity quantity_;
  Timestamp executed_at_;
  SequenceNumber sequence_;
};

}  // namespace pmm::core
