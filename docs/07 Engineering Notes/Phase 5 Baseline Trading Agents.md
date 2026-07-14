# Phase 5: Baseline trading agents

## Purpose

Provide reproducible synthetic participants and market-data consumption while preserving the
Phase 3 matching boundary and Phase 4 exchange ordering contract.

## Design

`SimulationCoordinator` owns agent scheduling. At a logical timestamp it first drains external
commands due at that time, pulls all resulting events through a stable watermark, runs every due
agent in `AgentId` order, then enqueues all intents in the same order. No agent can observe events
caused by another same-time decision until a later turn.

The coordinator maintains a depth projection keyed by `(side, price)`, so consumers do not depend
on depth-delta vector ordering. It starts from `ExchangeSimulator::snapshot` and applies
`BookDepthChanged` and `TradeExecuted` journal events. Continuation state is explicit: exchange
checkpoint, agent wakeups, decision ordinals, PRNG state, projection, and event watermark.

## Validation

`pmm_baseline_agents_test` verifies same-seed repeatability, same-time watermark isolation and
AgentId ordering, checkpoint continuation, and signal-agent decisions from pulled projections.
Phase 4 replay tests compare every event payload field rather than only timestamp, sequence, and
variant shape.

## Known limitations

- Agent commands receive normal exchange validation only; there is no account/risk gate.
- Exchange and coordinator checkpoints are reproducible in-memory values, not durable recovery.
- Baseline signals have no PnL, inventory, latency, fees, or historical-data adapter.

## Follow-up

Add versioned configuration files and experiment metrics before broad research. Add event-fed
inventory/risk admission and resolve Phase 4 durable-journal/event-batch debt before market making
or paper trading.

See [[07 Engineering Notes/Phase 5 Explained]] for a plain-language walkthrough and
[[07 Engineering Notes/Phase 5 Critique]] for the prioritized follow-up register.
