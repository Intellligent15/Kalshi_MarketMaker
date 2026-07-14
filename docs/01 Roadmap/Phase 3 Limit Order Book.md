# Phase 3: Limit order book

## Goal

Build one deterministic, contract-scoped limit order book that implements price-time priority,
matching, partial fills, cancellation, and market-order handling while reusing Phase 2 value
types.

## Delivered scope

- `pmm_book` library with one single-writer `LimitOrderBook` per contract.
- Dense price ladders derived from the validated contract price grid.
- Intrusive FIFO queues per price level and an `OrderId` hash locator for live orders.
- Price-time matching at the resting order's price.
- Limit-order resting, market-order expiry, partial fills, and `O(1)` expected cancellation.
- Cancel-aggressor self-trade prevention.
- Injected execution-ID source and emitted `Trade`/`Fill` records.
- Unit tests for FIFO, price priority, partial fills, cancellation, market residuals, self trades,
  and dense-ladder bounds.

## Explicitly deferred

- Market-status gating, risk checks, account/inventory updates, fees, and PnL.
- Global event sequencing, persistence, replay, recovery, and market-data fanout.
- Order amend/replace, iceberg/hidden orders, auctions, and alternative self-trade policies.
- Sparse price-ladder implementation and performance benchmarking.

## Completion criteria

The book builds with warnings-as-errors and all matching/cancellation semantics are covered by
independent tests. See [[02 Architecture/ADR-003 Limit Order Book]] and
[[07 Engineering Notes/Phase 3 Limit Order Book]].
