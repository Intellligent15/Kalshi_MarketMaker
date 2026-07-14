# Phase 4: Exchange simulator and deterministic replay

## Purpose

Turn the Phase 3 matching core into a deterministic exchange boundary suitable for future
simulation, research, agents, historical replay, risk controls, and market-data consumers.

## Design

`pmm_sim::ExchangeSimulator` owns the event loop. A caller enqueues a submit, cancel, or lifecycle
command at a logical timestamp. The loop processes the earliest timestamp first and breaks ties by
an exchange-assigned ingress sequence. It validates lifecycle state, constructs accepted `Order`
values with exchange-owned IDs, invokes the correct single-writer book, and appends immutable
events to its journal.

The simulator shares a stable sequencer object with every book. That object implements the Phase
3 `ExecutionIdSource` and reserves global trade IDs plus the exact event sequence used by each
`TradeExecuted` event before the book mutates. The sequencer lives independently from the movable
simulator object so book references remain valid after construction, restoration, or return by
value.

Book changes are exposed as final aggregate `PriceLevelDelta` values. The first implementation
computes them by comparing full pre/post snapshots; this is correct and deterministic, not an
assertion of optimal market-data performance.

`ExchangeCheckpoint` and `BookCheckpoint` are detached value records. Restoring a checkpoint
rebuilds price-level FIFO order using stored resting priority, then continues from the stored ID,
event, ingress, and clock state. The exchange command journal can be replayed through the regular
event loop rather than bypassing the matching engine.

## Event, time, and depth-consumer contract

`scheduled_at` is the logical time at which an input becomes eligible for the exchange queue;
equal times are ordered by exchange-assigned ingress sequence. `Order::submitted_at` is client
intent metadata. `ExchangeEvent::occurred_at` is logical matching/lifecycle time, and a
`Trade::executed_at` equals its `TradeExecuted` event's `occurred_at`. Consumers must use global
event sequence, never wall-clock time, as the authoritative order.

`BookDepthChanged` contains final aggregate state for each changed `(side, price)` level.
`total_quantity == 0` and `order_count == 0` remove a level. Consumers must apply levels keyed by
side and price rather than infer a priority from the vector's implementation order.

The checkpoint excludes emitted events, terminal-order history, consumer offsets, format versions,
checksums, and durable-storage guarantees. It is an in-memory continuation value, not a
crash-recovery artifact.

## Tests

- Multiple contracts share one global event/trade sequence.
- Equal-time commands retain exchange ingress order.
- Closed markets cancel live orders and reject fresh submissions.
- Checkpoint restoration produces the same later trade IDs, event sequence, and full payloads.
- Command-journal replay reproduces every original event payload and order.
- Four fixed-seed, 1,500-command randomized tests compare the order book against a simple
  price-time reference model and run queue, aggregate, bitmap, and locator invariant validation
  after every add or cancel.

## Known limitations

- The default simulator remains in memory. Opt-in durable mode now uses a versioned,
  checksummed write-ahead journal and atomic exchange checkpoints, and recovery compares every
  regenerated post-checkpoint event payload with its committed batch.
- Durable mode protects the exchange only. It has no journal compaction, cross-process locking,
  distributed replication, agent/risk/market-maker checkpoint recovery, or schema migration
  beyond rejecting an unsupported version.
- `OrderOutcome` records the incoming order's final status. Passive fills are represented by the
  `TradeExecuted` fill projections rather than separate passive-order-update events.
- Risk is intentionally an external future gate; Phase 4 does not authorize accounts or update
  inventory.
- Full snapshots for delta calculation and vector insertion for the command queue are correctness
  baselines to benchmark before optimization or sharding.

For a plain-language walkthrough, see [[07 Engineering Notes/Phase 4 Explained]]. For the ranked
debt, test, documentation, optimization, and scalability register, see
[[07 Engineering Notes/Phase 4 Critique]].
