#pragma once

#include <cstdint>
#include <map>
#include <optional>
#include <utility>
#include <vector>

#include "pmm/sim/exchange_simulator.hpp"

namespace pmm::agents {

struct AgentIdTag {};
using AgentId = core::Identifier<AgentIdTag>;

enum class AgentKind {
  Noise,
  Momentum,
  MeanReversion,
  Informed,
  LiquidityTaker,
};

// Each agent owns one execution identity in Phase 5. Account authorization and risk limits
// deliberately remain external to both agents and the exchange.
struct AgentConfig {
  AgentId id;
  core::TraderId trader_id;
  core::ContractId contract_id;
  AgentKind kind;
  core::Timestamp first_decision_at;
  std::int64_t decision_interval_nanoseconds;
  core::Quantity quantity;
  core::Price reference_price;
  std::uint64_t threshold_price_units = 1;
};

struct AgentCheckpoint {
  AgentId id;
  core::Timestamp next_decision_at;
  std::uint64_t decision_ordinal;
  std::uint64_t random_state;
};

struct AgentIntent {
  AgentId agent_id;
  std::uint64_t local_command_sequence;
  sim::SubmitOrderRequest request;
};

struct AgentDecisionRecord {
  AgentId agent_id;
  core::Timestamp decision_time;
  std::uint64_t event_watermark;
  std::vector<AgentIntent> intents;
};

struct MarketDataView {
  std::optional<sim::PriceLevelDelta> best_bid;
  std::optional<sim::PriceLevelDelta> best_ask;
  std::optional<core::Price> last_trade_price;
};

struct MarketDataCheckpoint {
  core::ContractId contract_id;
  std::vector<sim::PriceLevelDelta> levels;
  std::optional<core::Price> last_trade_price;
};

struct SimulationCheckpoint {
  sim::ExchangeCheckpoint exchange;
  std::uint64_t event_watermark;
  std::vector<AgentCheckpoint> agents;
  std::vector<MarketDataCheckpoint> market_data;
};

class SimulationCoordinator final {
 public:
  [[nodiscard]] static core::Result<SimulationCoordinator> create(std::vector<core::Market> markets,
                                                                  std::vector<AgentConfig> agents,
                                                                  std::uint64_t run_seed);
  [[nodiscard]] static core::Result<SimulationCoordinator> restore(SimulationCheckpoint checkpoint,
                                                                   std::vector<AgentConfig> agents,
                                                                   std::uint64_t run_seed);

  SimulationCoordinator(SimulationCoordinator&&) noexcept;
  SimulationCoordinator& operator=(SimulationCoordinator&&) noexcept;
  SimulationCoordinator(const SimulationCoordinator&) = delete;
  SimulationCoordinator& operator=(const SimulationCoordinator&) = delete;
  ~SimulationCoordinator();

  // External/historical input is deliberately separate from agent output. Agents never receive
  // an ExchangeSimulator reference and cannot call this method.
  [[nodiscard]] core::Result<std::uint64_t> enqueue_external(sim::ExchangeCommand command,
                                                             core::Timestamp scheduled_at);
  [[nodiscard]] core::Result<void> run_until(core::Timestamp inclusive_time);

  [[nodiscard]] const sim::ExchangeSimulator& exchange() const;
  [[nodiscard]] const std::vector<AgentDecisionRecord>& decisions() const {
    return decisions_;
  }
  [[nodiscard]] std::uint64_t event_watermark() const {
    return event_watermark_;
  }
  [[nodiscard]] SimulationCheckpoint checkpoint() const;

 private:
  struct AgentRuntime;
  struct Projection;

  explicit SimulationCoordinator(sim::ExchangeSimulator exchange);

  [[nodiscard]] core::Result<void> initialize(std::vector<AgentConfig> agents,
                                              std::uint64_t run_seed);
  [[nodiscard]] core::Result<void> consume_events();
  [[nodiscard]] core::Result<void> run_agents_at(core::Timestamp time);
  [[nodiscard]] std::optional<core::Timestamp> next_agent_time() const;
  [[nodiscard]] static core::Result<void> validate_config(const AgentConfig& config);

  sim::ExchangeSimulator exchange_;
  std::vector<AgentRuntime> agents_;
  std::map<core::ContractId, Projection> projections_;
  std::vector<AgentDecisionRecord> decisions_;
  std::uint64_t event_watermark_ = 0;
};

}  // namespace pmm::agents
