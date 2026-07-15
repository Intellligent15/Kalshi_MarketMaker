#include <iostream>
#include <optional>
#include <sstream>
#include <string>

#include "pmm/risk/account_risk.hpp"

namespace {

using pmm::core::ContractId;
using pmm::core::Price;
using pmm::core::Quantity;
using pmm::core::Result;
using pmm::core::SequenceNumber;
using pmm::core::Side;
using pmm::core::Timestamp;
using pmm::core::TraderId;
using pmm::risk::AccountBinding;
using pmm::risk::AccountCancellation;
using pmm::risk::AccountCommandRejected;
using pmm::risk::AccountEvent;
using pmm::risk::AccountEventTruth;
using pmm::risk::AccountFill;
using pmm::risk::AccountId;
using pmm::risk::AccountOrderAcknowledged;
using pmm::risk::AccountRiskProjection;
using pmm::risk::ClientIntentId;
using pmm::risk::OrderIntent;
using pmm::risk::RiskLimits;
using pmm::risk::StrategyId;

template <typename T>
std::optional<T> Required(Result<T> value) {
  if (!value) {
    return std::nullopt;
  }
  return std::move(value).value();
}

std::optional<Side> ParseSide(const std::string& value) {
  if (value == "buy") {
    return Side::Buy;
  }
  if (value == "sell") {
    return Side::Sell;
  }
  return std::nullopt;
}

void PrintView(const AccountRiskProjection& risk) {
  const auto view = risk.view();
  std::cout << "VIEW " << view.event_watermark << ' ' << view.net_position << ' '
            << view.open_buy_quantity.units() << ' ' << view.open_sell_quantity.units() << ' '
            << view.pending_buy_quantity.units() << ' ' << view.pending_sell_quantity.units() << ' '
            << (view.kill_switch_active ? 1 : 0) << '\n';
}

void Error(const std::string& message) {
  std::cout << "ERROR " << message << '\n';
}

}  // namespace

int main() {
  std::optional<AccountRiskProjection> risk;
  std::string line;
  while (std::getline(std::cin, line)) {
    std::istringstream input(line);
    std::string command;
    input >> command;
    if (command.empty() || command.starts_with('#')) {
      continue;
    }
    if (command == "INIT") {
      std::uint64_t account = 0;
      std::uint64_t strategy = 0;
      std::uint64_t trader = 0;
      std::uint64_t contract = 0;
      std::int64_t max_order = 0;
      std::int64_t max_position = 0;
      std::int64_t max_buy = 0;
      std::int64_t max_sell = 0;
      std::int64_t max_pending = 0;
      std::size_t max_active = 0;
      if (!(input >> account >> strategy >> trader >> contract >> max_order >> max_position >>
            max_buy >> max_sell >> max_pending >> max_active)) {
        Error("invalid_init");
        continue;
      }
      const auto account_id = Required(AccountId::from_value(account));
      const auto strategy_id = Required(StrategyId::from_value(strategy));
      const auto trader_id = Required(TraderId::from_value(trader));
      const auto contract_id = Required(ContractId::from_value(contract));
      const auto maximum_order = Required(Quantity::from_units(max_order));
      const auto maximum_position = Required(Quantity::from_units(max_position));
      const auto maximum_buy = Required(Quantity::from_units(max_buy));
      const auto maximum_sell = Required(Quantity::from_units(max_sell));
      const auto maximum_pending = Required(Quantity::from_units(max_pending));
      if (!account_id || !strategy_id || !trader_id || !contract_id || !maximum_order ||
          !maximum_position || !maximum_buy || !maximum_sell || !maximum_pending) {
        Error("invalid_init_domain");
        continue;
      }
      auto created = AccountRiskProjection::create(
          AccountBinding{*account_id, *strategy_id, *trader_id, *contract_id},
          RiskLimits{*maximum_order, *maximum_position, *maximum_buy, *maximum_sell,
                     *maximum_pending, max_active});
      if (!created) {
        Error(created.error().message);
        continue;
      }
      risk = std::move(created).value();
      std::cout << "READY\n";
      continue;
    }
    if (!risk) {
      Error("not_initialized");
      continue;
    }
    if (command == "ADMIT") {
      std::uint64_t client = 0;
      std::string side_text;
      std::int64_t quantity = 0;
      std::int64_t price = 0;
      std::int64_t time = 0;
      if (!(input >> client >> side_text >> quantity >> price >> time)) {
        Error("invalid_admit");
        continue;
      }
      const auto client_id = Required(ClientIntentId::from_value(client));
      const auto side = ParseSide(side_text);
      const auto order_quantity = Required(Quantity::from_units(quantity));
      const auto limit_price = Required(Price::from_units(price));
      if (!client_id || !side || !order_quantity || !limit_price) {
        Error("invalid_admit_domain");
        continue;
      }
      const auto decision = risk->admit(OrderIntent{*client_id, risk->binding().contract_id, *side,
                                                    *order_quantity, *limit_price, true},
                                        Timestamp::from_unix_nanoseconds(time));
      if (decision.approved()) {
        std::cout << "ADMISSION approved " << client << '\n';
      } else {
        std::cout << "ADMISSION rejected " << client << ' '
                  << static_cast<int>(decision.rejection->code) << '\n';
      }
      continue;
    }
    if (command == "BIND") {
      std::uint64_t client = 0;
      std::uint64_t ingress = 0;
      if (!(input >> client >> ingress)) {
        Error("invalid_bind");
        continue;
      }
      const auto client_id = Required(ClientIntentId::from_value(client));
      if (!client_id) {
        Error("invalid_bind_domain");
      } else if (const auto result = risk->bind_ingress(*client_id, ingress); !result) {
        Error(result.error().message);
      } else {
        std::cout << "BOUND " << client << ' ' << ingress << '\n';
      }
      continue;
    }
    if (command == "ACK") {
      std::uint64_t sequence = 0;
      std::uint64_t ingress = 0;
      std::uint64_t order = 0;
      std::string side_text;
      std::int64_t quantity = 0;
      std::int64_t price = 0;
      std::int64_t time = 0;
      if (!(input >> sequence >> ingress >> order >> side_text >> quantity >> price >> time)) {
        Error("invalid_ack");
        continue;
      }
      const auto event_sequence = Required(SequenceNumber::from_value(sequence));
      const auto order_id = Required(pmm::core::OrderId::from_value(order));
      const auto side = ParseSide(side_text);
      const auto order_quantity = Required(Quantity::from_units(quantity));
      const auto limit_price = Required(Price::from_units(price));
      if (!event_sequence || !order_id || !side || !order_quantity || !limit_price) {
        Error("invalid_ack_domain");
        continue;
      }
      const auto binding = risk->binding();
      const auto result = risk->apply(
          AccountEvent{*event_sequence, Timestamp::from_unix_nanoseconds(time), ingress,
                       AccountEventTruth::ModelDerived,
                       AccountOrderAcknowledged{*order_id, binding.trader_id, binding.contract_id,
                                                *side, *order_quantity, *limit_price}});
      if (!result) {
        Error(result.error().message);
      } else {
        std::cout << "APPLIED " << sequence << '\n';
      }
      continue;
    }
    if (command == "FILL") {
      std::uint64_t sequence = 0;
      std::uint64_t order = 0;
      std::string side_text;
      std::int64_t quantity = 0;
      std::int64_t price = 0;
      std::int64_t time = 0;
      if (!(input >> sequence >> order >> side_text >> quantity >> price >> time)) {
        Error("invalid_fill");
        continue;
      }
      const auto event_sequence = Required(SequenceNumber::from_value(sequence));
      const auto order_id = Required(pmm::core::OrderId::from_value(order));
      const auto side = ParseSide(side_text);
      const auto fill_quantity = Required(Quantity::from_units(quantity));
      const auto fill_price = Required(Price::from_units(price));
      if (!event_sequence || !order_id || !side || !fill_quantity || !fill_price) {
        Error("invalid_fill_domain");
        continue;
      }
      const auto binding = risk->binding();
      const auto result =
          risk->apply(AccountEvent{*event_sequence, Timestamp::from_unix_nanoseconds(time), 0,
                                   AccountEventTruth::ModelDerived,
                                   AccountFill{*order_id, binding.trader_id, binding.contract_id,
                                               *side, *fill_price, *fill_quantity}});
      if (!result) {
        Error(result.error().message);
      } else {
        std::cout << "APPLIED " << sequence << '\n';
      }
      continue;
    }
    if (command == "REJECT") {
      std::uint64_t sequence = 0;
      std::uint64_t ingress = 0;
      std::int64_t time = 0;
      if (!(input >> sequence >> ingress >> time)) {
        Error("invalid_reject");
        continue;
      }
      const auto event_sequence = Required(SequenceNumber::from_value(sequence));
      if (!event_sequence) {
        Error("invalid_reject_domain");
        continue;
      }
      const auto result =
          risk->apply(AccountEvent{*event_sequence, Timestamp::from_unix_nanoseconds(time), ingress,
                                   AccountEventTruth::ModelDerived, AccountCommandRejected{}});
      if (!result) {
        Error(result.error().message);
      } else {
        std::cout << "APPLIED " << sequence << '\n';
      }
      continue;
    }
    if (command == "CANCEL") {
      std::uint64_t sequence = 0;
      std::uint64_t order = 0;
      std::int64_t time = 0;
      if (!(input >> sequence >> order >> time)) {
        Error("invalid_cancel");
        continue;
      }
      const auto event_sequence = Required(SequenceNumber::from_value(sequence));
      const auto order_id = Required(pmm::core::OrderId::from_value(order));
      if (!event_sequence || !order_id) {
        Error("invalid_cancel_domain");
        continue;
      }
      const auto result = risk->apply(
          AccountEvent{*event_sequence, Timestamp::from_unix_nanoseconds(time), 0,
                       AccountEventTruth::ModelDerived, AccountCancellation{*order_id}});
      if (!result) {
        Error(result.error().message);
      } else {
        std::cout << "APPLIED " << sequence << '\n';
      }
      continue;
    }
    if (command == "VIEW") {
      PrintView(*risk);
      continue;
    }
    Error("unknown_command");
  }
  return 0;
}
