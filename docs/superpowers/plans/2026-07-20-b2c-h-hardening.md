# B2c-H Evidence and Measurement Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add additive, offline B2c-H measurement and evidence verification controls while preserving every V1 command and accepted artifact meaning.

**Architecture:** Keep `pmm_phase7_evidence.py` as the frozen V1 surface plus V2 CLI/verifier adapter. Put all process-group, stream, sampling, accounting, and report-publishing ownership in `pmm_phase7_measurement.py`; V2 evidence reconstruction remains in the evidence module and consumes formal successor schemas.

**Tech Stack:** Python standard library, JSON Schema validation already provided by `pmm_phase7`, unittest, Nix/uv.

## Global Constraints

- V1 `measure` and `verify` behavior, output, exit codes, and first-failure order are frozen.
- No network, venue feed, retained capture, product acquisition, or accepted-artifact rewrite.
- V2 uses a 64 MiB ceiling for each captured stream, per the approved implementation instruction.
- All new behavior is test-first; every commit is green.
- Do not claim Result V4 streaming, telemetry atomicity, escaped-daemon containment, or performance improvements.

---

### Task 1: V2 measurement supervisor

**Files:**
- Create: `python/pmm_phase7_measurement.py`
- Create: `python/tests/test_phase7_b2c_measurement.py`
- Modify: `python/pmm_phase7_evidence.py`
- Create: `schemas/historical/b2c-measurement-v2.schema.json`
- Create: `schemas/historical/b2c-evidence-policy-v2.schema.json`

**Interfaces:**
- Produces `run_measurement_v2(config) -> MeasurementResult` and a JSON-serializable Measurement V2 report.
- Consumes command argv, accounting roots, policy controls, and identity files from the additive CLI.

- [ ] Write each named lifecycle/sampler/storage test from the approved design, observing its missing-module or missing-command failure.
- [ ] Implement the smallest PGID-owned supervisor: preflight, concurrent bounded streams, valid PGID sampling, SIGINT/SIGTERM/SIGKILL grace/reap, report publishing, and typed result.
- [ ] Add `measure-v2` only; leave the V1 parser branch unchanged.
- [ ] Run `python -m unittest python.tests.test_phase7_b2c_measurement` and the existing B2c evidence tests.
- [ ] Commit `feat(phase7): harden b2c measurement lifecycle` after scoped tests pass.

### Task 2: V2 mounted verifier and successor schemas

**Files:**
- Modify: `python/pmm_phase7_evidence.py`
- Modify: `python/tests/test_phase7_b2c_evidence.py`
- Create: `schemas/historical/b2c-evidence-manifest-v2.schema.json`
- Create: `schemas/historical/b2c-repetition-inventory-v1.schema.json`
- Create: `schemas/historical/b2c-credential-scan-v1.schema.json`
- Create: `schemas/historical/risk-conformance-trace-v2.schema.json`

**Interfaces:**
- Produces `verify_evidence_manifest_v2(manifest_path, artifact_root) -> dict` and `verify-v2` CLI.
- Consumes exact mounted members and reconstructs membership, schema, scanner, lineage, and repetition facts.

- [ ] Add individually named positive, schema, role, inventory, lineage, scanner, and V1-freeze tests; run them to observe the absent V2 entrypoint failures.
- [ ] Implement a private immutable role registry, additive schema dispatch, exact stage/outcome enforcement, full JSON/JSONL validation, scanner, product delegation, inventory rebuild, and exact lineage reconciliation.
- [ ] Run the focused evidence and measurement modules and retain the existing V1 test assertions.
- [ ] Commit `feat(phase7): reconstruct b2c evidence and lineage` after scoped tests pass.

### Task 3: Compatibility closure

**Files:**
- Modify: `python/tests/test_phase7_b2c_evidence.py`
- Modify: `python/tests/test_phase7_b2c_measurement.py`

- [ ] Add individually named frozen-byte/CLI and partial-publication compatibility tests.
- [ ] Run all focused compatibility commands, format, and full suite; use systematic debugging for unexpected failures.
- [ ] Commit `test(phase7): close b2c-h compatibility gates` only after all validation is green.

### Task 4: Documentation and navigation closure

**Files:**
- Modify: `README.md`, `python/README.md`, the B2c operator/design/explanation/critique notes, refusal-code reference, Phase 7 notes, Project Hub, current-state roadmap, and Phase 7 roadmap.

- [ ] Record actual commands/counts and distinguish implemented controls, closed defects, unmeasured debt, V1 compatibility, and no retained evidence.
- [ ] Refresh Graphify incrementally after documentation changes; do not commit its generated output.
- [ ] Commit `docs(phase7): close b2c-h hardening` only after all closure gates pass.
