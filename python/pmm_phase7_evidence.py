#!/usr/bin/env python3
"""Offline B2c evidence verification and process-tree measurement.

This module is additive. It does not capture venue data and does not alter accepted
Capture V2, normalization V3, feature V3, Backtest V4, or Result V4 formats.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterable

try:
    from . import pmm_phase7 as phase7
except ImportError:
    python_root = str(Path(__file__).resolve().parent)
    if python_root not in sys.path:
        sys.path.insert(0, python_root)
    import pmm_phase7 as phase7  # type: ignore[no-redef]


EVIDENCE_SCHEMA = "pmm.phase7.b2c_evidence_manifest.v1"
MEASUREMENT_SCHEMA = "pmm.phase7.b2c_measurement.v1"
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
    measure = commands.add_parser("measure", help="Measure one unchanged offline command.")
    measure.add_argument("--stage", required=True)
    measure.add_argument("--report", required=True, type=Path)
    measure.add_argument("--input", action="append", default=[], type=Path)
    measure.add_argument("--output", action="append", default=[], type=Path)
    measure.add_argument("--identity-file", action="append", default=[], type=Path)
    measure.add_argument("--sample-interval", type=float, default=1.0)
    measure.add_argument("--max-output-bytes", type=int)
    measure.add_argument("command_argv", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.command == "verify":
            result = verify_evidence_manifest(
                args.manifest, artifact_root=args.artifact_root,
                require_artifacts=args.require_artifacts,
            )
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
