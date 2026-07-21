# B2c-H Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the confirmed B2c-H process-supervision and mounted-evidence defects, complete the approved offline acceptance matrix, preserve every frozen V1 behavior, and leave B2c-P blocked until an independent final review proves all B2c-H gates closed.

**Architecture:** Keep `python/pmm_phase7_measurement.py` as the sole owner of V2 process-group lifecycle, sampling, stream draining, storage accounting, and report publication. Keep `python/pmm_phase7_evidence.py` as the frozen V1 implementation plus an additive V2 adapter/verifier, but make its private V2 role registry authoritative for runtime dispatch while formal JSON Schemas remain authoritative for document shape. Execute measurement and verifier work in parallel with exclusive file ownership, then integrate, run independent review agents, update documentation, and commit only from the coordinator.

**Tech Stack:** Python 3.11, standard-library POSIX process control, `jsonschema` Draft 2020-12 validation, `unittest`, Nix, uv, CMake/CTest, Graphify as advisory navigation.

## Global Constraints

- Start from clean `main` at `d5551b9`; verify the actual baseline before implementation.
- Read every applicable `AGENTS.md`, then `PROJECT_CHARTER.md`, `README.md`, the living roadmap, the B2c-H design/explanation/critique, operator guide, schemas, implementation, and focused tests.
- Use Graphify first when `graphify-out/graph.json` exists, but verify every material claim against source, tests, schemas, accepted ADRs, and the living roadmap.
- Use test-driven development: one named defect per test, observe the intended failure, implement the smallest fix, and rerun the focused suite.
- Use systematic debugging for every unexpected failure; preserve the exact command, output, minimal reproduction, and root cause.
- All new tests must be offline, deterministic, bounded, and use synthetic secrets only.
- Do not access a venue, acquire product evidence, run a capture, create retained evidence, or begin B2c-P.
- Do not change Capture V2, normalization V3, feature V3, Backtest V4, Result V4, risk, product-term, checkpoint, or fixture semantics.
- V1 `measure` and `verify` bytes, accepted inputs, refusal ordering, exit codes, stdout/stderr ownership, and cleanup behavior are frozen.
- New behavior must remain additive under `measure-v2` and `verify-v2`.
- Preserve the POSIX PGID guarantee and explicit no-daemonization boundary; do not claim containment of descendants that deliberately call `setsid`.
- Do not add dependencies.
- Workers must not stage, commit, edit documentation, or touch another worker's assigned files. The coordinator owns integration, documentation, Graphify refresh, and commits.
- Never add an AI assistant as author or co-author.

## Multi-agent execution topology

Wave 1 uses three concurrent workers plus the coordinator:

| Worker | Exclusive write ownership | Deliverable |
| --- | --- | --- |
| Measurement worker | `python/pmm_phase7_measurement.py`, `python/tests/test_phase7_b2c_measurement.py` | Lifecycle, sampler, streams, storage, path, and publication fixes |
| Verifier worker | `python/pmm_phase7_evidence.py`, `python/tests/test_phase7_b2c_evidence.py`, every `schemas/historical/b2c-*.schema.json`, `schemas/historical/risk-conformance-trace-v2.schema.json` | Exact V2 role/stage/schema/scanner/lineage/repetition verification |
| Compatibility worker | Read-only repository access | V1 compatibility audit, frozen-byte/CLI inventory, and review findings sent to the coordinator |
| Coordinator | No production edits during Wave 1 | Interface arbitration, test-output collection, conflict prevention, and integration review |

Wave 2 starts only after Wave 1 is integrated:

| Worker | Scope | Deliverable |
| --- | --- | --- |
| Lifecycle reviewer | Read-only | Spec-compliance review of measurement code and tests |
| Evidence reviewer | Read-only | Spec-compliance review of verifier, schemas, lineage, repetition, and scanner |
| Compatibility reviewer | Read-only | Independent V1/V2 CLI, artifact, checkpoint, and fixture regression review |
| Coordinator | Documentation and commits | Resolve findings, run gates, update authoritative docs, refresh Graphify, commit logical slices |

No worker may declare B2c-H closed. Only the coordinator may do so after every gate in Task 8 passes and all severity-1 through severity-4 findings are resolved or explicitly remain blocking.

---

### Task 1: Freeze the baseline and define shared V2 interfaces

**Files:**
- Read: `AGENTS.md`
- Read: `python/pmm_phase7_measurement.py`
- Read: `python/pmm_phase7_evidence.py`
- Read: `python/tests/test_phase7_b2c_measurement.py`
- Read: `python/tests/test_phase7_b2c_evidence.py`
- Read: `docs/07 Engineering Notes/Phase 7 B2c-H Hardening Design.md`
- Read: `docs/00 Project Hub/Current State and Remaining Work.md`

**Interfaces:**
- Consumes: current `MeasurementControls`, `MeasurementResult`, `run_measurement_v2`, `V2_ROLE_REGISTRY`, and both V2 CLI branches.
- Produces: one coordinator-owned interface note delivered to both implementation workers before edits begin.

- [ ] **Step 1: Verify baseline state and toolchain**

Run:

```sh
git status --short
git rev-parse HEAD
git status --branch --short
UV_CACHE_DIR=/tmp/pmm-uv-cache nix develop --command uv sync --locked
```

Expected: empty short status, HEAD `d5551b9e01a2d2a928e82bbc16a5b9b04399c0e9`, `main` ahead of `origin/main` by 16, and locked dependency setup succeeds.

- [ ] **Step 2: Record the shared measurement contract**

Retain the exact existing `run_measurement_v2` keyword-only signature: `stage: str`,
`command: list[str]`, `report_path: Path`, `package_root: Path`, `raw_roots: list[Path]`,
`output_roots: list[Path]`, `controls: MeasurementControls = V2_CONTROLS`, optional
`identity_files: list[Path]`, the existing sampler callback, and the existing free-space callback;
the return type remains `MeasurementResult`.

`report_path`, every raw root, every output root, and every retained identity file must resolve beneath `package_root`. Capture-stage layout is:

```text
<package-root>/
  control/
  raw/
  measurements/capture.json
```

Exact cross-class equality `raw_root == output_root` is allowed only for `stage == "capture-v2"`; duplicate roots within a class and ancestor/descendant overlaps remain refusals. A capture raw root must be absent or empty before spawn. Derived stages may reference immutable, pre-existing raw roots.

- [ ] **Step 3: Record stable additive refusal codes**

Use these codes in new V2 paths without changing V1 codes:

```text
MeasurementPathUnsafe
MeasurementRootDuplicate
MeasurementRootOverlap
MeasurementRawRootNotEmpty
MeasurementInventoryUnstable
MeasurementSamplerUnavailable
MeasurementSamplerMalformed
MeasurementSamplerLeaderMissing
MeasurementSignalPermissionDenied
MeasurementNoSuccessfulSample
EvidenceV2ManifestSchemaMismatch
EvidenceV2PayloadHashMismatch
EvidenceV2MembershipMismatch
EvidenceV2RoleMissing
EvidenceV2RoleForbidden
EvidenceV2RoleSchemaMismatch
EvidenceV2EligibilityMismatch
EvidenceV2LineageMismatch
EvidenceV2RepetitionMismatch
EvidenceV2CredentialScanMismatch
```

- [ ] **Step 4: Dispatch Wave 1 workers with exclusive ownership**

Each worker receives the global constraints, exact ownership table, shared interface contract, baseline commit, and prohibition on staging/committing. The compatibility worker is read-only and must return a list of exact existing V1 assertions and any untested boundary.

---

### Task 2: Fix post-spawn process-group lifecycle ownership

**Files:**
- Modify: `python/pmm_phase7_measurement.py:204-460`
- Test: `python/tests/test_phase7_b2c_measurement.py`

**Interfaces:**
- Consumes: the unchanged `run_measurement_v2` signature from Task 1.
- Produces: one cleanup owner that always reaches direct-child reap, live-group termination, quiescence confirmation, finalized stream facts, and report publication when publication remains possible.

- [ ] **Step 1: Add failing child/grandchild lifecycle tests**

Add these individually named tests using PID files under `TemporaryDirectory`, bounded polling, and
`addCleanup` termination safeguards: `test_measurement_child_exit_does_not_leave_grandchild_running`,
`test_measurement_keyboard_interrupt_terminates_child_and_grandchild`,
`test_measurement_sigint_ignoring_child_escalates_to_sigterm`,
`test_measurement_sigint_and_sigterm_ignoring_child_escalates_to_sigkill`,
`test_measurement_second_keyboard_interrupt_accelerates_but_does_not_skip_reap`,
`test_measurement_wrapper_error_after_spawn_still_reaps_group`, and
`test_measurement_group_absence_timeout_is_shutdown_failure`.

The first test must reproduce the audited defect: a direct child spawns an in-group grandchild with its streams redirected to `os.devnull`, records the grandchild PID, exits, and expects the wrapper to make `os.kill(pid, 0)` raise `ProcessLookupError` before return.

- [ ] **Step 2: Run the lifecycle tests and preserve failures**

Run:

```sh
UV_CACHE_DIR=/tmp/pmm-uv-cache nix develop --command uv run python -m unittest \
  python.tests.test_phase7_b2c_measurement.B2cMeasurementV2Tests.test_measurement_child_exit_does_not_leave_grandchild_running \
  python.tests.test_phase7_b2c_measurement.B2cMeasurementV2Tests.test_measurement_second_keyboard_interrupt_accelerates_but_does_not_skip_reap
```

Expected before implementation: the grandchild remains alive, and the second interrupt propagates without a report.

- [ ] **Step 3: Replace split cleanup paths with one explicit shutdown state machine**

Implement a focused `_ShutdownState` dataclass containing `reason: str`, `signals: list[str]`,
`direct_child_reaped: bool`, `process_group_quiescent: bool`, `zombie_members_observed: int`, and
`failure_code: str | None`. Add `_shutdown_owned_group` with keyword-only inputs
`process: subprocess.Popen[bytes]`, `pgid: int`, `reason: str`, `controls: MeasurementControls`, the
existing sampler callback type, and `expedite_requested: threading.Event`; it returns `_ShutdownState`.

The algorithm must:

1. sample the PGID even when the direct child has already exited;
2. send SIGINT when any live member remains;
3. wait the SIGINT grace while continuing group checks;
4. send SIGTERM when members remain;
5. wait the SIGTERM grace;
6. send SIGKILL when members remain or a second interrupt sets `expedite_requested`;
7. call `process.wait` until the direct child is reaped or the final deadline fails;
8. require one successful PGID sample showing zero non-zombie members;
9. treat EPERM, sampler failure, or surviving live members as teardown failure;
10. retain ESRCH as an observed absent-group signal, then still reap the direct child.

- [ ] **Step 4: Make the second interrupt an acceleration request**

Install a temporary SIGINT handler only around post-spawn supervision. The first SIGINT selects `operator_interrupted`; the second sets `expedite_requested`. Restore the prior handler before returning. Do not permit a nested `KeyboardInterrupt` to escape the cleanup owner.

- [ ] **Step 5: Run lifecycle tests**

Run:

```sh
UV_CACHE_DIR=/tmp/pmm-uv-cache nix develop --command uv run python -m unittest \
  python.tests.test_phase7_b2c_measurement
```

Expected: all measurement tests pass, no helper PID remains alive, operator interruption returns 130 with empty stdout and coded stderr through the CLI, and the report records final reap/quiescence facts.

---

### Task 3: Harden sampler, streams, and signal-error semantics

**Files:**
- Modify: `python/pmm_phase7_measurement.py:135-215`
- Test: `python/tests/test_phase7_b2c_measurement.py`

**Interfaces:**
- Consumes: `_shutdown_owned_group` from Task 2.
- Produces: strict process-table parsing, explicit zero-RSS validity, bounded concurrent stream draining, and stable EPERM/ESRCH behavior.

- [ ] **Step 1: Add the full sampler failure matrix**

Add `test_measurement_zero_rss_requires_successful_zero_sample`,
`test_measurement_ps_launch_failure_cannot_report_zero_rss`,
`test_measurement_ps_nonzero_exit_cannot_report_zero_rss`,
`test_measurement_malformed_ps_row_cannot_report_zero_rss`,
`test_measurement_duplicate_ps_pid_cannot_report_valid_sample`,
`test_measurement_exit_before_first_sample_is_explicitly_invalid`,
`test_measurement_signal_eperm_is_teardown_failure`, and
`test_measurement_signal_esrch_still_reaps_direct_child`.

Inject `subprocess.run` results or the existing sampler callback; do not depend on host process-table races.

- [ ] **Step 2: Reject duplicate and malformed process rows**

Within `_sample_process_group`, track every parsed PID:

```python
seen_pids: set[int] = set()
if pid in seen_pids:
    raise SamplerFailure("MeasurementSamplerMalformed")
seen_pids.add(pid)
```

Require exactly four columns, integer PID/PGID/RSS, nonnegative RSS, and leader presence while `require_leader` is true. A successful sample with RSS zero is valid; failure or no successful sample keeps peaks `None`.

- [ ] **Step 3: Make signal outcomes typed**

Replace the Boolean signal result with:

```python
class _SignalOutcome(Enum):
    SENT = "sent"
    GROUP_ABSENT = "esrch"
    PERMISSION_DENIED = "eperm"
```

Every EPERM sets `failure_code = "MeasurementSignalPermissionDenied"`; ESRCH never substitutes for direct-child reap.

- [ ] **Step 4: Add independent 64 MiB stream tests**

Add `test_measurement_stdout_flood_is_drained_without_unbounded_storage`,
`test_measurement_stderr_flood_is_drained_without_unbounded_storage`,
`test_measurement_simultaneous_stdout_stderr_floods_do_not_deadlock`, and
`test_measurement_each_stream_has_an_independent_limit`.

Each flood writes at most 65 MiB plus one byte, uses a sub-second test control interval, records hashes/counts only, and asserts no temporary log file exists after return.

- [ ] **Step 5: Run the sampler and stream suite**

Run:

```sh
UV_CACHE_DIR=/tmp/pmm-uv-cache nix develop --command uv run python -m unittest \
  python.tests.test_phase7_b2c_measurement
```

Expected: all tests pass in bounded time; no stream deadlock, fabricated zero, uncaught process-table conversion error, or signal-permission ambiguity remains.

---

### Task 4: Enforce path, inventory, free-space, and storage contracts

**Files:**
- Modify: `python/pmm_phase7_measurement.py:85-132`
- Modify: `python/pmm_phase7_measurement.py:223-255`
- Test: `python/tests/test_phase7_b2c_measurement.py`

**Interfaces:**
- Consumes: package layout and capture-stage overlap rule from Task 1.
- Produces: deterministic preflight refusal before spawn and stable logical-byte accounting during execution.

- [ ] **Step 1: Add path and root tests**

Add `test_measurement_report_must_be_inside_package_root`,
`test_measurement_package_root_symlink_refuses_before_spawn`,
`test_measurement_accounting_root_escape_refuses_before_spawn`,
`test_measurement_duplicate_raw_root_refuses_before_spawn`,
`test_measurement_duplicate_output_root_refuses_before_spawn`,
`test_measurement_ancestor_descendant_root_overlap_refuses_before_spawn`,
`test_measurement_capture_stage_allows_exact_raw_output_root_identity`,
`test_measurement_capture_stage_requires_absent_or_empty_raw_root`,
`test_measurement_derived_stage_allows_preexisting_immutable_raw_root`, and
`test_measurement_symlinked_accounting_member_refuses`.

- [ ] **Step 2: Add budget and instability tests**

Add `test_measurement_exact_aggregate_budget_is_allowed`,
`test_measurement_aggregate_budget_one_byte_over_stops_group`,
`test_measurement_preexisting_aggregate_bytes_are_counted`,
`test_measurement_free_space_exact_minimum_is_allowed`,
`test_measurement_control_plane_reservation_prevents_aggregate_overrun`,
`test_measurement_same_size_path_swap_is_inventory_unstable`, and
`test_measurement_unstable_inventory_fails_closed_and_reaps`.

- [ ] **Step 3: Validate paths before resolving away symlink evidence**

Use the unresolved configured path for `is_symlink()` and the resolved path for containment. Normalize roots once, reject duplicates by resolved identity, and compare all pairs for ancestor/descendant overlap. Do not use exception text from `Path.relative_to` as the public refusal.

- [ ] **Step 4: Compare complete logical inventories**

Represent one storage snapshot as:

```python
@dataclass(frozen=True)
class _InventorySnapshot:
    total_bytes: int
    entries: Sequence[tuple[str, int]]
```

`_package_bytes` must compare two full snapshots, not only totals. A same-size rename or path swap is unstable. Continue using logical file sizes rather than hashing every file during every budget sample.

- [ ] **Step 5: Account for publication within the package**

Require `report_path` beneath `package_root`. Before spawn require:

```python
initial_aggregate_bytes + publication_reserve_bytes <= aggregate_budget_bytes
```

During execution require:

```python
current_aggregate_bytes + remaining_publication_reserve_bytes <= aggregate_budget_bytes
```

Publication failure removes only the wrapper-owned `.partial`; measured outputs remain untouched.

- [ ] **Step 6: Run storage tests**

Run:

```sh
UV_CACHE_DIR=/tmp/pmm-uv-cache nix develop --command uv run python -m unittest \
  python.tests.test_phase7_b2c_measurement
```

Expected: every preflight defect spawns no child and publishes no report; every post-spawn instability reaps the group and produces a failed report when publication remains possible.

---

### Task 5: Make Manifest V2 and the private role registry enforce the same contract

**Files:**
- Modify: `schemas/historical/b2c-evidence-manifest-v2.schema.json`
- Modify: `schemas/historical/b2c-evidence-policy-v2.schema.json`
- Modify: `schemas/historical/b2c-measurement-v2.schema.json`
- Modify: `python/pmm_phase7_evidence.py:38-196`
- Test: `python/tests/test_phase7_b2c_evidence.py`
- Create: `python/tests/b2c_v2_fixture_builder.py`

**Interfaces:**
- Consumes: existing successor schema filenames and frozen V1 constants.
- Produces: a frozen private `RoleSpec` registry and a fixture builder that creates valid raw, record-only, normalization, feature, and backtest V2 packages.

- [ ] **Step 1: Build one reusable valid-package fixture builder**

Create a `V2PackageFixture` dataclass with `root: Path`, `manifest_path: Path`, and
`manifest: dict[str, Any]`. Create `build_v2_package` with required `root: Path`, keyword-only
`materialized_stage: str` and `eligible_stage: str`, plus defaults `capture_exit: int = 0` and
`product_status: str = "bracketed"`; it returns `V2PackageFixture`.

The builder must write schema-valid synthetic members for each stage, use three synthetic tickers and contract IDs, recompute all outer hashes after a mutation, and never import production secrets or network clients.

- [ ] **Step 2: Expand Manifest V2 to carry the approved evidence facts**

The payload must formally require:

```text
evidence_id
capture_spec
capture_outcome
market_tickers
retention
product_lineage
furthest_materialized_stage
furthest_eligible_stage
members
lineage_edges
repetitions
credential_scan
```

Every object uses `additionalProperties: false`; every hash uses lowercase 64-hex syntax; roles and relative paths are non-empty; stage enums remain exactly `raw`, `normalization_record_only`, `normalization_v3`, `features_v3`, and `backtest_v4`.

- [ ] **Step 3: Replace tuple registry entries with frozen specifications**

```python
@dataclass(frozen=True)
class RoleSpec:
    schema_file: str
    schema_tag: str
    kind: Literal["json", "jsonl"]
    introduced_at: str
    cardinality: Literal["one", "per_contract", "per_ticker", "pair_per_stage"]

V2_ROLE_REGISTRY: Mapping[str, RoleSpec] = MappingProxyType(role_specs)
```

The registry must cover the five always-required roles, normalization documents/measurement/telemetry/inventories, feature documents/measurement/inventories, Backtest V4 config/result/measurement/risk telemetry, all nine typed result streams, and dynamic risk traces. Product-package members remain delegated to the existing product verifier and are derived per selected ticker/status.

- [ ] **Step 4: Add role/schema/kind parity tests**

Add `test_verify_v2_role_registry_schema_runtime_parity`,
`test_verify_v2_rejects_member_selected_wrong_schema_file`,
`test_verify_v2_rejects_member_selected_wrong_kind`,
`test_verify_v2_rejects_correct_schema_with_wrong_role`, and
`test_verify_v2_rejects_unknown_role`.

The audited package in which all five required roles point to `b2c-credential-scan-v1.schema.json` must fail with `EvidenceV2RoleSchemaMismatch` before mounted row validation.

- [ ] **Step 5: Enforce exact stage and eligibility rules**

Add the positive and negative stage matrix named in the approved design, including:

Add `test_verify_raw_stage_rejects_normalization_role`,
`test_verify_raw_stage_rejects_feature_role`,
`test_verify_record_only_stage_requires_normalization_measurement`,
`test_verify_record_only_stage_requires_both_normalization_inventories`,
`test_verify_features_v3_rejects_backtest_role`,
`test_verify_backtest_v4_requires_all_nine_typed_streams`,
`test_verify_backtest_v4_requires_one_trace_per_contract`,
`test_verify_raw_materialization_cannot_self_assert_backtest_eligibility`,
`test_verify_exit_one_rejects_normalization_v3_stage`,
`test_verify_exit_two_rejects_features_v3_stage`, and
`test_verify_exit_130_rejects_backtest_v4_stage`.

Derive both stage values from outcome, continuity, product coverage, exact role membership, and validated lineage; compare the derived values to the manifest declarations.

- [ ] **Step 6: Run schema and role tests**

Run:

```sh
UV_CACHE_DIR=/tmp/pmm-uv-cache nix develop --command uv run python -m unittest \
  python.tests.test_phase7_b2c_evidence
```

Expected: valid packages at each supported stage pass; every wrong schema, kind, missing role, forbidden role, unknown role, and false eligibility claim fails with its named V2 code.

---

### Task 6: Reconstruct mounted membership, credential scanning, lineage, and repetitions

**Files:**
- Modify: `python/pmm_phase7_evidence.py:85-196`
- Modify: `schemas/historical/b2c-credential-scan-v1.schema.json`
- Modify: `schemas/historical/b2c-repetition-inventory-v1.schema.json`
- Test: `python/tests/test_phase7_b2c_evidence.py`
- Test helper: `python/tests/b2c_v2_fixture_builder.py`

**Interfaces:**
- Consumes: `RoleSpec`, stage-derived exact membership, and the fixture builder from Task 5.
- Produces: read-only mounted verification whose `verified: true` means exact membership, schema, counts, scanner, lineage, and repetition facts were independently reconstructed.

- [ ] **Step 1: Reject every unsafe or mismatched mounted member**

Add `test_verify_v2_rejects_missing_member`, `test_verify_v2_rejects_extra_regular_file`,
`test_verify_v2_rejects_undeclared_symlink`, `test_verify_v2_rejects_declared_symlink`,
`test_verify_v2_rejects_escape`, `test_verify_v2_rejects_length_mismatch`,
`test_verify_v2_rejects_hash_mismatch`, `test_verify_v2_rejects_malformed_json_document`, and
`test_verify_v2_rejects_malformed_jsonl_row`.

Enumerate symlinks as explicit unsafe entries rather than filtering them out of `actual`. Require manifest placement inside the mounted root and compare normalized POSIX path sets exactly.

- [ ] **Step 2: Implement two-pass credential scanning without self-reference**

Use:

```python
@dataclass(frozen=True)
class CredentialScanResult:
    scanner_identity: str
    ruleset_sha256: str
    payload_inventory_sha256: str
    member_count: int
    byte_count: int
    status: Literal["clean"]
```

Pass one scans every payload member except the evidence manifest and scanner report. Pass two scans the completed manifest and scanner-report bytes for content rules, but does not classify the mandated scanner-report filename itself as suspicious. The verifier rebuilds the payload inventory and requires exact report identity/count/hash agreement.

- [ ] **Step 3: Add scanner detection and false-positive tests**

Add `test_credential_scan_detects_each_supported_pem_variant`,
`test_credential_scan_detects_authorization_header`,
`test_credential_scan_detects_credential_assignment`,
`test_credential_scan_detects_suspicious_payload_filename`,
`test_credential_scan_allows_credential_scan_report_filename`,
`test_credential_scan_allows_benign_hashes_and_public_identifiers`,
`test_verify_rejects_stale_credential_inventory_identity`, and
`test_verify_rejects_self_asserted_clean_scan`.

- [ ] **Step 4: Rebuild cross-artifact lineage**

Validate every JSON document and JSONL row first, delegate product packages to the existing offline product verifier, then reconstruct:

```text
raw frames + metadata -> normalization manifest and four normalization outputs
normalization identities + segments + products -> feature manifest and rows
normalization + features + reviewed products -> Backtest V4 config
config + features -> Result V4 descriptors and nine typed streams
one configured contract -> one matching risk trace and Result-level trace descriptor
measurement and telemetry identities -> the exact mounted inputs and outputs they describe
```

Derive the complete edge set and require exact equality with `lineage_edges`; missing and extra edges both refuse.

- [ ] **Step 5: Rebuild and byte-compare repetitions**

For normalization, features, and backtest, recompute both inventory documents from their mounted roots, require exact canonical inventory bytes, compare path/length/hash triples, then stream-compare corresponding files. Add:

Add `test_verify_repetition_rebuilds_both_mounted_inventories`,
`test_verify_repetition_rejects_missing_path`, `test_verify_repetition_rejects_extra_path`,
`test_verify_repetition_rejects_length_mismatch`, `test_verify_repetition_rejects_hash_mismatch`,
`test_verify_repetition_rejects_byte_mismatch`, `test_verify_repetition_rejects_symlink_member`, and
`test_verify_repetition_rejects_stale_inventory_document`.

- [ ] **Step 6: Add one-defect lineage tests**

Add `test_verify_lineage_rejects_missing_edge`, `test_verify_lineage_rejects_extra_edge`,
`test_verify_lineage_rejects_product_identity_mutation`,
`test_verify_lineage_rejects_conversion_identity_mutation`,
`test_verify_lineage_rejects_measurement_input_identity_mutation`,
`test_verify_lineage_rejects_measurement_output_identity_mutation`,
`test_verify_lineage_rejects_telemetry_identity_mutation`,
`test_verify_result_v4_rejects_duplicate_or_wrong_descriptor`, and
`test_verify_result_v4_rejects_product_trace_disagreement`.

- [ ] **Step 7: Run the mounted verifier suite**

Run:

```sh
UV_CACHE_DIR=/tmp/pmm-uv-cache nix develop --command uv run python -m unittest \
  python.tests.test_phase7_b2c_evidence
```

Expected: every valid synthetic package verifies read-only; each one-defect mutation reaches and fails at its named boundary.

---

### Task 7: Integrate CLI and frozen compatibility gates

**Files:**
- Modify: `python/pmm_phase7_evidence.py:660-765`
- Modify: `python/tests/test_phase7_b2c_measurement.py`
- Modify: `python/tests/test_phase7_b2c_evidence.py`
- Read/test: `python/kalshi_capture.py`
- Read/test: `python/pmm_phase7.py`
- Read/test: `python/pmm_phase7_multimarket.py`
- Read/test: relevant capture, product-term, checkpoint, and fixture-integrity tests

**Interfaces:**
- Consumes: completed measurement and verifier implementations.
- Produces: stable V2 CLI behavior and evidence that V1 and downstream artifacts remain frozen.

- [ ] **Step 1: Merge Wave 1 changes and run focused tests**

Run:

```sh
UV_CACHE_DIR=/tmp/pmm-uv-cache nix develop --command uv run python -m unittest \
  python.tests.test_phase7_b2c_measurement \
  python.tests.test_phase7_b2c_evidence
```

Expected: all focused tests pass without a live process, network request, retained artifact, or test-owned PID left behind.

- [ ] **Step 2: Enforce V2 CLI stream and status ownership**

Add assertions for:

```text
preflight/config/output-exists refusal -> exit 2, empty stdout, coded stderr, no report
child success -> exit 0, JSON stdout, empty stderr, retained report
child expected refusal -> exit 2, empty stdout, coded stderr, retained report
child/wrapper/teardown failure -> exit 1, empty stdout, coded stderr, failed report when possible
operator or budget stop -> exit 130, empty stdout, coded stderr, retained report
publication failure -> exit 1, no final report, owned partial removed
```

- [ ] **Step 3: Run the compatibility worker's frozen inventory**

At minimum run:

```sh
UV_CACHE_DIR=/tmp/pmm-uv-cache nix develop --command uv run python -m unittest \
  python.tests.test_kalshi_capture \
  python.tests.test_phase7 \
  python.tests.test_phase7_multimarket_backtest \
  python.tests.test_product_terms \
  python.tests.test_risk_checkpoint_conformance \
  python.tests.test_risk_fixture_integrity
```

Expected: all suites pass; V1 `measure` and `verify`, Capture V2, normalization V3, feature V3, Backtest/Result V4, risk trace, product, checkpoint, and fixture bytes/semantics remain unchanged.

- [ ] **Step 4: Verify the V1 implementation diff is additive**

Run:

```sh
git diff --unified=0 f7094722..HEAD -- python/pmm_phase7_evidence.py
```

Review requirement: no pre-existing V1 validation, measurement, CLI, or first-failure branch may be deleted or reinterpreted. Any necessary shared refactor must be covered by byte/status compatibility tests before acceptance.

- [ ] **Step 5: Commit the two implementation slices**

After reviewing exact staged scope:

```sh
git add python/pmm_phase7_measurement.py python/tests/test_phase7_b2c_measurement.py
git commit -m "fix(phase7): close b2c measurement lifecycle gaps"

git add python/pmm_phase7_evidence.py python/tests/test_phase7_b2c_evidence.py \
  python/tests/b2c_v2_fixture_builder.py schemas/historical
git commit -m "fix(phase7): enforce b2c v2 evidence contracts"
```

The coordinator must run focused tests before each commit so every commit is green.

---

### Task 8: Independent reviews, complete validation, and documentation

**Files:**
- Modify: `README.md`
- Modify: `python/README.md`
- Modify: `docs/00 Project Hub/Current State and Remaining Work.md`
- Modify: `docs/01 Roadmap/Phase 7 Historical Replay and Backtesting.md`
- Modify: `docs/07 Engineering Notes/Phase 7 B2c-H Hardening Design.md`
- Modify: `docs/07 Engineering Notes/Phase 7 B2c-H Hardening Explained.md`
- Modify: `docs/07 Engineering Notes/Phase 7 B2c-H Hardening Critique.md`
- Modify: `docs/07 Engineering Notes/Phase 7 Retained Capture Evidence.md`
- Create: `docs/07 Engineering Notes/Phase 7 B2c-H Refusal Codes.md`

**Interfaces:**
- Consumes: integrated implementation, exact test outputs, and three independent review reports.
- Produces: an evidence-backed closure decision, corrected operator layout, current roadmap state, and one next-agent handoff.

- [ ] **Step 1: Dispatch three read-only review agents**

Lifecycle reviewer checks every design lifecycle/sampler/storage test against implementation. Evidence reviewer checks schema/registry parity, exact stage roles, mounted membership, scanner, lineage, repetition, and refusal order. Compatibility reviewer checks V1 and downstream artifact behavior. Each returns severity-ranked findings with exact file/line evidence and no edits.

- [ ] **Step 2: Resolve every blocking review finding test-first**

Severity 1-4 lifecycle, evidence-integrity, compatibility, or documentation contradictions remain B2c-H blockers. Add one named failing test per accepted defect, make the smallest fix, rerun focused tests, and request the corresponding reviewer to recheck.

- [ ] **Step 3: Run formatting and full validation**

Run:

```sh
nix develop --command ./scripts/check_format.sh
UV_CACHE_DIR=/tmp/pmm-uv-cache nix develop --command ./scripts/test.sh
```

Expected baseline floor: 78 CTest tests and at least 171 Python tests pass. Record the actual increased Python/focused counts; do not copy old counts forward.

- [ ] **Step 4: Run explicit focused closure commands**

```sh
UV_CACHE_DIR=/tmp/pmm-uv-cache nix develop --command uv run python -m unittest \
  python.tests.test_phase7_b2c_measurement \
  python.tests.test_phase7_b2c_evidence

UV_CACHE_DIR=/tmp/pmm-uv-cache nix develop --command uv run python -m unittest \
  python.tests.test_product_terms \
  python.tests.test_risk_checkpoint_conformance \
  python.tests.test_risk_fixture_integrity
```

Expected: all pass with no skipped B2c-H acceptance test and no environment-dependent network behavior.

- [ ] **Step 5: Update operator documentation**

Correct the documented layout to keep all accounting roots and the report beneath one package root:

```sh
UV_CACHE_DIR=/tmp/pmm-uv-cache uv run python python/pmm_phase7_evidence.py measure-v2 \
  --stage capture-v2 \
  --report data/raw/<capture-id>-package/measurements/capture.json \
  --package-root data/raw/<capture-id>-package \
  --raw-root data/raw/<capture-id>-package/raw \
  --output-root data/raw/<capture-id>-package/raw \
  --identity-file data/raw/<capture-id>-package/control/evidence-policy-v2.json \
  -- uv run --env-file .env python python/kalshi_capture.py capture-v2 \
    --ticker <MARKET-A> --ticker <MARKET-B> --ticker <MARKET-C> \
    --duration 43200 --output data/raw/<capture-id>-package/raw
```

Keep the command explicitly unauthorized until the final B2c-H closure decision and a separate B2c-P approval packet.

- [ ] **Step 6: Write the V2 refusal-code reference**

Document each code from Task 1 with trigger, report/no-report behavior, exit status, stdout owner, stderr owner, cleanup owner, and V1 compatibility statement. Do not fold these codes into the frozen product-term reference.

- [ ] **Step 7: Reconcile design, explanation, critique, and roadmap**

For every audited defect and every original B2CH-T01 through B2CH-T09 item, record one of:

```text
closed by named test and implementation commit
still open and blocking B2c-H
deferred outside B2c-H with no stronger current claim
```

Only mark B2c-H complete when the full named matrix, reviews, formatting, focused suites, 78 CTests, and full Python suite are green. Otherwise keep B2c-H current and B2c-P blocked.

- [ ] **Step 8: Refresh Graphify after documentation changes**

Run:

```sh
graphify . --update
```

Report refresh failure honestly. Do not edit or commit `graphify-out/`, and do not use graph freshness as a closure claim.

- [ ] **Step 9: Commit documentation and final compatibility evidence**

```sh
git add README.md python/README.md \
  'docs/00 Project Hub/Current State and Remaining Work.md' \
  'docs/01 Roadmap/Phase 7 Historical Replay and Backtesting.md' \
  'docs/07 Engineering Notes/Phase 7 B2c-H Hardening Design.md' \
  'docs/07 Engineering Notes/Phase 7 B2c-H Hardening Explained.md' \
  'docs/07 Engineering Notes/Phase 7 B2c-H Hardening Critique.md' \
  'docs/07 Engineering Notes/Phase 7 Retained Capture Evidence.md' \
  'docs/07 Engineering Notes/Phase 7 B2c-H Refusal Codes.md'
git commit -m "docs(phase7): reconcile b2c-h hardening evidence"
```

- [ ] **Step 10: Final clean-state gate**

Run:

```sh
git status --short
git log --oneline --decorate -5
git diff HEAD~3..HEAD --check
```

Expected: clean worktree, logically separated green commits, no generated Graphify files staged, no temporary test assets, and no AI authorship trailers.

## Closure checklist

- [ ] No direct-child exit can leave an in-PGID descendant alive.
- [ ] First and second interrupt paths publish the correct report after reap/quiescence.
- [ ] SIGINT, SIGTERM, SIGKILL, ESRCH, EPERM, zombie, malformed sampler, and no-sample behavior are individually tested.
- [ ] Stdout and stderr independently enforce 64 MiB without deadlock or retained logs.
- [ ] Free-space, raw, aggregate, reservation, equality, and one-byte-over boundaries are tested.
- [ ] Configured paths, report, roots, symlinks, escapes, duplicates, capture equality, and ancestor overlaps have one unambiguous contract.
- [ ] Manifest V2 cannot select its own role schema or kind.
- [ ] Materialized and eligible stages are independently derived and exact roles are enforced.
- [ ] Mounted regular files and symlinks are inventoried exactly.
- [ ] Every JSON document and JSONL row receives full schema validation.
- [ ] Credential scanning detects the supported synthetic patterns without rejecting its own report or benign hashes/public IDs.
- [ ] Product, measurement, telemetry, normalization, feature, result, risk, and repetition lineage are independently rebuilt.
- [ ] V1 behavior and accepted bytes remain frozen.
- [ ] Capture V2, normalization V3, features V3, Backtest/Result V4, risk, products, checkpoints, and fixtures remain green.
- [ ] Documentation matches the actual supported layout and refusal behavior.
- [ ] B2c-P remains blocked unless the complete B2c-H gate is genuinely closed.
