# Phase 6: Baseline market making and risk admission

## Goal

Add deterministic passive market making around the Phase 4 exchange and Phase 5 pull-based
projections without moving risk, inventory, PnL, persistence, or market-data fanout into the book.

## Delivered scope

- `pmm_risk` with strong account, strategy, and client-intent identities.
- Identity-free post-only `OrderIntent` values bound to a permitted `TraderId` only by admission.
- Event-fed signed inventory, live-order exposure, pending reservations, quantity limits, and a
  kill switch outside the exchange/book.
- Exchange event ingress correlation so admission can reconcile acknowledgements and rejections.
- Exchange-level post-only rejection before a book call.
- `pmm_market_maker` with fixed-spread, tick-rounded, passive quotes; inventory-aware integer
  skew; stale-quote cancellation; and cancel-before-replace behavior.
- In-memory risk and market-maker checkpoints plus fixed deterministic replay/continuation tests.

## Explicitly deferred

- Durable journals, transactional event batches, serialized checkpoint schemas, and crash recovery.
- Fees, money scale, collateral, PnL, settlement, margin, and paper-trading safety.
- Account sharing across multiple strategies, portfolio/cross-contract risk, and market-data
  retention/backpressure.
- Amend/replace, latency modelling, event-triggered quote scheduling, live gateways, and ML inputs.

## Completion criteria

The market maker never calls an order book, every submitted quote passes account admission, risk
state follows the exchange event sequence, post-only quotes cannot intentionally take liquidity,
and checkpoint continuation preserves later decision and event order. See
[[02 Architecture/ADR-006 Baseline Market Making and Risk Admission]].
