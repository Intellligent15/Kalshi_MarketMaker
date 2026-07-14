# Phase 2 explained in plain language

## The goal

Phase 2 gave the project a shared, trustworthy vocabulary before any order book or simulation
exists. It answers basic questions consistently: what is a market, what is tradeable, what is a
valid price or quantity, what is an order, what happened in a trade, and how did it change a
trader's exposure?

Think of Phase 1 as building a workshop and Phase 2 as creating standardized parts and
measurements. Phase 3 will build the order book that uses those parts.

## The central rule: invalid data should be hard to create

Factories validate values before construction. The system rejects negative prices, zero IDs,
zero order quantities, prices outside a contract's grid, lot-size violations, trades with the
same buyer and seller, and fills applied to the wrong inventory. The result is that later code
can rely on domain objects being internally valid.

Expected validation failures return `Result<T>` with a `DomainError`; they are not ordinary
exceptions. A caller checks whether the result contains a value before using it.

## The building blocks

### IDs and time

`MarketId`, `ContractId`, `OrderId`, `TradeId`, `TraderId`, and `SequenceNumber` are separate
non-zero 64-bit types. Although they are numeric internally, C++ will not let an order ID be
used where a trader ID is required. `Timestamp` records UTC nanoseconds; `SequenceNumber` gives
the exchange's deterministic ordering when two events have the same timestamp.

### Price, quantity, and contract rules

`Price` and `Quantity` are integers, never floating-point numbers. For example, a price of `63`
can mean 63 price units. This removes decimal rounding surprises from matching and accounting.

The `Contract` owns the rules that make those otherwise generic values valid:

```text
PriceGrid: minimum, maximum, increment
LotSize: valid quantity increment
```

An order at 63 is valid only if 63 is inside the contract's price grid. A quantity of 10 is valid
only if it is positive and aligned with the contract's lot size.

### Market and binary contract

A `Market` owns one binary `Contract` in this phase. The contract pays a fixed payout when its
event resolves true and zero otherwise. There is one tradeable claim, not mirrored YES and NO
order books: buying the claim creates YES exposure, while selling it reduces or shorts that
exposure.

### Order, trade, and fill

An `Order` is immutable intent: trader, contract, buy/sell side, order type, quantity, optional
limit price, and submission time. Limit orders have a price; market orders do not. Remaining
quantity, cancellation, and queue priority are deliberately future order-book state.

A `Trade` is the immutable market-level fact that a buyer and seller executed a quantity at a
price. It produces two `Fill` objects: one buyer fill and one seller fill. The distinction lets
market history consume trades while inventory and strategy callbacks consume their own fills.

```text
Trade at 63 for 10 contracts
├── buyer fill: Buy 10 at 63
└── seller fill: Sell 10 at 63
```

### Position and inventory

A `Position` tracks one trader's signed exposure in one contract. A buy fill increases it; a sell
fill decreases it. An `Inventory` owns all positions for one trader and refuses fills belonging to
another trader.

```text
Start: 0
Buy 10: +10
Sell 4: +6
Sell 6:  0
Sell 3: -3
```

Phase 2 tracks exposure only. PnL, fees, collateral, average cost, and risk limits require later
accounting and risk-policy decisions.

## Why the ownership model matters

Markets own contracts by value. Orders, trades, fills, and positions refer to other objects by
ID instead of pointer. This avoids circular ownership and lifetime bugs. The future exchange owns
markets, order state, and history; the future risk engine owns inventory; strategies read events
and snapshots rather than mutating exchange state directly.

## What the tests prove

The core test suite verifies invalid inputs, price-grid and lot-size rules, market ownership,
limit/market order shape, complementary fills, long and short positions, and inventory ownership.
It does not claim that an order book or matching engine works, because neither exists yet.

## What comes next

Phase 3 will define and implement the order book: order lifecycle, price levels, FIFO priority,
matching, partial fills, and cancellation. It must reuse the Phase 2 types instead of inventing
new price, quantity, or identifier representations.
