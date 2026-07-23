# Phase 7 B2c-H V2 Refusal Codes

## Scope

This reference documents the additive `measure-v2` and `verify-v2` codes implemented by
`python/pmm_phase7_measurement.py` and `python/pmm_phase7_evidence.py`. It does not change the frozen
V1 `measure` or `verify` commands, their accepted inputs, first-failure ordering, output bytes, or
exit/stream behavior. It is separate from the product-term refusal-code reference.

On every nonzero V2 CLI path stdout is empty and the diagnostic is written to stderr. Verification
is read-only. A measurement preflight refusal spawns no child and publishes no report. After spawn,
the supervisor owns signal escalation, direct-child reap, group-quiescence checks, stream draining,
and report publication; the measured stage continues to own its canonical output and cleanup.

## `measure-v2` CLI result codes

| Code | Trigger | Exit | Report |
| --- | --- | ---: | --- |
| `MeasurementV2Completed` | Child exits 0, sampling is valid, and teardown/publication succeed. | 0 | Published; JSON report also goes to stdout. |
| `MeasurementV2RecordOnly` | Child exits 2 with valid measurement and successful teardown/publication. | 2 | Published; coded stderr only. |
| `MeasurementV2ChildFailure` | Child exits outside 0/2 without a stronger wrapper failure. | 1 | Published. |
| `MeasurementV2OperatorInterrupted` | Operator interruption initiates bounded shutdown. | 130 | Published. |
| `MeasurementV2RawBudgetExceeded` | Raw bytes exceed the absolute 1 GiB policy ceiling. | 130 | Published. |
| `MeasurementV2AggregateBudgetExceeded` | Package bytes plus publication reserve exceed the 5 GiB ceiling. | 130 | Published. |
| `MeasurementV2StreamBudgetExceeded` | Either stdout or stderr exceeds its independent 64 MiB ceiling. | 130 | Published. |
| `MeasurementV2SamplerFailure` | Process-group sampling is unusable. | 1 | Published with `sampling.error_code`. |
| `MeasurementV2WrapperFailure` | Stream, inventory, spawn/ownership, or other wrapper operation fails. | 1 | Published when final accounting/publication remains possible. |
| `MeasurementV2TeardownFailure` | Reap or live-group absence cannot be confirmed. | 1 | Published when final accounting/publication remains possible. |
| `MeasurementV2PublicationFailed` | Reserved report bytes are insufficient, atomic rename/write fails, or post-publication package accounting disagrees. | 1 | Not retained; owned partial/final report is removed. |

The first interrupt requests cooperative SIGINT finalization. A second interrupt accelerates to
SIGKILL but does not waive direct-child reap or group-quiescence checks. SIGTERM or SIGKILL makes
output finalization `forced` or `unknown` as recorded by the report.

## Measurement preflight refusal codes

These are exit 2, stderr-only, no-child, no-report outcomes.

| Code | Trigger |
| --- | --- |
| `MeasurementConfigInvalid` | Stage/command is empty or a measurement control is nonpositive. |
| `MeasurementOutputExists` | The final report or its `.partial` sibling already exists. |
| `MeasurementPathUnsafe` | Package/report/accounting/identity path escapes, is symlinked where forbidden, is missing, or has the wrong file type. |
| `MeasurementRootDuplicate` | A raw-root list or output-root list resolves to the same root more than once. |
| `MeasurementRootOverlap` | Accounting roots are equal or ancestor-related; exact raw/output equality is exempt only for `capture-v2`. |
| `MeasurementRawRootNotEmpty` | A `capture-v2` raw root already contains bytes. |
| `MeasurementFreeSpaceInsufficient` | Available package-root space is below 10 GiB; exact equality is accepted. |
| `MeasurementAggregateBudgetExceeded` | Pre-existing package bytes plus the publication reserve exceed 5 GiB. |
| `MeasurementPolicyV2SchemaMismatch` | An explicitly supplied Policy V2 document fails its runtime schema. |

`MeasurementInventoryUnstable` may occur during a preflight inventory walk, or after spawn while
sampling/finalizing. Before spawn it is an exit-2 refusal with no report. A runtime inventory error
is normally retained as the report's underlying wrapper error; if report-size fixed-point accounting
itself cannot stabilize, it propagates as exit 2 with stderr only and no published report.

## Measurement report error codes

These codes explain invalid sampling or teardown inside a published report; they are not alternate
success statuses.

| Code | Meaning |
| --- | --- |
| `MeasurementSamplerUnavailable` | Host `ps` could not launch or returned nonzero. |
| `MeasurementSamplerMalformed` | A process row is malformed, duplicated, or internally inconsistent. |
| `MeasurementSamplerLeaderMissing` | A required leader was absent from an otherwise parsed sample. |
| `MeasurementNoSuccessfulSample` | The child exited before any successful scheduled sample. |
| `MeasurementProcessGroupInvalid` | The spawned child did not own the expected fresh process group. |
| `MeasurementStreamReadFailed` | A stdout/stderr collector could not continue reading. |
| `MeasurementStreamDrainTimeout` | A collector did not reach EOF within the bounded join. |
| `MeasurementSignalPermissionDenied` | Signalling the owned process group returned EPERM. |
| `MeasurementTeardownIncomplete` | Direct-child reap or live-group absence was not confirmed. |
| `MeasurementInventoryUnstable` | Two bounded inventory snapshots disagree by path, length, or hash. |

ESRCH is recorded in the report's signal history as group absence and does not by itself waive the
direct-child reap. A successful zero-RSS sample is valid; sampler failure never becomes zero RSS.
If the constructed report violates `b2c-measurement-v2.schema.json`,
`MeasurementV2SchemaMismatch` propagates as exit 2 with stderr only and no report. That path is an
implementation invariant failure, not an operator-correctable request refusal.

## `verify-v2` refusal codes

All codes below are exit 2, stderr-only, read-only outcomes with no output artifact publication.

| Code | Trigger |
| --- | --- |
| `EvidenceV2ManifestSchemaMismatch` | Manifest JSON is malformed, fails the V2 schema, or has the wrong discriminator. |
| `EvidenceV2PayloadHashMismatch` | Canonical V2 payload hash is stale. |
| `EvidenceV2MembershipMismatch` | Declared paths/cardinality/counts/hashes disagree, a path is missing/extra/escaping/symlinked, or mounted bytes differ. |
| `EvidenceV2RoleSchemaMismatch` | A role selects the wrong schema file or kind, or a mounted JSON/JSONL value fails its bound schema/discriminator. |
| `EvidenceV2RoleMissing` | The materialized stage lacks a required fixed role or per-contract trace. |
| `EvidenceV2RoleForbidden` | A role is unknown, belongs to a later stage, or a trace appears before Backtest V4. |
| `EvidenceV2EligibilityMismatch` | Outcome, reviewed product coverage, materialized stage, or declared eligible stage disagree. |
| `EvidenceV2LineageMismatch` | Declared lineage or reconstructed market/product/measurement/Result/risk identities disagree. |
| `EvidenceV2RepetitionMismatch` | Repetition declarations, roots, inventories, member declarations, or exact bytes disagree. |
| `EvidenceV2CredentialScanMismatch` | Retained scan identity/ruleset/payload inventory/counts/status are stale or self-asserted. |
| `EvidenceCredentialLeak` | Deterministic scanning finds a private-key marker, authorization token, credential assignment, or suspicious secret-bearing filename. |

Verification refuses at the first reached boundary. Tests that target a later semantic boundary
must repair outer hashes and earlier declarations; callers must not depend on a different refusal
ordering than the implementation and frozen compatibility tests establish.

## Compatibility and closure boundary

V2 codes are additive and must not be interpreted as stronger meanings for V1 artifacts. A green
B2c-H is closed as offline control-plane hardening. Real subprocess tests validate the supervisor;
the fully mounted twelve-hour/three-market Synthetic package validates the verifier and is not a
production measurement. B2c-P is current, but venue access, acquisition, and the documented live
capture command remain unauthorized until its separate human approval gates pass.
