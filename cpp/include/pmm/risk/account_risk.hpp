#pragma once

#include <cstddef>
#include <cstdint>
#include <map>
#include <optional>
#include <variant>
#include <vector>

#include "pmm/sim/exchange_simulator.hpp"

namespace pmm::risk {

struct AccountIdTag {};
struct StrategyIdTag {};
struct ClientIntentIdTag {};

using AccountId = core::Identifier<AccountIdTag>;
using StrategyId = core::Identifier<StrategyIdTag>;
using ClientIntentId = core::Identifier<ClientIntentIdTag>;

struct AccountBinding {
  AccountId account_id;
  StrategyId strategy_id;
  core::TraderId trader_id;
  core::ContractId contract_id;
};

struct RiskLimits {
  core::Quantity maximum_order_quantity;
  core::Quantity maximum_absolute_position;
  core::Quantity maximum_buy_exposure;
  core::Quantity maximum_sell_exposure;
  core::Quantity maximum_pending_exposure;
  std::size_t maximum_active_orders;
};

// Strategies create this identity-free request. Admission supplies the permitted TraderId.
struct OrderIntent {
  ClientIntentId client_intent_id;
  core::ContractId contract_id;
  core::Side side;
  core::Quantity quantity;
  core::Price limit_price;
  bool post_only = true;
};

enum class AdmissionRejectCode {
  KillSwitchActive,
  ContractMismatch,
  OrderQuantityLimit,
  ActiveOrderLimit,
  BuyExposureLimit,
  SellExposureLimit,
  PendingExposureLimit,
  PositionLimit,
  DuplicateClientIntent,
};

struct AdmissionRejection {
  AdmissionRejectCode code;
  core::DomainError error;
};

struct AdmissionDecision {
  ClientIntentId client_intent_id;
  std::optional<sim::SubmitOrderRequest> command;
  std::optional<AdmissionRejection> rejection;

  [[nodiscard]] bool approved() const {
    return command.has_value();
  }
};

struct LiveRiskOrder {
  core::OrderId order_id;
  core::Side side;
  core::Price price;
  core::Quantity remaining_quantity;
  core::Timestamp acknowledged_at;
};

struct PendingRiskOrder {
  OrderIntent intent;
  std::optional<std::uint64_t> ingress_sequence;
};

struct AccountRiskView {
  AccountId account_id;
  core::ContractId contract_id;
  std::uint64_t event_watermark;
  std::int64_t net_position;
  core::Quantity open_buy_quantity;
  core::Quantity open_sell_quantity;
  core::Quantity pending_buy_quantity;
  core::Quantity pending_sell_quantity;
  bool kill_switch_active;
};

struct RiskCheckpoint {
  std::uint64_t event_watermark;
  std::int64_t net_position;
  bool kill_switch_active;
  std::vector<LiveRiskOrder> live_orders;
  std::vector<PendingRiskOrder> pending_orders;
};

// Validation categories for restoring a checkpoint.  The first failure in the documented
// order wins: live orders in vector order (zero quantity, then duplicate identifier), pending
// orders in vector order (contract, zero quantity, post-only, zero ingress, duplicate ingress,
// duplicate intent), then active-order count, open/pending exposure, and position.
enum class CheckpointRejectCode {
  ZeroLiveQuantity,
  DuplicateOrderId,
  ContractMismatch,
  ZeroPendingQuantity,
  NonPostOnlyIntent,
  ZeroIngress,
  DuplicateIngress,
  DuplicateClientIntent,
  ActiveOrderLimit,
  BuyExposureLimit,
  SellExposureLimit,
  PendingExposureLimit,
  PositionLimit,
};

struct CheckpointRejection {
  CheckpointRejectCode code;
  core::DomainError error;
};

// Account events are the canonical input to account risk.  Production exchange events are
// adapted into this shape, while research execution models may emit ModelDerived events without
// pretending that observed Level-2 data was matched by the exchange.
enum class AccountEventTruth {
  Simulator,
  ModelDerived,
  Observed,
};

struct AccountOrderAcknowledged {
  core::OrderId order_id;
  core::TraderId trader_id;
  core::ContractId contract_id;
  core::Side side;
  core::Quantity quantity;
  core::Price limit_price;
};

struct AccountFill {
  core::OrderId order_id;
  core::TraderId trader_id;
  core::ContractId contract_id;
  core::Side side;
  core::Price price;
  core::Quantity quantity;
};

struct AccountOrderOutcome {
  core::OrderId order_id;
  core::Quantity remaining_quantity;
};

struct AccountCancellation {
  core::OrderId order_id;
};

struct AccountCommandRejected {};
struct AccountOtherEvent {};

using AccountEventPayload =
    std::variant<AccountOrderAcknowledged, AccountFill, AccountOrderOutcome, AccountCancellation,
                 AccountCommandRejected, AccountOtherEvent>;

struct AccountEvent {
  core::SequenceNumber sequence;
  core::Timestamp occurred_at;
  std::uint64_t ingress_sequence;
  AccountEventTruth truth;
  AccountEventPayload payload;
};

// The exchange owns executions. This projection owns account exposure derived from them.
class AccountRiskProjection final {
 public:
  [[nodiscard]] static core::Result<AccountRiskProjection> create(AccountBinding binding,
                                                                  RiskLimits limits);
  [[nodiscard]] static core::Result<AccountRiskProjection> restore(AccountBinding binding,
                                                                   RiskLimits limits,
                                                                   RiskCheckpoint checkpoint);
  // Pure first-failure validation of a checkpoint against a binding and limits.  `restore`
  // delegates to it, so a checkpoint is restorable exactly when this returns no rejection.
  [[nodiscard]] static std::optional<CheckpointRejection> validate_checkpoint(
      const AccountBinding& binding, const RiskLimits& limits, const RiskCheckpoint& checkpoint);

  [[nodiscard]] const AccountBinding& binding() const {
    return binding_;
  }
  [[nodiscard]] AccountRiskView view() const;
  [[nodiscard]] RiskCheckpoint checkpoint() const;
  [[nodiscard]] const std::map<core::OrderId, LiveRiskOrder>& live_orders() const {
    return live_orders_;
  }
  [[nodiscard]] const std::map<ClientIntentId, PendingRiskOrder>& pending_orders() const {
    return pending_orders_;
  }

  [[nodiscard]] AdmissionDecision admit(const OrderIntent& intent, core::Timestamp submitted_at);
  [[nodiscard]] core::Result<void> bind_ingress(ClientIntentId client_intent_id,
                                                std::uint64_t ingress_sequence);
  // Applies a canonical event from either the exchange adapter or an explicitly labelled
  // research execution model.  The same reservation and exposure rules apply to both sources.
  [[nodiscard]] core::Result<void> apply(const AccountEvent& event);
  [[nodiscard]] core::Result<void> apply(const sim::ExchangeEvent& event);
  void activate_kill_switch() {
    kill_switch_active_ = true;
  }
  void clear_kill_switch() {
    kill_switch_active_ = false;
  }

 private:
  AccountRiskProjection(AccountBinding binding, RiskLimits limits)
      : binding_(binding), limits_(limits) {}

  [[nodiscard]] core::Quantity aggregate_quantity(core::Side side, bool pending) const;
  [[nodiscard]] bool exceeds_position_limit(core::Side side, core::Quantity quantity) const;
  [[nodiscard]] static core::Result<core::Quantity> quantity_from_units(std::uint64_t units);
  [[nodiscard]] static core::DomainError risk_error(const char* message);

  AccountBinding binding_;
  RiskLimits limits_;
  std::uint64_t event_watermark_ = 0;
  std::int64_t net_position_ = 0;
  bool kill_switch_active_ = false;
  std::map<core::OrderId, LiveRiskOrder> live_orders_;
  std::map<ClientIntentId, PendingRiskOrder> pending_orders_;
};

}  // namespace pmm::risk
