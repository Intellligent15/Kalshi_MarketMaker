#include "pmm/risk/account_risk.hpp"

#include <algorithm>
#include <limits>

namespace pmm::risk {
namespace {

core::DomainError Error(core::DomainErrorCode code, const char* message) {
  return core::DomainError{code, message};
}

}  // namespace

core::Result<AccountRiskProjection> AccountRiskProjection::create(AccountBinding binding,
                                                                  RiskLimits limits) {
  if (limits.maximum_order_quantity.is_zero() || limits.maximum_absolute_position.is_zero() ||
      limits.maximum_buy_exposure.is_zero() || limits.maximum_sell_exposure.is_zero() ||
      limits.maximum_pending_exposure.is_zero() || limits.maximum_active_orders == 0) {
    return Error(core::DomainErrorCode::InvalidQuantity, "risk limits must be positive");
  }
  return AccountRiskProjection(binding, limits);
}

core::Result<AccountRiskProjection> AccountRiskProjection::restore(AccountBinding binding,
                                                                   RiskLimits limits,
                                                                   RiskCheckpoint checkpoint) {
  auto restored = create(binding, limits);
  if (!restored) {
    return restored.error();
  }
  AccountRiskProjection projection = std::move(restored).value();
  projection.event_watermark_ = checkpoint.event_watermark;
  projection.net_position_ = checkpoint.net_position;
  projection.kill_switch_active_ = checkpoint.kill_switch_active;
  for (const LiveRiskOrder& order : checkpoint.live_orders) {
    if (order.remaining_quantity.is_zero() ||
        !projection.live_orders_.emplace(order.order_id, order).second) {
      return Error(core::DomainErrorCode::InvalidOrder,
                   "risk checkpoint contains invalid live orders");
    }
  }
  for (const PendingRiskOrder& pending : checkpoint.pending_orders) {
    if (!projection.pending_orders_.emplace(pending.intent.client_intent_id, pending).second) {
      return Error(core::DomainErrorCode::InvalidOrder,
                   "risk checkpoint contains duplicate client intents");
    }
  }
  if (projection.live_orders_.size() + projection.pending_orders_.size() >
      projection.limits_.maximum_active_orders) {
    return Error(core::DomainErrorCode::InvalidOrder, "risk checkpoint exceeds active order limit");
  }
  return projection;
}

AccountRiskView AccountRiskProjection::view() const {
  return AccountRiskView{binding_.account_id,
                         binding_.contract_id,
                         event_watermark_,
                         net_position_,
                         aggregate_quantity(core::Side::Buy, false),
                         aggregate_quantity(core::Side::Sell, false),
                         aggregate_quantity(core::Side::Buy, true),
                         aggregate_quantity(core::Side::Sell, true),
                         kill_switch_active_};
}

RiskCheckpoint AccountRiskProjection::checkpoint() const {
  std::vector<LiveRiskOrder> live_orders;
  live_orders.reserve(live_orders_.size());
  for (const auto& [order_id, order] : live_orders_) {
    static_cast<void>(order_id);
    live_orders.push_back(order);
  }
  std::vector<PendingRiskOrder> pending_orders;
  pending_orders.reserve(pending_orders_.size());
  for (const auto& [client_intent_id, pending] : pending_orders_) {
    static_cast<void>(client_intent_id);
    pending_orders.push_back(pending);
  }
  return RiskCheckpoint{event_watermark_, net_position_, kill_switch_active_,
                        std::move(live_orders), std::move(pending_orders)};
}

AdmissionDecision AccountRiskProjection::admit(const OrderIntent& intent,
                                               core::Timestamp submitted_at) {
  const auto reject = [&intent](AdmissionRejectCode code, const char* message) {
    return AdmissionDecision{intent.client_intent_id, std::nullopt,
                             AdmissionRejection{code, risk_error(message)}};
  };
  if (kill_switch_active_) {
    return reject(AdmissionRejectCode::KillSwitchActive, "account kill switch is active");
  }
  if (intent.contract_id != binding_.contract_id) {
    return reject(AdmissionRejectCode::ContractMismatch, "intent contract is not bound to account");
  }
  if (intent.quantity.is_zero()) {
    return reject(AdmissionRejectCode::OrderQuantityLimit, "order quantity must be positive");
  }
  if (pending_orders_.contains(intent.client_intent_id)) {
    return reject(AdmissionRejectCode::DuplicateClientIntent, "duplicate client intent identifier");
  }
  if (intent.quantity > limits_.maximum_order_quantity) {
    return reject(AdmissionRejectCode::OrderQuantityLimit, "order quantity exceeds risk limit");
  }
  if (live_orders_.size() + pending_orders_.size() >= limits_.maximum_active_orders) {
    return reject(AdmissionRejectCode::ActiveOrderLimit, "active order limit reached");
  }

  const std::uint64_t pending_side = aggregate_quantity(intent.side, true).units();
  if (pending_side > limits_.maximum_pending_exposure.units() ||
      intent.quantity.units() > limits_.maximum_pending_exposure.units() - pending_side) {
    return reject(AdmissionRejectCode::PendingExposureLimit, "pending exposure exceeds risk limit");
  }
  const std::uint64_t open_side = aggregate_quantity(intent.side, false).units();
  const std::uint64_t side_limit = intent.side == core::Side::Buy
                                       ? limits_.maximum_buy_exposure.units()
                                       : limits_.maximum_sell_exposure.units();
  if (intent.quantity.units() > std::numeric_limits<std::uint64_t>::max() - open_side ||
      intent.quantity.units() + open_side > side_limit) {
    return reject(intent.side == core::Side::Buy ? AdmissionRejectCode::BuyExposureLimit
                                                 : AdmissionRejectCode::SellExposureLimit,
                  "open exposure exceeds risk limit");
  }
  if (exceeds_position_limit(intent.side, intent.quantity)) {
    return reject(AdmissionRejectCode::PositionLimit, "worst-case position exceeds risk limit");
  }

  pending_orders_.emplace(intent.client_intent_id, PendingRiskOrder{intent, std::nullopt});
  return AdmissionDecision{
      intent.client_intent_id,
      sim::SubmitOrderRequest{binding_.trader_id, intent.contract_id, intent.side,
                              core::OrderType::Limit, intent.quantity, intent.limit_price,
                              submitted_at, intent.post_only},
      std::nullopt};
}

core::Result<void> AccountRiskProjection::bind_ingress(ClientIntentId client_intent_id,
                                                       std::uint64_t ingress_sequence) {
  const auto pending = pending_orders_.find(client_intent_id);
  if (pending == pending_orders_.end() || pending->second.ingress_sequence.has_value() ||
      ingress_sequence == 0) {
    return Error(core::DomainErrorCode::InvalidOrder, "cannot bind risk reservation to ingress");
  }
  pending->second.ingress_sequence = ingress_sequence;
  return {};
}

core::Result<void> AccountRiskProjection::apply(const sim::ExchangeEvent& event) {
  AccountEventPayload payload = AccountOtherEvent{};
  if (const auto* acknowledgement = std::get_if<sim::OrderAcknowledged>(&event.payload)) {
    const core::Order& order = acknowledgement->order;
    if (!order.limit_price().has_value()) {
      return Error(core::DomainErrorCode::InvalidOrder,
                   "risk projection received a non-limit acknowledged order");
    }
    payload = AccountOrderAcknowledged{order.id(),   order.trader_id(), order.contract_id(),
                                       order.side(), order.quantity(),  *order.limit_price()};
  } else if (const auto* execution = std::get_if<sim::TradeExecuted>(&event.payload)) {
    const core::Fill& buyer = execution->execution.buyer_fill;
    const core::Fill& seller = execution->execution.seller_fill;
    if (buyer.trader_id() == binding_.trader_id) {
      payload = AccountFill{buyer.order_id(), buyer.trader_id(), buyer.contract_id(),
                            buyer.side(),     buyer.price(),     buyer.quantity()};
    } else if (seller.trader_id() == binding_.trader_id) {
      payload = AccountFill{seller.order_id(), seller.trader_id(), seller.contract_id(),
                            seller.side(),     seller.price(),     seller.quantity()};
    }
  } else if (const auto* outcome = std::get_if<sim::OrderOutcome>(&event.payload)) {
    payload = AccountOrderOutcome{outcome->update.order_id, outcome->update.remaining_quantity};
  } else if (const auto* cancellation =
                 std::get_if<sim::CancellationAcknowledged>(&event.payload)) {
    payload = AccountCancellation{cancellation->update.order_id};
  } else if (std::holds_alternative<sim::CommandRejected>(event.payload)) {
    payload = AccountCommandRejected{};
  }
  return apply(AccountEvent{event.sequence, event.occurred_at, event.ingress_sequence,
                            AccountEventTruth::Simulator, std::move(payload)});
}

core::Result<void> AccountRiskProjection::apply(const AccountEvent& event) {
  if (event.sequence.value() != event_watermark_ + 1U) {
    return Error(core::DomainErrorCode::InvalidOrder,
                 "risk projection requires contiguous exchange events");
  }
  if (const auto* acknowledgement = std::get_if<AccountOrderAcknowledged>(&event.payload)) {
    if (acknowledgement->trader_id == binding_.trader_id) {
      const auto pending =
          std::find_if(pending_orders_.begin(), pending_orders_.end(), [&event](const auto& entry) {
            return entry.second.ingress_sequence == event.ingress_sequence;
          });
      if (pending == pending_orders_.end()) {
        return Error(core::DomainErrorCode::OwnershipMismatch,
                     "account observed an unadmitted trader order");
      }
      const PendingRiskOrder reservation = pending->second;
      if (reservation.intent.contract_id != acknowledgement->contract_id ||
          reservation.intent.side != acknowledgement->side ||
          reservation.intent.quantity != acknowledgement->quantity ||
          reservation.intent.limit_price != acknowledgement->limit_price) {
        return Error(core::DomainErrorCode::InvalidOrder,
                     "acknowledged order does not match risk reservation");
      }
      if (live_orders_.contains(acknowledgement->order_id)) {
        return Error(core::DomainErrorCode::InvalidOrder,
                     "acknowledged order identifier already exists in risk projection");
      }
      live_orders_.emplace(acknowledgement->order_id,
                           LiveRiskOrder{acknowledgement->order_id, acknowledgement->side,
                                         acknowledgement->limit_price, acknowledgement->quantity,
                                         event.occurred_at});
      pending_orders_.erase(pending);
    }
  } else if (const auto* fill = std::get_if<AccountFill>(&event.payload)) {
    if (fill->trader_id == binding_.trader_id) {
      if (fill->contract_id != binding_.contract_id) {
        return Error(core::DomainErrorCode::OwnershipMismatch,
                     "account fill has a contract outside this risk binding");
      }
      const auto live = live_orders_.find(fill->order_id);
      if (live == live_orders_.end() || live->second.side != fill->side ||
          live->second.remaining_quantity.units() < fill->quantity.units()) {
        return Error(core::DomainErrorCode::InvalidOrder,
                     "fill does not match projected live order");
      }
      if (fill->quantity.units() >
          static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max())) {
        return Error(core::DomainErrorCode::PositionOverflow, "fill exceeds signed position range");
      }
      const std::int64_t quantity = static_cast<std::int64_t>(fill->quantity.units());
      if ((fill->side == core::Side::Buy &&
           net_position_ > std::numeric_limits<std::int64_t>::max() - quantity) ||
          (fill->side == core::Side::Sell &&
           net_position_ < std::numeric_limits<std::int64_t>::min() + quantity)) {
        return Error(core::DomainErrorCode::PositionOverflow, "account position overflow");
      }
      const auto remaining =
          quantity_from_units(live->second.remaining_quantity.units() - fill->quantity.units());
      if (!remaining) {
        return remaining.error();
      }
      net_position_ += fill->side == core::Side::Buy ? quantity : -quantity;
      if (remaining.value().is_zero()) {
        live_orders_.erase(live);
      } else {
        live->second.remaining_quantity = remaining.value();
      }
    }
  } else if (const auto* outcome = std::get_if<AccountOrderOutcome>(&event.payload)) {
    const auto live = live_orders_.find(outcome->order_id);
    if (live != live_orders_.end()) {
      if (outcome->remaining_quantity.is_zero()) {
        live_orders_.erase(live);
      } else if (outcome->remaining_quantity > live->second.remaining_quantity) {
        return Error(core::DomainErrorCode::InvalidOrder,
                     "order outcome cannot increase projected remaining quantity");
      } else {
        live->second.remaining_quantity = outcome->remaining_quantity;
      }
    }
  } else if (const auto* cancellation = std::get_if<AccountCancellation>(&event.payload)) {
    live_orders_.erase(cancellation->order_id);
  } else if (std::holds_alternative<AccountCommandRejected>(event.payload)) {
    const auto pending =
        std::find_if(pending_orders_.begin(), pending_orders_.end(), [&event](const auto& entry) {
          return entry.second.ingress_sequence == event.ingress_sequence;
        });
    if (pending != pending_orders_.end()) {
      pending_orders_.erase(pending);
    }
  }
  event_watermark_ = event.sequence.value();
  return {};
}

core::Quantity AccountRiskProjection::aggregate_quantity(core::Side side, bool pending) const {
  std::uint64_t total = 0;
  if (pending) {
    for (const auto& [client_intent_id, reservation] : pending_orders_) {
      static_cast<void>(client_intent_id);
      if (reservation.intent.side == side) {
        if (reservation.intent.quantity.units() >
            std::numeric_limits<std::uint64_t>::max() - total) {
          return core::Quantity::from_units(std::numeric_limits<std::int64_t>::max()).value();
        }
        total += reservation.intent.quantity.units();
      }
    }
  } else {
    for (const auto& [order_id, order] : live_orders_) {
      static_cast<void>(order_id);
      if (order.side == side) {
        if (order.remaining_quantity.units() > std::numeric_limits<std::uint64_t>::max() - total) {
          return core::Quantity::from_units(std::numeric_limits<std::int64_t>::max()).value();
        }
        total += order.remaining_quantity.units();
      }
    }
  }
  return quantity_from_units(total).value();
}

bool AccountRiskProjection::exceeds_position_limit(core::Side side, core::Quantity quantity) const {
  const auto add = [](std::uint64_t left, std::uint64_t right, std::uint64_t* result) {
    if (right > std::numeric_limits<std::uint64_t>::max() - left) {
      return false;
    }
    *result = left + right;
    return true;
  };
  std::uint64_t buys = aggregate_quantity(core::Side::Buy, false).units();
  std::uint64_t sells = aggregate_quantity(core::Side::Sell, false).units();
  if (!add(buys, aggregate_quantity(core::Side::Buy, true).units(), &buys) ||
      !add(sells, aggregate_quantity(core::Side::Sell, true).units(), &sells) ||
      (side == core::Side::Buy && !add(buys, quantity.units(), &buys)) ||
      (side == core::Side::Sell && !add(sells, quantity.units(), &sells)) ||
      buys > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()) ||
      sells > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max())) {
    return true;
  }
  const std::int64_t buy_quantity = static_cast<std::int64_t>(buys);
  const std::int64_t sell_quantity = static_cast<std::int64_t>(sells);
  const std::int64_t limit = static_cast<std::int64_t>(limits_.maximum_absolute_position.units());
  return net_position_ > limit - buy_quantity || net_position_ < -limit + sell_quantity;
}

core::Result<core::Quantity> AccountRiskProjection::quantity_from_units(std::uint64_t units) {
  if (units > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max())) {
    return Error(core::DomainErrorCode::PositionOverflow, "quantity exceeds domain range");
  }
  return core::Quantity::from_units(static_cast<std::int64_t>(units));
}

core::DomainError AccountRiskProjection::risk_error(const char* message) {
  return Error(core::DomainErrorCode::InvalidOrder, message);
}

}  // namespace pmm::risk
