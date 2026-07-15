# Research Execution Foundation Explained

## What we did

We added a safer bridge between the historical backtest and the C++ risk system that already
protects the simulator. A backtest can now ask the real C++ `AccountRiskProjection` whether a
quote is allowed, then tell it when the model acknowledges, fills, or cancels that quote.

We also added an optional cash-flow ledger. When enabled, it records the cash and fee effect of a
model-derived fill. It deliberately stops before PnL or settlement because the current data and
product terms do not justify those claims.

## How it works

```text
observed Level-2 data -> causal feature -> quote intent
    -> C++ risk admission -> model acknowledgement/fill/cancel event
    -> risk state + optional unresolved cash-flow ledger
```

The observed Level-2 stream remains outside the exchange and order book. It still says only what
the venue published. The backtest emits `ModelDerived` lifecycle events for hypothetical orders;
the C++ risk engine uses those events for reservations, exposure, active orders, and position.

`pmm_risk_oracle` is a tiny local program that exposes this C++ logic to Python. It is not an
exchange connection, does not submit orders, and does not turn observed L2 into matched venue
orders. Existing V1 configurations retain their compatibility Python risk model; a new experiment
must explicitly opt into `cxx_oracle_v1` with complete quantity/exposure limits.

## Why we did it

The old Python backtest gate was enough to demonstrate a pipeline, but it could disagree with the
production C++ risk projection about reservations and order lifecycle. Letting the C++ projection
be the canonical path removes that silent divergence for opt-in research runs.

The ledger exists for the same reason: it makes the currently assumed cash/fee policy visible in
artifacts instead of hiding it inside a future PnL number. A visible, limited ledger is more useful
than an apparently precise PnL calculation built on unknown fee, collateral, and settlement rules.

## What has not changed

- `LimitOrderBook` remains single-writer and contract-scoped.
- `ExchangeSimulator` remains the sole production caller of the book.
- Historical L2 remains an external observed projection.
- Phase 3 matching, post-only behaviour, ordering, watermarks, and integer core types are unchanged.
- `trade_touch_v1` remains a `ModelDerived` synthetic fill model; it is not execution realism.

## What comes next

ADR-009 now makes C++ risk mandatory for new V2 experiments, emits a canonical risk trace, and
uses a CMake target launcher instead of a machine-specific executable path. The checked-in V2
example is intentionally `no_fill_v1`: it proves deterministic lifecycle/risk handling, not
execution quality. V1 Python configurations remain reproducible compatibility baselines.

Next, capture timestamped own account executions and ingest explicit product metadata/lot terms
before calibrating or sensitivity-testing fill assumptions without look-ahead bias. Only after
those terms are explicit should the ledger grow into collateral, settlement, marking, or policy
PnL.

The implementation walkthrough and ranked follow-up register are now recorded in
[[07 Engineering Notes/Canonical Risk Conformance Explained]] and
[[07 Engineering Notes/Canonical Risk Conformance Critique]].
