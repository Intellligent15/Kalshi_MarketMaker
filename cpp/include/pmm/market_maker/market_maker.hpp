#pragma once

#include <cstdint>
#include <limits>
#include <map>
#include <memory>
#include <optional>
#include <vector>

#include "pmm/risk/account_risk.hpp"

namespace pmm::market_maker {

enum class ReferencePriceSource {
  Configured,
  LastTrade,
  Midpoint,
};

struct MarketMakerConfig {
  risk::AccountBinding account;
  risk::RiskLimits risk_limits;
  core::Timestamp first_decision_at;
  std::int64_t decision_interval_nanoseconds;
  core::Quantity quote_quantity;
  core::Price configured_reference_price;
  ReferencePriceSource reference_price_source = ReferencePriceSource::Configured;
  std::uint64_t bid_offset_ticks = 1;
  std::uint64_t ask_offset_ticks = 1;
  std::uint64_t maximum_inventory_skew_ticks = 0;
  // Logical age; a stale quote is cancelled before any replacement is admitted.
  std::int64_t maximum_quote_age_nanoseconds = std::numeric_limits<std::int64_t>::max();
};

struct QuoteDecisionRecord {
  core::Timestamp decision_time;
  std::uint64_t event_watermark;
  risk::AccountRiskView risk_view;
  std::optional<core::Price> bid_price;
  std::optional<core::Price> ask_price;
  std::vector<risk::AdmissionDecision> admissions;
  std::vector<core::OrderId> cancellations;
};

struct MarketDataCheckpoint {
  std::vector<sim::PriceLevelDelta> levels;
  std::optional<core::Price> last_trade_price;
};

struct MarketMakerCheckpoint {
  sim::ExchangeCheckpoint exchange;
  risk::RiskCheckpoint risk;
  std::uint64_t event_watermark;
  core::Timestamp next_decision_at;
  std::uint64_t next_client_intent_value;
  MarketDataCheckpoint market_data;
};

// A deterministic, passive-only market-making runtime. It owns scheduling and command flow;
// the exchange owns matching, and AccountRiskProjection owns inventory/exposure.
class MarketMakingCoordinator final {
 public:
  [[nodiscard]] static core::Result<MarketMakingCoordinator> create(
      std::vector<core::Market> markets, MarketMakerConfig config);
  [[nodiscard]] static core::Result<MarketMakingCoordinator> restore(
      MarketMakerCheckpoint checkpoint, MarketMakerConfig config);

  MarketMakingCoordinator(MarketMakingCoordinator&&) noexcept;
  MarketMakingCoordinator& operator=(MarketMakingCoordinator&&) noexcept;
  MarketMakingCoordinator(const MarketMakingCoordinator&) = delete;
  MarketMakingCoordinator& operator=(const MarketMakingCoordinator&) = delete;
  ~MarketMakingCoordinator();

  [[nodiscard]] core::Result<std::uint64_t> enqueue_external(sim::ExchangeCommand command,
                                                             core::Timestamp scheduled_at);
  [[nodiscard]] core::Result<void> run_until(core::Timestamp inclusive_time);
  void activate_kill_switch();

  [[nodiscard]] const sim::ExchangeSimulator& exchange() const {
    return exchange_;
  }
  [[nodiscard]] const risk::AccountRiskProjection& risk() const {
    return risk_;
  }
  [[nodiscard]] const std::vector<QuoteDecisionRecord>& decisions() const {
    return decisions_;
  }
  [[nodiscard]] MarketMakerCheckpoint checkpoint() const;

 private:
  struct Projection;

  MarketMakingCoordinator(sim::ExchangeSimulator exchange, core::Contract contract,
                          MarketMakerConfig config, risk::AccountRiskProjection risk);

  [[nodiscard]] static core::Result<void> validate_config(const core::Contract& contract,
                                                          const MarketMakerConfig& config);
  [[nodiscard]] core::Result<void> consume_events();
  [[nodiscard]] core::Result<void> run_decision(core::Timestamp time);
  [[nodiscard]] std::pair<std::optional<core::Price>, std::optional<core::Price>> desired_quotes()
      const;
  [[nodiscard]] std::optional<core::Price> reference_price() const;
  [[nodiscard]] core::Result<risk::ClientIntentId> next_client_intent_id();

  sim::ExchangeSimulator exchange_;
  core::Contract contract_;
  MarketMakerConfig config_;
  risk::AccountRiskProjection risk_;
  std::unique_ptr<Projection> projection_;
  std::uint64_t event_watermark_ = 0;
  core::Timestamp next_decision_at_ = core::Timestamp::from_unix_nanoseconds(0);
  std::uint64_t next_client_intent_value_ = 1;
  std::vector<QuoteDecisionRecord> decisions_;
};

}  // namespace pmm::market_maker
