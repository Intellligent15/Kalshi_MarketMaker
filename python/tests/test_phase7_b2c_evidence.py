from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

import pmm_phase7 as phase7
import pmm_phase7_evidence as evidence


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


if __name__ == "__main__":
    unittest.main()
