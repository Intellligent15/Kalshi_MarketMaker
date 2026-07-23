# Phase 7 B2c-H Evidence-Verifier and Measurement-Lifecycle Hardening Design

## Status and authority

This document records the consolidated B2c-H design and its implementation reconciliation. It does
not authorize product acquisition or a venue capture. The living roadmap remains authoritative for
status and work order; ADR-007 and ADR-010 through ADR-013 remain authoritative for accepted artifact
meanings.

B2c-H is an additive control-plane hardening package. It must preserve every accepted Capture V2,
normalization V3, feature V3, Backtest V4, Result V4, product, conversion, risk, checkpoint, and
refusal contract.

## Implementation status: closed offline milestone

Commits `842db83`, `d19ac3b`, and `38fb667` implement the initial additive V2 slice. Commits
`df905ff` and `ce0218f` close the audited supervisor and mounted-verifier defects: post-leader-exit
descendants are terminated, second interruption accelerates without skipping reap, sampler/stream
failures are explicit, storage/path invariants fail closed, and mounted evidence is checked through
an immutable role registry, runtime schemas, exact membership, repetition bytes, reconstructed
lineage, product coverage, and a recomputed credential scan. V1 commands remain unchanged.

The closure series `e70098e`, `4236943`, `aa04c70`, `6b6c176`, `b1d6b2f`, `65b5989`, and `79801e7`
adds Synthetic product truth, immutable pre-spawn identities, atomic telemetry refusal behavior, a
fully mounted strict verifier-conformance package, exact path/hash and product/Result lineage,
canonical repetition binding, portable mounted Backtest paths, and operational-approval checks.
Validation passes formatting, 68 measurement, 72 evidence, 11 operator, 253 integrated B2c/product/
Phase 7/multimarket, 307 full Python, and 78 CTest tests.

B2c-H is closed as an offline control-plane milestone. Real subprocess tests validate Measurement
V2 lifecycle behavior. The fully mounted twelve-hour/three-market package is Synthetic; its
`synthetic-fixture-v1` measurement documents are constructed verifier inputs, not twelve-hour
supervisor output. It does not prove venue access, observed product coverage, production resource
use, long-run stability, or capture readiness. B2c-P is current but remains stopped at Gate A.

## Objective

B2c-H is intended to close the operator-safety and independent-verification blockers identified as
B2C-R01, B2C-R02, B2C-R05 through B2C-R09, and B2C-R12. It must:

- stop every live member of the measured process group on every post-spawn exit path;
- distinguish operator interruption, policy termination, child failure, and measurement failure;
- independently reconstruct repetition and lineage from mounted bytes;
- validate every mounted JSON and JSONL document against its runtime schema;
- enforce exact outcome/stage membership and storage rules;
- represent invalid sampling explicitly rather than as zero RSS; and
- bind a deterministic credential scan to retained evidence.

It must not acquire product evidence, access a live feed, perform a capture, change market-data
semantics, change risk/checkpoint refusal behavior, or begin B2c-P, B3, Phase 8, or live operations.

## Compatibility strategy

Do not tighten accepted B2c V1 schemas in place. V1 documents remain readable under their frozen
meaning. New retained B2c evidence uses additive successors:

- `pmm.phase7.b2c_evidence_policy.v2` adds fixed measurement-control values while retaining the V1
  capture, selection, outcome, and retention policy;
- `pmm.phase7.b2c_evidence_manifest.v2` binds mounted product members, repetition inventories,
  measurement identities, and a scanner report;
- `pmm.phase7.b2c_measurement.v2` records sampler validity, exact storage accounting, termination,
  signals, reap, and role-qualified input/output identities;
- `pmm.phase7.b2c_repetition_inventory.v1` records canonical file inventories; and
- `pmm.phase7.b2c_credential_scan.v1` records the deterministic scanner identity and result.

The implementation must also add a formal structural validator for existing
`pmm.risk_conformance_trace.v2` rows. That validator documents existing bytes; it does not change
their schema discriminator or meaning.

The existing `measure` and `verify` subcommands remain frozen V1 compatibility surfaces, including
their current validation depth, stdout, stderr, and exit behavior. The stronger mounted verifier is
exposed as additive `verify-v2`. The operator-ready supervisor is exposed as additive `measure-v2`;
only that subcommand accepts Policy V2 and publishes Measurement V2. This prevents old automation
from silently acquiring stronger refusal or exit meanings.

The fixed policy V2 measurement controls are:

| Control | Value |
| --- | ---: |
| Sample interval | 1 second |
| SIGINT grace | 5 seconds |
| SIGTERM grace | 5 seconds |
| SIGKILL/group-absence confirmation | 5 seconds |
| Stdout ceiling | 67,108,864 bytes |
| Stderr ceiling | 67,108,864 bytes |
| Report-publication reservation | 1,048,576 bytes |

These values are prospective controls for the one B2c run. They are not performance targets or
claims about future workloads.

## Implementation ownership

The smallest ownership boundary is:

- `python/pmm_phase7_evidence.py`: CLI dispatch, V1 compatibility, role registry, mounted verifier,
  inventory construction, lineage reconstruction, and credential scanning;
- new `python/pmm_phase7_measurement.py`: process supervision, stream collection, sampling, storage
  accounting, shutdown, and Measurement V2 publication;
- `schemas/historical/`: additive B2c successor schemas and the existing-trace structural schema;
- `python/tests/test_phase7_b2c_evidence.py`: focused evidence, lifecycle, schema, and compatibility
  tests; and
- an optional small offline helper executable/script owned only by process-lifecycle tests.

Capture, normalization, features, backtesting, risk-oracle IPC, checkpoints, fixtures, and accepted
product packages are not implementation targets.

## Process ownership and shutdown state machine

The measurement supervisor owns exactly one new session/process group and its direct child:

```text
PREFLIGHT
  -> RUNNING
  -> STOP_REQUESTED
  -> SIGINT_GRACE
  -> SIGTERM_GRACE
  -> SIGKILL_CONFIRMATION
  -> DIRECT_CHILD_REAPED
  -> PROCESS_GROUP_QUIESCENT
  -> REPORT_PUBLISHED
```

### Preflight

Before spawn, the supervisor must:

1. reject an existing final or `.partial` report;
2. resolve every configured path beneath its declared root;
3. reject symlinks, escapes, duplicate roots, and overlapping accounting roots;
4. compute initial raw and aggregate inventories;
5. require free space greater than or equal to 10 GiB;
6. require initial aggregate bytes plus the 1 MiB control-plane reservation to remain within 5 GiB;
   and
7. require a create-new capture raw root to be absent or empty.

A preflight refusal spawns no child, publishes no report, and mutates no measured output.

### Running ownership

Launch the unchanged command with `start_new_session=True`. Capture its PGID immediately and verify
that the direct child is the process-group leader. Descendants such as Backtest V4 risk oracles
inherit the group because they do not create new sessions.

Every post-spawn path is enclosed by one cleanup owner. The direct child reaching an exit status is
not sufficient: the supervisor must also check for live descendants in the owned PGID.

### Stop sequence

For operator interruption or a policy stop:

1. send SIGINT to the PGID;
2. continue draining streams and checking group state for up to five seconds;
3. send SIGTERM if live members remain;
4. wait up to five more seconds;
5. send SIGKILL if live members remain;
6. wait up to five seconds for direct-child reap and group quiescence; and
7. publish the report only after teardown facts are final.

A second operator interrupt accelerates to SIGKILL but cannot skip stream draining, direct-child
`wait`, or final group confirmation. `ESRCH` means the group is absent. `EPERM`, a deadline expiry,
or surviving live members is a teardown failure.

POSIX cannot portably reap grandchildren. The exact guarantee is therefore: reap the direct child
and use a successful PGID-scoped process-table sample to confirm no non-zombie member remains. A
remaining zombie is recorded but is quiescent: it cannot execute or write and cannot be reaped by
this supervisor unless it is the direct child. `EPERM`, an unreadable process table, or a live member
at deadline is teardown failure. Retained-evidence commands must not daemonize or escape with
`setsid`; arbitrary escaped-process containment would require a separate platform-specific
cgroup/subreaper design.

## Termination and CLI semantics

For `measure-v2`, the report records the stop initiator, stop reason, exact child status, every
signal attempt, grace expiry, escalation, direct-child reap, group-absence confirmation, and whether
child output finalization was cooperative or forced/unknown.

| Path | Report | CLI behavior |
| --- | --- | --- |
| Preflight/config/output-exists refusal | None | Exit 2; empty stdout; coded stderr |
| Child success | Valid report after reap | Exit 0; JSON stdout; empty stderr |
| Child expected refusal | Retained report | Exit 2; empty stdout; coded stderr |
| Child or wrapper failure | Failed/invalid report when possible | Exit 1; empty stdout; coded stderr |
| Operator interruption | Retained report after teardown | Exit 130; empty stdout; coded stderr |
| Raw/aggregate/stream budget stop | Retained policy-stop report | Exit 130; empty stdout; coded stderr |
| Report publication failure | Remove only owned `.partial` | Exit 1; no final report |

Other child statuses normalize to wrapper exit 1 while the exact status remains in the report.
The wrapper never deletes measured outputs. Capture V2 retains/finalizes raw evidence according to
its accepted contract; derived commands keep their existing partial-cleanup ownership. Forced
escalation must never relabel raw bytes as cleanly finalized.

## Resource and sampler semantics

Raw and aggregate budgets are absolute logical-byte ceilings. Equality passes; one byte over stops
the group. Pre-existing upstream bytes count toward the aggregate ceiling and are also reported
separately from growth. Aggregate accounting includes every regular file under the retained-package
root: pre-existing product/upstream members, raw and derived outputs, measurements, telemetry,
inventories, scanner report, and final manifest.

Before spawn, 1 MiB is reserved for all still-unpublished control-plane documents, not just the
measurement report. At runtime the invariant is `current aggregate bytes + remaining reservation <=
5 GiB`. Each create-new control document consumes part of that reservation; unused reservation is
released only after the final manifest is published. A document exceeding the remaining reservation
is a publication failure, never permission to exceed the aggregate ceiling.

Logical accounting enumerates each regular package-relative path once. It rejects symlinks,
overlapping roots, escapes, and persistently unstable inventories. Free space is a pre-spawn gate,
not a promise that 10 GiB remains free throughout the run.

Unbounded temporary logs are removed. Stdout and stderr are drained concurrently through bounded,
boundary-aware redaction/hash collectors. The combined bytes are counted even though the bytes are
not retained. After the 64 MiB threshold, collectors continue draining and discarding while the
supervisor stops the group, preventing pipe deadlock.

The process sampler requests PID, PGID, RSS, and state, then selects the owned PGID. It rejects
malformed/duplicate rows, negative values, and inability to observe a still-running leader. The
first sampler failure makes the measurement invalid and initiates bounded shutdown.

Measurement V2 records sampler identity, attempted/successful samples, stable error category,
zombie count, and nullable peaks. Zero process count or RSS is valid only after a successful sample
actually observes zero; no successful sample produces `null`, never a fabricated zero.

## Role and stage model

One private immutable role registry owns schema tag, schema filename, JSON/JSONL kind, cardinality,
stage introduction, and lineage rules. It drives verifier behavior and focused-fixture construction.

Always-required roles are:

```text
capture_policy
raw_frames
raw_metadata
capture_measurement
credential_scan_report
```

Manifest V2 separates `furthest_materialized_stage` from the independently derived
`furthest_eligible_stage`. Materialized means the last stage whose complete role set is mounted.
Eligible means the furthest stage the observed completeness and reviewed product coverage permit,
whether or not the operator chose to run it. The verifier reconstructs both; a raw-only successful
package can therefore be materialized at `raw` while eligible for a later stage.

| Furthest materialized stage | Additional required roles | Forbidden roles |
| --- | --- | --- |
| `raw` | None | All normalization, feature, backtest, telemetry, and repetition roles |
| `normalization_record_only` | Records, normalization manifest, source scopes, product map, normalization measurement/telemetry, two normalization inventories | All feature and backtest roles |
| `normalization_v3` | Same normalization roles and inventories; complete observed interval and reviewed products | All feature and backtest roles |
| `features_v3` | Normalization set plus feature rows/manifest, feature measurement, two feature inventories | All backtest/result/risk roles |
| `backtest_v4` | Feature set plus config, Result V4 manifest, backtest measurement, risk telemetry, nine typed streams, one trace per contract, and two backtest inventories | Unknown or extra roles |

Exit 1, 2, or 130 may materialize only raw or record-only normalization. Strict normalization,
features, and backtest require reviewed coverage for all selected tickers. Stage eligibility is
derived independently from exit, completeness, product, and lineage facts.

Product roles are orthogonal to materialized pipeline stage and are exact per selected ticker. A
ticker's verifier-derived status is one of `unavailable`, `opening_only`, or `bracketed`. Unavailable
forbids every product-package role. Opening-only requires exactly one package root containing
`product_terms`, `product_review`, `product_source_manifest`, all source members named by that
manifest, and any version-required `product_acquisition_policy`, `product_evidence_profile`, and
`product_evidence_map`; it also requires the referenced shared `product_conversion_policy`.
Bracketed requires the same exact set for opening and closing observations. Unknown or extra package
members are forbidden. Strict normalization and later eligibility require `bracketed` for every
selected ticker; raw and record-only materialization retain whichever status is honestly available.

## Canonical repetition inventories

Each repetition names two safe mounted roots and two inventory documents outside those roots.

For each root:

1. enumerate only regular non-symlink files;
2. normalize each name to a POSIX path relative to that root;
3. reject escapes, duplicate normalized paths, symlinked descendants, and unexpected files;
4. sort paths by UTF-8 bytes;
5. record exactly `path`, `byte_length`, and `sha256`; and
6. hash the canonical JSON inventory bytes.

Mounted verification recomputes both inventories, requires each retained document to match its
recomputation byte-for-byte, compares path sets, lengths, and hashes, then stream-compares every file
byte-for-byte.

Fixed scopes are:

- normalization: `records.jsonl`, `source_scopes.json`, `product.json`, `manifest.json`;
- features: `features.jsonl`, `manifest.json`; and
- backtest: Result V4 `manifest.json`, nine typed streams, and one risk trace per contract.

Normalization still uses the same raw locator in both repetitions. Path-independent identity remains
B2A-17 debt rather than being silently changed here.

## Mounted schema and lineage reconstruction

Verification order is stable:

1. evidence-manifest schema and payload hash;
2. outcome/role structure;
3. safe paths and exact mounted membership;
4. byte lengths and hashes;
5. full JSON/JSONL schema validation;
6. credential scan;
7. record/count reconciliation;
8. product, measurement, telemetry, normalization, feature, result, and risk lineage; and
9. repetition reconstruction.

The verifier derives the required lineage-edge set and requires the manifest declaration to equal
it exactly. It independently proves:

- raw frames/metadata into normalization and all four normalization outputs;
- normalization inputs and product/segment/watermark identities into features;
- normalization/features/product/reviewed-lineage identities into Backtest V4 configuration;
- configuration and feature identities into every Result V4 descriptor and typed row;
- one risk trace per configured contract, with identical Result-level and product-level descriptors;
- mounted source/terms/review/conversion/profile evidence through the existing offline product
  verifier; and
- measurement and telemetry identities against the exact mounted roles they describe.

Every mounted JSON document and every JSONL row runs its full formal schema validator rather than
only comparing a discriminator string.

## Credential-scanner contract

The reproducible offline scanner reads normalized relative filenames and raw member bytes. It
detects private-key PEM variants, authorization/bearer headers, API-key/token/password/secret
assignments, and suspicious credential filenames. It deliberately avoids generic entropy detection;
explicit allow rules keep ordinary SHA-256 values, schema identifiers, public key IDs, and benign
prose from becoming findings.

The payload scan covers every mounted member except the evidence manifest and scanner report, which
cannot inventory themselves without a cycle. After those two control documents are assembled, the
same deterministic pattern rules scan their complete bytes as an additional verification step. The
offline verifier reconstructs the payload inventory, reruns both scans, and requires a clean result.

At authoring time only, a second check searches payload and control bytes for configured credential
values held in memory. Historical secrets are neither retained nor required for later offline
verification, so this check is explicitly a capture-time attestation rather than a reproducible
claim. It is defense in depth and cannot substitute for the deterministic scan.

The retained clean report contains scanner executable/version identity, ruleset hash, payload
inventory hash, member/byte counts, deterministic status, and whether the configured-value check ran.
It contains no findings, secret-derived hashes, secret bytes, or paths. On a finding, publication
fails with only a stable rule identifier and a hash of the normalized path in stderr; no manifest or
clean scanner report is published. The manifest binds the clean report hash. Tests use synthetic
secrets only.

## Exact acceptance-test matrix

Each negative test introduces one defect and updates outer hashes as needed so the verifier reaches
the named boundary. Process tests use offline helper processes, PID handshakes, bounded polling, and
no network or venue data. Broad fixture loops may supplement these tests but may not replace their
individual names.

### Lifecycle, CLI, and publication

- `test_measurement_completed_child_publishes_valid_v2_report`
- `test_measurement_child_exit_two_publishes_report_and_preserves_exit_status`
- `test_measurement_operator_sigint_allows_capture_style_cooperative_finalization`
- `test_measurement_budget_sigint_allows_capture_style_cooperative_finalization`
- `test_measurement_reaps_child_and_confirms_quiescent_process_group`
- `test_measurement_keyboard_interrupt_terminates_child_and_grandchild`
- `test_measurement_child_exit_does_not_leave_grandchild_running`
- `test_measurement_sigint_ignoring_child_escalates_to_sigterm`
- `test_measurement_sigint_and_sigterm_ignoring_child_escalates_to_sigkill`
- `test_measurement_second_keyboard_interrupt_accelerates_but_does_not_skip_reap`
- `test_measurement_group_absence_timeout_is_shutdown_failure`
- `test_measurement_wrapper_error_after_spawn_still_reaps_group`
- `test_measurement_existing_final_report_refuses_before_spawn`
- `test_measurement_existing_partial_report_refuses_before_spawn`
- `test_measurement_repeated_invocation_refuses_without_mutation`
- `test_measurement_publication_failure_removes_only_owned_partial`
- `test_measurement_nonzero_exit_keeps_stdout_empty_and_uses_coded_stderr`
- `test_measurement_child_exit_one_returns_one_with_failed_report`
- `test_measurement_wrapper_failure_returns_one_without_success_json`
- `test_measure_v1_cli_stdout_stderr_and_exit_contract_remain_frozen`

### Sampler and storage

- `test_measurement_zero_rss_requires_successful_zero_sample`
- `test_measurement_ps_launch_failure_cannot_report_zero_rss`
- `test_measurement_ps_nonzero_exit_cannot_report_zero_rss`
- `test_measurement_malformed_ps_row_cannot_report_zero_rss`
- `test_measurement_exit_before_first_sample_is_explicitly_invalid`
- `test_measurement_exact_raw_budget_is_allowed`
- `test_measurement_raw_budget_one_byte_over_stops_group`
- `test_measurement_exact_aggregate_budget_is_allowed`
- `test_measurement_aggregate_budget_one_byte_over_stops_group`
- `test_measurement_preexisting_aggregate_bytes_are_counted`
- `test_measurement_free_space_exact_minimum_is_allowed`
- `test_measurement_free_space_one_byte_below_refuses_before_spawn`
- `test_measurement_overlapping_accounting_roots_refuse_before_spawn`
- `test_measurement_symlinked_accounting_member_refuses`
- `test_measurement_unstable_inventory_fails_closed_and_reaps`
- `test_measurement_stream_budget_one_byte_over_stops_group`
- `test_measurement_exact_stream_budget_is_allowed`
- `test_measurement_stderr_stream_budget_one_byte_over_stops_group`
- `test_measurement_control_plane_reservation_prevents_aggregate_overrun`
- `test_measurement_stdout_flood_is_drained_without_unbounded_storage`

### Schema, roles, and positive packages

- `test_verify_raw_only_completed_package`
- `test_verify_raw_only_interrupted_package`
- `test_verify_raw_only_failed_package`
- `test_verify_record_only_discontinuous_package`
- `test_verify_raw_package_with_unavailable_product_status`
- `test_verify_normalization_v3_package`
- `test_verify_features_v3_package`
- `test_verify_backtest_v4_package`
- `test_verify_policy_v1_schema_runtime_parity_remains_frozen`
- `test_verify_manifest_v1_schema_runtime_parity_remains_frozen`
- `test_verify_measurement_v1_schema_runtime_parity_remains_frozen`
- `test_verify_normalization_telemetry_v1_schema_runtime_parity`
- `test_verify_risk_telemetry_v1_schema_runtime_parity`
- `test_verify_policy_v2_rejects_malformed_document`
- `test_verify_manifest_v2_rejects_malformed_document`
- `test_verify_measurement_v2_rejects_malformed_document`
- `test_verify_repetition_inventory_v1_rejects_malformed_document`
- `test_verify_credential_scan_v1_rejects_malformed_document`
- `test_verify_raw_frames_rejects_malformed_jsonl_row`
- `test_verify_normalized_records_rejects_malformed_jsonl_row`
- `test_verify_feature_rows_rejects_malformed_jsonl_row`
- `test_verify_acknowledgements_rejects_malformed_jsonl_row`
- `test_verify_cancellations_rejects_malformed_jsonl_row`
- `test_verify_decisions_rejects_malformed_jsonl_row`
- `test_verify_exposure_rejects_malformed_jsonl_row`
- `test_verify_fills_rejects_malformed_jsonl_row`
- `test_verify_rejections_rejects_malformed_jsonl_row`
- `test_verify_risk_events_rejects_malformed_jsonl_row`
- `test_verify_submitted_orders_rejects_malformed_jsonl_row`
- `test_verify_summary_rejects_malformed_jsonl_row`
- `test_verify_risk_trace_rejects_malformed_jsonl_row`
- `test_verify_raw_stage_rejects_normalization_role`
- `test_verify_raw_stage_requires_capture_policy`
- `test_verify_raw_stage_requires_raw_frames`
- `test_verify_raw_stage_requires_raw_metadata`
- `test_verify_raw_stage_requires_capture_measurement`
- `test_verify_raw_stage_requires_credential_scan_report`
- `test_verify_record_only_stage_requires_normalized_records`
- `test_verify_record_only_stage_requires_normalization_manifest`
- `test_verify_record_only_stage_requires_source_scopes`
- `test_verify_record_only_stage_requires_product_map`
- `test_verify_record_only_stage_requires_normalization_measurement`
- `test_verify_record_only_stage_requires_normalization_telemetry`
- `test_verify_record_only_stage_requires_both_normalization_inventories`
- `test_verify_record_only_stage_rejects_feature_role`
- `test_verify_normalization_v3_requires_reviewed_complete_interval`
- `test_verify_features_v3_requires_feature_rows`
- `test_verify_features_v3_requires_feature_manifest`
- `test_verify_features_v3_requires_feature_measurement`
- `test_verify_features_v3_requires_both_feature_inventories`
- `test_verify_features_v3_rejects_backtest_role`
- `test_verify_backtest_v4_requires_backtest_config`
- `test_verify_backtest_v4_requires_result_manifest`
- `test_verify_backtest_v4_requires_backtest_measurement`
- `test_verify_backtest_v4_requires_risk_telemetry`
- `test_verify_backtest_v4_requires_acknowledgements`
- `test_verify_backtest_v4_requires_cancellations`
- `test_verify_backtest_v4_requires_decisions`
- `test_verify_backtest_v4_requires_exposure`
- `test_verify_backtest_v4_requires_fills`
- `test_verify_backtest_v4_requires_rejections`
- `test_verify_backtest_v4_requires_risk_events`
- `test_verify_backtest_v4_requires_submitted_orders`
- `test_verify_backtest_v4_requires_summary`
- `test_verify_backtest_v4_requires_one_trace_per_contract`
- `test_verify_backtest_v4_requires_both_backtest_inventories`
- `test_verify_exit_one_rejects_normalization_v3_stage`
- `test_verify_exit_two_rejects_features_v3_stage`
- `test_verify_exit_130_rejects_backtest_v4_stage`
- `test_verify_unavailable_product_rejects_product_and_strict_roles`
- `test_verify_opening_product_requires_terms_review_and_source_manifest`
- `test_verify_opening_product_requires_each_manifest_source_member`
- `test_verify_product_requires_version_selected_policy_profile_and_map`
- `test_verify_product_requires_referenced_conversion_policy`
- `test_verify_bracketed_product_requires_opening_and_closing_packages`
- `test_verify_product_package_rejects_unknown_member`

### Repetition and lineage

- `test_verify_repetition_rebuilds_both_mounted_inventories`
- `test_verify_repetition_rejects_missing_path`
- `test_verify_repetition_rejects_extra_path`
- `test_verify_repetition_rejects_length_mismatch`
- `test_verify_repetition_rejects_hash_mismatch`
- `test_verify_repetition_rejects_byte_mismatch`
- `test_verify_repetition_rejects_symlink_member`
- `test_verify_repetition_rejects_stale_inventory_document`
- `test_verify_lineage_rejects_missing_edge`
- `test_verify_lineage_rejects_extra_edge`
- `test_verify_lineage_rejects_product_identity_mutation`
- `test_verify_lineage_rejects_conversion_identity_mutation`
- `test_verify_lineage_rejects_measurement_input_identity_mutation`
- `test_verify_lineage_rejects_measurement_output_identity_mutation`
- `test_verify_lineage_rejects_telemetry_identity_mutation`
- `test_verify_result_v4_rejects_duplicate_or_wrong_descriptor`
- `test_verify_result_v4_rejects_product_trace_disagreement`

### Credential scanning and frozen compatibility

- `test_credential_scan_detects_configured_synthetic_secret`
- `test_credential_scan_detects_each_supported_pem_variant`
- `test_credential_scan_detects_authorization_header`
- `test_credential_scan_detects_suspicious_filename`
- `test_credential_scan_failure_cannot_publish_clean_report`
- `test_credential_scan_finding_uses_path_hash_not_plain_path`
- `test_credential_scan_excludes_self_referential_inventory_members`
- `test_credential_scan_allows_benign_hashes_and_public_identifiers`
- `test_verify_rejects_stale_credential_inventory_identity`
- `test_verify_rejects_self_asserted_clean_scan`
- `test_capture_v2_legacy_bytes_and_exit_contract_remain_frozen`
- `test_verify_v1_index_only_behavior_remains_frozen`
- `test_verify_v1_full_behavior_remains_frozen`
- `test_normalization_v3_and_feature_v3_bytes_remain_frozen`
- `test_backtest_v4_result_v4_and_risk_trace_bytes_remain_frozen`
- `test_b2b2_checkpoint_and_fixture_compatibility_gates_remain_green`
- `test_normalization_telemetry_rename_failure_leaves_detectable_partial_publication`
- `test_backtest_telemetry_rename_failure_leaves_detectable_partial_publication`
- `test_repeated_invocation_refuses_after_canonical_output_without_telemetry`

## Proposed implementation commits

After implementation approval, keep the work reviewable in these logical commits. Within each
implementation slice, write the named tests first and observe the intended failures locally, then add
the smallest implementation that makes them pass. Do not record an intentionally red commit:

1. `feat(phase7): harden b2c measurement lifecycle` — add the offline process helpers, lifecycle and
   budget tests, Measurement V2, and the focused supervisor module, including bounded streams,
   sampling validity, signals, reap, and additive `measure-v2` CLI behavior.
2. `feat(phase7): reconstruct b2c evidence and lineage` — add the evidence tests,
   manifest/inventory/scanner successors, `verify-v2`, mounted schema validation, role rules, product
   verification, lineage reconstruction, and repetition comparison.
3. `test(phase7): close b2c-h compatibility gates` — add frozen-byte and full-suite compatibility
   coverage, then record exact validation counts.
4. `docs(phase7): close b2c-h hardening` — update the operator guide, refusal-code reference,
   explanation, critique, validation evidence, README surfaces, and living roadmap only after the
   implementation gates pass.

Every new V2 refusal code must be additive, stable, individually tested, and documented with its
stdout/stderr/exit meaning. Existing V1 codes and first-failure ordering remain byte-for-byte and
behaviorally frozen.

If a production change is too large to review with its matching focused tests, split it within the
same ownership boundary. Do not mix product acquisition, capture execution, retained evidence, or
deferred performance redesign into these commits.

## Acceptance and closure

### 2026-07-21 acceptance reconciliation

| Design area | Current disposition |
| --- | --- |
| B2CH-T01 child/grandchild interruption | Closed by named tests in `df905ff`. |
| B2CH-T02 bounded escalation and quiescence | Closed by named SIGINT, SIGTERM, SIGKILL, second-interrupt, ESRCH, EPERM, and absence-timeout tests in `df905ff`. |
| B2CH-T03 sampler validity and zero RSS | Closed by launch, exit, malformed/duplicate row, no-sample, zombie, and valid-zero tests in `df905ff`. |
| B2CH-T04 stage/outcome role matrix | Closed for offline conformance by the fully mounted Synthetic strict package; Observed execution is not evaluated and transfers to B2c-P. |
| B2CH-T05 repetition inventories | Closed by mounted rebuild, canonical-output binding, symlink, inventory mutation, and exact-byte tests. |
| B2CH-T06 mounted schema validation | Closed for registered JSON/JSONL roles, discriminator binding, record counts, and risk-trace V2 parity in `ce0218f`. |
| B2CH-T07 cross-artifact identity | Closed by path-plus-hash measurement identities, truth/catalog/exact product-map reconstruction, normalization/feature/Result mutations, portable Backtest path binding, and operational approval. |
| B2CH-T08 credential scan | Implemented with synthetic PEM/header/assignment tests and recomputed report binding in `ce0218f`; real secrets remain prohibited from fixtures. |
| B2CH-T09 telemetry publication/repeat invocation | Closed by atomic normalization/telemetry publication cleanup, rename-failure, and repeated-invocation tests. |

All B2c-H offline controls above are closed. The live command remains unauthorized because B2c-P's
external-evidence and human-approval gates are separate from offline hardening.

B2c-H closes only after:

- every individually named lifecycle, budget, schema, stage, inventory, lineage, credential, and
  positive-partial-package test passes;
- frozen capture, Phase 7, B2b-2, product-term, checkpoint-reader, fixture-integrity, formatting,
  full Python, and CTest gates pass;
- the operator guide documents authoring, signals, grace/escalation/reap, report/output ownership,
  scanner review, safe refusal, and machine-comparison limits;
- the explanation and critique distinguish implemented controls, measured behavior, deferred debt,
  and absent retained evidence; and
- the living roadmap records exact validation evidence; once every preceding gate is satisfied, the
  closure update promotes B2c-P as the next package as a consequence of closure.

R03/R04 remain B2c-P prerequisites. R10, R11, R13 through R15, R18 through R20, and B2A-17 remain
measured, characterized, or deferred. B2C-R16 is targeted for closure by the individually named
one-defect matrix. B2C-R17 is targeted for closure by the private role registry and schema/runtime
parity tests; unavoidable duplication in public schemas and prose remains guarded compatibility
surface, not a second runtime authority. B3 remains blocked until the applicable B2c evidence gates
actually close.
