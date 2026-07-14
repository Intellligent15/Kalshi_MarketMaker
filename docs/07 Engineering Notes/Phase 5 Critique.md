# Phase 5 critique and follow-up register

## Rating scale

- **1 — Low:** cosmetic or inexpensive to correct later.
- **2 — Limited:** useful improvement, but does not constrain the next milestone.
- **3 — Moderate:** should be resolved during the next one or two milestones.
- **4 — High:** likely to cause rework or incorrect behavior if ignored.
- **5 — Critical:** blocks a safe, credible implementation of the roadmap.

This review evaluates the Phase 5 reference runtime, not a production trading platform. Its
single-threaded coordinator, in-memory event reading, and intentionally small strategies are
correctness baselines. The register separates those deliberate bounds from debt that must shape
future work.

## Unnecessary complexity

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| The coordinator has a scheduling loop in addition to the exchange command queue. | 2 | Both are necessary ownership boundaries, but two timelines are harder to explain than one. | Retain; document coordinator phases and avoid another queue abstraction until a real latency model needs one. |
| Restore rebuilds initial projections from exchange snapshots before replacing them with saved projection state. | 2 | Correct but performs work that a large checkpoint restore does not need. | Keep as a clear baseline; add a private restore construction path only after profiling. |
| `AgentIntent` currently embeds a `SubmitOrderRequest`, including `TraderId`. | 3 | Today only built-in agents construct intents, but a future plug-in strategy could impersonate another identity. | Replace with an identity-free order intent before extensible strategy APIs; let admission bind `TraderId`. |
| The coordinator records every decision even when the agent emits no intent. | 2 | This is excellent for auditability but grows memory with every scheduled turn. | Keep for small experiments; make retention/export a deliberate later policy. |

## Future technical debt

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| Phase 4 still has no durable, transactional command/event journal. | 5 | State may diverge from history on failure and process exit loses audit/recovery data. | Design prepared execution, versioned checksummed storage, and atomic event-batch recovery before claiming durable replay or paper trading. |
| Agent output has no account, risk, outstanding-exposure, inventory, or collateral gate. | 4 | Baselines can submit unlimited exposure; `TraderId` is identity only. | Add an external event-fed inventory/risk admission boundary before Phase 6 market making. |
| Passive terminal order state is still not an exchange-owned projection. | 4 | An agent, risk service, or gateway must reconstruct passive status from fills. | Add a terminal-order projection or explicit passive outcomes at the exchange boundary. |
| Coordinator checkpoints lack schema versioning and thorough validation. | 4 | Corrupt or incompatible agent IDs, projections, timestamps, and RNG state can silently create a different continuation. | Add a versioned checkpoint schema and table-driven validation with the Phase 4 durability work. |
| There is no versioned experiment configuration or result artifact. | 3 | A C++ fixture is reproducible for tests but not a complete research experiment definition. | Introduce explicit config files, provenance, metrics, and seed recording before broad synthetic studies. |
| Baseline strategies have no latency, cancel/replace behavior, private order-state model, fees, or PnL. | 3 | They are useful flow generators but not credible trading-performance baselines. | Keep Phase 5 narrow; add these only with risk/inventory and Phase 6 requirements. |
| Agent replay is exercised through deterministic reruns and checkpoint continuation, not a first-class coordinator replay API. | 3 | Consumers can reproduce a run, but the API does not yet package inputs, outputs, and expected audit records as one artifact. | Add an experiment runner/replay envelope after durable journal semantics are defined. |

## Missing tests

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| No malformed coordinator-checkpoint tests cover duplicate agents, missing projections, invalid RNG state, or incompatible configuration. | 4 | Restore is a deterministic-continuation boundary. | Add table-driven rejection tests before persisting checkpoints. |
| No randomized multi-agent schedules combine lifecycle changes, rejections, checkpoint restore, and full replay equality. | 4 | Ordering bugs emerge from interactions rather than one agent at a time. | Add fixed-seed model/metamorphic tests with exact decision and event comparison. |
| No test proves that adding an unrelated agent leaves an existing agent's PRNG stream unchanged. | 3 | Per-agent seed derivation is a core reproducibility promise. | Compare one-agent and two-agent runs for the shared agent. |
| Agent admission/rejection and ownership attribution are untested because the risk/account boundary does not exist. | 4 | This will be the first safety-critical agent integration. | Add tests with the future admission interface, not an ad hoc Phase 5 bypass. |
| Signal tests cover the primary branches but not threshold boundaries, empty/deleted depth levels, or long logical-time overflow. | 2 | These are low-frequency but important deterministic edges. | Add compact table-driven cases in the next test pass. |

## Missing documentation

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| The public header has no full agent input/visibility table. | 3 | Future strategies need a precise statement that Phase 5 sees public depth/trades and has no private order-state service. | Add an API table before external strategies are introduced. |
| Configuration field units and signal formulas are only described informally. | 3 | A user can confuse logical nanoseconds, integer price units, and thresholds. | Document each `AgentConfig` field with units, valid ranges, and baseline formula examples. |
| No complexity/memory table covers event copies, projection scans, decision records, or checkpoints. | 2 | The baseline is intentionally simple but its costs are invisible. | Add it with the first reproducible benchmark. |
| The checkpoint documentation does not yet list all coordinator omissions, such as decision history and external configuration identity. | 3 | A checkpoint can be mistaken for a complete experiment artifact. | Add a contents/omissions table with the future versioned schema. |

## Possible optimizations

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| Finding best bid/ask scans every projected level on every agent turn. | 3 | Work grows with active depth and number of agents. | Maintain best-level caches after benchmarks demonstrate a bottleneck. |
| `read_events_after` copies event values into a vector before projection. | 3 | Long runs repeatedly copy trade, fill, and depth payloads. | Add a non-owning cursor or batched view only after retention semantics are designed. |
| Decision and event journals retain unbounded vectors. | 3 | Memory grows with simulation duration. | Design cursor-aware export/compaction with durable storage and consumer offsets. |
| Exchange scheduled-command insertion remains `O(Q)` vector insertion. | 3 | Large synthetic workloads can spend material time shifting commands. | Benchmark timestamp distributions; consider a heap/calendar queue while preserving `(time, ingress)` order. |

## Future scalability concerns

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| One coordinator and one exchange event loop serialize all contracts and agents. | 4 | Throughput is bounded by one core. | Preserve this reference model; only shard after a new ADR defines global ingress/event merge and recovery semantics. |
| Global event history and per-contract projections live in process memory. | 4 | Long runs and broad market universes amplify memory pressure. | Resolve durable retention first, then measure market count/depth workloads. |
| There are no subscriptions, bounded queues, or slow-consumer policy. | 4 | Future strategy/gateway fanout can block matching or lose ordered data silently. | Add sequenced cursors and explicit overflow/recovery policy before asynchronous consumers. |
| The one-contract binary market model constrains cross-market agents and correlated products. | 4 | Multi-contract products alter lifecycle, risk, and market-data assumptions. | Preserve the model through Phase 6; ADR a market aggregate before product expansion. |
| Independent agent processes would need deterministic transport, watermark, and failure contracts. | 3 | Naive process isolation breaks replayability. | Defer process boundaries until a serialized durable journal exists. |

## Prioritized follow-up

Priority balances impact with the effort needed to make the system easier to reason about.

| Priority | Work | Impact | Effort | Why now |
| ---: | --- | ---: | --- | --- |
| 1 | Add malformed coordinator-checkpoint, multi-agent fixed-seed, and PRNG-isolation tests. | 4 | Low | Validates the new deterministic contract before more behavior is layered on it. |
| 2 | Document public inputs, configuration units, and checkpoint omissions. | 3 | Low | Makes the baseline understandable and safe to use in experiments. |
| 3 | Design external account, inventory, and risk admission. | 4 | Medium | Required before inventory-aware market making; must remain outside the book. |
| 4 | ADR durable journal and atomic event-batch recovery. | 5 | Medium | Resolves the central state/history correctness debt before durable or paper-trading claims. |
| 5 | Implement durable recovery, versioned checkpoints, and fault injection. | 5 | High | Turns the current in-memory continuation model into a credible recovery boundary. |
| 6 | Add experiment configs, metrics, and benchmark baselines. | 3 | Medium | Makes synthetic research inspectable before optimizing. |
| 7 | Optimize projections, queues, retention, or sharding only with measurement. | 3–4 | High | Avoids obscuring the correct reference model prematurely. |
