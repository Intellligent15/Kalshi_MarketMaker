#include "pmm/market_maker/market_maker.hpp"

#include <algorithm>
#include <limits>
#include <utility>

namespace pmm::market_maker {
namespace {

core::DomainError Error(core::DomainErrorCode code, const char* message) {
  return core::DomainError{code, message};
}

core::Timestamp add_interval(core::Timestamp time, std::int64_t interval) {
  return core::Timestamp::from_unix_nanoseconds(time.unix_nanoseconds() + interval);
}

}  // namespace

struct MarketMakingCoordinator::Projection {
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
    } else if (const auto* trade = std::get_if<sim::TradeExecuted>(&event.payload)) {
      last_trade_price = trade->execution.trade.price();
    }
  }

  [[nodiscard]] std::optional<sim::PriceLevelDelta> best(core::Side side) const {
    std::optional<sim::PriceLevelDelta> result;
    for (const auto& [key, level] : levels) {
      if (key.first != side ||
          (result.has_value() && !(side == core::Side::Buy ? level.price > result->price
                                                           : level.price < result->price))) {
        continue;
      }
      result = level;
    }
    return result;
  }

  [[nodiscard]] MarketDataCheckpoint checkpoint() const {
    std::vector<sim::PriceLevelDelta> values;
    values.reserve(levels.size());
    for (const auto& [key, level] : levels) {
      static_cast<void>(key);
      values.push_back(level);
    }
    return MarketDataCheckpoint{std::move(values), last_trade_price};
  }
};

MarketMakingCoordinator::MarketMakingCoordinator(sim::ExchangeSimulator exchange,
                                                 core::Contract contract, MarketMakerConfig config,
                                                 risk::AccountRiskProjection risk)
    : exchange_(std::move(exchange)),
      contract_(std::move(contract)),
      config_(std::move(config)),
      risk_(std::move(risk)),
      projection_(std::make_unique<Projection>()),
      next_decision_at_(config_.first_decision_at) {}

MarketMakingCoordinator::MarketMakingCoordinator(MarketMakingCoordinator&&) noexcept = default;
MarketMakingCoordinator& MarketMakingCoordinator::operator=(MarketMakingCoordinator&&) noexcept =
    default;
MarketMakingCoordinator::~MarketMakingCoordinator() = default;

core::Result<MarketMakingCoordinator> MarketMakingCoordinator::create(
    std::vector<core::Market> markets, MarketMakerConfig config) {
  const auto selected = std::find_if(markets.begin(), markets.end(), [&config](const auto& market) {
    return market.contract().id() == config.account.contract_id;
  });
  if (selected == markets.end()) {
    return Error(core::DomainErrorCode::InvalidContract,
                 "market maker contract is not registered with exchange");
  }
  const auto valid = validate_config(selected->contract(), config);
  if (!valid) {
    return valid.error();
  }
  const core::Contract contract = selected->contract();
  auto exchange = sim::ExchangeSimulator::create(std::move(markets));
  if (!exchange) {
    return exchange.error();
  }
  auto risk = risk::AccountRiskProjection::create(config.account, config.risk_limits);
  if (!risk) {
    return risk.error();
  }
  return MarketMakingCoordinator(std::move(exchange).value(), contract, std::move(config),
                                 std::move(risk).value());
}

core::Result<MarketMakingCoordinator> MarketMakingCoordinator::restore(
    MarketMakerCheckpoint checkpoint, MarketMakerConfig config) {
  const auto selected =
      std::find_if(checkpoint.exchange.markets.begin(), checkpoint.exchange.markets.end(),
                   [&config](const auto& market) {
                     return market.market.contract().id() == config.account.contract_id;
                   });
  if (selected == checkpoint.exchange.markets.end()) {
    return Error(core::DomainErrorCode::InvalidContract,
                 "market maker checkpoint has no configured contract");
  }
  const auto valid = validate_config(selected->market.contract(), config);
  if (!valid) {
    return valid.error();
  }
  const core::Contract contract = selected->market.contract();
  auto exchange = sim::ExchangeSimulator::restore(std::move(checkpoint.exchange));
  if (!exchange) {
    return exchange.error();
  }
  auto risk = risk::AccountRiskProjection::restore(config.account, config.risk_limits,
                                                   std::move(checkpoint.risk));
  if (!risk) {
    return risk.error();
  }
  MarketMakingCoordinator restored(std::move(exchange).value(), contract, std::move(config),
                                   std::move(risk).value());
  restored.event_watermark_ = checkpoint.event_watermark;
  restored.next_decision_at_ = checkpoint.next_decision_at;
  restored.next_client_intent_value_ = checkpoint.next_client_intent_value;
  restored.projection_->last_trade_price = checkpoint.market_data.last_trade_price;
  for (const sim::PriceLevelDelta& level : checkpoint.market_data.levels) {
    restored.projection_->levels.emplace(std::make_pair(level.side, level.price.units()), level);
  }
  return restored;
}

core::Result<std::uint64_t> MarketMakingCoordinator::enqueue_external(
    sim::ExchangeCommand command, core::Timestamp scheduled_at) {
  return exchange_.enqueue(std::move(command), scheduled_at);
}

core::Result<void> MarketMakingCoordinator::run_until(core::Timestamp inclusive_time) {
  while (next_decision_at_ <= inclusive_time) {
    const auto processed = exchange_.run_until(next_decision_at_);
    if (!processed) {
      return processed.error();
    }
    const auto consumed = consume_events();
    if (!consumed) {
      return consumed.error();
    }
    const auto decision = run_decision(next_decision_at_);
    if (!decision) {
      return decision.error();
    }
    if (next_decision_at_.unix_nanoseconds() >
        std::numeric_limits<std::int64_t>::max() - config_.decision_interval_nanoseconds) {
      return Error(core::DomainErrorCode::InvalidOrder, "market maker decision time overflow");
    }
    next_decision_at_ = add_interval(next_decision_at_, config_.decision_interval_nanoseconds);
  }
  const auto processed = exchange_.run_until(inclusive_time);
  if (!processed) {
    return processed.error();
  }
  return consume_events();
}

void MarketMakingCoordinator::activate_kill_switch() {
  risk_.activate_kill_switch();
}

MarketMakerCheckpoint MarketMakingCoordinator::checkpoint() const {
  return MarketMakerCheckpoint{exchange_.checkpoint(),    risk_.checkpoint(),
                               event_watermark_,          next_decision_at_,
                               next_client_intent_value_, projection_->checkpoint()};
}

core::Result<void> MarketMakingCoordinator::validate_config(const core::Contract& contract,
                                                            const MarketMakerConfig& config) {
  if (config.account.contract_id != contract.id() || config.decision_interval_nanoseconds <= 0 ||
      config.quote_quantity.is_zero() ||
      (config.bid_offset_ticks == 0 && config.ask_offset_ticks == 0) ||
      config.maximum_quote_age_nanoseconds <= 0) {
    return Error(core::DomainErrorCode::InvalidOrder, "invalid market maker configuration");
  }
  const auto reference = contract.validate_price(config.configured_reference_price);
  if (!reference) {
    return reference.error();
  }
  const auto quantity = contract.validate_quantity(config.quote_quantity);
  if (!quantity) {
    return quantity.error();
  }
  return {};
}

core::Result<void> MarketMakingCoordinator::consume_events() {
  const auto events =
      exchange_.read_events_after(event_watermark_, std::numeric_limits<std::size_t>::max());
  for (const sim::ExchangeEvent& event : events) {
    if (const auto* depth = std::get_if<sim::BookDepthChanged>(&event.payload)) {
      if (depth->contract_id == contract_.id()) {
        projection_->apply(event);
      }
    } else if (const auto* trade = std::get_if<sim::TradeExecuted>(&event.payload)) {
      if (trade->execution.trade.contract_id() == contract_.id()) {
        projection_->apply(event);
      }
    }
    const auto risk_applied = risk_.apply(event);
    if (!risk_applied) {
      return risk_applied.error();
    }
    event_watermark_ = event.sequence.value();
  }
  return {};
}

core::Result<void> MarketMakingCoordinator::run_decision(core::Timestamp time) {
  auto [bid, ask] = desired_quotes();
  if (risk_.view().kill_switch_active) {
    bid.reset();
    ask.reset();
  }
  QuoteDecisionRecord record{time, event_watermark_, risk_.view(), bid, ask, {}, {}};
  const auto matches_quote = [this](const risk::LiveRiskOrder& order,
                                    const std::optional<core::Price>& desired) {
    return desired.has_value() && order.price == *desired &&
           order.remaining_quantity == config_.quote_quantity;
  };
  bool has_matching_bid = false;
  bool has_matching_ask = false;
  for (const auto& [order_id, order] : risk_.live_orders()) {
    const bool matches =
        order.side == core::Side::Buy ? matches_quote(order, bid) : matches_quote(order, ask);
    const bool stale =
        time >= order.acknowledged_at &&
        static_cast<std::uint64_t>(time.unix_nanoseconds()) -
                static_cast<std::uint64_t>(order.acknowledged_at.unix_nanoseconds()) >=
            static_cast<std::uint64_t>(config_.maximum_quote_age_nanoseconds);
    if (matches && !stale) {
      has_matching_bid = has_matching_bid || order.side == core::Side::Buy;
      has_matching_ask = has_matching_ask || order.side == core::Side::Sell;
      continue;
    }
    const auto cancelled = exchange_.enqueue(
        sim::CancelOrderRequest{config_.account.trader_id, config_.account.contract_id, order_id},
        time);
    if (!cancelled) {
      return cancelled.error();
    }
    record.cancellations.push_back(order_id);
  }

  const auto admit_side = [this, &record, time](core::Side side,
                                                const std::optional<core::Price>& price,
                                                bool has_matching) -> core::Result<void> {
    const risk::AccountRiskView view = risk_.view();
    const core::Quantity pending =
        side == core::Side::Buy ? view.pending_buy_quantity : view.pending_sell_quantity;
    if (!price.has_value() || has_matching || !pending.is_zero()) {
      return {};
    }
    const auto client_intent_id = next_client_intent_id();
    if (!client_intent_id) {
      return client_intent_id.error();
    }
    const risk::OrderIntent intent{client_intent_id.value(),
                                   config_.account.contract_id,
                                   side,
                                   config_.quote_quantity,
                                   *price,
                                   true};
    risk::AdmissionDecision admission = risk_.admit(intent, time);
    if (admission.approved()) {
      const auto ingress = exchange_.enqueue(*admission.command, time);
      if (!ingress) {
        return ingress.error();
      }
      const auto bound = risk_.bind_ingress(admission.client_intent_id, ingress.value());
      if (!bound) {
        return bound.error();
      }
    }
    record.admissions.push_back(std::move(admission));
    return {};
  };
  const auto bid_admission = admit_side(core::Side::Buy, bid, has_matching_bid);
  if (!bid_admission) {
    return bid_admission.error();
  }
  const auto ask_admission = admit_side(core::Side::Sell, ask, has_matching_ask);
  if (!ask_admission) {
    return ask_admission.error();
  }
  decisions_.push_back(std::move(record));
  return {};
}

std::pair<std::optional<core::Price>, std::optional<core::Price>>
MarketMakingCoordinator::desired_quotes() const {
  const std::optional<core::Price> reference = reference_price();
  if (!reference.has_value()) {
    return {};
  }
  const core::PriceGrid& grid = contract_.price_grid();
  const std::uint64_t increment = grid.increment().units();
  const std::uint64_t maximum_tick = (grid.maximum().units() - grid.minimum().units()) / increment;
  std::uint64_t center_tick = (reference->units() - grid.minimum().units()) / increment;
  const std::int64_t position = risk_.view().net_position;
  const std::uint64_t magnitude =
      position < 0 ? static_cast<std::uint64_t>(-position) : static_cast<std::uint64_t>(position);
  const std::uint64_t position_limit = config_.risk_limits.maximum_absolute_position.units();
  std::uint64_t skew = 0;
  if (magnitude == position_limit) {
    skew = config_.maximum_inventory_skew_ticks;
  } else if (magnitude != 0 && config_.maximum_inventory_skew_ticks <=
                                   std::numeric_limits<std::uint64_t>::max() / magnitude) {
    skew = (magnitude * config_.maximum_inventory_skew_ticks) / position_limit;
  } else if (magnitude != 0) {
    skew = config_.maximum_inventory_skew_ticks;
  }
  if (position > 0) {
    center_tick = skew > center_tick ? 0 : center_tick - skew;
  } else if (position < 0) {
    center_tick = std::min(maximum_tick, center_tick + std::min(skew, maximum_tick - center_tick));
  }
  std::uint64_t bid_tick =
      config_.bid_offset_ticks > center_tick ? 0 : center_tick - config_.bid_offset_ticks;
  std::uint64_t ask_tick = std::min(
      maximum_tick, center_tick + std::min(config_.ask_offset_ticks, maximum_tick - center_tick));
  const std::optional<sim::PriceLevelDelta> best_bid = projection_->best(core::Side::Buy);
  const std::optional<sim::PriceLevelDelta> best_ask = projection_->best(core::Side::Sell);
  if (best_ask.has_value()) {
    const std::uint64_t ask_tick_limit =
        (best_ask->price.units() - grid.minimum().units()) / increment;
    if (bid_tick >= ask_tick_limit) {
      if (ask_tick_limit == 0) {
        return {};
      }
      bid_tick = ask_tick_limit - 1;
    }
  }
  if (best_bid.has_value()) {
    const std::uint64_t bid_tick_limit =
        (best_bid->price.units() - grid.minimum().units()) / increment;
    if (ask_tick <= bid_tick_limit) {
      if (bid_tick_limit == maximum_tick) {
        return {};
      }
      ask_tick = bid_tick_limit + 1;
    }
  }
  if (bid_tick >= ask_tick) {
    return {};
  }
  const auto price_at = [&grid, increment](std::uint64_t tick) {
    return core::Price::from_units(
        static_cast<std::int64_t>(grid.minimum().units() + tick * increment));
  };
  const auto bid = price_at(bid_tick);
  const auto ask = price_at(ask_tick);
  if (!bid || !ask) {
    return {};
  }
  return {bid.value(), ask.value()};
}

std::optional<core::Price> MarketMakingCoordinator::reference_price() const {
  if (config_.reference_price_source == ReferencePriceSource::Configured) {
    return config_.configured_reference_price;
  }
  if (config_.reference_price_source == ReferencePriceSource::LastTrade) {
    return projection_->last_trade_price;
  }
  const auto bid = projection_->best(core::Side::Buy);
  const auto ask = projection_->best(core::Side::Sell);
  if (!bid.has_value() || !ask.has_value()) {
    return std::nullopt;
  }
  return core::Price::from_units(
             static_cast<std::int64_t>(bid->price.units() +
                                       (ask->price.units() - bid->price.units()) / 2U))
      .value();
}

core::Result<risk::ClientIntentId> MarketMakingCoordinator::next_client_intent_id() {
  if (next_client_intent_value_ == std::numeric_limits<std::uint64_t>::max()) {
    return Error(core::DomainErrorCode::IdentifierExhausted,
                 "market maker client intent identifiers are exhausted");
  }
  const auto identifier = risk::ClientIntentId::from_value(next_client_intent_value_);
  if (!identifier) {
    return identifier.error();
  }
  ++next_client_intent_value_;
  return identifier.value();
}

}  // namespace pmm::market_maker
