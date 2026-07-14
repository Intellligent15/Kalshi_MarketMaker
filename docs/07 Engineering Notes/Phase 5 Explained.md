# Phase 5 explained in plain language

## What we built

Phase 5 adds controlled traders to the deterministic exchange. They provide repeatable synthetic
order flow for research without giving strategy code permission to touch the order book.

```text
external input -> exchange -> ordered events -> shared market-data view -> agent decisions
                                                               -> coordinator -> exchange commands
```

The important boundary is that agents return requests, not mutations. `SimulationCoordinator` is
the only agent-side object that calls the exchange queue. The exchange remains the only production
caller of a book, so Phase 3 price-time priority and Phase 4 lifecycle/ID rules remain unchanged.

## How a logical time step works

At time `t`, the coordinator first processes external commands already scheduled for `t`. It reads
the complete resulting event batches and updates a shared depth/trade projection. Every agent due
at `t` sees that same event watermark, in stable `AgentId` order. Their intents are collected and
only then enqueued in the same stable order. Events caused by those intents wait until a later
agent turn, so a strategy cannot create a reentrant callback loop while matching is running.

## The five baselines

- Noise traders use a seeded pseudo-random side to create background demand.
- Momentum traders react to a last-trade move away from a reference price.
- Mean-reversion traders react against a displayed best-price displacement.
- Informed traders have a configured synthetic reference value and trade favorable displayed quotes.
- Liquidity takers act only when displayed spread is sufficiently tight.

They all submit existing integer-quantity market orders. They deliberately do not calculate PnL,
hold authoritative inventory, authorize themselves, or market make. Those requirements belong to
the future risk/inventory and Phase 6 designs.

## Why it is reproducible

Each run has a fixed seed. Each agent derives its own SplitMix64 state from that seed and its
identity, so its pseudo-random choices do not depend on wall-clock time or a global random source.
The checkpoint stores that state, the next scheduled turn, the event watermark, the depth/trade
projection, and the exchange checkpoint. Restoring it continues the same logical run.

## What this does not claim

The journals and checkpoints are memory-only values. They support deterministic tests and local
continuation, not crash recovery. There is also no risk/account boundary yet, so Phase 5 is a
synthetic research baseline—not a safe autonomous or paper-trading system.
