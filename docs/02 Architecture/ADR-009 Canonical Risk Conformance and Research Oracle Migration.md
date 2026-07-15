# ADR-009: Canonical risk conformance and research-oracle migration

- Status: Accepted
- Date: 2026-07-14
- Scope: Post-ADR-008 research risk migration

## Context

ADR-008 made the C++ `AccountRiskProjection` available to the Python backtest through a small
local oracle. The V1 Python compatibility gate remains intentionally smaller: it has no pending
reservation, ingress correlation, contiguous account-event watermark, side exposure, kill switch,
or checkpoint semantics. Retaining it as a default for new work would allow silent risk drift.

## Decision

New research configurations use `pmm.backtest.v2` and require `risk.engine:
"cxx_oracle_v2"`. C++ remains the sole canonical account-risk implementation. The old
`pmm.backtest.v1` configurations retain their selected V1 path for reproducibility; they are not
rewritten or silently migrated.

The V2 runner emits `pmm.risk_conformance_trace.v1` JSONL. Each record has a stable step number,
operation, typed input, result, and C++ risk view (watermark, position, open and pending exposure,
and kill-switch state). The trace is a research artifact with a manifest hash. It records
`ModelDerived` lifecycle handling and is not an exchange, venue, or observed-L2 event stream.

The local oracle is launched from a repository-relative CMake build directory and target name.
CMake generates the target artifact path after configuration; the runner verifies that the
resolved executable remains inside that build directory. Configurations therefore contain no
machine-specific executable path.

V2 accepts only the explicit research integer contract: whole-contract quantities, cent prices,
and post-only intents. A nonrepresentable value fails before a final result directory is published.
The first checked-in V2 configuration is a no-fill control; it proves lifecycle/risk control only.

## Conformance scope

The shared conformance subset is positive whole-contract, cent-priced, post-only intents under one
account/trader/contract binding with deterministic admit, ingress bind, acknowledgement, partial
or full fill, cancellation, command rejection, and contiguous event sequencing. V1 Python is a
compatibility reference only. `pmm.backtest.v2` rejects it explicitly rather than approximating
C++-only behavior.

C++ tests cover direct risk behavior beyond that runner subset: each admission rejection,
reservation/ingress binding, acknowledgements, partial/full fill, cancellation, invalid ordering,
kill switch, and checkpoint/restore. The projection validates an acknowledgement and fill before
mutating state, so an invalid event cannot partially update risk state.

## Determinism and failure handling

Risk traces, orders, fills, ledger, and manifests use canonical UTF-8 JSON with sorted keys and
newline termination. The manifest hashes every artifact. Identical input data, configuration,
implementation, and build target must yield byte-identical artifacts. The runner rejects malformed
launcher configuration, failed CMake target builds, target paths outside the build directory,
missing oracle responses, nonzero oracle exits, unsupported units, and invalid V2 risk selection.
It deletes the partial result directory on failure.

## Amendment: fixture-driven lifecycle conformance

The conformance suite uses versioned `pmm.risk_conformance_fixture.v1` inputs, reviewed
`pmm.risk_conformance_expected_trace.v1` outputs, and a manifest that hashes both files for every
case.  A transition trace is compared after every operation, including failures.  A complete state
contains the aggregate view plus stable, identifier-sorted live-order and pending-reservation
records.  Each record carries the identity and remaining/reserved quantity required to audit
ingress binding and release.

`pmm.risk_conformance_trace.v2` serializes that complete state.  It is emitted by the C++ oracle
through a deterministic `SNAPSHOT` response and hashed by the research result manifest.  The
request transport remains the deliberately small V1 local whitespace adapter; this amendment does
not call it a production or versioned IPC protocol.

The target intentionally shared subset is one account/trader/contract binding, nonnegative cent
prices, whole-contract quantities, post-only intents, admission, ingress bind, model-derived
acknowledge, partial/full fill, cancellation/logical expiry, command rejection, contiguous
watermarks, kill-switch transitions, and checkpoint/restore.  The first checked-in fixture covers
the reserve-to-expiry path; the remaining matrix is documented debt, not implied coverage.  The
Python implementation exists only below `python/tests/`; it is not a backtest engine and raises
explicitly for C++-only operations such as
exchange-event adaptation, order outcomes, foreign-trader handling, observed events, or portfolio
behaviour.  C++ remains canonical.

## Consequences and non-claims

This decision does not change Phase 3 matching, integer core types, deterministic ordering,
watermarks, post-only enforcement, external admission, or kill-switch ownership. Observed L2
remains outside `ExchangeSimulator` and `LimitOrderBook`; `trade_touch_v1` fills remain
`ModelDerived`.

It does not establish calibrated fills, queue priority, execution realism, PnL correctness,
settlement, collateral, durable full-run recovery, paper trading, or live readiness. Product-term
ingestion, fractional-lot support, calibrated/queue models, portfolio risk, and a high-throughput
oracle transport remain later work.

See [[07 Engineering Notes/Canonical Risk Conformance Explained]] for a plain-language walkthrough
and [[07 Engineering Notes/Canonical Risk Conformance Critique]] for the ranked debt register.

## Amendment: completed shared lifecycle matrix

The V1 corpus now covers every `AdmissionRejectCode`, ingress-binding failure, acknowledgement and
fill validation failure, command rejection, cancellation/logical expiry, invalid event ordering,
and kill-switch transition. Each reviewed transition records its result and complete post-state.

The V1 oracle is frozen as a compatibility adapter. Fixture integration uses only existing `INIT`,
`ADMIT`, `BIND`, `ACK`, `FILL`, `REJECT`, `CANCEL`, `KILL`, and `SNAPSHOT` commands. Contract
mismatch and foreign-identity cases stay direct-C++ only; checkpoint/restore remains the next,
separate versioned test-only harness. Generic V1 errors are fixture-level domain failures, not a
stable textual API contract.

## Amendment: direct-C++ fixture conformance closure

The checked-in V1 fixture corpus is now also executed directly against
`AccountRiskProjection` by a test-only C++ reader and executor. The reader verifies canonical
UTF-8 JSON bytes, manifest payload and member SHA-256 values, exact schemas and required fields,
safe local member paths, executor eligibility, and complete expected states before constructing a
risk projection. It is linked only into the CTest target; neither `pmm_risk` nor the frozen local
oracle gains a JSON dependency.

Direct C++ assertions compare the reviewed result and the complete state after every operation:
view totals, watermark, kill switch, identifier-sorted live orders, and identifier-sorted pending
reservations. An omitted legacy `executors` field means the established shared default
(`direct_cpp`, `python_reference`, and `v1_oracle`); an explicit field must be a unique subset of
those names. A fixture that V1 cannot faithfully express remains explicitly non-V1.

V1 integration now checks the exact numeric `AdmissionRejectCode` emitted by its existing
`ADMISSION rejected` response. Other V1 failures remain generic `ERROR` handling: tests compare
the reviewed unchanged state but do not make diagnostic prose a protocol contract.

Checkpoint/restore remains outside fixture V1 and outside this increment. It requires a separate,
versioned test-only fixture schema after this lifecycle-conformance closure.

## Amendment: versioned checkpoint/restore conformance

Serialized risk state now has its own reviewed corpus under
`python/tests/fixtures/risk_conformance/checkpoint_v1/`. The schemas are
`pmm.risk_checkpoint_conformance_fixture.v1`, `pmm.risk_checkpoint_conformance_expected_trace.v1`,
a manifest with the established payload and member SHA-256 rules, and an inline
`pmm.risk_checkpoint.v1` document carrying the complete restore input: account, strategy, trader,
and contract identity, all six configured limits, the watermark, net position, kill-switch state,
identifier-sorted live orders, and identifier-sorted pending reservations with their ingress
bindings. The serialization is test-only evidence, not a production or durability format.

A `roundtrip` fixture builds state through the existing V1 operation vocabulary, captures a
checkpoint whose canonical bytes must equal the reviewed document, restores immediately, and then
applies every later transition to both the original and restored projections, requiring identical
results, identical complete state, and byte-identical re-serialized checkpoints after every step.
A `document_restore` fixture restores an authored checkpoint document directly; its first
transition is either `restored` with the complete post-state or exactly one
`checkpoint_<category>` rejection, in which case nothing may continue.

The reader validates syntax and canonicality only for input documents: zero quantities, duplicate
identifiers, non-post-only intents, zero or duplicate ingress bindings, wrong contracts, and
limit violations stay expressible so `AccountRiskProjection::restore` is shown to reject them.
Reviewed captured documents are additionally strict. `pmm_risk` gains one addition: a typed
`CheckpointRejectCode` returned by the pure `validate_checkpoint`, which `restore` now delegates
to with an unchanged signature and unchanged accept/reject behavior. The first-failure order is
documented and fixture-asserted; rejection prose remains non-contractual.

Eligible executors are `direct_cpp` and the test-only Python reference through separate
checkpoint entry points; `ReferenceRisk.apply` still refuses checkpoint operations, and the frozen
V1 whitespace oracle is not a legal executor for this corpus. This amendment proves in-memory
capture/restore fidelity only. It does not establish durable full-run recovery, calibrated fills,
queue priority, execution realism, PnL correctness, settlement, collateral, paper trading, or
live readiness.
