# Phase 7 Critique

## Rating method

Impact is rated from 1 (minor) to 5 (blocks credible research or creates a material correctness risk). Ease is rated from 1 (large architectural effort) to 5 (small, well-contained change). Priority orders correctness and research validity before convenience.

## Findings

| Finding | Type | Impact | Ease | Why it matters | Recommended handling |
| --- | --- | ---: | ---: | --- | --- |
| `trade_touch_v1` has no queue position, cancellation priority, hidden liquidity, or venue acknowledgement model. | Execution realism | 5 | 1 | Its 76 fills are useful systems tests but can be substantially biased relative to executable fills. | Keep `ModelDerived` labels; add calibrated and sensitivity-tested fill models before interpreting strategy outcomes. |
| The Python `BacktestRisk` gate is a small research implementation rather than the C++ `AccountRiskProjection`. | Correctness drift | 4 | 2 | Limits or reservation semantics can diverge as the production risk component evolves. | Define a shared cross-language admission contract or bind the C++ projection before research results drive decisions. |
| Backtest runner state is replayable but not durably checkpointed. | Recovery | 4 | 3 | Restart requires replaying all normalized events and cannot resume a long experiment exactly from a persisted runner state. | Persist versioned runner checkpoints containing cursor, active orders, risk, scheduled decisions, config hash, and input hashes. |
| The normalizer derives product identity from a one-market capture; WebSocket data lacks complete contract metadata. | Provenance | 4 | 3 | Tick, lot, payout, lifecycle, event metadata, and settlement rules are not independently versioned. | Add a versioned venue-product metadata ingest and require its hash in normalization manifests. |
| Backtesting loads every feature row into a Python dictionary and retains all orders/fills before writing. | Scalability | 3 | 4 | This is simple and deterministic for 20k events, but memory grows linearly with longer captures and multi-market work. | Stream features with a cursor, append outputs incrementally, and benchmark before adding columnar storage. |
| Scheduled decisions are maintained by sorting a Python list on each insertion. | Performance | 2 | 5 | It is deterministic but becomes unnecessarily expensive at high decision rates. | Replace with a stable heap keyed by logical time and ordinal after profiling. |
| JSONL schemas are implementation-defined rather than published formal schemas with migration tests. | Compatibility | 3 | 3 | External tools and future versions can silently disagree on fields or units. | Publish JSON Schema or equivalent compatibility fixtures and reject unsupported schema versions. |
| Normalized and feature writes use temporary-directory rename but no explicit file/directory fsync protocol. | Durability | 3 | 3 | A local crash can lose the most recent generated artifact despite the raw capture remaining safe. | Reuse the Phase 4 durability discipline if generated-artifact durability becomes a requirement. |
| One capture and one market do not establish cross-market ordering, timezone, or source-recovery behaviour. | Coverage | 3 | 2 | The implementation may appear general while key multi-stream policies are untested. | Add fixtures for multiple products, sequence scopes, reconnect snapshots, late records, and gap recovery. |
| The first configuration uses a fixed 100 ms latency and one-contract quotes without calibration or sensitivity ranges. | Research validity | 4 | 4 | Results can be dominated by unvalidated assumptions. | Add experiment grids and report latency/fill/risk sensitivity before comparing strategies. |

## Missing tests

| Missing test | Impact | Ease | Suggested acceptance condition |
| --- | ---: | ---: | --- |
| Conflicting duplicate source event | 4 | 5 | Same source identity with a different payload fails and leaves no output directory. |
| Truncated JSONL and corrupt manifest | 4 | 5 | Normalization fails closed and removes partial output. |
| Multi-product/source-scope ordering | 4 | 2 | Stable ingress order and per-scope sequence validation are proven across products. |
| Reconnect snapshot after a gap | 4 | 2 | A discontinuity is labelled and downstream features/results are incomplete unless explicitly recovered. |
| Latency boundary and quote-expiry tests | 4 | 4 | A current event cannot fill an order that becomes active after it. |
| Partial fill, cancellation, and position-limit interaction | 4 | 4 | Exposure and inventory remain correct across partial model fills and replacements. |
| Persisted runner-checkpoint continuation | 4 | 2 | Restarted backtest emits byte-identical later orders, fills, and manifest metrics. |
| Full-capture normalization regression fixture | 3 | 3 | The known raw capture yields its recorded manifests and counts. |

## Priority order

| Priority | Work | Impact | Ease | Reason |
| ---: | --- | ---: | ---: | --- |
| P0 | Preserve ModelDerived labels and prohibit performance/PnL claims from `trade_touch_v1`. | 5 | 5 | This is already implemented and must remain non-negotiable. |
| P1 | Add calibrated fill-model sensitivity experiments and explicit latency assumptions. | 5 | 3 | Highest research-validity improvement without changing the C++ matching core. |
| P2 | Add formal product metadata and source-schema compatibility validation. | 4 | 3 | Prevents provenance/units mistakes as more markets arrive. |
| P3 | Unify or formally contract-test Python backtest risk admission with C++ risk projection. | 4 | 2 | Prevents silent safety drift before strategies rely on historical results. |
| P4 | Add durable runner checkpoints and continuation tests. | 4 | 2 | Required for long-running, restartable experiments, but full replay is adequate for the current capture. |
| P5 | Stream feature/backtest processing and use a stable scheduling heap after benchmarks. | 3 | 4 | Straightforward scalability work once larger inputs justify it. |
