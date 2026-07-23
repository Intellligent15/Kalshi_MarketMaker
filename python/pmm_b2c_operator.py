#!/usr/bin/env python3
"""Offline verification for B2c-P candidate selection and run authorization."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path
from typing import Any

try:
    from . import pmm_phase7 as phase7
except ImportError:
    import pmm_phase7 as phase7  # type: ignore[no-redef]


CANDIDATE_SNAPSHOT_SCHEMA = "pmm.phase7.b2c_candidate_snapshot.v1"
RUN_APPROVAL_SCHEMA = "pmm.phase7.b2c_run_approval.v1"
_CANDIDATE_FIELDS = (
    "ticker",
    "event_ticker",
    "series_ticker",
    "contract_kind",
    "status",
    "close_time_utc",
    "volume_24h_fp",
)


class OperatorError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def payload_sha256(value: Any) -> str:
    return hashlib.sha256(phase7.canonical_json(value).encode("utf-8")).hexdigest()


def _utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise OperatorError("B2cOperatorTimeInvalid", "timestamp is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OperatorError("B2cOperatorTimeInvalid", "timestamp lacks an offset")
    return parsed.astimezone(timezone.utc)


def _load(path: Path, schema_file: str, schema_tag: str) -> dict[str, Any]:
    try:
        document = phase7.read_json(path)
        phase7.validate_historical_schema(document, schema_file, "B2cOperatorSchemaMismatch")
    except ValueError as error:
        raise OperatorError("B2cOperatorSchemaMismatch", "control document is invalid") from error
    if document.get("schema") != schema_tag or document.get("payload_sha256") != payload_sha256(
        document["payload"]
    ):
        raise OperatorError("B2cOperatorHashMismatch", "control payload hash is stale")
    return document


def _member(root: Path, relative: str, *, code: str, label: str) -> Path:
    value = Path(relative)
    if value.is_absolute() or ".." in value.parts or "\\" in relative:
        raise OperatorError(code, f"{label} path is unsafe")
    path = root / value
    current = root
    for part in value.parts:
        current /= part
        if current.is_symlink():
            raise OperatorError(code, f"{label} path is a symlink")
    try:
        path.resolve(strict=False).relative_to(root)
    except ValueError as error:
        raise OperatorError(code, f"{label} escapes artifact root") from error
    return path


def _cursor(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise OperatorError(
            "CandidateSnapshotPaginationMismatch", "page cursor is not a non-empty string"
        )
    return value


def _project_market(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or any(field not in value for field in _CANDIDATE_FIELDS):
        raise OperatorError(
            "CandidateSnapshotPageMismatch", "retained page has a malformed market row"
        )
    return {field: value[field] for field in _CANDIDATE_FIELDS}


def _storage_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise OperatorError("RunApprovalStorageMismatch", "durable paths must be absolute")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            raise OperatorError("RunApprovalStorageMismatch", "durable path uses a symlink")
    return path.resolve(strict=False)


def verify_candidate_snapshot(path: Path, *, artifact_root: Path | None = None) -> dict[str, Any]:
    document = _load(
        path, "b2c-candidate-snapshot-v1.schema.json", CANDIDATE_SNAPSHOT_SCHEMA
    )
    payload = document["payload"]
    root = (path.parent if artifact_root is None else artifact_root).resolve()
    retrieval_start = _utc(payload["retrieval_started_at_utc"])
    retrieval_end = _utc(payload["retrieval_completed_at_utc"])
    if retrieval_end < retrieval_start:
        raise OperatorError("CandidateSnapshotTimeInvalid", "retrieval completion precedes start")
    query = payload["query"]
    if (
        query["endpoint"] != "/trade-api/v2/markets"
        or query["parameters"].get("status") != "open"
    ):
        raise OperatorError(
            "CandidateSnapshotQueryMismatch", "candidate query must list open production markets"
        )
    pages = payload["pages"]
    if _cursor(pages[0]["cursor_in"]) is not None:
        raise OperatorError("CandidateSnapshotPaginationMismatch", "first cursor must be null")
    if _cursor(pages[-1]["cursor_out"]) is not None:
        raise OperatorError("CandidateSnapshotPaginationMismatch", "final cursor must be null")
    retained_candidates: list[dict[str, Any]] = []
    retained_tickers: set[str] = set()
    page_members: set[Path] = set()
    for index, page in enumerate(pages):
        cursor_in = _cursor(page["cursor_in"])
        cursor_out = _cursor(page["cursor_out"])
        if index and cursor_in != _cursor(pages[index - 1]["cursor_out"]):
            raise OperatorError("CandidateSnapshotPaginationMismatch", "cursor chain is incomplete")
        if index < len(pages) - 1 and cursor_out is None:
            raise OperatorError(
                "CandidateSnapshotPaginationMismatch", "cursor chain ends before the final page"
            )
        member = _member(
            root,
            page["path"],
            code="CandidateSnapshotPageMismatch",
            label="page",
        )
        resolved_member = member.resolve(strict=False)
        if resolved_member in page_members:
            raise OperatorError("CandidateSnapshotPageMismatch", "page path is duplicated")
        page_members.add(resolved_member)
        if not member.is_file() or phase7.sha256_file(member) != page["sha256"]:
            raise OperatorError("CandidateSnapshotPageMismatch", "retained page differs")
        try:
            retained_page = phase7.read_json(member)
        except (OSError, ValueError) as error:
            raise OperatorError(
                "CandidateSnapshotPageMismatch", "retained page is not a JSON object"
            ) from error
        markets = retained_page.get("markets")
        if not isinstance(markets, list):
            raise OperatorError(
                "CandidateSnapshotPageMismatch", "retained page lacks a market list"
            )
        if "cursor" not in retained_page:
            raise OperatorError(
                "CandidateSnapshotPaginationMismatch", "retained page lacks a cursor"
            )
        if _cursor(retained_page.get("cursor")) != cursor_out:
            raise OperatorError(
                "CandidateSnapshotPaginationMismatch", "retained cursor differs from page record"
            )
        for market in markets:
            candidate = _project_market(market)
            ticker = candidate["ticker"]
            if not isinstance(ticker, str) or not ticker or ticker in retained_tickers:
                raise OperatorError(
                    "CandidateSnapshotPageMismatch", "retained market ticker is invalid or duplicated"
                )
            retained_tickers.add(ticker)
            retained_candidates.append(candidate)
    window = payload["capture_window"]
    start, end = _utc(window["started_at_utc"]), _utc(window["ended_at_utc"])
    if retrieval_end >= start:
        raise OperatorError(
            "CandidateSnapshotTimeInvalid", "retrieval must complete before capture starts"
        )
    if int((end - start).total_seconds()) != 43_200:
        raise OperatorError("CandidateSelectionMismatch", "capture window is not twelve hours")
    close_floor = end + timedelta(seconds=window["closing_margin_seconds"])
    declared_candidates: dict[str, dict[str, Any]] = {}
    for candidate in payload["candidates"]:
        ticker = candidate["ticker"]
        if ticker in declared_candidates:
            raise OperatorError("CandidateSnapshotPageMismatch", "candidate ticker is duplicated")
        declared_candidates[ticker] = candidate
    reconstructed_candidates = {
        candidate["ticker"]: candidate for candidate in retained_candidates
    }
    if declared_candidates != reconstructed_candidates:
        raise OperatorError(
            "CandidateSnapshotPageMismatch", "candidate projection differs from retained pages"
        )
    eligible: list[tuple[Decimal, str, str]] = []
    for candidate in retained_candidates:
        ticker = candidate["ticker"]
        try:
            activity = Decimal(candidate["volume_24h_fp"])
        except (InvalidOperation, TypeError) as error:
            raise OperatorError("CandidateSelectionMismatch", "activity is invalid") from error
        if activity < 0 or _utc(candidate["close_time_utc"]) < close_floor:
            continue
        eligible.append((activity, ticker, candidate["series_ticker"]))
    eligible.sort(key=lambda item: (-item[0], item[1]))
    selected: list[str] = []
    series: set[str] = set()
    for _, ticker, series_ticker in eligible:
        if series_ticker in series:
            continue
        selected.append(ticker)
        series.add(series_ticker)
        if len(selected) == 3:
            break
    if len(selected) != 3 or selected != payload["selected_market_tickers"]:
        raise OperatorError("CandidateSelectionMismatch", "selected markets differ from reconstruction")
    return {
        "schema": CANDIDATE_SNAPSHOT_SCHEMA,
        "verified": True,
        "selected_market_tickers": selected,
        "capture_window": {
            "started_at_utc": window["started_at_utc"],
            "ended_at_utc": window["ended_at_utc"],
        },
        "retrieval_started_at_utc": payload["retrieval_started_at_utc"],
        "retrieval_completed_at_utc": payload["retrieval_completed_at_utc"],
    }


def verify_run_approval(
    path: Path, *, candidate_snapshot_path: Path, artifact_root: Path | None = None
) -> dict[str, Any]:
    document = _load(path, "b2c-run-approval-v1.schema.json", RUN_APPROVAL_SCHEMA)
    payload = document["payload"]
    snapshot = verify_candidate_snapshot(candidate_snapshot_path, artifact_root=artifact_root)
    if payload["candidate_snapshot_sha256"] != phase7.sha256_file(candidate_snapshot_path):
        raise OperatorError("RunApprovalSnapshotMismatch", "approval names another snapshot")
    frozen_policy = phase7.REPOSITORY_ROOT / "configs/phase7/b2c_evidence_policy_v1.json"
    if payload["policy_sha256"] != phase7.sha256_file(frozen_policy):
        raise OperatorError("RunApprovalPolicyMismatch", "approval names another policy")
    if payload["selected_market_tickers"] != snapshot["selected_market_tickers"]:
        raise OperatorError("RunApprovalSelectionMismatch", "approval selection differs")
    start = _utc(payload["capture_window"]["started_at_utc"])
    end = _utc(payload["capture_window"]["ended_at_utc"])
    if int((end - start).total_seconds()) != 43_200:
        raise OperatorError("RunApprovalWindowMismatch", "approval window is not twelve hours")
    if payload["capture_window"] != snapshot["capture_window"]:
        raise OperatorError("RunApprovalWindowMismatch", "approval window differs from selection")
    specs = payload["acquisition_specs"]
    if [item["ticker"] for item in specs] != payload["selected_market_tickers"]:
        raise OperatorError("RunApprovalAcquisitionMismatch", "acquisition specs differ")
    root = (path.parent if artifact_root is None else artifact_root).resolve()
    spec_members: set[Path] = set()
    for item in specs:
        for observation in ("opening", "closing"):
            member = _member(
                root,
                item[f"{observation}_path"],
                code="RunApprovalAcquisitionMismatch",
                label=f"{observation} acquisition spec",
            )
            resolved_member = member.resolve(strict=False)
            if resolved_member in spec_members:
                raise OperatorError(
                    "RunApprovalAcquisitionMismatch", "acquisition spec path is duplicated"
                )
            spec_members.add(resolved_member)
            if (
                not member.is_file()
                or phase7.sha256_file(member) != item[f"{observation}_sha256"]
            ):
                raise OperatorError(
                    "RunApprovalAcquisitionMismatch", "acquisition spec bytes differ"
                )
    approved_at = _utc(payload["approved_at_utc"])
    retrieval_completed = _utc(snapshot["retrieval_completed_at_utc"])
    if approved_at < retrieval_completed or approved_at >= start:
        raise OperatorError(
            "RunApprovalTimeInvalid",
            "approval must follow retrieval and precede capture",
        )
    storage = payload["storage"]
    primary = _storage_path(storage["primary_path"])
    backup = _storage_path(storage["backup_path"])
    if primary == backup:
        raise OperatorError("RunApprovalStorageMismatch", "durable paths must be distinct")
    if primary in backup.parents or backup in primary.parents:
        raise OperatorError("RunApprovalStorageMismatch", "durable paths must not overlap")
    if storage["owner"] not in storage["readers"]:
        raise OperatorError("RunApprovalStorageMismatch", "storage owner must retain read access")
    return {"schema": RUN_APPROVAL_SCHEMA, "verified": True, "approved": True}
