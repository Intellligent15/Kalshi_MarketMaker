# Phase 6: Baseline market making

## Purpose

Introduce a credible deterministic market-making baseline while keeping matching, account risk,
and strategy logic in their respective layers.

## Design

`pmm_risk::AccountRiskProjection` binds `AccountId`, `StrategyId`, `TraderId`, and one contract.
It consumes every exchange event in sequence order. `OrderAcknowledged` promotes a correlated
reservation to a live order; fills change signed inventory and remaining exposure; cancellations
remove live exposure; a correlated `CommandRejected` removes the reservation.

The exchange now includes the source ingress sequence on every event. Replay preserves recorded
ingress sequences instead of regenerating them, so command correlation is reproducible. The new
post-only flag is checked at the exchange boundary before book submission.

`MarketMakingCoordinator` pulls depth/trade events, then periodically computes passive bid/ask
quotes. It uses integer ticks only. Fixed spread offsets sit around a configured, last-trade, or
midpoint reference; inventory-aware mode shifts that common center by a bounded integer amount.
It cancels quotes whose desired price/size changed or whose logical age expired. The risk kill
switch schedules cancels and prevents replacement admission.

## Validation

- Existing Phase 1–5 tests remain green.
- Post-only rejection carries the originating ingress sequence and leaves displayed liquidity live.
- Risk admission projects acknowledgements and fills, rejects excess quantity, and releases a
  reservation when the exchange rejects a post-only command.
- Fixed-spread quotes, kill-switch cancellation, inventory skew, checkpoint continuation, and
  replay-preserved ingress correlation are independently tested.
- `pmm_demo --steps 5` is a deterministic manual walkthrough that prints quote decisions, fills,
  inventory/exposure, admissions, cancellations, and displayed depth.

## Known limitations

The implementation is an in-memory research baseline. It has no durable or transactional journal,
no money/PnL/collateral/settlement model, no account sharing, no retained terminal-order service,
and no asynchronous market-data fanout. It must not be described as paper-trading safe.
