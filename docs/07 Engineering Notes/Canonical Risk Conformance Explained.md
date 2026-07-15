# Canonical Risk Conformance Explained

## What we changed

Before this milestone, a historical backtest could either use a small Python admission gate or ask
the real C++ risk projection. The Python gate was useful for the first Phase-7 pipeline, but it
did not understand reservations, ingress binding, side exposure, event watermarks, or the kill
switch.

We introduced `pmm.backtest.v2`. New V2 experiments must use the C++ oracle. The old V1
configurations keep their original Python path so prior experiments remain reproducible instead of
changing behavior under the same name.

## How it works

```text
observed Level-2 -> causal feature -> quote intent
                                      |
                                      v
                         C++ AccountRiskProjection
                                      |
                 ModelDerived lifecycle transition
                                      |
                  risk trace + orders/fills/ledger
```

Python still owns observed-data replay, causal feature scheduling, and the deliberately synthetic
fill model. It does not send observed L2 into the exchange or order book. When a strategy produces
a quote, Python asks C++ risk to admit it. C++ reserves the worst-case exposure; Python binds the
synthetic ingress ID and sends a model-derived acknowledgement. Later model fills, cancellations,
and expiries are sent through the same projection.

V2 writes `risk-trace.jsonl`. Each row records the operation, its input, C++ result, and the C++
risk view after it ran. The result manifest hashes that trace alongside orders, fills, and ledger.
Running the same inputs, configuration, implementation, and build target twice produces the same
artifact bytes.

The configuration names the CMake target `pmm_risk_oracle`, not an absolute executable path. The
runner builds that target in a repository-relative build directory, reads CMake's generated target
path, and verifies that it did not escape the build directory.

## Why it matters

The important improvement is not a claim that the fill model became realistic. It did not.
`trade_touch_v1`, when used, remains `ModelDerived`; the first V2 example intentionally uses
`no_fill_v1`.

Instead, the improvement is that newly created research runs can no longer silently use weaker
risk semantics than the C++ simulator-side projection. A rejected C++ event now also leaves the
projection unchanged: acknowledgement, fill, and order-outcome validation occurs before state
mutation.

## What remains deliberately limited

- The oracle's transport is still a small local line protocol; the versioned trace is an artifact,
  not yet a complete versioned IPC specification.
- The trace records aggregate risk state, not enough order/reservation detail for independent
  replay.
- V2 supports a fixed whole-contract, cent-priced, post-only research baseline only.
- There is no calibrated fill model, queue position, fee/PnL correctness, collateral, settlement,
  paper trading, durable full-run recovery, or live-trading claim.

The next correctness milestone is fixture-driven transition parity plus explicit product terms.
