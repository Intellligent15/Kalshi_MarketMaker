# Phase 4: Event-driven exchange simulator and deterministic replay

## Goal

Build the exchange layer around the Phase 3 matching core without changing matching semantics or
placing lifecycle, risk, persistence, inventory, or market-data consumers inside the book.

## Delivered scope

- `pmm_sim` with one deterministic, single-threaded `ExchangeSimulator`.
- Global exchange-owned order IDs, trade IDs, and event sequence numbers across all registered
  contracts.
- Scheduled command ingestion ordered by logical time then ingress sequence.
- Submit, cancel, market lifecycle, acknowledgement, rejection, trade/fill, order-outcome, and
  aggregate depth-change events.
- Open/halted/closed/settled lifecycle gating; close cancels live resting orders deterministically.
- In-memory append-only command/event journals, exchange checkpoints, checkpoint restore, and
  deterministic command replay.
- Detached `BookCheckpoint` support that preserves live orders and queue priority while keeping
  persistence outside the book.
- Deterministic randomized reference-model tests for Phase 3 price-time matching.

## Explicitly deferred

- Durable file/network event stores, checksums, schema migration, and crash-safe write-ahead
  commit protocols.
- Risk limits, account authorization, inventory/PnL projections, fees, collateral, and settlement
  cash flows.
- Synthetic order-flow generators, historical input adapters, strategy-agent scheduling, and
  consumer backpressure queues.
- Instrument sharding, cross-process sequencing, and book-internal concurrency.
- Optimized incremental book-delta reporting and performance benchmarks.

## Completion criteria

The simulator must preserve Phase 3 behavior, use one exchange-owned sequencer across books,
produce a contiguous deterministic event stream per command, restore live book state from a
checkpoint, and reproduce the same output order when replaying recorded commands. See
[[02 Architecture/ADR-004 Exchange Simulator and Replay]].
