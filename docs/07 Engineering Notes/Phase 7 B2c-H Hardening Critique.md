# Phase 7 B2c-H Hardening Design Critique

## Review boundary

This critique reviews the B2c-H design recorded in
[[07 Engineering Notes/Phase 7 B2c-H Hardening Design]]. It does not review an implementation:
B2c-H code, schemas, tests, and retained evidence do not exist yet. A planned test or control remains
missing until implementation and validation prove it.

Impact rates the consequence if the issue is mishandled, not the effort required to address it.

| Impact | Meaning |
| ---: | --- |
| 5 | Can invalidate the central safety/evidence claim or permit unsafe operation. |
| 4 | High correctness, compatibility, security, or research-validity risk. |
| 3 | Material maintainability, portability, or operational debt. |
| 2 | Bounded complexity or efficiency debt; address when evidence justifies it. |
| 1 | Cosmetic or low-value concern. |

## Finding register

| ID | Category | Finding | Impact | Required treatment |
| --- | --- | --- | ---: | --- |
| B2CH-C01 | Unnecessary complexity | Five new document formats plus one structural validator/schema create six schema/validation surfaces before any retained run exists. | 3 | Keep each schema single-purpose, generate none dynamically, and reject fields that merely duplicate reconstructible facts. |
| B2CH-C02 | Unnecessary complexity | A single role registry must express fixed roles, per-stage rules, per-ticker product members, nine Result V4 roles, and dynamic risk traces. It could become a second hidden schema language. | 4 | Keep the registry private and declarative; formal schemas remain public authority. Add parity tests that fail when registry and schema disagree. |
| B2CH-C03 | Unnecessary complexity | Process supervision, stream redaction, filesystem accounting, sampling, signal escalation, and report publication are too much ownership for the existing 577-line evidence module. | 4 | Extract the measurement supervisor into one focused module and keep CLI/evidence reconstruction separate. |
| B2CH-C04 | Unnecessary complexity | Exact lineage reconstruction can duplicate checks already owned by product, feature, and Backtest V4 verifiers. | 4 | Delegate to existing verifiers, then add only B2c cross-boundary reconciliation. Do not fork domain semantics. |
| B2CH-D01 | Future technical debt | V1/V2 compatibility paths will permanently increase schema dispatch and refusal-order complexity. | 3 | Freeze adapters and test them; do not add silent upgrade or rewrite behavior. |
| B2CH-D02 | Future technical debt | The process guarantee is POSIX process-group scoped. A descendant that deliberately calls `setsid` escapes the boundary. | 4 | State the no-daemonization command contract. Treat arbitrary escaped-process containment as a separately approved cgroup/subreaper package. |
| B2CH-D03 | Future technical debt | The 5/5/5-second grace sequence and 64 MiB stream ceiling are prospective policy choices, not measured optimums. | 3 | Hash-bind them now for reproducibility; revisit only through an additive policy after observed evidence. |
| B2CH-D04 | Future technical debt | Canonical output and telemetry remain non-atomic across two renames. | 3 | Preserve R13 as characterized debt; verify/detect the partial state and document repair without claiming atomic publication. |
| B2CH-D05 | Future technical debt | Credential rules will need maintenance as credential formats and false-positive experience evolve. | 3 | Version the ruleset independently and retain its hash in every scanner report. |
| B2CH-T01 | Missing tests | No implemented test yet proves KeyboardInterrupt teardown of a child and grandchild. | 5 | Add a named offline PID-handshake test before operator readiness. |
| B2CH-T02 | Missing tests | No implemented test yet proves bounded SIGINT -> SIGTERM -> SIGKILL escalation for signal-resistant descendants. | 5 | Add separate one-defect tests for each escalation boundary and final group quiescence. |
| B2CH-T03 | Missing tests | No implemented test yet proves sampler failure cannot appear as valid zero RSS. | 4 | Cover launch failure, nonzero sampler exit, malformed rows, and exit-before-first-sample individually. |
| B2CH-T04 | Missing tests | No implemented matrix yet proves exact required/forbidden roles for every stage/outcome combination. | 4 | Add named positive packages and one-defect missing/forbidden-role tests. |
| B2CH-T05 | Missing tests | No mounted test yet rebuilds both inventories and detects path, length, hash, byte, extra, missing, and symlink defects independently. | 5 | Implement the full named inventory matrix; declarations alone do not close R02. |
| B2CH-T06 | Missing tests | No test yet verifies every mounted B2c JSON document and JSONL row against its complete schema. | 4 | Add one named malformed-but-correct-tag test per schema family. |
| B2CH-T07 | Missing tests | No test yet reconstructs every product, measurement, telemetry, Result V4, and trace identity edge. | 5 | Mutate one edge at a time after updating outer hashes; require specific read-only refusal. |
| B2CH-T08 | Missing tests | No synthetic-secret matrix yet proves scanner detection and benign-hash/public-ID exclusions. | 4 | Use only synthetic values and cover both false negatives and false positives. |
| B2CH-T09 | Missing tests | Telemetry rename failure and repeated invocation remain characterized but not individually named. | 3 | Prove the detectable partial state, owned cleanup, and refusal without canonical-output mutation. |
| B2CH-M01 | Missing documentation | The operator guide does not yet contain the final process-control runbook or safe resumption rules. | 4 | Update it only after implementation matches the design and tests pass. |
| B2CH-M02 | Missing documentation | No final schema migration/refusal-code reference explains V1 versus successor behavior. | 3 | Add the exact discriminator, compatibility, and new-code table during implementation. |
| B2CH-M03 | Missing documentation | Machine-comparison guidance is incomplete for sampler identity, OS RSS semantics, interval, and toolchain. | 3 | Document compatible-comparison requirements and prohibit portable benchmark claims. |
| B2CH-M04 | Missing documentation | There is no operator-reviewed scanner sign-off procedure. | 4 | Document scanner invocation, retained report review, failure handling, and prohibition on real-secret fixtures. |
| B2CH-O01 | Possible optimization | Sampling invokes host `ps` and inventories output trees repeatedly. | 2 | Measure overhead first; optimize with PGID-native/platform sampling or incremental size accounting only if material. |
| B2CH-O02 | Possible optimization | Repetition verification hashes files and then reads them again for exact byte comparison. | 2 | Preserve the simple auditable algorithm initially; combine streaming passes only with identical refusal evidence. |
| B2CH-O03 | Possible optimization | Full JSON Schema validation of every large JSONL row can be CPU-heavy. | 2 | Measure validator cost; precompile validators without reducing row coverage. |
| B2CH-O04 | Possible optimization | Streaming redaction must retain boundary state for every configured secret/rule. | 2 | Prefer a small deterministic matcher; avoid general regex/entropy engines until profiling warrants them. |
| B2CH-S01 | Future scalability | Duration grows raw/normalized volume, inventory work, schema-validation work, and duplicate-state memory. | 4 | The twelve-hour run measures one bounded point; do not extrapolate to longer retention without evidence. |
| B2CH-S02 | Future scalability | Market count grows product members, role cardinality, risk processes, traces, and lineage edges. | 4 | Keep the first claim fixed at three markets; later scale requires a separate measured design. |
| B2CH-S03 | Future scalability | Result V4 still holds feature inputs, typed rows, and traces in memory until publication. | 3 | Keep R14 measurement-ready; do not stream outputs inside B2c-H. |
| B2CH-S04 | Future scalability | One synchronous risk oracle per contract makes process count and IPC cost grow with markets. | 3 | Measure B2B2-05 first; batching or native integration is a separate semantic/failure-boundary design. |
| B2CH-S05 | Future scalability | Credential scanning and exact byte comparison are linear in retained package size. | 2 | Accept linear bounded work for the 5 GiB policy; consider chunked parallel reads only after measurements. |

## Category analysis

### Unnecessary complexity

The design is intentionally explicit because the claims are cross-artifact and safety-sensitive. The
main risk is not the number of concepts; it is maintaining the same knowledge in schemas, Python
sets, tests, fixtures, and prose. The private role registry reduces duplication only if it stays a
thin routing table. If it grows its own conditional language, it becomes harder to audit than the
duplication it replaces.

The measurement supervisor deserves a separate module. Process ownership and evidence semantics
change for different reasons and have different failure modes. Keeping them together would make
future reviews less reliable.

### Future technical debt

Additive schemas preserve history but create permanent compatibility work. That cost is justified;
silently strengthening V1 would be worse. The implementation should make the split obvious and
avoid convenience conversions that make a V1 artifact appear to support V2 claims.

The POSIX process-group boundary is honest but not universal containment. Documenting that limit is
better than adding fragile PID-chasing logic. Platform-specific containment should be considered only
if future commands need to daemonize or run in environments where PGID inspection is insufficient.

### Missing tests

The design contains a detailed named matrix, but none of it exists yet. The highest-impact tests are
the child/grandchild teardown, signal escalation, independent inventory rebuild, complete lineage
mutation, and stage/outcome matrix. These tests are acceptance gates, not follow-up polish.

Tests must remain offline, bounded, and synthetic. Process tests need PID handshakes and bounded
polling rather than sleeps that can hang CI. Evidence mutations must update outer hashes so each test
reaches the intended semantic boundary instead of failing early for the wrong reason.

### Missing documentation

This design and its explanation make the intended behavior understandable, but they are not an
operator runbook. Commands, exact new refusal codes, repair steps, and scanner sign-off must be
written from the implemented behavior after validation. Publishing them now would risk documenting
an interface that later changes.

### Possible optimizations

The first implementation should favor auditability over cleverness. Repeated filesystem walks,
double reads for hash-plus-byte comparison, and row-level schema validation are acceptable within
the fixed 5 GiB package until measurements show otherwise. Any optimization must preserve exact
artifact bytes, first-failure behavior, and individually named negative tests.

### Future scalability concerns

B2c measures one twelve-hour, three-market point. Duration and market count stress different axes:
duration increases retained volume and long-lived state; market count increases simultaneous product,
process, trace, and lineage cardinality. Neither axis should be extrapolated from the first run.

## What the design did well

- It separates operator interruption, policy stop, child failure, and measurement invalidity.
- It gives one owner responsibility from spawn through signal escalation, reap, and report publish.
- It reconstructs evidence instead of trusting manifest declarations.
- It preserves raw-only and record-only evidence without weakening strict eligibility.
- It uses additive formats rather than changing accepted bytes retroactively.
- It keeps product verification, canonical pipeline semantics, and risk/checkpoint behavior in their
  existing owners.
- It leaves unmeasured optimization work explicitly open.

## Judgment

The design is coherent and appropriately bounded for B2c-H. Its largest implementation risks are
process-control correctness, duplicated truth across registry/schema/runtime, and test-suite breadth.
It is approved to serve as the bounded implementation specification, but it does not itself close
any B2c finding or authorize B2c-P.
