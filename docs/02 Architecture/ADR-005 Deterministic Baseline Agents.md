# ADR-005: Deterministic baseline trading agents

- Status: Accepted
- Date: 2026-07-13
- Scope: Phase 5

## Context

Phase 4 provides a deterministic exchange and globally sequenced event journal, but deliberately
contains no order-flow generators, strategy scheduling, market-data consumers, risk, or inventory
ownership. Phase 5 needs useful synthetic participants without allowing strategy code to bypass
lifecycle validation, mutate a book, or create callback reentrancy.

## Decision

Create `pmm_agents`, centered on a single-threaded `SimulationCoordinator`. It owns baseline
agent schedules, per-agent pseudo-random streams, agent-local checkpointable state, market-data
projections, event cursors, and decision records. The coordinator is the only agent-runtime
component that enqueues an `ExchangeCommand`; agents produce `AgentIntent` values only.

```text
exchange event journal -> pull projection -> agent decision -> intent
                                                       -> coordinator -> exchange command queue
```

An agent has a distinct `AgentId` and one Phase-5 `TraderId`. `TraderId` is an execution identity,
not an authorization or accounting model. Future account, risk, and inventory services own the
mapping from accounts to permitted trader identities and make admission decisions before the
coordinator enqueues a command.

At a decision time, the coordinator first processes already-scheduled external exchange commands,
pulls their complete event batches to one watermark, then runs due agents ordered by `(AgentId,
decision ordinal)`. It collects their intents, enqueues them in that order, and processes their
commands only after every same-time agent has observed the same watermark. Resulting events are
visible on a later turn only; callback reentrancy is prohibited.

Each agent receives a keyed aggregate-depth projection and last-trade price reconstructed from
snapshots plus sequenced events. It does not retain a book reference. The implementation uses
checkpointable mutable state (next wakeup, decision ordinal, and PRNG state), not a second event
store. Coordinator checkpoints combine that state and projection with an exchange checkpoint.

Randomness is SplitMix64-derived from `(run seed, AgentId)` and is never taken from wall-clock
time, `random_device`, or global process state. Prices and quantities remain existing integer
domain values.

## Baselines

- Noise: seeded random market-order side at a configured cadence.
- Momentum: trades with last-trade direction beyond a fixed integer threshold.
- Mean reversion: trades against displayed best-price displacement from a reference price.
- Informed: trades only when a displayed quote is favorable to an explicitly configured synthetic
  reference value; it does not inspect future historical events.
- Liquidity taker: sends a seeded-side market order only when displayed spread is within a
  configured threshold.

These are order-flow baselines, not market makers. They do not own PnL, fees, inventory, or risk.

## Consequences

- Phase 5 runs are reproducible from markets, agent config, run seed, and external command schedule.
- The runtime is intentionally centralized and single-threaded; processes, async subscriptions,
  retention/backpressure, and sharding require a later ordering/recovery ADR.
- Events/checkpoints remain in-memory and non-durable. This ADR makes no durable recovery claim.
- The exchange remains the sole production caller of `LimitOrderBook`; matching and lifecycle do
  not change.
