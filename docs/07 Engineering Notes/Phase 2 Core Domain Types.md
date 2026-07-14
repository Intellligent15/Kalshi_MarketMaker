# Phase 2: Core domain types

## Purpose

Provide one tested, deterministic vocabulary for market definitions, orders, executions, and
inventory before building the order book.

## Design

`pmm_core` is a standalone CMake library under `cpp/include/pmm/core` and `cpp/src/core`.
It exposes integer price/quantity primitives, typed IDs, timestamps, binary contracts, markets,
orders, trades, fills, positions, and inventory. Its public aggregate header is
`pmm/core/core.hpp`.

Factories validate inputs and return `Result<T>`. Contract rules validate all prices and positive
lot-aligned quantities. Orders are immutable intent records; trades are immutable execution facts;
fills are generated from a valid trade; inventory is the only fill-updated state in this phase.

## Tests

`tests/core_domain_test.cpp` covers:

- rejecting zero identifiers and negative prices;
- price-grid bounds and increments;
- market/contract ownership;
- limit-versus-market order shape and contract validation;
- complementary buyer and seller fills from a trade; and
- inventory position updates and trader-ownership rejection.

## Known limitations

- The project supports one binary contract per market only.
- Position records quantity exposure, not cost basis, PnL, fees, or collateral.
- Trade construction validates supplied identifiers and contract rules, but matching ownership and
  order-state consistency belong to the future matching engine.
- `Result<T>` is intentionally minimal: callers must check it before reading its value or error.
- No order book, matching, cancellation, market simulation, or strategy behavior is present.

## Next design boundary

Phase 3 now implements price-time priority, order-book ownership, lifecycle state, cancellation,
and partial-fill semantics while reusing these types. See
[[07 Engineering Notes/Phase 3 Limit Order Book]].

For a plain-language walkthrough, see [[07 Engineering Notes/Phase 2 Explained]]. For a ranked
review of debt, tests, documentation, optimization, and scalability concerns, see
[[07 Engineering Notes/Phase 2 Critique]].
