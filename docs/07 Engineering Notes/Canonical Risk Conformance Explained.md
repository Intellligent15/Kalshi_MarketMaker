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

## Fixture conformance increment

The first fixture is deliberately small: reserve a buy, bind its ingress, acknowledge it, partially
fill it, then logically expire its remainder.  It has a reviewed state after each transition and is
run against both C++ and a test-only Python reference.  The resulting V2 trace now includes the
live order or pending reservation itself, not only the totals.  This proves state-machine agreement
for the shared lifecycle subset; it does not make the local whitespace oracle a production protocol.

## What, how, and why

### What changed

The risk trace now records the individual things that make up its totals: each live order and each
pending reservation.  The repository also has a small reviewed lifecycle fixture, its expected
state after every step, a manifest that hashes both, and a Python reference that exists only in the
test tree.

### How it works

1. A fixture admits a two-contract buy, binds its ingress ID, acknowledges order 11, fills one
   contract, then expires the remaining contract.
2. The Python test-only reference applies the same operations and compares every result and state
   to the reviewed expected trace.
3. The same fixture drives the real C++ oracle.  After each operation, `SNAPSHOT` returns the
   complete C++ state, which must equal the Python state.
4. Backtest V2 uses that same snapshot to write `pmm.risk_conformance_trace.v2`; its manifest
   hashes the trace as before.

### Why this shape

Comparing only final position can miss a reservation leak or a wrongly correlated order that later
balances out.  Comparing the complete state after every transition makes those defects visible at
the first bad operation.  Keeping Python under `python/tests/` gives an independent check without
allowing a second production risk engine to enter research runs.

### Debt in plain language

This is a foundation, not full conformance yet.  We proved one representative lifecycle path and
made all future traces inspectable.  The next work is repetitive but important: add the remaining
small fixtures, especially rejection, restore, and malformed-input paths, before treating the
suite as complete lifecycle coverage.

## Latest ingress-safety and fixture-integrity increment

### What we did

We closed three small state-machine holes and added one negative fixture:

- A pending reservation can now bind an ingress sequence only if no other reservation owns it.
- A zero-quantity fill is rejected before it can advance the risk watermark.
- Restoring a risk checkpoint now rejects invalid pending reservations and state that exceeds the
  configured order, exposure, or position limits.
- The fixture manifest now hashes its own canonical payload as well as every fixture and expected
  trace. A second fixture proves that duplicate ingress binding fails without changing state.

The standard `scripts/test.sh` command now runs the C++ CTest suite and the Python unittest suite.

### How we did it

```text
admit two reservations
        |
bind client 1 to ingress 7
        |
attempt to bind client 2 to ingress 7
        |
reject, retain both reservations exactly as they were
```

The C++ projection enforces the rule. The Python test-only reference implements the same narrow
rule. The reviewed fixture is replayed through both and `SNAPSHOT` compares watermark, position,
exposures, live orders, pending reservations, and kill-switch state after each step.

### Why we did it

Ingress is the link between a risk reservation and a later exchange response. If two reservations
could share it, an acknowledgement or rejection could release or activate the wrong reservation.
That is a risk-state correctness problem even if the final inventory later happens to balance.

The manifest-payload hash prevents a reviewer from trusting a manifest whose member list was
changed but whose individual files were not. Replaying the fixture twice and comparing raw bytes
checks that the test reference does not introduce hidden nondeterminism.

### What this still does not mean

This does not create a versioned production oracle protocol, durable full-run recovery, realistic
fills, queue priority, PnL correctness, paper trading, or live readiness. The whitespace oracle
remains the limited V1 local adapter. Full checkpoint/restore parity still belongs in a separate,
versioned test-only fixture harness.

## Completed lifecycle matrix

The shared corpus now checks every admission rejection, bad reservation binding, bad
acknowledgement or fill, command rejection, cancellation, logical expiry, bad event sequence, and
kill-switch transition. Each row compares watermark, position, all exposure totals, sorted live
orders, sorted pending reservations, and kill-switch state.

The V1 oracle did not grow: it is used only where its existing commands faithfully express the
fixture operation. Different-contract and foreign-identity boundaries stay direct-C++ only, and
checkpoint/restore remains the next separate versioned test-only harness.

## What we did, how we did it, and why

### What we did

We expanded two small fixtures into a reviewed lifecycle matrix. It covers the ways an order can
be refused before reservation, the ways a reservation can fail to bind to ingress, bad exchange
responses, ordinary lifecycle release, event ordering, and the kill switch. The matrix also checks
that the manifest and expected traces have not been silently changed.

### How we did it

Each fixture gives the test-only Python reference a binding, optional risk limits, and a short list
of operations. Its matching expected trace records the result and full account-risk state after
each operation. The same V1-compatible operation list is sent to the existing local C++ oracle;
after each response, `SNAPSHOT` must match the reviewed state exactly. Cases the V1 adapter cannot
say faithfully, such as a different contract on admission, stay in direct C++ tests.

### Why we did it

Final position alone can be correct after an earlier bug leaked a reservation or advanced a failed
event watermark. Comparing state at every step finds the first wrong transition. Keeping the
Python model under tests creates an independent check without making it a second research engine,
while freezing the whitespace adapter avoids accidentally presenting it as a production protocol.

### What remains next

The next correctness increment is not more V1 commands. It is a separate, versioned test-only
checkpoint/restore harness, followed by a direct C++ fixture executor so all three test surfaces
share the reviewed documents.
