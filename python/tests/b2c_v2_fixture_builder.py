"""Synthetic, offline fixtures for the B2c V2 evidence verifier."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
from pathlib import Path
import shutil
from typing import Any

import pmm_phase7 as phase7
import pmm_phase7_evidence as evidence
import pmm_product_terms as product_terms


@dataclass
class V2PackageFixture:
    root: Path
    manifest_path: Path
    manifest: dict[str, Any]

    def rewrite_manifest(self) -> None:
        self.manifest["payload_sha256"] = evidence._payload_sha256(self.manifest["payload"])
        phase7.write_json(self.manifest_path, self.manifest)

    def refresh_credential_report(self) -> None:
        members = self.manifest["payload"]["members"]
        report_member = next(item for item in members if item["role"] == "credential_scan_report")
        entries = [
            {"path": item["path"], "byte_length": item["byte_length"], "sha256": item["sha256"]}
            for item in members
            if item["role"] != "credential_scan_report"
        ]
        entries.sort(key=lambda item: item["path"].encode("utf-8"))
        report_path = self.root / report_member["path"]
        report = phase7.read_json(report_path)
        report["payload_inventory_sha256"] = evidence._payload_sha256(entries)
        report["member_count"] = len(entries)
        report["byte_count"] = sum(item["byte_length"] for item in entries)
        phase7.write_json(report_path, report)
        report_member["byte_length"] = report_path.stat().st_size
        report_member["sha256"] = phase7.sha256_file(report_path)
        self.rewrite_manifest()


def _write_json(root: Path, relative: str, value: dict[str, Any]) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    phase7.write_json(path, value)
    return path


def _write_jsonl(root: Path, relative: str, rows: list[dict[str, Any]]) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(phase7.canonical_json(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def build_v2_package(
    root: Path,
    *,
    materialized_stage: str = "raw",
    eligible_stage: str = "normalization_record_only",
    capture_exit: int = 0,
    product_status: str = "unavailable",
    product_package: Path | None = None,
    conversion_policy: Path | None = None,
) -> V2PackageFixture:
    """Build a bounded package without venue or credential access."""
    if materialized_stage not in evidence._STAGE_ORDER:
        raise ValueError("unsupported materialized stage")
    loaded_product = None
    if product_package is not None:
        if conversion_policy is None:
            raise ValueError("a product package requires its conversion policy")
        loaded_product = product_terms.ProductPackage.load(product_package)
        product_terms.ConversionPolicy.load(conversion_policy)
        tickers = [loaded_product.terms.market_ticker, "SYNTH-B", "SYNTH-C"]
        capture_start = loaded_product.review.payload["effective_from_utc"]
        capture_end = (
            datetime.fromisoformat(capture_start.replace("Z", "+00:00")) + timedelta(seconds=43200)
        ).isoformat().replace("+00:00", "Z")
    else:
        tickers = ["SYNTH-A", "SYNTH-B", "SYNTH-C"]
        capture_start = "2026-07-18T00:00:00Z"
        capture_end = "2026-07-18T12:00:00Z"
    digest = hashlib.sha256(b"synthetic-fixture").hexdigest()
    files: dict[str, tuple[Path, str | None, str]] = {}
    repeatable_members: list[dict[str, Any]] = []
    files["capture_policy"] = (
        _write_json(
            root,
            "control/capture-policy.json",
            {
                "schema": "pmm.phase7.b2c_evidence_policy.v2",
                "base_policy_sha256": phase7.sha256_file(
                    phase7.REPOSITORY_ROOT / "configs/phase7/b2c_evidence_policy_v1.json"
                ),
                "measurement": {
                    "sample_interval_seconds": 1,
                    "sigint_grace_seconds": 5,
                    "sigterm_grace_seconds": 5,
                    "quiescence_grace_seconds": 5,
                    "stream_limit_bytes": 67108864,
                    "publication_reserve_bytes": 1048576,
                },
            },
        ),
        "b2c-evidence-policy-v2.schema.json",
        "json",
    )
    files["raw_frames"] = (
        _write_jsonl(
            root,
            "raw/frames.jsonl",
            [
                {
                    "schema": "pmm.kalshi.raw_capture_record.v2",
                    "kind": "connection_closed",
                    "raw_ingress_ordinal": 1,
                    "received_at_utc_ns": 1,
                    "connection_segment_id": 1,
                    "close_reason": "synthetic fixture",
                    "clean": True,
                }
            ],
        ),
        "raw-capture-record-v2.schema.json",
        "jsonl",
    )
    files["raw_metadata"] = (
        _write_json(
            root,
            "raw/metadata.json",
            {
                "schema": "pmm.kalshi.raw_capture.v2",
                "source": "kalshi",
                "environment": "production",
                "truth_category": "Synthetic",
                "source_fidelity": "level_2",
                "market_tickers": tickers,
                "capture_started_at_utc_ns": 1,
                "capture_ended_at_utc_ns": 43_200_000_000_001,
                "requested_duration_seconds": 43200,
                "connection_strategy": "single_connection_v1",
                "websocket_endpoint": "wss://synthetic.invalid",
                "subscription_template": {},
                "sequence_domain": {
                    "status": "fixture_declared",
                    "topology": "independent",
                    "components": [],
                    "mechanical_validation_key": [
                        "connection_segment_id",
                        "venue_subscription_id",
                        "market_ticker",
                    ],
                    "limitation": "synthetic fixture only",
                },
                "credential_environment_variables": [],
                "credential_values_persisted": False,
                "message_counts_by_type": {},
                "message_counts_by_market": {},
                "connections": 1,
                "disconnects": 0,
                "connection_segments": [],
                "sequence_gaps": [],
                "non_monotonic_sequences": [],
                "raw_record_count": 1,
                "capture_continuity": "continuous_within_recorded_mechanical_scopes",
                "data_usability": "strict_eligible",
                "shutdown": {"status": "completed", "clean": True},
            },
        ),
        "raw-capture-v2.schema.json",
        "json",
    )
    measurement = {
        "schema": "pmm.phase7.b2c_measurement.v2",
        "stage": "capture-v2",
        "command_sha256": digest,
        "started_at_utc": "2026-07-18T00:00:00Z",
        "finished_at_utc": "2026-07-18T00:00:01Z",
        "wall_time_seconds": 1,
        "child": {"exit_code": capture_exit},
        "termination": {
            "reason": "completed" if capture_exit == 0 else "child_failure",
            "stop_initiator": "child",
            "signals": [],
            "grace_expiries": [],
            "escalation_cause": None,
        },
        "teardown": {
            "direct_child_reaped": True,
            "process_group_quiescent": True,
            "zombie_members_observed": 0,
            "group_absence_confirmed": True,
            "output_finalization": "cooperative",
        },
        "sampling": {
            "valid": True,
            "sampler_identity": "synthetic-v1",
            "attempted_samples": 1,
            "successful_samples": 1,
            "error_code": None,
            "peak_process_count": 1,
            "peak_rss_kib": 1,
        },
        "streams": {
            "stdout": {"bytes_seen": 0, "sha256": hashlib.sha256(b"").hexdigest(), "over_budget": False},
            "stderr": {"bytes_seen": 0, "sha256": hashlib.sha256(b"").hexdigest(), "over_budget": False},
        },
        "storage": {
            "initial_raw_bytes": 0,
            "final_raw_bytes": 1,
            "initial_aggregate_bytes": 0,
            "final_aggregate_bytes": 1,
            "minimum_free_bytes": 1,
            "raw_budget_bytes": 1,
            "aggregate_budget_bytes": 2,
            "publication_reserve_bytes": 1,
        },
        "machine": {"system": "synthetic"},
        "identity_files": [
            {"path": str(path.resolve()), "sha256": phase7.sha256_file(path)}
            for path, _, _ in files.values()
        ],
    }
    files["capture_measurement"] = (
        _write_json(root, "measurements/capture.json", measurement),
        "b2c-measurement-v2.schema.json",
        "json",
    )

    stage_ceiling = evidence._STAGE_ORDER.index(materialized_stage)
    for role, spec in evidence.V2_ROLE_REGISTRY.items():
        if (
            role in files
            or role == "credential_scan_report"
            or evidence._STAGE_ORDER.index(spec.introduced_at) > stage_ceiling
        ):
            continue
        suffix = "jsonl" if spec.kind == "jsonl" else "json"
        path = root / "synthetic-stage" / f"{role}.{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        if spec.kind == "jsonl":
            path.write_bytes(b"")
        else:
            phase7.write_json(path, {"schema": spec.schema_tag})
        files[role] = (path, spec.schema_file, spec.kind)
    if materialized_stage == "backtest_v4":
        for contract_id in range(1, len(tickers) + 1):
            role = f"risk_trace_{contract_id}"
            spec = evidence._role_spec(role)
            assert spec is not None
            path = root / "synthetic-stage" / f"{role}.jsonl"
            path.write_bytes(b"")
            files[role] = (path, spec.schema_file, spec.kind)

    product_packages: list[dict[str, Any]] = []
    if loaded_product is not None and product_package is not None and conversion_policy is not None:
        mounted_package = root / "product-packages" / loaded_product.terms.market_ticker
        shutil.copytree(product_package, mounted_package)
        mounted_policy = root / "product-packages" / "conversion-policy.json"
        shutil.copy2(conversion_policy, mounted_policy)
        for path in sorted(mounted_package.rglob("*")):
            if path.is_file():
                repeatable_members.append(
                    {
                        "role": "product_package_member",
                        "path": path.relative_to(root).as_posix(),
                        "schema_file": None,
                        "kind": "opaque",
                        "byte_length": path.stat().st_size,
                        "sha256": phase7.sha256_file(path),
                    }
                )
        repeatable_members.append(
            {
                "role": "product_package_member",
                "path": mounted_policy.relative_to(root).as_posix(),
                "schema_file": None,
                "kind": "opaque",
                "byte_length": mounted_policy.stat().st_size,
                "sha256": phase7.sha256_file(mounted_policy),
            }
        )
        product_packages.append(
            {
                "ticker": loaded_product.terms.market_ticker,
                "package_root": mounted_package.relative_to(root).as_posix(),
                "conversion_policy_path": mounted_policy.relative_to(root).as_posix(),
            }
        )

    payload_entries = [
        {
            "path": path.relative_to(root).as_posix(),
            "byte_length": path.stat().st_size,
            "sha256": phase7.sha256_file(path),
        }
        for path, _, _ in files.values()
    ] + [
        {"path": item["path"], "byte_length": item["byte_length"], "sha256": item["sha256"]}
        for item in repeatable_members
    ]
    payload_inventory_sha256 = evidence._payload_sha256(
        sorted(payload_entries, key=lambda item: item["path"].encode("utf-8"))
    )
    files["credential_scan_report"] = (
        _write_json(
            root,
            "control/credential-scan-report.json",
            {
                "schema": "pmm.phase7.b2c_credential_scan.v1",
                "scanner_identity": "pmm-b2c-deterministic-scanner-v1",
                "ruleset_sha256": hashlib.sha256(b"pmm-b2c-ruleset-v1").hexdigest(),
                "payload_inventory_sha256": payload_inventory_sha256,
                "member_count": len(payload_entries),
                "byte_count": sum(item["byte_length"] for item in payload_entries),
                "status": "clean",
            },
        ),
        "b2c-credential-scan-v1.schema.json",
        "json",
    )
    members = []
    for role, (path, schema_file, kind) in files.items():
        members.append(
            {
                "role": role,
                "path": path.relative_to(root).as_posix(),
                "schema_file": schema_file,
                "kind": kind,
                "byte_length": path.stat().st_size,
                "sha256": phase7.sha256_file(path),
            }
        )
        if kind == "jsonl":
            members[-1]["record_count"] = sum(1 for _ in phase7.iter_jsonl(path))
        if role.startswith("risk_trace_"):
            members[-1]["contract_id"] = int(role.rsplit("_", 1)[1])
    members.extend(repeatable_members)
    if capture_exit == 1:
        shutdown_status, continuity, usability = "failed", "incomplete", "unusable"
    elif capture_exit == 130:
        shutdown_status, continuity, usability = "interrupted", "incomplete", "unusable"
    elif capture_exit == 2:
        shutdown_status, continuity, usability = "completed", "observed_discontinuous", "record_only"
    else:
        shutdown_status, continuity, usability = (
            "completed",
            "continuous_within_recorded_mechanical_scopes",
            "strict_eligible",
        )
    repetitions = []
    repetition_specs = (
        ("normalization_v3", "normalization"),
        ("features_v3", "feature"),
        ("backtest_v4", "backtest"),
    )
    for repetition_stage, prefix in repetition_specs:
        required_at = {
            "normalization_v3": "normalization_record_only",
            "features_v3": "features_v3",
            "backtest_v4": "backtest_v4",
        }[repetition_stage]
        if evidence._STAGE_ORDER.index(materialized_stage) >= evidence._STAGE_ORDER.index(required_at):
            repetitions.append(
                {
                    "stage": repetition_stage,
                    "first_root": f"repetitions/{prefix}/first",
                    "second_root": f"repetitions/{prefix}/second",
                    "first_inventory_role": f"{prefix}_inventory_first",
                    "second_inventory_role": f"{prefix}_inventory_second",
                }
            )
    payload = {
        "evidence_id": "synthetic-b2c-v2",
        "capture_spec": {
            "policy_sha256": phase7.sha256_file(files["capture_policy"][0]),
            "started_at_utc": capture_start,
            "ended_at_utc": capture_end,
            "duration_seconds": 43200,
            "market_count": 3,
            "minimum_free_bytes": 10737418240,
            "raw_budget_bytes": 1073741824,
            "total_budget_bytes": 5368709120,
            "selection": {
                "environment": "production",
                "contract_kind": "binary",
                "distinct_series_required": True,
                "activity_order": "descending",
                "tie_breaker": "market_ticker_ascending",
                "fallback_selection_allowed": False,
                "substitution_after_opening_allowed": False,
            },
        },
        "capture_outcome": {
            "exit_code": capture_exit,
            "shutdown_status": shutdown_status,
            "capture_continuity": continuity,
            "data_usability": usability,
        },
        "market_tickers": tickers,
        "retention": {"large_bytes_in_git": False},
        "product_lineage": [
            {
                "ticker": ticker,
                "status": product_status if loaded_product is not None and ticker == loaded_product.terms.market_ticker else "unavailable",
            }
            for ticker in tickers
        ],
        "product_packages": product_packages,
        "furthest_materialized_stage": materialized_stage,
        "furthest_eligible_stage": eligible_stage,
        "members": members,
        "lineage_edges": evidence._derive_role_lineage(members, materialized_stage),
        "repetitions": repetitions,
        "credential_scan": {"status": "clean"},
    }
    manifest = {
        "schema": evidence.EVIDENCE_V2_SCHEMA,
        "payload": payload,
        "payload_sha256": evidence._payload_sha256(payload),
    }
    manifest_path = _write_json(root, "evidence-manifest.json", manifest)
    return V2PackageFixture(root, manifest_path, manifest)
