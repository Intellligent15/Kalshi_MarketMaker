#include "pmm/book/order_book.hpp"

#include <algorithm>
#include <bit>
#include <limits>
#include <unordered_set>
#include <utility>

namespace pmm::book {

namespace {

DomainError BookError(core::DomainErrorCode code, const char* message) {
  return DomainError{code, message};
}

}  // namespace

Result<MonotonicExecutionIdSource> MonotonicExecutionIdSource::create(
    TradeId first_trade_id, SequenceNumber first_sequence) {
  return MonotonicExecutionIdSource(first_trade_id.value(), first_sequence.value());
}

Result<std::vector<ExecutionIdentifiers>> MonotonicExecutionIdSource::reserve(
    std::size_t execution_count) {
  if (execution_count == 0) {
    return std::vector<ExecutionIdentifiers>{};
  }
  if (execution_count > std::numeric_limits<std::uint64_t>::max()) {
    return BookError(core::DomainErrorCode::IdentifierExhausted,
                     "execution identifier source is exhausted");
  }

  const std::uint64_t count = static_cast<std::uint64_t>(execution_count);
  if (count > std::numeric_limits<std::uint64_t>::max() - next_trade_id_ ||
      count > std::numeric_limits<std::uint64_t>::max() - next_sequence_) {
    return BookError(core::DomainErrorCode::IdentifierExhausted,
                     "execution identifier source is exhausted");
  }

  std::vector<ExecutionIdentifiers> identifiers;
  identifiers.reserve(execution_count);
  for (std::uint64_t offset = 0; offset < count; ++offset) {
    const auto trade_id = TradeId::from_value(next_trade_id_ + offset);
    const auto sequence = SequenceNumber::from_value(next_sequence_ + offset);
    if (!trade_id || !sequence) {
      return BookError(core::DomainErrorCode::IdentifierExhausted,
                       "execution identifier source generated an invalid identifier");
    }
    identifiers.push_back(ExecutionIdentifiers{trade_id.value(), sequence.value()});
  }

  next_trade_id_ += count;
  next_sequence_ += count;
  return identifiers;
}

Result<LimitOrderBook> LimitOrderBook::create(Contract contract,
                                              ExecutionIdSource& execution_id_source,
                                              BookOptions options) {
  if (options.maximum_price_levels == 0) {
    return BookError(core::DomainErrorCode::InvalidBook,
                     "maximum price levels must be greater than zero");
  }

  const core::PriceGrid& grid = contract.price_grid();
  const std::uint64_t range = grid.maximum().units() - grid.minimum().units();
  const std::uint64_t level_count = range / grid.increment().units() + 1;
  if (level_count > options.maximum_price_levels ||
      level_count > std::numeric_limits<std::size_t>::max()) {
    return BookError(core::DomainErrorCode::InvalidBook,
                     "contract price grid exceeds the order book's dense ladder limit");
  }

  const std::size_t count = static_cast<std::size_t>(level_count);
  const std::size_t word_count = count / 64U + (count % 64U == 0 ? 0U : 1U);
  BookSide bids;
  BookSide asks;
  bids.levels.reserve(count);
  asks.levels.reserve(count);
  bids.occupied_words.assign(word_count, 0);
  asks.occupied_words.assign(word_count, 0);

  for (std::size_t index = 0; index < count; ++index) {
    const std::uint64_t units =
        grid.minimum().units() + static_cast<std::uint64_t>(index) * grid.increment().units();
    const auto price = Price::from_units(static_cast<std::int64_t>(units));
    if (!price) {
      return price.error();
    }
    bids.levels.emplace_back(price.value());
    asks.levels.emplace_back(price.value());
  }

  return LimitOrderBook(std::move(contract), execution_id_source, std::move(bids), std::move(asks),
                        options, 1);
}

Result<SubmitReport> LimitOrderBook::submit(Order order, Timestamp received_at) {
  if (order.contract_id() != contract_.id()) {
    return BookError(core::DomainErrorCode::InvalidOrder,
                     "order contract does not match this order book");
  }
  if (live_orders_.contains(order.id())) {
    return BookError(core::DomainErrorCode::DuplicateOrder,
                     "order identifier is already resting in this order book");
  }

  const auto plan_result = plan_matches(order);
  if (!plan_result) {
    return plan_result.error();
  }
  const MatchPlan& plan = plan_result.value();

  std::uint64_t incoming_remaining = order.quantity().units();
  for (const PlannedMatch& match : plan.matches) {
    incoming_remaining -= match.quantity;
  }
  if (!plan.self_trade_prevented && incoming_remaining != 0 &&
      order.type() == core::OrderType::Limit &&
      next_priority_sequence_ == std::numeric_limits<std::uint64_t>::max()) {
    return BookError(core::DomainErrorCode::IdentifierExhausted,
                     "order priority sequence is exhausted");
  }
  if (!plan.self_trade_prevented && incoming_remaining != 0 &&
      order.type() == core::OrderType::Limit) {
    const BookSide& book_side = side_for(order.side());
    const PriceLevel& level = book_side.levels[price_index(*order.limit_price())];
    if (level.total_quantity > std::numeric_limits<std::uint64_t>::max() - incoming_remaining ||
        level.order_count == std::numeric_limits<std::size_t>::max()) {
      return BookError(core::DomainErrorCode::InvalidBook, "price level aggregate overflow");
    }
  }

  const auto identifiers_result = execution_id_source_.reserve(plan.matches.size());
  if (!identifiers_result) {
    return identifiers_result.error();
  }
  const std::vector<ExecutionIdentifiers>& identifiers = identifiers_result.value();
  if (identifiers.size() != plan.matches.size()) {
    return BookError(core::DomainErrorCode::InvalidBook,
                     "execution identifier source returned an unexpected identifier count");
  }

  std::vector<Execution> executions;
  executions.reserve(plan.matches.size());
  for (std::size_t index = 0; index < plan.matches.size(); ++index) {
    const PlannedMatch& match = plan.matches[index];
    const Order& resting = match.resting_order->order;
    const bool incoming_is_buyer = order.side() == Side::Buy;
    const Order& buyer = incoming_is_buyer ? order : resting;
    const Order& seller = incoming_is_buyer ? resting : order;
    const auto trade = Trade::create(
        identifiers[index].trade_id, contract_.id(), buyer.id(), seller.id(), buyer.trader_id(),
        seller.trader_id(), *resting.limit_price(), quantity_from_units(match.quantity),
        received_at, identifiers[index].sequence, order.side(), contract_);
    if (!trade) {
      return trade.error();
    }
    executions.push_back(
        Execution{trade.value(), Fill::for_buyer(trade.value()), Fill::for_seller(trade.value())});
  }

  std::vector<OrderUpdate> resting_updates;
  resting_updates.reserve(plan.matches.size());
  for (const PlannedMatch& match : plan.matches) {
    OrderNode& resting = *match.resting_order;
    const OrderId resting_id = resting.order.id();
    const std::uint64_t original_quantity = resting.order.quantity().units();
    resting.remaining_quantity -= match.quantity;
    resting.level->total_quantity -= match.quantity;
    if (resting.remaining_quantity == 0) {
      unlink_resting_order(resting);
      live_orders_.erase(resting_id);
      resting_updates.push_back(
          OrderUpdate{resting_id, OrderStatus::Filled, quantity_from_units(0)});
    } else {
      resting_updates.push_back(
          OrderUpdate{resting_id, status_for_resting(resting.remaining_quantity, original_quantity),
                      quantity_from_units(resting.remaining_quantity)});
    }
  }

  if (plan.self_trade_prevented) {
    return SubmitReport{
        std::move(executions), std::move(resting_updates),
        OrderUpdate{order.id(), OrderStatus::Cancelled, quantity_from_units(incoming_remaining)},
        true};
  }
  if (incoming_remaining == 0) {
    return SubmitReport{std::move(executions), std::move(resting_updates),
                        OrderUpdate{order.id(), OrderStatus::Filled, quantity_from_units(0)},
                        false};
  }
  if (order.type() == core::OrderType::Market) {
    return SubmitReport{
        std::move(executions), std::move(resting_updates),
        OrderUpdate{order.id(), OrderStatus::Expired, quantity_from_units(incoming_remaining)},
        false};
  }
  const auto inserted = live_orders_.emplace(
      order.id(), OrderNode{std::move(order), incoming_remaining,
                            SequenceNumber::from_value(next_priority_sequence_).value()});
  OrderNode& resting = inserted.first->second;
  const Result<void> link_result = link_resting_order(resting);
  if (!link_result) {
    live_orders_.erase(inserted.first);
    return link_result.error();
  }
  ++next_priority_sequence_;
  return SubmitReport{
      std::move(executions), std::move(resting_updates),
      OrderUpdate{resting.order.id(),
                  status_for_resting(resting.remaining_quantity, resting.order.quantity().units()),
                  quantity_from_units(resting.remaining_quantity)},
      false};
}

Result<SubmitPreview> LimitOrderBook::preview_submit(const Order& order) const {
  if (order.contract_id() != contract_.id()) {
    return BookError(core::DomainErrorCode::InvalidOrder,
                     "order contract does not match this order book");
  }
  if (live_orders_.contains(order.id())) {
    return BookError(core::DomainErrorCode::DuplicateOrder,
                     "order identifier is already resting in this order book");
  }
  const auto plan = plan_matches(order);
  if (!plan) {
    return plan.error();
  }
  std::uint64_t remaining = order.quantity().units();
  for (const PlannedMatch& match : plan.value().matches) {
    remaining -= match.quantity;
  }
  const bool rests = !plan.value().self_trade_prevented && remaining != 0 &&
                     order.type() == core::OrderType::Limit;
  return SubmitPreview{plan.value().matches.size(), !plan.value().matches.empty() || rests};
}

Result<CancelReport> LimitOrderBook::cancel(OrderId order_id) {
  const auto order = live_orders_.find(order_id);
  if (order == live_orders_.end()) {
    return BookError(core::DomainErrorCode::UnknownOrder,
                     "order identifier is not resting in this order book");
  }

  const std::uint64_t remaining = order->second.remaining_quantity;
  unlink_resting_order(order->second);
  live_orders_.erase(order);
  return CancelReport{
      OrderUpdate{order_id, OrderStatus::Cancelled, quantity_from_units(remaining)}};
}

std::optional<LiveOrderView> LimitOrderBook::find_live_order(OrderId order_id) const {
  const auto order = live_orders_.find(order_id);
  if (order == live_orders_.end()) {
    return std::nullopt;
  }
  const OrderNode& node = order->second;
  return LiveOrderView{node.order.id(),       node.order.trader_id(),
                       node.order.side(),     *node.order.limit_price(),
                       node.order.quantity(), quantity_from_units(node.remaining_quantity),
                       node.priority_sequence};
}

BookSnapshot LimitOrderBook::snapshot(std::size_t depth) const {
  BookSnapshot snapshot;
  const auto collect = [depth](const BookSide& side, Side direction) {
    std::vector<PriceLevelView> levels;
    for (std::size_t offset = 0; offset < side.levels.size() && levels.size() < depth; ++offset) {
      const std::size_t index = direction == Side::Buy ? side.levels.size() - 1U - offset : offset;
      const PriceLevel& level = side.levels[index];
      if (level.order_count != 0) {
        levels.push_back(PriceLevelView{level.price, quantity_from_units(level.total_quantity),
                                        level.order_count});
      }
    }
    return levels;
  };
  snapshot.bids = collect(bids_, Side::Buy);
  snapshot.asks = collect(asks_, Side::Sell);
  return snapshot;
}

BookCheckpoint LimitOrderBook::checkpoint() const {
  std::vector<RestingOrderState> resting_orders;
  resting_orders.reserve(live_orders_.size());
  for (const auto& [order_id, node] : live_orders_) {
    static_cast<void>(order_id);
    resting_orders.push_back(RestingOrderState{
        node.order, quantity_from_units(node.remaining_quantity), node.priority_sequence});
  }
  std::sort(resting_orders.begin(), resting_orders.end(),
            [](const RestingOrderState& left, const RestingOrderState& right) {
              return left.priority_sequence < right.priority_sequence;
            });
  return BookCheckpoint{contract_, options_, std::move(resting_orders),
                        SequenceNumber::from_value(next_priority_sequence_).value()};
}

Result<LimitOrderBook> LimitOrderBook::restore(BookCheckpoint checkpoint,
                                               ExecutionIdSource& execution_id_source) {
  auto create_result =
      LimitOrderBook::create(checkpoint.contract, execution_id_source, checkpoint.options);
  if (!create_result) {
    return create_result.error();
  }
  LimitOrderBook restored = std::move(create_result).value();
  for (const RestingOrderState& state : checkpoint.resting_orders) {
    if (state.order.contract_id() != checkpoint.contract.id() ||
        state.order.type() != core::OrderType::Limit || !state.order.limit_price().has_value() ||
        state.remaining_quantity.is_zero() ||
        state.remaining_quantity.units() > state.order.quantity().units() ||
        state.priority_sequence >= checkpoint.next_priority_sequence) {
      return BookError(core::DomainErrorCode::InvalidBook, "invalid order book checkpoint");
    }

    const auto inserted = restored.live_orders_.emplace(
        state.order.id(),
        OrderNode{state.order, state.remaining_quantity.units(), state.priority_sequence});
    if (!inserted.second) {
      return BookError(core::DomainErrorCode::DuplicateOrder,
                       "order book checkpoint contains a duplicate order identifier");
    }
    const Result<void> linked = restored.link_resting_order(inserted.first->second);
    if (!linked) {
      return linked.error();
    }
  }
  restored.next_priority_sequence_ = checkpoint.next_priority_sequence.value();
  return restored;
}

Result<void> LimitOrderBook::validate_invariants() const {
  std::unordered_set<OrderId, IdentifierHash> queued_order_ids;
  const auto validate_side = [this, &queued_order_ids](const BookSide& side,
                                                       Side expected_side) -> Result<void> {
    for (std::size_t index = 0; index < side.levels.size(); ++index) {
      const PriceLevel& level = side.levels[index];
      std::uint64_t computed_quantity = 0;
      std::size_t computed_count = 0;
      const OrderNode* previous = nullptr;
      std::optional<SequenceNumber> previous_priority;
      for (const OrderNode* node = level.head; node != nullptr; node = node->next) {
        if (node->previous != previous || node->level != &level ||
            node->order.side() != expected_side || !node->order.limit_price().has_value() ||
            *node->order.limit_price() != level.price || node->remaining_quantity == 0 ||
            (previous_priority.has_value() && node->priority_sequence <= *previous_priority)) {
          return BookError(core::DomainErrorCode::InvalidBook,
                           "order book queue linkage or priority invariant failed");
        }
        const auto located = live_orders_.find(node->order.id());
        if (located == live_orders_.end() || &located->second != node ||
            !queued_order_ids.insert(node->order.id()).second) {
          return BookError(core::DomainErrorCode::InvalidBook,
                           "order book live-order locator invariant failed");
        }
        if (computed_quantity >
            std::numeric_limits<std::uint64_t>::max() - node->remaining_quantity) {
          return BookError(core::DomainErrorCode::InvalidBook,
                           "order book queue quantity invariant overflowed");
        }
        computed_quantity += node->remaining_quantity;
        ++computed_count;
        previous = node;
        previous_priority = node->priority_sequence;
      }
      if (level.tail != previous || level.total_quantity != computed_quantity ||
          level.order_count != computed_count ||
          is_occupied(side, index) != (computed_count != 0)) {
        return BookError(core::DomainErrorCode::InvalidBook,
                         "order book price-level aggregate invariant failed");
      }
    }
    return {};
  };

  const Result<void> bids_valid = validate_side(bids_, Side::Buy);
  if (!bids_valid) {
    return bids_valid.error();
  }
  const Result<void> asks_valid = validate_side(asks_, Side::Sell);
  if (!asks_valid) {
    return asks_valid.error();
  }
  if (queued_order_ids.size() != live_orders_.size()) {
    return BookError(core::DomainErrorCode::InvalidBook,
                     "order book has a live order absent from its price queue");
  }
  return {};
}

Result<LimitOrderBook::MatchPlan> LimitOrderBook::plan_matches(const Order& incoming) const {
  MatchPlan plan{{}, false};
  std::uint64_t remaining = incoming.quantity().units();
  const Side resting_side = incoming.side() == Side::Buy ? Side::Sell : Side::Buy;
  std::optional<std::size_t> level_index = best_index(resting_side);
  OrderNode* current = nullptr;

  while (remaining != 0 && level_index.has_value()) {
    const PriceLevel& level = side_for(resting_side).levels[*level_index];
    if (!crosses(incoming, level.price)) {
      break;
    }
    if (current == nullptr) {
      current = level.head;
    }
    if (current == nullptr) {
      return BookError(core::DomainErrorCode::InvalidBook,
                       "occupied price level has no queue head");
    }
    if (current->order.trader_id() == incoming.trader_id()) {
      plan.self_trade_prevented = true;
      break;
    }

    const std::uint64_t quantity = std::min(remaining, current->remaining_quantity);
    plan.matches.push_back(PlannedMatch{current, quantity});
    remaining -= quantity;
    if (remaining == 0) {
      break;
    }
    if (quantity != current->remaining_quantity) {
      return BookError(core::DomainErrorCode::InvalidBook,
                       "match planning left an unexpected partial resting order");
    }

    current = current->next;
    if (current == nullptr) {
      level_index = next_index(resting_side, *level_index);
    }
  }
  return plan;
}

std::optional<std::size_t> LimitOrderBook::best_index(Side side) const {
  const BookSide& book_side = side_for(side);
  if (side == Side::Sell) {
    for (std::size_t word_index = 0; word_index < book_side.occupied_words.size(); ++word_index) {
      const std::uint64_t word = book_side.occupied_words[word_index];
      if (word != 0) {
        return word_index * 64U + static_cast<std::size_t>(std::countr_zero(word));
      }
    }
  } else {
    for (std::size_t word_index = book_side.occupied_words.size(); word_index > 0; --word_index) {
      const std::uint64_t word = book_side.occupied_words[word_index - 1U];
      if (word != 0) {
        return (word_index - 1U) * 64U + 63U - static_cast<std::size_t>(std::countl_zero(word));
      }
    }
  }
  return std::nullopt;
}

std::optional<std::size_t> LimitOrderBook::next_index(Side side, std::size_t index) const {
  const BookSide& book_side = side_for(side);
  if (side == Side::Sell) {
    if (index + 1U >= book_side.levels.size()) {
      return std::nullopt;
    }
    std::size_t word_index = (index + 1U) / 64U;
    const std::size_t bit_index = (index + 1U) % 64U;
    const std::uint64_t mask = std::numeric_limits<std::uint64_t>::max() << bit_index;
    std::uint64_t word = book_side.occupied_words[word_index] & mask;
    if (word != 0) {
      return word_index * 64U + static_cast<std::size_t>(std::countr_zero(word));
    }
    for (++word_index; word_index < book_side.occupied_words.size(); ++word_index) {
      word = book_side.occupied_words[word_index];
      if (word != 0) {
        return word_index * 64U + static_cast<std::size_t>(std::countr_zero(word));
      }
    }
  } else {
    if (index == 0) {
      return std::nullopt;
    }
    const std::size_t previous = index - 1U;
    std::size_t word_index = previous / 64U;
    const std::size_t bit_index = previous % 64U;
    const std::uint64_t mask = bit_index == 63U ? std::numeric_limits<std::uint64_t>::max()
                                                : (std::uint64_t{1} << (bit_index + 1U)) - 1U;
    std::uint64_t word = book_side.occupied_words[word_index] & mask;
    if (word != 0) {
      return word_index * 64U + 63U - static_cast<std::size_t>(std::countl_zero(word));
    }
    while (word_index > 0) {
      --word_index;
      word = book_side.occupied_words[word_index];
      if (word != 0) {
        return word_index * 64U + 63U - static_cast<std::size_t>(std::countl_zero(word));
      }
    }
  }
  return std::nullopt;
}

bool LimitOrderBook::crosses(const Order& incoming, Price resting_price) const {
  if (incoming.type() == core::OrderType::Market) {
    return true;
  }
  const Price limit = *incoming.limit_price();
  return incoming.side() == Side::Buy ? limit >= resting_price : limit <= resting_price;
}

std::size_t LimitOrderBook::price_index(Price price) const {
  const core::PriceGrid& grid = contract_.price_grid();
  return static_cast<std::size_t>((price.units() - grid.minimum().units()) /
                                  grid.increment().units());
}

LimitOrderBook::BookSide& LimitOrderBook::side_for(Side side) {
  return side == Side::Buy ? bids_ : asks_;
}

const LimitOrderBook::BookSide& LimitOrderBook::side_for(Side side) const {
  return side == Side::Buy ? bids_ : asks_;
}

Result<void> LimitOrderBook::link_resting_order(OrderNode& order) {
  if (order.order.type() != core::OrderType::Limit || !order.order.limit_price().has_value()) {
    return BookError(core::DomainErrorCode::OrderNotResting,
                     "only limit orders with a price can rest in an order book");
  }
  BookSide& book_side = side_for(order.order.side());
  PriceLevel& level = book_side.levels[price_index(*order.order.limit_price())];
  if (level.total_quantity > std::numeric_limits<std::uint64_t>::max() - order.remaining_quantity ||
      level.order_count == std::numeric_limits<std::size_t>::max()) {
    return BookError(core::DomainErrorCode::InvalidBook, "price level aggregate overflow");
  }

  order.level = &level;
  order.previous = level.tail;
  order.next = nullptr;
  if (level.tail != nullptr) {
    level.tail->next = &order;
  } else {
    level.head = &order;
  }
  level.tail = &order;
  level.total_quantity += order.remaining_quantity;
  ++level.order_count;
  set_occupied(book_side, price_index(level.price), true);
  return {};
}

void LimitOrderBook::unlink_resting_order(OrderNode& order) {
  PriceLevel& level = *order.level;
  BookSide& book_side = side_for(order.order.side());
  if (order.previous != nullptr) {
    order.previous->next = order.next;
  } else {
    level.head = order.next;
  }
  if (order.next != nullptr) {
    order.next->previous = order.previous;
  } else {
    level.tail = order.previous;
  }
  level.total_quantity -= order.remaining_quantity;
  --level.order_count;
  if (level.order_count == 0) {
    set_occupied(book_side, price_index(level.price), false);
  }
  order.level = nullptr;
  order.previous = nullptr;
  order.next = nullptr;
}

void LimitOrderBook::set_occupied(BookSide& side, std::size_t index, bool occupied) {
  const std::size_t word_index = index / 64U;
  const std::uint64_t bit = std::uint64_t{1} << (index % 64U);
  if (occupied) {
    side.occupied_words[word_index] |= bit;
  } else {
    side.occupied_words[word_index] &= ~bit;
  }
}

bool LimitOrderBook::is_occupied(const BookSide& side, std::size_t index) const {
  return (side.occupied_words[index / 64U] & (std::uint64_t{1} << (index % 64U))) != 0;
}

Quantity LimitOrderBook::quantity_from_units(std::uint64_t units) {
  return Quantity::from_units(static_cast<std::int64_t>(units)).value();
}

OrderStatus LimitOrderBook::status_for_resting(std::uint64_t remaining, std::uint64_t original) {
  return remaining == original ? OrderStatus::Resting : OrderStatus::PartiallyFilled;
}

}  // namespace pmm::book
