# ADR-008: Calibrated execution, accounting, and research evaluation

- Status: Accepted
- Date: 2026-07-14
- Scope: Post-Phase-7 research foundations

## Context

Phase 7 provides immutable observed Level-2 replay, causal features, deterministic synthetic
fills, and a deliberately small Python risk gate. Level-2 cannot identify queue ownership or
counterfactual execution. The production C++ `AccountRiskProjection` has stronger semantics:
pending reservations, ingress correlation, acknowledgements, partial fills, contiguous event
watermarks, exposure limits, and a kill switch. A separate accounting and evaluation boundary is
needed before fee, collateral, settlement, PnL, or execution-quality claims are made.

## Decision

Historical observed data remains outside `ExchangeSimulator` and `LimitOrderBook`. Research uses
the following external pipeline:

```text
observed events -> causal features -> strategy intents -> canonical account-risk events
    -> labelled latency/fill model -> policy ledger -> markouts and result artifacts
```

`AccountRiskProjection` now accepts canonical `AccountEvent` values in addition to its exchange
adapter. `AccountEventTruth` labels an event as `Simulator`, `ModelDerived`, or `Observed`; the
label preserves provenance and does not change admission semantics. A small line-oriented
`pmm_risk_oracle` executable exposes the actual C++ projection to Python research orchestration.
It is not an exchange gateway and never receives observed L2 as exchange input.

V1 research accounting is opt-in and requires `pmm.accounting_policy.v1`. It records only
explicit model-fill cash flows and fees under an unresolved-settlement policy. It cannot report
settlement, collateral, realized/unrealized PnL, paper-trading results, or venue-correct economic
results.

## Execution fidelity

| Mode | Truth of fills | Permitted conclusion |
| --- | --- | --- |
| `no_fill_v1` | None | Lifecycle/risk control only |
| `trade_touch_v1` | `ModelDerived` | Deterministic systems baseline |
| Calibrated probabilistic | `ModelDerived` | Held-out scenario estimate after own-fill calibration |
| Queue approximation | reconstructed queue estimate; `ModelDerived` fill | Sensitivity to stated queue assumptions |
| External account fill | `Observed` | Actual account execution record |
| Paper fill | observed in named paper environment | Paper-environment behaviour only |
| Live fill | observed live account record | Actual live-account record only |

## Calibration and evaluation rules

Calibrated models require timestamped own submits, acknowledgements, cancellations, fills, fees,
and matched market data. Fitting is chronological: train on earlier windows, freeze parameters,
then score later validation/test windows. Cancellations and expiries are censored observations,
not automatic non-fills. Without such data, parameters are `Assumed` and runs must use a
predeclared latency/queue/fill sensitivity grid.

Result manifests must hash inputs, product terms, risk contract, execution parameters, latency
policy, accounting policy, and outputs. Runs with different source scope, partitions, execution
fidelity, latency policy, or accounting policy cannot be ranked as equivalent performance tests.

ADR-010 supplies the product/source/review/conversion hashes for `pmm.backtest.v3`. Fee type and
rounding sources are retained for compatibility, but V3 explicitly records `not_applied`; this does
not implement the accounting work described by this ADR.

## Consequences

- C++ is the canonical account-risk implementation; Python is orchestration and a compatibility
  reference only.
- Phase 3 matching semantics and core integer types are unchanged.
- The current oracle supports deterministic admission, acknowledgement, model-fill, rejection,
  cancellation, and view traces. It does not imply a production IPC or live gateway protocol.
- Persisted full-run checkpoints, calibrated/queue models, collateral, settlement, markouts, and
  PnL remain separate increments with their own tests.
