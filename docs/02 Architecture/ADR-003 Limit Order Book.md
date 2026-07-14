# ADR-003: Limit order book

- Status: Accepted
- Date: 2026-07-13
- Scope: Phase 3

## Context

Phase 2 deliberately made `Order` immutable and deferred remaining quantity, cancellation,
queue priority, and matching. Prediction-market contracts normally use compact, bounded price
grids, while matching requires fast cancellation and strict FIFO at each price.

## Decision

Create a `pmm_book` library with a single-writer `LimitOrderBook` scoped to one immutable
`Contract`. It owns only live mutable order state:

```text
Bid/ask dense price ladders
  -> price-level aggregate quantity and order count
  -> intrusive FIFO queue of live order nodes

OrderId hash table -> live order node -> price-level queue links
```

The price grid determines a direct ladder index. The book validates that its number of ticks is
within a named dense-ladder bound (default 4096). Each side maintains an occupancy bitmap so the
best ask and best bid can be located without scanning order nodes.

The book assigns a monotonic priority sequence only when a limit order rests. It matches best
price first, then FIFO at a price. A trade occurs at the resting order's price. It emits the
existing Phase 2 `Trade` and buyer/seller `Fill` values through a report; it does not update
inventory. `ExecutionIdSource` reserves trade IDs and execution sequences before mutation, so a
source failure cannot leave a partially applied command.

## Matching policy

- A buy crosses asks at or below its limit; a sell crosses bids at or above its limit.
- Market orders consume available liquidity then expire with their remainder; they never rest.
- Limit remainders rest at their limit price.
- Partial fills retain the resting order's queue position.
- Cancellation is allowed only for a live resting order and removes it from its queue.
- A duplicate order ID or unknown cancellation is rejected without mutation.
- If an aggressor reaches a same-trader resting order, it is cancelled with its remaining quantity.
  It does not bypass that order to execute against later time priority.

## Rationale

The dense ladder has direct price-level lookup and good cache locality for typical binary
prediction-market grids such as 1–99 cents. Intrusive queues make unlinking an order constant
time once found, and the hash locator makes that find expected constant time. A single writer
provides deterministic replay behavior without locks in the matching path.

## Alternatives considered

- `std::map<Price, PriceLevel>`: more general for sparse/unbounded grids, but `O(log P)` lookup,
  node allocation, and pointer chasing are unnecessary for the expected compact grid.
- Skip list or custom balanced tree: also ordered, but add implementation complexity and weaker
  determinism/cache locality without solving FIFO or ID lookup.
- Hash table only: efficient cancellation lookup but cannot establish price priority.
- `std::list` queues: correct FIFO behavior but adds separate list-node allocation; intrusive
  links live directly in the owned order node.
- Heap: efficient best-price lookup but poor arbitrary cancellation semantics and stale-entry
  management.

## Consequences

The Phase 3 book is intentionally a bounded-grid implementation. A sparse tree-backed ladder may
be introduced behind the same behavior after benchmark evidence justifies it. Phase 4 must own
global event ordering, market lifecycle, persistence, and any multi-book ID source. Risk remains
outside the book and must approve commands before submission.
