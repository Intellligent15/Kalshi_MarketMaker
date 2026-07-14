# Phase 4 explained in plain language

## The result

Phase 4 wraps the Phase 3 order book in an exchange simulator. The book still answers one narrow
question: given one contract and one valid order, what trades and resting orders result? The
simulator answers the surrounding exchange questions: which command arrives first, whether the
market is open, which IDs are globally unique, what the rest of the system sees, and how the run
can be repeated.

```text
command source
    -> deterministic exchange queue
    -> lifecycle check and global IDs
    -> one contract's single-writer order book
    -> immutable exchange events
    -> journal, checkpoint, replay, and future consumers
```

## What we built

`ExchangeSimulator` registers one `LimitOrderBook` for each contract. It accepts three commands:

- submit an order;
- cancel an owned live order; or
- change a market's lifecycle state.

It places commands in a queue ordered first by logical timestamp and then by a monotonically
assigned ingress sequence. This means that two commands at the same time do not depend on thread
timing or wall-clock arrival: the exchange records which entered its queue first.

The simulator, rather than a book, creates order IDs. It also owns one shared trade/event
sequencer. Before a book matches, that sequencer reserves globally unique trade IDs and the event
sequence for each resulting trade. This lets two contracts share one unambiguous market history.

## What happens to a submitted order

For an accepted order, the simulator records the following facts in order:

```text
OrderAcknowledged
    -> TradeExecuted (zero or more; each includes buyer and seller Fill values)
    -> OrderOutcome for the incoming order
    -> BookDepthChanged when aggregate depth changed
```

Each event receives one global sequence number. That number is the authoritative order of
history, even when events have the same logical timestamp. A trade's existing Phase 2 sequence is
exactly the sequence number of its `TradeExecuted` event.

The simulator does not call strategy or market-data callbacks while matching. Consumers instead
read the journal. This prevents a slow or reentrant consumer from mutating the book or changing
the order in which matching occurs.

## Lifecycle in this first version

The `Market` value remains immutable product metadata. The simulator holds the mutable state:

```text
Open <-> Halted
Open/Halted -> Closed -> Settled
```

New orders are accepted only while open. Cancels are allowed while open, halted, or closed. A
close operation deterministically cancels all resting orders, then emits a depth update. Settlement
currently stops trading only; payout, fees, collateral, and cash accounting are intentionally not
implemented.

## Replay and checkpoints

A checkpoint copies the current simulator clock, next identifiers, pending commands, lifecycle
state, and every book's live resting orders plus their queue priority. Restoring it rebuilds the
same FIFO queues and continues with the same next IDs. The command journal can then be fed back
through the ordinary queue and book path. This is why replay exercises matching rather than
pretending that recorded trades alone can rebuild an order book.

The current journal and checkpoints are deliberately in memory. They prove deterministic behavior
and create the right ownership boundary, but they are not crash-safe persistence. ADR-004 and the
Phase 4 critique make durable write-ahead storage the next major correctness decision.

## Why the design stays single-threaded

One event loop is easier to explain and verify:

- one command order;
- one global event history;
- no locks in matching;
- deterministic synthetic or historical inputs; and
- straightforward snapshots and tests.

This is not a claim that a production exchange should always use one core. It is a reference model
that future instrument shards must reproduce at the public command/event boundary.

## How we verified it

The simulator tests cover global ordering across contracts, close/cancel behavior, checkpoint
restore, and command-journal replay. The book test suite also runs four fixed random seeds with
1,500 commands each. After every command it compares the real book against a simple price-time
reference model and checks queue links, level aggregates, bitmap occupancy, and order-locator
membership.

## What should happen next

The shortest high-value follow-up is to formalize the public event/time/lifecycle table and add
full event-payload replay comparisons. Then test malformed checkpoints and queued-command restore.
After those low-cost correctness steps, design durable write-ahead journaling and atomic event
batches before connecting strategies, agents, paper trading, or external data.
