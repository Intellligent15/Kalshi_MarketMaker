#include "pmm/agents/baseline_agents.hpp"

#include <algorithm>
#include <limits>
#include <map>
#include <utility>

namespace pmm::agents {
namespace {

core::DomainError AgentError(core::DomainErrorCode code, const char* message) {
  return core::DomainError{code, message};
}

std::uint64_t mix_seed(std::uint64_t value) {
  value += 0x9e3779b97f4a7c15ULL;
  value = (value ^ (value >> 30U)) * 0xbf58476d1ce4e5b9ULL;
  value = (value ^ (value >> 27U)) * 0x94d049bb133111ebULL;
  return value ^ (value >> 31U);
}

std::uint64_t next_random(std::uint64_t& state) {
  state += 0x9e3779b97f4a7c15ULL;
  return mix_seed(state);
}

core::Timestamp add_interval(core::Timestamp time, std::int64_t interval) {
  return core::Timestamp::from_unix_nanoseconds(time.unix_nanoseconds() + interval);
}

}  // namespace

struct SimulationCoordinator::Projection {
  std::map<std::pair<core::Side, std::uint64_t>, sim::PriceLevelDelta> levels;
  std::optional<core::Price> last_trade_price;

  void apply(const sim::ExchangeEvent& event) {
    if (const auto* depth = std::get_if<sim::BookDepthChanged>(&event.payload)) {
      for (const sim::PriceLevelDelta& level : depth->levels) {
        const auto key = std::make_pair(level.side, level.price.units());
        if (level.total_quantity.is_zero()) {
          levels.erase(key);
        } else {
          levels.insert_or_assign(key, level);
        }
      }
      return;
    }
    if (const auto* trade = std::get_if<sim::TradeExecuted>(&event.payload)) {
      last_trade_price = trade->execution.trade.price();
    }
  }

  [[nodiscard]] MarketDataView view() const {
    MarketDataView result;
    for (const auto& [key, level] : levels) {
      if (key.first == core::Side::Buy &&
          (!result.best_bid.has_value() || level.price > result.best_bid->price)) {
        result.best_bid = level;
      }
      if (key.first == core::Side::Sell &&
          (!result.best_ask.has_value() || level.price < result.best_ask->price)) {
        result.best_ask = level;
      }
    }
    result.last_trade_price = last_trade_price;
    return result;
  }

  [[nodiscard]] MarketDataCheckpoint checkpoint(core::ContractId contract_id) const {
    std::vector<sim::PriceLevelDelta> values;
    values.reserve(levels.size());
    for (const auto& [key, level] : levels) {
      static_cast<void>(key);
      values.push_back(level);
    }
    return MarketDataCheckpoint{contract_id, std::move(values), last_trade_price};
  }
};

struct SimulationCoordinator::AgentRuntime {
  AgentConfig config;
  core::Timestamp next_decision_at;
  std::uint64_t decision_ordinal = 0;
  std::uint64_t random_state = 0;

  [[nodiscard]] AgentCheckpoint checkpoint() const {
    return AgentCheckpoint{config.id, next_decision_at, decision_ordinal, random_state};
  }

  [[nodiscard]] std::optional<AgentIntent> decide(core::Timestamp time,
                                                  const MarketDataView& market,
                                                  std::uint64_t event_watermark) {
    static_cast<void>(event_watermark);
    std::optional<core::Side> side;
    switch (config.kind) {
      case AgentKind::Noise:
        side = next_random(random_state) % 2U == 0U ? core::Side::Buy : core::Side::Sell;
        break;
      case AgentKind::Momentum:
        if (!market.last_trade_price.has_value()) {
          break;
        }
        if (market.last_trade_price->units() >=
            config.reference_price.units() + config.threshold_price_units) {
          side = core::Side::Buy;
        } else if (market.last_trade_price->units() + config.threshold_price_units <=
                   config.reference_price.units()) {
          side = core::Side::Sell;
        }
        break;
      case AgentKind::MeanReversion:
        if (!market.best_bid.has_value() || !market.best_ask.has_value()) {
          break;
        }
        if (market.best_ask->price.units() >=
            config.reference_price.units() + config.threshold_price_units) {
          side = core::Side::Sell;
        } else if (market.best_bid->price.units() + config.threshold_price_units <=
                   config.reference_price.units()) {
          side = core::Side::Buy;
        }
        break;
      case AgentKind::Informed:
        if (market.best_ask.has_value() && market.best_ask->price < config.reference_price) {
          side = core::Side::Buy;
        } else if (market.best_bid.has_value() && market.best_bid->price > config.reference_price) {
          side = core::Side::Sell;
        }
        break;
      case AgentKind::LiquidityTaker:
        if (!market.best_bid.has_value() || !market.best_ask.has_value()) {
          break;
        }
        if (market.best_ask->price.units() - market.best_bid->price.units() <=
            config.threshold_price_units) {
          side = next_random(random_state) % 2U == 0U ? core::Side::Buy : core::Side::Sell;
        }
        break;
    }

    ++decision_ordinal;
    if (!side.has_value()) {
      return std::nullopt;
    }
    return AgentIntent{
        config.id, decision_ordinal,
        sim::SubmitOrderRequest{config.trader_id, config.contract_id, *side,
                                core::OrderType::Market, config.quantity, std::nullopt, time}};
  }
};

SimulationCoordinator::SimulationCoordinator(sim::ExchangeSimulator exchange)
    : exchange_(std::move(exchange)) {}

SimulationCoordinator::SimulationCoordinator(SimulationCoordinator&&) noexcept = default;
SimulationCoordinator& SimulationCoordinator::operator=(SimulationCoordinator&&) noexcept = default;
SimulationCoordinator::~SimulationCoordinator() = default;

core::Result<SimulationCoordinator> SimulationCoordinator::create(std::vector<core::Market> markets,
                                                                  std::vector<AgentConfig> agents,
                                                                  std::uint64_t run_seed) {
  auto exchange = sim::ExchangeSimulator::create(std::move(markets));
  if (!exchange) {
    return exchange.error();
  }
  SimulationCoordinator coordinator(std::move(exchange).value());
  const auto initialized = coordinator.initialize(std::move(agents), run_seed);
  if (!initialized) {
    return initialized.error();
  }
  return std::move(coordinator);
}

core::Result<SimulationCoordinator> SimulationCoordinator::restore(SimulationCheckpoint checkpoint,
                                                                   std::vector<AgentConfig> agents,
                                                                   std::uint64_t run_seed) {
  auto exchange = sim::ExchangeSimulator::restore(std::move(checkpoint.exchange));
  if (!exchange) {
    return exchange.error();
  }
  SimulationCoordinator coordinator(std::move(exchange).value());
  const auto initialized = coordinator.initialize(std::move(agents), run_seed);
  if (!initialized) {
    return initialized.error();
  }
  if (checkpoint.agents.size() != coordinator.agents_.size()) {
    return AgentError(core::DomainErrorCode::InvalidOrder,
                      "agent checkpoint does not match configured agents");
  }
  for (const AgentCheckpoint& saved : checkpoint.agents) {
    const auto runtime =
        std::find_if(coordinator.agents_.begin(), coordinator.agents_.end(),
                     [&saved](const AgentRuntime& agent) { return agent.config.id == saved.id; });
    if (runtime == coordinator.agents_.end()) {
      return AgentError(core::DomainErrorCode::InvalidOrder,
                        "agent checkpoint contains an unknown agent");
    }
    runtime->next_decision_at = saved.next_decision_at;
    runtime->decision_ordinal = saved.decision_ordinal;
    runtime->random_state = saved.random_state;
  }
  coordinator.event_watermark_ = checkpoint.event_watermark;
  for (const MarketDataCheckpoint& saved : checkpoint.market_data) {
    Projection projection;
    projection.last_trade_price = saved.last_trade_price;
    for (const sim::PriceLevelDelta& level : saved.levels) {
      projection.levels.emplace(std::make_pair(level.side, level.price.units()), level);
    }
    coordinator.projections_.insert_or_assign(saved.contract_id, std::move(projection));
  }
  return std::move(coordinator);
}

core::Result<void> SimulationCoordinator::initialize(std::vector<AgentConfig> agents,
                                                     std::uint64_t run_seed) {
  std::sort(agents.begin(), agents.end(),
            [](const AgentConfig& left, const AgentConfig& right) { return left.id < right.id; });
  for (const AgentConfig& config : agents) {
    const auto valid = validate_config(config);
    if (!valid) {
      return valid.error();
    }
    if (!agents_.empty() && agents_.back().config.id == config.id) {
      return AgentError(core::DomainErrorCode::InvalidIdentifier, "duplicate agent identifier");
    }
    const auto snapshot =
        exchange_.snapshot(config.contract_id, std::numeric_limits<std::size_t>::max());
    if (!snapshot) {
      return snapshot.error();
    }
    Projection& projection = projections_[config.contract_id];
    for (const book::PriceLevelView& level : snapshot.value().bids) {
      projection.levels.insert_or_assign(
          std::make_pair(core::Side::Buy, level.price.units()),
          sim::PriceLevelDelta{core::Side::Buy, level.price, level.total_quantity,
                               level.order_count});
    }
    for (const book::PriceLevelView& level : snapshot.value().asks) {
      projection.levels.insert_or_assign(
          std::make_pair(core::Side::Sell, level.price.units()),
          sim::PriceLevelDelta{core::Side::Sell, level.price, level.total_quantity,
                               level.order_count});
    }
    agents_.push_back(
        AgentRuntime{config, config.first_decision_at, 0, mix_seed(run_seed ^ config.id.value())});
  }
  return {};
}

core::Result<std::uint64_t> SimulationCoordinator::enqueue_external(sim::ExchangeCommand command,
                                                                    core::Timestamp scheduled_at) {
  return exchange_.enqueue(std::move(command), scheduled_at);
}

core::Result<void> SimulationCoordinator::run_until(core::Timestamp inclusive_time) {
  while (const std::optional<core::Timestamp> due = next_agent_time()) {
    if (*due > inclusive_time) {
      break;
    }
    const auto external = exchange_.run_until(*due);
    if (!external) {
      return external.error();
    }
    const auto consumed = consume_events();
    if (!consumed) {
      return consumed.error();
    }
    const auto agents = run_agents_at(*due);
    if (!agents) {
      return agents.error();
    }
  }
  const auto external = exchange_.run_until(inclusive_time);
  if (!external) {
    return external.error();
  }
  return consume_events();
}

core::Result<void> SimulationCoordinator::consume_events() {
  const std::vector<sim::ExchangeEvent> events =
      exchange_.read_events_after(event_watermark_, std::numeric_limits<std::size_t>::max());
  for (const sim::ExchangeEvent& event : events) {
    if (const auto* depth = std::get_if<sim::BookDepthChanged>(&event.payload)) {
      projections_[depth->contract_id].apply(event);
    } else if (const auto* trade = std::get_if<sim::TradeExecuted>(&event.payload)) {
      projections_[trade->execution.trade.contract_id()].apply(event);
    }
    event_watermark_ = event.sequence.value();
  }
  return {};
}

core::Result<void> SimulationCoordinator::run_agents_at(core::Timestamp time) {
  std::vector<AgentIntent> intents;
  for (AgentRuntime& agent : agents_) {
    if (agent.next_decision_at != time) {
      continue;
    }
    const auto projection = projections_.find(agent.config.contract_id);
    if (projection == projections_.end()) {
      return AgentError(core::DomainErrorCode::InvalidContract,
                        "agent contract has no market-data projection");
    }
    AgentDecisionRecord record{agent.config.id, time, event_watermark_, {}};
    const std::optional<AgentIntent> intent =
        agent.decide(time, projection->second.view(), event_watermark_);
    if (intent.has_value()) {
      record.intents.push_back(*intent);
      intents.push_back(*intent);
    }
    decisions_.push_back(std::move(record));
    agent.next_decision_at = add_interval(time, agent.config.decision_interval_nanoseconds);
  }
  std::sort(intents.begin(), intents.end(), [](const AgentIntent& left, const AgentIntent& right) {
    if (left.agent_id != right.agent_id) {
      return left.agent_id < right.agent_id;
    }
    return left.local_command_sequence < right.local_command_sequence;
  });
  for (const AgentIntent& intent : intents) {
    const auto queued = exchange_.enqueue(intent.request, time);
    if (!queued) {
      return queued.error();
    }
  }
  const auto processed = exchange_.run_until(time);
  if (!processed) {
    return processed.error();
  }
  return {};
}

std::optional<core::Timestamp> SimulationCoordinator::next_agent_time() const {
  std::optional<core::Timestamp> result;
  for (const AgentRuntime& agent : agents_) {
    if (!result.has_value() || agent.next_decision_at < *result) {
      result = agent.next_decision_at;
    }
  }
  return result;
}

const sim::ExchangeSimulator& SimulationCoordinator::exchange() const {
  return exchange_;
}

SimulationCheckpoint SimulationCoordinator::checkpoint() const {
  std::vector<AgentCheckpoint> agents;
  agents.reserve(agents_.size());
  for (const AgentRuntime& agent : agents_) {
    agents.push_back(agent.checkpoint());
  }
  std::vector<MarketDataCheckpoint> market_data;
  market_data.reserve(projections_.size());
  for (const auto& [contract_id, projection] : projections_) {
    market_data.push_back(projection.checkpoint(contract_id));
  }
  return SimulationCheckpoint{exchange_.checkpoint(), event_watermark_, std::move(agents),
                              std::move(market_data)};
}

core::Result<void> SimulationCoordinator::validate_config(const AgentConfig& config) {
  if (config.decision_interval_nanoseconds <= 0) {
    return AgentError(core::DomainErrorCode::InvalidOrder,
                      "agent decision interval must be positive logical time");
  }
  if (config.threshold_price_units == 0) {
    return AgentError(core::DomainErrorCode::InvalidPrice,
                      "agent threshold must be positive integer price units");
  }
  return {};
}

}  // namespace pmm::agents
