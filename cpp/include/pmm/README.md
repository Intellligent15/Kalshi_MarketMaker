# Public C++ headers

This directory contains stable, project-owned C++ interfaces. The Phase 2 core domain model is
available through `pmm/core/core.hpp`; the Phase 3 limit order book is available through
`pmm/book/order_book.hpp`; and the Phase 4 exchange boundary is available through
`pmm/sim/exchange_simulator.hpp`. Phase 5 baseline agents are available through
`pmm/agents/baseline_agents.hpp`. The book owns mutable matching state only. The simulator owns
event ordering, lifecycle, IDs, in-memory journals, checkpoints, and replay; the agent
coordinator owns schedules and projections. Risk, inventory, durable persistence, and gateways
remain separate layers. Phase 6 adds `pmm/risk/account_risk.hpp` for external account exposure
and command admission plus `pmm/market_maker/market_maker.hpp` for deterministic passive quoting.
The market maker cannot mutate a book, and its identity-free order intent receives the exchange
`TraderId` only after risk admission.

```cpp
auto exchange = pmm::sim::ExchangeSimulator::create({market});
exchange.value().enqueue(submit_request, pmm::core::Timestamp::from_unix_nanoseconds(100));
exchange.value().run_until(pmm::core::Timestamp::from_unix_nanoseconds(100));
for (const auto& event : exchange.value().events()) {
  // Consume immutable, globally sequenced exchange events.
}
```

`enqueue` is the only normal path to matching. The caller owns command construction and consumes
results through the journal; it never calls a contract book directly.
