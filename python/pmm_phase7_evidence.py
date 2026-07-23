#!/usr/bin/env python3
"""Offline B2c evidence verification and process-tree measurement.

This module is additive. It does not capture venue data and does not alter accepted
Capture V2, normalization V3, feature V3, Backtest V4, or Result V4 formats.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from types import MappingProxyType
from typing import Any, Iterable, Literal, Mapping
import re

try:
    from . import pmm_phase7 as phase7
    from . import pmm_phase7_measurement as measurement_v2
    from . import pmm_product_terms as product_terms
    from . import pmm_b2c_operator as b2c_operator
except ImportError:
    python_root = str(Path(__file__).resolve().parent)
    if python_root not in sys.path:
        sys.path.insert(0, python_root)
    import pmm_phase7 as phase7  # type: ignore[no-redef]
    import pmm_phase7_measurement as measurement_v2  # type: ignore[no-redef]
    import pmm_product_terms as product_terms  # type: ignore[no-redef]
    import pmm_b2c_operator as b2c_operator  # type: ignore[no-redef]


EVIDENCE_SCHEMA = "pmm.phase7.b2c_evidence_manifest.v1"
MEASUREMENT_SCHEMA = "pmm.phase7.b2c_measurement.v1"
EVIDENCE_V2_SCHEMA = "pmm.phase7.b2c_evidence_manifest.v2"
REPETITION_INVENTORY_SCHEMA = "pmm.phase7.b2c_repetition_inventory.v1"
CREDENTIAL_SCAN_SCHEMA = "pmm.phase7.b2c_credential_scan.v1"
V4_ARTIFACT_SCHEMAS = {
    "acknowledgements": "pmm.backtest_acknowledgement.v1",
    "cancellations": "pmm.backtest_cancellation.v1",
    "decisions": "pmm.backtest_decision.v1",
    "exposure": "pmm.backtest_exposure.v1",
    "fills": "pmm.backtest_fill.v1",
    "rejections": "pmm.backtest_rejection.v1",
    "risk-events": "pmm.backtest_risk_event.v1",
    "submitted-orders": "pmm.backtest_submitted_order.v1",
    "summary": "pmm.backtest_summary.v1",
}
V4_ARTIFACT_ROLES = {f"v4_{name}" for name in V4_ARTIFACT_SCHEMAS}
BASE_ROLES = {"capture_policy", "raw_frames", "raw_metadata", "capture_measurement"}
STRICT_CHAIN_ROLES = {
    "normalization_manifest", "normalized_records", "source_scopes", "product_map",
    "feature_manifest", "feature_rows", "backtest_config", "result_manifest",
    "normalization_measurement", "feature_measurement", "backtest_measurement",
    "normalization_telemetry", "risk_telemetry",
    *V4_ARTIFACT_ROLES,
}


class EvidenceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class RoleSpec:
    schema_file: str
    schema_tag: str
    kind: Literal["json", "jsonl"]
    introduced_at: str
    cardinality: Literal["one", "per_contract", "per_ticker", "pair_per_stage"]


def _role(
    schema_file: str,
    schema_tag: str,
    kind: Literal["json", "jsonl"],
    introduced_at: str,
    cardinality: Literal["one", "per_contract", "per_ticker", "pair_per_stage"] = "one",
) -> RoleSpec:
    return RoleSpec(schema_file, schema_tag, kind, introduced_at, cardinality)


# Formal schemas own document shape; this immutable table owns mounted dispatch.
_ROLE_SPECS = {
    "capture_policy": _role("b2c-evidence-policy-v2.schema.json", "pmm.phase7.b2c_evidence_policy.v2", "json", "raw"),
    "capture_measurement": _role("b2c-measurement-v2.schema.json", "pmm.phase7.b2c_measurement.v2", "json", "raw"),
    "credential_scan_report": _role("b2c-credential-scan-v1.schema.json", CREDENTIAL_SCAN_SCHEMA, "json", "raw"),
    "raw_frames": _role("raw-capture-record-v2.schema.json", "pmm.kalshi.raw_capture_record.v2", "jsonl", "raw"),
    "raw_metadata": _role("raw-capture-v2.schema.json", "pmm.kalshi.raw_capture.v2", "json", "raw"),
    "candidate_snapshot": _role("b2c-candidate-snapshot-v1.schema.json", b2c_operator.CANDIDATE_SNAPSHOT_SCHEMA, "json", "raw"),
    "run_approval": _role("b2c-run-approval-v1.schema.json", b2c_operator.RUN_APPROVAL_SCHEMA, "json", "raw"),
    "normalized_records": _role("normalized-record-v2.schema.json", "pmm.historical.normalized_record.v2", "jsonl", "normalization_record_only"),
    "normalization_manifest": _role("normalization-manifest-v3.schema.json", "pmm.historical.normalization_manifest.v3", "json", "normalization_record_only"),
    "source_scopes": _role("source-scope-map-v1.schema.json", "pmm.historical.source_scope_map.v1", "json", "normalization_record_only"),
    "product_map": _role("product-map-v3.schema.json", "pmm.historical.product_map.v3", "json", "normalization_record_only"),
    "normalization_measurement": _role("b2c-measurement-v2.schema.json", "pmm.phase7.b2c_measurement.v2", "json", "normalization_record_only"),
    "normalization_telemetry": _role("b2c-normalization-telemetry-v1.schema.json", "pmm.phase7.b2c_normalization_telemetry.v1", "json", "normalization_record_only"),
    "normalization_inventory_first": _role("b2c-repetition-inventory-v1.schema.json", REPETITION_INVENTORY_SCHEMA, "json", "normalization_record_only", "pair_per_stage"),
    "normalization_inventory_second": _role("b2c-repetition-inventory-v1.schema.json", REPETITION_INVENTORY_SCHEMA, "json", "normalization_record_only", "pair_per_stage"),
    "feature_rows": _role("feature-row-v2.schema.json", "pmm.historical.feature_row.v2", "jsonl", "features_v3"),
    "feature_manifest": _role("feature-manifest-v3.schema.json", "pmm.historical.feature_manifest.v3", "json", "features_v3"),
    "feature_measurement": _role("b2c-measurement-v2.schema.json", "pmm.phase7.b2c_measurement.v2", "json", "features_v3"),
    "feature_inventory_first": _role("b2c-repetition-inventory-v1.schema.json", REPETITION_INVENTORY_SCHEMA, "json", "features_v3", "pair_per_stage"),
    "feature_inventory_second": _role("b2c-repetition-inventory-v1.schema.json", REPETITION_INVENTORY_SCHEMA, "json", "features_v3", "pair_per_stage"),
    "backtest_config": _role("backtest-v4.schema.json", "pmm.backtest.v4", "json", "backtest_v4"),
    "result_manifest": _role("backtest-result-manifest-v4.schema.json", "pmm.backtest_result_manifest.v4", "json", "backtest_v4"),
    "backtest_measurement": _role("b2c-measurement-v2.schema.json", "pmm.phase7.b2c_measurement.v2", "json", "backtest_v4"),
    "risk_telemetry": _role("b2c-risk-telemetry-v1.schema.json", "pmm.phase7.b2c_risk_telemetry.v1", "json", "backtest_v4"),
    "backtest_inventory_first": _role("b2c-repetition-inventory-v1.schema.json", REPETITION_INVENTORY_SCHEMA, "json", "backtest_v4", "pair_per_stage"),
    "backtest_inventory_second": _role("b2c-repetition-inventory-v1.schema.json", REPETITION_INVENTORY_SCHEMA, "json", "backtest_v4", "pair_per_stage"),
}
for _artifact_name, _artifact_schema in V4_ARTIFACT_SCHEMAS.items():
    _ROLE_SPECS[f"v4_{_artifact_name}"] = _role(
        "backtest-artifact-v1.schema.json", _artifact_schema, "jsonl", "backtest_v4"
    )
V2_ROLE_REGISTRY: Mapping[str, RoleSpec] = MappingProxyType(_ROLE_SPECS)

_STAGE_ORDER = ("raw", "normalization_record_only", "normalization_v3", "features_v3", "backtest_v4")
_ALWAYS_V2_ROLES = frozenset(
    {"capture_policy", "raw_frames", "raw_metadata", "capture_measurement", "credential_scan_report"}
)
_OPTIONAL_CONTROL_ROLES = frozenset({"candidate_snapshot", "run_approval"})


def _role_spec(role: str) -> RoleSpec | None:
    spec = V2_ROLE_REGISTRY.get(role)
    if spec is not None:
        return spec
    if re.fullmatch(r"risk_trace_[1-9][0-9]*", role):
        return _role(
            "risk-conformance-trace-v2.schema.json",
            phase7.RISK_TRACE_SCHEMA,
            "jsonl",
            "backtest_v4",
            "per_contract",
        )
    return None


def _required_roles_for_stage(stage: str) -> set[str]:
    if stage not in _STAGE_ORDER:
        raise EvidenceError("EvidenceV2RoleForbidden", "unknown materialized stage")
    ceiling = _STAGE_ORDER.index(stage)
    roles = set(_ALWAYS_V2_ROLES)
    roles.update(
        role
        for role, spec in V2_ROLE_REGISTRY.items()
        if role not in _OPTIONAL_CONTROL_ROLES
        and _STAGE_ORDER.index(spec.introduced_at) <= ceiling
    )
    return roles


def _derive_role_lineage(members: list[dict[str, Any]], stage: str) -> list[dict[str, str]]:
    roles = {member["role"] for member in members}
    edges: set[tuple[str, str]] = set()

    def connect(sources: Iterable[str], targets: Iterable[str]) -> None:
        edges.update(
            (source, target)
            for source in sources
            for target in targets
            if source in roles and target in roles
        )

    if _STAGE_ORDER.index(stage) >= _STAGE_ORDER.index("normalization_record_only"):
        connect(("raw_frames", "raw_metadata"), ("normalization_manifest",))
        connect(
            ("normalization_manifest",),
            ("normalized_records", "source_scopes", "product_map", "normalization_measurement", "normalization_telemetry"),
        )
    if _STAGE_ORDER.index(stage) >= _STAGE_ORDER.index("features_v3"):
        connect(
            ("normalization_manifest", "normalized_records", "source_scopes", "product_map"),
            ("feature_manifest",),
        )
        connect(("feature_manifest",), ("feature_rows", "feature_measurement"))
    if stage == "backtest_v4":
        connect(
            ("normalization_manifest", "product_map", "feature_manifest", "feature_rows"),
            ("backtest_config",),
        )
        connect(("backtest_config", "feature_manifest", "feature_rows"), ("result_manifest",))
        connect(
            ("result_manifest",),
            tuple(sorted(role for role in roles if role in V4_ARTIFACT_ROLES or role.startswith("risk_trace_"))),
        )
        connect(("backtest_config",), ("backtest_measurement", "risk_telemetry"))
    connect(("operational_control_member",), ("candidate_snapshot", "run_approval"))
    connect(("candidate_snapshot",), ("run_approval",))
    connect(("run_approval",), ("capture_policy",))
    return [
        {"from_role": source, "to_role": target}
        for source, target in sorted(edges)
    ]


def _verify_repetitions(
    root: Path,
    repetitions: list[dict[str, Any]],
    members: list[dict[str, Any]],
) -> None:
    member_by_role = {member["role"]: member for member in members}
    expected_repetition_paths: set[str] = set()
    canonical_roots = {
        "normalization_v3": "normalization",
        "features_v3": "features",
        "backtest_v4": "backtest/result",
    }
    canonical_required_paths = {
        "normalization_v3": {
            "records.jsonl", "source_scopes.json", "product.json", "manifest.json",
        },
        "features_v3": {"features.jsonl", "manifest.json"},
    }
    for repetition in repetitions:
        try:
            first_root = _safe_member(root, repetition["first_root"])
            second_root = _safe_member(root, repetition["second_root"])
            first_member = member_by_role[repetition["first_inventory_role"]]
            second_member = member_by_role[repetition["second_inventory_role"]]
            first_path = _safe_member(root, first_member["path"])
            second_path = _safe_member(root, second_member["path"])
        except (KeyError, EvidenceError) as error:
            raise EvidenceError("EvidenceV2RepetitionMismatch", "repetition declaration is incomplete") from error
        if first_root == second_root or first_root in second_root.parents or second_root in first_root.parents:
            raise EvidenceError("EvidenceV2RepetitionMismatch", "repetition roots overlap")
        expected_repetition_paths.update(
            path.relative_to(root).as_posix()
            for repeated_root in (first_root, second_root)
            for path in repeated_root.rglob("*")
            if path.is_file()
        )
        rebuilt_first = build_repetition_inventory(first_root)
        rebuilt_second = build_repetition_inventory(second_root)
        retained_first = phase7.read_json(first_path)
        retained_second = phase7.read_json(second_path)
        try:
            phase7.validate_historical_schema(
                retained_first, "b2c-repetition-inventory-v1.schema.json", "EvidenceV2RepetitionMismatch"
            )
            phase7.validate_historical_schema(
                retained_second, "b2c-repetition-inventory-v1.schema.json", "EvidenceV2RepetitionMismatch"
            )
        except ValueError as error:
            raise EvidenceError("EvidenceV2RepetitionMismatch", "retained repetition inventory is invalid") from error
        if retained_first != rebuilt_first or retained_second != rebuilt_second:
            raise EvidenceError("EvidenceV2RepetitionMismatch", "retained inventory differs from mounted root")
        if retained_first["entries"] != retained_second["entries"]:
            raise EvidenceError("EvidenceV2RepetitionMismatch", "repetition inventories differ")
        canonical = build_repetition_inventory(
            _safe_member(root, canonical_roots[repetition["stage"]])
        )
        required_paths = canonical_required_paths.get(repetition["stage"])
        canonical_entries = {
            item["path"]: item
            for item in canonical["entries"]
            if required_paths is None or item["path"] in required_paths
        }
        repeated_entries = {
            item["path"]: item
            for item in retained_first["entries"]
            if required_paths is None or item["path"] in required_paths
        }
        if canonical_entries != repeated_entries:
            raise EvidenceError(
                "EvidenceV2RepetitionMismatch",
                "canonical output differs from retained repetitions",
            )
        for entry in retained_first["entries"]:
            if (first_root / entry["path"]).read_bytes() != (second_root / entry["path"]).read_bytes():
                raise EvidenceError("EvidenceV2RepetitionMismatch", "repetition member bytes differ")
    declared_repetition_paths = {
        member["path"] for member in members if member["role"] == "repetition_member"
    }
    if declared_repetition_paths != expected_repetition_paths:
        raise EvidenceError("EvidenceV2RepetitionMismatch", "repetition mounted member declarations differ")


def _verify_backtest_descriptors(
    config: dict[str, Any],
    result: dict[str, Any],
    members: list[dict[str, Any]],
    result_manifest_path: str,
) -> None:
    result_parent = PurePosixPath(result_manifest_path).parent

    def mounted_descriptor_path(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        relative = PurePosixPath(value)
        if relative.is_absolute() or ".." in relative.parts:
            return None
        return (result_parent / relative).as_posix()

    configured: dict[int, str] = {}
    for product in config.get("products", []):
        contract_id = product.get("contract_identity", {}).get("contract_id")
        ticker = product.get("product_identity", {}).get("ticker")
        if not isinstance(contract_id, int) or not isinstance(ticker, str) or contract_id in configured:
            raise EvidenceError("EvidenceV2LineageMismatch", "configured contract identity is invalid")
        configured[contract_id] = ticker
    traces = result.get("risk", {}).get("traces", [])
    trace_by_contract = {item.get("contract_id"): item for item in traces}
    if set(trace_by_contract) != set(configured) or len(trace_by_contract) != len(traces):
        raise EvidenceError("EvidenceV2LineageMismatch", "Result risk trace contracts differ from config")
    member_by_role = {member["role"]: member for member in members if member["role"] != "product_package_member"}
    for contract_id, ticker in configured.items():
        trace = trace_by_contract[contract_id]
        if trace.get("ticker") != ticker:
            raise EvidenceError("EvidenceV2LineageMismatch", "risk trace ticker differs from config")
        member = member_by_role.get(f"risk_trace_{contract_id}")
        expected = {
            "path": mounted_descriptor_path(trace.get("path")), "sha256": trace.get("sha256"),
            "record_count": trace.get("row_count"), "contract_id": contract_id,
        }
        if member is None or any(member.get(key) != value for key, value in expected.items()):
            raise EvidenceError("EvidenceV2LineageMismatch", "risk trace member differs from Result descriptor")
    product_traces: dict[int, dict[str, Any]] = {}
    for product in result.get("products", []):
        contract_id = product.get("contract_identity", {}).get("contract_id")
        ticker = product.get("product_identity", {}).get("ticker")
        if contract_id in product_traces or configured.get(contract_id) != ticker:
            raise EvidenceError("EvidenceV2LineageMismatch", "Result product identity differs from config")
        product_traces[contract_id] = product.get("risk_trace", {})
    if set(product_traces) != set(configured) or any(
        product_traces[contract_id] != trace_by_contract[contract_id] for contract_id in configured
    ):
        raise EvidenceError("EvidenceV2LineageMismatch", "Result product trace differs from Result risk descriptor")
    artifact_by_name = {item.get("name"): item for item in result.get("artifacts", [])}
    if set(artifact_by_name) != set(V4_ARTIFACT_SCHEMAS) or len(artifact_by_name) != len(result.get("artifacts", [])):
        raise EvidenceError("EvidenceV2LineageMismatch", "Result typed artifact set differs")
    for name, schema_tag in V4_ARTIFACT_SCHEMAS.items():
        descriptor = artifact_by_name[name]
        member = member_by_role.get(f"v4_{name}")
        expected = {
            "path": mounted_descriptor_path(descriptor.get("path")), "sha256": descriptor.get("sha256"),
            "record_count": descriptor.get("row_count"),
        }
        if descriptor.get("schema") != schema_tag or member is None or any(
            member.get(key) != value for key, value in expected.items()
        ):
            raise EvidenceError("EvidenceV2LineageMismatch", "typed artifact member differs from Result descriptor")


def _verify_backtest_rows_and_telemetry(
    root: Path,
    config: dict[str, Any],
    result: dict[str, Any],
    members: list[dict[str, Any]],
) -> None:
    member_by_role = {member["role"]: member for member in members}
    config_member = member_by_role["backtest_config"]
    configured = {
        item["contract_identity"]["contract_id"]: item["product_identity"]["ticker"]
        for item in config["products"]
    }
    trace_rows = {
        item["contract_id"]: item["row_count"] for item in result["risk"]["traces"]
    }
    telemetry_member = member_by_role.get("risk_telemetry")
    if telemetry_member is not None:
        telemetry = phase7.read_json(root / telemetry_member["path"])
        telemetry_products = {
            item.get("contract_id"): (item.get("ticker"), item.get("trace_rows"))
            for item in telemetry.get("products", [])
        }
        expected = {
            contract_id: (ticker, trace_rows[contract_id])
            for contract_id, ticker in configured.items()
        }
        if telemetry.get("config_sha256") != config_member["sha256"] or telemetry_products != expected:
            raise EvidenceError("EvidenceV2LineageMismatch", "risk telemetry differs from config or traces")
    descriptors = {item["name"]: item for item in result["artifacts"]}
    aggregates = result.get("aggregate_counts", {})
    for name, descriptor in descriptors.items():
        if aggregates.get(name, 0) != descriptor["row_count"]:
            raise EvidenceError("EvidenceV2LineageMismatch", "Result aggregate count differs from typed stream")
        member = member_by_role[f"v4_{name}"]
        for row in phase7.iter_jsonl(root / member["path"]):
            contract_id = row.get("contract_identity", {}).get("contract_id")
            ticker = row.get("product_identity", {}).get("ticker")
            if (
                row.get("run_id") != result.get("run_id")
                or row.get("configuration_sha256") != config_member["sha256"]
                or row.get("feature_definition_sha256") != result.get("feature_definition_sha256")
                or configured.get(contract_id) != ticker
            ):
                raise EvidenceError("EvidenceV2LineageMismatch", "typed row identity differs")


def build_repetition_inventory(root: Path) -> dict[str, Any]:
    """Rebuild a safe, canonical inventory from mounted bytes."""
    if root.is_symlink():
        raise EvidenceError("EvidencePathUnsafe", "inventory root is not a safe directory")
    root = root.resolve()
    entries: list[dict[str, Any]] = []
    if root.is_symlink() or not root.is_dir():
        raise EvidenceError("EvidencePathUnsafe", "inventory root is not a safe directory")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise EvidenceError("EvidencePathUnsafe", "inventory contains a symlink")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            entries.append({"path": relative, "byte_length": path.stat().st_size, "sha256": phase7.sha256_file(path)})
    entries.sort(key=lambda item: item["path"].encode("utf-8"))
    payload = {"root": ".", "entries": entries}
    return {"schema": REPETITION_INVENTORY_SCHEMA, "entries": entries, "payload_sha256": _payload_sha256(payload)}


_CREDENTIAL_PATTERNS: tuple[tuple[str, re.Pattern[bytes]], ...] = (
    ("pem_private_key", re.compile(br"-----BEGIN (?:RSA |DSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----")),
    ("authorization_header", re.compile(br"(?:authorization\s*:\s*(?:bearer|basic)\s+|bearer\s+)[^\r\n\s]+", re.I)),
    ("credential_assignment", re.compile(br"['\"]?(?:api[_-]?key|token|password|secret)['\"]?\s*[=:]\s*['\"]?[^\s'\"]+", re.I)),
)
CREDENTIAL_RULESET_SHA256 = hashlib.sha256(b"pmm-b2c-ruleset-v1").hexdigest()


def scan_credential_bytes(members: Iterable[tuple[str, bytes]]) -> list[dict[str, str]]:
    """Deterministic, low-false-positive offline scan; never returns a source path."""
    findings: list[dict[str, str]] = []
    for relative, raw in members:
        path_hash = _sha256_bytes(relative.encode("utf-8"))
        lower_name = relative.lower()
        if any(token in lower_name for token in (".pem", "private_key", "credential", "secret")):
            findings.append({"rule_id": "suspicious_filename", "path_sha256": path_hash})
        for rule_id, pattern in _CREDENTIAL_PATTERNS:
            if pattern.search(raw):
                findings.append({"rule_id": rule_id, "path_sha256": path_hash})
    unique = sorted({(item["rule_id"], item["path_sha256"]) for item in findings})
    return [
        {"rule_id": rule, "path_sha256": path_hash}
        for rule, path_hash in unique
    ]


def _v2_validate_member(path: Path, member: dict[str, Any], spec: RoleSpec | None) -> int | None:
    raw = path.read_bytes()
    if len(raw) != member["byte_length"] or _sha256_bytes(raw) != member["sha256"]:
        raise EvidenceError("EvidenceV2MembershipMismatch", "mounted V2 member bytes differ")
    if spec is None:
        return None
    try:
        if spec.kind == "json":
            value = phase7.read_json(path)
            phase7.validate_historical_schema(value, spec.schema_file, "EvidenceV2RoleSchemaMismatch")
            if value.get("schema") != spec.schema_tag:
                raise EvidenceError("EvidenceV2RoleSchemaMismatch", "mounted document schema tag differs from role")
            if "record_count" in member:
                raise EvidenceError("EvidenceV2MembershipMismatch", "JSON member cannot declare record_count")
            return None
        else:
            count = 0
            for row in phase7.iter_jsonl(path):
                phase7.validate_historical_schema(row, spec.schema_file, "EvidenceV2RoleSchemaMismatch")
                if row.get("schema") != spec.schema_tag:
                    raise EvidenceError("EvidenceV2RoleSchemaMismatch", "mounted row schema tag differs from role")
                count += 1
            if member.get("record_count") != count:
                raise EvidenceError("EvidenceV2MembershipMismatch", "JSONL record_count differs from mounted rows")
            return count
    except (OSError, ValueError, json.JSONDecodeError) as error:
        if isinstance(error, EvidenceError):
            raise
        raise EvidenceError("EvidenceV2RoleSchemaMismatch", "mounted V2 member fails runtime schema") from error


def _derive_eligible_stage(
    payload: dict[str, Any], verified_product_statuses: Mapping[str, str] | None = None,
) -> str:
    outcome = payload["capture_outcome"]
    if outcome["exit_code"] in {1, 130} or outcome["data_usability"] == "unusable":
        return "raw"
    if outcome["exit_code"] == 2 or outcome["data_usability"] == "record_only":
        return "normalization_record_only"
    if outcome["shutdown_status"] != "completed" or outcome["capture_continuity"] != "continuous_within_recorded_mechanical_scopes":
        return "normalization_record_only"
    if verified_product_statuses is not None and all(
        verified_product_statuses.get(ticker) == "bracketed"
        for ticker in payload["market_tickers"]
    ):
        return "backtest_v4"
    return "normalization_record_only"


def _verify_product_packages(
    root: Path,
    payload: dict[str, Any],
    product_member_paths: set[str],
) -> dict[str, str]:
    declarations = payload["product_packages"]
    by_ticker: dict[str, dict[str, Any]] = {}
    expected_paths: set[str] = set()
    statuses: dict[str, str] = {}
    selected = set(payload["market_tickers"])
    declared_tickers = {item["ticker"] for item in declarations}
    unavailable = {
        item["ticker"] for item in payload["product_lineage"] if item["status"] == "unavailable"
    }
    if not declared_tickers.issubset(selected) or declared_tickers & unavailable:
        raise EvidenceError("EvidenceV2MembershipMismatch", "product package is unselected or unavailable")
    catalog: product_terms.ProductCatalog | None = None
    catalog_path_value = payload.get("product_catalog_path")
    if payload.get("furthest_materialized_stage") == "backtest_v4" and catalog_path_value is None:
        raise EvidenceError(
            "EvidenceV2EligibilityMismatch",
            "strict backtest evidence requires a mounted product catalog",
        )
    if catalog_path_value is not None:
        catalog_path = _safe_member(root, catalog_path_value)
        if catalog_path.name != "manifest.json":
            raise EvidenceError("EvidenceV2MembershipMismatch", "product catalog path must name manifest.json")
        try:
            catalog = product_terms.ProductCatalog.load(catalog_path.parent)
        except ValueError as error:
            raise EvidenceError("EvidenceV2EligibilityMismatch", "delegated catalog verification failed") from error
        expected_paths.add(catalog_path.relative_to(root).as_posix())
    for declaration in declarations:
        ticker = declaration["ticker"]
        if ticker in by_ticker:
            raise EvidenceError("EvidenceV2MembershipMismatch", "duplicate product-package ticker")
        by_ticker[ticker] = declaration
        package_root = _safe_member(root, declaration["package_root"])
        policy_path = _safe_member(root, declaration["conversion_policy_path"])
        try:
            package = product_terms.ProductPackage.load(package_root)
            policy = product_terms.ConversionPolicy.load(policy_path)
            policy.require_core_compatible(package.terms)
        except ValueError as error:
            raise EvidenceError("EvidenceV2EligibilityMismatch", "delegated product verification failed") from error
        if package.terms.market_ticker != ticker:
            raise EvidenceError("EvidenceV2EligibilityMismatch", "product package ticker differs")
        if declaration.get("truth_category", package.evidence.truth_category) != package.evidence.truth_category:
            raise EvidenceError("EvidenceV2EligibilityMismatch", "product package truth category differs")
        capture_start = _parse_utc(payload["capture_spec"]["started_at_utc"], "capture start")
        capture_end = _parse_utc(payload["capture_spec"]["ended_at_utc"], "capture end")
        try:
            package.verify_capture(
                {
                    "ticker": ticker,
                    "capture_started_at_utc_ns": int(capture_start.timestamp() * 1_000_000_000),
                    "capture_ended_at_utc_ns": int(capture_end.timestamp() * 1_000_000_000),
                }
            )
        except ValueError as error:
            raise EvidenceError("EvidenceV2EligibilityMismatch", "product review does not cover capture") from error
        observations = {
            item.get("observation_id") for item in package.evidence.payload.get("acquisitions", [])
        }
        statuses[ticker] = "bracketed" if {"opening", "closing"}.issubset(observations) else "opening_only"
        expected_paths.add(policy_path.relative_to(root).as_posix())
        expected_paths.update(
            path.relative_to(root).as_posix()
            for path in package_root.rglob("*")
            if path.is_file()
        )
    if expected_paths != product_member_paths:
        raise EvidenceError("EvidenceV2MembershipMismatch", "product package member declarations differ")
    if catalog is not None:
        entries = catalog.payload["entries"]
        if len(entries) != len(selected) or {item["market_ticker"] for item in entries} != selected:
            raise EvidenceError("EvidenceV2EligibilityMismatch", "catalog market membership differs")
        capture_start = _parse_utc(payload["capture_spec"]["started_at_utc"], "capture start")
        capture_end = _parse_utc(payload["capture_spec"]["ended_at_utc"], "capture end")
        series: set[str] = set()
        for declaration in declarations:
            ticker = declaration["ticker"]
            try:
                resolved = catalog.resolve(
                    {
                        "ticker": ticker,
                        "capture_started_at_utc_ns": int(capture_start.timestamp() * 1_000_000_000),
                        "capture_ended_at_utc_ns": int(capture_end.timestamp() * 1_000_000_000),
                    }
                )
            except ValueError as error:
                raise EvidenceError("EvidenceV2EligibilityMismatch", "catalog does not resolve capture") from error
            declared_root = _safe_member(root, declaration["package_root"])
            if resolved.path != declared_root.resolve():
                raise EvidenceError("EvidenceV2EligibilityMismatch", "catalog package differs from declaration")
            series.add(resolved.terms.identity["series_ticker"])
        if len(series) != len(selected):
            raise EvidenceError("EvidenceV2EligibilityMismatch", "selected products do not have distinct series")
    lineage = {item["ticker"]: item["status"] for item in payload["product_lineage"]}
    if set(lineage) != set(payload["market_tickers"]):
        raise EvidenceError("EvidenceV2EligibilityMismatch", "product lineage ticker membership differs")
    for ticker, declared_status in lineage.items():
        verified = statuses.get(ticker, "unavailable")
        if declared_status != verified:
            raise EvidenceError("EvidenceV2EligibilityMismatch", "product status is not verifier-derived")
    return {ticker: statuses.get(ticker, "unavailable") for ticker in payload["market_tickers"]}


def _verify_selected_markets(
    selected: list[str],
    raw_metadata: dict[str, Any],
    config: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    if raw_metadata.get("market_tickers") != selected:
        raise EvidenceError("EvidenceV2LineageMismatch", "raw selected markets differ")
    for document, label in ((config, "config"), (result, "Result")):
        if document is None:
            continue
        tickers = [item.get("product_identity", {}).get("ticker") for item in document.get("products", [])]
        if tickers != selected:
            raise EvidenceError("EvidenceV2LineageMismatch", f"{label} selected markets differ")


def _verify_measurement_identities(root: Path, members: list[dict[str, Any]]) -> None:
    member_by_role = {
        member["role"]: member
        for member in members
        if member["role"] not in {"product_package_member", "repetition_member"}
    }
    expected = {
        "capture_measurement": ("capture-v2", ("capture_policy",)),
        "normalization_measurement": (
            "normalization-v3",
            ("raw_frames", "raw_metadata", "product_catalog"),
        ),
        "feature_measurement": (
            "features-v3",
            ("normalization_manifest", "normalized_records", "source_scopes", "product_map"),
        ),
        "backtest_measurement": (
            "backtest-v4",
            (
                "backtest_config", "normalization_manifest", "normalized_records",
                "source_scopes", "product_map", "feature_manifest", "feature_rows",
            ),
        ),
    }
    product_identities = [
        (member["path"], member["sha256"])
        for member in members if member["role"] == "product_package_member"
    ]
    for role, (expected_stage, input_roles) in expected.items():
        member = member_by_role.get(role)
        if member is None:
            continue
        document = phase7.read_json(root / member["path"])
        if document.get("stage") != expected_stage:
            raise EvidenceError("EvidenceV2LineageMismatch", f"{role} stage differs")
        expected_identities = [
            (
                member_by_role[input_role]["path"],
                member_by_role[input_role]["sha256"],
            )
            for input_role in input_roles
            if input_role in member_by_role
        ]
        if role == "normalization_measurement" and product_identities:
            expected_identities.extend(product_identities)
        actual_identities = [
            (item.get("path"), item.get("sha256"))
            for item in document.get("identity_files", [])
        ]
        if Counter(actual_identities) != Counter(expected_identities):
            raise EvidenceError("EvidenceV2LineageMismatch", f"{role} identity files differ")


def _verify_truth_boundary(
    raw_metadata: dict[str, Any], payload: dict[str, Any]
) -> None:
    raw_truth = raw_metadata.get("truth_category")
    package_truth = {
        declaration.get("truth_category")
        for declaration in payload.get("product_packages", [])
    }
    if package_truth and package_truth != {raw_truth}:
        raise EvidenceError(
            "EvidenceV2EligibilityMismatch",
            "raw and reviewed-product truth categories differ",
        )


def _normalization_sequence_identity(
    row: dict[str, Any], topology: Any
) -> tuple[Any, ...]:
    subscription = row.get("subscription_id")
    key: tuple[Any, ...] = (
        row.get("connection_segment_id"),
        None if subscription is None else str(subscription),
        row.get("source_sequence"),
    )
    if topology == "independent":
        key = (*key[:2], row.get("market_ticker"), key[2])
    return key


def _verify_normalization_chain(
    root: Path,
    selected: list[str],
    members: list[dict[str, Any]],
    payload: dict[str, Any] | None = None,
) -> None:
    by_role = {member["role"]: member for member in members}
    required = (
        "raw_frames", "raw_metadata", "normalization_manifest", "normalized_records",
        "source_scopes", "product_map", "normalization_telemetry",
    )
    if any(role not in by_role for role in required):
        raise EvidenceError("EvidenceV2LineageMismatch", "normalization chain is incomplete")
    manifest = phase7.read_json(root / by_role["normalization_manifest"]["path"])
    product_map = phase7.read_json(root / by_role["product_map"]["path"])
    telemetry = phase7.read_json(root / by_role["normalization_telemetry"]["path"])
    expected_hashes = {
        "input_frames_sha256": by_role["raw_frames"]["sha256"],
        "input_capture_metadata_sha256": by_role["raw_metadata"]["sha256"],
        "output_records_sha256": by_role["normalized_records"]["sha256"],
        "output_source_scopes_sha256": by_role["source_scopes"]["sha256"],
        "output_product_sha256": by_role["product_map"]["sha256"],
    }
    if any(manifest.get(key) != value for key, value in expected_hashes.items()):
        raise EvidenceError("EvidenceV2LineageMismatch", "normalization artifact identity differs")
    if manifest.get("market_tickers") != selected:
        raise EvidenceError("EvidenceV2LineageMismatch", "normalization selected markets differ")
    products = product_map.get("products", [])
    if [item.get("ticker") for item in products] != selected:
        raise EvidenceError("EvidenceV2LineageMismatch", "normalization product-map order differs")
    if payload is not None and payload.get("product_packages"):
        catalog_path = payload.get("product_catalog_path")
        if catalog_path is None:
            raise EvidenceError("EvidenceV2LineageMismatch", "normalization catalog is absent")
        try:
            catalog = product_terms.ProductCatalog.load(_safe_member(root, catalog_path).parent)
            declaration_by_ticker = {
                item["ticker"]: item for item in payload["product_packages"]
            }
            declarations = [declaration_by_ticker[ticker] for ticker in selected]
            policies = {
                product_terms.ConversionPolicy.load(
                    _safe_member(root, item["conversion_policy_path"])
                ).payload_sha256
                for item in declarations
            }
            if len(policies) != 1:
                raise EvidenceError(
                    "EvidenceV2LineageMismatch",
                    "normalization conversion policy is not singular",
                )
            expected_product_lineage = []
            for item in declarations:
                package = product_terms.ProductPackage.load(
                    _safe_member(root, item["package_root"])
                )
                expected_product_lineage.append({
                    "ticker": item["ticker"],
                    "product_terms_sha256": package.terms.payload_sha256,
                    "source_manifest_sha256": package.evidence.payload_sha256,
                    "review_sha256": package.review.payload_sha256,
                })
        except ValueError as error:
            raise EvidenceError(
                "EvidenceV2LineageMismatch",
                "mounted normalization product proof is invalid",
            ) from error
        if (
            manifest.get("product_catalog_sha256") != catalog.payload_sha256
            or manifest.get("conversion_policy_sha256") != next(iter(policies))
            or manifest.get("product_lineage") != expected_product_lineage
        ):
            raise EvidenceError(
                "EvidenceV2LineageMismatch",
                "normalization product lineage differs from mounted product proof",
            )
    records_path = root / by_role["normalized_records"]["path"]
    event_counts: Counter[str] = Counter()
    discontinuity_counts: Counter[str] = Counter()
    for row in phase7.iter_jsonl(records_path):
        ticker = row.get("ticker")
        if ticker is not None and ticker not in selected:
            raise EvidenceError("EvidenceV2LineageMismatch", "normalized row names an unselected market")
        if row.get("kind") == "market_event":
            event_counts[str(row.get("event_type"))] += 1
        elif row.get("kind") == "discontinuity":
            discontinuity_counts[str(row.get("control_type"))] += 1
    if dict(sorted(event_counts.items())) != manifest.get("event_counts"):
        raise EvidenceError("EvidenceV2LineageMismatch", "normalization event counts differ")
    if dict(sorted(discontinuity_counts.items())) != manifest.get("discontinuity_counts"):
        raise EvidenceError("EvidenceV2LineageMismatch", "normalization discontinuity counts differ")
    raw_rows = list(phase7.iter_jsonl(root / by_role["raw_frames"]["path"]))
    raw_count = len(raw_rows)
    raw_metadata = phase7.read_json(root / by_role["raw_metadata"]["path"])
    topology = raw_metadata.get("sequence_domain", {}).get("topology")
    sequence_payloads: dict[tuple[Any, ...], str] = {}
    duplicate_count = 0
    reconstructed_samples: list[dict[str, int]] = []
    for row in raw_rows:
        sequence = row.get("source_sequence")
        if sequence is None:
            continue
        key = _normalization_sequence_identity(row, topology)
        raw_frame = row.get("raw_frame_utf8")
        try:
            message = json.loads(raw_frame) if isinstance(raw_frame, str) else row
        except json.JSONDecodeError as error:
            raise EvidenceError("EvidenceV2LineageMismatch", "raw sequence payload is malformed") from error
        payload_hash = _payload_sha256(message)
        prior = sequence_payloads.get(key)
        if prior is not None:
            if prior != payload_hash:
                raise EvidenceError("EvidenceV2LineageMismatch", "raw sequence identity conflicts")
            duplicate_count += 1
            continue
        sequence_payloads[key] = payload_hash
        count = len(sequence_payloads)
        if count & (count - 1) == 0:
            reconstructed_samples.append(
                {
                    "raw_ingress_ordinal": row["raw_ingress_ordinal"],
                    "sequenced_unique_identities": count,
                }
            )
    telemetry_expected = {
        "input_frames_sha256": by_role["raw_frames"]["sha256"],
        "input_capture_metadata_sha256": by_role["raw_metadata"]["sha256"],
        "processed_raw_records": raw_count,
        "sequenced_unique_identities": len(sequence_payloads),
        "peak_sequenced_unique_identities": len(sequence_payloads),
        "identical_duplicates_skipped": duplicate_count,
        "samples": reconstructed_samples,
    }
    if any(telemetry.get(key) != value for key, value in telemetry_expected.items()):
        raise EvidenceError("EvidenceV2LineageMismatch", "normalization telemetry differs")
    if manifest.get("identical_duplicates_skipped") != duplicate_count:
        raise EvidenceError("EvidenceV2LineageMismatch", "normalization duplicate count differs")
    samples = telemetry.get("samples", [])
    ordinals = [item.get("raw_ingress_ordinal") for item in samples]
    counts = [item.get("sequenced_unique_identities") for item in samples]
    if (
        ordinals != sorted(set(ordinals))
        or any(not isinstance(value, int) or value > raw_count for value in ordinals)
        or counts != sorted(counts)
        or any(value <= 0 or value & (value - 1) for value in counts)
        or (counts and counts[-1] > telemetry.get("sequenced_unique_identities", -1))
        or telemetry.get("peak_sequenced_unique_identities", -1)
        < telemetry.get("sequenced_unique_identities", 0)
    ):
        raise EvidenceError("EvidenceV2LineageMismatch", "normalization telemetry samples differ")


def _verify_feature_chain(
    root: Path, selected: list[str], members: list[dict[str, Any]]
) -> None:
    by_role = {member["role"]: member for member in members}
    required = (
        "raw_frames", "raw_metadata", "normalization_manifest", "normalized_records",
        "source_scopes", "product_map", "feature_manifest", "feature_rows",
    )
    if any(role not in by_role for role in required):
        raise EvidenceError("EvidenceV2LineageMismatch", "feature chain is incomplete")
    normalization = phase7.read_json(root / by_role["normalization_manifest"]["path"])
    product_map = phase7.read_json(root / by_role["product_map"]["path"])
    manifest = phase7.read_json(root / by_role["feature_manifest"]["path"])
    inputs = manifest.get("input", {})
    expected_inputs = {
        "normalization_manifest_sha256": by_role["normalization_manifest"]["sha256"],
        "records_sha256": by_role["normalized_records"]["sha256"],
        "source_scopes_sha256": by_role["source_scopes"]["sha256"],
        "product_map_sha256": by_role["product_map"]["sha256"],
    }
    if any(inputs.get(key) != value for key, value in expected_inputs.items()):
        raise EvidenceError("EvidenceV2LineageMismatch", "feature upstream identity differs")
    if inputs.get("capture_identity") != {
        "frames_sha256": by_role["raw_frames"]["sha256"],
        "metadata_sha256": by_role["raw_metadata"]["sha256"],
    }:
        raise EvidenceError("EvidenceV2LineageMismatch", "feature capture identity differs")
    if inputs.get("market_tickers") != selected:
        raise EvidenceError("EvidenceV2LineageMismatch", "feature selected markets differ")
    for key in ("product_catalog_sha256", "conversion_policy_sha256"):
        if inputs.get(key) != normalization.get(key):
            raise EvidenceError("EvidenceV2LineageMismatch", "feature product input differs")
    rows_path = root / by_role["feature_rows"]["path"]
    rows = list(phase7.iter_jsonl(rows_path))
    output = manifest.get("output", {})
    if output.get("feature_rows_sha256") != by_role["feature_rows"]["sha256"] or output.get(
        "feature_row_count"
    ) != len(rows):
        raise EvidenceError("EvidenceV2LineageMismatch", "feature output identity differs")
    product_entries = {item["ticker"]: item for item in product_map.get("products", [])}
    manifest_products = manifest.get("products", [])
    if [item.get("product_identity", {}).get("ticker") for item in manifest_products] != selected:
        raise EvidenceError("EvidenceV2LineageMismatch", "feature product order differs")
    rows_by_ticker: dict[str, list[dict[str, Any]]] = {ticker: [] for ticker in selected}
    common_lineage = {
        "input_normalization_manifest_sha256": by_role["normalization_manifest"]["sha256"],
        "input_records_sha256": by_role["normalized_records"]["sha256"],
        "input_source_scopes_sha256": by_role["source_scopes"]["sha256"],
        "input_product_map_sha256": by_role["product_map"]["sha256"],
    }
    for row in rows:
        ticker = row.get("product_identity", {}).get("ticker")
        if ticker not in rows_by_ticker:
            raise EvidenceError("EvidenceV2LineageMismatch", "feature row names an unselected market")
        entry = product_entries[ticker]
        entry_hash = _payload_sha256(entry)
        expected_lineage = {**common_lineage, "input_product_entry_sha256": entry_hash}
        for key in (
            "product_terms_sha256", "source_manifest_sha256", "review_sha256",
            "conversion_policy_sha256",
        ):
            if key in entry:
                expected_lineage[key] = entry[key]
        if row.get("lineage") != expected_lineage or row.get("product_identity", {}).get(
            "input_product_entry_sha256"
        ) != entry_hash:
            raise EvidenceError("EvidenceV2LineageMismatch", "feature row lineage differs")
        rows_by_ticker[ticker].append(row)
    for item in manifest_products:
        ticker = item["product_identity"]["ticker"]
        entry = product_entries[ticker]
        entry_hash = _payload_sha256(entry)
        ticker_rows = rows_by_ticker[ticker]
        segments = list(dict.fromkeys(row["segment_identity"]["book_segment_id"] for row in ticker_rows))
        first = None if not ticker_rows else ticker_rows[0]["as_of"]["product_applied_watermark"]
        last = None if not ticker_rows else ticker_rows[-1]["as_of"]["product_applied_watermark"]
        expected_reviewed = {
            "ticker": ticker,
            **{
                key: entry.get(key)
                for key in (
                    "product_terms_sha256", "source_manifest_sha256", "review_sha256",
                    "conversion_policy_sha256",
                )
            },
        }
        if (
            item.get("product_identity") != entry
            or item.get("input_product_entry_sha256") != entry_hash
            or item.get("row_count") != len(ticker_rows)
            or item.get("segments") != segments
            or item.get("first_product_applied_watermark") != first
            or item.get("last_product_applied_watermark") != last
            or item.get("reviewed_lineage") != expected_reviewed
        ):
            raise EvidenceError("EvidenceV2LineageMismatch", "feature product reconstruction differs")


def _verify_backtest_upstream_chain(
    root: Path, selected: list[str], members: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    by_role = {member["role"]: member for member in members}
    required = (
        "normalization_manifest", "normalized_records", "source_scopes", "product_map",
        "feature_manifest", "feature_rows", "backtest_config", "result_manifest",
    )
    if any(role not in by_role for role in required):
        raise EvidenceError("EvidenceV2LineageMismatch", "backtest upstream chain is incomplete")
    config = phase7.read_json(root / by_role["backtest_config"]["path"])
    result = phase7.read_json(root / by_role["result_manifest"]["path"])
    product_map = phase7.read_json(root / by_role["product_map"]["path"])
    feature_manifest = phase7.read_json(root / by_role["feature_manifest"]["path"])
    normalization_inputs = config.get("inputs", {}).get("normalization", {})
    feature_inputs = config.get("inputs", {}).get("features", {})
    expected_normalization = {
        "manifest_sha256": by_role["normalization_manifest"]["sha256"],
        "records_sha256": by_role["normalized_records"]["sha256"],
        "source_scopes_sha256": by_role["source_scopes"]["sha256"],
        "product_map_sha256": by_role["product_map"]["sha256"],
    }
    expected_features = {
        "manifest_sha256": by_role["feature_manifest"]["sha256"],
        "rows_sha256": by_role["feature_rows"]["sha256"],
        "feature_definition_sha256": _payload_sha256(feature_manifest.get("feature_definitions")),
    }
    if any(normalization_inputs.get(key) != value for key, value in expected_normalization.items()):
        raise EvidenceError("EvidenceV2LineageMismatch", "backtest normalization input differs")
    if any(feature_inputs.get(key) != value for key, value in expected_features.items()):
        raise EvidenceError("EvidenceV2LineageMismatch", "backtest feature input differs")
    declared_paths = {
        ("normalization", "manifest_path"): "normalization_manifest",
        ("normalization", "records_path"): "normalized_records",
        ("normalization", "source_scopes_path"): "source_scopes",
        ("normalization", "product_map_path"): "product_map",
        ("features", "manifest_path"): "feature_manifest",
        ("features", "rows_path"): "feature_rows",
    }
    package_prefix: tuple[str, ...] | None = None
    for (group, field), role in declared_paths.items():
        declared_value = config.get("inputs", {}).get(group, {}).get(field)
        if not isinstance(declared_value, str):
            raise EvidenceError(
                "EvidenceV2LineageMismatch",
                f"backtest {group} path is absent",
            )
        declared_path = PurePosixPath(declared_value)
        member_path = PurePosixPath(by_role[role]["path"])
        if (
            declared_path.is_absolute()
            or "\\" in declared_value
            or ".." in declared_path.parts
            or len(declared_path.parts) < len(member_path.parts)
            or declared_path.parts[-len(member_path.parts):] != member_path.parts
        ):
            raise EvidenceError(
                "EvidenceV2LineageMismatch",
                f"backtest {group} path differs from mounted {role}",
            )
        prefix = declared_path.parts[:-len(member_path.parts)]
        if package_prefix is None:
            package_prefix = prefix
        elif prefix != package_prefix:
            raise EvidenceError(
                "EvidenceV2LineageMismatch",
                "backtest mounted input paths do not share one package root",
            )
    entries = {item["ticker"]: item for item in product_map.get("products", [])}
    products = config.get("products", [])
    if [item.get("product_identity", {}).get("ticker") for item in products] != selected:
        raise EvidenceError("EvidenceV2LineageMismatch", "backtest product order differs")
    for product in products:
        ticker = product["product_identity"]["ticker"]
        entry = entries.get(ticker)
        if entry is None or product["product_identity"].get("input_product_entry_sha256") != _payload_sha256(entry):
            raise EvidenceError("EvidenceV2LineageMismatch", "backtest product entry differs")
        reviewed = {
            "ticker": ticker,
            **{
                key: entry.get(key)
                for key in (
                    "product_terms_sha256", "source_manifest_sha256", "review_sha256",
                    "conversion_policy_sha256",
                )
            },
        }
        if product.get("reviewed_lineage") != reviewed:
            raise EvidenceError("EvidenceV2LineageMismatch", "backtest reviewed lineage differs")
    if (
        result.get("run_id") != config.get("run_id")
        or result.get("execution") != config.get("execution")
        or result.get("scheduling_policy")
        != config.get("execution", {}).get("scheduling_policy")
        or
        result.get("config_sha256") != by_role["backtest_config"]["sha256"]
        or result.get("inputs") != config.get("inputs")
        or result.get("feature_definition_sha256")
        != expected_features["feature_definition_sha256"]
        or [item.get("product_identity") for item in result.get("products", [])]
        != [item.get("product_identity") for item in products]
        or [item.get("reviewed_lineage") for item in result.get("products", [])]
        != [item.get("reviewed_lineage") for item in products]
    ):
        raise EvidenceError("EvidenceV2LineageMismatch", "Result upstream lineage differs")
    return config, result


def _validate_outcome(payload: dict[str, Any]) -> None:
    outcome = payload["capture_outcome"]
    expected = {
        0: ("completed", "continuous_within_recorded_mechanical_scopes", "strict_eligible"),
        1: ("failed", "incomplete", "unusable"),
        2: ("completed", "observed_discontinuous", "record_only"),
        130: ("interrupted", "incomplete", "unusable"),
    }
    actual = (
        outcome["shutdown_status"], outcome["capture_continuity"], outcome["data_usability"]
    )
    if actual != expected[outcome["exit_code"]]:
        raise EvidenceError("EvidenceV2EligibilityMismatch", "capture outcome tuple differs from exit code")


def _credential_payload_inventory(
    loaded: Iterable[tuple[dict[str, Any], bytes]],
) -> tuple[str, int, int]:
    entries = [
        {
            "path": member["path"],
            "byte_length": len(raw),
            "sha256": _sha256_bytes(raw),
        }
        for member, raw in loaded
        if member["role"] != "credential_scan_report"
    ]
    entries.sort(key=lambda item: item["path"].encode("utf-8"))
    return _payload_sha256(entries), len(entries), sum(item["byte_length"] for item in entries)


def verify_evidence_manifest_v2(
    manifest_path: Path, *, artifact_root: Path | None = None, require_artifacts: bool = False,
) -> dict[str, Any]:
    """Additive stronger verifier; never routes through frozen V1 behavior."""
    try:
        document = phase7.read_json(manifest_path)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
        raise EvidenceError(
            "EvidenceV2ManifestSchemaMismatch", "unsupported V2 evidence manifest"
        ) from error
    try:
        phase7.validate_historical_schema(document, "b2c-evidence-manifest-v2.schema.json", "EvidenceV2ManifestSchemaMismatch")
    except (ValueError, KeyError) as error:
        raise EvidenceError("EvidenceV2ManifestSchemaMismatch", "unsupported V2 evidence manifest") from error
    if document.get("schema") != EVIDENCE_V2_SCHEMA:
        raise EvidenceError("EvidenceV2ManifestSchemaMismatch", "verify-v2 requires a V2 manifest")
    payload = document["payload"]
    if document.get("payload_sha256") != _payload_sha256(payload):
        raise EvidenceError("EvidenceV2PayloadHashMismatch", "V2 payload hash is stale")
    _validate_outcome(payload)
    members = payload["members"]
    roles = [member["role"] for member in members]
    paths = [member["path"] for member in members]
    if len(paths) != len(set(paths)):
        raise EvidenceError("EvidenceV2MembershipMismatch", "member paths must be unique")
    repeatable_opaque_roles = {
        "product_package_member",
        "repetition_member",
        "operational_control_member",
    }
    fixed_roles = [role for role in roles if role not in repeatable_opaque_roles]
    if len(fixed_roles) != len(set(fixed_roles)):
        raise EvidenceError("EvidenceV2MembershipMismatch", "fixed pipeline roles must be unique")
    specs: dict[str, RoleSpec | None] = {}
    for member in members:
        role = member["role"]
        if role in repeatable_opaque_roles:
            if member["kind"] != "opaque" or member["schema_file"] is not None:
                raise EvidenceError("EvidenceV2RoleSchemaMismatch", "product members must be opaque")
            specs[member["path"]] = None
            continue
        spec = _role_spec(role)
        if spec is None:
            raise EvidenceError("EvidenceV2RoleForbidden", f"unknown V2 member role {role}")
        if member["schema_file"] != spec.schema_file or member["kind"] != spec.kind:
            raise EvidenceError("EvidenceV2RoleSchemaMismatch", "member schema binding differs from its role")
        specs[member["path"]] = spec
    stage = payload["furthest_materialized_stage"]
    required = _required_roles_for_stage(stage)
    actual_fixed = {
        role for role in roles
        if not role.startswith("risk_trace_") and role not in repeatable_opaque_roles
    }
    missing = required - actual_fixed
    if missing:
        raise EvidenceError("EvidenceV2RoleMissing", f"stage-required role is absent: {sorted(missing)[0]}")
    forbidden = actual_fixed - required - _OPTIONAL_CONTROL_ROLES
    if forbidden:
        raise EvidenceError("EvidenceV2RoleForbidden", f"role is forbidden at this stage: {sorted(forbidden)[0]}")
    traces = [role for role in roles if role.startswith("risk_trace_")]
    if stage == "backtest_v4":
        if len(traces) != len(payload["market_tickers"]):
            raise EvidenceError("EvidenceV2RoleMissing", "backtest requires one risk trace per contract")
    elif traces:
        raise EvidenceError("EvidenceV2RoleForbidden", "risk traces are forbidden before backtest")
    if payload["lineage_edges"] != _derive_role_lineage(members, stage):
        raise EvidenceError("EvidenceV2LineageMismatch", "declared role lineage differs from reconstruction")
    required_repetition_stages: list[str] = []
    if _STAGE_ORDER.index(stage) >= _STAGE_ORDER.index("normalization_record_only"):
        required_repetition_stages.append("normalization_v3")
    if _STAGE_ORDER.index(stage) >= _STAGE_ORDER.index("features_v3"):
        required_repetition_stages.append("features_v3")
    if stage == "backtest_v4":
        required_repetition_stages.append("backtest_v4")
    if [item["stage"] for item in payload["repetitions"]] != required_repetition_stages:
        raise EvidenceError("EvidenceV2RepetitionMismatch", "stage repetition declarations differ")
    if not require_artifacts:
        derived_eligible = _derive_eligible_stage(payload)
        if _STAGE_ORDER.index(stage) > _STAGE_ORDER.index(derived_eligible):
            raise EvidenceError("EvidenceV2EligibilityMismatch", "materialized stage exceeds outcome eligibility")
        if payload["furthest_eligible_stage"] != derived_eligible:
            raise EvidenceError("EvidenceV2EligibilityMismatch", "declared eligible stage requires mounted product proof")
        return {"schema": EVIDENCE_V2_SCHEMA, "verified": True, "artifacts_verified": False, "member_count": len(members)}
    configured_root = artifact_root or manifest_path.parent
    if configured_root.is_symlink():
        raise EvidenceError("EvidenceV2MembershipMismatch", "mounted artifact root is a symlink")
    root = configured_root.resolve()
    try:
        manifest_relative = manifest_path.resolve().relative_to(root).as_posix()
    except ValueError as error:
        raise EvidenceError("EvidenceV2MembershipMismatch", "manifest is outside mounted root") from error
    actual: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise EvidenceError("EvidenceV2MembershipMismatch", "mounted package contains a symlink")
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    allowed = set(paths) | {manifest_relative}
    if actual != allowed:
        raise EvidenceError("EvidenceV2MembershipMismatch", "mounted V2 membership differs")
    loaded: list[tuple[dict[str, Any], bytes]] = []
    record_counts: dict[str, int] = {}
    for member in members:
        path = _safe_member(root, member["path"])
        if not path.is_file():
            raise EvidenceError("EvidenceV2MembershipMismatch", "mounted V2 member is missing")
        count = _v2_validate_member(path, member, specs[member["path"]])
        if count is not None:
            record_counts[member["role"]] = count
        loaded.append((member, path.read_bytes()))
    payload_members = [
        (member["path"], raw)
        for member, raw in loaded
        if member["role"] != "credential_scan_report"
    ]
    findings = scan_credential_bytes(payload_members)
    if findings:
        raise EvidenceError("EvidenceCredentialLeak", f"credential scanner finding {findings[0]['rule_id']}")
    scan_member, scan_raw = next(
        (member, raw) for member, raw in loaded if member["role"] == "credential_scan_report"
    )
    control_findings = scan_credential_bytes(
        [("evidence-manifest.json", manifest_path.read_bytes()), ("control-report.json", scan_raw)]
    )
    if control_findings:
        raise EvidenceError("EvidenceCredentialLeak", f"credential scanner finding {control_findings[0]['rule_id']}")
    scan_report = json.loads(scan_raw)
    inventory_sha256, member_count, byte_count = _credential_payload_inventory(loaded)
    expected_scan = {
        "scanner_identity": "pmm-b2c-deterministic-scanner-v1",
        "ruleset_sha256": CREDENTIAL_RULESET_SHA256,
        "payload_inventory_sha256": inventory_sha256,
        "member_count": member_count,
        "byte_count": byte_count,
        "status": "clean",
    }
    if any(scan_report.get(key) != value for key, value in expected_scan.items()):
        raise EvidenceError("EvidenceV2CredentialScanMismatch", "credential scan report is stale or self-asserted")
    product_statuses = _verify_product_packages(
        root,
        payload,
        {member["path"] for member in members if member["role"] == "product_package_member"},
    )
    derived_eligible = _derive_eligible_stage(payload, product_statuses)
    if _STAGE_ORDER.index(stage) > _STAGE_ORDER.index(derived_eligible):
        raise EvidenceError("EvidenceV2EligibilityMismatch", "materialized stage exceeds mounted eligibility")
    if payload["furthest_eligible_stage"] != derived_eligible:
        raise EvidenceError("EvidenceV2EligibilityMismatch", "declared eligible stage differs from mounted evidence")
    policy_document = phase7.read_json(
        root / next(member["path"] for member in members if member["role"] == "capture_policy")
    )
    policy_member = next(member for member in members if member["role"] == "capture_policy")
    if payload["capture_spec"]["policy_sha256"] != policy_member["sha256"]:
        raise EvidenceError("EvidenceV2LineageMismatch", "capture spec policy identity differs")
    frozen_policy = phase7.REPOSITORY_ROOT / "configs/phase7/b2c_evidence_policy_v1.json"
    if policy_document.get("base_policy_sha256") != phase7.sha256_file(frozen_policy):
        raise EvidenceError("EvidenceV2LineageMismatch", "capture policy does not bind frozen V1 policy bytes")
    capture_start = _parse_utc(payload["capture_spec"]["started_at_utc"], "capture start")
    capture_end = _parse_utc(payload["capture_spec"]["ended_at_utc"], "capture end")
    if int((capture_end - capture_start).total_seconds()) != 43200:
        raise EvidenceError("EvidenceV2LineageMismatch", "capture interval is not exactly twelve hours")
    if len(payload["market_tickers"]) != payload["capture_spec"]["market_count"]:
        raise EvidenceError("EvidenceV2LineageMismatch", "selected market count differs")
    try:
        raw_metadata = phase7.read_json(
            root / next(member["path"] for member in members if member["role"] == "raw_metadata")
        )
        raw_frames = root / next(member["path"] for member in members if member["role"] == "raw_frames")
        _verify_raw_counts(raw_frames, raw_metadata)
    except EvidenceError as error:
        raise EvidenceError("EvidenceV2MembershipMismatch", "raw record counts differ") from error
    _verify_selected_markets(payload["market_tickers"], raw_metadata)
    _verify_truth_boundary(raw_metadata, payload)
    if raw_metadata.get("truth_category") == "Observed":
        member_by_role = {member["role"]: member for member in members}
        missing_control = _OPTIONAL_CONTROL_ROLES - set(member_by_role)
        if missing_control:
            raise EvidenceError(
                "EvidenceV2RoleMissing",
                f"Observed evidence requires operational control role: {sorted(missing_control)[0]}",
            )
        try:
            b2c_operator.verify_run_approval(
                root / member_by_role["run_approval"]["path"],
                candidate_snapshot_path=root / member_by_role["candidate_snapshot"]["path"],
                artifact_root=root,
            )
        except b2c_operator.OperatorError as error:
            raise EvidenceError(
                "EvidenceV2EligibilityMismatch",
                "Observed evidence operational approval is invalid",
            ) from error
        snapshot = phase7.read_json(root / member_by_role["candidate_snapshot"]["path"])
        approval = phase7.read_json(root / member_by_role["run_approval"]["path"])
        referenced_control_paths = {
            item["path"] for item in snapshot["payload"]["pages"]
        }
        referenced_control_paths.update(
            item[field]
            for item in approval["payload"]["acquisition_specs"]
            for field in ("opening_path", "closing_path")
        )
        declared_control_paths = {
            member["path"]
            for member in members
            if member["role"] == "operational_control_member"
        }
        if declared_control_paths != referenced_control_paths:
            raise EvidenceError(
                "EvidenceV2MembershipMismatch",
                "operational control member declarations differ from approval inputs",
            )
        if (
            approval["payload"]["selected_market_tickers"] != payload["market_tickers"]
            or approval["payload"]["capture_window"] != {
                "started_at_utc": payload["capture_spec"]["started_at_utc"],
                "ended_at_utc": payload["capture_spec"]["ended_at_utc"],
            }
        ):
            raise EvidenceError(
                "EvidenceV2EligibilityMismatch",
                "operational approval differs from evidence capture",
            )
    _verify_measurement_identities(root, members)
    if _STAGE_ORDER.index(stage) >= _STAGE_ORDER.index("normalization_record_only"):
        _verify_normalization_chain(root, payload["market_tickers"], members, payload)
    if _STAGE_ORDER.index(stage) >= _STAGE_ORDER.index("features_v3"):
        _verify_feature_chain(root, payload["market_tickers"], members)
    backtest_documents: tuple[dict[str, Any], dict[str, Any]] | None = None
    if stage == "backtest_v4":
        backtest_documents = _verify_backtest_upstream_chain(
            root, payload["market_tickers"], members
        )
    if payload["repetitions"]:
        _verify_repetitions(root, payload["repetitions"], members)
    if stage == "backtest_v4":
        assert backtest_documents is not None
        config_document, result_document = backtest_documents
        _verify_selected_markets(
            payload["market_tickers"], raw_metadata, config_document, result_document
        )
        result_member = next(member for member in members if member["role"] == "result_manifest")
        _verify_backtest_descriptors(
            config_document, result_document, members, result_member["path"]
        )
        _verify_backtest_rows_and_telemetry(root, config_document, result_document, members)
    return {"schema": EVIDENCE_V2_SCHEMA, "verified": True, "artifacts_verified": True, "member_count": len(members)}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _payload_sha256(value: Any) -> str:
    return _sha256_bytes(phase7.canonical_json(value).encode("utf-8"))


def _parse_utc(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise EvidenceError("EvidenceIntervalMismatch", f"{field_name} is not RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError("EvidenceIntervalMismatch", f"{field_name} must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _count_jsonl(path: Path, expected_schema: str | None) -> int:
    count = 0
    try:
        for row in phase7.iter_jsonl(path):
            if expected_schema is not None and row.get("schema") != expected_schema:
                raise EvidenceError(
                    "EvidenceMemberSchemaMismatch", f"JSONL row schema differs in {path.name}"
                )
            count += 1
    except (OSError, ValueError, json.JSONDecodeError) as error:
        if isinstance(error, EvidenceError):
            raise
        raise EvidenceError("EvidenceMemberInvalid", f"cannot parse JSONL member {path.name}") from error
    return count


def _safe_member(root: Path, relative: str) -> Path:
    candidate = root / relative
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise EvidenceError("EvidencePathUnsafe", f"member path escapes artifact root: {relative}") from error
    if candidate.is_symlink():
        raise EvidenceError("EvidencePathUnsafe", f"member path is a symlink: {relative}")
    return candidate


def _validate_index(document: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    phase7.validate_historical_schema(
        document, "b2c-evidence-manifest-v1.schema.json", "EvidenceManifestSchemaMismatch"
    )
    payload = document["payload"]
    if document["schema"] != EVIDENCE_SCHEMA or document["payload_sha256"] != _payload_sha256(payload):
        raise EvidenceError("EvidencePayloadHashMismatch", "evidence manifest payload hash is stale")
    tickers = payload["market_tickers"]
    if tickers != sorted(tickers):
        raise EvidenceError("EvidenceMarketMembershipMismatch", "market tickers must be sorted")
    lineage_tickers = [item["ticker"] for item in payload["product_lineage"]]
    if lineage_tickers != tickers:
        raise EvidenceError(
            "EvidenceProductLineageMismatch", "product lineage must name every selected ticker in order"
        )
    capture_start = _parse_utc(payload["capture_spec"]["started_at_utc"], "capture start")
    capture_end = _parse_utc(payload["capture_spec"]["ended_at_utc"], "capture end")
    if capture_end <= capture_start or int((capture_end - capture_start).total_seconds()) != payload["capture_spec"]["duration_seconds"]:
        raise EvidenceError("EvidenceIntervalMismatch", "capture timestamps do not span the declared duration")
    for lineage in payload["product_lineage"]:
        if lineage["status"] != "reviewed":
            unexpected = {
                "effective_from_utc", "effective_until_utc", "product_terms_sha256",
                "source_manifest_sha256", "review_sha256", "conversion_policy_sha256",
            } & set(lineage)
            if unexpected:
                raise EvidenceError(
                    "EvidenceProductLineageMismatch", "unavailable lineage cannot carry reviewed identities"
                )
            continue
        effective_from = _parse_utc(lineage["effective_from_utc"], "product effective start")
        effective_until = _parse_utc(lineage["effective_until_utc"], "product effective end")
        if effective_from > capture_start or effective_until < capture_end:
            raise EvidenceError(
                "EvidenceProductLineageMismatch",
                f"reviewed product interval does not cover the capture for {lineage['ticker']}",
            )
    members: dict[str, dict[str, Any]] = {}
    paths: set[str] = set()
    for member in payload["members"]:
        role = member["role"]
        path = member["path"]
        if role in members or path in paths:
            raise EvidenceError("EvidenceMemberDuplicate", "member roles and paths must be unique")
        members[role] = member
        paths.add(path)
    for edge in payload["lineage_edges"]:
        if edge["from_role"] not in members or edge["to_role"] not in members:
            raise EvidenceError("EvidenceLineageMismatch", "lineage edge names an unknown member role")
    for repetition in payload["repetitions"]:
        equal_hash = repetition["first_inventory_sha256"] == repetition["second_inventory_sha256"]
        if repetition["byte_identical"] != equal_hash:
            raise EvidenceError(
                "EvidenceRepetitionMismatch", "byte-identical verdict differs from inventory identities"
            )
    outcome = payload["capture_outcome"]
    missing_base = BASE_ROLES - set(members)
    if missing_base:
        raise EvidenceError("EvidenceMemberMissing", "evidence requires raw members and capture measurement")
    if payload["capture_spec"]["policy_sha256"] != members["capture_policy"]["sha256"]:
        raise EvidenceError("EvidenceLineageMismatch", "capture policy identity differs")
    strict = outcome["data_usability"] == "strict_eligible"
    if strict != (outcome["exit_code"] == 0):
        raise EvidenceError("EvidenceOutcomeMismatch", "only strict-eligible capture evidence may use exit zero")
    expected_capture_outcomes = {
        0: ("completed", "continuous_within_recorded_mechanical_scopes", "strict_eligible"),
        130: ("interrupted", "incomplete", "unusable"),
        1: ("failed", "incomplete", "unusable"),
    }
    if outcome["exit_code"] in expected_capture_outcomes and (
        outcome["shutdown_status"], outcome["capture_continuity"], outcome["data_usability"]
    ) != expected_capture_outcomes[outcome["exit_code"]]:
        raise EvidenceError("EvidenceOutcomeMismatch", "capture status fields disagree with the exit code")
    if outcome["exit_code"] == 2 and (
        outcome["shutdown_status"] != "completed"
        or outcome["data_usability"] not in {"record_only", "unusable"}
    ):
        raise EvidenceError("EvidenceOutcomeMismatch", "exit two must be completed non-strict evidence")
    if outcome["furthest_eligible_stage"] == "backtest_v4":
        if any(item["status"] != "reviewed" for item in payload["product_lineage"]):
            raise EvidenceError(
                "EvidenceProductLineageMismatch", "backtest-v4 evidence requires reviewed lineage for every market"
            )
        missing = STRICT_CHAIN_ROLES - set(members)
        traces = [member for member in members.values() if member["role"].startswith("risk_trace_")]
        if missing or len(traces) != len(tickers):
            raise EvidenceError(
                "EvidenceMemberMissing", "backtest-v4 evidence requires the complete typed chain and one trace per market"
            )
    return payload, members


def _verify_raw_counts(path: Path, metadata: dict[str, Any]) -> None:
    by_type: Counter[str] = Counter()
    by_market: dict[str, Counter[str]] = {}
    count = 0
    for row in phase7.iter_jsonl(path):
        count += 1
        if row.get("raw_ingress_ordinal") != count:
            raise EvidenceError("EvidenceCountMismatch", "raw ingress ordinals are not contiguous")
        if row.get("kind") != "inbound_frame":
            continue
        message_type = str(row.get("message_type"))
        by_type[message_type] += 1
        ticker = row.get("market_ticker")
        if isinstance(ticker, str):
            by_market.setdefault(ticker, Counter())[message_type] += 1
    if metadata.get("raw_record_count") != count:
        raise EvidenceError("EvidenceCountMismatch", "raw_record_count differs from frames JSONL")
    if dict(sorted(by_type.items())) != metadata.get("message_counts_by_type"):
        raise EvidenceError("EvidenceCountMismatch", "message_counts_by_type differs from raw frames")
    actual_market = {ticker: dict(sorted(counts.items())) for ticker, counts in sorted(by_market.items())}
    if actual_market != metadata.get("message_counts_by_market"):
        raise EvidenceError("EvidenceCountMismatch", "message_counts_by_market differs from raw frames")
    if metadata.get("credential_values_persisted") is not False:
        raise EvidenceError("EvidenceCredentialLeak", "raw metadata does not exclude credential values")


def _verify_normalization_counts(path: Path, manifest: dict[str, Any]) -> None:
    event_counts: Counter[str] = Counter()
    discontinuity_counts: Counter[str] = Counter()
    for record in phase7.iter_jsonl(path):
        if record.get("kind") == "market_event":
            event_counts[str(record.get("event_type"))] += 1
        elif record.get("kind") == "discontinuity":
            discontinuity_counts[str(record.get("control_type"))] += 1
    if dict(sorted(event_counts.items())) != manifest.get("event_counts"):
        raise EvidenceError("EvidenceCountMismatch", "normalization event counts differ from records")
    if dict(sorted(discontinuity_counts.items())) != manifest.get("discontinuity_counts"):
        raise EvidenceError("EvidenceCountMismatch", "normalization discontinuity counts differ from records")


def verify_evidence_manifest(
    manifest_path: Path, *, artifact_root: Path | None = None, require_artifacts: bool = False
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    document = phase7.read_json(manifest_path)
    payload, members = _validate_index(document)
    root = (manifest_path.parent if artifact_root is None else artifact_root).resolve()
    if not require_artifacts:
        return {
            "schema": EVIDENCE_SCHEMA,
            "evidence_id": payload["evidence_id"],
            "manifest_sha256": phase7.sha256_file(manifest_path),
            "member_count": len(members),
            "artifacts_verified": False,
            "verified": True,
        }

    loaded_json: dict[str, dict[str, Any]] = {}
    jsonl_counts: dict[str, int] = {}
    forbidden = (b"-----BEGIN PRIVATE KEY-----", b"-----BEGIN RSA PRIVATE KEY-----")
    for role, member in members.items():
        path = _safe_member(root, member["path"])
        if not path.is_file():
            raise EvidenceError("EvidenceMemberMissing", f"required member is missing: {role}")
        raw = path.read_bytes()
        if len(raw) != member["byte_length"] or _sha256_bytes(raw) != member["sha256"]:
            raise EvidenceError("EvidenceMemberHashMismatch", f"member bytes differ: {role}")
        if any(marker in raw for marker in forbidden):
            raise EvidenceError("EvidenceCredentialLeak", f"private-key material appears in {role}")
        if "record_count" in member:
            count = _count_jsonl(path, member.get("schema"))
            if count != member["record_count"]:
                raise EvidenceError("EvidenceCountMismatch", f"record count differs: {role}")
            jsonl_counts[role] = count
        elif member.get("schema") is not None:
            value = phase7.read_json(path)
            if value.get("schema") != member["schema"]:
                raise EvidenceError("EvidenceMemberSchemaMismatch", f"schema differs: {role}")
            loaded_json[role] = value

    declared_paths = {member["path"] for member in members.values()}
    actual_paths = {
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    try:
        manifest_relative = str(manifest_path.relative_to(root))
    except ValueError:
        manifest_relative = None
    allowed_paths = declared_paths | ({manifest_relative} if manifest_relative is not None else set())
    if actual_paths != allowed_paths:
        raise EvidenceError("EvidenceMembershipMismatch", "mounted package membership differs from the index")

    if "raw_frames" in jsonl_counts and "raw_metadata" in loaded_json:
        _verify_raw_counts(_safe_member(root, members["raw_frames"]["path"]), loaded_json["raw_metadata"])
    if "normalized_records" in jsonl_counts and "normalization_manifest" in loaded_json:
        _verify_normalization_counts(
            _safe_member(root, members["normalized_records"]["path"]),
            loaded_json["normalization_manifest"],
        )
        normalized = loaded_json["normalization_manifest"]
        expected = {
            "input_frames_sha256": members["raw_frames"]["sha256"],
            "input_capture_metadata_sha256": members["raw_metadata"]["sha256"],
            "output_records_sha256": members["normalized_records"]["sha256"],
            "output_source_scopes_sha256": members["source_scopes"]["sha256"],
            "output_product_sha256": members["product_map"]["sha256"],
        }
        if any(normalized.get(name) != value for name, value in expected.items()):
            raise EvidenceError("EvidenceLineageMismatch", "normalization member lineage differs")
    if "feature_rows" in jsonl_counts and "feature_manifest" in loaded_json:
        feature_manifest = loaded_json["feature_manifest"]
        feature_count = jsonl_counts["feature_rows"]
        if feature_manifest.get("output", {}).get("feature_row_count") != feature_count:
            raise EvidenceError("EvidenceCountMismatch", "feature row count differs from feature manifest")
        if sum(item.get("row_count", 0) for item in feature_manifest.get("products", [])) != feature_count:
            raise EvidenceError("EvidenceCountMismatch", "per-product feature counts do not sum")
        expected_feature_inputs = {
            "normalization_manifest_sha256": members["normalization_manifest"]["sha256"],
            "records_sha256": members["normalized_records"]["sha256"],
            "source_scopes_sha256": members["source_scopes"]["sha256"],
            "product_map_sha256": members["product_map"]["sha256"],
        }
        if any(feature_manifest.get("input", {}).get(name) != value for name, value in expected_feature_inputs.items()):
            raise EvidenceError("EvidenceLineageMismatch", "feature input lineage differs")
        if feature_manifest.get("output", {}).get("feature_rows_sha256") != members["feature_rows"]["sha256"]:
            raise EvidenceError("EvidenceLineageMismatch", "feature output lineage differs")
    if payload["capture_outcome"]["furthest_eligible_stage"] == "backtest_v4":
        result = loaded_json.get("result_manifest")
        if result is None or {f"v4_{item['name']}" for item in result.get("artifacts", [])} != V4_ARTIFACT_ROLES:
            raise EvidenceError("EvidenceResultMismatch", "Result V4 typed artifact membership differs")
        if result.get("config_sha256") != members["backtest_config"]["sha256"]:
            raise EvidenceError("EvidenceLineageMismatch", "Result V4 configuration identity differs")
        for descriptor in result["artifacts"]:
            role = f"v4_{descriptor['name']}"
            member = members[role]
            if (
                descriptor.get("path") != Path(member["path"]).name
                or descriptor.get("schema") != member.get("schema")
                or descriptor.get("sha256") != member["sha256"]
                or descriptor.get("row_count") != member.get("record_count")
            ):
                raise EvidenceError("EvidenceResultMismatch", f"Result V4 descriptor differs: {role}")
        traces = result.get("risk", {}).get("traces", [])
        if len(traces) != len(payload["market_tickers"]):
            raise EvidenceError("EvidenceResultMismatch", "Result V4 trace cardinality differs")
        for trace in traces:
            role = f"risk_trace_{trace['contract_id']}"
            member = members.get(role)
            if (
                member is None
                or trace.get("path") != Path(member["path"]).name
                or member.get("schema") != phase7.RISK_TRACE_SCHEMA
                or trace.get("sha256") != member["sha256"]
                or trace.get("row_count") != member.get("record_count")
            ):
                raise EvidenceError("EvidenceResultMismatch", f"Result V4 trace descriptor differs: {role}")
    return {
        "schema": EVIDENCE_SCHEMA,
        "evidence_id": payload["evidence_id"],
        "manifest_sha256": phase7.sha256_file(manifest_path),
        "member_count": len(members),
        "artifacts_verified": True,
        "verified": True,
    }


def _path_bytes(paths: Iterable[Path]) -> int:
    total = 0
    for path in paths:
        if path.is_file() and not path.is_symlink():
            total += path.stat().st_size
        elif path.is_dir() and not path.is_symlink():
            total += sum(item.stat().st_size for item in path.rglob("*") if item.is_file() and not item.is_symlink())
    return total


def _process_tree_usage(root_pid: int) -> tuple[int, int]:
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,rss="], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return 0, 0
    rows: dict[int, tuple[int, int]] = {}
    for line in result.stdout.splitlines():
        values = line.split()
        if len(values) == 3:
            rows[int(values[0])] = (int(values[1]), int(values[2]))
    selected = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, (parent, _) in rows.items():
            if parent in selected and pid not in selected:
                selected.add(pid)
                changed = True
    rss = sum(rows.get(pid, (0, 0))[1] for pid in selected)
    return len(selected & rows.keys()), rss


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _scrub_credentials(value: bytes) -> bytes:
    result = value
    for name in ("KALSHI_API_KEY_ID", "KALSHI_PRIVATE_KEY_PATH"):
        secret = os.environ.get(name)
        if secret:
            result = result.replace(secret.encode("utf-8"), b"[REDACTED]")
    return result


def _git_context() -> dict[str, Any]:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=phase7.REPOSITORY_ROOT,
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--short"], cwd=phase7.REPOSITORY_ROOT,
        capture_output=True, text=True, check=False,
    ).stdout
    return {"revision": revision or None, "dirty": bool(status)}


def measure_command(
    *, stage: str, command: list[str], report_path: Path, input_paths: list[Path],
    output_paths: list[Path], identity_files: list[Path], sample_interval: float = 1.0,
    max_output_bytes: int | None = None,
) -> dict[str, Any]:
    if not stage or not command or sample_interval <= 0 or (
        max_output_bytes is not None and max_output_bytes <= 0
    ):
        raise EvidenceError("MeasurementConfigInvalid", "stage, command, and positive interval are required")
    report_path = report_path.resolve()
    if report_path.exists():
        raise EvidenceError("MeasurementOutputExists", f"report already exists: {report_path}")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    initial_output = _path_bytes(output_paths)
    input_bytes = _path_bytes(input_paths)
    started_at = _utc_now()
    started = time.monotonic()
    peak_processes = 0
    peak_rss = 0
    peak_output = initial_output
    budget_exceeded = False
    with tempfile.TemporaryDirectory(prefix="pmm-b2c-measure-") as temporary:
        stdout_path = Path(temporary) / "stdout"
        stderr_path = Path(temporary) / "stderr"
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr, start_new_session=True)
            while process.poll() is None:
                count, rss = _process_tree_usage(process.pid)
                peak_processes = max(peak_processes, count)
                peak_rss = max(peak_rss, rss)
                observed_output = _path_bytes(output_paths)
                peak_output = max(peak_output, observed_output)
                if (
                    max_output_bytes is not None
                    and observed_output > max_output_bytes
                    and not budget_exceeded
                ):
                    budget_exceeded = True
                    os.killpg(process.pid, signal.SIGINT)
                time.sleep(sample_interval)
            exit_code = process.returncode
        stdout_bytes = stdout_path.read_bytes()
        stderr_bytes = stderr_path.read_bytes()
    final_output = _path_bytes(output_paths)
    report = {
        "schema": MEASUREMENT_SCHEMA,
        "stage": stage,
        "command_sha256": _payload_sha256(
            [_scrub_credentials(item.encode("utf-8")).decode("utf-8") for item in command]
        ),
        "started_at_utc": started_at,
        "finished_at_utc": _utc_now(),
        "wall_time_seconds": time.monotonic() - started,
        "exit_code": exit_code,
        "stdout_sha256": _sha256_bytes(_scrub_credentials(stdout_bytes)),
        "stderr_sha256": _sha256_bytes(_scrub_credentials(stderr_bytes)),
        "resources": {
            "sample_interval_seconds": sample_interval,
            "output_budget_bytes": max_output_bytes,
            "output_budget_exceeded": budget_exceeded,
            "termination_reason": "output_budget_exceeded" if budget_exceeded else "completed",
            "peak_process_count": peak_processes,
            "peak_rss_kib": peak_rss,
            "input_bytes": input_bytes,
            "initial_output_bytes": initial_output,
            "peak_output_bytes": max(peak_output, final_output),
            "final_output_bytes": final_output,
        },
        "machine": {
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
            "git": _git_context(),
        },
        "inputs": [str(path.resolve()) for path in input_paths],
        "outputs": [str(path.resolve()) for path in output_paths],
        "identity_files": [
            {"path": str(path.resolve()), "sha256": phase7.sha256_file(path.resolve())}
            for path in identity_files
        ],
    }
    phase7.validate_historical_schema(
        report, "b2c-measurement-v1.schema.json", "MeasurementSchemaMismatch"
    )
    temporary_report = report_path.with_name(f"{report_path.name}.partial")
    if temporary_report.exists():
        raise EvidenceError("MeasurementOutputExists", f"partial report already exists: {temporary_report}")
    try:
        phase7.write_json(temporary_report, report)
        temporary_report.rename(report_path)
    except BaseException:
        temporary_report.unlink(missing_ok=True)
        raise
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline B2c evidence and measurement utilities.")
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify", help="Verify a B2c evidence index or mounted package.")
    verify.add_argument("--manifest", required=True, type=Path)
    verify.add_argument("--artifact-root", type=Path)
    verify.add_argument("--require-artifacts", action="store_true")
    verify_v2 = commands.add_parser("verify-v2", help="Verify a mounted B2c V2 evidence package.")
    verify_v2.add_argument("--manifest", required=True, type=Path)
    verify_v2.add_argument("--artifact-root", type=Path)
    verify_v2.add_argument("--require-artifacts", action="store_true")
    measure = commands.add_parser("measure", help="Measure one unchanged offline command.")
    measure.add_argument("--stage", required=True)
    measure.add_argument("--report", required=True, type=Path)
    measure.add_argument("--input", action="append", default=[], type=Path)
    measure.add_argument("--output", action="append", default=[], type=Path)
    measure.add_argument("--identity-file", action="append", default=[], type=Path)
    measure.add_argument("--sample-interval", type=float, default=1.0)
    measure.add_argument("--max-output-bytes", type=int)
    measure.add_argument("command_argv", nargs=argparse.REMAINDER)
    measure_v2 = commands.add_parser("measure-v2", help="Supervise an offline command with B2c Measurement V2.")
    measure_v2.add_argument("--stage", required=True)
    measure_v2.add_argument("--report", required=True, type=Path)
    measure_v2.add_argument("--package-root", required=True, type=Path)
    measure_v2.add_argument("--raw-root", required=True, action="append", type=Path)
    measure_v2.add_argument("--output-root", required=True, action="append", type=Path)
    measure_v2.add_argument("--identity-file", action="append", default=[], type=Path)
    measure_v2.add_argument("--policy", type=Path)
    measure_v2.add_argument("command_argv", nargs=argparse.REMAINDER)
    return parser


def _measurement_controls_from_policy(path: Path | None) -> measurement_v2.MeasurementControls:
    if path is None:
        return measurement_v2.V2_CONTROLS
    document = phase7.read_json(path)
    phase7.validate_historical_schema(
        document, "b2c-evidence-policy-v2.schema.json", "MeasurementPolicyV2SchemaMismatch"
    )
    values = document["measurement"]
    return measurement_v2.MeasurementControls(
        sample_interval_seconds=float(values["sample_interval_seconds"]),
        sigint_grace_seconds=float(values["sigint_grace_seconds"]),
        sigterm_grace_seconds=float(values["sigterm_grace_seconds"]),
        quiescence_grace_seconds=float(values["quiescence_grace_seconds"]),
        stream_limit_bytes=int(values["stream_limit_bytes"]),
        publication_reserve_bytes=int(values["publication_reserve_bytes"]),
    )


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.command == "verify":
            result = verify_evidence_manifest(
                args.manifest, artifact_root=args.artifact_root,
                require_artifacts=args.require_artifacts,
            )
        elif args.command == "verify-v2":
            result = verify_evidence_manifest_v2(
                args.manifest, artifact_root=args.artifact_root,
                require_artifacts=args.require_artifacts,
            )
        elif args.command == "measure-v2":
            command = list(args.command_argv)
            if command and command[0] == "--":
                command = command[1:]
            measured = measurement_v2.run_measurement_v2(
                stage=args.stage, command=command, report_path=args.report,
                package_root=args.package_root, raw_roots=args.raw_root,
                output_roots=args.output_root, identity_files=args.identity_file,
                controls=_measurement_controls_from_policy(args.policy),
            )
            if measured.exit_status == 0:
                print(json.dumps(measured.report, indent=2, sort_keys=True))
            else:
                detail = f"error: {measured.diagnostic_code}"
                if measured.report_published:
                    detail += f": report={measured.report_path}"
                print(detail, file=sys.stderr)
            return measured.exit_status
        else:
            command = list(args.command_argv)
            if command and command[0] == "--":
                command = command[1:]
            result = measure_command(
                stage=args.stage, command=command, report_path=args.report,
                input_paths=args.input, output_paths=args.output,
                identity_files=args.identity_file, sample_interval=args.sample_interval,
                max_output_bytes=args.max_output_bytes,
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except KeyboardInterrupt:
        print("error: interrupted", file=sys.stderr)
        return 130
    except (EvidenceError, phase7.HistoricalDataError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"programming failure: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
