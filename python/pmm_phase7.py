#!/usr/bin/env python3
"""Deterministic Phase 7 normalization, observed-market replay, features, and backtesting.

This module treats captured Level-2 data as observed market truth.  It never calls the C++
exchange or order book and labels all simulated orders and fills as model-derived.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Iterable

from jsonschema import Draft202012Validator

try:
    from .pmm_product_terms import (
        ConversionPolicy,
        ProductCatalog,
        ProductPackage,
        ProductTermsError,
        copy_package,
        sha256_file as product_sha256_file,
    )
except ImportError:
    python_root = str(Path(__file__).resolve().parent)
    if python_root not in sys.path:
        sys.path.insert(0, python_root)
    from pmm_product_terms import (  # type: ignore[no-redef]
        ConversionPolicy,
        ProductCatalog,
        ProductPackage,
        ProductTermsError,
        copy_package,
        sha256_file as product_sha256_file,
    )


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_SCHEMA_ROOT = REPOSITORY_ROOT / "schemas" / "historical"
NORMALIZED_SCHEMA = "pmm.historical.normalized_event.v1"
NORMALIZED_RECORD_V2_SCHEMA = "pmm.historical.normalized_record.v2"
NORMALIZATION_MANIFEST_V3_SCHEMA = "pmm.historical.normalization_manifest.v3"
PRODUCT_MAP_V3_SCHEMA = "pmm.historical.product_map.v3"
SOURCE_SCOPE_MAP_SCHEMA = "pmm.historical.source_scope_map.v1"
RAW_CAPTURE_V2_SCHEMA = "pmm.kalshi.raw_capture.v2"
RAW_CAPTURE_RECORD_V2_SCHEMA = "pmm.kalshi.raw_capture_record.v2"
NORMALIZER_VERSION = "kalshi-l2-normalizer.v1"
NORMALIZER_V2_VERSION = "kalshi-multi-scope-normalizer.v2"
FEATURE_SCHEMA = "pmm.historical.feature_row.v1"
FEATURE_VERSION = "observed-l2-top-of-book.v1"
FEATURE_ROW_V2_SCHEMA = "pmm.historical.feature_row.v2"
FEATURE_MANIFEST_V3_SCHEMA = "pmm.historical.feature_manifest.v3"
FEATURE_V2_VERSION = "observed-l2-per-market-segment.v2"
BACKTEST_SCHEMA = "pmm.backtest.v1"
BACKTEST_V2_SCHEMA = "pmm.backtest.v2"
BACKTEST_V3_SCHEMA = "pmm.backtest.v3"
BACKTEST_V4_SCHEMA = "pmm.backtest.v4"
RISK_TRACE_SCHEMA = "pmm.risk_conformance_trace.v2"


class HistoricalDataError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def validate_historical_schema(document: dict[str, Any], filename: str, code: str) -> None:
    schema = read_json(HISTORICAL_SCHEMA_ROOT / filename)
    errors = sorted(Draft202012Validator(schema).iter_errors(document), key=lambda item: list(item.path))
    if errors:
        location = ".".join(str(part) for part in errors[0].absolute_path) or "document"
        raise HistoricalDataError(code, f"{filename} rejects {location}: {errors[0].message}")


def canonical_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def ensure_new_output(path: Path) -> Path:
    output = path.resolve()
    try:
        output.relative_to(REPOSITORY_ROOT)
    except ValueError as error:
        raise ValueError("output must be inside the repository") from error
    if output.exists():
        raise ValueError(f"output already exists: {output}")
    return output


def decimal_string(value: Any, *, field_name: str, minimum: Decimal | None = None,
                   maximum: Decimal | None = None, allow_negative: bool = False) -> str:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{field_name} is not a decimal") from error
    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if not allow_negative and parsed < 0:
        raise ValueError(f"{field_name} must not be negative")
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{field_name} is below its valid range")
    if maximum is not None and parsed > maximum:
        raise ValueError(f"{field_name} is above its valid range")
    return format(parsed, "f")


def int_value(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be an integer") from error


def parse_raw_message(record: dict[str, Any], line_number: int) -> tuple[str, dict[str, Any]]:
    raw = record.get("raw_frame_utf8")
    if not isinstance(raw, str):
        raise ValueError(f"raw record {line_number} has no raw_frame_utf8")
    try:
        message = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"raw record {line_number} has invalid JSON payload") from error
    if not isinstance(message, dict) or not isinstance(message.get("msg"), dict):
        raise ValueError(f"raw record {line_number} has an unsupported WebSocket message")
    message_type = message.get("type")
    if message_type not in {"orderbook_snapshot", "orderbook_delta", "trade"}:
        raise ValueError(f"raw record {line_number} has unsupported message type {message_type!r}")
    return str(message_type), message


def normalize_levels(levels: Any, field_name: str) -> list[dict[str, str]]:
    if not isinstance(levels, list):
        raise ValueError(f"{field_name} must be a list")
    result: list[dict[str, str]] = []
    seen_prices: set[str] = set()
    for index, level in enumerate(levels):
        if not isinstance(level, list) or len(level) != 2:
            raise ValueError(f"{field_name}[{index}] must be [price, quantity]")
        price = decimal_string(level[0], field_name=f"{field_name}[{index}].price",
                               minimum=Decimal("0"), maximum=Decimal("1"))
        quantity = decimal_string(level[1], field_name=f"{field_name}[{index}].quantity")
        if price in seen_prices:
            raise ValueError(f"{field_name}[{index}] repeats a price level")
        seen_prices.add(price)
        result.append({"price_dollars": price, "quantity_contracts": quantity})
    return result


@dataclass
class SequenceValidation:
    previous: dict[tuple[int, str], int] = field(default_factory=dict)
    gaps: list[dict[str, Any]] = field(default_factory=list)

    def observe(self, connection_id: int, sid: Any, sequence: Any) -> None:
        if sequence is None:
            return
        current = int_value(sequence, "source sequence")
        key = (connection_id, str(sid))
        prior = self.previous.get(key)
        if prior is not None and current > prior + 1:
            self.gaps.append(
                {
                    "connection_id": connection_id,
                    "subscription_id": str(sid),
                    "expected_sequence": prior + 1,
                    "received_sequence": current,
                }
            )
        if prior is not None and current < prior:
            raise ValueError("source sequence moves backwards")
        self.previous[key] = max(prior, current) if prior is not None else current


def normalized_payload(message_type: str, message: dict[str, Any]) -> tuple[str, str | None, dict[str, Any]]:
    payload = message["msg"]
    ticker = payload.get("market_ticker")
    market_id = payload.get("market_id")
    if not isinstance(ticker, str) or not ticker:
        raise ValueError("market_ticker is required")
    if market_id is not None and (not isinstance(market_id, str) or not market_id):
        raise ValueError("market_id must be a non-empty string when present")
    if message_type == "orderbook_snapshot":
        return ticker, market_id, {
            "yes_bids": normalize_levels(payload.get("yes_dollars_fp"), "yes_dollars_fp"),
            "yes_asks": normalize_levels(payload.get("no_dollars_fp"), "no_dollars_fp"),
        }
    if message_type == "orderbook_delta":
        side = payload.get("side")
        if side not in {"yes", "no"}:
            raise ValueError("orderbook_delta side must be yes or no")
        return ticker, market_id, {
            "book_side": side,
            "price_dollars": decimal_string(payload.get("price_dollars"), field_name="price_dollars",
                                             minimum=Decimal("0"), maximum=Decimal("1")),
            "quantity_delta_contracts": decimal_string(
                payload.get("delta_fp"), field_name="delta_fp", allow_negative=True
            ),
        }
    return ticker, market_id, {
        "trade_id": str(payload.get("trade_id", "")),
        "yes_price_dollars": decimal_string(payload.get("yes_price_dollars"),
                                             field_name="yes_price_dollars",
                                             minimum=Decimal("0"), maximum=Decimal("1")),
        "no_price_dollars": decimal_string(payload.get("no_price_dollars"),
                                            field_name="no_price_dollars",
                                            minimum=Decimal("0"), maximum=Decimal("1")),
        "quantity_contracts": decimal_string(payload.get("count_fp"), field_name="count_fp"),
        "taker_side": payload.get("taker_side"),
        "taker_book_side": payload.get("taker_book_side"),
    }


def validate_product_payload(package: ProductPackage, payload: dict[str, Any], event_type: str) -> None:
    terms = package.terms
    if event_type == "orderbook_snapshot":
        for side in ("yes_bids", "yes_asks"):
            for index, level in enumerate(payload[side]):
                terms.validate_price(level["price_dollars"], f"{side}[{index}].price_dollars")
                terms.validate_quantity(level["quantity_contracts"], f"{side}[{index}].quantity_contracts")
    elif event_type == "orderbook_delta":
        terms.validate_price(payload["price_dollars"], "book_delta.price_dollars")
        terms.validate_quantity(payload["quantity_delta_contracts"], "book_delta.quantity_delta_contracts", allow_negative=True)
    else:
        yes_price = terms.validate_price(payload["yes_price_dollars"], "trade.yes_price_dollars")
        no_price = terms.validate_price(payload["no_price_dollars"], "trade.no_price_dollars")
        if yes_price + no_price != Decimal("1"):
            raise ProductTermsError(
                "ComplementaryPriceMismatch",
                "trade yes and no prices must sum exactly to one dollar",
            )
        terms.validate_quantity(payload["quantity_contracts"], "trade.quantity_contracts")


def normalize_capture(
    input_dir: Path,
    output_dir: Path,
    *,
    allow_sequence_gaps: bool = False,
    product_catalog: ProductCatalog | None = None,
    conversion_policy: ConversionPolicy | None = None,
) -> dict[str, Any]:
    input_dir = input_dir.resolve()
    frames = input_dir / "frames.jsonl"
    capture_metadata = input_dir / "metadata.json"
    if not frames.is_file() or not capture_metadata.is_file():
        raise ValueError("input must be a capture directory containing frames.jsonl and metadata.json")
    metadata = read_json(capture_metadata)
    ticker_from_metadata = metadata.get("ticker")
    if not isinstance(ticker_from_metadata, str) or not ticker_from_metadata:
        raise ValueError("capture metadata does not identify a ticker")
    package: ProductPackage | None = None
    if (product_catalog is None) != (conversion_policy is None):
        raise ValueError("product catalog and conversion policy must be provided together")
    if product_catalog is not None:
        package = product_catalog.resolve(metadata)
        package.verify_capture(metadata)
    output_dir = ensure_new_output(output_dir)
    temporary = output_dir.with_name(f"{output_dir.name}.partial")
    if temporary.exists():
        raise ValueError(f"temporary normalization output already exists: {temporary}")
    temporary.mkdir(parents=True)
    event_counts: Counter[str] = Counter()
    sequence = SequenceValidation()
    duplicate_count = 0
    identities: dict[tuple[int, str, int], str] = {}
    market_id: str | None = None
    last_logical_time = -1
    late_source_events = 0
    ingress_order = 0
    product: dict[str, Any] | None = None
    events_path = temporary / "events.jsonl"
    try:
        with frames.open(encoding="utf-8") as source, events_path.open("x", encoding="utf-8") as destination:
            for line_number, line in enumerate(source, start=1):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"raw JSONL line {line_number} is corrupt") from error
                if not isinstance(record, dict) or record.get("kind") != "inbound_frame":
                    continue
                message_type = record.get("message_type")
                if message_type not in {"orderbook_snapshot", "orderbook_delta", "trade"}:
                    continue
                parsed_type, message = parse_raw_message(record, line_number)
                if parsed_type != message_type:
                    raise ValueError(f"raw record {line_number} message-type mismatch")
                ticker, parsed_market_id, payload = normalized_payload(parsed_type, message)
                if package is not None:
                    validate_product_payload(package, payload, parsed_type)
                if ticker != ticker_from_metadata:
                    raise ValueError(f"raw record {line_number} ticker conflicts with capture metadata")
                if market_id is None and parsed_market_id is None:
                    raise ValueError(f"raw record {line_number} has no market_id before identity is established")
                market_id_origin = "source_message" if parsed_market_id is not None else "capture_bound"
                if market_id is None:
                    assert parsed_market_id is not None
                    market_id = parsed_market_id
                    if package is None:
                        product = {
                            "schema": "pmm.historical.product_map.v1",
                            "venue": "kalshi",
                            "venue_market_id": market_id,
                            "ticker": ticker,
                            "price_unit": "yes_probability_dollars_fixed_point",
                            "quantity_unit": "contracts_fixed_point",
                            "timezone": "UTC",
                            "contract_metadata_status": "not_present_in_websocket_capture",
                            "source_fidelity": "level_2",
                        }
                    else:
                        assert conversion_policy is not None
                        identity = package.terms.identity
                        product = {
                            "schema": "pmm.historical.product_map.v2",
                            "venue": "kalshi",
                            "environment": "production",
                            "capture_identity": {
                                "ticker": ticker,
                                "venue_market_id": market_id,
                                "venue_market_id_authority": "capture_only_not_in_terms_source",
                            },
                            "authoritative_identity": {
                                "series_ticker": identity["series_ticker"],
                                "event_ticker": identity["event_ticker"],
                                "market_ticker": identity["market_ticker"],
                                "contracts": identity["contracts"],
                            },
                            "binding": {
                                "market_ticker_match": True,
                                "venue_market_id_consistent_within_capture": True,
                            },
                            "product_terms_sha256": package.terms.payload_sha256,
                            "source_manifest_sha256": package.evidence.payload_sha256,
                            "review_sha256": package.review.payload_sha256,
                            "conversion_policy_sha256": conversion_policy.payload_sha256,
                            "source_fidelity": "level_2",
                        }
                elif parsed_market_id is not None and market_id != parsed_market_id:
                    raise ValueError(f"raw record {line_number} market_id changes within a capture")
                connection_id = int_value(record.get("connection_id"), "connection_id")
                sid = record.get("subscription_id", message.get("sid"))
                source_sequence = record.get("source_sequence", message.get("seq"))
                sequence.observe(connection_id, sid, source_sequence)
                if source_sequence is not None:
                    identity = (connection_id, str(sid), int_value(source_sequence, "source sequence"))
                    payload_hash = hashlib.sha256(canonical_json(message).encode()).hexdigest()
                    prior = identities.get(identity)
                    if prior is not None:
                        if prior != payload_hash:
                            raise ValueError(f"conflicting duplicate source event at raw line {line_number}")
                        duplicate_count += 1
                        continue
                    identities[identity] = payload_hash
                received_at = int_value(record.get("received_at_utc_ns"), "received_at_utc_ns")
                source_ts_ms = message["msg"].get("ts_ms")
                source_time = None if source_ts_ms is None else int_value(source_ts_ms, "ts_ms") * 1_000_000
                event_time = source_time if source_time is not None else received_at
                source_time_late = source_time is not None and source_time < last_logical_time
                late_source_events += source_time_late
                logical_time = max(last_logical_time, event_time)
                last_logical_time = logical_time
                ingress_order += 1
                event = {
                    "schema": NORMALIZED_SCHEMA,
                    "normalizer_version": NORMALIZER_VERSION,
                    "event_id": f"{ticker}:{ingress_order}",
                    "ingress_order": ingress_order,
                    "logical_time_utc_ns": logical_time,
                    "event_time_utc_ns": event_time,
                    "event_time_basis": "source_ts_ms" if source_time is not None else "local_receive_time",
                    "source_time_late": source_time_late,
                    "local_received_at_utc_ns": received_at,
                    "source_sequence": source_sequence,
                    "subscription_id": sid,
                    "connection_id": connection_id,
                    "raw_line_number": line_number,
                    "venue": "kalshi",
                    "ticker": ticker,
                    "venue_market_id": market_id,
                    "venue_market_id_provenance": market_id_origin,
                    "event_type": {
                        "orderbook_snapshot": "book_snapshot",
                        "orderbook_delta": "book_delta",
                        "trade": "trade",
                    }[parsed_type],
                    "truth_category": "Observed",
                    "source_fidelity": "level_2",
                    "payload": payload,
                }
                destination.write(canonical_json(event) + "\n")
                event_counts[event["event_type"]] += 1
        if sequence.gaps and not allow_sequence_gaps:
            raise ValueError("source sequence gaps found; normalization refuses incomplete input by default")
        if ingress_order == 0 or product is None:
            raise ValueError("capture contains no supported market-data events")
        write_json(temporary / "product.json", product)
        if package is not None:
            assert product_catalog is not None and conversion_policy is not None
            copy_package(package, temporary / "product_terms")
            shutil.copy2(conversion_policy.path, temporary / "conversion_policy.json")
        manifest = {
            "schema": "pmm.historical.normalization_manifest.v2" if package is not None else "pmm.historical.normalization_manifest.v1",
            "normalizer_version": NORMALIZER_VERSION,
            "input_capture_directory": str(input_dir.relative_to(REPOSITORY_ROOT)),
            "input_frames_sha256": sha256_file(frames),
            "input_capture_metadata_sha256": sha256_file(capture_metadata),
            "output_events_sha256": sha256_file(events_path),
            "ticker": ticker_from_metadata,
            "venue_market_id": market_id,
            "ordering_policy": "source_sequence within connection/subscription; raw ingress breaks ties; logical time is monotonic source time or receive time",
            "sequence_gap_policy": "rejected" if not allow_sequence_gaps else "recorded",
            "sequence_gaps": sequence.gaps,
            "late_source_events": late_source_events,
            "identical_duplicates_skipped": duplicate_count,
            "event_counts": dict(sorted(event_counts.items())),
            "truth_category": "Observed",
            "source_fidelity": "level_2",
            "limitations": [
                "Level-2 data has no individual order identity or queue position.",
                "Snapshot source time was absent and uses local receive time.",
                "Contract metadata was not present in the captured WebSocket messages.",
            ],
        }
        if package is not None:
            assert product_catalog is not None and conversion_policy is not None
            manifest.update({
                "output_product_sha256": sha256_file(temporary / "product.json"),
                "product_terms_file_sha256": sha256_file(temporary / "product_terms" / "product_terms.json"),
                "product_terms_sha256": package.terms.payload_sha256,
                "source_manifest_sha256": package.evidence.payload_sha256,
                "review_sha256": package.review.payload_sha256,
                "conversion_policy_file_sha256": sha256_file(temporary / "conversion_policy.json"),
                "conversion_policy_sha256": conversion_policy.payload_sha256,
                "product_catalog_sha256": product_catalog.payload_sha256,
                "product_terms_effective_time_basis": package.review.payload["effective_time_basis"],
                "product_terms_review_limitations": package.review.payload["limitations"],
            })
        write_json(temporary / "manifest.json", manifest)
        temporary.rename(output_dir)
        return manifest
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def normalize_capture_v3(
    input_dir: Path,
    output_dir: Path,
    *,
    continuity_policy: str = "refuse",
    product_catalog: ProductCatalog | None = None,
    conversion_policy: ConversionPolicy | None = None,
) -> dict[str, Any]:
    if continuity_policy not in {"refuse", "record"}:
        raise HistoricalDataError(
            "ContinuityPolicyInvalid", "continuity policy must be 'refuse' or 'record'"
        )
    if (product_catalog is None) != (conversion_policy is None):
        raise HistoricalDataError(
            "ProductLineageIncomplete", "product catalog and conversion policy must be provided together"
        )
    input_dir = input_dir.resolve()
    frames = input_dir / "frames.jsonl"
    metadata_path = input_dir / "metadata.json"
    if not frames.is_file() or not metadata_path.is_file():
        raise HistoricalDataError(
            "CaptureInputMissing", "input must contain frames.jsonl and metadata.json"
        )
    metadata = read_json(metadata_path)
    if metadata.get("schema") != RAW_CAPTURE_V2_SCHEMA:
        raise HistoricalDataError("CaptureSchemaMismatch", "normalize-v3 requires raw capture V2")
    validate_historical_schema(metadata, "raw-capture-v2.schema.json", "CaptureSchemaMismatch")
    tickers_value = metadata.get("market_tickers")
    if (
        not isinstance(tickers_value, list)
        or not tickers_value
        or any(not isinstance(ticker, str) or not ticker for ticker in tickers_value)
        or tickers_value != sorted(set(tickers_value))
    ):
        raise HistoricalDataError(
            "CaptureIdentityInvalid", "market_tickers must be a sorted unique non-empty list"
        )
    tickers = tuple(tickers_value)
    sequence_domain = metadata.get("sequence_domain")
    if not isinstance(sequence_domain, dict) or sequence_domain.get("status") not in {
        "documented",
        "fixture_declared",
        "unknown",
    }:
        raise HistoricalDataError(
            "SequenceDomainMissing", "capture must represent sequence-domain status explicitly"
        )
    sequence_topology = sequence_domain.get("topology")
    if sequence_topology not in {"shared", "independent", "unknown"}:
        raise HistoricalDataError(
            "SequenceDomainMissing", "capture must declare shared, independent, or unknown topology"
        )
    if sequence_domain["status"] == "unknown" and sequence_topology != "unknown":
        raise HistoricalDataError(
            "SequenceDomainInvalid", "unknown sequence evidence must use unknown topology"
        )
    expected_sequence_key = ["connection_segment_id", "venue_subscription_id"]
    if sequence_topology == "independent":
        expected_sequence_key.append("market_ticker")
    if sequence_domain.get("mechanical_validation_key") != expected_sequence_key:
        raise HistoricalDataError(
            "SequenceDomainInvalid", "mechanical validation key does not match sequence topology"
        )
    source_truth = metadata.get("truth_category", "Observed")
    if source_truth not in {"Observed", "Synthetic"}:
        raise HistoricalDataError(
            "TruthCategoryInvalid", "raw capture truth must be Observed or Synthetic"
        )

    packages: dict[str, ProductPackage] = {}
    if product_catalog is not None:
        for ticker in tickers:
            ticker_metadata = dict(metadata)
            ticker_metadata["ticker"] = ticker
            package = product_catalog.resolve(ticker_metadata)
            package.verify_capture(ticker_metadata)
            packages[ticker] = package

    output_dir = ensure_new_output(output_dir)
    temporary = output_dir.with_name(f"{output_dir.name}.partial")
    if temporary.exists():
        raise HistoricalDataError(
            "PartialOutputExists", f"temporary normalization output already exists: {temporary}"
        )
    temporary.mkdir(parents=True)
    records_path = temporary / "records.jsonl"
    scope_path = temporary / "source_scopes.json"
    product_path = temporary / "product.json"
    manifest_path = temporary / "manifest.json"

    next_normalized_ordinal = 1
    last_raw_ordinal = 0
    last_logical_time = -1
    last_scope_time: dict[str, int] = {}
    requests: dict[int, dict[str, Any]] = {}
    scopes: dict[tuple[int, str], dict[str, Any]] = {}
    acknowledgements: dict[tuple[int, str], str] = {}
    logical_request_ids: set[str] = set()
    sequence_previous: dict[str, int] = {}
    sequence_payloads: dict[tuple[str, int], str] = {}
    market_ids: dict[str, str] = {}
    market_state = {
        ticker: {
            "segment": 0,
            "valid": False,
            "awaiting": "initial_snapshot",
            "ever_valid": False,
        }
        for ticker in tickers
    }
    snapshot_counts: Counter[tuple[int, str]] = Counter()
    event_counts: Counter[str] = Counter()
    discontinuity_counts: Counter[str] = Counter()
    identical_duplicates = 0
    late_source_events = 0
    has_discontinuity = False
    incomplete_reasons: list[dict[str, Any]] = []

    def write_record(destination: Any, record: dict[str, Any]) -> None:
        nonlocal next_normalized_ordinal
        record["schema"] = NORMALIZED_RECORD_V2_SCHEMA
        record["normalization_ordinal"] = next_normalized_ordinal
        next_normalized_ordinal += 1
        validate_historical_schema(
            record, "normalized-record-v2.schema.json", "NormalizedRecordSchemaMismatch"
        )
        destination.write(canonical_json(record) + "\n")

    def control_record(
        destination: Any,
        *,
        raw_ordinal: int,
        received_at: int,
        control_type: str,
        ticker: str | None,
        source_scope_id: str | None,
        details: dict[str, Any],
    ) -> None:
        nonlocal last_logical_time, has_discontinuity
        last_logical_time = max(last_logical_time, received_at)
        discontinuity_counts[control_type] += 1
        has_discontinuity = True
        write_record(
            destination,
            {
                "kind": "discontinuity",
                "control_type": control_type,
                "raw_ingress_ordinal": raw_ordinal,
                "logical_time_utc_ns": last_logical_time,
                "local_received_at_utc_ns": received_at,
                "ticker": ticker,
                "source_scope_id": source_scope_id,
                "truth_category": "Synthetic" if source_truth == "Synthetic" else "Reconstructed",
                "source_fidelity": "level_2",
                "details": details,
            },
        )

    try:
        with frames.open(encoding="utf-8") as source, records_path.open(
            "x", encoding="utf-8"
        ) as destination:
            for line_number, line in enumerate(source, start=1):
                try:
                    raw_record = json.loads(line)
                except json.JSONDecodeError as error:
                    raise HistoricalDataError(
                        "MalformedCaptureRecord", f"raw JSONL line {line_number} is corrupt"
                    ) from error
                if not isinstance(raw_record, dict) or raw_record.get("schema") != RAW_CAPTURE_RECORD_V2_SCHEMA:
                    raise HistoricalDataError(
                        "CaptureRecordSchemaMismatch", f"raw line {line_number} is not a V2 record"
                    )
                validate_historical_schema(
                    raw_record,
                    "raw-capture-record-v2.schema.json",
                    "CaptureRecordSchemaMismatch",
                )
                raw_ordinal = int_value(
                    raw_record.get("raw_ingress_ordinal"), "raw_ingress_ordinal"
                )
                if raw_ordinal != last_raw_ordinal + 1:
                    raise HistoricalDataError(
                        "IngressOrdinalMismatch",
                        f"raw line {line_number} does not continue ingress ordinals",
                    )
                last_raw_ordinal = raw_ordinal
                received_at = int_value(
                    raw_record.get("received_at_utc_ns"), "received_at_utc_ns"
                )
                kind = raw_record.get("kind")
                connection_id = raw_record.get("connection_segment_id")
                if kind == "subscription_sent":
                    connection = int_value(connection_id, "connection_segment_id")
                    if connection in requests:
                        raise HistoricalDataError(
                            "SubscriptionRequestInvalid", "connection has more than one subscription request"
                        )
                    subscription = raw_record.get("subscription")
                    if not isinstance(subscription, dict):
                        raise HistoricalDataError(
                            "SubscriptionRequestInvalid", "subscription_sent has no request"
                        )
                    wire_id = int_value(subscription.get("id"), "subscription.id")
                    top_level_wire_id = int_value(
                        raw_record.get("wire_request_id"), "wire_request_id"
                    )
                    logical_id = raw_record.get("subscription_request_id")
                    expected_logical_id = f"c{connection}:r1"
                    if (
                        wire_id != top_level_wire_id
                        or wire_id != connection
                        or logical_id != expected_logical_id
                        or logical_id in logical_request_ids
                        or subscription.get("cmd") != "subscribe"
                    ):
                        raise HistoricalDataError(
                            "SubscriptionRequestInvalid",
                            "subscription logical or wire request identity is invalid",
                        )
                    params = subscription.get("params")
                    membership = params.get("market_tickers") if isinstance(params, dict) else None
                    channels = params.get("channels") if isinstance(params, dict) else None
                    if (
                        membership != list(tickers)
                        or channels != ["orderbook_delta", "trade"]
                        or params.get("use_yes_price") is not True
                    ):
                        raise HistoricalDataError(
                            "SubscriptionRequestInvalid",
                            "subscription request differs from canonical capture membership",
                        )
                    logical_request_ids.add(logical_id)
                    requests[connection] = {
                        "logical_id": logical_id,
                        "wire_id": wire_id,
                        "membership": tickers,
                    }
                    continue
                if kind == "subscription_acknowledged":
                    connection = int_value(connection_id, "connection_segment_id")
                    wire_id = int_value(raw_record.get("wire_request_id"), "wire_request_id")
                    request = requests.get(connection)
                    if request is None or wire_id != request["wire_id"]:
                        raise HistoricalDataError(
                            "SubscriptionAckMismatch", "acknowledgement has no matching request"
                        )
                    channel = raw_record.get("channel")
                    sid = raw_record.get("venue_subscription_id")
                    logical_id = raw_record.get("subscription_request_id")
                    membership = raw_record.get("requested_market_tickers")
                    membership_claim = raw_record.get("membership_claim")
                    if (
                        channel not in {"orderbook_delta", "trade"}
                        or sid is None
                        or not str(sid)
                        or logical_id != request["logical_id"]
                        or membership != list(request["membership"])
                        or membership_claim != "request_bound_not_echoed_by_acknowledgement"
                    ):
                        raise HistoricalDataError(
                            "SubscriptionAckMismatch", "acknowledgement channel or sid is invalid"
                        )
                    acknowledgement_key = (connection, str(channel))
                    key = (connection, str(sid))
                    if acknowledgement_key in acknowledgements or key in scopes:
                        raise HistoricalDataError(
                            "SubscriptionAckMismatch", "duplicate or conflicting sid binding"
                        )
                    acknowledgements[acknowledgement_key] = str(sid)
                    scopes[key] = {
                        "source_scope_id": f"c{connection}:sid{sid}",
                        "connection_segment_id": connection,
                        "subscription_request_id": logical_id,
                        "wire_request_id": wire_id,
                        "channel": channel,
                        "venue_subscription_id": str(sid),
                        "requested_market_tickers": list(request["membership"]),
                        "membership_claim": membership_claim,
                        "sequence_domain_status": sequence_domain["status"],
                        "sequence_domain_components": sequence_domain.get("components", []),
                        "sequence_domain_topology": sequence_topology,
                    }
                    continue
                if kind == "connection_gap":
                    connection = int_value(connection_id, "connection_segment_id")
                    for ticker in tickers:
                        state = market_state[ticker]
                        if not state["ever_valid"]:
                            incomplete_reasons.append(
                                {
                                    "code": "IncompletePrefix",
                                    "ticker": ticker,
                                    "raw_ingress_ordinal": raw_ordinal,
                                }
                            )
                        state["valid"] = False
                        state["awaiting"] = (
                            "recovery_snapshot" if state["ever_valid"] else "initial_snapshot"
                        )
                        control_record(
                            destination,
                            raw_ordinal=raw_ordinal,
                            received_at=received_at,
                            control_type="connection_gap",
                            ticker=ticker,
                            source_scope_id=None,
                            details={
                                "connection_segment_id": connection,
                                "failure_phase": raw_record.get("failure_phase"),
                                "error_code": raw_record.get("error_code"),
                                "prior_book_state": (
                                    "invalidated" if state["ever_valid"] else "not_yet_established"
                                ),
                            },
                        )
                    continue
                if kind in {
                    "connection_attempt",
                    "connection_opened",
                    "connection_closed",
                    "binary_frame_rejected",
                }:
                    if kind == "binary_frame_rejected":
                        incomplete_reasons.append(
                            {"code": "UnsupportedBinaryFrame", "raw_ingress_ordinal": raw_ordinal}
                        )
                    continue
                if kind != "inbound_frame":
                    continue
                message_type = raw_record.get("message_type")
                if message_type not in {"orderbook_snapshot", "orderbook_delta", "trade"}:
                    continue
                connection = int_value(connection_id, "connection_segment_id")
                sid = raw_record.get("subscription_id")
                scope = scopes.get((connection, str(sid)))
                if scope is None:
                    raise HistoricalDataError(
                        "UnboundSourceScope", f"raw line {line_number} uses unbound sid {sid!r}"
                    )
                expected_channel = "trade" if message_type == "trade" else "orderbook_delta"
                if scope["channel"] != expected_channel:
                    raise HistoricalDataError(
                        "SourceScopeConflict", f"{message_type} arrived on {scope['channel']} scope"
                    )
                parsed_type, message = parse_raw_message(raw_record, line_number)
                if parsed_type != message_type:
                    raise HistoricalDataError(
                        "MessageTypeMismatch", f"raw line {line_number} type conflicts with payload"
                    )
                ticker, parsed_market_id, payload = normalized_payload(parsed_type, message)
                if ticker not in tickers:
                    raise HistoricalDataError(
                        "MarketMembershipMismatch", f"raw line {line_number} ticker was not requested"
                    )
                if ticker in packages:
                    validate_product_payload(packages[ticker], payload, parsed_type)
                known_market_id = market_ids.get(ticker)
                if known_market_id is None and parsed_market_id is None:
                    raise HistoricalDataError(
                        "MarketIdentityMissing", f"{ticker} has no market_id before identity is established"
                    )
                if known_market_id is None:
                    assert parsed_market_id is not None
                    market_ids[ticker] = parsed_market_id
                    known_market_id = parsed_market_id
                elif parsed_market_id is not None and parsed_market_id != known_market_id:
                    raise HistoricalDataError(
                        "MarketIdentityConflict", f"{ticker} market_id changed within the capture"
                    )

                source_scope_id = scope["source_scope_id"]
                sequence_validation_scope = (
                    f"{source_scope_id}:ticker:{ticker}"
                    if sequence_topology == "independent"
                    else source_scope_id
                )
                source_sequence_value = raw_record.get("source_sequence", message.get("seq"))
                sequence_required = parsed_type in {"orderbook_snapshot", "orderbook_delta"}
                if source_sequence_value is None and sequence_required:
                    incomplete_reasons.append(
                        {
                            "code": "RequiredSourceSequenceMissing",
                            "ticker": ticker,
                            "message_type": parsed_type,
                            "raw_ingress_ordinal": raw_ordinal,
                        }
                    )
                    if continuity_policy == "refuse":
                        raise HistoricalDataError(
                            "RequiredSourceSequenceMissing",
                            f"{parsed_type} for {ticker} has no required source sequence",
                        )
                if source_sequence_value is not None:
                    current_sequence = int_value(source_sequence_value, "source_sequence")
                    duplicate_key = (sequence_validation_scope, current_sequence)
                    payload_hash = hashlib.sha256(canonical_json(message).encode()).hexdigest()
                    prior_hash = sequence_payloads.get(duplicate_key)
                    if prior_hash is not None:
                        if prior_hash != payload_hash:
                            raise HistoricalDataError(
                                "ConflictingDuplicate",
                                f"source identity conflicts at raw line {line_number}",
                            )
                        identical_duplicates += 1
                        continue
                    previous_sequence = sequence_previous.get(sequence_validation_scope)
                    if previous_sequence is not None and current_sequence < previous_sequence:
                        raise HistoricalDataError(
                            "SourceSequenceRegression", f"sequence regressed at raw line {line_number}"
                        )
                    if previous_sequence is not None and current_sequence > previous_sequence + 1:
                        if sequence_topology == "independent":
                            affected_tickers = [ticker]
                        else:
                            affected_tickers = list(scope["requested_market_tickers"])
                        control_record(
                            destination,
                            raw_ordinal=raw_ordinal,
                            received_at=received_at,
                            control_type="sequence_gap",
                            ticker=None,
                            source_scope_id=source_scope_id,
                            details={
                                "expected_sequence": previous_sequence + 1,
                                "received_sequence": current_sequence,
                                "scope_status": sequence_domain["status"],
                                "scope_topology": sequence_topology,
                                "observed_post_gap_ticker": ticker,
                                "affected_market_tickers": affected_tickers,
                            },
                        )
                        if scope["channel"] == "orderbook_delta":
                            for affected_ticker in affected_tickers:
                                affected_state = market_state[affected_ticker]
                                affected_state["valid"] = False
                                affected_state["awaiting"] = (
                                    "recovery_snapshot"
                                    if affected_state["ever_valid"]
                                    else "initial_snapshot"
                                )
                    sequence_previous[sequence_validation_scope] = current_sequence
                    sequence_payloads[duplicate_key] = payload_hash

                state = market_state[ticker]
                if parsed_type == "orderbook_snapshot":
                    if state["valid"]:
                        raise HistoricalDataError(
                            "RecoverySnapshotDuplicate",
                            f"unexpected additional snapshot for {ticker}",
                        )
                    state["segment"] += 1
                    state["valid"] = True
                    state["ever_valid"] = True
                    recovery_kind = state["awaiting"]
                    state["awaiting"] = None
                    snapshot_counts[(connection, ticker)] += 1
                    write_record(
                        destination,
                        {
                            "kind": "segment_boundary",
                            "boundary_type": "segment_started",
                            "raw_ingress_ordinal": raw_ordinal,
                            "logical_time_utc_ns": max(last_logical_time, received_at),
                            "local_received_at_utc_ns": received_at,
                            "ticker": ticker,
                            "source_scope_id": source_scope_id,
                            "book_segment_id": f"{ticker}:segment:{state['segment']}",
                            "start_evidence": recovery_kind,
                            "continuity_claim": "valid_from_observed_snapshot_only",
                            "truth_category": source_truth,
                            "source_fidelity": "level_2",
                        },
                    )
                elif parsed_type == "orderbook_delta" and not state["valid"]:
                    incomplete_reasons.append(
                        {
                            "code": "DeltaBeforeRecovery",
                            "ticker": ticker,
                            "raw_ingress_ordinal": raw_ordinal,
                        }
                    )
                    if continuity_policy == "refuse":
                        raise HistoricalDataError(
                            "DeltaBeforeRecovery", f"{ticker} delta arrived before required snapshot"
                        )

                received_at = int_value(
                    raw_record.get("received_at_utc_ns"), "received_at_utc_ns"
                )
                source_ts_ms = message["msg"].get("ts_ms")
                source_time = (
                    None
                    if source_ts_ms is None
                    else int_value(source_ts_ms, "ts_ms") * 1_000_000
                )
                event_time = source_time if source_time is not None else received_at
                scope_previous_time = last_scope_time.get(source_scope_id)
                scope_time_late = (
                    source_time is not None
                    and scope_previous_time is not None
                    and source_time < scope_previous_time
                )
                global_time_late = source_time is not None and source_time < last_logical_time
                late_source_events += global_time_late
                last_scope_time[source_scope_id] = max(
                    scope_previous_time if scope_previous_time is not None else event_time,
                    event_time,
                )
                last_logical_time = max(last_logical_time, event_time)
                event_counts[
                    {
                        "orderbook_snapshot": "book_snapshot",
                        "orderbook_delta": "book_delta",
                        "trade": "trade",
                    }[parsed_type]
                ] += 1
                write_record(
                    destination,
                    {
                        "kind": "market_event",
                        "event_id": f"{ticker}:{raw_ordinal}",
                        "raw_ingress_ordinal": raw_ordinal,
                        "logical_time_utc_ns": last_logical_time,
                        "event_time_utc_ns": event_time,
                        "event_time_basis": (
                            "source_ts_ms" if source_time is not None else "local_receive_time"
                        ),
                        "source_time_late": global_time_late,
                        "source_scope_time_late": scope_time_late,
                        "local_received_at_utc_ns": received_at,
                        "source_sequence": source_sequence_value,
                        "source_scope_id": source_scope_id,
                        "sequence_domain_status": sequence_domain["status"],
                        "connection_segment_id": connection,
                        "subscription_id": str(sid),
                        "ticker": ticker,
                        "venue_market_id": known_market_id,
                        "venue_market_id_provenance": (
                            "source_message" if parsed_market_id is not None else "capture_bound"
                        ),
                        "book_segment_id": (
                            f"{ticker}:segment:{state['segment']}" if state["segment"] else None
                        ),
                        "book_state_valid": state["valid"],
                        "event_type": {
                            "orderbook_snapshot": "book_snapshot",
                            "orderbook_delta": "book_delta",
                            "trade": "trade",
                        }[parsed_type],
                        "truth_category": source_truth,
                        "source_fidelity": "level_2",
                        "payload": payload,
                    },
                )

        for connection in requests:
            acknowledged_channels = {
                channel for candidate_connection, channel in acknowledgements
                if candidate_connection == connection
            }
            if acknowledged_channels != {"orderbook_delta", "trade"}:
                incomplete_reasons.append(
                    {"code": "SubscriptionAckMissing", "connection_segment_id": connection}
                )
            for ticker in tickers:
                if snapshot_counts[(connection, ticker)] != 1:
                    incomplete_reasons.append(
                        {
                            "code": "SnapshotCardinalityMismatch",
                            "connection_segment_id": connection,
                            "ticker": ticker,
                            "count": snapshot_counts[(connection, ticker)],
                        }
                    )
        if not requests:
            incomplete_reasons.append({"code": "SubscriptionRequestMissing"})
        for ticker, state in market_state.items():
            if not state["valid"]:
                incomplete_reasons.append(
                    {"code": "RecoverySnapshotMissing", "ticker": ticker}
                )

        missing_market_ids = [ticker for ticker in tickers if ticker not in market_ids]
        if missing_market_ids:
            raise HistoricalDataError(
                "MarketIdentityMissing",
                f"requested markets have no stable capture identity: {', '.join(missing_market_ids)}",
            )

        if incomplete_reasons:
            completeness = "incomplete"
        elif has_discontinuity:
            completeness = "observed_discontinuous"
        else:
            completeness = "complete_observed_interval"
        if completeness != "complete_observed_interval" and continuity_policy == "refuse":
            first = incomplete_reasons[0]["code"] if incomplete_reasons else "DiscontinuousInput"
            raise HistoricalDataError(
                first,
                f"normalization refuses {completeness} input by default; use --continuity-policy record",
            )

        scope_document = {
            "schema": SOURCE_SCOPE_MAP_SCHEMA,
            "sequence_domain": sequence_domain,
            "scopes": sorted(scopes.values(), key=lambda value: value["source_scope_id"]),
        }
        validate_historical_schema(
            scope_document, "source-scope-map-v1.schema.json", "SourceScopeSchemaMismatch"
        )
        write_json(scope_path, scope_document)
        product_entries: list[dict[str, Any]] = []
        for ticker in tickers:
            entry: dict[str, Any] = {
                "ticker": ticker,
                "venue_market_id": market_ids.get(ticker),
                "venue_market_id_authority": "capture_only_not_in_terms_source",
                "source_fidelity": "level_2",
            }
            package = packages.get(ticker)
            if package is not None:
                assert conversion_policy is not None
                identity = package.terms.identity
                entry.update(
                    {
                        "authoritative_identity": identity,
                        "product_terms_sha256": package.terms.payload_sha256,
                        "source_manifest_sha256": package.evidence.payload_sha256,
                        "review_sha256": package.review.payload_sha256,
                        "conversion_policy_sha256": conversion_policy.payload_sha256,
                    }
                )
            product_entries.append(entry)
        product_document = {
            "schema": PRODUCT_MAP_V3_SCHEMA,
            "venue": "kalshi",
            "environment": "production",
            "products": product_entries,
        }
        validate_historical_schema(
            product_document, "product-map-v3.schema.json", "ProductMapSchemaMismatch"
        )
        write_json(product_path, product_document)
        if packages:
            terms_root = temporary / "product_terms"
            terms_root.mkdir()
            for ticker, package in sorted(packages.items()):
                copy_package(package, terms_root / ticker)
            assert conversion_policy is not None
            shutil.copy2(conversion_policy.path, temporary / "conversion_policy.json")

        manifest: dict[str, Any] = {
            "schema": NORMALIZATION_MANIFEST_V3_SCHEMA,
            "normalizer_version": NORMALIZER_V2_VERSION,
            "input_capture_directory": str(input_dir.relative_to(REPOSITORY_ROOT)),
            "input_frames_sha256": sha256_file(frames),
            "input_capture_metadata_sha256": sha256_file(metadata_path),
            "output_records_sha256": sha256_file(records_path),
            "output_source_scopes_sha256": sha256_file(scope_path),
            "output_product_sha256": sha256_file(product_path),
            "market_tickers": list(tickers),
            "ordering_policy": (
                "raw ingress ordinal is the cross-scope total order; source sequences validate "
                "only their represented domain; timestamps never reorder records"
            ),
            "continuity_policy": continuity_policy,
            "completeness": completeness,
            "incomplete_reasons": incomplete_reasons,
            "event_counts": dict(sorted(event_counts.items())),
            "discontinuity_counts": dict(sorted(discontinuity_counts.items())),
            "identical_duplicates_skipped": identical_duplicates,
            "late_source_events": late_source_events,
            "truth_category": source_truth,
            "source_fidelity": "level_2",
            "limitations": [
                "Level-2 data has no individual order identity or queue position.",
                "Unknown sequence domains do not prove venue-global continuity.",
                "A recovery snapshot starts a new segment and does not recover a missing interval.",
            ],
        }
        if packages:
            assert product_catalog is not None and conversion_policy is not None
            manifest["product_catalog_sha256"] = product_catalog.payload_sha256
            manifest["conversion_policy_sha256"] = conversion_policy.payload_sha256
            manifest["product_lineage"] = [
                {
                    "ticker": ticker,
                    "product_terms_sha256": package.terms.payload_sha256,
                    "source_manifest_sha256": package.evidence.payload_sha256,
                    "review_sha256": package.review.payload_sha256,
                }
                for ticker, package in sorted(packages.items())
            ]
        validate_historical_schema(
            manifest,
            "normalization-manifest-v3.schema.json",
            "NormalizationManifestSchemaMismatch",
        )
        write_json(manifest_path, manifest)
        temporary.rename(output_dir)
        return manifest
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path} line {line_number} is not valid JSON") from error
            if not isinstance(value, dict):
                raise ValueError(f"{path} line {line_number} is not an object")
            yield value


@dataclass
class ObservedMarketProjection:
    yes_bids: dict[Decimal, Decimal] = field(default_factory=dict)
    yes_asks: dict[Decimal, Decimal] = field(default_factory=dict)
    last_trade_price: Decimal | None = None
    last_ingress_order: int = 0
    has_snapshot: bool = False

    def apply(self, event: dict[str, Any]) -> None:
        ingress = int_value(event.get("ingress_order"), "ingress_order")
        if ingress != self.last_ingress_order + 1:
            raise ValueError("normalized events do not have a contiguous ingress order")
        event_type = event.get("event_type")
        payload = event.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("normalized event has no payload")
        if event_type == "book_snapshot":
            self.yes_bids = self._levels(payload.get("yes_bids"), "yes_bids")
            self.yes_asks = self._levels(payload.get("yes_asks"), "yes_asks")
            self.has_snapshot = True
        elif event_type == "book_delta":
            if not self.has_snapshot:
                raise ValueError("book delta appeared before the initial snapshot")
            side = payload.get("book_side")
            levels = self.yes_bids if side == "yes" else self.yes_asks if side == "no" else None
            if levels is None:
                raise ValueError("book delta has an invalid side")
            price = Decimal(str(payload.get("price_dollars")))
            quantity = levels.get(price, Decimal(0)) + Decimal(str(payload.get("quantity_delta_contracts")))
            if quantity < 0:
                raise ValueError("book delta would create negative displayed quantity")
            if quantity == 0:
                levels.pop(price, None)
            else:
                levels[price] = quantity
        elif event_type == "trade":
            self.last_trade_price = Decimal(str(payload.get("yes_price_dollars")))
        else:
            raise ValueError(f"unsupported normalized event type {event_type!r}")
        self.last_ingress_order = ingress

    @staticmethod
    def _levels(value: Any, field_name: str) -> dict[Decimal, Decimal]:
        if not isinstance(value, list):
            raise ValueError(f"{field_name} must be a list")
        result: dict[Decimal, Decimal] = {}
        for level in value:
            if not isinstance(level, dict):
                raise ValueError(f"{field_name} level must be an object")
            price = Decimal(str(level.get("price_dollars")))
            quantity = Decimal(str(level.get("quantity_contracts")))
            if quantity <= 0 or price in result:
                raise ValueError(f"{field_name} contains an invalid level")
            result[price] = quantity
        return result

    def feature_values(self) -> dict[str, str | None]:
        bid_price = max(self.yes_bids) if self.yes_bids else None
        ask_price = min(self.yes_asks) if self.yes_asks else None
        bid_quantity = self.yes_bids.get(bid_price) if bid_price is not None else None
        ask_quantity = self.yes_asks.get(ask_price) if ask_price is not None else None
        midpoint = None if bid_price is None or ask_price is None else (bid_price + ask_price) / Decimal(2)
        spread = None if bid_price is None or ask_price is None else ask_price - bid_price
        imbalance = None
        if bid_quantity is not None and ask_quantity is not None and bid_quantity + ask_quantity > 0:
            imbalance = (bid_quantity - ask_quantity) / (bid_quantity + ask_quantity)
        return {
            "best_yes_bid_dollars": None if bid_price is None else format(bid_price, "f"),
            "best_yes_ask_dollars": None if ask_price is None else format(ask_price, "f"),
            "best_bid_quantity_contracts": None if bid_quantity is None else format(bid_quantity, "f"),
            "best_ask_quantity_contracts": None if ask_quantity is None else format(ask_quantity, "f"),
            "midpoint_dollars": None if midpoint is None else format(midpoint, "f"),
            "spread_dollars": None if spread is None else format(spread, "f"),
            "top_of_book_imbalance": None if imbalance is None else format(imbalance, "f"),
            "last_trade_yes_price_dollars": None if self.last_trade_price is None else format(self.last_trade_price, "f"),
        }

    def checkpoint(self) -> dict[str, Any]:
        return {
            "schema": "pmm.historical.observed_projection_checkpoint.v1",
            "last_ingress_order": self.last_ingress_order,
            "has_snapshot": self.has_snapshot,
            "yes_bids": self._checkpoint_levels(self.yes_bids),
            "yes_asks": self._checkpoint_levels(self.yes_asks),
            "last_trade_price": None if self.last_trade_price is None else format(self.last_trade_price, "f"),
        }

    @staticmethod
    def _checkpoint_levels(levels: dict[Decimal, Decimal]) -> list[list[str]]:
        return [[format(price, "f"), format(quantity, "f")] for price, quantity in sorted(levels.items())]

    @classmethod
    def restore(cls, checkpoint: dict[str, Any]) -> "ObservedMarketProjection":
        if checkpoint.get("schema") != "pmm.historical.observed_projection_checkpoint.v1":
            raise ValueError("unsupported observed-projection checkpoint schema")
        projection = cls(
            yes_bids=cls._restore_checkpoint_levels(checkpoint.get("yes_bids"), "yes_bids"),
            yes_asks=cls._restore_checkpoint_levels(checkpoint.get("yes_asks"), "yes_asks"),
            last_trade_price=None if checkpoint.get("last_trade_price") is None else Decimal(str(checkpoint["last_trade_price"])),
            last_ingress_order=int_value(checkpoint.get("last_ingress_order"), "last_ingress_order"),
            has_snapshot=bool(checkpoint.get("has_snapshot")),
        )
        if not projection.has_snapshot and (projection.yes_bids or projection.yes_asks):
            raise ValueError("checkpoint has book levels before a snapshot")
        return projection

    @staticmethod
    def _restore_checkpoint_levels(value: Any, field_name: str) -> dict[Decimal, Decimal]:
        if not isinstance(value, list):
            raise ValueError(f"checkpoint {field_name} must be a list")
        levels: dict[Decimal, Decimal] = {}
        for level in value:
            if not isinstance(level, list) or len(level) != 2:
                raise ValueError(f"checkpoint {field_name} contains an invalid level")
            price, quantity = Decimal(str(level[0])), Decimal(str(level[1]))
            if price in levels or quantity <= 0:
                raise ValueError(f"checkpoint {field_name} contains an invalid quantity or duplicate price")
            levels[price] = quantity
        return levels


@dataclass
class ObservedMarketCursor:
    """A pull-driven historical cursor with a stable applied-event watermark."""

    projection: ObservedMarketProjection = field(default_factory=ObservedMarketProjection)

    @property
    def watermark(self) -> int:
        return self.projection.last_ingress_order

    def advance(self, event: dict[str, Any]) -> None:
        self.projection.apply(event)

    def checkpoint(self) -> dict[str, Any]:
        return self.projection.checkpoint()

    @classmethod
    def restore(cls, checkpoint: dict[str, Any]) -> "ObservedMarketCursor":
        return cls(projection=ObservedMarketProjection.restore(checkpoint))


@dataclass(frozen=True)
class CausalWatermark:
    raw_ingress_ordinal: int
    normalization_ordinal: int

    def document(self) -> dict[str, int]:
        return {
            "raw_ingress_ordinal": self.raw_ingress_ordinal,
            "normalization_ordinal": self.normalization_ordinal,
        }


@dataclass
class SegmentAwareProductCursor:
    """One product-owned projection whose mutable book never crosses a segment."""

    ticker: str
    venue_market_id: str
    state: str = "awaiting_initial_snapshot"
    segment_id: str | None = None
    segment_start_evidence: str | None = None
    projection: ObservedMarketProjection = field(default_factory=ObservedMarketProjection)
    product_applied_watermark: CausalWatermark | None = None
    snapshot_seed_watermark: CausalWatermark | None = None
    valid_from_watermark: CausalWatermark | None = None
    invalidated_by_watermark: CausalWatermark | None = None
    pending_boundary: dict[str, Any] | None = None
    seen_segments: set[str] = field(default_factory=set)

    @staticmethod
    def _watermark(record: dict[str, Any]) -> CausalWatermark:
        return CausalWatermark(
            int_value(record.get("raw_ingress_ordinal"), "raw_ingress_ordinal"),
            int_value(record.get("normalization_ordinal"), "normalization_ordinal"),
        )

    def start_segment(self, record: dict[str, Any]) -> None:
        if self.pending_boundary is not None:
            raise HistoricalDataError("FeatureSegmentInvalid", f"{self.ticker} has an unmatched segment boundary")
        segment_id = record.get("book_segment_id")
        evidence = record.get("start_evidence")
        expected_evidence = (
            "initial_snapshot" if self.state == "awaiting_initial_snapshot" else "recovery_snapshot"
        )
        if (
            not isinstance(segment_id, str)
            or not segment_id
            or segment_id in self.seen_segments
            or record.get("ticker") != self.ticker
            or evidence != expected_evidence
            or record.get("continuity_claim") != "valid_from_observed_snapshot_only"
        ):
            raise HistoricalDataError("FeatureSegmentInvalid", f"invalid segment boundary for {self.ticker}")
        self.pending_boundary = dict(record)
        self.product_applied_watermark = self._watermark(record)

    def invalidate(self, record: dict[str, Any]) -> None:
        self.product_applied_watermark = self._watermark(record)
        self.invalidated_by_watermark = self.product_applied_watermark
        self.state = (
            "invalid_awaiting_recovery"
            if self.segment_id is not None or self.state == "valid"
            else "awaiting_initial_snapshot"
        )
        self.segment_id = None
        self.segment_start_evidence = None
        self.snapshot_seed_watermark = None
        self.valid_from_watermark = None
        self.pending_boundary = None
        self.projection = ObservedMarketProjection()

    def apply_market_event(self, record: dict[str, Any]) -> bool:
        if record.get("ticker") != self.ticker or record.get("venue_market_id") != self.venue_market_id:
            raise HistoricalDataError("FeatureProductIdentityMismatch", f"market event identity changed for {self.ticker}")
        event_type = record.get("event_type")
        watermark = self._watermark(record)
        if event_type == "book_snapshot":
            boundary = self.pending_boundary
            if boundary is None:
                raise HistoricalDataError("FeatureSegmentInvalid", f"snapshot for {self.ticker} has no segment boundary")
            if any(
                record.get(field) != boundary.get(field)
                for field in ("ticker", "book_segment_id", "source_scope_id", "raw_ingress_ordinal")
            ) or record.get("book_state_valid") is not True:
                raise HistoricalDataError("FeatureSegmentInvalid", f"snapshot does not match boundary for {self.ticker}")
            self.projection = ObservedMarketProjection()
            legacy_event = dict(record)
            legacy_event["ingress_order"] = 1
            self.projection.apply(legacy_event)
            self.segment_id = str(record["book_segment_id"])
            self.segment_start_evidence = str(boundary["start_evidence"])
            self.seen_segments.add(self.segment_id)
            self.snapshot_seed_watermark = self._watermark(boundary)
            self.valid_from_watermark = watermark
            self.product_applied_watermark = watermark
            self.pending_boundary = None
            self.state = "valid"
            return True
        if self.pending_boundary is not None:
            raise HistoricalDataError("FeatureSegmentInvalid", f"segment boundary for {self.ticker} is not followed by its snapshot")
        if event_type == "trade" and self.state != "valid":
            self.product_applied_watermark = watermark
            return False
        if (
            self.state != "valid"
            or record.get("book_state_valid") is not True
            or record.get("book_segment_id") != self.segment_id
        ):
            raise HistoricalDataError("FeatureBookStateInvalid", f"{event_type} cannot apply to {self.ticker}")
        legacy_event = dict(record)
        legacy_event["ingress_order"] = self.projection.last_ingress_order + 1
        try:
            self.projection.apply(legacy_event)
        except ValueError as error:
            raise HistoricalDataError("FeatureProjectionInvalid", str(error)) from error
        self.product_applied_watermark = watermark
        return True


def _feature_v3_definitions() -> list[dict[str, Any]]:
    definitions = [
        ("best_yes_bid_dollars", "dollars", "maximum displayed YES bid", "current_projected_segment_state"),
        ("best_yes_ask_dollars", "dollars", "minimum displayed YES ask", "current_projected_segment_state"),
        ("best_bid_quantity_contracts", "contracts", "displayed quantity at best YES bid", "current_projected_segment_state"),
        ("best_ask_quantity_contracts", "contracts", "displayed quantity at best YES ask", "current_projected_segment_state"),
        ("midpoint_dollars", "dollars", "(best_yes_bid + best_yes_ask) / 2", "current_projected_segment_state"),
        ("spread_dollars", "dollars", "best_yes_ask - best_yes_bid", "current_projected_segment_state"),
        ("top_of_book_imbalance", "ratio", "(bid_quantity - ask_quantity) / (bid_quantity + ask_quantity)", "current_projected_segment_state"),
        ("last_trade_yes_price_dollars", "dollars", "last observed YES trade price in current segment", "last_observed_trade_in_current_segment"),
    ]
    return [
        {
            "name": name,
            "unit": unit,
            "formula": formula,
            "lookback": lookback,
            "warmup": "observed_snapshot_required",
            "nullable": True,
        }
        for name, unit, formula, lookback in definitions
    ]


def _feature_v3_limitations(normalization_limitations: Any) -> list[str]:
    limitations = list(normalization_limitations) if isinstance(normalization_limitations, list) else []
    limitations.extend(
        [
            "Level-2 state does not identify queue position, individual orders, cancellations, or hidden liquidity.",
            "A segment is valid only from its observed snapshot; a later segment never recovers a missing interval.",
            "Feature rows contain one product only and make no cross-market causality claim.",
        ]
    )
    return sorted(set(str(item) for item in limitations))


def materialize_features_v3(input_dir: Path, output_dir: Path) -> dict[str, Any]:
    input_dir = input_dir.resolve()
    manifest_path = input_dir / "manifest.json"
    records_path = input_dir / "records.jsonl"
    scopes_path = input_dir / "source_scopes.json"
    product_path = input_dir / "product.json"
    if not all(path.is_file() for path in (manifest_path, records_path, scopes_path, product_path)):
        raise HistoricalDataError("FeatureInputMissing", "input must contain V3 manifest, records, scopes, and product map")
    normalized = read_json(manifest_path)
    if normalized.get("schema") != NORMALIZATION_MANIFEST_V3_SCHEMA:
        raise HistoricalDataError("FeatureInputSchemaMismatch", "features-v3 requires normalization manifest V3")
    validate_historical_schema(normalized, "normalization-manifest-v3.schema.json", "FeatureInputSchemaMismatch")
    if normalized.get("completeness") != "complete_observed_interval":
        raise HistoricalDataError("FeatureInputContinuityRequired", "features-v3 accepts only complete_observed_interval input")
    expected_hashes = {
        records_path: normalized.get("output_records_sha256"),
        scopes_path: normalized.get("output_source_scopes_sha256"),
        product_path: normalized.get("output_product_sha256"),
    }
    if any(expected != sha256_file(path) for path, expected in expected_hashes.items()):
        raise HistoricalDataError("FeatureInputHashMismatch", "normalization V3 input hash is stale")
    scopes = read_json(scopes_path)
    product_map = read_json(product_path)
    validate_historical_schema(scopes, "source-scope-map-v1.schema.json", "FeatureInputSchemaMismatch")
    validate_historical_schema(product_map, "product-map-v3.schema.json", "FeatureInputSchemaMismatch")
    products_value = product_map.get("products")
    if not isinstance(products_value, list):
        raise HistoricalDataError("FeatureProductIdentityMismatch", "product map has no products")
    products = {str(item.get("ticker")): item for item in products_value if isinstance(item, dict)}
    tickers = normalized.get("market_tickers")
    if not isinstance(tickers, list) or list(products) != tickers:
        raise HistoricalDataError("FeatureProductIdentityMismatch", "product map order differs from manifest")
    lineage_by_ticker = {
        str(item.get("ticker")): item
        for item in normalized.get("product_lineage", [])
        if isinstance(item, dict)
    }
    conversion_hash = normalized.get("conversion_policy_sha256")
    for ticker, reviewed in lineage_by_ticker.items():
        entry = products.get(ticker)
        if entry is None or conversion_hash is None or any(
            entry.get(field) != reviewed.get(field)
            for field in ("product_terms_sha256", "source_manifest_sha256", "review_sha256")
        ) or entry.get("conversion_policy_sha256") != conversion_hash:
            raise HistoricalDataError(
                "FeatureProductLineageMismatch", f"reviewed lineage is inconsistent for {ticker}"
            )
    limitations = _feature_v3_limitations(normalized.get("limitations"))

    output_dir = ensure_new_output(output_dir)
    temporary = output_dir.with_name(f"{output_dir.name}.partial")
    if temporary.exists():
        raise HistoricalDataError("PartialOutputExists", f"temporary feature output already exists: {temporary}")
    temporary.mkdir(parents=True)
    features_path = temporary / "features.jsonl"
    cursors = {
        ticker: SegmentAwareProductCursor(ticker, str(products[ticker].get("venue_market_id")))
        for ticker in tickers
    }
    product_rows: Counter[str] = Counter()
    product_segments: dict[str, list[str]] = {ticker: [] for ticker in tickers}
    first_watermarks: dict[str, dict[str, int]] = {}
    last_watermarks: dict[str, dict[str, int]] = {}
    last_normalization_ordinal = 0
    last_raw_ordinal = 0
    feature_count = 0
    try:
        with features_path.open("x", encoding="utf-8") as destination:
            for record in iter_jsonl(records_path):
                if record.get("schema") != NORMALIZED_RECORD_V2_SCHEMA:
                    raise HistoricalDataError("FeatureRecordSchemaMismatch", "records input is not normalized record V2")
                validate_historical_schema(record, "normalized-record-v2.schema.json", "FeatureRecordSchemaMismatch")
                normalization_ordinal = int_value(record.get("normalization_ordinal"), "normalization_ordinal")
                raw_ordinal = int_value(record.get("raw_ingress_ordinal"), "raw_ingress_ordinal")
                if normalization_ordinal != last_normalization_ordinal + 1 or raw_ordinal < last_raw_ordinal:
                    raise HistoricalDataError("FeatureOrderingInvalid", "normalized records are not in canonical order")
                last_normalization_ordinal = normalization_ordinal
                last_raw_ordinal = raw_ordinal
                kind = record.get("kind")
                pending = [cursor for cursor in cursors.values() if cursor.pending_boundary is not None]
                if pending:
                    if len(pending) != 1:
                        raise HistoricalDataError("FeatureSegmentInvalid", "multiple segment boundaries are pending")
                    boundary = pending[0].pending_boundary
                    if not (
                        kind == "market_event"
                        and record.get("event_type") == "book_snapshot"
                        and record.get("ticker") == boundary.get("ticker")
                        and record.get("book_segment_id") == boundary.get("book_segment_id")
                        and record.get("source_scope_id") == boundary.get("source_scope_id")
                        and raw_ordinal == boundary.get("raw_ingress_ordinal")
                    ):
                        raise HistoricalDataError(
                            "FeatureSegmentInvalid", "segment boundary is not immediately followed by its snapshot"
                        )
                if kind == "segment_boundary":
                    ticker = str(record.get("ticker"))
                    if ticker not in cursors:
                        raise HistoricalDataError("FeatureProductIdentityMismatch", "segment names an unknown product")
                    cursors[ticker].start_segment(record)
                    continue
                if kind == "discontinuity":
                    affected = (
                        record.get("details", {}).get("affected_market_tickers")
                        if record.get("control_type") == "sequence_gap"
                        else [record.get("ticker")]
                    )
                    if not isinstance(affected, list) or any(ticker not in cursors for ticker in affected):
                        raise HistoricalDataError("FeatureDiscontinuityInvalid", "discontinuity has invalid affected products")
                    for ticker in affected:
                        cursors[str(ticker)].invalidate(record)
                    raise HistoricalDataError("FeatureInputContinuityRequired", "complete feature input contains a discontinuity")
                ticker = str(record.get("ticker"))
                if ticker not in cursors:
                    raise HistoricalDataError("FeatureProductIdentityMismatch", "market event names an unknown product")
                cursor = cursors[ticker]
                if not cursor.apply_market_event(record):
                    continue
                assert cursor.segment_id is not None
                assert cursor.product_applied_watermark is not None
                assert cursor.snapshot_seed_watermark is not None
                assert cursor.valid_from_watermark is not None
                if cursor.segment_id not in product_segments[ticker]:
                    product_segments[ticker].append(cursor.segment_id)
                product_entry_hash = hashlib.sha256(canonical_json(products[ticker]).encode()).hexdigest()
                lineage = {
                    "input_normalization_manifest_sha256": sha256_file(manifest_path),
                    "input_records_sha256": sha256_file(records_path),
                    "input_source_scopes_sha256": sha256_file(scopes_path),
                    "input_product_map_sha256": sha256_file(product_path),
                    "input_product_entry_sha256": product_entry_hash,
                }
                reviewed = lineage_by_ticker.get(ticker)
                if reviewed is not None:
                    lineage.update(
                        {
                            "product_terms_sha256": reviewed.get("product_terms_sha256"),
                            "source_manifest_sha256": reviewed.get("source_manifest_sha256"),
                            "review_sha256": reviewed.get("review_sha256"),
                            "conversion_policy_sha256": conversion_hash,
                        }
                    )
                row = {
                    "schema": FEATURE_ROW_V2_SCHEMA,
                    "feature_version": FEATURE_V2_VERSION,
                    "product_identity": {
                        "venue": product_map.get("venue"),
                        "environment": product_map.get("environment"),
                        "ticker": ticker,
                        "venue_market_id": products[ticker].get("venue_market_id"),
                        "venue_market_id_authority": products[ticker].get("venue_market_id_authority"),
                        "input_product_entry_sha256": product_entry_hash,
                    },
                    "segment_identity": {
                        "book_segment_id": cursor.segment_id,
                        "start_evidence": cursor.segment_start_evidence,
                        "continuity_claim": "valid_from_observed_snapshot_only",
                        "snapshot_seed_watermark": cursor.snapshot_seed_watermark.document(),
                        "valid_from_watermark": cursor.valid_from_watermark.document(),
                    },
                    "as_of": {
                        "logical_time_utc_ns": int_value(record.get("logical_time_utc_ns"), "logical_time_utc_ns"),
                        "capture_raw_ingress_watermark": raw_ordinal,
                        "normalization_watermark": normalization_ordinal,
                        "product_applied_watermark": cursor.product_applied_watermark.document(),
                    },
                    "trigger": {"kind": "market_event", "event_type": record.get("event_type")},
                    "truth": {
                        "truth_category": "Synthetic" if normalized.get("truth_category") == "Synthetic" else "Reconstructed",
                        "input_truth_category": normalized.get("truth_category"),
                        "source_fidelity": "level_2",
                        "derivation": "deterministic_from_normalized_market_events",
                    },
                    "completeness": {
                        "input": "complete_observed_interval",
                        "segment": "valid_from_observed_snapshot_only",
                    },
                    "limitations": limitations,
                    "lineage": lineage,
                    "values": cursor.projection.feature_values(),
                }
                validate_historical_schema(row, "feature-row-v2.schema.json", "FeatureRowSchemaMismatch")
                destination.write(canonical_json(row) + "\n")
                feature_count += 1
                product_rows[ticker] += 1
                first_watermarks.setdefault(ticker, cursor.product_applied_watermark.document())
                last_watermarks[ticker] = cursor.product_applied_watermark.document()
        if any(cursor.pending_boundary is not None for cursor in cursors.values()):
            raise HistoricalDataError("FeatureSegmentInvalid", "input ends with an unmatched segment boundary")
        manifest_products = []
        for ticker in tickers:
            entry = products[ticker]
            item = {
                "product_identity": entry,
                "input_product_entry_sha256": hashlib.sha256(canonical_json(entry).encode()).hexdigest(),
                "segments": product_segments[ticker],
                "row_count": product_rows[ticker],
                "first_product_applied_watermark": first_watermarks.get(ticker),
                "last_product_applied_watermark": last_watermarks.get(ticker),
            }
            reviewed = lineage_by_ticker.get(ticker)
            if reviewed is not None:
                item["reviewed_lineage"] = {**reviewed, "conversion_policy_sha256": conversion_hash}
            manifest_products.append(item)
        manifest = {
            "schema": FEATURE_MANIFEST_V3_SCHEMA,
            "feature_version": FEATURE_V2_VERSION,
            "input": {
                "normalization_schema": NORMALIZATION_MANIFEST_V3_SCHEMA,
                "normalization_manifest_sha256": sha256_file(manifest_path),
                "records_sha256": sha256_file(records_path),
                "source_scopes_sha256": sha256_file(scopes_path),
                "product_map_sha256": sha256_file(product_path),
                "capture_identity": {
                    "frames_sha256": normalized.get("input_frames_sha256"),
                    "metadata_sha256": normalized.get("input_capture_metadata_sha256"),
                },
                "completeness": "complete_observed_interval",
                "market_tickers": tickers,
            },
            "ordering": {
                "input": "normalization_ordinal_ascending",
                "output": ["normalization_ordinal", "ticker"],
            },
            "truth": {
                "truth_category": "Synthetic" if normalized.get("truth_category") == "Synthetic" else "Reconstructed",
                "input_truth_category": normalized.get("truth_category"),
                "source_fidelity": "level_2",
            },
            "completeness": "complete_observed_interval",
            "limitations": limitations,
            "feature_definitions": _feature_v3_definitions(),
            "products": manifest_products,
            "output": {
                "feature_rows_sha256": sha256_file(features_path),
                "feature_row_count": feature_count,
            },
        }
        if normalized.get("product_catalog_sha256") is not None:
            manifest["input"]["product_catalog_sha256"] = normalized["product_catalog_sha256"]
            manifest["input"]["conversion_policy_sha256"] = conversion_hash
        validate_historical_schema(manifest, "feature-manifest-v3.schema.json", "FeatureManifestSchemaMismatch")
        write_json(temporary / "manifest.json", manifest)
        temporary.rename(output_dir)
        return manifest
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def materialize_features(input_dir: Path, output_dir: Path) -> dict[str, Any]:
    input_dir = input_dir.resolve()
    events_path = input_dir / "events.jsonl"
    normalization_manifest = input_dir / "manifest.json"
    if not normalization_manifest.is_file():
        raise ValueError("input must be a normalized directory containing manifest.json")
    normalized = read_json(normalization_manifest)
    if normalized.get("schema") == NORMALIZATION_MANIFEST_V3_SCHEMA:
        raise HistoricalDataError(
            "DownstreamContinuityRequired",
            "normalization manifest V3 requires B2b segment-aware feature projection",
        )
    if not events_path.is_file():
        raise ValueError("input must be a normalized directory containing events.jsonl")
    if normalized.get("sequence_gaps"):
        raise ValueError("cannot materialize complete features from normalized data with sequence gaps")
    product_lineage: dict[str, Any] | None = None
    if normalized.get("schema") == "pmm.historical.normalization_manifest.v2":
        package = ProductPackage.load(input_dir / "product_terms")
        policy = ConversionPolicy.load(input_dir / "conversion_policy.json")
        expected_lineage = {
            "product_terms_sha256": package.terms.payload_sha256,
            "source_manifest_sha256": package.evidence.payload_sha256,
            "review_sha256": package.review.payload_sha256,
            "conversion_policy_sha256": policy.payload_sha256,
        }
        for name, value in expected_lineage.items():
            if normalized.get(name) != value:
                raise ProductTermsError("UpstreamManifestMismatch", f"normalization manifest {name} is stale")
        if normalized.get("output_events_sha256") != sha256_file(events_path):
            raise ProductTermsError("UpstreamManifestMismatch", "normalized events hash is stale")
        if normalized.get("output_product_sha256") != sha256_file(input_dir / "product.json"):
            raise ProductTermsError("UpstreamManifestMismatch", "product identity hash is stale")
        product_lineage = expected_lineage
    elif normalized.get("schema") != "pmm.historical.normalization_manifest.v1":
        raise ValueError("unsupported normalization manifest schema")
    output_dir = ensure_new_output(output_dir)
    temporary = output_dir.with_name(f"{output_dir.name}.partial")
    if temporary.exists():
        raise ValueError(f"temporary feature output already exists: {temporary}")
    temporary.mkdir(parents=True)
    cursor = ObservedMarketCursor()
    feature_count = 0
    features_path = temporary / "features.jsonl"
    try:
        with features_path.open("x", encoding="utf-8") as destination:
            for event in iter_jsonl(events_path):
                cursor.advance(event)
                if not cursor.projection.has_snapshot:
                    continue
                feature_count += 1
                row = {
                    "schema": FEATURE_SCHEMA,
                    "feature_version": FEATURE_VERSION,
                    "truth_category": "DerivedFromObserved",
                    "source_fidelity": "level_2",
                    "ticker": event["ticker"],
                    "as_of_watermark": event["ingress_order"],
                    "as_of_logical_time_utc_ns": event["logical_time_utc_ns"],
                    "as_of_event_type": event["event_type"],
                    "causal_inputs": "events up to and including as_of_watermark",
                    "values": cursor.projection.feature_values(),
                }
                destination.write(canonical_json(row) + "\n")
        manifest = {
            "schema": "pmm.historical.feature_manifest.v2" if product_lineage is not None else "pmm.historical.feature_manifest.v1",
            "feature_version": FEATURE_VERSION,
            "input_events_sha256": sha256_file(events_path),
            "output_features_sha256": sha256_file(features_path),
            "feature_count": feature_count,
            "causal_availability": "Each row contains only state applied through as_of_watermark.",
            "leakage_prevention": "No future returns, future book state, or post-watermark data are features.",
            "truth_category": "DerivedFromObserved",
            "source_fidelity": "level_2",
        }
        if product_lineage is not None:
            manifest.update(product_lineage)
            manifest["input_normalization_manifest_sha256"] = sha256_file(normalization_manifest)
            manifest["input_product_sha256"] = sha256_file(input_dir / "product.json")
        write_json(temporary / "manifest.json", manifest)
        temporary.rename(output_dir)
        return manifest
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


@dataclass
class BacktestOrder:
    order_id: int
    side: str
    price: Decimal
    remaining: Decimal
    active_at_ns: int
    expires_at_ns: int
    created_from_watermark: int


@dataclass
class BacktestRisk:
    maximum_absolute_position: Decimal
    maximum_active_orders: int
    position: Decimal = Decimal(0)

    def admit(self, client_intent_id: int, side: str, quantity: Decimal, price: Decimal,
              submitted_at_ns: int, active_orders: Iterable[BacktestOrder]) -> str | None:
        del client_intent_id, price, submitted_at_ns
        active = list(active_orders)
        if len(active) >= self.maximum_active_orders:
            return "active_order_limit"
        pending_buy = sum((order.remaining for order in active if order.side == "buy"), Decimal(0))
        pending_sell = sum((order.remaining for order in active if order.side == "sell"), Decimal(0))
        projected = self.position + pending_buy + quantity if side == "buy" else self.position - pending_sell - quantity
        if abs(projected) > self.maximum_absolute_position:
            return "position_limit"
        return None

    def acknowledge(self, order: BacktestOrder) -> None:
        del order

    def apply_fill(self, order: BacktestOrder, quantity: Decimal) -> None:
        self.position += quantity if order.side == "buy" else -quantity

    def cancel(self, order: BacktestOrder, reason: str = "cancellation") -> None:
        del order, reason

    def close(self) -> None:
        return


def integer_units(value: Decimal, field_name: str) -> int:
    if value != value.to_integral_value():
        raise ValueError(f"{field_name} must be an integer for cxx_oracle_v1")
    return int(value)


class CxxRiskOracle:
    """Minimal deterministic bridge to the canonical C++ AccountRiskProjection."""

    def __init__(self, config: dict[str, Any], *, canonical_trace: bool = False) -> None:
        self.canonical_trace = canonical_trace
        self.trace: list[dict[str, Any]] = []
        executable = self._resolve_executable(config)
        risk = config.get("limits")
        if not isinstance(risk, dict):
            raise ValueError("risk.limits is required for cxx_oracle_v1")
        self.process = subprocess.Popen(
            [str(executable)], text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, bufsize=1,
        )
        self.sequence = 0
        self.pending_clients: dict[int, int] = {}
        binding = config.get("binding", {})
        if not isinstance(binding, dict):
            raise ValueError("risk.binding must be an object")
        account_id = int_value(binding.get("account_id", 1), "risk.binding.account_id")
        strategy_id = int_value(binding.get("strategy_id", 1), "risk.binding.strategy_id")
        trader_id = int_value(binding.get("trader_id", 1), "risk.binding.trader_id")
        contract_id = int_value(binding.get("contract_id", 1), "risk.binding.contract_id")
        if min(account_id, strategy_id, trader_id, contract_id) <= 0:
            raise ValueError("risk binding identifiers must be positive")
        self._send(
            f"INIT {account_id} {strategy_id} {trader_id} {contract_id} "
            f"{int_config({'value': risk['maximum_order_quantity_contracts']}, 'value')} "
            f"{int_config({'value': risk['maximum_absolute_position_contracts']}, 'value')} "
            f"{int_config({'value': risk['maximum_buy_exposure_contracts']}, 'value')} "
            f"{int_config({'value': risk['maximum_sell_exposure_contracts']}, 'value')} "
            f"{int_config({'value': risk['maximum_pending_exposure_contracts']}, 'value')} "
            f"{int_config({'value': risk['maximum_active_orders']}, 'value')}"
        )
        if self._receive() != "READY":
            raise ValueError("C++ risk oracle did not initialize")
        self._record("init", {"engine": "cxx_oracle_v2" if canonical_trace else "cxx_oracle_v1"},
                     "ready")

    @staticmethod
    def _resolve_executable(config: dict[str, Any]) -> Path:
        executable_value = config.get("oracle_executable")
        if isinstance(executable_value, str) and executable_value:
            executable = (REPOSITORY_ROOT / executable_value).resolve()
            if executable.is_file():
                return executable
            raise ValueError(f"C++ risk oracle does not exist: {executable}")
        launcher = config.get("oracle")
        if not isinstance(launcher, dict) or launcher.get("schema") != "pmm.risk_oracle_launcher.v1":
            raise ValueError("risk.oracle must use schema pmm.risk_oracle_launcher.v1")
        build_dir_value = launcher.get("build_dir")
        target = launcher.get("cmake_target")
        if not isinstance(build_dir_value, str) or not build_dir_value or target != "pmm_risk_oracle":
            raise ValueError("risk.oracle requires build_dir and cmake_target pmm_risk_oracle")
        build_dir = (REPOSITORY_ROOT / build_dir_value).resolve()
        try:
            build_dir.relative_to(REPOSITORY_ROOT)
        except ValueError as error:
            raise ValueError("risk.oracle.build_dir must be inside the repository") from error
        if not (build_dir / "CMakeCache.txt").is_file():
            raise ValueError(f"CMake build directory is not configured: {build_dir}")
        try:
            subprocess.run(["cmake", "--build", str(build_dir), "--target", target], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        except (OSError, subprocess.CalledProcessError) as error:
            raise ValueError("failed to build pmm_risk_oracle through the configured CMake target") from error
        path_file = build_dir / "pmm_risk_oracle.path"
        if not path_file.is_file():
            raise ValueError("configured CMake build did not produce pmm_risk_oracle.path")
        executable = Path(path_file.read_text(encoding="utf-8").strip()).resolve()
        try:
            executable.relative_to(build_dir)
        except ValueError as error:
            raise ValueError("CMake oracle target resolved outside its configured build directory") from error
        if not executable.is_file():
            raise ValueError(f"CMake oracle target does not exist: {executable}")
        return executable

    def _record(self, operation: str, input_value: dict[str, Any], result: str) -> None:
        if not self.canonical_trace:
            return
        self.trace.append({
            "schema": RISK_TRACE_SCHEMA,
            "step": len(self.trace) + 1,
            "operation": operation,
            "truth_category": "ModelDerived" if operation != "init" else "NotApplicable",
            "input": input_value,
            "result": result,
            "state": self.view(),
        })

    def _send(self, line: str) -> None:
        if self.process.stdin is None:
            raise ValueError("C++ risk oracle stdin is unavailable")
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()

    def _receive(self) -> str:
        if self.process.stdout is None:
            raise ValueError("C++ risk oracle stdout is unavailable")
        line = self.process.stdout.readline().strip()
        if not line:
            raise ValueError("C++ risk oracle terminated without a response")
        if line.startswith("ERROR "):
            raise ValueError(f"C++ risk oracle: {line[6:]}")
        return line

    def admit(self, client_intent_id: int, side: str, quantity: Decimal, price: Decimal,
              submitted_at_ns: int, active_orders: Iterable[BacktestOrder]) -> str | None:
        del active_orders
        quantity_units = integer_units(quantity, "strategy.quote_quantity_contracts")
        price_units = integer_units(price * Decimal(100), "order price in cents")
        self._send(f"ADMIT {client_intent_id} {side} {quantity_units} {price_units} {submitted_at_ns}")
        response = self._receive().split()
        if response[:2] == ["ADMISSION", "approved"]:
            self.pending_clients[client_intent_id] = client_intent_id
            self._record("admit", {"client_intent_id": client_intent_id, "side": side,
                                    "quantity_contracts": format(quantity, "f"),
                                    "price_dollars": format(price, "f"), "time_utc_ns": submitted_at_ns},
                         "approved")
            return None
        if response[:2] == ["ADMISSION", "rejected"]:
            rejection = f"cxx_risk_{response[3]}"
            self._record("admit", {"client_intent_id": client_intent_id, "side": side,
                                    "quantity_contracts": format(quantity, "f"),
                                    "price_dollars": format(price, "f"), "time_utc_ns": submitted_at_ns},
                         rejection)
            return rejection
        raise ValueError(f"unexpected C++ risk admission response: {' '.join(response)}")

    def acknowledge(self, order: BacktestOrder) -> None:
        client = self.pending_clients.pop(order.order_id)
        self._send(f"BIND {client} {order.order_id}")
        self._expect_applied_or_bound("BOUND")
        self._record("bind_ingress", {"client_intent_id": client,
                                       "ingress_sequence": order.order_id}, "bound")
        self.sequence += 1
        price_units = integer_units(order.price * Decimal(100), "order price in cents")
        quantity_units = integer_units(order.remaining, "order quantity")
        self._send(
            f"ACK {self.sequence} {order.order_id} {order.order_id} {order.side} "
            f"{quantity_units} {price_units} {order.active_at_ns}"
        )
        self._expect_applied_or_bound("APPLIED")
        self._record("acknowledge", {"order_id": order.order_id, "ingress_sequence": order.order_id,
                                      "side": order.side, "quantity_contracts": format(order.remaining, "f"),
                                      "price_dollars": format(order.price, "f"),
                                      "time_utc_ns": order.active_at_ns}, "applied")

    def apply_fill(
        self, order: BacktestOrder, quantity: Decimal, time_ns: int | None = None
    ) -> None:
        self.sequence += 1
        price_units = integer_units(order.price * Decimal(100), "fill price in cents")
        quantity_units = integer_units(quantity, "fill quantity")
        self._send(
            f"FILL {self.sequence} {order.order_id} {order.side} {quantity_units} "
            f"{price_units} {order.active_at_ns if time_ns is None else time_ns}"
        )
        self._expect_applied_or_bound("APPLIED")
        self._record("fill", {"order_id": order.order_id, "side": order.side,
                               "quantity_contracts": format(quantity, "f"),
                               "price_dollars": format(order.price, "f"),
                               "time_utc_ns": order.active_at_ns if time_ns is None else time_ns},
                     "applied")

    def cancel(
        self, order: BacktestOrder, reason: str = "cancellation", time_ns: int | None = None
    ) -> None:
        self.sequence += 1
        occurred_at = order.expires_at_ns if time_ns is None else time_ns
        self._send(f"CANCEL {self.sequence} {order.order_id} {occurred_at}")
        self._expect_applied_or_bound("APPLIED")
        self._record("expire" if reason == "logical_expiry" else "cancel",
                     {"order_id": order.order_id, "reason": reason,
                      "time_utc_ns": occurred_at}, "applied")

    def reject_pending(self, order: BacktestOrder, time_ns: int) -> None:
        client = self.pending_clients.pop(order.order_id)
        self._send(f"BIND {client} {order.order_id}")
        self._expect_applied_or_bound("BOUND")
        self._record(
            "bind_ingress",
            {"client_intent_id": client, "ingress_sequence": order.order_id},
            "bound",
        )
        self.sequence += 1
        self._send(f"REJECT {self.sequence} {order.order_id} {time_ns}")
        self._expect_applied_or_bound("APPLIED")
        self._record(
            "command_reject",
            {"ingress_sequence": order.order_id, "time_utc_ns": time_ns},
            "applied",
        )

    @property
    def position(self) -> Decimal:
        return Decimal(self.view()["net_position_contracts"])

    def view(self) -> dict[str, Any]:
        self._send("SNAPSHOT")
        try:
            value = json.loads(self._receive())
        except json.JSONDecodeError as error:
            raise ValueError("unexpected C++ risk snapshot response") from error
        if not isinstance(value, dict) or not isinstance(value.get("live_orders"), list) or not isinstance(value.get("pending_orders"), list):
            raise ValueError("unexpected C++ risk snapshot response")
        value["event_watermark"] = int_value(value.get("event_watermark"), "event_watermark")
        return value

    def _expect_applied_or_bound(self, prefix: str) -> None:
        response = self._receive().split()
        if not response or response[0] != prefix:
            raise ValueError(f"unexpected C++ risk oracle response: {' '.join(response)}")

    def close(self) -> None:
        if self.process.stdin is not None:
            self.process.stdin.close()
        return_code = self.process.wait(timeout=5)
        if self.process.stdout is not None:
            self.process.stdout.close()
        if self.process.stderr is not None:
            self.process.stderr.close()
        if return_code != 0:
            raise ValueError(f"C++ risk oracle exited with status {return_code}")


@dataclass
class ResearchLedger:
    enabled: bool
    fee_per_contract: Decimal = Decimal(0)
    cash_balance: Decimal = Decimal(0)
    total_fees: Decimal = Decimal(0)
    entries: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "ResearchLedger":
        accounting = config.get("accounting")
        if accounting is None:
            return cls(enabled=False)
        if not isinstance(accounting, dict) or accounting.get("schema") != "pmm.accounting_policy.v1":
            raise ValueError("accounting must use schema pmm.accounting_policy.v1")
        if accounting.get("settlement_status") != "unresolved":
            raise ValueError("V1 accounting supports only unresolved settlement")
        return cls(enabled=True, fee_per_contract=decimal_config(accounting, "fee_per_contract_dollars"))

    def apply_fill(self, order: BacktestOrder, quantity: Decimal, time_ns: int) -> None:
        if not self.enabled:
            return
        notional = order.price * quantity
        fee = self.fee_per_contract * quantity
        cash_delta = -(notional + fee) if order.side == "buy" else notional - fee
        self.cash_balance += cash_delta
        self.total_fees += fee
        self.entries.append({
            "kind": "model_fill_cashflow", "truth_category": "ModelDerived",
            "time_utc_ns": time_ns, "order_id": order.order_id, "side": order.side,
            "quantity_contracts": format(quantity, "f"), "price_dollars": format(order.price, "f"),
            "notional_dollars": format(notional, "f"), "fee_dollars": format(fee, "f"),
            "cash_delta_dollars": format(cash_delta, "f"),
            "policy_note": "Unresolved synthetic ledger; it is not settlement or venue PnL.",
        })


def decimal_config(config: dict[str, Any], path: str) -> Decimal:
    current: Any = config
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"backtest config requires {path}")
        current = current[part]
    return Decimal(str(current))


def int_config(config: dict[str, Any], path: str) -> int:
    return int_value(decimal_config(config, path), path)


def feature_by_watermark(features_path: Path) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for row in iter_jsonl(features_path):
        watermark = int_value(row.get("as_of_watermark"), "as_of_watermark")
        if watermark in result:
            raise ValueError("features repeat a watermark")
        result[watermark] = row
    return result


def verify_v3_lineage(
    config: dict[str, Any], normalized_path: Path, features_path: Path
) -> tuple[ProductPackage, ConversionPolicy, dict[str, Any]]:
    normalization_manifest_path = (
        REPOSITORY_ROOT / str(config.get("normalization_manifest", ""))
    ).resolve()
    feature_manifest_path = (
        REPOSITORY_ROOT / str(config.get("feature_manifest", ""))
    ).resolve()
    if not normalization_manifest_path.is_file() or not feature_manifest_path.is_file():
        raise ProductTermsError(
            "UpstreamManifestMismatch", "pmm.backtest.v3 requires normalization and feature manifests"
        )
    if normalization_manifest_path.parent / "events.jsonl" != normalized_path:
        raise ProductTermsError(
            "UpstreamManifestMismatch", "normalization manifest does not own normalized_events"
        )
    if feature_manifest_path.parent / "features.jsonl" != features_path:
        raise ProductTermsError(
            "UpstreamManifestMismatch", "feature manifest does not own features"
        )
    normalization = read_json(normalization_manifest_path)
    features = read_json(feature_manifest_path)
    if normalization.get("schema") != "pmm.historical.normalization_manifest.v2":
        raise ProductTermsError(
            "UnsupportedTermsSchema", "pmm.backtest.v3 requires normalization manifest V2"
        )
    if features.get("schema") != "pmm.historical.feature_manifest.v2":
        raise ProductTermsError(
            "UnsupportedTermsSchema", "pmm.backtest.v3 requires feature manifest V2"
        )
    package = ProductPackage.load(normalization_manifest_path.parent / "product_terms")
    policy = ConversionPolicy.load(normalization_manifest_path.parent / "conversion_policy.json")
    policy.require_core_compatible(package.terms)
    expected = {
        "product_terms_sha256": package.terms.payload_sha256,
        "source_manifest_sha256": package.evidence.payload_sha256,
        "review_sha256": package.review.payload_sha256,
        "conversion_policy_sha256": policy.payload_sha256,
    }
    declared = config.get("product_terms")
    if not isinstance(declared, dict) or set(declared) != set(expected):
        raise ProductTermsError(
            "TermsHashMismatch", "pmm.backtest.v3 must declare the complete product_terms identity"
        )
    mismatch_codes = {
        "product_terms_sha256": "TermsHashMismatch",
        "source_manifest_sha256": "SourceHashMismatch",
        "review_sha256": "ReviewHashMismatch",
        "conversion_policy_sha256": "ConversionPolicyMismatch",
    }
    for name, value in expected.items():
        if declared.get(name) != value:
            raise ProductTermsError(
                mismatch_codes[name], f"config {name} differs from the reviewed package"
            )
        if normalization.get(name) != value or features.get(name) != value:
            raise ProductTermsError(
                "UpstreamManifestMismatch", f"upstream manifest {name} differs from the reviewed package"
            )
    if normalization.get("output_events_sha256") != sha256_file(normalized_path):
        raise ProductTermsError("UpstreamManifestMismatch", "normalized events hash is stale")
    product_path = normalization_manifest_path.parent / "product.json"
    if normalization.get("output_product_sha256") != sha256_file(product_path):
        raise ProductTermsError("UpstreamManifestMismatch", "normalized product identity hash is stale")
    if normalization.get("product_terms_file_sha256") != sha256_file(
        normalization_manifest_path.parent / "product_terms" / "product_terms.json"
    ):
        raise ProductTermsError("UpstreamManifestMismatch", "copied product terms file hash is stale")
    if normalization.get("conversion_policy_file_sha256") != sha256_file(
        normalization_manifest_path.parent / "conversion_policy.json"
    ):
        raise ProductTermsError("UpstreamManifestMismatch", "copied conversion policy file hash is stale")
    if features.get("input_events_sha256") != sha256_file(normalized_path):
        raise ProductTermsError("UpstreamManifestMismatch", "feature input events hash is stale")
    if features.get("output_features_sha256") != sha256_file(features_path):
        raise ProductTermsError("UpstreamManifestMismatch", "features hash is stale")
    if features.get("input_product_sha256") != sha256_file(product_path):
        raise ProductTermsError("UpstreamManifestMismatch", "feature product identity hash is stale")
    normalization_manifest_sha256 = sha256_file(normalization_manifest_path)
    if features.get("input_normalization_manifest_sha256") != normalization_manifest_sha256:
        raise ProductTermsError(
            "UpstreamManifestMismatch", "feature manifest does not bind the normalization manifest"
        )
    return package, policy, {
        **expected,
        "normalization_manifest_sha256": normalization_manifest_sha256,
        "feature_manifest_sha256": sha256_file(feature_manifest_path),
    }


def verify_lineage(config_path: Path, result_dir: Path | None = None) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = read_json(config_path)
    if config.get("schema") != BACKTEST_V3_SCHEMA:
        raise ProductTermsError(
            "UnsupportedTermsSchema", "lineage verification requires pmm.backtest.v3"
        )
    normalized_path = (REPOSITORY_ROOT / str(config.get("normalized_events", ""))).resolve()
    features_path = (REPOSITORY_ROOT / str(config.get("features", ""))).resolve()
    package, policy, lineage = verify_v3_lineage(config, normalized_path, features_path)
    result: dict[str, Any] = {
        "status": "valid",
        "market_ticker": package.terms.market_ticker,
        **lineage,
        "fee_application": policy.payload["fee_application"],
        "settlement_application": policy.payload["settlement_application"],
    }
    if result_dir is None:
        return result
    resolved_result = result_dir.resolve()
    manifest_path = resolved_result / "manifest.json"
    manifest = read_json(manifest_path)
    if manifest.get("schema") != "pmm.backtest_result_manifest.v3":
        raise ProductTermsError(
            "UnsupportedTermsSchema", "result directory does not contain a V3 result manifest"
        )
    if manifest.get("config_sha256") != sha256_file(config_path):
        raise ProductTermsError("UpstreamManifestMismatch", "result config hash is stale")
    for name, value in lineage.items():
        if manifest.get(name) != value:
            raise ProductTermsError(
                "UpstreamManifestMismatch", f"result manifest {name} differs from verified lineage"
            )
    if manifest.get("normalized_events_sha256") != sha256_file(normalized_path):
        raise ProductTermsError("UpstreamManifestMismatch", "result normalized events hash is stale")
    if manifest.get("features_sha256") != sha256_file(features_path):
        raise ProductTermsError("UpstreamManifestMismatch", "result features hash is stale")
    expected_metadata = {
        "product_identity": package.terms.identity,
        "product_terms_effective": package.terms.payload["effective"],
        "product_terms_review_limitations": package.review.payload["limitations"],
        "fee_application": policy.payload["fee_application"],
        "settlement_application": policy.payload["settlement_application"],
    }
    for name, value in expected_metadata.items():
        if manifest.get(name) != value:
            raise ProductTermsError(
                "UpstreamManifestMismatch", f"result manifest {name} differs from verified product metadata"
            )
    output_names = {
        "orders_sha256": "orders.jsonl",
        "fills_sha256": "fills.jsonl",
        "ledger_sha256": "ledger.jsonl",
        "risk_trace_sha256": "risk-trace.jsonl",
    }
    for field_name, filename in output_names.items():
        path = resolved_result / filename
        if not path.is_file() or manifest.get(field_name) != sha256_file(path):
            raise ProductTermsError(
                "UpstreamManifestMismatch", f"result artifact {filename} has a stale hash"
            )
    result["result_manifest_sha256"] = sha256_file(manifest_path)
    return result


def run_backtest(config_path: Path, output_dir: Path) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = read_json(config_path)
    config_schema = config.get("schema")
    if config_schema not in {BACKTEST_SCHEMA, BACKTEST_V2_SCHEMA, BACKTEST_V3_SCHEMA}:
        raise ValueError(
            f"backtest config schema must be {BACKTEST_SCHEMA}, {BACKTEST_V2_SCHEMA}, or {BACKTEST_V3_SCHEMA}"
        )
    if config_schema in {BACKTEST_V2_SCHEMA, BACKTEST_V3_SCHEMA}:
        declared_risk = config.get("risk")
        if not isinstance(declared_risk, dict) or declared_risk.get("engine") != "cxx_oracle_v2":
            raise ValueError(f"{config_schema} requires risk.engine cxx_oracle_v2")
    fill_model = config.get("fill_model")
    if fill_model not in {"no_fill_v1", "trade_touch_v1"}:
        raise ValueError("fill_model must be no_fill_v1 or trade_touch_v1")
    normalized_path = (REPOSITORY_ROOT / str(config.get("normalized_events", ""))).resolve()
    features_path = (REPOSITORY_ROOT / str(config.get("features", ""))).resolve()
    if not normalized_path.is_file() or not features_path.is_file():
        raise ValueError("backtest config must reference existing normalized_events and features files")
    product_package: ProductPackage | None = None
    conversion_policy: ConversionPolicy | None = None
    product_lineage: dict[str, Any] | None = None
    if config_schema == BACKTEST_V3_SCHEMA:
        if config.get("accounting") is not None:
            raise ProductTermsError(
                "FeePolicyUnsupported", "pmm.backtest.v3 does not apply fees or accounting"
            )
        product_package, conversion_policy, product_lineage = verify_v3_lineage(
            config, normalized_path, features_path
        )
    output_dir = ensure_new_output(output_dir)
    temporary = output_dir.with_name(f"{output_dir.name}.partial")
    if temporary.exists():
        raise ValueError(f"temporary backtest output already exists: {temporary}")
    features = feature_by_watermark(features_path)
    market_data_latency = int_config(config, "latency.market_data_ns")
    decision_latency = int_config(config, "latency.decision_ns")
    order_latency = int_config(config, "latency.order_ns")
    decision_interval = int_config(config, "strategy.decision_interval_ns")
    lifetime = int_config(config, "strategy.order_lifetime_ns")
    minimum_spread = decimal_config(config, "strategy.minimum_spread_dollars")
    quantity = decimal_config(config, "strategy.quote_quantity_contracts")
    if quantity <= 0 or lifetime <= 0 or decision_interval <= 0:
        raise ValueError("quote quantity, order lifetime, and decision interval must be positive")
    if conversion_policy is not None:
        conversion_policy.convert_quantity_to_contracts(quantity, "strategy.quote_quantity_contracts")
        conversion_policy.convert_price_to_cents(minimum_spread, "strategy.minimum_spread_dollars")
    risk_config = config.get("risk")
    if not isinstance(risk_config, dict):
        raise ValueError("backtest config requires risk")
    risk_kind = risk_config.get("engine", "python_reference_v1")
    if risk_kind == "python_reference_v1":
        if config_schema != BACKTEST_SCHEMA:
            raise ValueError(f"{config_schema} requires risk.engine cxx_oracle_v2")
        risk: BacktestRisk | CxxRiskOracle = BacktestRisk(
            maximum_absolute_position=decimal_config(config, "risk.maximum_absolute_position_contracts"),
            maximum_active_orders=int_config(config, "risk.maximum_active_orders"),
        )
        if risk.maximum_absolute_position <= 0 or risk.maximum_active_orders <= 0:
            raise ValueError("risk limits must be positive")
    elif risk_kind == "cxx_oracle_v1":
        if config_schema != BACKTEST_SCHEMA:
            raise ValueError("cxx_oracle_v1 is supported only by pmm.backtest.v1")
        risk = CxxRiskOracle(risk_config)
    elif risk_kind == "cxx_oracle_v2":
        if config_schema not in {BACKTEST_V2_SCHEMA, BACKTEST_V3_SCHEMA}:
            raise ValueError("cxx_oracle_v2 requires schema pmm.backtest.v2 or pmm.backtest.v3")
        risk_contract = risk_config.get("risk_contract")
        if not isinstance(risk_contract, dict) or risk_contract.get("schema") != "pmm.research_risk_contract.v1":
            raise ValueError("cxx_oracle_v2 requires risk.risk_contract schema pmm.research_risk_contract.v1")
        if risk_contract.get("quantity_unit") != "whole_contract" or risk_contract.get("price_unit") != "cent":
            raise ValueError("cxx_oracle_v2 supports only whole_contract quantities and cent prices")
        if risk_contract.get("post_only") is not True:
            raise ValueError("cxx_oracle_v2 requires post_only true")
        risk = CxxRiskOracle(risk_config, canonical_trace=True)
    else:
        raise ValueError("risk.engine must be python_reference_v1, cxx_oracle_v1, or cxx_oracle_v2")
    ledger = ResearchLedger.from_config(config)
    scheduled: list[tuple[int, int, dict[str, Any]]] = []
    active: dict[int, BacktestOrder] = {}
    next_decision_at = -1
    next_order_id = 1
    schedule_ordinal = 0
    decisions = 0
    rejections: Counter[str] = Counter()
    fills: list[dict[str, Any]] = []
    order_records: list[dict[str, Any]] = []
    cancellation_count = 0

    def schedule(at_ns: int, feature: dict[str, Any]) -> None:
        nonlocal schedule_ordinal
        schedule_ordinal += 1
        scheduled.append((at_ns, schedule_ordinal, feature))
        scheduled.sort(key=lambda item: (item[0], item[1]))

    def cancel_all(reason: str, now_ns: int) -> None:
        nonlocal cancellation_count
        for order in list(active.values()):
            risk.cancel(order, reason)
            order_records.append({
                "kind": "cancellation", "truth_category": "ModelDerived", "order_id": order.order_id,
                "time_utc_ns": now_ns, "reason": reason, "remaining_contracts": format(order.remaining, "f"),
            })
            del active[order.order_id]
            cancellation_count += 1

    def activate_due(now_ns: int) -> None:
        nonlocal decisions, next_order_id, cancellation_count
        for order in list(active.values()):
            if order.expires_at_ns <= now_ns:
                risk.cancel(order, "logical_expiry")
                order_records.append({
                    "kind": "cancellation", "truth_category": "ModelDerived", "order_id": order.order_id,
                    "time_utc_ns": now_ns, "reason": "logical_expiry", "remaining_contracts": format(order.remaining, "f"),
                })
                del active[order.order_id]
                cancellation_count += 1
        while scheduled and scheduled[0][0] <= now_ns:
            _, _, feature = scheduled.pop(0)
            decisions += 1
            values = feature["values"]
            bid = values.get("best_yes_bid_dollars")
            ask = values.get("best_yes_ask_dollars")
            if bid is None or ask is None:
                rejections["missing_two_sided_book"] += 1
                continue
            bid_price, ask_price = Decimal(str(bid)), Decimal(str(ask))
            if ask_price - bid_price < minimum_spread or bid_price >= ask_price:
                rejections["post_only_or_spread"] += 1
                continue
            cancel_all("quote_replacement", now_ns)
            for side, price in (("buy", bid_price), ("sell", ask_price)):
                # The research order ID is also its stable client-intent and ingress correlation.
                # A rejected intent has no reservation, so retrying that unused ID is safe.
                client_intent_id = next_order_id
                rejection = risk.admit(client_intent_id, side, quantity, price, now_ns, active.values())
                if rejection is not None:
                    rejections[rejection] += 1
                    continue
                order = BacktestOrder(
                    order_id=next_order_id, side=side, price=price, remaining=quantity,
                    active_at_ns=now_ns, expires_at_ns=now_ns + lifetime,
                    created_from_watermark=int_value(feature["as_of_watermark"], "as_of_watermark"),
                )
                active[order.order_id] = order
                risk.acknowledge(order)
                order_records.append({
                    "kind": "order_accepted", "truth_category": "ModelDerived", "order_id": order.order_id,
                    "side": side, "price_dollars": format(price, "f"), "quantity_contracts": format(quantity, "f"),
                    "active_at_utc_ns": now_ns, "expires_at_utc_ns": order.expires_at_ns,
                    "feature_watermark": order.created_from_watermark, "post_only": True,
                })
                next_order_id += 1

    def apply_trade_fills(event: dict[str, Any]) -> None:
        if fill_model != "trade_touch_v1" or event.get("event_type") != "trade":
            return
        payload = event["payload"]
        trade_price = Decimal(str(payload["yes_price_dollars"]))
        remaining_trade = Decimal(str(payload["quantity_contracts"]))
        for order in sorted(active.values(), key=lambda value: value.order_id):
            eligible = (order.side == "buy" and trade_price <= order.price) or (
                order.side == "sell" and trade_price >= order.price
            )
            if not eligible or remaining_trade <= 0:
                continue
            filled = min(order.remaining, remaining_trade)
            order.remaining -= filled
            remaining_trade -= filled
            risk.apply_fill(order, filled)
            ledger.apply_fill(order, filled, int_value(event["logical_time_utc_ns"], "logical_time_utc_ns"))
            fills.append({
                "truth_category": "ModelDerived", "fill_model": "trade_touch_v1",
                "order_id": order.order_id, "side": order.side, "price_dollars": format(order.price, "f"),
                "quantity_contracts": format(filled, "f"), "trade_event_id": event["event_id"],
                "trade_yes_price_dollars": format(trade_price, "f"),
                "time_utc_ns": event["logical_time_utc_ns"],
                "assumption": "A qualifying public trade consumes displayed simulated size without queue-position modelling.",
            })
            if order.remaining == 0:
                del active[order.order_id]

    temporary.mkdir(parents=True)
    try:
        for event in iter_jsonl(normalized_path):
            watermark = int_value(event.get("ingress_order"), "ingress_order")
            event_time = int_value(event.get("logical_time_utc_ns"), "logical_time_utc_ns")
            activate_due(event_time)
            apply_trade_fills(event)
            feature = features.get(watermark)
            if feature is None:
                raise ValueError(f"feature dataset is missing watermark {watermark}")
            available_at = event_time + market_data_latency
            if available_at >= next_decision_at:
                schedule(available_at + decision_latency + order_latency, feature)
                next_decision_at = available_at + decision_interval
        if scheduled:
            activate_due(max(value[0] for value in scheduled))
        orders_path = temporary / "orders.jsonl"
        fills_path = temporary / "fills.jsonl"
        ledger_path = temporary / "ledger.jsonl"
        risk_trace_path = temporary / "risk-trace.jsonl"
        with orders_path.open("x", encoding="utf-8") as destination:
            for record in order_records:
                destination.write(canonical_json(record) + "\n")
        with fills_path.open("x", encoding="utf-8") as destination:
            for record in fills:
                destination.write(canonical_json(record) + "\n")
        with ledger_path.open("x", encoding="utf-8") as destination:
            for record in ledger.entries:
                destination.write(canonical_json(record) + "\n")
        with risk_trace_path.open("x", encoding="utf-8") as destination:
            if isinstance(risk, CxxRiskOracle):
                for record in risk.trace:
                    destination.write(canonical_json(record) + "\n")
        fill_assumption = (
            "trade_touch_v1 allocates qualifying public trade quantity to simulated orders by deterministic order id."
            if fill_model == "trade_touch_v1"
            else "no_fill_v1 never creates simulated fills; it is the execution-free control."
        )
        manifest = {
            "schema": (
                "pmm.backtest_result_manifest.v3"
                if config_schema == BACKTEST_V3_SCHEMA
                else "pmm.backtest_result_manifest.v2"
                if config_schema == BACKTEST_V2_SCHEMA
                else "pmm.backtest_result_manifest.v1"
            ),
            "config_sha256": sha256_file(config_path),
            "normalized_events_sha256": sha256_file(normalized_path),
            "features_sha256": sha256_file(features_path),
            "run_id": config.get("run_id"),
            "seed": config.get("seed"),
            "source_fidelity": "level_2",
            "market_truth": "Observed",
            "execution_truth": "ModelDerived",
            "fill_model": fill_model,
            "risk_engine": risk_kind,
            "risk_trace_schema": RISK_TRACE_SCHEMA if isinstance(risk, CxxRiskOracle) and risk.canonical_trace else None,
            "latency": config["latency"],
            "accounting": {
                "enabled": ledger.enabled,
                "settlement_status": "unresolved" if ledger.enabled else "not_configured",
                "cash_balance_dollars": format(ledger.cash_balance, "f") if ledger.enabled else None,
                "total_fees_dollars": format(ledger.total_fees, "f") if ledger.enabled else None,
                "claim": "Policy cashflows only; no settlement or PnL claim.",
            },
            "assumptions": [
                "Observed Level-2 book data is not replayed through ExchangeSimulator.",
                "No queue position, hidden liquidity, venue acknowledgement, fees, PnL, collateral, or settlement is modelled.",
                fill_assumption,
            ],
            "metrics": {
                "decisions": decisions,
                "accepted_orders": sum(1 for record in order_records if record["kind"] == "order_accepted"),
                "cancellations": cancellation_count,
                "model_derived_fills": len(fills),
                "final_inventory_contracts": format(risk.position, "f"),
                "active_orders_at_end": len(active),
                "admission_rejections": dict(sorted(rejections.items())),
            },
            "orders_sha256": sha256_file(orders_path),
            "fills_sha256": sha256_file(fills_path),
            "ledger_sha256": sha256_file(ledger_path),
            "risk_trace_sha256": sha256_file(risk_trace_path),
        }
        if product_lineage is not None:
            assert product_package is not None and conversion_policy is not None
            manifest.update(product_lineage)
            manifest["product_identity"] = product_package.terms.identity
            manifest["product_terms_effective"] = product_package.terms.payload["effective"]
            manifest["product_terms_review_limitations"] = product_package.review.payload["limitations"]
            manifest["fee_application"] = conversion_policy.payload["fee_application"]
            manifest["settlement_application"] = conversion_policy.payload["settlement_application"]
        write_json(temporary / "manifest.json", manifest)
        temporary.rename(output_dir)
        risk.close()
        return manifest
    except Exception:
        risk.close()
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 7 deterministic historical-data utilities.")
    commands = parser.add_subparsers(dest="command", required=True)
    normalize = commands.add_parser("normalize", help="Normalize an immutable raw capture into canonical events.")
    normalize.add_argument("--input", required=True, type=Path)
    normalize.add_argument("--output", required=True, type=Path)
    normalize.add_argument("--allow-sequence-gaps", action="store_true")
    normalize_v2 = commands.add_parser(
        "normalize-v2", help="Normalize with a reviewed authoritative product-term revision."
    )
    normalize_v2.add_argument("--input", required=True, type=Path)
    normalize_v2.add_argument("--output", required=True, type=Path)
    normalize_v2.add_argument("--catalog", required=True, type=Path)
    normalize_v2.add_argument("--conversion-policy", required=True, type=Path)
    normalize_v2.add_argument("--allow-sequence-gaps", action="store_true")
    normalize_v3 = commands.add_parser(
        "normalize-v3", help="Normalize V2 raw capture with explicit scopes and discontinuities."
    )
    normalize_v3.add_argument("--input", required=True, type=Path)
    normalize_v3.add_argument("--output", required=True, type=Path)
    normalize_v3.add_argument(
        "--continuity-policy", choices=("refuse", "record"), default="refuse"
    )
    normalize_v3.add_argument("--catalog", type=Path)
    normalize_v3.add_argument("--conversion-policy", type=Path)
    features = commands.add_parser("features", help="Materialize causal observed-L2 feature rows.")
    features.add_argument("--input", required=True, type=Path)
    features.add_argument("--output", required=True, type=Path)
    features_v3 = commands.add_parser(
        "features-v3", help="Materialize segment-aware per-market features from normalization V3."
    )
    features_v3.add_argument("--input", required=True, type=Path)
    features_v3.add_argument("--output", required=True, type=Path)
    backtest = commands.add_parser("backtest", help="Run an explicit deterministic research backtest.")
    backtest.add_argument("--config", required=True, type=Path)
    backtest.add_argument("--output", required=True, type=Path)
    backtest_v4 = commands.add_parser(
        "backtest-v4", help="Run the additive deterministic multi-market backtest."
    )
    backtest_v4.add_argument("--config", required=True, type=Path)
    backtest_v4.add_argument("--output", required=True, type=Path)
    verify_v4 = commands.add_parser(
        "verify-backtest-v4", help="Verify an additive multi-market result bundle offline."
    )
    verify_v4.add_argument("--config", required=True, type=Path)
    verify_v4.add_argument("--result", required=True, type=Path)
    verify = commands.add_parser(
        "verify-lineage", help="Verify a V3 configuration and optional result bundle offline."
    )
    verify.add_argument("--config", required=True, type=Path)
    verify.add_argument("--result", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.command == "normalize":
            result = normalize_capture(args.input, args.output, allow_sequence_gaps=args.allow_sequence_gaps)
        elif args.command == "normalize-v2":
            result = normalize_capture(
                args.input,
                args.output,
                allow_sequence_gaps=args.allow_sequence_gaps,
                product_catalog=ProductCatalog.load(args.catalog),
                conversion_policy=ConversionPolicy.load(args.conversion_policy),
            )
        elif args.command == "normalize-v3":
            if (args.catalog is None) != (args.conversion_policy is None):
                raise HistoricalDataError(
                    "ProductLineageIncomplete",
                    "--catalog and --conversion-policy must be provided together",
                )
            result = normalize_capture_v3(
                args.input,
                args.output,
                continuity_policy=args.continuity_policy,
                product_catalog=(
                    None if args.catalog is None else ProductCatalog.load(args.catalog)
                ),
                conversion_policy=(
                    None
                    if args.conversion_policy is None
                    else ConversionPolicy.load(args.conversion_policy)
                ),
            )
        elif args.command == "features":
            result = materialize_features(args.input, args.output)
        elif args.command == "features-v3":
            try:
                result = materialize_features_v3(args.input, args.output)
            except (HistoricalDataError, ValueError, ProductTermsError, KeyboardInterrupt):
                raise
            except Exception as error:
                print(
                    f"programming failure: {type(error).__name__}: {error}", file=sys.stderr
                )
                return 1
        elif args.command == "verify-lineage":
            result = verify_lineage(args.config, args.result)
        elif args.command == "backtest-v4":
            from pmm_phase7_multimarket import run_backtest_v4

            try:
                result = run_backtest_v4(args.config, args.output)
            except (HistoricalDataError, ValueError, ProductTermsError, KeyboardInterrupt):
                raise
            except Exception as error:
                print(
                    f"programming failure: {type(error).__name__}: {error}", file=sys.stderr
                )
                return 1
        elif args.command == "verify-backtest-v4":
            from pmm_phase7_multimarket import verify_backtest_v4

            result = verify_backtest_v4(args.config, args.result)
        else:
            result = run_backtest(args.config, args.output)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except KeyboardInterrupt:
        print("error: interrupted", file=sys.stderr)
        return 130
    except HistoricalDataError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except (ValueError, ProductTermsError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except (OSError, InvalidOperation) as error:
        print(f"programming failure: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
