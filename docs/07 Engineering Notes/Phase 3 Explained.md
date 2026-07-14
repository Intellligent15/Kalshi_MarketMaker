# Phase 3 explained in plain language

## The goal

Phase 2 defined trustworthy market vocabulary: contracts, orders, trades, fills, and inventory.
Phase 3 turns that vocabulary into a working exchange mechanism. Its goal is deliberately narrow:
given valid orders for one contract, decide who trades, at what price, in what order, and what
remains available to trade.

It does not decide whether an order is safe, whether a market is open, how PnL works, or how an
event is persisted. Those are exchange, risk, and simulator concerns that must stay outside the
matching core.

## The mental model

An order book is two waiting lines:

```text
Buyers: highest price first, then earliest arrival
Sellers: lowest price first, then earliest arrival
```

At any one price, arrival order matters. If two traders offer to sell at 60, the trader who was
already waiting at 60 must trade first. That is price-time priority.

When a new buy reaches the book, it first trades with the cheapest eligible seller. When a new
sell arrives, it first trades with the highest eligible buyer. The trade price is the resting
order's price, which makes the incoming order the aggressor and preserves the quote already shown
to the market.

## What happens on submission

```text
Validate the contract and duplicate ID
        ↓
Find eligible opposite-side price levels
        ↓
Match queue heads in price-time order
        ↓
Reserve execution IDs and construct Trade/Fills
        ↓
Apply fills to resting state
        ↓
Rest a remaining limit order, or expire/cancel the remainder
```

The reserve step occurs before book mutation. If the ID source cannot provide enough trade IDs or
sequences, the incoming command fails and the resting book remains unchanged.

## How the implementation is organized

`LimitOrderBook` is scoped to one immutable contract and is intentionally single-writer.

```text
LimitOrderBook
├── bid ladder: one level for each valid price tick
├── ask ladder: one level for each valid price tick
├── level: aggregate quantity + FIFO order queue
├── live-order hash table: OrderId -> order node
└── occupancy bitmap: identifies non-empty price levels
```

The contract's price grid supplies a direct array index. On a normal binary market with prices
from 1 to 99 cents, price 60 maps directly to its level; the engine does not search a tree to find
it. Each level is an intrusive FIFO queue: the order node contains its own previous/next links.
The hash table finds a live order by ID so cancellation can unlink it without scanning the queue.

This gives direct price lookup, expected constant-time cancellation, and strict FIFO behavior.
The tradeoff is that a dense ladder reserves a small amount of memory for every allowed tick,
including empty ticks. The implementation therefore rejects grids over a named 4096-level guard.

## Important behavior choices

- **Limit order:** trades while its price crosses the opposite best price, then rests any remainder.
- **Market order:** trades available liquidity, then expires any remainder; it never rests.
- **Partial fill:** the unfilled resting order stays in its existing queue position.
- **Cancellation:** only a live resting order can be cancelled; unknown IDs are rejected.
- **Self trade:** if an aggressor reaches its own resting order, its remaining quantity is
  cancelled. It cannot skip ahead of that order to trade with later liquidity.
- **Inventory:** the book emits `Trade` and two `Fill` values but does not update inventory itself.

## Why this design was chosen

The project models bounded binary prediction-market prices, so a dense ladder is simpler and more
cache-friendly than a general tree. A `std::map` would support sparse or enormous price ranges,
but it adds logarithmic level lookup and pointer-heavy allocations. A hash table alone cannot
enforce best-price priority, and a linked list alone cannot locate an order by ID. The selected
combination gives each problem to the structure that handles it well.

## Debt to prioritize

The most important unfinished work is not a micro-optimization of the book.

1. **Impact 5 — durable, globally sequenced events.** The system needs an exchange-owned event
   log, snapshots, and replay to become a credible simulator or research platform.
2. **Impact 4 — invariant/property testing.** Randomized command sequences should compare the
   book with a simple reference model and verify queue, aggregate, bitmap, and order-locator
   invariants after every command.
3. **Impact 4 — global ID ownership.** A test-local ID source can collide across books. The future
   simulator/exchange must issue unique trade IDs and event sequences across every contract.
4. **Impact 4 — exchange boundaries.** Market lifecycle, risk checks, inventory ownership, and
   market-data publication need explicit ownership before agents or paper trading are introduced.

The full ranked register is [[07 Engineering Notes/Phase 3 Critique]].

## What comes next

The next engineering milestone is Phase 4: an event-driven exchange simulator and replay model.
It should own books, global IDs, sequenced events, market status, deterministic command ordering,
snapshots, and synthetic/replayed event inputs. It should begin with the invariant tests above,
then add a minimal single-market event loop before expanding to multiple contract shards.
