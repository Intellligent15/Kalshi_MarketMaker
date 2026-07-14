#pragma once

#include <string>
#include <utility>
#include <vector>

#include "pmm/core/identifiers.hpp"
#include "pmm/core/primitives.hpp"

namespace pmm::core {

enum class ContractKind {
  Binary,
};

enum class MarketStatus {
  Open,
  Halted,
  Closed,
  Settled,
};

class Contract {
 public:
  [[nodiscard]] static Result<Contract> create(ContractId id, MarketId market_id, Price payout,
                                               PriceGrid price_grid, LotSize lot_size);

  [[nodiscard]] const ContractId& id() const {
    return id_;
  }
  [[nodiscard]] const MarketId& market_id() const {
    return market_id_;
  }
  [[nodiscard]] ContractKind kind() const {
    return ContractKind::Binary;
  }
  [[nodiscard]] const Price& payout() const {
    return payout_;
  }
  [[nodiscard]] const PriceGrid& price_grid() const {
    return price_grid_;
  }
  [[nodiscard]] const LotSize& lot_size() const {
    return lot_size_;
  }

  [[nodiscard]] Result<void> validate_price(Price price) const;
  [[nodiscard]] Result<void> validate_quantity(Quantity quantity) const;

 private:
  Contract(ContractId id, MarketId market_id, Price payout, PriceGrid price_grid, LotSize lot_size)
      : id_(id),
        market_id_(market_id),
        payout_(payout),
        price_grid_(price_grid),
        lot_size_(lot_size) {}

  ContractId id_;
  MarketId market_id_;
  Price payout_;
  PriceGrid price_grid_;
  LotSize lot_size_;
};

class Market {
 public:
  [[nodiscard]] static Result<Market> create(MarketId id, std::string title, Contract contract,
                                             MarketStatus status = MarketStatus::Open);

  [[nodiscard]] const MarketId& id() const {
    return id_;
  }
  [[nodiscard]] const std::string& title() const {
    return title_;
  }
  [[nodiscard]] MarketStatus status() const {
    return status_;
  }
  [[nodiscard]] const Contract& contract() const {
    return contract_;
  }

 private:
  Market(MarketId id, std::string title, Contract contract, MarketStatus status)
      : id_(id), title_(std::move(title)), contract_(std::move(contract)), status_(status) {}

  MarketId id_;
  std::string title_;
  Contract contract_;
  MarketStatus status_;
};

}  // namespace pmm::core
