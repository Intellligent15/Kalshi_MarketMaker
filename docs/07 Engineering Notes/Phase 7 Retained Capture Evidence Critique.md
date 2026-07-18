# Phase 7 Retained Capture Evidence Critique

## Review boundary

This review covers the B2c offline evidence and measurement tooling in `e6a211b`, its tests in
`4f77020`, and its first documentation package in `677c66d`. It is a review of the tooling, not of a
retained twelve-hour run: no contemporaneous product package, live capture, or retained B2c artifact
exists yet.

The central design choice remains sound: add an evidence control plane around the accepted Capture
V2 through Result V4 chain instead of changing capture, normalization, features, backtesting, or
risk semantics merely to collect measurements. The implementation also correctly keeps telemetry
outside canonical deterministic outputs.

The deeper review found two impact-5 hardening defects. They must be fixed before B2c-P is allowed to
acquire product evidence or start the live capture. Consequently, B2c tooling remains implemented,
but it is not yet operator-ready.

## Impact scale

| Impact | Meaning |
| ---: | --- |
| 5 | Blocks safe capture or makes a central retained-evidence claim unauditable. Must close first. |
| 4 | High correctness, security, measurement, or research-validity risk. Close before claiming B2c evidence complete. |
| 3 | Material operational, maintainability, or scale debt. May proceed only with an explicit boundary. |
| 2 | Bounded complexity or efficiency debt. Improve when the containing code next changes. |
| 1 | Cosmetic or low-value cleanup. Do not prioritize independently. |

The number rates impact, not implementation effort. Status is deliberately separate: an implemented
measurement can expose a problem without closing it.

## Executive findings

| ID | Primary category | Finding | Impact | Status / required closure |
| --- | --- | --- | ---: | --- |
| B2C-R01 | Missing test / operator safety | Interrupting `measure_command` can unwind the wrapper without terminating and reaping the fresh child process group. A live capture could continue after the operator believes it stopped. | 5 | Open blocker. Add `try/finally` process-group shutdown, bounded escalation and reap behavior, then test wrapper interruption with a child and grandchild. |
| B2C-R02 | Evidence correctness | Repetition inventories and much of the lineage graph are declarations inside the payload. The verifier checks their internal consistency but does not independently rebuild inventories or prove every product/measurement identity edge from mounted bytes. | 5 | Open blocker. Define a canonical inventory algorithm, retain both inventories, recompute them from mounted members, and verify the full raw-to-result/product/measurement graph. |
| B2C-R03 | Prerequisite evidence | Current reviewed product intervals do not cover a new capture. | 5 | Open prerequisite after hardening. B2c-P must pin selection evidence and obtain complete opening and closing reviewed packages. |
| B2C-R04 | Retention | No approved durable artifact destination, backup promise, or retention owner exists. | 5 | Open prerequisite after hardening. An ignored local directory cannot close the retained-evidence claim. |
| B2C-R05 | Missing test / evidence correctness | The mounted verifier checks a JSON member's declared `schema` tag, but it does not validate every member against the corresponding JSON Schema. A malformed policy, measurement, or telemetry document can pass if its tag and outer hash are updated. | 4 | Open. Add a role-to-schema validation registry and one-defect runtime/schema parity tests for all five new B2c formats. |
| B2C-R06 | Outcome modelling | Only the `backtest_v4` terminal stage has a complete required-role rule. `normalization_v3` and `features_v3` can be declared without requiring the artifacts that make those claims true. Exit 1, 2, and 130 combinations are only partially constrained. | 4 | Open. Define required and forbidden roles for every outcome/stage pair and test the entire matrix. |
| B2C-R07 | Resource enforcement | The policy declares a 5 GiB total evidence ceiling and 10 GiB free-space preflight, but the harness enforces only the explicitly supplied output-path budget. Neither total-package growth nor free space is enforced by this tooling. | 4 | Open. Add preflight and aggregate-budget checks, identity-bind their results, and test boundary/equality/overrun cases. |
| B2C-R08 | Measurement validity | Failure of host `ps` sampling silently becomes zero processes and zero RSS. The report has no `measurement_valid` or sampler-error field, so missing measurement can resemble a real zero. | 4 | Open. Fail closed or record an explicit invalid measurement with error count; never use zero as the absence sentinel. |
| B2C-R09 | Credential safety | The verifier scans only two PEM markers, while `credential_scan.status` is a self-asserted field. The stream scrubber replaces only the two known environment values. This is useful defense-in-depth, not a complete secret scan. | 4 | Open before external publication. Specify the scanner, scan filenames and bytes for configured secrets and common key/header forms, retain a scanner report hash, and test positive/negative cases without real secrets. |
| B2C-R10 | Scalability | Normalization still retains one payload hash per unique scoped sequence identity for the full run. Telemetry measures this linear table but does not bound it. | 4 | Measurement-ready, unresolved. Use the real run to quantify B2A-10; redesign only if measurements justify it. |
| B2C-R11 | Missing evidence | No real twelve-hour, three-market run exists, so long-duration stability, actual disk growth, peak RSS, throughput, reconnect behavior, and per-contract oracle cost remain unknown. | 4 | Open by design. A single approved attempt supplies evidence; it is retained even when discontinuous or incomplete. |
| B2C-R12 | Process control | Output-budget enforcement sends SIGINT once. A child that ignores SIGINT can run indefinitely, and temporary stdout/stderr files are outside the declared output budget. | 3 | Open with R01. Add grace-period escalation, bounded log accounting, and explicit termination metadata. |
| B2C-R13 | Publication durability | Canonical output and telemetry sidecars are not published in one filesystem transaction. A telemetry rename failure can leave canonical output published without its sidecar. | 3 | Accepted B6/B2A-15 debt. Characterize the state and document repair; do not claim crash-atomic evidence publication. |
| B2C-R14 | Scalability | Backtest V4 retains feature inputs, typed output rows, and risk traces in memory until publication. | 3 | Measurement-ready. Use process-tree RSS before proposing streaming changes. |
| B2C-R15 | Scalability / optimization | One synchronous C++ risk process is launched per contract, so startup cost and IPC waits grow with market count. | 3 | Measurement-ready for B2B2-05. Batching or native integration requires a separate design because it can affect failure and ownership boundaries. |
| B2C-R16 | Missing tests | The five focused B2c methods contain many `subTest` cases. Coverage is useful, but failures are grouped under broad methods and several requested defects lack stable, individually named tests. | 2 | Open maintainability debt. Split high-impact cases into named tests while retaining table-driven helpers. |
| B2C-R17 | Unnecessary complexity | Roles, V4 artifact names, schema names, and stage requirements are duplicated across Python sets, schemas, fixture construction, and documentation. Manual manifest assembly compounds the duplication. | 2 | Open. Introduce one internal role registry and a deterministic manifest/inventory builder after R02, without changing public formats. |
| B2C-R18 | Optimization | Every measurement sample recursively rescans all declared output trees and invokes `ps` for the whole host. This is simple and acceptable for three markets, but work grows with file count and sampling frequency. | 2 | Defer until measured. Prefer incremental file-size accounting or a platform sampler only if the real profile shows material overhead. |
| B2C-R19 | Portability | Process-tree RSS is a sum of sampled per-process RSS using host `ps`; it can miss short-lived children, double-count shared pages, and is descriptive rather than cross-platform identical. | 3 | Accepted measurement limitation. Record sampler identity and uncertainty; compare runs only with compatible machine/toolchain context. |
| B2C-R20 | Identity debt | Normalization identity still includes the repository-relative raw path, so repetitions must use the same locator even when the bytes are identical elsewhere. | 2 | Existing B2A-17 debt. Do not change accepted identity semantics inside B2c hardening. |

## Category analysis

### Unnecessary complexity

The package added five schemas and a 577-line evidence module because it has to describe policy,
package membership, generic process measurements, normalization internals, and per-contract risk
internals. Those concerns are genuinely different, so collapsing them into one untyped report would
make review worse. The avoidable complexity is duplication: `V4_ARTIFACT_SCHEMAS`, role sets, schema
constants, JSON Schema enums, tests, and prose each maintain overlapping knowledge.

The safest simplification is not fewer evidence concepts. It is one private role registry that can
drive validation, inventory construction, and fixture generation. This should follow R02 so the
registry represents a proven lineage algorithm rather than merely centralizing the current gap.

### Future technical debt

The largest debt is truth ownership. A payload hash proves that a manifest did not change after it
was written; it does not prove that all statements inside the payload were independently derived.
R02, R05, and R06 are therefore evidence-verification debt, not formatting preferences.

The next tier is operational debt: portable process control, aggregate storage enforcement,
credential scanning, and two-file publication. These do not alter market semantics, but they decide
whether an operator can safely create and preserve evidence.

The existing algorithmic debt remains explicit: linear duplicate tracking, all-in-memory V4 output,
one synchronous oracle per contract, and path-sensitive normalization identity. B2c should measure
these before optimizing them.

### Missing tests

The current suite proves valuable properties: index and mounted verification are read-only; stale
members and counts fail; symlinks and extra files fail; measurement reports are create-new; budget
overrun sends a signal; capture cleanup is characterized; and instrumentation does not change
canonical normalization or V4 bytes.

Before a live run, add individually named tests for:

1. KeyboardInterrupt terminates and reaps a child and grandchild, with no surviving process group.
2. A SIGINT-ignoring child is escalated after a bounded grace period.
3. Every new schema rejects one valid-looking but structurally invalid mounted member at runtime.
4. Every `furthest_eligible_stage` and exit-code combination has exact required/forbidden roles.
5. Canonical repetition inventories are rebuilt from two mounted trees and a one-byte mutation fails.
6. Product hashes reconcile with product map, catalog/review identities, Backtest V4 config, and Result V4.
7. Measurement and telemetry reports reconcile with the exact stage inputs and outputs they claim.
8. Free-space and aggregate-budget checks cover below, equal, above, and pre-existing-byte cases.
9. Sampler failure cannot produce an apparently valid zero-RSS report.
10. Secret scanning detects configured values, PEM variants, authorization-like fields, and suspicious
    filenames while avoiding false positives in hashes and public identifiers.
11. Telemetry publication failure leaves a documented, detectable state and repeated invocation
    refuses without mutating the canonical output.
12. Raw-only, record-only, discontinuous, interrupted, failed, and unavailable-product packages
    verify positively at exactly their permitted boundary.

The real retained run is not a CI test. CI must remain offline and bounded; its fixtures prove the
rules that will later be applied to external bytes.

### Missing documentation

The first operator guide explains the intended command and outcome boundaries well, but three
operator-facing items remain missing:

- a deterministic evidence-manifest and repetition-inventory authoring procedure;
- an exact credential scanner specification and review/sign-off record; and
- a process-control runbook covering interrupt, grace period, escalation, reap confirmation,
  partial outputs, and safe resumption/refusal.

The guide must also stop presenting the live measured command as usable until R01 and R02 close.
Machine comparison guidance should say explicitly that RSS values are compatible only under the
same sampler, OS semantics, sample interval, and comparable toolchain.

### Possible optimizations

Do not optimize the accepted pipeline merely because the review can name hot spots. First collect:

- normalized records per second and duplicate identities per processed raw record;
- peak process-tree RSS by stage;
- output bytes per raw record and per feature row;
- feature and backtest rows per second; and
- per-contract oracle startup, command count, blocking time, and lifetime.

If evidence supports action, the likely sequence is: reduce repeated filesystem scans, bound or
partition duplicate identity state, stream V4 artifacts, then evaluate oracle process reuse. Each
step needs artifact-byte equivalence and failure-semantics tests.

### Future scalability concerns

The fixed B2c claim is deliberately only three markets for twelve hours. It validates a useful
multi-market path but does not establish scaling to tens or hundreds of markets. Market count grows
subscription payload size, source-scope state, normalized and feature volume, in-memory V4 rows,
risk child count, trace volume, process-tree sampling cost, and manifest membership.

Duration mainly stresses raw/normalized volume and the unbounded duplicate table. Market count also
stresses concurrency and per-contract process ownership. These axes should be measured separately;
one three-market twelve-hour result cannot be extrapolated linearly without evidence.

## What was done well

- Accepted Capture V2, normalization V3, feature V3, Backtest V4, Result V4, risk-trace, product,
  conversion, checkpoint, and refusal contracts retained their meanings and bytes.
- The fixed prospective policy prevents post-outcome changes to duration, market count, budgets,
  substitution, reconnect requirements, and recapture behavior.
- Raw-only outcomes remain valuable without being relabelled complete or forced downstream.
- Natural reconnect evidence stays Observed while forced recovery tests stay Synthetic.
- Process-tree, duplicate-table, and per-contract oracle measurements have separate ownership.
- Instrumentation-on/off tests protect deterministic canonical outputs.
- Large bytes remain outside Git by default, with compact hash-bound control-plane artifacts.
- Current product coverage and storage ownership were honestly left as prerequisites rather than
  being hidden inside the capture step.

## Revised closure judgment

The architecture is directionally correct and the offline implementation is a strong foundation,
but the deeper audit found operator-lifecycle and independent-verification gaps that the first
critique missed. B2c is therefore:

- **implemented** as an additive offline control plane;
- **not operator-ready** until R01 and R02 close;
- **not evidence-complete** until product/storage prerequisites and the one retained attempt close;
  and
- **not a scalability proof** until B2A-10/11 and B2B2-05/06 have actual measurements and reviewed
  artifacts.

The next bounded package is B2c-H hardening for R01, R02, R05 through R09, and their focused tests.
B2c-P follows only after that package passes review. B3 remains later.
