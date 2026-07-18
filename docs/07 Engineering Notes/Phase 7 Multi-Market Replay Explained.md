# Phase 7 Multi-Market Replay Explained

## The short version

The old backtest was one market in one box. Putting that function in a loop would create several
boxes that disagree about which market event happened first. B2b-2 keeps one global clock and
gives every market its own sealed strategy, orders, segment state, and risk projection.

## Why the global coordinator matters

Normalization records one authoritative ingress order. The coordinator preserves it while
latency moves derived actions forward in logical time. Every action keeps the record and product
watermark that caused it, so a timestamp tie cannot accidentally become a cross-market signal.

## Why risk is one projection per contract

The canonical C++ projection is deliberately bound to one contract. Reusing one projection for
several contracts would require new portfolio semantics and a new checkpoint shape. B2b-2 keeps
the proven projection unchanged and lets one coordinator own a deterministic contract map. This
is honest contract isolation, not portfolio risk.

## Why there are more artifacts

A final fill is not enough to audit a backtest. V4 records the feature-driven decision, submitted
intent, risk result, acknowledgement, cancellation or fill, and resulting risk view. Product,
contract, segment, and causal-watermark fields make accidental state crossing machine-checkable.

## What this still does not prove

Fills remain model-derived. There is no queue position, hidden liquidity, calibration, fees, PnL,
collateral, margin, settlement, portfolio risk, paper trading, or live-order behavior.
