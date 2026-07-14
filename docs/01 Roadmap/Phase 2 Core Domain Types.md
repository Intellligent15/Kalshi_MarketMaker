# Phase 2: Core domain types

## Goal

Create the validated, exchange-independent vocabulary used by every later component without
implementing order-book storage, matching, cancellation, simulation, PnL, or strategy behavior.

## Delivered scope

- Strong `MarketId`, `ContractId`, `OrderId`, `TradeId`, `TraderId`, and `SequenceNumber` types.
- Integer `Price`, `Quantity`, `LotSize`, `PriceGrid`, and `Timestamp` values.
- A binary `Contract` and its owning `Market` definition.
- Immutable limit/market `Order`, `Trade`, and trader-specific `Fill` records.
- Fill-driven `Position` and `Inventory` updates without any PnL accounting.
- Result-based domain validation and unit tests.

## Explicitly deferred

- Order-book state, priority assignment, matching, partial-fill generation, and cancellation.
- A mutable market-state model and settlement process.
- Fees, cost basis, realized/unrealized PnL, and inventory risk limits.
- External exchange identifiers, gateway mapping, configuration parsing, and persistence.

## Completion criteria

The core target builds with warnings-as-errors, and tests cover invalid construction, contract
rules, order shape, trade/fill projections, inventory ownership, and position updates.

See [[02 Architecture/ADR-002 Core Domain Model]] and
[[07 Engineering Notes/Phase 2 Core Domain Types]] for the detailed rationale. The implemented
next milestone is [[01 Roadmap/Phase 3 Limit Order Book]].
