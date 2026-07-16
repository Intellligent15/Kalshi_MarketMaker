# Research Execution Foundation Critique

## Rating method

Impact is rated from 1 (minor) to 5 (blocks credible research or creates a material correctness
risk). Ease is rated from 1 (large architectural effort) to 5 (small, contained change). Priority
puts correctness and claim discipline ahead of convenience or throughput.

## Findings

| Finding | Category | Impact | Ease | Why it matters | Recommended handling |
| --- | --- | ---: | ---: | --- | --- |
| Existing checked-in V1 experiments still default to `python_reference_v1`; that implementation does not have C++ pending-reservation, ingress, or kill-switch semantics. | Correctness debt | 5 | 3 | The new canonical path is opt-in, so a future experiment can accidentally retain the weaker admission model. | Add a versioned C++-oracle experiment config and parity fixtures; deprecate the Python path for new research runs once migration is proven. |
| The oracle uses an ad-hoc whitespace protocol and hard-coded account/trader/contract IDs. | Interface debt | 4 | 3 | It is intentionally local, but has no formal schema, escaping rules, protocol version, or multi-account/product support. | Define a versioned research account-event schema before adding portfolio or process-boundary work; retain the narrow oracle only as a development adapter. |
| C++ oracle input requires whole-contract quantities and cent-aligned prices. | Representation debt | 3 | 2 | ADR-010 now validates exact venue grids/increments and refuses lossy conversion, but the core still cannot research valid sub-cent or fractional-quantity strategies. | Add richer core types only in a separately designed package; never weaken exact-conversion refusal. |
| The new ledger records unresolved model cash flows and fees only. | Accounting boundary | 5 | 2 | It does not model collateral, settlement, realized/unrealized PnL, fee rounding, or venue sell/short semantics. | Keep the non-claim prominent; add a double-entry ledger and sourced contract terms before exposing PnL metrics. |
| `AccountEventTruth` preserves provenance but is not yet materialized as a complete risk-event artifact. | Auditability | 3 | 3 | A result manifest names the risk engine, but cannot independently replay or inspect every risk transition. | Emit a hashed canonical risk trace before using the oracle for larger experiments. |
| The Python and C++ risk paths were retained without a full trace-by-trace conformance suite. | Unnecessary transitional complexity | 4 | 3 | The compatibility path is useful, but two implementations can drift if only broad outcome tests exist. | Addressed by ADR-009 for the V2 shared no-fill subset: C++ emits a hashed transition trace and V2 rejects Python risk. Broader lifecycle fixtures remain follow-up coverage. |
| The oracle invokes one synchronous request/response per lifecycle action. | Scalability | 3 | 3 | Subprocess I/O will dominate a dense or multi-market replay long before risk arithmetic does. | Replace it with a batch protocol or native binding only after trace correctness and profiling justify the added integration surface. |
| The runner still loads all features, orders, fills, and ledger entries into memory and sorts scheduled decisions on every insert. | Scalability | 3 | 4 | Current 20k-event data is safe, but long captures and parameter grids will grow memory and scheduling cost linearly or worse. | Stream JSONL artifacts and replace the sorted list with a stable heap after benchmark evidence. |

## Missing tests

| Missing test | Impact | Ease | Acceptance condition |
| --- | ---: | ---: | --- |
| Python-reference versus C++-oracle conformance trace | 5 | 3 | The same lifecycle fixture produces identical admissions, active exposure, position, and rejection reason. |
| Oracle protocol failure and malformed-command tests | 4 | 4 | Missing fields, non-integer inputs, broken subprocess output, and nonzero exit status fail closed without a partial result directory. |
| C++ oracle partial-fill/cancel/expiry integration | 4 | 4 | Remaining quantity, active-order count, and position stay aligned through partial fills and replacement cancellations. |
| Ledger fee rounding and buy/sell cash-flow cases | 4 | 4 | Fixed-point rounding is deterministic and a ledger invariant holds for both sides. |
| Oracle-run determinism regression | 4 | 3 | Two runs of the same C++-oracle config produce byte-identical orders, fills, ledger, and manifests. |
| Accounting-policy and product-term compatibility gate | 4 | 3 | Product/source/review/conversion hashes now fail closed in V3; accounting remains deliberately unimplemented. |
| Kill-switch and rejected-order lifecycle through the oracle | 4 | 4 | A rejected reservation is released and a kill switch blocks new admissions but permits cancellation. |

## Missing documentation

| Gap | Impact | Ease | Recommended addition |
| --- | ---: | ---: | --- |
| No checked-in runnable C++-oracle experiment example | 3 | 4 | Add one once product terms and a generated output refresh are deliberately reviewed. |
| No protocol/schema reference for oracle commands or risk traces | 4 | 3 | Publish a formal account-event schema before treating the adapter as an external interface. |
| No result-comparison tool or experiment report yet | 4 | 2 | Add manifest compatibility validation and a research report once the first sensitivity grid exists. |

## Possible optimizations

- Batch account events or use a native C++ binding after profiling proves subprocess overhead matters.
- Stream feature, order, fill, ledger, and risk-trace output rather than retaining full lists.
- Use a stable priority queue for scheduled decisions after retaining the current stable ordering contract.
- Store hashes incrementally while writing artifacts to avoid rereading large files.

## Priority order

| Priority | Work | Impact | Ease | Reason |
| ---: | --- | ---: | ---: | --- |
| P0 | Preserve `ModelDerived` and unresolved-accounting labels. | 5 | 5 | Prevents unsupported execution and PnL claims now. |
| P1 | Add C++-oracle parity and lifecycle conformance fixtures. | 5 | 3 | Closes the main Python/C++ risk-drift path. |
| P2 | Retain linked contract documents and add contemporaneous, multi-market product revisions. | 4 | 3 | Extends the implemented ADR-010 boundary before broader accounting work. |
| P3 | Add canonical risk trace plus manifest comparison gate. | 4 | 3 | Makes decisions and results auditable across runs. |
| P4 | Add calibrated/sensitivity execution experiments only after own-execution data arrives. | 5 | 1 | High research value, but blocked by required evidence. |
| P5 | Stream artifacts and batch oracle calls after benchmarks. | 3 | 3 | Important for scale, not current correctness. |

## Non-claims retained

This work does not establish calibrated fills, queue priority, venue-equivalent execution, fees or
PnL correctness, collateral, settlement, durable full-run recovery, paper trading, or live
readiness.
