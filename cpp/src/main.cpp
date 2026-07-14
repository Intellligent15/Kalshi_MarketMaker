#include <algorithm>
#include <charconv>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "pmm/market_maker/market_maker.hpp"

namespace {

using pmm::core::Contract;
using pmm::core::ContractId;
using pmm::core::Market;
using pmm::core::MarketId;
using pmm::core::Price;
using pmm::core::PriceGrid;
using pmm::core::Quantity;
using pmm::core::Result;
using pmm::core::Side;
using pmm::core::Timestamp;
using pmm::core::TraderId;

template <typename T>
T Require(Result<T> result) {
  if (!result) {
    std::cerr << "demo setup failed: " << result.error().message << '\n';
    std::exit(1);
  }
  return std::move(result).value();
}

void Require(Result<void> result) {
  if (!result) {
    std::cerr << "demo simulation failed: " << result.error().message << '\n';
    std::exit(1);
  }
}

void PrintUsage(std::ostream& output) {
  output << "Usage: pmm_demo [--steps <positive integer>]\n"
         << "Runs a deterministic market-maker simulation and prints quotes, fills, inventory,\n"
         << "risk admission, and displayed depth at each logical decision turn.\n";
}

std::optional<std::uint64_t> ParseSteps(int argc, char** argv) {
  std::uint64_t steps = 5;
  for (int index = 1; index < argc; ++index) {
    const std::string_view argument(argv[index]);
    if (argument == "--help") {
      PrintUsage(std::cout);
      return std::nullopt;
    }
    if (argument != "--steps" || index + 1 >= argc) {
      PrintUsage(std::cerr);
      std::exit(2);
    }
    const std::string_view value(argv[++index]);
    const auto parsed = std::from_chars(value.data(), value.data() + value.size(), steps);
    if (parsed.ec != std::errc{} || parsed.ptr != value.data() + value.size() || steps == 0) {
      std::cerr << "--steps must be a positive integer\n";
      std::exit(2);
    }
  }
  return steps;
}

Market MakeMarket() {
  const MarketId market_id = Require(MarketId::from_value(1));
  const ContractId contract_id = Require(ContractId::from_value(10));
  const PriceGrid grid =
      Require(PriceGrid::create(Require(Price::from_units(1)), Require(Price::from_units(99)),
                                Require(Price::from_units(1))));
  const Contract contract =
      Require(Contract::create(contract_id, market_id, Require(Price::from_units(100)), grid,
                               Require(pmm::core::LotSize::from_units(1))));
  return Require(Market::create(market_id, "Will the demo event resolve YES?", contract));
}

pmm::market_maker::MarketMakerConfig MakeConfig(ContractId contract_id) {
  return pmm::market_maker::MarketMakerConfig{
      pmm::risk::AccountBinding{Require(pmm::risk::AccountId::from_value(1)),
                                Require(pmm::risk::StrategyId::from_value(1)),
                                Require(TraderId::from_value(100)), contract_id},
      pmm::risk::RiskLimits{Require(Quantity::from_units(1)), Require(Quantity::from_units(4)),
                            Require(Quantity::from_units(4)), Require(Quantity::from_units(4)),
                            Require(Quantity::from_units(4)), 4},
      Timestamp::from_unix_nanoseconds(10),
      10,
      Require(Quantity::from_units(1)),
      Require(Price::from_units(50)),
      pmm::market_maker::ReferencePriceSource::Configured,
      2,
      2,
      2,
      30};
}

void PrintDepth(const pmm::book::BookSnapshot& snapshot) {
  const auto print_side = [](std::string_view name,
                             const std::vector<pmm::book::PriceLevelView>& levels) {
    std::cout << "  " << name << ":";
    if (levels.empty()) {
      std::cout << " empty\n";
      return;
    }
    for (const auto& level : levels) {
      std::cout << ' ' << level.price.units() << 'x' << level.total_quantity.units();
    }
    std::cout << '\n';
  };
  print_side("bids", snapshot.bids);
  print_side("asks", snapshot.asks);
}

void PrintEvents(const std::vector<pmm::sim::ExchangeEvent>& events, std::uint64_t* watermark) {
  for (const auto& event : events) {
    if (event.sequence.value() <= *watermark) {
      continue;
    }
    if (const auto* trade = std::get_if<pmm::sim::TradeExecuted>(&event.payload)) {
      std::cout << "  fill: " << trade->execution.trade.quantity().units() << " at "
                << trade->execution.trade.price().units() << " (buyer "
                << trade->execution.trade.buyer_trader_id().value() << ", seller "
                << trade->execution.trade.seller_trader_id().value() << ")\n";
    } else if (const auto* rejected = std::get_if<pmm::sim::CommandRejected>(&event.payload)) {
      std::cout << "  exchange rejection: " << rejected->error.message << '\n';
    }
    *watermark = event.sequence.value();
  }
}

void PrintDecision(const pmm::market_maker::QuoteDecisionRecord& decision) {
  const std::size_t approved = static_cast<std::size_t>(std::count_if(
      decision.admissions.begin(), decision.admissions.end(),
      [](const pmm::risk::AdmissionDecision& admission) { return admission.approved(); }));
  std::cout << "  quote: bid "
            << (decision.bid_price.has_value() ? std::to_string(decision.bid_price->units())
                                               : "off")
            << ", ask "
            << (decision.ask_price.has_value() ? std::to_string(decision.ask_price->units())
                                               : "off")
            << "; admission approved/rejected " << approved << '/'
            << decision.admissions.size() - approved << ", cancels "
            << decision.cancellations.size() << '\n';
}

}  // namespace

int main(int argc, char** argv) {
  const std::optional<std::uint64_t> steps = ParseSteps(argc, argv);
  if (!steps.has_value()) {
    return 0;
  }
  if (*steps > 1000) {
    std::cerr << "--steps must not exceed 1000 for the interactive demo\n";
    return 2;
  }

  const Market market = MakeMarket();
  pmm::market_maker::MarketMakingCoordinator coordinator =
      Require(pmm::market_maker::MarketMakingCoordinator::create(
          {market}, MakeConfig(market.contract().id())));
  const auto external_order = [&market](std::uint64_t trader, Side side, std::int64_t price,
                                        std::int64_t time) {
    return pmm::sim::SubmitOrderRequest{Require(TraderId::from_value(trader)),
                                        market.contract().id(),
                                        side,
                                        pmm::core::OrderType::Limit,
                                        Require(Quantity::from_units(1)),
                                        Require(Price::from_units(price)),
                                        Timestamp::from_unix_nanoseconds(time)};
  };
  Require(coordinator.enqueue_external(external_order(201, Side::Sell, 48, 15),
                                       Timestamp::from_unix_nanoseconds(15)));
  Require(coordinator.enqueue_external(external_order(202, Side::Buy, 52, 25),
                                       Timestamp::from_unix_nanoseconds(25)));
  Require(coordinator.enqueue_external(external_order(203, Side::Sell, 48, 35),
                                       Timestamp::from_unix_nanoseconds(35)));
  Require(coordinator.enqueue_external(external_order(204, Side::Buy, 52, 45),
                                       Timestamp::from_unix_nanoseconds(45)));

  std::cout
      << "Prediction Market ML Market Maker demo\n"
      << "Scenario: a passive maker quotes around 50 while external traders alternately hit it.\n";
  std::uint64_t event_watermark = 0;
  std::size_t decision_count = 0;
  for (std::uint64_t step = 1; step <= *steps; ++step) {
    const std::int64_t time = static_cast<std::int64_t>(step * 10U);
    Require(coordinator.run_until(Timestamp::from_unix_nanoseconds(time)));
    std::cout << "\nt=" << time << "\n";
    PrintEvents(coordinator.exchange().events(), &event_watermark);
    while (decision_count < coordinator.decisions().size()) {
      PrintDecision(coordinator.decisions()[decision_count++]);
    }
    const pmm::risk::AccountRiskView risk = coordinator.risk().view();
    std::cout << "  inventory: " << risk.net_position << "; open buy/sell "
              << risk.open_buy_quantity.units() << '/' << risk.open_sell_quantity.units()
              << "; pending buy/sell " << risk.pending_buy_quantity.units() << '/'
              << risk.pending_sell_quantity.units() << '\n';
    PrintDepth(Require(coordinator.exchange().snapshot(market.contract().id(), 5)));
  }
  return 0;
}
