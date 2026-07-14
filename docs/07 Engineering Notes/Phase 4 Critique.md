# Phase 4 critique and follow-up register

## Rating scale

- **1 — Low:** cosmetic or inexpensive to correct later.
- **2 — Limited:** worth improving, but does not constrain the next milestone.
- **3 — Moderate:** should be resolved during the next one or two milestones.
- **4 — High:** likely to cause rework or incorrect behavior if ignored.
- **5 — Critical:** blocks a safe, credible implementation of the roadmap.

This review evaluates the implemented Phase 4 reference exchange, not an idealized production
venue. Its single-threaded event loop, in-memory journal, and snapshot comparison are deliberate
correctness baselines. The register distinguishes those bounded choices from debt that must drive
the next design work.

## Unnecessary complexity

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| `ExchangeSequencer` is a separate heap-owned object solely to keep the book's injected `ExecutionIdSource` reference stable when the simulator moves. | 2 | The lifetime fix is correct, but it adds indirection and move-only implementation detail to a small simulator. | Retain it. Revisit only if an exchange object becomes non-movable or the ID service becomes a broader explicit dependency. |
| Checkpoint restore creates an empty simulator, then replaces every empty book with a restored book. | 2 | It is simple and correct, but constructs temporary ladders and makes restore less direct. | Keep until profiling or durable recovery makes restore cost material; then add a private construction path. |
| The exchange maintains both a market map and a contract-to-market routing map. | 1 | The second map is small and keeps routing explicit, but duplicates identity relationships already present in `Market`. | Retain for clear contract routing. Reconsider only if a future multi-contract market aggregate changes the model. |
| The Phase 3 virtual `ExecutionIdSource` returns an allocating vector for every crossing command. | 2 | It now has a real exchange consumer, but remains more machinery than a single in-memory simulator strictly needs. | Retain until benchmarks show allocation cost; consider a caller-owned small buffer or reserved range object only with evidence. |

## Future technical debt

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| Durable exchange persistence has no compaction, cross-process locking, replication, or coordinator-level recovery. | 3 | The new local store protects exchange command/event batches and snapshots, but long runs and broader runtime recovery still need retention and ownership decisions. | Keep the bounded local store as the Phase 7 foundation; ADR retention/compaction and higher-layer checkpoint identity before long-running or multi-process work. |
| The default exchange remains in-memory and durable checkpoints require an empty command queue. | 3 | This keeps queued inputs from being duplicated during recovery, but callers need an explicit checkpoint boundary. | Preserve the fail-closed contract; add a durable pending-command format only with a new recovery proof and tests. |
| Replay reprocesses commands but does not automatically compare full event payloads against a recorded expected stream. | 4 | Sequence and variant shape can match while a price, quantity, fill owner, status, or depth delta differs. | Add a canonical event equality/serialization form and an assertion mode that compares every field during replay tests. |
| `OrderOutcome` describes only the incoming order. Passive orders change through fills but have no explicit final-status event or queryable terminal-order projection. | 4 | Client order-status, audit, and risk consumers otherwise reconstruct state from fills and accepted orders. | Define an exchange-owned terminal order projection or explicit passive `OrderOutcome` events before gateways, agents, or paper trading. |
| Lifecycle state has no scheduled open/pre-open phase, close reason, halt reason, auction policy, or settlement accounting. | 4 | Current transitions gate matching, but they do not model a complete prediction-market lifecycle. | Keep the current finite-state machine for simulation; define product/lifecycle semantics before auctions, settlement, or live integration. |
| There is no risk gate, account model, inventory projection, fee model, or collateral policy in the command path. | 4 | The exchange can admit unlimited exposure and `TraderId` is only a test identity, not authorization. | Add a separate, event-fed risk/inventory boundary before market-making agents or paper trading; do not place it in the book. |
| Detached in-memory checkpoints still have no public schema/version contract, although the opt-in on-disk exchange checkpoint is versioned and checksummed. | 3 | Direct C++ continuation values remain process-local and higher-layer checkpoints lack configuration identity. | Keep rejecting unknown durable exchange versions; add configuration fingerprints and higher-layer schemas before durable coordinator recovery. |
| Event retention is unbounded in vectors. | 3 | Long simulations consume memory proportional to every command and event. | Add cursor-aware retention/compaction only after durable storage and consumer semantics are defined. |

## Missing tests

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| Replay tests compare sequence, time, and variant index, not complete event payloads. | 4 | They do not prove exact replay of trades, fills, order states, or depth deltas. | Add event equality fixtures and compare every payload field, including vector order. |
| No malformed-checkpoint tests cover duplicate live IDs, wrong-contract orders, zero/invalid counters, invalid priority, or unsorted pending commands. | 4 | Restore is a recovery boundary and currently has only a successful-path test. | Add table-driven invalid checkpoint tests and assert no partially restored exchange escapes. |
| No checkpoint test restores queued commands with equal timestamps and preserved ingress order. | 4 | This is the key deterministic-recovery tie-break guarantee. | Snapshot with pending mixed-time commands, restore, run, and compare the exact event stream. |
| No event-batch failure/exhaustion tests exist. | 4 | The known state/journal atomicity limitation is neither demonstrated nor bounded by tests. | Add injectable journal/sequence failure tests when prepared execution is designed. |
| Lifecycle tests omit halt/cancel behavior, invalid transitions, settlement rejection, and close ordering across several live orders. | 3 | The basic close path works, but the lifecycle contract is under-specified at its boundaries. | Add table-driven transition and deterministic cancel-order tests. |
| Global-ID coverage has one trade on one contract and only a resting order on the other. | 3 | It does not prove interleaved trade IDs and event sequences across multiple books. | Match on two contracts in one logical time batch and assert the combined order. |
| Randomized testing validates the book, but not random simulator schedules, lifecycle changes, event batches, or checkpoint/replay equivalence. | 3 | Exchange-level ordering bugs need a model or metamorphic test layer too. | Add fixed-seed simulator schedule tests with replay equality and lifecycle invariants. |
| No tests cover slow consumers, cursor gaps, or retention because no consumer queue exists yet. | 2 | This is intentionally outside the initial in-memory journal, but must precede asynchronous fanout. | Add them with the cursor/queue API, not prematurely. |

## Missing documentation

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| The public header lacks a concise event table that states recipient visibility, payload, and exact sequence relationship for every event variant. | 4 | Strategy, market-data, and future gateway code must not infer semantics from a `std::variant`. | Add an API event-contract table before adding another consumer. |
| `submitted_at`, `scheduled_at`, `occurred_at`, and `Trade::executed_at` are not documented together in one time-policy contract. | 4 | Replay and latency modeling can silently conflate client intent, exchange arrival, and matching time. | Add a time-and-ordering section with examples and prohibit wall-clock use in deterministic paths. |
| Snapshot/replay documentation does not state what is intentionally omitted: prior emitted events, terminal order history, consumer offsets, and durability guarantees. | 3 | Users could mistake an in-memory checkpoint for a complete recovery artifact. | Add an explicit checkpoint contents/omissions table. |
| Market-data delta ordering and removal representation (`quantity == 0`, `order_count == 0`) are not documented as a consumer contract. | 3 | A consumer can apply a removal incorrectly or assume bid ordering. | Document side/price sort order, final-state semantics, and zero-quantity removal records. |
| No performance/memory complexity table exists for queue insertion, full-snapshot delta generation, journals, or checkpoint creation. | 2 | The implementation is intentionally simple, but its costs are invisible to users. | Add after the first Phase 4 benchmark. |

## Possible optimizations

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| Every mutation creates full pre/post book snapshots and temporary ordered maps to form depth deltas. | 3 | Cost grows with configured price levels even when one level changes. | Have the book return a detached changed-level summary, then benchmark before replacing the correct baseline. |
| The scheduled command queue is a sorted `std::vector`; insertion shifts later commands. | 3 | Large synthetic/historical workloads turn enqueue into `O(Q)`. | Benchmark timestamp distributions; then consider a binary heap or calendar queue while preserving `(time, ingress)` order. |
| Events, commands, checkpoints, and event reads copy value-heavy payloads. | 3 | Long runs allocate and copy orders, trades, fills, and depth vectors repeatedly. | Keep values for audit clarity now; consider move-aware cursors, arenas, or serialized frames after profiling. |
| Market and contract lookups use ordered maps. | 1 | This favors deterministic traversal and tiny registries, but is not the fastest routing path. | Retain until market counts warrant benchmark-backed alternatives. |
| Invariant validation walks every level and live order. | 1 | It is intentionally expensive and test-only diagnostic work. | Keep out of production hot loops; run in randomized/debug tests. |

## Future scalability concerns

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| One global event loop serializes all markets. | 4 | It is deterministic and correct, but aggregate throughput eventually scales with one core. | Preserve it as the reference model. Consider instrument shards only after benchmarks and a new ADR defines global-log merge semantics. |
| A future shard model must preserve global ingress/event order while books execute independently. | 5 | Naive per-book queues make cross-contract replay, lifecycle commands, and consumers nondeterministic. | Keep a global ingress journal and sequencer; define shard watermark, merge, and recovery rules before parallelism. |
| The dense ladder's 4,096-level guard plus full snapshots can become memory/cache heavy across many contracts. | 3 | A broad contract universe multiplies empty ladder allocation and snapshot work. | Measure realistic grids and active-market counts before choosing sparse books or a different snapshot policy. |
| The event model has no consumer flow control, subscriptions, or isolation boundary. | 4 | A real market-data/strategy fanout must not let slow consumers block matching or lose ordering silently. | Add sequenced cursors and bounded queues with explicit overflow/recovery policy before agents or gateways. |
| One binary contract per market constrains multi-outcome and linked-market products. | 4 | Product expansion will change routing, lifecycle, risk, and settlement assumptions. | Preserve the current model through baseline simulation; design a multi-contract market aggregate before expansion. |

## Prioritized next work

Priority combines impact with the effort needed to reduce uncertainty. Do the small contract and
test improvements first, then the durability boundary before strategy or paper-trading work.

| Priority | Work | Impact | Effort | Why now |
| ---: | --- | ---: | --- | --- |
| 1 | Define event/time/lifecycle contract tables and add complete event payload equality. | 4 | Low | Makes every later consumer and replay test unambiguous. |
| 2 | Add malformed checkpoint, pending-queue restore, lifecycle-boundary, and multi-book trade tests. | 4 | Low | Closes the most important untested deterministic paths before architecture expands. |
| 3 | Add interrupted-write, prepared-command, and durable pending-queue fault injection. | 4 | Medium | Extends the completed local durability proof to crash-window cases. |
| 4 | Define retention/compaction and higher-layer checkpoint identity. | 4 | Medium | Required before long backtests, coordinator recovery, or broader runtime claims. |
| 5 | Add an external risk-gate and event-fed inventory projection interface. | 4 | Medium | Required before autonomous agents can safely submit orders. |
| 6 | Benchmark queue insertion, snapshot/delta work, memory, and book workloads. | 3 | Low | Supplies evidence before optimizing or sharding. |
| 7 | Replace snapshot-diff deltas and consider instrument sharding only if benchmarks require it. | 3–5 | High | Avoids premature performance complexity while preserving a clear scale path. |
