# Canonical Risk Conformance Critique

## Rating method

Impact rates the consequence if the issue remains: 1 is minor and 5 blocks trustworthy research.
Ease rates the expected containment of the next corrective increment: 1 is broad or externally
blocked and 5 is small and local. Priority favors correctness and claim discipline over convenience.

## Findings

| Finding | Category | Impact | Ease | Why it matters | Recommended handling |
| --- | --- | ---: | ---: | --- | --- |
| V2 writes a Python-owned JSONL risk trace, but the oracle transport is still the unversioned whitespace protocol from V1. | Interface debt | 4 | 3 | The artifact is versioned, but request/response syntax, field escaping, and protocol capability are not. Calling the engine `v2` can overstate the boundary. | Specify and implement a versioned oracle request/response schema, or rename V2 as a runner/artifact migration until that protocol exists. |
| The trace contains aggregate risk view only; it omits canonical live-order and pending-reservation identities. | Auditability | 4 | 3 | A reviewer cannot independently confirm ingress correlation, individual remaining quantity, or reservation release from the trace alone. | Serialize stable live and pending records from `RiskCheckpoint` into trace state and add a trace replayer. |
| The only Python/C++ parity assertion covers the safe no-fill shared subset by comparing orders. | Correctness debt | 5 | 3 | It does not prove transition-by-transition equivalence for admission rejects, partial fills, command rejection, cancellation, expiry, or restore. | Add versioned fixtures with expected state after every operation and a test-only Python reference for the intentionally shared subset. |
| The V2 runner cannot exercise command rejection, kill switch, or checkpoint/restore through the oracle. | Lifecycle coverage | 4 | 3 | C++ supports these boundaries, but V2 research traces cannot demonstrate them. | Extend the oracle adapter only after its protocol is versioned; add dedicated fixture coverage before exposing those operations to experiments. |
| The V2 example uses `no_fill_v1` only. | Research coverage | 3 | 3 | This is the safe migration starting point, but it does not prove exact conversion and lifecycle behavior for `trade_touch_v1` fills. | Add a small synthetic integer-fill fixture before allowing a checked-in V2 trade-touch configuration. |
| The risk contract declares only whole contracts and cents, not product terms, lot rules, or a price grid. | Product-metadata debt | 5 | 2 | Risk can be internally consistent while accepting values that an actual venue contract would reject. | Ingest, hash, and validate explicit product terms before treating V2 results as broader than the fixed integer baseline. |
| The portable launcher rebuilds `pmm_risk_oracle` for every V2 run. | Unnecessary work | 2 | 4 | It is deterministic and safe, but slows parameter grids and couples a research run to local build availability. | Add a verified already-built mode keyed by target/source identity after correctness work is complete. |
| Exposure aggregation saturates its public quantity view at signed-int64 maximum if an impossible aggregate overflows. | Failure semantics | 3 | 2 | It prevents unsigned wraparound, but saturation hides the underlying invariant failure rather than reporting it. | Refactor aggregate/view construction to return `Result` and fail closed on impossible aggregate state. |
| Oracle I/O remains one synchronous subprocess request per risk lifecycle action. | Scalability | 3 | 3 | Dense multi-market replay will spend more time in pipes than risk arithmetic. | Batch trace operations or adopt a native binding only after profiling proves the need. |

| The initial fixture set covers the representative reserve-to-expiry path, but not every listed lifecycle and restore edge yet. | Coverage debt | 4 | 4 | The schema and complete trace are now exercised, but the fixture matrix still needs expansion before it is broad conformance evidence. | Add one focused fixture per admission rejection, invalid transition, command rejection, kill-switch case, and restore failure. |

## Missing tests

| Test | Impact | Ease | Acceptance condition |
| --- | ---: | ---: | --- |
| Full fixture-driven Python/C++ state parity | 5 | 3 | Every shared trace step has identical result, watermark, position, exposure, order, and reservation state. |
| V2 partial/full fill and expiry trace | 4 | 4 | Trace preserves remaining quantity through partial fill, full fill, and logical expiry. |
| V2 command rejection, kill-switch, and checkpoint/restore | 4 | 3 | Each operation is represented through the oracle and leaves the expected state. |
| Portable launcher failure matrix | 3 | 4 | Missing cache, failed build, malformed path file, target outside build directory, and dead child all fail without a final result directory. |
| Product-term conversion tests | 5 | 2 | Fractional lots, off-grid prices, and missing term hashes are rejected before admission. |
| Trace replayer and manifest tamper test | 4 | 3 | Modified trace/artifact hashes fail verification and valid traces reconstruct the recorded state. |

## Post-increment critique

Impact is the consequence of leaving the issue open; Ease is how contained the next corrective
increment should be.  Priority is impact first, then ease.

| Priority | Finding | Category | Impact | Ease | Recommended next action |
| ---: | --- | --- | ---: | ---: | --- |
| P1 | Only one fixture exercises the happy reserve/bind/acknowledge/partial-fill/expiry path. It does not yet cover every admission rejection, command rejection, bad ordering, kill switch, checkpoint/restore, or malformed fixture. | Missing tests | 5 | 4 | Add one small reviewed fixture per matrix row and require both direct C++ and Python-oracle parity for each transition. |
| P1 | The Python reference implements only the first path and does not yet model configured limits, command rejection, checkpoint/restore, or invalid transition cases. | Coverage debt | 5 | 3 | Expand it only alongside fixture cases; reject any operation not deliberately admitted to the shared subset. |
| P1 | The V2 trace is complete, but the oracle request transport remains the unversioned whitespace protocol. `SNAPSHOT` and `KILL` add capability without a formal request/response schema. | Interface debt | 4 | 3 | Define a separate versioned local protocol before adding more lifecycle commands to research orchestration. Keep V1 frozen. |
| P2 | Snapshot JSON is manually streamed in C++. Its fields are numeric or fixed enums today, but hand-written serialization will become fragile if arbitrary strings are added. | Technical debt | 3 | 4 | Keep the payload closed; introduce a tested canonical JSON serializer before any free-form field is added. |
| P2 | The fixture manifest hashes members, but has no independently stored hash of its own payload and no trace-tamper verifier yet. | Auditability | 4 | 4 | Add a manifest-payload digest and a trace replay/verification command that fails on a changed byte. |
| P3 | The oracle is still synchronously queried for a snapshot after every lifecycle transition. This is correct for conformance but expensive for dense replay. | Scalability | 3 | 3 | Keep it in tests; batch operations or add a native binding only after profiling production-sized replay. |
| P3 | Full trace rows retain complete order and reservation records. This is intentionally auditable but grows with open state times transitions. | Scalability | 2 | 3 | Stream trace writes and consider periodic full checkpoints plus compact deltas only after retaining a full-fixture replay oracle. |

## Missing documentation

| Gap | Impact | Ease | Required addition |
| --- | ---: | ---: | --- |
| No formal V1 local-oracle command reference, including `SNAPSHOT` and `KILL`. | 4 | 4 | Document grammar, response forms, failure semantics, and its explicit non-production status. |
| No machine-readable complete trace schema reference. | 4 | 4 | Publish field types, sort order, and compatibility rules for `pmm.risk_conformance_trace.v2`. |
| No fixture authoring guide. | 3 | 5 | Explain fixture/expected-trace/manifest layout, reviewed-answer policy, and the shared-versus-C++-only boundary. |

## Possible optimizations

- Add a fixture loader that drives direct C++ tests from the same reviewed inputs rather than only
  Python-oracle integration.
- Stream and hash `risk-trace.jsonl` while writing it instead of retaining the whole trace in memory.
- Batch a fixture's oracle operations after the transport is versioned; do not weaken
  transition-by-transition assertions.
- Use compact deltas only after a replayer proves they reconstruct the same complete state.

## Missing documentation

- A formal oracle transport specification, including exact V1 limitations and the intended V2 replacement.
- A trace-state schema that declares which data is sufficient for independent replay.
- A migration matrix for each legacy V1 experiment and its eligibility for C++ risk.
- Product-term and unit-conversion policy documentation.
- A result-comparison policy for manifests with different risk contracts or execution models.

## Possible optimizations and scalability concerns

- Stream orders, fills, ledger, and trace records instead of retaining all records in Python lists.
- Replace the sorted scheduled-decision list with a stable heap after a benchmark demonstrates need.
- Batch oracle commands or use a native binding after trace correctness is demonstrated.
- Cache a verified built oracle by CMake target and source identity rather than invoking a build for every run.
- Incrementally hash artifacts while writing them to avoid a second full read on large outputs.

## Priority order

| Priority | Work | Impact | Ease | Reason |
| ---: | --- | ---: | ---: | --- |
| P0 | Preserve `ModelDerived` labels and the no-PnL/non-execution claims. | 5 | 5 | Prevents unsupported research conclusions immediately. |
| P1 | Add full fixture-driven parity and complete trace state. | 5 | 3 | Closes the remaining Python/C++ transition-drift gap. |
| P2 | Add product terms, lot/price validation, and compatibility hashes. | 5 | 2 | Required before widening the fixed integer baseline. |
| P3 | Version the oracle transport and cover remaining lifecycle operations. | 4 | 3 | Makes the local adapter an auditable interface rather than a convention. |
| P4 | Add trace replay/tamper validation and result comparison. | 4 | 3 | Turns artifacts into independently checkable evidence. |
| P5 | Batch/stream/cache only after benchmark evidence. | 3 | 3 | Important for scale, but not ahead of correctness. |

## Retained non-claims

This work still does not establish calibrated fills, queue priority, venue-equivalent execution,
PnL correctness, collateral, settlement, durable full-run recovery, paper trading, or live
readiness.
