# Phase 7 Retained Capture Evidence Critique

## Review boundary

This critique reviews the B2c tooling package before any retained product acquisition or observed
capture. It distinguishes implemented controls from evidence that cannot exist until B2c-P and the
single capture attempt are separately approved.

Severity uses 5 for a correctness or research-validity blocker, 4 for high evidence risk, 3 for
material operational/scale debt, 2 for bounded maintainability debt, and 1 for minor cleanup.

## Finding register

| ID | Finding | Severity | Status and required follow-up |
| --- | --- | ---: | --- |
| B2C-T01 | Current reviewed product intervals do not cover a new capture. | 5 | Open prerequisite. Approve B2c-P, pin selection evidence, and obtain complete opening/closing packages before strict processing. |
| B2C-T02 | No approved durable artifact destination or retention owner exists. | 5 | Open prerequisite. An ignored local directory cannot close the retained-evidence claim. |
| B2C-T03 | B2A-10 linear duplicate state is still present. | 4 | Measurement implemented; optimization deliberately deferred. Telemetry can close the missing measurement, not bounded-memory semantics. |
| B2C-T04 | No real 12-hour multi-market evidence exists yet. | 4 | Open by design. Do not mark B2A-11 closed before the one authorized attempt and reviewed index exist. |
| B2C-T05 | Real reconnect evidence is nondeterministic. | 4 | Retain a natural reconnect if observed. If none occurs, leave that portion of B2A-11 unobserved; never manufacture or recapture for it. |
| B2C-T06 | The measurement sampler relies on host `ps` semantics. | 3 | Machine/toolchain context and the one-second interval make results interpretable, but cross-platform comparison remains descriptive rather than identical. |
| B2C-T07 | Telemetry and canonical output cannot be published in one filesystem transaction. | 3 | Sidecars are create-new and prepared before publication, but full-run durability remains B6/B2A-15 debt. Do not claim crash-atomic evidence publication. |
| B2C-T08 | V4 still retains full inputs and typed outputs in memory. | 3 | Process-tree RSS will measure it. Do not optimize or redesign before the observed run. |
| B2C-T09 | One synchronous oracle remains per contract. | 3 | Per-contract timing is implemented and informs B2B2-05. Batching/native changes remain separately approved work. |
| B2C-T10 | A full retained V4 run may exceed the Git exception. | 2 | Use the fixed no-fill control and coarse approved decision interval. If the complete bundle exceeds 10 MiB, keep it external and leave B2B2-06 open. |
| B2C-T11 | Normalization identity still includes the repository-relative raw path. | 2 | Repeated runs use the same path. Path-independent identity remains B2A-17 debt. |

## What is implemented well

- Accepted Capture V2, normalization V3, feature V3, Backtest V4, Result V4, risk-trace, product,
  conversion, checkpoint, and refusal contracts remain unchanged.
- The fixed policy prevents post-outcome changes to duration, market count, budgets, substitution,
  reconnect requirements, and recapture behavior.
- Full verification checks exact membership and reconciles hashes with parsed counts rather than
  treating hashes alone as enough.
- Raw-only outcomes and unavailable closing product evidence remain representable without weakening
  strict downstream eligibility.
- Process-tree, duplicate-table, and per-contract oracle measurements have separate ownership.
- Instrumentation-on and instrumentation-off tests compare canonical artifact bytes.
- Capture and derived-stage interruption/cleanup semantics remain intentionally different and now
  have explicit characterization coverage.

## Closure judgment

The B2c tooling boundary is implementable and offline-testable, but B2c evidence is not complete.
B2A-10, B2A-11, B2B2-05, and B2B2-06 remain open or measurement-pending until actual reviewed
artifacts exist. The next bounded package is B2c-P product-evidence and capture-execution approval,
not B3.
