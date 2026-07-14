# Phase 5: Baseline trading agents

## Goal

Add deterministic synthetic order-flow participants around the Phase 4 exchange without coupling
strategy logic to matching, lifecycle, global IDs, or book mutation.

## Delivered scope

- `pmm_agents` and a single-threaded `SimulationCoordinator`.
- Stable `AgentId` / `TraderId` ownership, logical-time cadences, and per-agent seeded PRNG state.
- Pull-based projections from exchange snapshots and sequenced trade/depth events.
- Intent-only agent output; only the coordinator enqueues agent commands.
- Agent/coordinator checkpoints containing schedules, PRNG state, event watermark, and projections.
- Noise, momentum, mean-reversion, informed, and liquidity-taker baselines.
- Fixed-seed, same-time ordering, checkpoint continuation, and signal/projection tests.

## Explicitly deferred

- Risk limits, accounts, inventory/PnL, fees, collateral, and authorization.
- Durable journal/snapshot recovery, schema versions, checksums, and transactional event batches.
- Callback subscriptions, consumer retention/backpressure, multi-process agents, and sharding.
- Market making and inventory-aware quotes (Phase 6).

See [[02 Architecture/ADR-005 Deterministic Baseline Agents]] and
[[07 Engineering Notes/Phase 5 Baseline Trading Agents]].
