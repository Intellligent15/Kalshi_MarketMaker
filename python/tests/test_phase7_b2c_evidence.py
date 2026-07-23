from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

import pmm_phase7 as phase7
import pmm_phase7_evidence as evidence
import pmm_b2c_operator as operator
from python.tests.b2c_v2_fixture_builder import build_v2_package
from python.tests.b2c_v2_strict_fixture_builder import (
    build_strict_v2_evidence_package,
    build_strict_v2_pipeline,
)
from python.tests.synthetic_product_package_builder import build_synthetic_product_catalog


class B2cEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_json(self, relative: str, value: dict) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        phase7.write_json(path, value)
        return path

    def write_jsonl(self, relative: str, rows: list[dict]) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(phase7.canonical_json(row) + "\n" for row in rows), encoding="utf-8")
        return path

    @staticmethod
    def _strict_primary_members(fixture) -> list[dict]:
        members = []
        for role, path in fixture.primary_members().items():
            member = {
                "role": role,
                "path": path.relative_to(fixture.root).as_posix(),
                "sha256": phase7.sha256_file(path),
            }
            if path.suffix == ".jsonl":
                member["record_count"] = sum(1 for _ in phase7.iter_jsonl(path))
            members.append(member)
        return members

    def build_package(self) -> tuple[Path, dict]:
        tickers = ["KX-A", "KX-B", "KX-C"]
        self.write_json("control/capture-policy.json", {"schema": "pmm.phase7.b2c_evidence_policy.v1"})
        raw_rows = [
            {
                "schema": "pmm.kalshi.raw_capture_record.v2",
                "kind": "connection_attempt",
                "raw_ingress_ordinal": 1,
                "received_at_utc_ns": 1,
            },
            {
                "schema": "pmm.kalshi.raw_capture_record.v2",
                "kind": "connection_closed",
                "raw_ingress_ordinal": 2,
                "received_at_utc_ns": 2,
            },
        ]
        self.write_jsonl("raw/frames.jsonl", raw_rows)
        self.write_json(
            "raw/metadata.json",
            {
                "schema": "pmm.kalshi.raw_capture.v2",
                "raw_record_count": 2,
                "message_counts_by_type": {},
                "message_counts_by_market": {},
                "credential_values_persisted": False,
            },
        )
        self.write_jsonl("normalized/records.jsonl", [])
        self.write_json(
            "normalized/manifest.json",
            {
                "schema": "pmm.historical.normalization_manifest.v3",
                "event_counts": {},
                "discontinuity_counts": {},
            },
        )
        self.write_json("normalized/source_scopes.json", {"schema": "pmm.historical.source_scope_map.v1"})
        self.write_json("normalized/product.json", {"schema": "pmm.historical.product_map.v3"})
        normalization_manifest = phase7.read_json(self.root / "normalized/manifest.json")
        normalization_manifest.update(
            {
                "input_frames_sha256": phase7.sha256_file(self.root / "raw/frames.jsonl"),
                "input_capture_metadata_sha256": phase7.sha256_file(self.root / "raw/metadata.json"),
                "output_records_sha256": phase7.sha256_file(self.root / "normalized/records.jsonl"),
                "output_source_scopes_sha256": phase7.sha256_file(self.root / "normalized/source_scopes.json"),
                "output_product_sha256": phase7.sha256_file(self.root / "normalized/product.json"),
            }
        )
        phase7.write_json(self.root / "normalized/manifest.json", normalization_manifest)
        self.write_jsonl("features/features.jsonl", [])
        self.write_json(
            "features/manifest.json",
            {
                "schema": "pmm.historical.feature_manifest.v3",
                "input": {
                    "normalization_manifest_sha256": phase7.sha256_file(self.root / "normalized/manifest.json"),
                    "records_sha256": phase7.sha256_file(self.root / "normalized/records.jsonl"),
                    "source_scopes_sha256": phase7.sha256_file(self.root / "normalized/source_scopes.json"),
                    "product_map_sha256": phase7.sha256_file(self.root / "normalized/product.json"),
                },
                "products": [{"row_count": 0} for _ in tickers],
                "output": {
                    "feature_row_count": 0,
                    "feature_rows_sha256": phase7.sha256_file(self.root / "features/features.jsonl"),
                },
            },
        )
        self.write_json("backtest/config.json", {"schema": "pmm.backtest.v4"})
        descriptors = []
        for name in sorted(role.removeprefix("v4_") for role in evidence.V4_ARTIFACT_ROLES):
            path = self.write_jsonl(f"result/{name}.jsonl", [])
            descriptors.append(
                {
                    "name": name,
                    "schema": evidence.V4_ARTIFACT_SCHEMAS[name],
                    "path": path.name,
                    "sha256": phase7.sha256_file(path),
                    "row_count": 0,
                }
            )
        traces = []
        for contract_id, ticker in enumerate(tickers, start=1):
            path = self.write_jsonl(f"result/risk-trace-{contract_id}.jsonl", [])
            traces.append(
                {
                    "ticker": ticker,
                    "contract_id": contract_id,
                    "path": path.name,
                    "sha256": phase7.sha256_file(path),
                    "row_count": 0,
                }
            )
        self.write_json(
            "result/manifest.json",
            {
                "schema": "pmm.backtest_result_manifest.v4",
                "config_sha256": phase7.sha256_file(self.root / "backtest/config.json"),
                "artifacts": descriptors,
                "risk": {"traces": traces},
            },
        )
        for stage in ("capture", "normalization", "feature", "backtest"):
            self.write_json(
                f"measurements/{stage}.json",
                {"schema": "pmm.phase7.b2c_measurement.v1", "stage": stage},
            )
        self.write_json(
            "measurements/normalization-telemetry.json",
            {"schema": "pmm.phase7.b2c_normalization_telemetry.v1"},
        )
        self.write_json(
            "measurements/risk-telemetry.json",
            {"schema": "pmm.phase7.b2c_risk_telemetry.v1"},
        )

        roles = {
            "capture_policy": ("control/capture-policy.json", "pmm.phase7.b2c_evidence_policy.v1", None),
            "raw_frames": ("raw/frames.jsonl", "pmm.kalshi.raw_capture_record.v2", 2),
            "raw_metadata": ("raw/metadata.json", "pmm.kalshi.raw_capture.v2", None),
            "normalized_records": ("normalized/records.jsonl", "pmm.historical.normalized_record.v2", 0),
            "normalization_manifest": ("normalized/manifest.json", "pmm.historical.normalization_manifest.v3", None),
            "source_scopes": ("normalized/source_scopes.json", "pmm.historical.source_scope_map.v1", None),
            "product_map": ("normalized/product.json", "pmm.historical.product_map.v3", None),
            "feature_rows": ("features/features.jsonl", "pmm.historical.feature_row.v2", 0),
            "feature_manifest": ("features/manifest.json", "pmm.historical.feature_manifest.v3", None),
            "backtest_config": ("backtest/config.json", "pmm.backtest.v4", None),
            "result_manifest": ("result/manifest.json", "pmm.backtest_result_manifest.v4", None),
            "capture_measurement": ("measurements/capture.json", "pmm.phase7.b2c_measurement.v1", None),
            "normalization_measurement": ("measurements/normalization.json", "pmm.phase7.b2c_measurement.v1", None),
            "feature_measurement": ("measurements/feature.json", "pmm.phase7.b2c_measurement.v1", None),
            "backtest_measurement": ("measurements/backtest.json", "pmm.phase7.b2c_measurement.v1", None),
            "normalization_telemetry": ("measurements/normalization-telemetry.json", "pmm.phase7.b2c_normalization_telemetry.v1", None),
            "risk_telemetry": ("measurements/risk-telemetry.json", "pmm.phase7.b2c_risk_telemetry.v1", None),
        }
        for descriptor in descriptors:
            roles[f"v4_{descriptor['name']}"] = (
                f"result/{descriptor['path']}", descriptor["schema"], 0
            )
        for trace in traces:
            roles[f"risk_trace_{trace['contract_id']}"] = (
                f"result/{trace['path']}", phase7.RISK_TRACE_SCHEMA, 0
            )
        members = []
        for role, (relative, schema, count) in roles.items():
            path = self.root / relative
            member = {
                "role": role,
                "path": relative,
                "retention_class": "external",
                "schema": schema,
                "byte_length": path.stat().st_size,
                "sha256": phase7.sha256_file(path),
            }
            if count is not None:
                member["record_count"] = count
            if role.startswith("risk_trace_"):
                member["contract_id"] = int(role.rsplit("_", 1)[1])
            members.append(member)
        digest = "1" * 64
        payload = {
            "evidence_id": "b2c-test",
            "capture_spec": {
                "policy_sha256": phase7.sha256_file(self.root / "control/capture-policy.json"),
                "started_at_utc": "2026-07-18T00:00:00Z",
                "ended_at_utc": "2026-07-18T12:00:00Z",
                "duration_seconds": 43200,
                "market_count": 3,
                "raw_budget_bytes": 1073741824,
                "total_budget_bytes": 5368709120,
            },
            "capture_outcome": {
                "exit_code": 0,
                "shutdown_status": "completed",
                "capture_continuity": "continuous_within_recorded_mechanical_scopes",
                "data_usability": "strict_eligible",
                "furthest_eligible_stage": "backtest_v4",
            },
            "market_tickers": tickers,
            "retention": {
                "owner": "test-owner",
                "durable_location": "test-only",
                "large_bytes_in_git": False,
            },
            "product_lineage": [
                {
                    "ticker": ticker,
                    "status": "reviewed",
                    "effective_from_utc": "2026-07-18T00:00:00Z",
                    "effective_until_utc": "2026-07-19T00:00:00Z",
                    "product_terms_sha256": digest,
                    "source_manifest_sha256": "2" * 64,
                    "review_sha256": "3" * 64,
                    "conversion_policy_sha256": "4" * 64,
                }
                for ticker in tickers
            ],
            "members": members,
            "lineage_edges": [
                {"from_role": "raw_frames", "to_role": "normalization_manifest"},
                {"from_role": "normalization_manifest", "to_role": "feature_manifest"},
                {"from_role": "feature_manifest", "to_role": "result_manifest"},
            ],
            "repetitions": [
                {
                    "stage": stage,
                    "first_inventory_sha256": digest,
                    "second_inventory_sha256": digest,
                    "byte_identical": True,
                }
                for stage in ("normalization_v3", "features_v3", "backtest_v4")
            ],
            "credential_scan": {"status": "passed", "scanner_version": "test-v1"},
        }
        manifest = {
            "schema": evidence.EVIDENCE_SCHEMA,
            "payload": payload,
            "payload_sha256": evidence._payload_sha256(payload),
        }
        manifest_path = self.write_json("evidence-manifest.json", manifest)
        return manifest_path, manifest

    def rewrite_manifest(self, path: Path, manifest: dict) -> None:
        manifest["payload_sha256"] = evidence._payload_sha256(manifest["payload"])
        phase7.write_json(path, manifest)

    def test_index_and_mounted_package_verify_without_mutation(self) -> None:
        policy_path = phase7.REPOSITORY_ROOT / "configs/phase7/b2c_evidence_policy_v1.json"
        phase7.validate_historical_schema(
            phase7.read_json(policy_path),
            "b2c-evidence-policy-v1.schema.json",
            "EvidencePolicySchemaMismatch",
        )
        manifest_path, _ = self.build_package()
        before = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        index = evidence.verify_evidence_manifest(manifest_path)
        full = evidence.verify_evidence_manifest(
            manifest_path, artifact_root=self.root, require_artifacts=True
        )
        self.assertFalse(index["artifacts_verified"])
        self.assertTrue(full["artifacts_verified"])
        self.assertEqual(
            before,
            {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*") if path.is_file()},
        )

    def test_index_rejects_each_single_control_defect(self) -> None:
        cases = (
            ("payload", lambda value: value.__setitem__("payload_sha256", "0" * 64), "EvidencePayloadHashMismatch", False),
            ("ticker-order", lambda value: value["payload"]["market_tickers"].reverse(), "EvidenceMarketMembershipMismatch", True),
            ("lineage", lambda value: value["payload"]["product_lineage"][0].__setitem__("ticker", "WRONG"), "EvidenceProductLineageMismatch", True),
            ("duplicate-role", lambda value: value["payload"]["members"][2].__setitem__("role", "raw_frames"), "EvidenceMemberDuplicate", True),
            ("bad-edge", lambda value: value["payload"]["lineage_edges"][0].__setitem__("from_role", "missing"), "EvidenceLineageMismatch", True),
            ("repetition", lambda value: value["payload"]["repetitions"][0].__setitem__("byte_identical", False), "EvidenceRepetitionMismatch", True),
            ("outcome", lambda value: value["payload"]["capture_outcome"].__setitem__("exit_code", 2), "EvidenceOutcomeMismatch", True),
        )
        for name, mutate, code, rehash in cases:
            with self.subTest(defect=name):
                shutil.rmtree(self.root)
                self.root.mkdir()
                path, manifest = self.build_package()
                mutate(manifest)
                if rehash:
                    self.rewrite_manifest(path, manifest)
                else:
                    phase7.write_json(path, manifest)
                with self.assertRaisesRegex(ValueError, code):
                    evidence.verify_evidence_manifest(path)

    def test_full_verification_rejects_each_member_defect(self) -> None:
        cases = ("missing", "truncated", "false-count", "raw-count", "symlink", "result", "extra")
        for name in cases:
            with self.subTest(defect=name):
                shutil.rmtree(self.root)
                self.root.mkdir()
                manifest_path, manifest = self.build_package()
                frames = self.root / "raw/frames.jsonl"
                if name == "missing":
                    frames.unlink()
                elif name == "truncated":
                    frames.write_bytes(frames.read_bytes()[:-1])
                elif name == "false-count":
                    member = next(item for item in manifest["payload"]["members"] if item["role"] == "raw_frames")
                    member["record_count"] = 3
                    self.rewrite_manifest(manifest_path, manifest)
                elif name == "raw-count":
                    metadata = phase7.read_json(self.root / "raw/metadata.json")
                    metadata["raw_record_count"] = 3
                    phase7.write_json(self.root / "raw/metadata.json", metadata)
                    member = next(item for item in manifest["payload"]["members"] if item["role"] == "raw_metadata")
                    member["byte_length"] = (self.root / member["path"]).stat().st_size
                    member["sha256"] = phase7.sha256_file(self.root / member["path"])
                    self.rewrite_manifest(manifest_path, manifest)
                elif name == "symlink":
                    target = self.root / "raw/frames-real.jsonl"
                    frames.rename(target)
                    frames.symlink_to(target)
                elif name == "extra":
                    (self.root / "undeclared.txt").write_text("extra", encoding="utf-8")
                else:
                    result = phase7.read_json(self.root / "result/manifest.json")
                    result["artifacts"][0]["row_count"] = 1
                    phase7.write_json(self.root / "result/manifest.json", result)
                    member = next(item for item in manifest["payload"]["members"] if item["role"] == "result_manifest")
                    member["byte_length"] = (self.root / member["path"]).stat().st_size
                    member["sha256"] = phase7.sha256_file(self.root / member["path"])
                    self.rewrite_manifest(manifest_path, manifest)
                with self.assertRaises(evidence.EvidenceError):
                    evidence.verify_evidence_manifest(
                        manifest_path, artifact_root=self.root, require_artifacts=True
                    )

    def test_cli_streams_status_and_measurement_create_new_contract(self) -> None:
        manifest_path, _ = self.build_package()
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = evidence.main(["verify", "--manifest", str(manifest_path)])
        self.assertEqual(status, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertTrue(json.loads(stdout.getvalue())["verified"])

        report = self.root / "measurement.json"
        output = self.root / "measured-output.txt"
        command = [
            sys.executable,
            "-c",
            f"from pathlib import Path; Path({str(output)!r}).write_text('measured')",
        ]
        measured = evidence.measure_command(
            stage="fixture",
            command=command,
            report_path=report,
            input_paths=[manifest_path],
            output_paths=[output],
            identity_files=[manifest_path],
            sample_interval=0.01,
            max_output_bytes=1024,
        )
        self.assertEqual(measured["exit_code"], 0)
        self.assertEqual(measured["resources"]["final_output_bytes"], len("measured"))
        self.assertTrue(report.is_file())
        before = report.read_bytes()
        with self.assertRaisesRegex(evidence.EvidenceError, "MeasurementOutputExists"):
            evidence.measure_command(
                stage="fixture",
                command=command,
                report_path=report,
                input_paths=[],
                output_paths=[],
                identity_files=[],
                sample_interval=0.01,
                max_output_bytes=1024,
            )
        self.assertEqual(before, report.read_bytes())

    def test_measurement_interrupts_the_process_group_at_the_output_budget(self) -> None:
        output = self.root / "budget-output"
        report = self.root / "budget-report.json"
        command = [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; import time; "
                f"Path({str(output)!r}).write_bytes(b'x' * 64); time.sleep(2)"
            ),
        ]
        measured = evidence.measure_command(
            stage="budget-fixture",
            command=command,
            report_path=report,
            input_paths=[],
            output_paths=[output],
            identity_files=[],
            sample_interval=0.01,
            max_output_bytes=32,
        )
        self.assertTrue(measured["resources"]["output_budget_exceeded"])
        self.assertEqual(measured["resources"]["termination_reason"], "output_budget_exceeded")
        self.assertNotEqual(measured["exit_code"], 0)

    def test_verify_v2_rebuilds_canonical_inventory_from_mounted_root(self) -> None:
        mounted = self.root / "mounted"
        (mounted / "nested").mkdir(parents=True)
        (mounted / "z.txt").write_bytes(b"z")
        (mounted / "nested/a.txt").write_bytes(b"alpha")
        inventory = evidence.build_repetition_inventory(mounted)
        self.assertEqual(
            inventory["entries"],
            [
                {"path": "nested/a.txt", "byte_length": 5,
                 "sha256": hashlib.sha256(b"alpha").hexdigest()},
                {"path": "z.txt", "byte_length": 1,
                 "sha256": hashlib.sha256(b"z").hexdigest()},
            ],
        )
        self.assertEqual(inventory["schema"], "pmm.phase7.b2c_repetition_inventory.v1")

    def test_verify_v2_rejects_synthetic_authorization_header(self) -> None:
        findings = evidence.scan_credential_bytes(
            [("control/command.txt", b"Authorization: Bearer synthetic-test-token")]
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule_id"], "authorization_header")
        self.assertNotIn("control/command.txt", findings[0].values())

    def test_verify_v2_cli_is_additive_and_does_not_reinterpret_v1_manifest(self) -> None:
        manifest_path, _ = self.build_package()
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = evidence.main(["verify-v2", "--manifest", str(manifest_path)])
        self.assertEqual(status, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("EvidenceV2ManifestSchemaMismatch", stderr.getvalue())

    def test_verify_v2_cli_normalizes_malformed_json_to_manifest_schema_mismatch(self) -> None:
        manifest_path = self.root / "malformed-v2.json"
        manifest_path.write_text("{not-json", encoding="utf-8")
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = evidence.main(["verify-v2", "--manifest", str(manifest_path)])
        self.assertEqual(status, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("EvidenceV2ManifestSchemaMismatch", stderr.getvalue())
        self.assertNotIn("Expecting property name", stderr.getvalue())

    def test_verify_v2_cli_success_is_status_zero_stdout_only(self) -> None:
        fixture = build_v2_package(self.root, product_status="unavailable")
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = evidence.main(["verify-v2", "--manifest", str(fixture.manifest_path)])
        self.assertEqual(status, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertTrue(json.loads(stdout.getvalue())["verified"])

    def test_v1_measure_cli_golden_child_nonzero_keeps_wrapper_status_zero(self) -> None:
        report = self.root / "v1-child-nonzero.json"
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = evidence.main([
                "measure", "--stage", "fixture", "--report", str(report),
                "--sample-interval", "0.01", "--", sys.executable, "-c",
                "import sys,time; print('child-out'); print('child-err', file=sys.stderr); "
                "time.sleep(.03); raise SystemExit(7)",
            ])
        payload = json.loads(stdout.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(payload["exit_code"], 7)
        self.assertEqual(payload["stdout_sha256"], hashlib.sha256(b"child-out\n").hexdigest())
        self.assertEqual(payload["stderr_sha256"], hashlib.sha256(b"child-err\n").hexdigest())
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(phase7.read_json(report), payload)

    def test_v1_measure_cli_golden_refusal_is_status_two_stderr_only(self) -> None:
        report = self.root / "v1-existing.json"
        report.write_text("sentinel", encoding="utf-8")
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = evidence.main([
                "measure", "--stage", "fixture", "--report", str(report),
                "--", sys.executable, "-c", "pass",
            ])
        self.assertEqual(status, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(
            stderr.getvalue(),
            f"error: MeasurementOutputExists: report already exists: {report.resolve()}\n",
        )
        self.assertEqual(report.read_text(encoding="utf-8"), "sentinel")

    def test_measure_v2_cli_status_streams_and_report_matrix(self) -> None:
        cases = (
            ("success", "import time; time.sleep(.03)", 0, "MeasurementV2Completed", True),
            ("record-only", "import time; time.sleep(.03); raise SystemExit(2)", 2, "MeasurementV2RecordOnly", True),
            ("child-failure", "import time; time.sleep(.03); raise SystemExit(7)", 1, "MeasurementV2ChildFailure", True),
        )
        for name, script, expected_status, expected_code, published in cases:
            with self.subTest(case=name):
                package = self.root / name
                package.mkdir()
                report = package / "measurements/report.json"
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    status = evidence.main([
                        "measure-v2", "--stage", "capture-v2", "--report", str(report),
                        "--package-root", str(package), "--raw-root", str(package / "raw"),
                        "--output-root", str(package / "raw"), "--", sys.executable, "-c", script,
                    ])
                self.assertEqual(status, expected_status)
                self.assertEqual(report.exists(), published)
                if status == 0:
                    self.assertEqual(stderr.getvalue(), "")
                    self.assertEqual(json.loads(stdout.getvalue())["schema"], "pmm.phase7.b2c_measurement.v2")
                else:
                    self.assertEqual(stdout.getvalue(), "")
                    self.assertEqual(stderr.getvalue(), f"error: {expected_code}: report={report.resolve()}\n")

    def test_measure_v2_cli_preflight_refusal_never_claims_report_path(self) -> None:
        package = self.root / "preflight"
        package.mkdir()
        report = package / "measurements/report.json"
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = evidence.main([
                "measure-v2", "--stage", "capture-v2", "--report", str(report),
                "--package-root", str(package), "--raw-root", str(package / "raw"),
                "--output-root", str(package / "raw"), "--",
            ])
        self.assertEqual(status, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("MeasurementConfigInvalid", stderr.getvalue())
        self.assertNotIn("report=", stderr.getvalue())
        self.assertFalse(report.exists())

    def test_measure_v2_cli_publication_failure_never_claims_report_path(self) -> None:
        package = self.root / "publication"
        package.mkdir()
        report = package / "measurements/report.json"
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(evidence.measurement_v2, "_publish_report", side_effect=OSError("synthetic")):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                status = evidence.main([
                    "measure-v2", "--stage", "capture-v2", "--report", str(report),
                    "--package-root", str(package), "--raw-root", str(package / "raw"),
                    "--output-root", str(package / "raw"), "--", sys.executable, "-c",
                    "import time; time.sleep(.03)",
                ])
        self.assertEqual(status, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "error: MeasurementV2PublicationFailed\n")
        self.assertFalse(report.exists())

    def test_measure_v2_cli_wrapper_failure_is_status_one_with_published_report(self) -> None:
        package = self.root / "wrapper"
        package.mkdir()
        report = package / "measurements/report.json"
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = evidence.main([
                "measure-v2", "--stage", "capture-v2", "--report", str(report),
                "--package-root", str(package), "--raw-root", str(package / "raw"),
                "--output-root", str(package / "raw"), "--", str(package / "missing-command"),
            ])
        self.assertEqual(status, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(
            stderr.getvalue(), f"error: MeasurementV2WrapperFailure: report={report.resolve()}\n"
        )
        self.assertEqual(phase7.read_json(report)["termination"]["reason"], "wrapper_failure")

    def test_measure_v2_cli_teardown_failure_is_status_one_with_published_report(self) -> None:
        package = self.root / "teardown"
        package.mkdir()
        report = package / "measurements/report.json"
        original = evidence.measurement_v2._shutdown_owned_group

        def fail_after_real_shutdown(**kwargs):
            state = original(**kwargs)
            state.failure_code = "MeasurementTeardownIncomplete"
            state.process_group_quiescent = False
            return state

        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(
            evidence.measurement_v2, "_shutdown_owned_group", side_effect=fail_after_real_shutdown
        ):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                status = evidence.main([
                    "measure-v2", "--stage", "capture-v2", "--report", str(report),
                    "--package-root", str(package), "--raw-root", str(package / "raw"),
                    "--output-root", str(package / "raw"), "--", sys.executable, "-c",
                    "import time; time.sleep(.03)",
                ])
        self.assertEqual(status, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(
            stderr.getvalue(), f"error: MeasurementV2TeardownFailure: report={report.resolve()}\n"
        )
        self.assertEqual(phase7.read_json(report)["termination"]["reason"], "teardown_failure")

    def test_verify_v2_rejects_member_selected_wrong_schema_file(self) -> None:
        fixture = build_v2_package(self.root)
        for member in fixture.manifest["payload"]["members"]:
            member["schema_file"] = "b2c-credential-scan-v1.schema.json"
            member["kind"] = "json"
            member.pop("record_count", None)
        fixture.rewrite_manifest()
        with self.assertRaisesRegex(
            evidence.EvidenceError, "EvidenceV2RoleSchemaMismatch"
        ):
            evidence.verify_evidence_manifest_v2(fixture.manifest_path)

    def test_verify_raw_only_completed_package(self) -> None:
        fixture = build_v2_package(self.root, product_status="unavailable")
        result = evidence.verify_evidence_manifest_v2(fixture.manifest_path)
        self.assertTrue(result["verified"])
        self.assertFalse(result["artifacts_verified"])

    def test_credential_scan_detects_quoted_json_assignment(self) -> None:
        findings = evidence.scan_credential_bytes(
            [("payload.json", b'{"api_key": "synthetic-secret"}')]
        )
        self.assertEqual([item["rule_id"] for item in findings], ["credential_assignment"])

    def test_verify_v2_rejects_member_selected_wrong_kind(self) -> None:
        fixture = build_v2_package(self.root, product_status="unavailable")
        member = next(item for item in fixture.manifest["payload"]["members"] if item["role"] == "raw_frames")
        member["kind"] = "json"
        member.pop("record_count")
        fixture.rewrite_manifest()
        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2RoleSchemaMismatch"):
            evidence.verify_evidence_manifest_v2(fixture.manifest_path)

    def test_verify_v2_rejects_correct_schema_with_wrong_role(self) -> None:
        fixture = build_v2_package(self.root, product_status="unavailable")
        policy = next(item for item in fixture.manifest["payload"]["members"] if item["role"] == "capture_policy")
        metadata = next(item for item in fixture.manifest["payload"]["members"] if item["role"] == "raw_metadata")
        policy["role"], metadata["role"] = metadata["role"], policy["role"]
        fixture.rewrite_manifest()
        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2RoleSchemaMismatch"):
            evidence.verify_evidence_manifest_v2(fixture.manifest_path)

    def test_verify_v2_rejects_unknown_role(self) -> None:
        fixture = build_v2_package(self.root, product_status="unavailable")
        fixture.manifest["payload"]["members"][0]["role"] = "unknown_role"
        fixture.rewrite_manifest()
        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2RoleForbidden"):
            evidence.verify_evidence_manifest_v2(fixture.manifest_path)

    def test_verify_raw_stage_rejects_normalization_role(self) -> None:
        fixture = build_v2_package(self.root, materialized_stage="normalization_record_only", product_status="unavailable")
        fixture.manifest["payload"]["furthest_materialized_stage"] = "raw"
        fixture.rewrite_manifest()
        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2RoleForbidden"):
            evidence.verify_evidence_manifest_v2(fixture.manifest_path)

    def test_verify_v2_real_reviewed_product_package_cannot_cover_fixed_capture(self) -> None:
        source = (
            phase7.REPOSITORY_ROOT
            / "configs/product_catalog/kalshi/production/markets/KXHMONTH-26JUL"
            / "2026-07-17T150716Z-150837Z-contemporaneous-bracketed"
        )
        fixture = build_v2_package(
            self.root,
            product_status="bracketed",
            eligible_stage="normalization_record_only",
            product_package=source,
            conversion_policy=(
                phase7.REPOSITORY_ROOT
                / "configs/product_catalog/conversion_policies/integer_cents_whole_contracts_v1.json"
            ),
        )
        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2EligibilityMismatch"):
            evidence.verify_evidence_manifest_v2(
                fixture.manifest_path, artifact_root=self.root, require_artifacts=True
            )

    def test_verify_raw_materialization_cannot_self_assert_backtest_eligibility(self) -> None:
        fixture = build_v2_package(
            self.root, eligible_stage="backtest_v4", product_status="bracketed"
        )
        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2EligibilityMismatch"):
            evidence.verify_evidence_manifest_v2(fixture.manifest_path)

    def test_verify_clean_raw_with_unavailable_product_derives_record_only_eligibility(self) -> None:
        fixture = build_v2_package(
            self.root, eligible_stage="normalization_record_only", product_status="unavailable"
        )
        self.assertTrue(evidence.verify_evidence_manifest_v2(fixture.manifest_path)["verified"])

    def test_verify_observed_strict_package_requires_operational_approval(self) -> None:
        fixture = build_v2_package(
            self.root, eligible_stage="normalization_record_only", product_status="unavailable"
        )
        metadata_path = self.root / "raw/metadata.json"
        metadata = phase7.read_json(metadata_path)
        metadata["truth_category"] = "Observed"
        phase7.write_json(metadata_path, metadata)
        member = next(
            item
            for item in fixture.manifest["payload"]["members"]
            if item["role"] == "raw_metadata"
        )
        member["byte_length"] = metadata_path.stat().st_size
        member["sha256"] = phase7.sha256_file(metadata_path)
        fixture.refresh_credential_report()

        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2RoleMissing"):
            evidence.verify_evidence_manifest_v2(
                fixture.manifest_path, artifact_root=self.root, require_artifacts=True
            )

    def test_verify_observed_package_accepts_verified_operational_approval(self) -> None:
        fixture = build_v2_package(
            self.root, eligible_stage="normalization_record_only", product_status="unavailable"
        )
        metadata_path = self.root / "raw/metadata.json"
        metadata = phase7.read_json(metadata_path)
        metadata["truth_category"] = "Observed"
        phase7.write_json(metadata_path, metadata)
        metadata_member = next(
            item for item in fixture.manifest["payload"]["members"]
            if item["role"] == "raw_metadata"
        )
        metadata_member["byte_length"] = metadata_path.stat().st_size
        metadata_member["sha256"] = phase7.sha256_file(metadata_path)

        candidates = [
            {
                "ticker": ticker,
                "event_ticker": f"EVENT-{ticker}",
                "series_ticker": f"SERIES-{index}",
                "contract_kind": "binary",
                "status": "open",
                "close_time_utc": "2026-07-19T00:00:00Z",
                "volume_24h_fp": str(10 - index),
            }
            for index, ticker in enumerate(("SYNTH-A", "SYNTH-B", "SYNTH-C"), start=1)
        ]
        page_path = self.write_json(
            "control/candidate-page.json", {"markets": candidates, "cursor": None}
        )
        snapshot_payload = {
            "environment": "production",
            "activity_field": "volume_24h_fp",
            "retrieval_started_at_utc": "2026-07-17T22:00:00Z",
            "retrieval_completed_at_utc": "2026-07-17T22:01:00Z",
            "query": {"endpoint": "/trade-api/v2/markets", "parameters": {"status": "open"}},
            "pagination_complete": True,
            "pages": [{
                "path": page_path.relative_to(self.root).as_posix(),
                "sha256": phase7.sha256_file(page_path),
                "cursor_in": None,
                "cursor_out": None,
            }],
            "capture_window": {
                "started_at_utc": "2026-07-18T00:00:00Z",
                "ended_at_utc": "2026-07-18T12:00:00Z",
                "closing_margin_seconds": 1800,
            },
            "candidates": candidates,
            "selected_market_tickers": ["SYNTH-A", "SYNTH-B", "SYNTH-C"],
        }
        snapshot_path = self.write_json(
            "control/candidate-snapshot.json",
            {
                "schema": operator.CANDIDATE_SNAPSHOT_SCHEMA,
                "payload": snapshot_payload,
                "payload_sha256": operator.payload_sha256(snapshot_payload),
            },
        )
        acquisition_specs = []
        operational_members = [page_path]
        for ticker in ("SYNTH-A", "SYNTH-B", "SYNTH-C"):
            opening = self.write_json(
                f"control/specs/{ticker}-opening.json",
                {"schema": "synthetic.acquisition", "ticker": ticker, "observation": "opening"},
            )
            closing = self.write_json(
                f"control/specs/{ticker}-closing.json",
                {"schema": "synthetic.acquisition", "ticker": ticker, "observation": "closing"},
            )
            operational_members.extend((opening, closing))
            acquisition_specs.append({
                "ticker": ticker,
                "opening_path": opening.relative_to(self.root).as_posix(),
                "opening_sha256": phase7.sha256_file(opening),
                "closing_path": closing.relative_to(self.root).as_posix(),
                "closing_sha256": phase7.sha256_file(closing),
            })
        approval_payload = {
            "candidate_snapshot_sha256": phase7.sha256_file(snapshot_path),
            "policy_sha256": phase7.sha256_file(
                phase7.REPOSITORY_ROOT / "configs/phase7/b2c_evidence_policy_v1.json"
            ),
            "selected_market_tickers": ["SYNTH-A", "SYNTH-B", "SYNTH-C"],
            "capture_window": {
                "started_at_utc": "2026-07-18T00:00:00Z",
                "ended_at_utc": "2026-07-18T12:00:00Z",
            },
            "operator": "test-operator",
            "reviewer": "test-reviewer",
            "acquisition_specs": acquisition_specs,
            "storage": {
                "owner": "test-owner",
                "readers": ["test-owner"],
                "primary_path": str((self.root / "durable-primary").resolve()),
                "backup_path": str((self.root / "durable-backup").resolve()),
                "retention": "project_lifetime",
                "owner_only_writes_during_construction": True,
                "immutable_after_verification": True,
                "hash_restore_check_required": True,
            },
            "approved_by": "test-approver",
            "approved_at_utc": "2026-07-17T23:00:00Z",
        }
        approval_path = self.write_json(
            "control/run-approval.json",
            {
                "schema": operator.RUN_APPROVAL_SCHEMA,
                "payload": approval_payload,
                "payload_sha256": operator.payload_sha256(approval_payload),
            },
        )
        for role, path, schema_file, kind in (
            ("candidate_snapshot", snapshot_path, "b2c-candidate-snapshot-v1.schema.json", "json"),
            ("run_approval", approval_path, "b2c-run-approval-v1.schema.json", "json"),
        ):
            fixture.manifest["payload"]["members"].append({
                "role": role,
                "path": path.relative_to(self.root).as_posix(),
                "schema_file": schema_file,
                "kind": kind,
                "byte_length": path.stat().st_size,
                "sha256": phase7.sha256_file(path),
            })
        for path in operational_members:
            fixture.manifest["payload"]["members"].append({
                "role": "operational_control_member",
                "path": path.relative_to(self.root).as_posix(),
                "schema_file": None,
                "kind": "opaque",
                "byte_length": path.stat().st_size,
                "sha256": phase7.sha256_file(path),
            })
        fixture.manifest["payload"]["lineage_edges"] = evidence._derive_role_lineage(
            fixture.manifest["payload"]["members"], "raw"
        )
        fixture.refresh_credential_report()

        result = evidence.verify_evidence_manifest_v2(
            fixture.manifest_path, artifact_root=self.root, require_artifacts=True
        )

        self.assertTrue(result["artifacts_verified"])

    def test_verify_truth_boundary_rejects_raw_product_mismatch(self) -> None:
        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2EligibilityMismatch"):
            evidence._verify_truth_boundary(
                {"truth_category": "Observed"},
                {"product_packages": [{"truth_category": "Synthetic"}]},
            )

    def test_verify_exit_one_rejects_normalization_v3_stage(self) -> None:
        fixture = build_v2_package(
            self.root, materialized_stage="normalization_v3", eligible_stage="raw", capture_exit=1
        )
        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2EligibilityMismatch"):
            evidence.verify_evidence_manifest_v2(fixture.manifest_path)

    def test_verify_exit_two_rejects_features_v3_stage(self) -> None:
        fixture = build_v2_package(
            self.root, materialized_stage="features_v3", eligible_stage="normalization_record_only", capture_exit=2
        )
        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2EligibilityMismatch"):
            evidence.verify_evidence_manifest_v2(fixture.manifest_path)

    def test_verify_exit_130_rejects_backtest_v4_stage(self) -> None:
        fixture = build_v2_package(
            self.root, materialized_stage="backtest_v4", eligible_stage="raw", capture_exit=130
        )
        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2EligibilityMismatch"):
            evidence.verify_evidence_manifest_v2(fixture.manifest_path)

    def test_verify_product_review_must_cover_capture_interval(self) -> None:
        source = (
            phase7.REPOSITORY_ROOT
            / "configs/product_catalog/kalshi/production/markets/KXHMONTH-26JUL"
            / "2026-07-17T150716Z-150837Z-contemporaneous-bracketed"
        )
        fixture = build_v2_package(
            self.root,
            eligible_stage="backtest_v4",
            product_status="bracketed",
            product_package=source,
            conversion_policy=(phase7.REPOSITORY_ROOT / "configs/product_catalog/conversion_policies/integer_cents_whole_contracts_v1.json"),
        )
        fixture.manifest["payload"]["capture_spec"]["started_at_utc"] = "2030-01-01T00:00:00Z"
        fixture.manifest["payload"]["capture_spec"]["ended_at_utc"] = "2030-01-01T00:00:01Z"
        fixture.rewrite_manifest()
        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2EligibilityMismatch"):
            evidence.verify_evidence_manifest_v2(
                fixture.manifest_path, artifact_root=self.root, require_artifacts=True
            )

    def test_credential_scan_detects_encrypted_private_key(self) -> None:
        findings = evidence.scan_credential_bytes(
            [("payload.bin", b"-----BEGIN ENCRYPTED PRIVATE KEY-----\nsynthetic")]
        )
        self.assertEqual([item["rule_id"] for item in findings], ["pem_private_key"])

    def test_verify_v2_rejects_symlinked_artifact_root(self) -> None:
        mounted = self.root / "mounted"
        fixture = build_v2_package(mounted, product_status="unavailable")
        link = self.root / "mounted-link"
        link.symlink_to(mounted, target_is_directory=True)
        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2MembershipMismatch"):
            evidence.verify_evidence_manifest_v2(
                link / fixture.manifest_path.name, artifact_root=link, require_artifacts=True
            )

    def test_verify_v2_role_registry_schema_runtime_parity(self) -> None:
        for role, spec in evidence.V2_ROLE_REGISTRY.items():
            with self.subTest(role=role):
                schema = phase7.read_json(phase7.HISTORICAL_SCHEMA_ROOT / spec.schema_file)
                discriminator = schema.get("properties", {}).get("schema", {})
                self.assertIn(spec.schema_tag, discriminator.get("enum", [discriminator.get("const")]))

    def test_verify_record_only_stage_requires_normalization_control_roles(self) -> None:
        required = {
            "normalization_measurement", "normalization_telemetry",
            "normalization_inventory_first", "normalization_inventory_second",
        }
        for role in required:
            with self.subTest(role=role):
                shutil.rmtree(self.root)
                self.root.mkdir()
                fixture = build_v2_package(
                    self.root, materialized_stage="normalization_record_only",
                    eligible_stage="normalization_record_only",
                )
                fixture.manifest["payload"]["members"] = [
                    item for item in fixture.manifest["payload"]["members"] if item["role"] != role
                ]
                fixture.rewrite_manifest()
                with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2RoleMissing"):
                    evidence.verify_evidence_manifest_v2(fixture.manifest_path)

    def test_verify_features_v3_rejects_backtest_role(self) -> None:
        fixture = build_v2_package(
            self.root, materialized_stage="backtest_v4", eligible_stage="backtest_v4"
        )
        fixture.manifest["payload"]["furthest_materialized_stage"] = "features_v3"
        fixture.rewrite_manifest()
        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2RoleForbidden"):
            evidence.verify_evidence_manifest_v2(fixture.manifest_path)

    def test_verify_backtest_v4_requires_all_typed_streams_and_traces(self) -> None:
        for role in [*sorted(evidence.V4_ARTIFACT_ROLES), "risk_trace_1"]:
            with self.subTest(role=role):
                shutil.rmtree(self.root)
                self.root.mkdir()
                fixture = build_v2_package(
                    self.root, materialized_stage="backtest_v4", eligible_stage="backtest_v4"
                )
                fixture.manifest["payload"]["members"] = [
                    item for item in fixture.manifest["payload"]["members"] if item["role"] != role
                ]
                fixture.rewrite_manifest()
                with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2RoleMissing"):
                    evidence.verify_evidence_manifest_v2(fixture.manifest_path)

    def test_verify_v2_checks_membership_before_declared_member_schema(self) -> None:
        fixture = build_v2_package(self.root, product_status="unavailable")
        (self.root / "undeclared-target").write_bytes(b"x")
        (self.root / "undeclared-link").symlink_to(self.root / "undeclared-target")
        (self.root / "raw/metadata.json").write_bytes(b"not json")
        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2MembershipMismatch"):
            evidence.verify_evidence_manifest_v2(
                fixture.manifest_path, artifact_root=self.root, require_artifacts=True
            )

    def test_repetition_inventory_rejects_symlinked_root(self) -> None:
        mounted = self.root / "inventory"
        mounted.mkdir()
        link = self.root / "inventory-link"
        link.symlink_to(mounted, target_is_directory=True)
        with self.assertRaisesRegex(evidence.EvidenceError, "EvidencePathUnsafe"):
            evidence.build_repetition_inventory(link)

    def test_verify_v2_binds_frozen_v1_policy_hash(self) -> None:
        fixture = build_v2_package(self.root, product_status="unavailable")
        policy_path = self.root / "control/capture-policy.json"
        policy = phase7.read_json(policy_path)
        policy["base_policy_sha256"] = "0" * 64
        phase7.write_json(policy_path, policy)
        member = next(item for item in fixture.manifest["payload"]["members"] if item["role"] == "capture_policy")
        member["byte_length"] = policy_path.stat().st_size
        member["sha256"] = phase7.sha256_file(policy_path)
        fixture.refresh_credential_report()
        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2LineageMismatch"):
            evidence.verify_evidence_manifest_v2(
                fixture.manifest_path, artifact_root=self.root, require_artifacts=True
            )

    def test_verify_v2_jsonl_record_count_is_reconstructed(self) -> None:
        fixture = build_v2_package(self.root, product_status="unavailable")
        frames = next(item for item in fixture.manifest["payload"]["members"] if item["role"] == "raw_frames")
        frames["record_count"] = 2
        fixture.rewrite_manifest()
        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2MembershipMismatch"):
            evidence.verify_evidence_manifest_v2(
                fixture.manifest_path, artifact_root=self.root, require_artifacts=True
            )

    def test_verify_v2_raw_metadata_count_is_reconstructed(self) -> None:
        fixture = build_v2_package(self.root, product_status="unavailable")
        metadata_path = self.root / "raw/metadata.json"
        metadata = phase7.read_json(metadata_path)
        metadata["raw_record_count"] = 2
        phase7.write_json(metadata_path, metadata)
        member = next(item for item in fixture.manifest["payload"]["members"] if item["role"] == "raw_metadata")
        member["byte_length"] = metadata_path.stat().st_size
        member["sha256"] = phase7.sha256_file(metadata_path)
        fixture.refresh_credential_report()
        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2MembershipMismatch"):
            evidence.verify_evidence_manifest_v2(
                fixture.manifest_path, artifact_root=self.root, require_artifacts=True
            )

    def test_risk_trace_v2_schema_accepts_existing_emitter_and_rejects_extra_field(self) -> None:
        from jsonschema import Draft202012Validator
        import pmm_phase7 as runtime

        oracle = runtime.CxxRiskOracle.__new__(runtime.CxxRiskOracle)
        oracle.canonical_trace = True
        oracle.trace = []
        oracle.view = lambda: {"event_watermark": 0, "live_orders": [], "pending_orders": []}
        oracle._record("init", {"engine": "cxx_oracle_v2"}, "ready")
        schema = phase7.read_json(phase7.HISTORICAL_SCHEMA_ROOT / "risk-conformance-trace-v2.schema.json")
        validator = Draft202012Validator(schema)
        self.assertTrue(validator.is_valid(oracle.trace[0]))
        mutated = dict(oracle.trace[0], unexpected=True)
        self.assertTrue(validator.is_valid(mutated))

    def test_verify_v2_rejects_outcome_tuple_mismatch(self) -> None:
        for exit_code, field, wrong in (
            (0, "shutdown_status", "failed"),
            (1, "capture_continuity", "observed_discontinuous"),
            (2, "data_usability", "unusable"),
            (130, "shutdown_status", "failed"),
        ):
            with self.subTest(exit_code=exit_code):
                shutil.rmtree(self.root)
                self.root.mkdir()
                eligible = "normalization_record_only" if exit_code in {0, 2} else "raw"
                fixture = build_v2_package(self.root, capture_exit=exit_code, eligible_stage=eligible)
                fixture.manifest["payload"]["capture_outcome"][field] = wrong
                fixture.rewrite_manifest()
                with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2ManifestSchemaMismatch|EvidenceV2EligibilityMismatch"):
                    evidence.verify_evidence_manifest_v2(fixture.manifest_path)

    def test_credential_scan_detects_dsa_private_key(self) -> None:
        findings = evidence.scan_credential_bytes(
            [("payload.bin", b"-----BEGIN DSA PRIVATE KEY-----\nsynthetic")]
        )
        self.assertEqual([item["rule_id"] for item in findings], ["pem_private_key"])

    def test_verify_product_packages_rejects_unselected_declaration(self) -> None:
        payload = {
            "market_tickers": ["SYNTH-A"],
            "product_lineage": [{"ticker": "SYNTH-A", "status": "unavailable"}],
            "product_packages": [{"ticker": "EXTRA", "package_root": "extra", "conversion_policy_path": "policy.json"}],
            "capture_spec": {"started_at_utc": "2026-01-01T00:00:00Z", "ended_at_utc": "2026-01-01T00:00:01Z"},
        }
        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2MembershipMismatch"):
            evidence._verify_product_packages(self.root, payload, set())

    def test_verify_product_packages_resolve_exact_distinct_series_catalog(self) -> None:
        catalog_root = self.root / "catalog"
        catalog = build_synthetic_product_catalog(catalog_root)
        conversion_source = (
            phase7.REPOSITORY_ROOT
            / "configs/product_catalog/conversion_policies/"
            "integer_cents_whole_contracts_v1.json"
        )
        conversion_path = self.root / "conversion-policy.json"
        shutil.copy2(conversion_source, conversion_path)
        declarations = []
        for ticker in ("SYNTH-A", "SYNTH-B", "SYNTH-C"):
            package = catalog.resolve(
                {
                    "ticker": ticker,
                    "capture_started_at_utc_ns": 1_767_225_600_000_000_000,
                    "capture_ended_at_utc_ns": 1_767_268_800_000_000_000,
                }
            )
            declarations.append(
                {
                    "ticker": ticker,
                    "package_root": package.path.relative_to(self.root.resolve()).as_posix(),
                    "conversion_policy_path": conversion_path.name,
                    "truth_category": "Synthetic",
                }
            )
        payload = {
            "market_tickers": ["SYNTH-A", "SYNTH-B", "SYNTH-C"],
            "product_lineage": [
                {"ticker": ticker, "status": "bracketed"}
                for ticker in ("SYNTH-A", "SYNTH-B", "SYNTH-C")
            ],
            "product_packages": declarations,
            "product_catalog_path": "catalog/manifest.json",
            "capture_spec": {
                "started_at_utc": "2026-01-01T00:00:00Z",
                "ended_at_utc": "2026-01-01T12:00:00Z",
            },
        }
        product_paths = {
            path.resolve().relative_to(self.root.resolve()).as_posix()
            for path in catalog_root.rglob("*")
            if path.is_file()
        }
        product_paths.add(conversion_path.name)

        statuses = evidence._verify_product_packages(self.root, payload, product_paths)

        self.assertEqual(
            statuses,
            {ticker: "bracketed" for ticker in ("SYNTH-A", "SYNTH-B", "SYNTH-C")},
        )

    def test_v2_schema_accepts_explicit_product_truth_and_catalog_path(self) -> None:
        fixture = build_v2_package(self.root, product_status="unavailable")
        fixture.manifest["payload"]["product_catalog_path"] = "catalog/manifest.json"
        fixture.manifest["payload"]["product_packages"] = [
            {
                "ticker": "SYNTH-A",
                "package_root": "catalog/packages/SYNTH-A",
                "conversion_policy_path": "control/conversion-policy.json",
                "truth_category": "Synthetic",
            }
        ]
        fixture.rewrite_manifest()

        phase7.validate_historical_schema(
            fixture.manifest,
            "b2c-evidence-manifest-v2.schema.json",
            "EvidenceV2ManifestSchemaMismatch",
        )

    def test_verify_selected_markets_match_raw_config_and_result(self) -> None:
        selected = ["SYNTH-A", "SYNTH-B", "SYNTH-C"]
        raw = {"market_tickers": selected}
        config = {"products": [{"product_identity": {"ticker": ticker}} for ticker in selected]}
        result = {"products": [{"product_identity": {"ticker": ticker}} for ticker in selected]}
        evidence._verify_selected_markets(selected, raw, config, result)
        result["products"][2]["product_identity"]["ticker"] = "EXTRA"
        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2LineageMismatch"):
            evidence._verify_selected_markets(selected, raw, config, result)

    def test_verify_measurement_stage_and_identity_files_are_reconstructed(self) -> None:
        fixture = build_v2_package(self.root, product_status="unavailable")
        measurement_path = self.root / "measurements/capture.json"
        measurement = phase7.read_json(measurement_path)
        measurement["stage"] = "wrong-stage"
        phase7.write_json(measurement_path, measurement)
        member = next(item for item in fixture.manifest["payload"]["members"] if item["role"] == "capture_measurement")
        member["byte_length"] = measurement_path.stat().st_size
        member["sha256"] = phase7.sha256_file(measurement_path)
        fixture.refresh_credential_report()
        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2LineageMismatch|EvidenceV2RoleSchemaMismatch"):
            evidence.verify_evidence_manifest_v2(
                fixture.manifest_path, artifact_root=self.root, require_artifacts=True
            )

    def test_verify_capture_measurement_requires_only_pre_run_policy_identity(self) -> None:
        fixture = build_v2_package(self.root, product_status="unavailable")
        measurement_path = self.root / "measurements/capture.json"
        measurement = phase7.read_json(measurement_path)
        policy_member = next(
            item
            for item in fixture.manifest["payload"]["members"]
            if item["role"] == "capture_policy"
        )
        measurement["identity_files"] = [
            {
                "path": policy_member["path"],
                "sha256": policy_member["sha256"],
            }
        ]
        phase7.write_json(measurement_path, measurement)
        measurement_member = next(
            item
            for item in fixture.manifest["payload"]["members"]
            if item["role"] == "capture_measurement"
        )
        measurement_member["byte_length"] = measurement_path.stat().st_size
        measurement_member["sha256"] = phase7.sha256_file(measurement_path)
        fixture.refresh_credential_report()

        result = evidence.verify_evidence_manifest_v2(
            fixture.manifest_path, artifact_root=self.root, require_artifacts=True
        )

        self.assertTrue(result["verified"])

    def test_verify_capture_measurement_rejects_duplicate_input_identity(self) -> None:
        fixture = build_v2_package(self.root, product_status="unavailable")
        measurement_path = self.root / "measurements/capture.json"
        measurement = phase7.read_json(measurement_path)
        measurement["identity_files"].append(dict(measurement["identity_files"][0]))
        phase7.write_json(measurement_path, measurement)
        measurement_member = next(
            item
            for item in fixture.manifest["payload"]["members"]
            if item["role"] == "capture_measurement"
        )
        measurement_member["byte_length"] = measurement_path.stat().st_size
        measurement_member["sha256"] = phase7.sha256_file(measurement_path)
        fixture.refresh_credential_report()

        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2LineageMismatch"):
            evidence.verify_evidence_manifest_v2(
                fixture.manifest_path, artifact_root=self.root, require_artifacts=True
            )

    def test_verify_normalization_measurement_requires_exact_stage_inputs(self) -> None:
        frames = self.write_jsonl("raw/frames.jsonl", [])
        metadata = self.write_json("raw/metadata.json", {"schema": "synthetic"})
        measurement = self.write_json(
            "measurements/normalization.json",
            {
                "stage": "normalization-v3",
                "identity_files": [
                    {"path": str(frames), "sha256": phase7.sha256_file(frames)}
                ],
            },
        )
        members = [
            {
                "role": "raw_frames",
                "path": "raw/frames.jsonl",
                "sha256": phase7.sha256_file(frames),
            },
            {
                "role": "raw_metadata",
                "path": "raw/metadata.json",
                "sha256": phase7.sha256_file(metadata),
            },
            {
                "role": "normalization_measurement",
                "path": "measurements/normalization.json",
                "sha256": phase7.sha256_file(measurement),
            },
        ]

        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2LineageMismatch"):
            evidence._verify_measurement_identities(self.root, members)

    def test_verify_backtest_rows_telemetry_and_aggregate_counts(self) -> None:
        digest = "1" * 64
        config = {
            "products": [{"product_identity": {"ticker": "SYNTH-A"}, "contract_identity": {"contract_id": 1}}]
        }
        config_path = self.write_json("backtest/config.json", config)
        artifacts = []
        members = [{"role": "backtest_config", "path": "backtest/config.json", "sha256": phase7.sha256_file(config_path)}]
        for name, schema in evidence.V4_ARTIFACT_SCHEMAS.items():
            path = self.write_jsonl(f"result/{name}.jsonl", [])
            artifacts.append({"name": name, "schema": schema, "path": path.name, "sha256": phase7.sha256_file(path), "row_count": 0})
            members.append({"role": f"v4_{name}", "path": f"result/{path.name}", "sha256": phase7.sha256_file(path), "record_count": 0})
        trace_path = self.write_jsonl("result/risk-1.jsonl", [])
        trace = {"ticker": "SYNTH-A", "contract_id": 1, "path": trace_path.name, "sha256": phase7.sha256_file(trace_path), "row_count": 0}
        result = {
            "run_id": "synthetic-run", "feature_definition_sha256": digest,
            "artifacts": artifacts, "aggregate_counts": {},
            "risk": {"traces": [trace]},
            "products": [{"product_identity": {"ticker": "SYNTH-A"}, "contract_identity": {"contract_id": 1}, "risk_trace": trace}],
        }
        result_path = self.write_json("result/manifest.json", result)
        members.extend([
            {"role": "result_manifest", "path": "result/manifest.json", "sha256": phase7.sha256_file(result_path)},
            {"role": "risk_trace_1", "path": "result/risk-1.jsonl", "sha256": phase7.sha256_file(trace_path), "record_count": 0, "contract_id": 1},
        ])
        telemetry = {"config_sha256": phase7.sha256_file(config_path), "products": [{"ticker": "SYNTH-A", "contract_id": 1, "trace_rows": 0}]}
        telemetry_path = self.write_json("measurements/risk.json", telemetry)
        members.append({"role": "risk_telemetry", "path": "measurements/risk.json", "sha256": phase7.sha256_file(telemetry_path)})
        evidence._verify_backtest_rows_and_telemetry(self.root, config, result, members)
        telemetry["config_sha256"] = "0" * 64
        phase7.write_json(telemetry_path, telemetry)
        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2LineageMismatch"):
            evidence._verify_backtest_rows_and_telemetry(self.root, config, result, members)

    def test_verify_real_pipeline_reconstructs_normalization_and_feature_lineage(self) -> None:
        processed = phase7.REPOSITORY_ROOT / "data" / "processed"
        processed.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=processed) as temporary:
            fixture = build_strict_v2_pipeline(Path(temporary) / "package")
            members = []
            for role, path in fixture.primary_members().items():
                member = {
                    "role": role,
                    "path": path.relative_to(fixture.root).as_posix(),
                    "sha256": phase7.sha256_file(path),
                }
                if path.suffix == ".jsonl":
                    member["record_count"] = sum(1 for _ in phase7.iter_jsonl(path))
                members.append(member)

            evidence._verify_normalization_chain(
                fixture.root, ["SYNTH-A", "SYNTH-B", "SYNTH-C"], members
            )
            evidence._verify_feature_chain(
                fixture.root, ["SYNTH-A", "SYNTH-B", "SYNTH-C"], members
            )
            evidence._verify_backtest_upstream_chain(
                fixture.root, ["SYNTH-A", "SYNTH-B", "SYNTH-C"], members
            )

            feature_manifest_path = fixture.feature_roots[0] / "manifest.json"
            feature_manifest_bytes = feature_manifest_path.read_bytes()
            feature_manifest = phase7.read_json(feature_manifest_path)
            feature_manifest["input"]["records_sha256"] = "0" * 64
            phase7.write_json(feature_manifest_path, feature_manifest)
            with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2LineageMismatch"):
                evidence._verify_feature_chain(
                    fixture.root, ["SYNTH-A", "SYNTH-B", "SYNTH-C"], members
                )
            feature_manifest_path.write_bytes(feature_manifest_bytes)

            config_bytes = fixture.backtest_config_path.read_bytes()
            config = phase7.read_json(fixture.backtest_config_path)
            config["inputs"]["features"]["rows_sha256"] = "0" * 64
            phase7.write_json(fixture.backtest_config_path, config)
            with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2LineageMismatch"):
                evidence._verify_backtest_upstream_chain(
                    fixture.root, ["SYNTH-A", "SYNTH-B", "SYNTH-C"], members
                )
            fixture.backtest_config_path.write_bytes(config_bytes)

            telemetry_bytes = fixture.normalization_telemetry_path.read_bytes()
            telemetry = phase7.read_json(fixture.normalization_telemetry_path)
            telemetry["input_frames_sha256"] = "0" * 64
            phase7.write_json(fixture.normalization_telemetry_path, telemetry)
            with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2LineageMismatch"):
                evidence._verify_normalization_chain(
                    fixture.root, ["SYNTH-A", "SYNTH-B", "SYNTH-C"], members
                )
            fixture.normalization_telemetry_path.write_bytes(telemetry_bytes)
            telemetry = phase7.read_json(fixture.normalization_telemetry_path)
            telemetry["sequenced_unique_identities"] += 1
            telemetry["peak_sequenced_unique_identities"] += 1
            phase7.write_json(fixture.normalization_telemetry_path, telemetry)
            with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2LineageMismatch"):
                evidence._verify_normalization_chain(
                    fixture.root, ["SYNTH-A", "SYNTH-B", "SYNTH-C"], members
                )

    def test_verify_v2_accepts_fully_mounted_synthetic_three_market_strict_chain(self) -> None:
        processed = phase7.REPOSITORY_ROOT / "data" / "processed"
        processed.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=processed) as temporary:
            fixture = build_strict_v2_evidence_package(Path(temporary) / "package")

            result = fixture.verify()

            self.assertTrue(result["verified"])
            self.assertTrue(result["artifacts_verified"])
            self.assertEqual(
                fixture.manifest["payload"]["market_tickers"],
                ["SYNTH-A", "SYNTH-B", "SYNTH-C"],
            )
            self.assertEqual(
                fixture.manifest["payload"]["furthest_eligible_stage"],
                "backtest_v4",
            )

    def test_verify_strict_package_is_portable_across_mount_roots(self) -> None:
        processed = phase7.REPOSITORY_ROOT / "data" / "processed"
        processed.mkdir(parents=True, exist_ok=True)
        mounted = self.root / "mounted"
        with tempfile.TemporaryDirectory(dir=processed) as temporary:
            fixture = build_strict_v2_evidence_package(Path(temporary) / "package")
            shutil.copytree(fixture.root, mounted)

        result = evidence.verify_evidence_manifest_v2(
            mounted / fixture.manifest_path.name,
            artifact_root=mounted,
            require_artifacts=True,
        )

        self.assertTrue(result["artifacts_verified"])

    def test_verify_strict_backtest_requires_mounted_product_catalog(self) -> None:
        processed = phase7.REPOSITORY_ROOT / "data" / "processed"
        processed.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=processed) as temporary:
            fixture = build_strict_v2_evidence_package(Path(temporary) / "package")
            payload = dict(fixture.manifest["payload"])
            payload.pop("product_catalog_path")
            product_paths = {
                member["path"]
                for member in payload["members"]
                if member["role"] == "product_package_member"
                and member["path"] != "catalog/manifest.json"
            }

            with self.assertRaisesRegex(
                evidence.EvidenceError, "EvidenceV2EligibilityMismatch"
            ):
                evidence._verify_product_packages(fixture.root, payload, product_paths)

    def test_verify_strict_backtest_rejects_dangling_config_paths(self) -> None:
        processed = phase7.REPOSITORY_ROOT / "data" / "processed"
        processed.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=processed) as temporary:
            fixture = build_strict_v2_evidence_package(Path(temporary) / "package")
            members = fixture.manifest["payload"]["members"]

            evidence._verify_backtest_upstream_chain(
                fixture.root, ["SYNTH-A", "SYNTH-B", "SYNTH-C"], members
            )
            config = phase7.read_json(fixture.root / "backtest/config.json")
            for group, fields in (
                ("normalization", ("manifest_path", "records_path", "source_scopes_path", "product_map_path")),
                ("features", ("manifest_path", "rows_path")),
            ):
                for field in fields:
                    declared = phase7.REPOSITORY_ROOT / config["inputs"][group][field]
                    self.assertTrue(declared.is_file(), f"dangling {group}.{field}")

    def test_verify_measurement_identity_rejects_path_only_mutation(self) -> None:
        processed = phase7.REPOSITORY_ROOT / "data" / "processed"
        processed.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=processed) as temporary:
            fixture = build_strict_v2_evidence_package(Path(temporary) / "package")
            measurement = phase7.read_json(fixture.root / "measurements/capture.json")
            measurement["identity_files"][0]["path"] = "unrelated/capture-policy.json"
            phase7.write_json(fixture.root / "measurements/capture.json", measurement)

            with self.assertRaisesRegex(
                evidence.EvidenceError, "EvidenceV2LineageMismatch"
            ):
                evidence._verify_measurement_identities(
                    fixture.root, fixture.manifest["payload"]["members"]
                )

    def test_normalization_sequence_identity_canonicalizes_subscription_id(self) -> None:
        numeric = {
            "connection_segment_id": 1,
            "subscription_id": 11,
            "market_ticker": "SYNTH-A",
            "source_sequence": 7,
        }
        textual = {**numeric, "subscription_id": "11"}

        self.assertEqual(
            evidence._normalization_sequence_identity(numeric, "independent"),
            evidence._normalization_sequence_identity(textual, "independent"),
        )

    def test_verify_real_normalization_lineage_mutation_matrix(self) -> None:
        processed = phase7.REPOSITORY_ROOT / "data" / "processed"
        processed.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=processed) as temporary:
            fixture = build_strict_v2_evidence_package(Path(temporary) / "package")
            members = fixture.manifest["payload"]["members"]
            selected = ["SYNTH-A", "SYNTH-B", "SYNTH-C"]
            manifest_path = fixture.root / "normalization/manifest.json"
            telemetry_path = fixture.root / "telemetry/normalization.json"
            product_path = fixture.root / "normalization/product.json"
            cases = (
                (manifest_path, lambda value: value.__setitem__("input_frames_sha256", "0" * 64)),
                (manifest_path, lambda value: value.__setitem__("input_capture_metadata_sha256", "0" * 64)),
                (manifest_path, lambda value: value.__setitem__("output_records_sha256", "0" * 64)),
                (manifest_path, lambda value: value.__setitem__("output_source_scopes_sha256", "0" * 64)),
                (manifest_path, lambda value: value.__setitem__("output_product_sha256", "0" * 64)),
                (manifest_path, lambda value: value.__setitem__("product_catalog_sha256", "0" * 64)),
                (manifest_path, lambda value: value.__setitem__("conversion_policy_sha256", "0" * 64)),
                (manifest_path, lambda value: value["product_lineage"][0].__setitem__("review_sha256", "0" * 64)),
                (manifest_path, lambda value: value["market_tickers"].reverse()),
                (manifest_path, lambda value: value["event_counts"].__setitem__("book_snapshot", 99)),
                (manifest_path, lambda value: value.__setitem__("identical_duplicates_skipped", 1)),
                (telemetry_path, lambda value: value.__setitem__("processed_raw_records", 0)),
                (telemetry_path, lambda value: value.__setitem__("sequenced_unique_identities", 99)),
                (telemetry_path, lambda value: value.__setitem__("peak_sequenced_unique_identities", 0)),
                (telemetry_path, lambda value: value["samples"].pop()),
                (product_path, lambda value: value["products"][0].__setitem__("ticker", "WRONG")),
                (product_path, lambda value: value["products"][0].__setitem__("venue_market_id", "wrong-market-id")),
                (product_path, lambda value: value["products"][0].__setitem__("venue_market_id_authority", "wrong-authority")),
                (product_path, lambda value: value["products"][0].__setitem__("source_fidelity", "wrong-fidelity")),
                (product_path, lambda value: value["products"][0]["authoritative_identity"].__setitem__("series_ticker", "WRONG-SERIES")),
                (product_path, lambda value: value["products"][0].__setitem__("product_terms_sha256", "0" * 64)),
                (product_path, lambda value: value["products"][0].__setitem__("source_manifest_sha256", "0" * 64)),
                (product_path, lambda value: value["products"][0].__setitem__("review_sha256", "0" * 64)),
                (product_path, lambda value: value["products"][0].__setitem__("conversion_policy_sha256", "0" * 64)),
            )
            for index, (path, mutation) in enumerate(cases):
                with self.subTest(case=index):
                    original = path.read_bytes()
                    value = phase7.read_json(path)
                    mutation(value)
                    phase7.write_json(path, value)
                    with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2LineageMismatch"):
                        evidence._verify_normalization_chain(
                            fixture.root, selected, members, fixture.manifest["payload"]
                        )
                    path.write_bytes(original)

    def test_verify_real_feature_lineage_mutation_matrix(self) -> None:
        processed = phase7.REPOSITORY_ROOT / "data" / "processed"
        processed.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=processed) as temporary:
            fixture = build_strict_v2_pipeline(Path(temporary) / "package")
            members = self._strict_primary_members(fixture)
            selected = ["SYNTH-A", "SYNTH-B", "SYNTH-C"]
            manifest_path = fixture.feature_roots[0] / "manifest.json"
            cases = (
                lambda value: value["input"].__setitem__("normalization_manifest_sha256", "0" * 64),
                lambda value: value["input"].__setitem__("records_sha256", "0" * 64),
                lambda value: value["input"].__setitem__("source_scopes_sha256", "0" * 64),
                lambda value: value["input"].__setitem__("product_map_sha256", "0" * 64),
                lambda value: value["input"]["capture_identity"].__setitem__("frames_sha256", "0" * 64),
                lambda value: value["input"]["market_tickers"].reverse(),
                lambda value: value["output"].__setitem__("feature_rows_sha256", "0" * 64),
                lambda value: value["output"].__setitem__("feature_row_count", 99),
                lambda value: value["products"][0].__setitem__("input_product_entry_sha256", "0" * 64),
                lambda value: value["products"][0].__setitem__("row_count", 99),
                lambda value: value["products"][0]["reviewed_lineage"].__setitem__("review_sha256", "0" * 64),
            )
            for index, mutation in enumerate(cases):
                with self.subTest(case=index):
                    original = manifest_path.read_bytes()
                    value = phase7.read_json(manifest_path)
                    mutation(value)
                    phase7.write_json(manifest_path, value)
                    with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2LineageMismatch"):
                        evidence._verify_feature_chain(fixture.root, selected, members)
                    manifest_path.write_bytes(original)

            rows_path = fixture.feature_roots[0] / "features.jsonl"
            for field in ("input_records_sha256", "input_product_entry_sha256"):
                with self.subTest(row_lineage=field):
                    original = rows_path.read_bytes()
                    rows = list(phase7.iter_jsonl(rows_path))
                    rows[0]["lineage"][field] = "0" * 64
                    rows_path.write_text(
                        "".join(phase7.canonical_json(row) + "\n" for row in rows),
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2LineageMismatch"):
                        evidence._verify_feature_chain(fixture.root, selected, members)
                    rows_path.write_bytes(original)

    def test_verify_real_backtest_upstream_mutation_matrix(self) -> None:
        processed = phase7.REPOSITORY_ROOT / "data" / "processed"
        processed.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=processed) as temporary:
            fixture = build_strict_v2_pipeline(Path(temporary) / "package")
            members = self._strict_primary_members(fixture)
            selected = ["SYNTH-A", "SYNTH-B", "SYNTH-C"]
            config_path = fixture.backtest_config_path
            result_path = fixture.backtest_roots[0] / "manifest.json"
            cases = (
                (config_path, lambda value: value["inputs"]["normalization"].__setitem__("manifest_sha256", "0" * 64)),
                (config_path, lambda value: value["inputs"]["normalization"].__setitem__("manifest_path", "data/processed/stale/normalization/manifest.json")),
                (config_path, lambda value: value["inputs"]["normalization"].__setitem__("records_sha256", "0" * 64)),
                (config_path, lambda value: value["inputs"]["features"].__setitem__("manifest_sha256", "0" * 64)),
                (config_path, lambda value: value["inputs"]["features"].__setitem__("rows_sha256", "0" * 64)),
                (config_path, lambda value: value["inputs"]["features"].__setitem__("feature_definition_sha256", "0" * 64)),
                (config_path, lambda value: value["products"][0]["product_identity"].__setitem__("input_product_entry_sha256", "0" * 64)),
                (config_path, lambda value: value["products"][0]["reviewed_lineage"].__setitem__("source_manifest_sha256", "0" * 64)),
                (result_path, lambda value: value.__setitem__("config_sha256", "0" * 64)),
                (result_path, lambda value: value.__setitem__("run_id", "wrong-run")),
                (result_path, lambda value: value["execution"].__setitem__("model", "trade_touch_v1")),
                (result_path, lambda value: value.__setitem__("feature_definition_sha256", "0" * 64)),
                (result_path, lambda value: value["inputs"]["features"].__setitem__("rows_sha256", "0" * 64)),
                (result_path, lambda value: value["products"][0]["product_identity"].__setitem__("ticker", "WRONG")),
                (result_path, lambda value: value["products"][0]["reviewed_lineage"].__setitem__("review_sha256", "0" * 64)),
            )
            for index, (path, mutation) in enumerate(cases):
                with self.subTest(case=index):
                    original = path.read_bytes()
                    value = phase7.read_json(path)
                    mutation(value)
                    phase7.write_json(path, value)
                    with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2LineageMismatch"):
                        evidence._verify_backtest_upstream_chain(fixture.root, selected, members)
                    path.write_bytes(original)

    def test_verify_lineage_rejects_missing_and_extra_edges(self) -> None:
        fixture = build_v2_package(
            self.root,
            materialized_stage="normalization_record_only",
            eligible_stage="normalization_record_only",
        )
        expected = evidence._derive_role_lineage(
            fixture.manifest["payload"]["members"], "normalization_record_only"
        )
        fixture.manifest["payload"]["lineage_edges"] = expected[:-1]
        fixture.rewrite_manifest()
        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2LineageMismatch"):
            evidence.verify_evidence_manifest_v2(fixture.manifest_path)
        fixture.manifest["payload"]["lineage_edges"] = [*expected, {"from_role": "raw_frames", "to_role": "capture_policy"}]
        fixture.rewrite_manifest()
        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2LineageMismatch"):
            evidence.verify_evidence_manifest_v2(fixture.manifest_path)

    def test_verify_repetition_rebuilds_and_byte_compares_both_roots(self) -> None:
        canonical = self.root / "normalization"
        first, second = self.root / "first", self.root / "second"
        canonical.mkdir()
        first.mkdir()
        second.mkdir()
        (canonical / "records.jsonl").write_bytes(b"same\n")
        (first / "records.jsonl").write_bytes(b"same\n")
        (second / "records.jsonl").write_bytes(b"same\n")
        first_inventory = evidence.build_repetition_inventory(first)
        second_inventory = evidence.build_repetition_inventory(second)
        first_path = self.write_json("control/first-inventory.json", first_inventory)
        second_path = self.write_json("control/second-inventory.json", second_inventory)
        members = [
            {"role": "normalization_inventory_first", "path": first_path.relative_to(self.root).as_posix()},
            {"role": "normalization_inventory_second", "path": second_path.relative_to(self.root).as_posix()},
            {"role": "repetition_member", "path": "first/records.jsonl"},
            {"role": "repetition_member", "path": "second/records.jsonl"},
        ]
        repetitions = [{
            "stage": "normalization_v3", "first_root": "first", "second_root": "second",
            "first_inventory_role": "normalization_inventory_first",
            "second_inventory_role": "normalization_inventory_second",
        }]
        evidence._verify_repetitions(self.root, repetitions, members)

    def test_verify_repetition_rejects_canonical_output_divergence(self) -> None:
        canonical = self.root / "normalization"
        first, second = self.root / "first", self.root / "second"
        for path in (canonical, first, second):
            path.mkdir()
        (canonical / "records.jsonl").write_bytes(b"canonical differs\n")
        (first / "records.jsonl").write_bytes(b"repeat\n")
        (second / "records.jsonl").write_bytes(b"repeat\n")
        first_path = self.write_json(
            "control/first-inventory.json", evidence.build_repetition_inventory(first)
        )
        second_path = self.write_json(
            "control/second-inventory.json", evidence.build_repetition_inventory(second)
        )
        members = [
            {"role": "normalization_inventory_first", "path": first_path.relative_to(self.root).as_posix()},
            {"role": "normalization_inventory_second", "path": second_path.relative_to(self.root).as_posix()},
            {"role": "repetition_member", "path": "first/records.jsonl"},
            {"role": "repetition_member", "path": "second/records.jsonl"},
        ]
        repetitions = [{
            "stage": "normalization_v3", "first_root": "first", "second_root": "second",
            "first_inventory_role": "normalization_inventory_first",
            "second_inventory_role": "normalization_inventory_second",
        }]

        with self.assertRaisesRegex(
            evidence.EvidenceError, "EvidenceV2RepetitionMismatch"
        ):
            evidence._verify_repetitions(self.root, repetitions, members)

    def test_verify_repetition_rejects_inventory_and_byte_mutations(self) -> None:
        for defect in ("stale_inventory", "byte_mismatch", "extra_path", "undeclared_member"):
            with self.subTest(defect=defect):
                shutil.rmtree(self.root)
                self.root.mkdir()
                first, second = self.root / "first", self.root / "second"
                canonical = self.root / "normalization"
                canonical.mkdir()
                first.mkdir()
                second.mkdir()
                (canonical / "records.jsonl").write_bytes(b"same\n")
                (first / "records.jsonl").write_bytes(b"same\n")
                (second / "records.jsonl").write_bytes(b"same\n")
                first_inventory = evidence.build_repetition_inventory(first)
                second_inventory = evidence.build_repetition_inventory(second)
                first_path = self.write_json("control/first-inventory.json", first_inventory)
                second_path = self.write_json("control/second-inventory.json", second_inventory)
                if defect == "stale_inventory":
                    stale = phase7.read_json(first_path)
                    stale["payload_sha256"] = "0" * 64
                    phase7.write_json(first_path, stale)
                elif defect == "byte_mismatch":
                    (second / "records.jsonl").write_bytes(b"diff\n")
                    phase7.write_json(second_path, evidence.build_repetition_inventory(second))
                else:
                    (second / "extra.json").write_bytes(b"{}\n")
                    phase7.write_json(second_path, evidence.build_repetition_inventory(second))
                members = [
                    {"role": "normalization_inventory_first", "path": first_path.relative_to(self.root).as_posix()},
                    {"role": "normalization_inventory_second", "path": second_path.relative_to(self.root).as_posix()},
                    {"role": "repetition_member", "path": "first/records.jsonl"},
                    {"role": "repetition_member", "path": "second/records.jsonl"},
                ]
                if defect == "undeclared_member":
                    members.pop()
                repetitions = [{
                    "stage": "normalization_v3", "first_root": "first", "second_root": "second",
                    "first_inventory_role": "normalization_inventory_first",
                    "second_inventory_role": "normalization_inventory_second",
                }]
                with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2RepetitionMismatch"):
                    evidence._verify_repetitions(self.root, repetitions, members)

    def test_verify_result_v4_rejects_product_trace_and_descriptor_disagreement(self) -> None:
        digest = "1" * 64
        config = {
            "products": [
                {"product_identity": {"ticker": "SYNTH-A"}, "contract_identity": {"contract_id": 1}},
                {"product_identity": {"ticker": "SYNTH-B"}, "contract_identity": {"contract_id": 2}},
            ]
        }
        artifacts = [
            {"name": name, "schema": schema, "path": f"{name}.jsonl", "sha256": digest, "row_count": 0}
            for name, schema in sorted(evidence.V4_ARTIFACT_SCHEMAS.items())
        ]
        traces = [
            {"ticker": f"SYNTH-{letter}", "contract_id": contract_id, "path": f"risk-{contract_id}.jsonl", "sha256": digest, "row_count": 0}
            for contract_id, letter in ((1, "A"), (2, "B"))
        ]
        result = {
            "artifacts": artifacts,
            "risk": {"traces": traces},
            "products": [
                {"product_identity": {"ticker": item["ticker"]}, "contract_identity": {"contract_id": item["contract_id"]}, "risk_trace": dict(item)}
                for item in traces
            ],
        }
        members = [
            {"role": f"v4_{item['name']}", "path": f"result/{item['path']}", "sha256": digest, "record_count": 0}
            for item in artifacts
        ] + [
            {"role": f"risk_trace_{item['contract_id']}", "path": f"result/{item['path']}", "sha256": digest, "record_count": 0, "contract_id": item["contract_id"]}
            for item in traces
        ]
        evidence._verify_backtest_descriptors(config, result, members, "result/manifest.json")
        result["products"][0]["risk_trace"]["contract_id"] = 2
        with self.assertRaisesRegex(evidence.EvidenceError, "EvidenceV2LineageMismatch"):
            evidence._verify_backtest_descriptors(config, result, members, "result/manifest.json")


if __name__ == "__main__":
    unittest.main()
