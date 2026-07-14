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
import sys
from typing import Any, Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
NORMALIZED_SCHEMA = "pmm.historical.normalized_event.v1"
NORMALIZER_VERSION = "kalshi-l2-normalizer.v1"
FEATURE_SCHEMA = "pmm.historical.feature_row.v1"
FEATURE_VERSION = "observed-l2-top-of-book.v1"
BACKTEST_SCHEMA = "pmm.backtest.v1"


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


def normalize_capture(input_dir: Path, output_dir: Path, *, allow_sequence_gaps: bool = False) -> dict[str, Any]:
    input_dir = input_dir.resolve()
    frames = input_dir / "frames.jsonl"
    capture_metadata = input_dir / "metadata.json"
    if not frames.is_file() or not capture_metadata.is_file():
        raise ValueError("input must be a capture directory containing frames.jsonl and metadata.json")
    metadata = read_json(capture_metadata)
    ticker_from_metadata = metadata.get("ticker")
    if not isinstance(ticker_from_metadata, str) or not ticker_from_metadata:
        raise ValueError("capture metadata does not identify a ticker")
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
                if ticker != ticker_from_metadata:
                    raise ValueError(f"raw record {line_number} ticker conflicts with capture metadata")
                if market_id is None and parsed_market_id is None:
                    raise ValueError(f"raw record {line_number} has no market_id before identity is established")
                market_id_origin = "source_message" if parsed_market_id is not None else "capture_bound"
                if market_id is None:
                    assert parsed_market_id is not None
                    market_id = parsed_market_id
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
        manifest = {
            "schema": "pmm.historical.normalization_manifest.v1",
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
        write_json(temporary / "manifest.json", manifest)
        temporary.rename(output_dir)
        return manifest
    except Exception:
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


def materialize_features(input_dir: Path, output_dir: Path) -> dict[str, Any]:
    input_dir = input_dir.resolve()
    events_path = input_dir / "events.jsonl"
    normalization_manifest = input_dir / "manifest.json"
    if not events_path.is_file() or not normalization_manifest.is_file():
        raise ValueError("input must be a normalized directory containing events.jsonl and manifest.json")
    normalized = read_json(normalization_manifest)
    if normalized.get("sequence_gaps"):
        raise ValueError("cannot materialize complete features from normalized data with sequence gaps")
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
            "schema": "pmm.historical.feature_manifest.v1",
            "feature_version": FEATURE_VERSION,
            "input_events_sha256": sha256_file(events_path),
            "output_features_sha256": sha256_file(features_path),
            "feature_count": feature_count,
            "causal_availability": "Each row contains only state applied through as_of_watermark.",
            "leakage_prevention": "No future returns, future book state, or post-watermark data are features.",
            "truth_category": "DerivedFromObserved",
            "source_fidelity": "level_2",
        }
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

    def admit(self, side: str, quantity: Decimal, active_orders: Iterable[BacktestOrder]) -> str | None:
        active = list(active_orders)
        if len(active) >= self.maximum_active_orders:
            return "active_order_limit"
        pending_buy = sum((order.remaining for order in active if order.side == "buy"), Decimal(0))
        pending_sell = sum((order.remaining for order in active if order.side == "sell"), Decimal(0))
        projected = self.position + pending_buy + quantity if side == "buy" else self.position - pending_sell - quantity
        if abs(projected) > self.maximum_absolute_position:
            return "position_limit"
        return None


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


def run_backtest(config_path: Path, output_dir: Path) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = read_json(config_path)
    if config.get("schema") != BACKTEST_SCHEMA:
        raise ValueError(f"backtest config schema must be {BACKTEST_SCHEMA}")
    fill_model = config.get("fill_model")
    if fill_model not in {"no_fill_v1", "trade_touch_v1"}:
        raise ValueError("fill_model must be no_fill_v1 or trade_touch_v1")
    normalized_path = (REPOSITORY_ROOT / str(config.get("normalized_events", ""))).resolve()
    features_path = (REPOSITORY_ROOT / str(config.get("features", ""))).resolve()
    if not normalized_path.is_file() or not features_path.is_file():
        raise ValueError("backtest config must reference existing normalized_events and features files")
    output_dir = ensure_new_output(output_dir)
    temporary = output_dir.with_name(f"{output_dir.name}.partial")
    if temporary.exists():
        raise ValueError(f"temporary backtest output already exists: {temporary}")
    temporary.mkdir(parents=True)
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
    risk = BacktestRisk(
        maximum_absolute_position=decimal_config(config, "risk.maximum_absolute_position_contracts"),
        maximum_active_orders=int_config(config, "risk.maximum_active_orders"),
    )
    if risk.maximum_absolute_position <= 0 or risk.maximum_active_orders <= 0:
        raise ValueError("risk limits must be positive")
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
                rejection = risk.admit(side, quantity, active.values())
                if rejection is not None:
                    rejections[rejection] += 1
                    continue
                order = BacktestOrder(
                    order_id=next_order_id, side=side, price=price, remaining=quantity,
                    active_at_ns=now_ns, expires_at_ns=now_ns + lifetime,
                    created_from_watermark=int_value(feature["as_of_watermark"], "as_of_watermark"),
                )
                active[order.order_id] = order
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
            risk.position += filled if order.side == "buy" else -filled
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
        with orders_path.open("x", encoding="utf-8") as destination:
            for record in order_records:
                destination.write(canonical_json(record) + "\n")
        with fills_path.open("x", encoding="utf-8") as destination:
            for record in fills:
                destination.write(canonical_json(record) + "\n")
        fill_assumption = (
            "trade_touch_v1 allocates qualifying public trade quantity to simulated orders by deterministic order id."
            if fill_model == "trade_touch_v1"
            else "no_fill_v1 never creates simulated fills; it is the execution-free control."
        )
        manifest = {
            "schema": "pmm.backtest_result_manifest.v1",
            "config_sha256": sha256_file(config_path),
            "normalized_events_sha256": sha256_file(normalized_path),
            "features_sha256": sha256_file(features_path),
            "run_id": config.get("run_id"),
            "seed": config.get("seed"),
            "source_fidelity": "level_2",
            "market_truth": "Observed",
            "execution_truth": "ModelDerived",
            "fill_model": fill_model,
            "latency": config["latency"],
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
        }
        write_json(temporary / "manifest.json", manifest)
        temporary.rename(output_dir)
        return manifest
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 7 deterministic historical-data utilities.")
    commands = parser.add_subparsers(dest="command", required=True)
    normalize = commands.add_parser("normalize", help="Normalize an immutable raw capture into canonical events.")
    normalize.add_argument("--input", required=True, type=Path)
    normalize.add_argument("--output", required=True, type=Path)
    normalize.add_argument("--allow-sequence-gaps", action="store_true")
    features = commands.add_parser("features", help="Materialize causal observed-L2 feature rows.")
    features.add_argument("--input", required=True, type=Path)
    features.add_argument("--output", required=True, type=Path)
    backtest = commands.add_parser("backtest", help="Run the explicit deterministic V1 synthetic-fill backtest.")
    backtest.add_argument("--config", required=True, type=Path)
    backtest.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.command == "normalize":
            result = normalize_capture(args.input, args.output, allow_sequence_gaps=args.allow_sequence_gaps)
        elif args.command == "features":
            result = materialize_features(args.input, args.output)
        else:
            result = run_backtest(args.config, args.output)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, InvalidOperation) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
