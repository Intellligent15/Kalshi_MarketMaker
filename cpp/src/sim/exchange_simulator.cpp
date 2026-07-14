#include "pmm/sim/exchange_simulator.hpp"

#include <algorithm>
#include <limits>
#include <map>
#include <type_traits>
#include <utility>

#include "durable_store.hpp"

namespace pmm::sim {

namespace {

core::DomainError SimulatorError(core::DomainErrorCode code, const char* message) {
  return core::DomainError{code, message};
}

bool command_less(const ScheduledCommand& left, const ScheduledCommand& right) {
  if (left.scheduled_at != right.scheduled_at) {
    return left.scheduled_at < right.scheduled_at;
  }
  return left.ingress_sequence < right.ingress_sequence;
}

}  // namespace

class ExchangeSimulator::ExchangeSequencer final : public book::ExecutionIdSource {
 public:
  [[nodiscard]] core::Result<void> ensure_event_capacity(std::size_t count) const {
    if (count > std::numeric_limits<std::uint64_t>::max()) {
      return SimulatorError(core::DomainErrorCode::IdentifierExhausted,
                            "exchange event sequence source is exhausted");
    }
    const std::uint64_t requested = static_cast<std::uint64_t>(count);
    if (requested > std::numeric_limits<std::uint64_t>::max() - next_event_sequence_) {
      return SimulatorError(core::DomainErrorCode::IdentifierExhausted,
                            "exchange event sequence source is exhausted");
    }
    return {};
  }

  [[nodiscard]] core::Result<std::vector<book::ExecutionIdentifiers>> reserve(
      std::size_t execution_count) override {
    if (execution_count == 0) {
      return std::vector<book::ExecutionIdentifiers>{};
    }
    if (execution_count > std::numeric_limits<std::uint64_t>::max()) {
      return SimulatorError(core::DomainErrorCode::IdentifierExhausted,
                            "exchange execution identifier source is exhausted");
    }
    const std::uint64_t count = static_cast<std::uint64_t>(execution_count);
    if (count > std::numeric_limits<std::uint64_t>::max() - next_trade_id_ ||
        count > std::numeric_limits<std::uint64_t>::max() - next_event_sequence_) {
      return SimulatorError(core::DomainErrorCode::IdentifierExhausted,
                            "exchange execution identifier source is exhausted");
    }

    std::vector<book::ExecutionIdentifiers> identifiers;
    identifiers.reserve(execution_count);
    for (std::uint64_t offset = 0; offset < count; ++offset) {
      const auto trade_id = core::TradeId::from_value(next_trade_id_ + offset);
      const auto sequence = core::SequenceNumber::from_value(next_event_sequence_ + offset);
      if (!trade_id || !sequence) {
        return SimulatorError(
            core::DomainErrorCode::IdentifierExhausted,
            "exchange execution identifier source generated an invalid identifier");
      }
      identifiers.push_back(book::ExecutionIdentifiers{trade_id.value(), sequence.value()});
    }
    next_trade_id_ += count;
    next_event_sequence_ += count;
    return identifiers;
  }

  [[nodiscard]] core::Result<core::SequenceNumber> reserve_event_sequence() {
    if (next_event_sequence_ == std::numeric_limits<std::uint64_t>::max()) {
      return SimulatorError(core::DomainErrorCode::IdentifierExhausted,
                            "exchange event sequence source is exhausted");
    }
    const auto sequence = core::SequenceNumber::from_value(next_event_sequence_);
    if (!sequence) {
      return sequence.error();
    }
    ++next_event_sequence_;
    return sequence.value();
  }

  [[nodiscard]] std::uint64_t next_trade_id() const {
    return next_trade_id_;
  }
  [[nodiscard]] std::uint64_t next_event_sequence() const {
    return next_event_sequence_;
  }
  void restore(std::uint64_t next_trade_id, std::uint64_t next_event_sequence) {
    next_trade_id_ = next_trade_id;
    next_event_sequence_ = next_event_sequence;
  }

 private:
  std::uint64_t next_trade_id_ = 1;
  std::uint64_t next_event_sequence_ = 1;
};

ExchangeSimulator::ExchangeSimulator(ExchangeSimulator&&) noexcept = default;
ExchangeSimulator& ExchangeSimulator::operator=(ExchangeSimulator&&) noexcept = default;
ExchangeSimulator::~ExchangeSimulator() = default;

core::Result<ExchangeSimulator> ExchangeSimulator::create(std::vector<core::Market> markets) {
  ExchangeSimulator simulator;
  simulator.sequencer_ = std::make_unique<ExchangeSequencer>();
  for (core::Market& market : markets) {
    const core::ContractId contract_id = market.contract().id();
    if (simulator.markets_.contains(market.id()) ||
        simulator.contract_to_market_.contains(contract_id)) {
      return SimulatorError(core::DomainErrorCode::InvalidMarket,
                            "exchange contains duplicate market or contract identifiers");
    }

    auto book = book::LimitOrderBook::create(market.contract(), *simulator.sequencer_);
    if (!book) {
      return book.error();
    }
    const core::MarketId market_id = market.id();
    simulator.contract_to_market_.emplace(contract_id, market_id);
    simulator.markets_.emplace(
        market_id, MarketRuntime{std::move(market), market.status(),
                                 std::make_unique<book::LimitOrderBook>(std::move(book).value())});
  }
  return simulator;
}

core::Result<ExchangeSimulator> ExchangeSimulator::create_durable(std::vector<core::Market> markets,
                                                                  DurableStoreConfig config) {
  auto store = DurableStore::create(std::move(config), markets);
  if (!store) {
    return store.error();
  }
  auto created = create(std::move(markets));
  if (!created) {
    return created.error();
  }
  ExchangeSimulator simulator = std::move(created).value();
  simulator.durable_store_ = std::move(store).value();
  return simulator;
}

core::Result<ExchangeSimulator> ExchangeSimulator::restore(ExchangeCheckpoint checkpoint) {
  std::vector<core::Market> markets;
  markets.reserve(checkpoint.markets.size());
  for (const MarketCheckpoint& market : checkpoint.markets) {
    markets.push_back(market.market);
  }
  auto created = create(std::move(markets));
  if (!created) {
    return created.error();
  }
  ExchangeSimulator restored = std::move(created).value();
  if (checkpoint.next_order_id == 0 || checkpoint.next_trade_id == 0 ||
      checkpoint.next_event_sequence == 0 || checkpoint.next_ingress_sequence == 0) {
    return SimulatorError(core::DomainErrorCode::InvalidBook,
                          "exchange checkpoint contains an invalid next identifier");
  }

  for (const MarketCheckpoint& market_checkpoint : checkpoint.markets) {
    const auto runtime = restored.markets_.find(market_checkpoint.market.id());
    if (runtime == restored.markets_.end()) {
      return SimulatorError(core::DomainErrorCode::InvalidMarket,
                            "exchange checkpoint contains an unknown market");
    }
    auto restored_book =
        book::LimitOrderBook::restore(market_checkpoint.book, *restored.sequencer_);
    if (!restored_book) {
      return restored_book.error();
    }
    runtime->second.status = market_checkpoint.status;
    runtime->second.book = std::make_unique<book::LimitOrderBook>(std::move(restored_book).value());
  }

  if (!std::is_sorted(checkpoint.pending_commands.begin(), checkpoint.pending_commands.end(),
                      command_less)) {
    return SimulatorError(core::DomainErrorCode::InvalidOrder,
                          "exchange checkpoint pending commands are not deterministically ordered");
  }
  restored.current_time_ = checkpoint.current_time;
  restored.next_order_id_ = checkpoint.next_order_id;
  restored.sequencer_->restore(checkpoint.next_trade_id, checkpoint.next_event_sequence);
  restored.next_ingress_sequence_ = checkpoint.next_ingress_sequence;
  restored.pending_commands_ = std::move(checkpoint.pending_commands);
  return restored;
}

core::Result<ExchangeSimulator> ExchangeSimulator::recover_durable(DurableStoreConfig config) {
  auto opened = DurableStore::open(std::move(config));
  if (!opened) {
    return opened.error();
  }
  auto [store, recovery] = std::move(opened).value();
  const std::size_t replay_start =
      recovery.snapshot.has_value() ? recovery.snapshot->committed_command_count : 0U;
  if (replay_start > recovery.commits.size()) {
    return SimulatorError(core::DomainErrorCode::InconsistentJournal,
                          "durable checkpoint is ahead of the committed command journal");
  }

  std::vector<ScheduledCommand> pending;
  pending.reserve(recovery.commits.size() - replay_start +
                  (recovery.prepared_command.has_value() ? 1U : 0U));
  for (std::size_t index = replay_start; index < recovery.commits.size(); ++index) {
    pending.push_back(recovery.commits[index].command);
  }
  if (recovery.prepared_command.has_value()) {
    pending.push_back(*recovery.prepared_command);
  }
  if (!std::is_sorted(pending.begin(), pending.end(), command_less)) {
    return SimulatorError(core::DomainErrorCode::InconsistentJournal,
                          "durable journal commands are not deterministically ordered");
  }

  ExchangeSimulator simulator;
  if (recovery.snapshot.has_value()) {
    ExchangeCheckpoint checkpoint = recovery.snapshot->checkpoint;
    if (!checkpoint.pending_commands.empty()) {
      return SimulatorError(core::DomainErrorCode::InconsistentJournal,
                            "durable checkpoint must not include unexecuted commands");
    }
    checkpoint.pending_commands = pending;
    std::uint64_t next_ingress = checkpoint.next_ingress_sequence;
    for (const ScheduledCommand& command : pending) {
      if (command.ingress_sequence == std::numeric_limits<std::uint64_t>::max()) {
        return SimulatorError(core::DomainErrorCode::InconsistentJournal,
                              "durable journal ingress sequence is exhausted");
      }
      next_ingress = std::max(next_ingress, command.ingress_sequence + 1U);
    }
    checkpoint.next_ingress_sequence = next_ingress;
    auto restored = restore(std::move(checkpoint));
    if (!restored) {
      return restored.error();
    }
    simulator = std::move(restored).value();
  } else {
    auto created = create(std::move(recovery.markets));
    if (!created) {
      return created.error();
    }
    simulator = std::move(created).value();
    simulator.pending_commands_ = pending;
    for (const ScheduledCommand& command : pending) {
      simulator.next_ingress_sequence_ =
          std::max(simulator.next_ingress_sequence_, command.ingress_sequence + 1U);
    }
  }

  const auto begin = store->begin_recovery_replay(replay_start);
  if (!begin) {
    return begin.error();
  }
  simulator.durable_store_ = std::move(store);
  const auto replayed = simulator.run_until(
      core::Timestamp::from_unix_nanoseconds(std::numeric_limits<std::int64_t>::max()));
  if (!replayed) {
    return replayed.error();
  }
  const auto finished = simulator.durable_store_->finish_recovery_replay();
  if (!finished) {
    return finished.error();
  }
  return simulator;
}

core::Result<ExchangeSimulator> ExchangeSimulator::replay(
    std::vector<core::Market> markets, const std::vector<ScheduledCommand>& commands) {
  auto created = create(std::move(markets));
  if (!created) {
    return created.error();
  }
  ExchangeSimulator replayed = std::move(created).value();
  if (!std::is_sorted(commands.begin(), commands.end(), command_less)) {
    return SimulatorError(core::DomainErrorCode::InvalidOrder,
                          "replay commands are not deterministically ordered");
  }
  std::uint64_t maximum_ingress = 0;
  std::vector<std::uint64_t> ingress_values;
  ingress_values.reserve(commands.size());
  for (const ScheduledCommand& command : commands) {
    if (command.ingress_sequence == 0 ||
        command.ingress_sequence == std::numeric_limits<std::uint64_t>::max()) {
      return SimulatorError(core::DomainErrorCode::InvalidOrder,
                            "replay command has an invalid ingress sequence");
    }
    ingress_values.push_back(command.ingress_sequence);
    maximum_ingress = std::max(maximum_ingress, command.ingress_sequence);
  }
  std::sort(ingress_values.begin(), ingress_values.end());
  if (std::adjacent_find(ingress_values.begin(), ingress_values.end()) != ingress_values.end()) {
    return SimulatorError(core::DomainErrorCode::InvalidOrder,
                          "replay commands contain duplicate ingress sequences");
  }
  replayed.pending_commands_ = commands;
  replayed.next_ingress_sequence_ = maximum_ingress + 1U;
  const core::Result<void> completed = replayed.run_until(
      core::Timestamp::from_unix_nanoseconds(std::numeric_limits<std::int64_t>::max()));
  if (!completed) {
    return completed.error();
  }
  return replayed;
}

core::Result<std::uint64_t> ExchangeSimulator::enqueue(ExchangeCommand command,
                                                       core::Timestamp scheduled_at) {
  if (poisoned_) {
    return SimulatorError(core::DomainErrorCode::RecoveryRequired,
                          "exchange is poisoned after a failed durable operation");
  }
  if (current_time_.has_value() && scheduled_at < *current_time_) {
    return SimulatorError(core::DomainErrorCode::InvalidOrder,
                          "cannot enqueue a command before simulator time");
  }
  if (next_ingress_sequence_ == std::numeric_limits<std::uint64_t>::max()) {
    return SimulatorError(core::DomainErrorCode::IdentifierExhausted,
                          "exchange ingress sequence is exhausted");
  }

  const ScheduledCommand scheduled{scheduled_at, next_ingress_sequence_, std::move(command)};
  ++next_ingress_sequence_;
  const auto insertion =
      std::lower_bound(pending_commands_.begin(), pending_commands_.end(), scheduled, command_less);
  pending_commands_.insert(insertion, scheduled);
  return scheduled.ingress_sequence;
}

core::Result<void> ExchangeSimulator::run_next() {
  if (poisoned_) {
    return SimulatorError(core::DomainErrorCode::RecoveryRequired,
                          "exchange is poisoned after a failed durable operation");
  }
  if (pending_commands_.empty()) {
    return {};
  }
  ScheduledCommand scheduled = pending_commands_.front();
  if (durable_store_) {
    const auto prepared = durable_store_->prepare(scheduled);
    if (!prepared) {
      poisoned_ = true;
      return prepared.error();
    }
  }
  pending_commands_.erase(pending_commands_.begin());
  current_time_ = scheduled.scheduled_at;
  std::vector<ExchangeEvent> batch;
  active_event_batch_ = &batch;
  const auto processed =
      process(scheduled.command, scheduled.scheduled_at, scheduled.ingress_sequence);
  active_event_batch_ = nullptr;
  if (!processed) {
    poisoned_ = durable_store_ != nullptr;
    return processed.error();
  }
  if (durable_store_) {
    const auto committed = durable_store_->commit(scheduled, batch);
    if (!committed) {
      poisoned_ = true;
      return committed.error();
    }
  }
  command_journal_.push_back(std::move(scheduled));
  events_.insert(events_.end(), std::make_move_iterator(batch.begin()),
                 std::make_move_iterator(batch.end()));
  return {};
}

core::Result<void> ExchangeSimulator::run_until(core::Timestamp inclusive_time) {
  while (!pending_commands_.empty() && pending_commands_.front().scheduled_at <= inclusive_time) {
    const core::Result<void> result = run_next();
    if (!result) {
      return result.error();
    }
  }
  return {};
}

core::Result<void> ExchangeSimulator::persist_checkpoint() {
  if (!durable_store_) {
    return SimulatorError(core::DomainErrorCode::InvalidOrder,
                          "exchange has no durable store configured");
  }
  if (poisoned_) {
    return SimulatorError(core::DomainErrorCode::RecoveryRequired,
                          "exchange is poisoned after a failed durable operation");
  }
  if (!pending_commands_.empty()) {
    return SimulatorError(core::DomainErrorCode::InvalidOrder,
                          "durable checkpoints require an empty command queue");
  }
  const auto saved = durable_store_->save_checkpoint(checkpoint(), command_journal_.size());
  if (!saved) {
    poisoned_ = true;
    return saved.error();
  }
  return {};
}

std::vector<ExchangeEvent> ExchangeSimulator::read_events_after(std::uint64_t sequence,
                                                                std::size_t limit) const {
  std::vector<ExchangeEvent> result;
  for (const ExchangeEvent& event : events_) {
    if (event.sequence.value() > sequence && result.size() < limit) {
      result.push_back(event);
    }
  }
  return result;
}

core::Result<book::BookSnapshot> ExchangeSimulator::snapshot(core::ContractId contract_id,
                                                             std::size_t depth) const {
  const MarketRuntime* market = find_market_by_contract(contract_id);
  if (market == nullptr) {
    return SimulatorError(core::DomainErrorCode::InvalidContract,
                          "contract is not registered with this exchange");
  }
  return market->book->snapshot(depth);
}

ExchangeCheckpoint ExchangeSimulator::checkpoint() const {
  std::vector<MarketCheckpoint> markets;
  markets.reserve(markets_.size());
  for (const auto& [market_id, runtime] : markets_) {
    static_cast<void>(market_id);
    markets.push_back(MarketCheckpoint{runtime.market, runtime.status, runtime.book->checkpoint()});
  }
  return ExchangeCheckpoint{current_time_,
                            next_order_id_,
                            sequencer_->next_trade_id(),
                            sequencer_->next_event_sequence(),
                            next_ingress_sequence_,
                            std::move(markets),
                            pending_commands_};
}

core::Result<void> ExchangeSimulator::process(const ExchangeCommand& command,
                                              core::Timestamp occurred_at,
                                              std::uint64_t ingress_sequence) {
  return std::visit(
      [this, occurred_at, ingress_sequence](const auto& value) -> core::Result<void> {
        using Command = std::decay_t<decltype(value)>;
        if constexpr (std::is_same_v<Command, SubmitOrderRequest>) {
          return process_submit(value, occurred_at, ingress_sequence);
        } else if constexpr (std::is_same_v<Command, CancelOrderRequest>) {
          return process_cancel(value, occurred_at, ingress_sequence);
        } else {
          return process_lifecycle(value, occurred_at, ingress_sequence);
        }
      },
      command);
}

core::Result<void> ExchangeSimulator::process_submit(const SubmitOrderRequest& request,
                                                     core::Timestamp occurred_at,
                                                     std::uint64_t ingress_sequence) {
  const auto rejection_capacity = ensure_event_capacity(1);
  if (!rejection_capacity) {
    return rejection_capacity.error();
  }
  MarketRuntime* market = find_market_by_contract(request.contract_id);
  if (market == nullptr) {
    return append_rejection(SimulatorError(core::DomainErrorCode::InvalidContract,
                                           "order contract is not registered with this exchange"),
                            occurred_at, ingress_sequence);
  }
  if (market->status != core::MarketStatus::Open) {
    return append_rejection(
        SimulatorError(core::DomainErrorCode::InvalidMarket, "market is not open for new orders"),
        occurred_at, ingress_sequence);
  }

  const std::uint64_t saved_order_id = next_order_id_;
  const std::uint64_t saved_trade_id = sequencer_->next_trade_id();
  const std::uint64_t saved_event_sequence = sequencer_->next_event_sequence();
  const auto order_id = reserve_order_id();
  if (!order_id) {
    return order_id.error();
  }
  core::Result<core::Order> order =
      SimulatorError(core::DomainErrorCode::InvalidOrder, "unsupported order type");
  if (request.type == core::OrderType::Limit && request.limit_price.has_value()) {
    order = core::Order::create_limit(order_id.value(), request.trader_id, request.contract_id,
                                      request.side, request.quantity, *request.limit_price,
                                      request.submitted_at, market->market.contract());
  } else if (request.type == core::OrderType::Market && !request.limit_price.has_value()) {
    order = core::Order::create_market(order_id.value(), request.trader_id, request.contract_id,
                                       request.side, request.quantity, request.submitted_at,
                                       market->market.contract());
  }
  if (!order) {
    next_order_id_ = saved_order_id;
    return append_rejection(order.error(), occurred_at, ingress_sequence);
  }

  if (request.post_only && request.type != core::OrderType::Limit) {
    next_order_id_ = saved_order_id;
    return append_rejection(SimulatorError(core::DomainErrorCode::InvalidOrder,
                                           "post-only orders must be limit orders"),
                            occurred_at, ingress_sequence);
  }
  if (request.post_only) {
    const book::BookSnapshot top = market->book->snapshot(1);
    const bool crosses =
        request.side == core::Side::Buy
            ? (!top.asks.empty() && *request.limit_price >= top.asks.front().price)
            : (!top.bids.empty() && *request.limit_price <= top.bids.front().price);
    if (crosses) {
      next_order_id_ = saved_order_id;
      return append_rejection(SimulatorError(core::DomainErrorCode::InvalidOrder,
                                             "post-only order would take displayed liquidity"),
                              occurred_at, ingress_sequence);
    }
  }

  const auto preview = market->book->preview_submit(order.value());
  if (!preview) {
    next_order_id_ = saved_order_id;
    return append_rejection(preview.error(), occurred_at, ingress_sequence);
  }
  const std::size_t event_count =
      2U + preview.value().execution_count + (preview.value().changes_displayed_depth ? 1U : 0U);
  const auto event_capacity = ensure_event_capacity(event_count);
  if (!event_capacity) {
    next_order_id_ = saved_order_id;
    return event_capacity.error();
  }
  if (active_event_batch_ != nullptr) {
    active_event_batch_->reserve(event_count);
  }

  const auto acknowledgement_sequence = reserve_event_sequence();
  if (!acknowledgement_sequence) {
    next_order_id_ = saved_order_id;
    return acknowledgement_sequence.error();
  }
  const book::BookSnapshot before = full_snapshot(*market->book);
  const auto report = market->book->submit(order.value(), occurred_at);
  if (!report) {
    next_order_id_ = saved_order_id;
    sequencer_->restore(saved_trade_id, saved_event_sequence);
    return append_rejection(report.error(), occurred_at, ingress_sequence);
  }

  append_event(acknowledgement_sequence.value(), occurred_at, ingress_sequence,
               OrderAcknowledged{order.value()});
  for (const book::Execution& execution : report.value().executions) {
    append_event(execution.trade.sequence(), occurred_at, ingress_sequence,
                 TradeExecuted{execution});
  }
  append_event(reserve_event_sequence().value(), occurred_at, ingress_sequence,
               OrderOutcome{report.value().incoming_order_update});
  const book::BookSnapshot after = full_snapshot(*market->book);
  const std::vector<PriceLevelDelta> changed = depth_delta(before, after);
  if (!changed.empty()) {
    append_event(reserve_event_sequence().value(), occurred_at, ingress_sequence,
                 BookDepthChanged{request.contract_id, changed});
  }
  return {};
}

core::Result<void> ExchangeSimulator::process_cancel(const CancelOrderRequest& request,
                                                     core::Timestamp occurred_at,
                                                     std::uint64_t ingress_sequence) {
  const auto rejection_capacity = ensure_event_capacity(1);
  if (!rejection_capacity) {
    return rejection_capacity.error();
  }
  MarketRuntime* market = find_market_by_contract(request.contract_id);
  if (market == nullptr) {
    return append_rejection(SimulatorError(core::DomainErrorCode::InvalidContract,
                                           "cancel contract is not registered with this exchange"),
                            occurred_at, ingress_sequence);
  }
  if (market->status == core::MarketStatus::Settled) {
    return append_rejection(
        SimulatorError(core::DomainErrorCode::InvalidMarket, "market is settled"), occurred_at,
        ingress_sequence);
  }
  const auto live_order = market->book->find_live_order(request.order_id);
  if (!live_order.has_value() || live_order->trader_id != request.trader_id) {
    return append_rejection(SimulatorError(core::DomainErrorCode::UnknownOrder,
                                           "cancel request does not own a live order"),
                            occurred_at, ingress_sequence);
  }

  const auto event_capacity = ensure_event_capacity(2);
  if (!event_capacity) {
    return event_capacity.error();
  }
  if (active_event_batch_ != nullptr) {
    active_event_batch_->reserve(active_event_batch_->size() + 2U);
  }

  const book::BookSnapshot before = full_snapshot(*market->book);
  const auto report = market->book->cancel(request.order_id);
  if (!report) {
    return append_rejection(report.error(), occurred_at, ingress_sequence);
  }
  append_event(reserve_event_sequence().value(), occurred_at, ingress_sequence,
               CancellationAcknowledged{report.value().order_update});
  const std::vector<PriceLevelDelta> changed = depth_delta(before, full_snapshot(*market->book));
  if (!changed.empty()) {
    append_event(reserve_event_sequence().value(), occurred_at, ingress_sequence,
                 BookDepthChanged{request.contract_id, changed});
  }
  return {};
}

core::Result<void> ExchangeSimulator::process_lifecycle(const MarketLifecycleCommand& command,
                                                        core::Timestamp occurred_at,
                                                        std::uint64_t ingress_sequence) {
  const auto rejection_capacity = ensure_event_capacity(1);
  if (!rejection_capacity) {
    return rejection_capacity.error();
  }
  const auto market = markets_.find(command.market_id);
  if (market == markets_.end()) {
    return append_rejection(SimulatorError(core::DomainErrorCode::InvalidMarket,
                                           "market lifecycle command targets an unknown market"),
                            occurred_at, ingress_sequence);
  }
  MarketRuntime& runtime = market->second;
  if (!valid_transition(runtime.status, command.target_status)) {
    return append_rejection(
        SimulatorError(core::DomainErrorCode::InvalidMarket, "invalid market lifecycle transition"),
        occurred_at, ingress_sequence);
  }

  const book::BookCheckpoint close_checkpoint = runtime.book->checkpoint();
  const std::size_t event_count = command.target_status == core::MarketStatus::Closed
                                      ? 1U + close_checkpoint.resting_orders.size() +
                                            (close_checkpoint.resting_orders.empty() ? 0U : 1U)
                                      : 1U;
  const auto event_capacity = ensure_event_capacity(event_count);
  if (!event_capacity) {
    return event_capacity.error();
  }
  if (active_event_batch_ != nullptr) {
    active_event_batch_->reserve(active_event_batch_->size() + event_count);
  }

  const core::MarketStatus previous = runtime.status;
  runtime.status = command.target_status;
  append_event(reserve_event_sequence().value(), occurred_at, ingress_sequence,
               MarketStatusChanged{command.market_id, previous, runtime.status});
  if (runtime.status != core::MarketStatus::Closed) {
    return {};
  }

  const book::BookSnapshot before = full_snapshot(*runtime.book);
  for (const book::RestingOrderState& order : close_checkpoint.resting_orders) {
    const auto cancelled = runtime.book->cancel(order.order.id());
    if (!cancelled) {
      return cancelled.error();
    }
    append_event(reserve_event_sequence().value(), occurred_at, ingress_sequence,
                 CancellationAcknowledged{cancelled.value().order_update});
  }
  const std::vector<PriceLevelDelta> changed = depth_delta(before, full_snapshot(*runtime.book));
  if (!changed.empty()) {
    append_event(reserve_event_sequence().value(), occurred_at, ingress_sequence,
                 BookDepthChanged{runtime.market.contract().id(), changed});
  }
  return {};
}

core::Result<core::OrderId> ExchangeSimulator::reserve_order_id() {
  if (next_order_id_ == std::numeric_limits<std::uint64_t>::max()) {
    return SimulatorError(core::DomainErrorCode::IdentifierExhausted,
                          "exchange order identifier source is exhausted");
  }
  const auto order_id = core::OrderId::from_value(next_order_id_);
  if (!order_id) {
    return order_id.error();
  }
  ++next_order_id_;
  return order_id.value();
}

core::Result<core::SequenceNumber> ExchangeSimulator::reserve_event_sequence() {
  return sequencer_->reserve_event_sequence();
}

core::Result<void> ExchangeSimulator::ensure_event_capacity(std::size_t count) const {
  return sequencer_->ensure_event_capacity(count);
}

core::Result<void> ExchangeSimulator::append_rejection(core::DomainError error,
                                                       core::Timestamp occurred_at,
                                                       std::uint64_t ingress_sequence) {
  const auto sequence = reserve_event_sequence();
  if (!sequence) {
    return sequence.error();
  }
  append_event(sequence.value(), occurred_at, ingress_sequence, CommandRejected{std::move(error)});
  return {};
}

void ExchangeSimulator::append_event(core::SequenceNumber sequence, core::Timestamp occurred_at,
                                     std::uint64_t ingress_sequence, ExchangeEventPayload payload) {
  ExchangeEvent event{sequence, occurred_at, ingress_sequence, std::move(payload)};
  if (active_event_batch_ != nullptr) {
    active_event_batch_->push_back(std::move(event));
    return;
  }
  events_.push_back(std::move(event));
}

ExchangeSimulator::MarketRuntime* ExchangeSimulator::find_market_by_contract(
    core::ContractId contract_id) {
  const auto route = contract_to_market_.find(contract_id);
  if (route == contract_to_market_.end()) {
    return nullptr;
  }
  return &markets_.find(route->second)->second;
}

const ExchangeSimulator::MarketRuntime* ExchangeSimulator::find_market_by_contract(
    core::ContractId contract_id) const {
  const auto route = contract_to_market_.find(contract_id);
  if (route == contract_to_market_.end()) {
    return nullptr;
  }
  return &markets_.find(route->second)->second;
}

bool ExchangeSimulator::valid_transition(core::MarketStatus from, core::MarketStatus to) {
  if (from == core::MarketStatus::Open) {
    return to == core::MarketStatus::Halted || to == core::MarketStatus::Closed;
  }
  if (from == core::MarketStatus::Halted) {
    return to == core::MarketStatus::Open || to == core::MarketStatus::Closed;
  }
  return from == core::MarketStatus::Closed && to == core::MarketStatus::Settled;
}

std::vector<PriceLevelDelta> ExchangeSimulator::depth_delta(const book::BookSnapshot& before,
                                                            const book::BookSnapshot& after) {
  std::vector<PriceLevelDelta> result;
  const auto append_side = [&result](const std::vector<book::PriceLevelView>& before_levels,
                                     const std::vector<book::PriceLevelView>& after_levels,
                                     core::Side side) {
    std::map<std::uint64_t, book::PriceLevelView> before_by_price;
    std::map<std::uint64_t, book::PriceLevelView> after_by_price;
    for (const book::PriceLevelView& level : before_levels) {
      before_by_price.emplace(level.price.units(), level);
    }
    for (const book::PriceLevelView& level : after_levels) {
      after_by_price.emplace(level.price.units(), level);
    }
    auto before_it = before_by_price.begin();
    auto after_it = after_by_price.begin();
    while (before_it != before_by_price.end() || after_it != after_by_price.end()) {
      if (after_it == after_by_price.end() ||
          (before_it != before_by_price.end() && before_it->first < after_it->first)) {
        result.push_back(PriceLevelDelta{side, before_it->second.price,
                                         core::Quantity::from_units(0).value(), 0});
        ++before_it;
      } else if (before_it == before_by_price.end() || after_it->first < before_it->first) {
        result.push_back(PriceLevelDelta{side, after_it->second.price,
                                         after_it->second.total_quantity,
                                         after_it->second.order_count});
        ++after_it;
      } else {
        if (before_it->second.total_quantity != after_it->second.total_quantity ||
            before_it->second.order_count != after_it->second.order_count) {
          result.push_back(PriceLevelDelta{side, after_it->second.price,
                                           after_it->second.total_quantity,
                                           after_it->second.order_count});
        }
        ++before_it;
        ++after_it;
      }
    }
  };
  append_side(before.bids, after.bids, core::Side::Buy);
  append_side(before.asks, after.asks, core::Side::Sell);
  return result;
}

book::BookSnapshot ExchangeSimulator::full_snapshot(const book::LimitOrderBook& book) {
  return book.snapshot(std::numeric_limits<std::size_t>::max());
}

}  // namespace pmm::sim
