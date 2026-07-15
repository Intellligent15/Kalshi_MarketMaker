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
