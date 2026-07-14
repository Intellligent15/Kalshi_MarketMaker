# Phase 6 explained in plain language

## What changed

Phase 6 adds a careful gate between a market maker and the exchange. The market maker may suggest
"buy one at 48" but it cannot name a trader, call a book, or decide that the order is safe. The
risk layer supplies the authorized trader identity only after checking the account's current
inventory and all known resting/pending orders.

```text
public market events -> read-only market and risk views -> quote suggestion
                                                -> risk approval -> exchange command
```

The implementation adds two libraries: `pmm_risk` owns account admission and event-derived
exposure; `pmm_market_maker` owns periodic quote decisions. The exchange event now includes its
ingress sequence, allowing a risk reservation to be tied to exactly the command that acknowledged
or rejected it. Replay preserves that ingress sequence.

## How one quote turn works

1. The coordinator processes exchange commands due at the decision's logical time.
2. It pulls every resulting exchange event through one stable sequence watermark.
3. The risk projection updates signed inventory, live orders, and pending reservations from those
   events; the market-data projection updates displayed depth and last trade.
4. The maker calculates desired integer-tick bid/ask prices from its configured, last-trade, or
   midpoint reference and optional inventory skew.
5. Stale or undesired quotes are cancelled. New identity-free post-only intents pass through
   admission in deterministic side order before the coordinator enqueues approved commands.

The risk view is deliberately conservative: a new bid is evaluated as though every existing and
pending bid could fill; the analogous rule applies to sells. An exchange rejection releases only
the matching pending reservation. A risk rejection never enters the exchange.

## Why the boundaries matter

The initial maker posts a bid below and an ask above a reference price. Prices remain integer
contract ticks. When inventory becomes long, both quotes shift lower; when short, both shift
higher. Quotes are post-only, so an intended maker quote that would immediately trade is rejected
before matching. Changed or old quotes are cancelled before a risk-constrained replacement.

The book remains unaware of accounts, risk, PnL, and strategies, so Phase 3 price-time priority
does not change. The exchange remains the matching authority. The risk projection is authoritative
only for account exposure derived from immutable exchange events; the strategy's local view is
read-only. This is why checkpoint/replay can reproduce the same continuation without giving a
strategy a mutable book reference.

## Manual walkthrough

Run the deterministic scenario with:

```sh
./build/cpp/pmm_demo --steps 5
```

The demo starts a maker quoting 48 bid / 52 ask around a 50 reference. Scheduled external traders
alternately sell at 48 and buy at 52, so the printed output shows fills, inventory changing from
flat to long and back, replacement quote admissions, and the current displayed depth. It is a
small observability aid for the simulation boundary, not a trading UI or a paper-trading tool.

Use `pmm_demo --help` to see its bounded `--steps` option.

Everything still uses logical time and the exchange event sequence. Checkpoints can continue the
same in-memory experiment, but no data survives a process crash and no financial-accounting claim
is made.
