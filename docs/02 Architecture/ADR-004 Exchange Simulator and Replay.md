# ADR-004: Deterministic exchange simulator and replay

- Status: Accepted
- Date: 2026-07-13
- Scope: Phase 4

## Context

Phase 3 provides deterministic, contract-scoped matching but deliberately omits exchange command
ordering, lifecycle state, globally unique IDs, market-data publication, replay, and recovery.
Those responsibilities must not be added to `LimitOrderBook`, whose single-writer boundary and
ownership of live mutable matching state are intentional.

## Decision

Create `pmm_sim` with one single-threaded `ExchangeSimulator`. It owns a deterministic scheduled
command queue, one book per registered contract, global order/trade/event identifier allocation,
mutable market lifecycle state, an append-only in-memory event journal, and detached checkpoints.

Commands are ordered by `(scheduled_at, ingress_sequence)`. `scheduled_at` is logical simulator
time; equal timestamps are resolved only by the exchange-assigned ingress sequence. The exchange
is the sole production caller of `LimitOrderBook::submit` and `cancel`.

Every externally observable event has a globally unique `SequenceNumber`. A successful submit
emits this contiguous event batch:

1. `OrderAcknowledged`;
2. zero or more `TradeExecuted` events, each carrying the market-level `Trade` and its buyer and
   seller `Fill` projections;
3. an `OrderOutcome`; and
4. one `BookDepthChanged` event if visible aggregate depth changed.

`Trade.sequence()` is the sequence of its `TradeExecuted` event. A shared exchange sequencer is
injected into every book through the existing `ExecutionIdSource`, so trade IDs and execution
sequences cannot collide across contracts. Cancels, lifecycle transitions, and rejections are
also exchange events. Consumers read the journal or a future bounded queue; matching never calls
consumer callbacks.

`Market` remains an immutable definition. The exchange keeps mutable lifecycle state separately.
Phase 4 supports `Open <-> Halted`, `Open/Halted -> Closed`, and `Closed -> Settled`. New orders
are allowed only while open; cancels are allowed while open, halted, or closed; closing a market
cancels its live resting orders in deterministic resting-priority order.

Snapshots are detached values containing simulator time, next identifier values, pending commands,
lifecycle state, and one `BookCheckpoint` per book. `BookCheckpoint` contains live book state and
priority only; the exchange owns its storage. Replay feeds recorded commands through the same
command queue and matching path.

## Rationale

One event loop gives the current project a total order across markets, deterministic replay,
simple failure boundaries, and testable lifecycle behavior without locks in the matching path. It
is the right reference implementation before evidence justifies instrument sharding. The mutable
book remains efficient in the hot path, while the event journal and snapshots provide an auditable
recovery foundation.

The initial journal and checkpoints are in-memory values. This deliberately validates ordering,
replay, and state restoration before choosing an on-disk encoding, schema-evolution policy,
checksums, or a durability protocol.

## Consequences

- The initial implementation is throughput-limited by one exchange loop, but each book still has
  good locality and no internal synchronization overhead.
- All event consumers must treat sequence order, not wall-clock time, as authoritative.
- Full-book snapshots are used internally to calculate correct depth deltas in the first version.
  A book-provided changed-level report is a later optimization after benchmarks.
- Durable write-ahead logging, event serialization, consumer backpressure, risk controls,
  inventory projection, synthetic sources, and historical adapters remain separate increments.
- Future per-instrument shards must preserve the same ingress order, global event sequencing, and
  replay contract at the exchange boundary.
