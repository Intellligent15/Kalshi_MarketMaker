# ADR-006: Baseline market making and risk admission

- Status: Accepted
- Date: 2026-07-13
- Scope: Phase 6

## Context

Phase 5 agents can produce normal exchange requests but do not own an account, inventory,
outstanding-order exposure, or command-risk boundary. A market maker must quote both sides while
preserving deterministic ordering and must not let a strategy mutate matching state or impersonate
an execution identity.

## Decision

Add `pmm_risk` outside `pmm_book` and `pmm_sim`. It owns an `AccountRiskProjection` for one
Phase-6 account/trader/contract binding. The projection applies every exchange event in contiguous
global sequence order and derives signed inventory from fills plus live/pending order exposure.

Strategies produce `OrderIntent`, which has no `TraderId`. Admission checks integer quantity,
active-order, pending, side-exposure, and worst-case position limits; it then binds the configured
trader identity and reserves exposure. A risk rejection never enters the exchange. An accepted
intent is bound to the exchange ingress sequence. `ExchangeEvent` now carries that exchange-owned
ingress sequence, allowing acknowledgements to promote reservations to live orders and rejections
to release them exactly.

`SubmitOrderRequest` adds `post_only`. The exchange rejects a post-only request that would cross
the current opposite best quote before invoking the book. This does not change Phase 3 matching.

`pmm_market_maker::MarketMakingCoordinator` owns quote decisions. It consumes a pull projection
to a stable watermark, derives a grid-rounded reference price, emits passive fixed-spread quotes,
and optionally shifts their shared center by an integer inventory skew. It uses cancel-and-replace:
an undesired or stale quote is cancelled first; a replacement waits unless simultaneous old/new
exposure already passes admission. A kill switch blocks new admissions while retaining cancels.

## Ordering and ownership

```text
exchange events -> market/risk projections -> quote decision -> admission -> exchange queue
```

The exchange remains the sole production caller of `LimitOrderBook` and owns IDs, lifecycle,
event sequencing, checkpoints, and replay. The book owns live matching state only. The risk
projection owns account inventory/exposure derived from events; a market maker sees it read-only.
The Phase-6 coordinator is the only component that enqueues its own quote/cancel commands.

## Consequences

- Phase 6 is deterministic and checkpointable in memory, but is not durable recovery.
- Risk is account-level and quantity-based. No fee, PnL, collateral, currency, or settlement
  policy is implied.
- The initial runtime is intentionally one account/strategy/trader/contract binding. A later
  multi-strategy account service must preserve the same central admission semantics.
- Fixed periodic decisions are the baseline. Cursor-gap handling, event-triggered repricing,
  backpressure, and asynchronous consumers require a later fanout/recovery ADR.
