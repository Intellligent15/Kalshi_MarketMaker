# Phase 3: Limit order book

## Purpose

Implement a correct, deterministic matching core before adding the simulator or strategies.

## Design

`pmm_book` adds `LimitOrderBook` around an immutable Phase 2 `Contract`. Each side has a dense
price ladder, a bitmap of occupied price levels, and aggregate level state. Live order nodes are
owned by an `OrderId` hash table and linked intrusively in FIFO order at their level. The book
uses an injected execution-ID source to construct validated `Trade` and `Fill` outputs.

The book is single-writer. It does not own risk, market status, inventory, PnL, persistence, or
market-data publication. Those boundaries avoid coupling a future exchange simulator or gateway
to matching storage.

## Tradeoffs

Dense ladders make compact prediction-market grids fast and cache-friendly but reserve memory for
empty ticks. The explicit maximum grid size rejects pathological contracts rather than silently
allocating excessive memory. `std::map` remains the future alternative if real workloads show a
sparse representation is necessary.

The intrusive queue minimizes allocations and makes cancellation expected `O(1)` with the order
locator, but its link invariants require comprehensive behavior tests. The first implementation
therefore prioritizes clear ownership and invariant-oriented test cases over allocator tuning.

## Tests and validation

`tests/order_book_test.cpp` covers:

- FIFO matching at one price and partial resting remainders;
- best-price traversal across multiple ask and bid levels;
- cancellation and unknown-cancel rejection;
- market-order residual expiry and resting-price execution;
- cancel-aggressor self-trade prevention; and
- rejection of a grid exceeding the dense-ladder bound.

## Known limitations

- The book has no amend/replace operation, auction logic, hidden liquidity, or alternative
  self-trade policy.
- Reports provide execution/final state information only; event persistence and publication are
  Phase 4 work.
- The default dense-ladder bound is an engineering guard, not a benchmark-derived optimum.
- No benchmarks or property-based invariant tests exist yet.

## Follow-up

Phase 4 should define a globally sequenced event log, market-state transitions, deterministic
replay, and a simulator-owned ID source. Add benchmark and property/fuzz coverage before changing
the selected data structure.
