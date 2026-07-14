# Phase 2 critique and follow-up register

## Rating scale

- **1 — Low:** cosmetic or inexpensive to correct later.
- **2 — Limited:** worth improving, but does not constrain the next milestone.
- **3 — Moderate:** should be resolved during the next one or two milestones.
- **4 — High:** likely to cause rework or incorrect behavior if ignored.
- **5 — Critical:** blocks a safe, credible implementation of the roadmap.

This is an intentional critique of the implemented Phase 2 work, not a claim that these items
should all be solved before Phase 3. The goal is to make tradeoffs visible.

## Unnecessary complexity

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| Project-owned `Result<T>` wrapper | 2 | It duplicates a facility expected in modern C++ and can be misused by calling `value()` or `error()` on the wrong state. | Retain it for C++20 now; evaluate C++23 `std::expected` or a mature equivalent only when the language baseline changes. |
| `MarketStatus` exists without a separate mutable market-state model | 1 | The enum is harmless, but it is not yet backed by lifecycle transitions. | Keep it as descriptive metadata; do not add transitions until settlement and exchange state are designed. |
| Aggregate header `pmm/core/core.hpp` | 1 | Convenient today, but it can eventually increase compile times and hide dependencies. | Keep it as an optional convenience header; production code should include precise headers as the project grows. |

## Future technical debt

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| Price units have no explicit currency, scale, or collateral semantics | 4 | A price of `63` is clear in a toy binary market but ambiguous across venues, currencies, and payout conventions. PnL and live gateways need precise monetary meaning. | Define a money/payout/collateral model before PnL, fees, or exchange integration; do not silently reinterpret `Price`. |
| One binary contract per market | 4 | This is correct for the current narrow model but does not directly represent multi-outcome markets, linked contracts, or more complex settlement structures. | Keep the restriction through the first order book; design a multi-contract market aggregate before expanding product scope. |
| ID generation, persistence, and external-ID mapping are unspecified | 3 | In-memory numeric IDs are fast, but replay, restarts, and live exchange adapters need stable identity rules. | Specify ID ownership and venue-string mapping with the simulator or gateway design. |
| Market status is stored with static definitions | 3 | Open/halted/settled state will change independently from contract metadata. | Introduce immutable `MarketDefinition` plus sequenced `MarketState` snapshots when simulator events are designed. |
| `Result<T>` stores formatted strings in every error | 2 | Error paths may allocate and messages are not structured for machine handling. | Add structured context only when diagnostics need it; keep the successful hot path allocation-free. |

## Missing tests

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| No boundary/overflow tests for signed position arithmetic | 4 | Large fills could overflow a signed position; the code has checks but they are not proven by tests. | Add targeted boundary tests once test-only construction or a checked quantity helper is available. |
| No duplicate-fill or replay-idempotency policy | 4 | Replaying the same fill twice would currently change inventory twice. Historical replay and live reconnection require an explicit policy. | Decide whether the event stream guarantees exactly-once delivery or inventory records processed trade/fill IDs before Phase 4. |
| No property-based tests for grids, lots, and position updates | 3 | Example tests miss combinations of boundaries and increments. | Add deterministic property/fuzz tests after the basic order-book behavior is stable. |
| No tests for order-state transitions | 2 | This is intentionally absent because order state belongs to Phase 3. | Add lifecycle, partial-fill, cancellation, and priority tests with the order-book design. |

## Missing documentation

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| No formal definition of price units, payout, cash settlement, collateral, or short-sale rules | 4 | These terms determine financial correctness and risk exposure. | Write a market-microstructure note before PnL or risk-engine work. |
| No public API usage examples | 2 | New contributors must infer factory and `Result<T>` use from tests. | Add one small documented example when the order-book API is introduced. |
| No event sequencing/replay contract | 3 | Deterministic replay needs a clear source of sequence numbers and ordering guarantees. | Document it in the simulator design before Phase 4. |

## Possible optimizations

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| `Inventory` uses `std::map` | 2 | It provides deterministic ordering but has logarithmic lookup and node allocations. | Benchmark realistic position counts first; consider a flat sorted container or hash map only with evidence. |
| Error strings and `std::variant` in `Result<T>` | 2 | Errors may allocate; variant adds a small representation cost. | Do nothing unless profiling shows validation/error handling is material. |
| `Market` titles allocate strings | 1 | Metadata is not a matching hot path. | Do not optimize prematurely; intern or share metadata only if profiling justifies it. |

## Future scalability concerns

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| No event log, snapshot, or persistence boundary | 5 | Replay, recovery, audit, historical research, and live integration all depend on durable ordered events. | Make event ordering and replayability a first-class Phase 4 design deliverable. |
| Single-contract market representation | 4 | Product breadth will be constrained as soon as multi-outcome or linked products are introduced. | Keep the current scope but define an extension path before expanding products. |
| Inventory has no risk limits or account partitioning | 4 | A future market maker needs per-strategy/account limits, outstanding-order exposure, and kill-switch behavior. | Design inventory snapshots and a separate risk engine before any paper or live trading. |
| Numeric IDs only exist in-process | 3 | Distributed/restarted systems need durable, collision-free identity and mapping rules. | Address with persistence and gateway architecture, not by prematurely switching to strings now. |

## Recommended milestone

**Phase 3A: Order-book and matching design review.** Do not begin with a data structure. First
write ADR-003 defining:

1. Order lifecycle states and valid transitions.
2. Ownership of remaining quantity, cumulative fills, cancellation state, and priority sequence.
3. Price-time priority, including exact tie-breaking.
4. Market-order behavior when there is insufficient liquidity.
5. Partial-fill, cancellation, self-trade, and duplicate-event policy.
6. The event sequence emitted by add, cancel, match, trade, and fill operations.
7. Test scenarios and invariants before implementation.

After that review is approved, implement the smallest limit-order book in stages: add/cancel first,
then crossing/matching, then partial fills and comprehensive invariant tests. This directly follows
the charter's correctness-before-optimization philosophy and resolves the highest Phase 2 risks at
the right time.
