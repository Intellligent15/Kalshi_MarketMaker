# ADR-002: Core domain model

- Status: Accepted
- Date: 2026-07-13
- Scope: Phase 2

## Context

Phase 3 will require deterministic matching and risk-aware inventory, but the project had no
validated representation of a market, contract, order, trade, or position. The core model must
be correct and exchange-independent before an order book can safely be designed.

## Decision

Create one `pmm_core` C++20 library with the following value-oriented relationships:

```text
Market owns one Binary Contract
Contract supplies price and lot rules
Order references ContractId and TraderId
Trade references the two orders and traders
Trade produces one buyer Fill and one seller Fill
Inventory owns Positions for one TraderId
Position changes only through its matching Fill
```

All IDs are distinct, non-zero 64-bit wrappers. `Price` and `Quantity` use integers, not
floating point. A `PriceGrid` belongs to a `Contract`, so valid bounds and increments are a
contract rule rather than a global assumption. A `LotSize` similarly controls valid quantity.

A binary market contains one YES-payout contract. `Buy` and `Sell` describe instructions on
that contract; YES/NO settlement is not conflated with order side. This avoids mirrored order
books and preserves a direct path to future multi-contract markets.

`Order` captures immutable accepted intent. Future exchange/order-book code owns mutable state
such as remaining quantity, cancellation status, and queue-priority sequence. `Trade` is the
market-level execution fact; `Fill` is its trader/order-specific projection. Inventory tracks
signed quantity only. Cost basis, fees, PnL, and risk limits are deferred until their accounting
policy is designed.

Expected validation failures return `Result<T>` or `Result<void>` containing a `DomainError`.
Constructors are private where validation is required, and normal validation does not use
exceptions. Debug assertions remain appropriate only for programmer-invariant failures.

## Rationale

Typed IDs prevent accidental category errors at compile time. Integer units remove rounding risk
from order and position arithmetic. Immutable event records permit replay, audit, and strategy
consumption without shared mutable ownership. ID references avoid object-lifetime cycles between
the future exchange, order book, risk engine, and strategies.

Separating order intent from order-book state prevents Phase 2 from implementing a disguised
order book. Separating trades from fills makes one market execution usable by both market history
and trader-specific accounting.

## Tradeoffs

- A project-owned C++20 `Result` wrapper is small and explicit, but has less ecosystem support
  than C++23 `std::expected`; it can be replaced deliberately if the language baseline changes.
- `Market` currently owns one binary contract. Multi-outcome products require a later market
  aggregate extension and a corresponding settlement design.
- Inventory uses a deterministic `std::map` rather than a faster hash table. This favors stable
  traversal and simple behavior; benchmark evidence should precede a container change.
- Position updates are mutable because risk/exchange ownership needs efficient incremental state.
  Orders, trades, fills, and definitions remain value-like and immutable after construction.
- IDs are numeric in the core. Gateways must map venue strings to these IDs at the boundary.

## Consequences

Phase 3 may add order-book and matching state around these interfaces, but it must not weaken
their validation rules or allow strategy code to mutate exchange inventory. Before adding PnL,
define the accounting policy; before assigning price-time priority, define the sequence-owner and
cancellation semantics.
