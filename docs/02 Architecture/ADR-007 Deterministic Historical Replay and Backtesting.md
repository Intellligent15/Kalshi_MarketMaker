# ADR-007: Deterministic historical replay, causal features, and backtesting

- Status: Accepted
- Date: 2026-07-13
- Scope: Phase 7

## Context

Phases 1–6 establish a deterministic matching, event, synthetic-agent, risk-admission, and
baseline-market-making reference runtime. They do not define historical source provenance,
market-data schemas, cursor retention, feature causality, execution assumptions, or experiment
artifacts. Replaying incomplete historical market data as `ExchangeSimulator` commands would
mistake reconstructed or synthetic state for venue-observed truth.

The first Phase 7 prerequisite is now an opt-in durable exchange store: a versioned, checksummed
write-ahead command/event journal plus atomically replaced exchange checkpoint. It protects the
exchange boundary only. It does not make coordinator, risk, market-maker, accounting, gateway, or
paper-trading recovery claims.

## Decision

Build Phase 7 around immutable normalized observed-market streams. An observed-market projection
is authoritative for historical data; it remains outside `ExchangeSimulator` and every book.

```text
raw/external capture -> versioned normalization -> immutable normalized events
                                                -> cursor/snapshot projection
                                                -> causal features -> strategy intents
                                                -> risk admission -> latency/fill model
                                                -> execution, inventory, and experiment artifacts
```

`ExchangeSimulator` remains the sole production caller of `LimitOrderBook`. It continues to own
simulator IDs, event sequencing, lifecycle, matching, checkpointing, and command replay.
Historical adapters may use it only in an explicitly labelled simulator-reconstruction mode, not
as the authoritative observed-market stream.

### Durability prerequisite

`ExchangeSimulator::create_durable` writes a genesis record, then fsyncs a `Prepared` command
record before matching. It buffers a command's event batch, fsyncs a matching `Committed` record
before publishing the batch in memory, and marks the live exchange poisoned after a durable-store
failure. A poisoned exchange must be recovered, not continued.

`persist_checkpoint` is allowed only with an empty command queue. It writes a versioned,
checksummed checkpoint to a temporary file, fsyncs it, atomically replaces the prior checkpoint,
and fsyncs the directory. Recovery restores the newest valid checkpoint, replays later committed
commands through matching, compares every regenerated event payload with the journal, then
finishes an interrupted prepared command if one exists.

## Historical-data rules

- Raw direct captures and external vendor packages are immutable and have source metadata and
  cryptographic hashes.
- Normalized data has a schema version, normalizer version, source-to-output hashes, product-map
  version, ordering policy, and validation report.
- Product mappings state venue/product identity, contract metadata, units, tick/lot rules, payout
  interpretation, lifecycle/session context, and timestamp timezone/original representation.
- All runtime time is UTC nanoseconds. Original source timestamps and timezone information remain
  provenance.
- Source sequence is preferred only within its declared scope. Source time merges scopes, and a
  stable raw-record identity breaks all remaining ties into assigned ingress order.
- Missing source sequences become explicit gaps. Identical duplicates are idempotent; conflicting
  duplicates, invalid units, unknown products, and corrupt records are rejected.

## Fidelity and truth labels

Every normalized event, projection, feature row, execution, and result identifies both source
fidelity and truth category.

| Input | Observed fact | Prohibited claim without extra validation |
| --- | --- | --- |
| Market-by-order | Venue event stream, subject to source completeness | Exact reconstruction or counterfactual own fills |
| Level 2 | Published price-level state/deltas | Queue ownership, FIFO position, cancellations, hidden liquidity |
| Trades only | Reported trade prints | Book state, spread/depth, quote availability, execution realism |

Truth categories are `Observed`, `Reconstructed`, `Synthetic`, and `ModelDerived`. A fill model
must label its outputs `ModelDerived` unless it consumes actual account executions.

## Causality and execution

A cursor advances only after a contiguous batch is applied. A snapshot is labelled with its
watermark and only seeds strictly later deltas. A cursor gap fails a run by default; explicit
snapshot recovery creates a discontinuity artifact and marks downstream features/results
incomplete.

Features declare inputs, lookback, units, output schema, version, warmup, `as_of_time`, and
`as_of_watermark`. Strategy decisions may consume only data at or before that watermark. Future
returns and markouts are separate labels with explicit availability; they cannot become inputs.

Backtests use deterministic logical latency for market-data visibility, decisions, order/cancel
arrival, acknowledgement, and fills. V1 starts with a clear synthetic fill model plus a no-fill
reference mode. Fees, PnL, collateral, settlement, and economic-risk metrics remain disabled until
their accounting policy is separately defined and tested.

## Consequences

- Historical replay is auditable and causally explicit without contaminating exchange matching.
- Materialized normalized and feature data reduce repeated parsing and support reproducible ML
  datasets later.
- The initial local durable store has no compaction, distributed replication, coordinator-level
  recovery, schema migration beyond version rejection, or cross-process locking.
- Backtest results cannot claim venue-equivalent execution, paper-trading safety, or economic PnL
  realism unless their source fidelity and assumptions support it.
