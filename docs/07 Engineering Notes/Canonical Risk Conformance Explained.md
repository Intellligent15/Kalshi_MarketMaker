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
checkpoint/restore harness. Direct C++ fixture execution now makes all three lifecycle test
surfaces consume the reviewed documents.

## Direct-C++ fixture closure

The reviewed V1 documents now drive three separate test surfaces:

```text
fixture + expected trace + manifest
       |              |             |
Python reference   direct C++    eligible V1 oracle
```

The direct path calls `AccountRiskProjection` directly. It does not launch the oracle, so a
whitespace-protocol or snapshot-serialization change cannot hide a direct API regression. Before
replay, its test-only reader verifies the document bytes, SHA-256 hashes, schemas, safe file names,
and complete expected state. After every operation it compares watermark, position, all exposure
totals, sorted live orders, sorted pending reservations, and kill-switch state.

The oracle remains frozen. Its existing admission rejection number is now asserted exactly; other
domain failures remain generic `ERROR` responses whose prose is not a public interface. This work
does not include checkpoint/restore, durable recovery, realistic fills, PnL, or live readiness.

## What, how, and why of the closure

### What we did

We removed the last lifecycle-conformance representation gap. The reviewed V1 fixtures and expected
traces now drive a direct C++ test as well as the Python reference and eligible oracle integration.
The direct test compares the C++ projection's full state after every operation, including failed
operations. The oracle integration now checks the existing numeric admission rejection code rather
than only the broad rejection shape.

### How we did it

The C++ test-only reader loads `manifest.json`, checks its payload hash and every member hash, and
rejects noncanonical JSON, unsafe paths, malformed fields, invalid values, bad executor eligibility,
and internally inconsistent expected state. It maps each fixture operation to the existing public
`AccountRiskProjection` calls. It uses the same fixed 50-cent fill price already used by V1 because
V1 fixtures intentionally have no fill-price field and account-risk state does not depend on it.

The Python test independently validates the reviewed corpus, runs only eligible executors, and
parses `ADMISSION rejected <client> <code>` exactly for admission failures. For every other V1
domain failure, it accepts generic `ERROR` and compares the reviewed post-state instead of treating
the human-readable diagnostic as an interface.

### Why we did it

Before this increment, direct C++ tests and the reviewed fixtures could drift apart even while the
oracle path passed. Using one reviewed scenario representation removes that blind spot. Comparing
complete post-state after every transition finds reservation leaks, unintended watermark movement,
or incorrect ingress release at the first incorrect operation rather than after later events happen
to balance it out.

The reader is test-only so fixture review does not create a production JSON format or alter Phase 3
matching, core integer types, deterministic ordering, risk admission, or kill-switch ownership.

## Checkpoint/restore conformance

### What we did

We gave serialized risk state its own reviewed, versioned, test-only corpus. A checkpoint document
now writes down everything a restore needs — identity, limits, watermark, position, kill switch,
live orders, and pending reservations with their ingress bindings — and the corpus proves both
directions: a captured checkpoint has exactly the reviewed bytes, and an invalid checkpoint is
refused for exactly the reviewed reason. `restore` itself did not change behavior; it now
delegates to a pure `validate_checkpoint` that names which rule a bad checkpoint broke.

### How it works

```text
build state through lifecycle operations
        |
   capture checkpoint  ->  bytes must equal the reviewed document
        |
      restore
        |
  original and restored projections
        |
   every later operation runs on both
        |
identical results, identical state, identical re-serialized bytes
```

Roundtrip fixtures prove nothing is lost across capture and restore, including the kill switch,
a nonzero watermark, and partial-fill remainders. Document-restore fixtures prove the other
boundary: authored documents with duplicate order identifiers, zero quantities, duplicate client
intents, duplicate or zero ingress bindings, wrong contracts, non-post-only intents, or state
beyond the configured limits are each rejected with one exact `checkpoint_<category>` result.
The reader deliberately checks only syntax and canonical bytes on input documents so those
semantic defects reach the C++ projection instead of being masked by the test harness. Malformed
bytes, wrong hashes, unsafe paths, and unknown fields are separate reader rejections, each with
its own negative test in both C++ and Python.

### Why we did it

Restore is where serialized state and a second implementation matter most: a checkpoint that
silently drops a reservation or accepts an over-limit position can look fine until much later.
Comparing the original and restored projections after every subsequent transition finds the first
divergence, and asserting rejection categories — not prose — keeps diagnostics free to improve.
The frozen V1 whitespace oracle gained nothing, and the Python checkpoint module lives only under
`python/tests/` behind explicit entry points, so no second risk engine can leak into research
runs.

### What this still does not mean

Checkpoint conformance is in-memory round-trip evidence. It is not durable full-run recovery, not
a production serialization format, and it does not change any fill-model, PnL, settlement,
collateral, paper-trading, or live-readiness claim.

## The checkpoint increment in plain terms

### What we did

Risk state could already be checkpointed and restored in memory, but the only proof lived in a
handful of hand-written C++ tests. We wrote the state down: a checkpoint is now a small JSON
document listing who the account is, what its limits are, and exactly which orders and
reservations it holds. Twenty-one reviewed fixtures prove two things about it. Round-trip
fixtures prove nothing is lost: capture must produce exactly the reviewed bytes, and after
restoring, the original and the copy must agree on every later event, forever. Document-restore
fixtures prove bad state is refused: a checkpoint with a duplicated order, a zero quantity, a
shared ingress binding, the wrong contract, or state beyond the configured limits is rejected
with one exact named reason.

### How we did it

The production change is one pure function: `validate_checkpoint` names which rule a checkpoint
broke, in a documented first-failure order, and `restore` now calls it without changing its own
behavior. Everything else is test-only. A strict reader verifies the corpus bytes, hashes, and
schemas before anything runs — but it deliberately checks only *syntax* on input checkpoints, so
semantic defects still reach the real C++ projection instead of being filtered out by the test
harness. The same reviewed documents then drive two independent implementations: direct C++ and
a small Python model that lives only under `python/tests/`. Both must produce identical results,
identical complete state, and byte-identical re-serialized checkpoints after every step, and a
mutation matrix proves the reader rejects every tampering category it claims to.

### Why we did it

Restore is where hidden state corruption does the most damage: a dropped reservation or an
over-limit position can stay invisible until events later happen to balance it. Comparing the
original and the restored projection after every subsequent transition finds the first
divergence, not the eventual symptom. Writing rejection *categories* into fixtures — never error
prose — means diagnostics can improve without breaking reviewed evidence. And keeping the second
implementation in the test tree keeps the useful property of a cross-check without ever creating
a second production risk engine.

### Where the debt is now

The full ranked register lives in the critique note; the short version, most important first:
restore currently accepts a checkpoint whose individual order quantities admission would have
rejected, and that semantics question deserves an explicit decision; the strict rules for
reviewed captured documents and the test-only SHA-256 still lack their own negative tests; and
the corpus has no checked-in authoring helper, so adding a fixture means recomputing canonical
bytes and hashes by hand. None of these weaken what the suite currently proves — they bound how
far it can grow before the next contained increment.

## Admission-reachable record quantities

### What changed

Restore no longer accepts an individual live order or pending reservation larger than the
configured maximum order size. Both cases produce the same typed result,
`checkpoint_order_quantity_limit`, while a quantity exactly at the limit remains valid.

### Why both record classes use the same rule

A pending reservation is created only after admission approves its quantity. When the exchange
acknowledges it, the live order must match that reservation exactly. Later fills and order outcomes
can shrink the remaining quantity but cannot increase it. In plain terms, a quantity-six live
order cannot appear naturally if the account has always had a per-order limit of five, just as a
quantity-six pending reservation cannot.

This makes restored records consistent with the normal admission path. It does not prove that
every field in an authored checkpoint came from a real sequence of historical events; watermark,
position, and record combinations are still validated through their stated structural and limit
rules rather than by reconstructing a hidden history.

### How ordering stays predictable

Existing record-structure failures still win first. A duplicate live order remains a duplicate
failure even if the repeated record is also oversized. A wrong-contract, non-post-only, invalid-
ingress, or duplicate pending record likewise keeps its existing result. The quantity-limit check
then runs before active-order, aggregate-exposure, and position checks.

The corpus now separates these ideas cleanly. Oversized-record cases use larger aggregate limits,
while aggregate-limit cases use two individually valid records whose combined quantity is too
large. A separate accepted case places both a live order and a pending reservation exactly at the
boundary. Direct C++ and the independent test-only Python model execute all 26 reviewed documents.

### What remains next

The previous highest-priority semantic gap is closed. The next package remains intentionally
smaller: add negative tests for strict captured-checkpoint validation and standard SHA-256
known-answer vectors. Durable risk persistence, production serialization, process recovery, and
portfolio recovery remain separate design work.
