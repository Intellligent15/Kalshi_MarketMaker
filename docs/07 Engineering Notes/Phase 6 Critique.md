# Phase 6 critique and follow-up register

## Rating scale

- **1 — Low:** cosmetic or inexpensive to correct later.
- **2 — Limited:** useful simplification or optimization; does not constrain the next milestone.
- **3 — Moderate:** should be resolved within the next one or two milestones.
- **4 — High:** likely to cause rework, incorrect simulation behavior, or an unsafe boundary if ignored.
- **5 — Critical:** blocks a credible recovery, accounting, paper-trading, or live-trading claim.

This review evaluates the implemented deterministic, in-memory Phase 6 reference runtime. It does
not treat deliberately deferred production concerns as accidental defects; it records the work
needed before those concerns can be claimed as supported.

## Unnecessary complexity

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| `MarketMakingCoordinator` owns a depth/trade projection very similar to the private Phase 5 coordinator projection. | 2 | Two implementations can drift in event interpretation and best-price behavior. | Keep the proven local version for now; extract a shared, tested projection interface only when a second Phase 6 consumer needs it. |
| Every exchange event repeats its ingress sequence instead of introducing an explicit event-batch envelope. | 2 | Correlation is correct, but repetitive metadata obscures the command/batch relationship. | Retain the simple value event now; ADR a batch envelope with durable journaling and consumer APIs. |
| Phase 6 has separate `AccountId`, `StrategyId`, `TraderId`, and `ClientIntentId` despite supporting one binding. | 2 | The identities prevent future conflation, but increase fixture/configuration ceremony today. | Retain. The type safety is useful at the account/admission boundary. |
| Risk stores a detached live-order projection while the book already stores live order state. | 2 | This duplicates selected state, but it is required because the book must stay account/risk agnostic. | Retain and document it as an event-derived projection, not a second matching authority. |

## Future technical debt

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| Journal/event append is still in-memory and non-transactional with exchange mutation. | 5 | A process failure can lose history or leave state/history inconsistent. | ADR and implement prepared, versioned, checksummed command and event batches before recovery or paper-trading claims. |
| Price units still lack money, fee, collateral, margin, short-sale, and settlement semantics. | 5 | Quantity limits are not sufficient financial risk controls. | Define accounting and settlement policy before PnL, economic limits, or venue integration. |
| Checkpoints are detached C++ values with no schema version, configuration identity, checksum, or malformed-state validation. | 4 | An incompatible or corrupt continuation can silently diverge. | Add a configuration fingerprint, table-driven validation, and schema policy with durable snapshots. |
| One `AccountRiskProjection` serves one account/trader/strategy/contract binding. | 4 | It cannot enforce shared limits across strategies or correlated products. | Introduce central account aggregation before multi-strategy or portfolio risk. |
| Passive terminal state is reconstructed privately from fills and cancels rather than exposed by an exchange-owned order projection. | 4 | Gateways and independent risk consumers must each reproduce lifecycle inference. | Add an exchange terminal-order projection before public clients or paper trading. |
| Admission does not validate an intent against the contract grid itself; the exchange is the final validator. | 3 | Invalid external strategy intent temporarily reserves exposure before exchange rejection releases it. | Give admission a read-only contract/rule view when strategy APIs become public. |
| A replacement can be admitted in the same turn as a cancellation when old-plus-new exposure fits limits. | 3 | Safe but can temporarily create extra quote churn and exposure. | Keep it for the baseline; add an explicit replace policy or atomic venue primitive only after measuring churn. |
| A pending reservation is found by linear search over client intents using ingress sequence. | 2 | Correct for small deterministic runs but not ideal for large command bursts. | Add an ingress-to-client index only after profiling. |

## Missing tests

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| No malformed risk or market-maker checkpoint tests cover duplicate orders, mismatched bindings, invalid watermark, or duplicate client intent. | 4 | Restore is a deterministic safety boundary. | Add table-driven rejection tests before serializing checkpoints. |
| No randomized schedule combines fills, cancel/replace, lifecycle changes, post-only rejection, and checkpoint restore. | 4 | Interactions—not isolated scenarios—are most likely to expose projection/order bugs. | Add fixed-seed model or metamorphic schedules with exact decisions and event payload equality. |
| Market-maker checkpoint continuation compares selected event fields, not every payload field. | 3 | A trade price, quantity, or depth delta could diverge while sequence/variant still match. | Reuse the exchange event equality helper for full continuation comparisons. |
| Quote tests omit non-unit tick grids, contract boundaries, midpoint/last-trade references, short inventory skew, and simultaneous replacement limits. | 3 | Tick rounding and boundary safety are core quote behavior. | Add compact table-driven quote calculation cases. |
| No test proves an unadmitted direct command using the bound trader identity is detected by the risk projection. | 3 | The control boundary should fail closed if bypassed. | Add a negative projection test and preserve the coordinator-only production path. |
| No long-run test measures logical-time overflow, journal growth, or quote churn. | 2 | These are not likely in tiny fixtures but matter for experiments. | Add bounded stress fixtures with explicit size expectations. |

## Missing documentation

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| The public headers do not yet include field/unit/range tables for risk limits, quote age, and skew. | 3 | Users can misconfigure integer quantity and logical-time fields. | Add API tables and configuration examples before external strategy consumers. |
| There is no command-to-event correlation table showing acknowledgement, rejection, fill, cancellation, and reservation effects. | 3 | The central admission invariant is otherwise inferred from code. | Add a table to the public API documentation with the durable event work. |
| Checkpoint contents and omissions are not documented for risk/market-maker state. | 3 | A continuation value can be mistaken for a complete experiment artifact. | Document stored watermarks, live/pending orders, quote state, and excluded history/config identity. |
| Cancel-and-replace behavior does not state when simultaneous old/new exposure is allowed. | 2 | The implementation is safe but its temporary exposure tradeoff is not obvious. | Add this rule to the API policy table. |

## Possible optimizations

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| Best bid/ask is recomputed by scanning every projected level on each quote decision. | 3 | Cost grows with depth and decision frequency. | Maintain best-level caches only after a benchmark identifies it as material. |
| Risk admission repeatedly scans live and pending orders to aggregate exposure. | 3 | Multiple quotes per decision turn make small maps repeatedly expensive. | Maintain checked aggregate counters after invariant and randomized tests exist. |
| `read_events_after` copies full event values into each projection pass. | 3 | Long experiments repeatedly allocate/copy execution and depth payloads. | Add a non-owning cursor/batch view only with explicit retention semantics. |
| Exchange depth deltas still use full pre/post snapshots. | 3 | Quote-heavy workloads amplify the known Phase 4 baseline cost. | Benchmark, then consider book-provided changed-level reports without changing matching. |
| Reservation lookup by ingress is linear. | 2 | Only matters with many pending commands. | Profile before adding an index. |

## Future scalability concerns

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| The exchange and market-maker coordinator are single-threaded and serialize every contract/decision. | 4 | Throughput is bounded by one process loop. | Preserve the reference ordering; shard only after a new ADR defines ingress merge, watermarks, and recovery. |
| Event journal, checkpoints, decisions, and projections are retained in memory. | 5 | Long experiments eventually exhaust memory and have no recovery path. | Resolve durable retention and cursor/compaction semantics before broad backtests. |
| No cursor-gap, bounded queue, or slow-consumer contract exists. | 4 | Future asynchronous market data can silently lose ordering or block progress. | Define consumer offsets, overflow recovery, and backpressure before process isolation or gateways. |
| One-contract risk and one-contract market maker cannot model portfolio or linked-market exposure. | 4 | Prediction-market products often have related contracts. | Design a market/account aggregate before expanding products. |
| There is no latency, cancel acknowledgement delay, or venue gateway model. | 3 | Quoting performance conclusions would be overly optimistic. | Add an explicit deterministic latency model before performance claims. |

## Deliberate boundaries retained

- `LimitOrderBook` remains single-writer and owns live matching state only.
- `ExchangeSimulator` remains the sole production caller of the book and owns lifecycle, IDs,
  event sequencing, replay, and in-memory checkpoints.
- Risk/inventory/PnL/persistence/market-data fanout remain outside the book.
- Cancel-and-replace preserves Phase 3 priority semantics; no amend/replace was added.
- Fixed periodic quoting is the deterministic baseline; event-triggered repricing is deferred.
- No concurrency, wall-clock time, floating-point price arithmetic, or uncontrolled randomness was
  introduced in deterministic paths.

## Prioritized follow-up

Priority balances impact with implementation effort and the value of making the system easier to
reason about. The first two rows are prerequisite design work for credible recovery or economic
risk claims; they are not claims made by Phase 6.

| Priority | Work | Impact | Effort | Why now |
| ---: | --- | ---: | --- | --- |
| 1 | Define durable prepared command/event batches, snapshot schemas, and recovery invariants. | 5 | High | Resolves the core state-versus-history correctness debt. |
| 2 | Define money, fees, collateral, settlement, and account accounting. | 5 | High | Required before PnL, financial risk, paper trading, or gateways. |
| 3 | Add malformed-checkpoint, randomized interaction, and full-payload continuation tests. | 4 | Low | Strongly improves confidence before expanding behavior. |
| 4 | Document risk/quote units, checkpoint omissions, and command-to-event effects. | 3 | Low | Makes the current safe baseline easier to use correctly. |
| 5 | Design central multi-strategy, multi-contract account aggregation. | 4 | Medium | Prevents a local API from becoming a future portfolio-risk dead end. |
| 6 | Define cursor gaps, retention, and consumer backpressure. | 4 | Medium | Required before asynchronous fanout or long experiments. |
| 7 | Benchmark projections, risk aggregation, queue insertion, and snapshot deltas. | 3 | Low | Supplies evidence before optimization or sharding. |
