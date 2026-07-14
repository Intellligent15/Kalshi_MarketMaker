#!/usr/bin/env python3
"""Passive, raw Kalshi market-data capture and inspection for Phase 7.

The recorder deliberately retains source frames rather than normalizing them.  It never submits
orders and only reads the API key identifier and private-key *path* from the environment.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WEBSOCKET_URL = "wss://external-api-ws.kalshi.com/trade-api/ws/v2"
WEBSOCKET_PATH = "/trade-api/ws/v2"
CAPTURE_SCHEMA = "pmm.kalshi.raw_capture.v1"
FRAMES_FILE = "frames.jsonl"
METADATA_FILE = "metadata.json"


@dataclass(frozen=True)
class CaptureConfig:
    ticker: str
    duration_seconds: int
    output: Path


def utc_now_ns() -> int:
    return time.time_ns()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def safe_git_revision() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for package in ("cryptography", "websockets"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def parse_capture_config(args: argparse.Namespace) -> CaptureConfig:
    ticker = args.ticker.strip()
    if not ticker:
        raise ValueError("--ticker must not be empty")
    if args.duration <= 0:
        raise ValueError("--duration must be positive")
    output = args.output.resolve()
    try:
        output.relative_to(REPOSITORY_ROOT)
    except ValueError as error:
        raise ValueError("--output must be within the repository") from error
    if output.exists():
        raise ValueError(f"--output already exists: {output}")
    return CaptureConfig(ticker=ticker, duration_seconds=args.duration, output=output)


def require_environment() -> tuple[str, Path]:
    api_key_id = os.environ.get("KALSHI_API_KEY_ID")
    private_key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH")
    if not api_key_id:
        raise RuntimeError("KALSHI_API_KEY_ID is required in the local environment")
    if not private_key_path:
        raise RuntimeError("KALSHI_PRIVATE_KEY_PATH is required in the local environment")
    path = Path(private_key_path).expanduser()
    if not path.is_file() or not os.access(path, os.R_OK):
        raise RuntimeError("KALSHI_PRIVATE_KEY_PATH must name a readable private-key file")
    return api_key_id, path


def verify_environment() -> int:
    require_environment()
    print("Credentials verified: API key identifier is set and private-key path is readable.")
    return 0


def load_runtime_dependencies() -> tuple[Any, Any, Any, Any]:
    try:
        import websockets
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError as error:
        raise RuntimeError("Install project dependencies with: uv sync") from error
    return websockets, hashes, serialization, padding


def signed_headers(
    api_key_id: str, private_key: Any, hashes: Any, padding: Any, path: str
) -> dict[str, str]:
    timestamp_ms = str(time.time_ns() // 1_000_000)
    message = f"{timestamp_ms}GET{path}".encode("utf-8")
    signature = private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return {
        "KALSHI-ACCESS-KEY": api_key_id,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("ascii"),
        "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
    }


def subscription_payload(ticker: str, request_id: int) -> dict[str, Any]:
    return {
        "id": request_id,
        "cmd": "subscribe",
        "params": {
            "channels": ["orderbook_delta", "trade"],
            "market_tickers": [ticker],
            "use_yes_price": True,
        },
    }


class SequenceTracker:
    """Checks monotonic source sequences independently for each connection/subscription."""

    def __init__(self) -> None:
        self._previous: dict[tuple[int, str], int] = {}
        self.gaps: list[dict[str, Any]] = []
        self.non_monotonic: list[dict[str, Any]] = []

    def observe(self, connection_id: int, sid: Any, sequence: Any) -> None:
        if sequence is None:
            return
        try:
            current = int(sequence)
        except (TypeError, ValueError):
            self.non_monotonic.append(
                {"connection_id": connection_id, "sid": str(sid), "sequence": sequence}
            )
            return
        key = (connection_id, str(sid))
        previous = self._previous.get(key)
        if previous is not None:
            if current > previous + 1:
                self.gaps.append(
                    {
                        "connection_id": connection_id,
                        "sid": str(sid),
                        "expected_sequence": previous + 1,
                        "received_sequence": current,
                    }
                )
            elif current <= previous:
                self.non_monotonic.append(
                    {
                        "connection_id": connection_id,
                        "sid": str(sid),
                        "previous_sequence": previous,
                        "received_sequence": current,
                    }
                )
        self._previous[key] = current


def decode_frame(raw_frame: str) -> tuple[str, Any, Any, dict[str, Any] | None]:
    try:
        decoded = json.loads(raw_frame)
    except json.JSONDecodeError:
        return "invalid_json", None, None, None
    if not isinstance(decoded, dict):
        return "non_object_json", None, None, None
    return str(decoded.get("type", "unknown")), decoded.get("sid"), decoded.get("seq"), decoded


class JsonlCapture:
    def __init__(self, path: Path) -> None:
        self._file = path.open("x", encoding="utf-8", buffering=1)
        self.message_counts: Counter[str] = Counter()
        self.sequence_tracker = SequenceTracker()

    def write(self, record: dict[str, Any]) -> None:
        self._file.write(json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n")

    def inbound_frame(self, connection_id: int, raw_frame: str) -> str:
        message_type, sid, sequence, _ = decode_frame(raw_frame)
        self.message_counts[message_type] += 1
        self.sequence_tracker.observe(connection_id, sid, sequence)
        self.write(
            {
                "kind": "inbound_frame",
                "received_at_utc_ns": utc_now_ns(),
                "connection_id": connection_id,
                "message_type": message_type,
                "subscription_id": sid,
                "source_sequence": sequence,
                "raw_frame_utf8": raw_frame,
            }
        )
        return message_type

    def close(self) -> None:
        if not self._file.closed:
            self._file.flush()
            os.fsync(self._file.fileno())
            self._file.close()


async def run_capture(
    config: CaptureConfig, api_key_id: str, private_key_path: Path, recorder: JsonlCapture
) -> tuple[int, int]:
    websockets, hashes, serialization, padding = load_runtime_dependencies()
    private_key = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
    deadline = time.monotonic() + config.duration_seconds
    connection_id = 0
    disconnects = 0
    reconnect_delay_seconds = 1

    while time.monotonic() < deadline:
        connection_id += 1
        recorder.write(
            {
                "kind": "connection_opening",
                "received_at_utc_ns": utc_now_ns(),
                "connection_id": connection_id,
                "websocket_url": WEBSOCKET_URL,
            }
        )
        try:
            headers = signed_headers(api_key_id, private_key, hashes, padding, WEBSOCKET_PATH)
            async with websockets.connect(
                WEBSOCKET_URL,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=20,
                max_size=None,
            ) as websocket:
                payload = subscription_payload(config.ticker, connection_id)
                await websocket.send(json.dumps(payload, separators=(",", ":")))
                recorder.write(
                    {
                        "kind": "subscription_sent",
                        "received_at_utc_ns": utc_now_ns(),
                        "connection_id": connection_id,
                        "subscription": payload,
                    }
                )
                print(f"Connected and subscribed (connection {connection_id}).", flush=True)
                reconnect_delay_seconds = 1
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return connection_id, disconnects
                    try:
                        raw = await asyncio.wait_for(websocket.recv(), timeout=min(remaining, 30))
                    except TimeoutError:
                        continue
                    if isinstance(raw, str):
                        message_type = recorder.inbound_frame(connection_id, raw)
                        if message_type == "subscribed":
                            print(f"Subscription confirmed (connection {connection_id}).", flush=True)
                    else:
                        recorder.write(
                            {
                                "kind": "binary_frame_rejected",
                                "received_at_utc_ns": utc_now_ns(),
                                "connection_id": connection_id,
                            }
                        )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            disconnects += 1
            recorder.write(
                {
                    "kind": "connection_gap",
                    "received_at_utc_ns": utc_now_ns(),
                    "connection_id": connection_id,
                    "error_type": type(error).__name__,
                    "reconnect_delay_seconds": reconnect_delay_seconds,
                }
            )
            remaining = deadline - time.monotonic()
            if remaining > 0:
                await asyncio.sleep(min(reconnect_delay_seconds, remaining))
                reconnect_delay_seconds = min(reconnect_delay_seconds * 2, 30)
    return connection_id, disconnects


def capture_metadata(config: CaptureConfig, started_at: int) -> dict[str, Any]:
    payload = subscription_payload(config.ticker, request_id=1)
    return {
        "schema": CAPTURE_SCHEMA,
        "source": "kalshi",
        "ticker": config.ticker,
        "capture_started_at_utc_ns": started_at,
        "requested_duration_seconds": config.duration_seconds,
        "websocket_endpoint": WEBSOCKET_URL,
        "subscription_payload": payload,
        "credential_environment_variables": ["KALSHI_API_KEY_ID", "KALSHI_PRIVATE_KEY_PATH"],
        "credential_values_persisted": False,
        "git_revision": safe_git_revision(),
        "package_versions": package_versions(),
        "message_counts_by_type": {},
        "disconnects": 0,
        "sequence_gaps": [],
        "non_monotonic_sequences": [],
        "shutdown": {"status": "running", "clean": False},
    }


def run_capture_command(args: argparse.Namespace) -> int:
    config = parse_capture_config(args)
    api_key_id, private_key_path = require_environment()
    config.output.mkdir(parents=True, exist_ok=False)
    started_at = utc_now_ns()
    metadata = capture_metadata(config, started_at)
    write_json(config.output / METADATA_FILE, metadata)
    recorder = JsonlCapture(config.output / FRAMES_FILE)
    print(f"Passive capture started for {config.ticker}; output: {config.output}", flush=True)
    exit_code = 0
    try:
        connections, disconnects = asyncio.run(run_capture(config, api_key_id, private_key_path, recorder))
        metadata["shutdown"] = {"status": "completed", "clean": True}
        metadata["connections"] = connections
        metadata["disconnects"] = disconnects
    except KeyboardInterrupt:
        metadata["shutdown"] = {"status": "interrupted", "clean": True}
        exit_code = 130
        print("Capture interrupted; flushing raw output.", flush=True)
    except Exception as error:
        metadata["shutdown"] = {"status": "failed", "clean": False, "error_type": type(error).__name__}
        exit_code = 1
        print(f"Capture failed: {type(error).__name__}", file=sys.stderr, flush=True)
    finally:
        recorder.close()
        metadata["capture_ended_at_utc_ns"] = utc_now_ns()
        metadata["message_counts_by_type"] = dict(sorted(recorder.message_counts.items()))
        metadata["sequence_gaps"] = recorder.sequence_tracker.gaps
        metadata["non_monotonic_sequences"] = recorder.sequence_tracker.non_monotonic
        write_json(config.output / METADATA_FILE, metadata)
    if exit_code == 0:
        print("Capture completed cleanly.", flush=True)
    return exit_code


class ObservedBookReplay:
    """Best-effort replay of observed L2 snapshots/deltas; it does not simulate execution."""

    def __init__(self) -> None:
        self.levels: dict[str, dict[str, Decimal]] = {"yes": {}, "no": {}}
        self.snapshots = 0
        self.deltas = 0
        self.deltas_before_snapshot = 0
        self.parse_errors = 0

    @staticmethod
    def _payload(message: dict[str, Any]) -> dict[str, Any]:
        nested = message.get("msg")
        return nested if isinstance(nested, dict) else message

    @staticmethod
    def _levels(payload: dict[str, Any], side: str) -> Iterable[tuple[Any, Any]]:
        candidates = (f"{side}_dollars", side, f"{side}_levels")
        for field in candidates:
            levels = payload.get(field)
            if isinstance(levels, list):
                for level in levels:
                    if isinstance(level, (list, tuple)) and len(level) >= 2:
                        yield level[0], level[1]
                    elif isinstance(level, dict):
                        yield level.get("price_dollars", level.get("price")), level.get(
                            "quantity_fp", level.get("quantity")
                        )
                return

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        return Decimal(str(value))

    def apply(self, message: dict[str, Any]) -> None:
        message_type = message.get("type")
        payload = self._payload(message)
        try:
            if message_type == "orderbook_snapshot":
                self.levels = {"yes": {}, "no": {}}
                for side in ("yes", "no"):
                    for price, quantity in self._levels(payload, side):
                        parsed_quantity = self._decimal(quantity)
                        if parsed_quantity > 0:
                            self.levels[side][str(price)] = parsed_quantity
                self.snapshots += 1
            elif message_type == "orderbook_delta":
                if self.snapshots == 0:
                    self.deltas_before_snapshot += 1
                side = str(payload.get("side", "")).lower()
                if side not in self.levels:
                    self.parse_errors += 1
                    return
                price = payload.get("price_dollars", payload.get("price"))
                delta = payload.get("delta_fp", payload.get("delta"))
                if price is None or delta is None:
                    self.parse_errors += 1
                    return
                next_quantity = self.levels[side].get(str(price), Decimal(0)) + self._decimal(delta)
                if next_quantity <= 0:
                    self.levels[side].pop(str(price), None)
                else:
                    self.levels[side][str(price)] = next_quantity
                self.deltas += 1
        except (InvalidOperation, TypeError, ValueError):
            self.parse_errors += 1


def inspect_capture(path: Path) -> dict[str, Any]:
    frames_path = path / FRAMES_FILE
    metadata_path = path / METADATA_FILE
    if not frames_path.is_file() or not metadata_path.is_file():
        raise ValueError(f"{path} must contain {FRAMES_FILE} and {METADATA_FILE}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    counts: Counter[str] = Counter()
    sequence_tracker = SequenceTracker()
    replay = ObservedBookReplay()
    malformed_records = 0
    with frames_path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("record is not an object")
            except (json.JSONDecodeError, ValueError):
                malformed_records += 1
                continue
            if record.get("kind") != "inbound_frame":
                continue
            message_type = str(record.get("message_type", "unknown"))
            counts[message_type] += 1
            sequence_tracker.observe(
                int(record.get("connection_id", 0)),
                record.get("subscription_id"),
                record.get("source_sequence"),
            )
            raw = record.get("raw_frame_utf8")
            if isinstance(raw, str):
                _, _, _, decoded = decode_frame(raw)
                if decoded is not None:
                    replay.apply(decoded)
    return {
        "capture_path": str(path),
        "ticker": metadata.get("ticker"),
        "shutdown": metadata.get("shutdown"),
        "message_counts_by_type": dict(sorted(counts.items())),
        "malformed_jsonl_records": malformed_records,
        "sequence_gaps": sequence_tracker.gaps,
        "non_monotonic_sequences": sequence_tracker.non_monotonic,
        "observed_l2_replay": {
            "snapshots_applied": replay.snapshots,
            "deltas_applied": replay.deltas,
            "deltas_before_snapshot": replay.deltas_before_snapshot,
            "parse_errors": replay.parse_errors,
            "remaining_yes_levels": len(replay.levels["yes"]),
            "remaining_no_levels": len(replay.levels["no"]),
        },
    }


def inspect_capture_command(args: argparse.Namespace) -> int:
    report = inspect_capture(args.input.resolve())
    failures: list[str] = []
    counts = report["message_counts_by_type"]
    if args.require_snapshot and counts.get("orderbook_snapshot", 0) == 0:
        failures.append("no orderbook_snapshot received")
    if args.require_subscription and counts.get("subscribed", 0) == 0:
        failures.append("no subscription acknowledgement received")
    if args.require_delta and counts.get("orderbook_delta", 0) == 0:
        failures.append("no orderbook_delta received")
    if args.require_trade and counts.get("trade", 0) == 0:
        failures.append("no trade received")
    if args.require_contiguous_sequences and (
        report["sequence_gaps"] or report["non_monotonic_sequences"]
    ):
        failures.append("source sequences were not continuous")
    if args.require_clean_shutdown and report["shutdown"] != {"status": "completed", "clean": True}:
        failures.append("capture did not complete with a clean normal shutdown")
    if report["malformed_jsonl_records"]:
        failures.append("malformed JSONL records found")
    if report["observed_l2_replay"]["deltas_before_snapshot"]:
        failures.append("delta encountered before an order-book snapshot")
    if report["observed_l2_replay"]["parse_errors"]:
        failures.append("observed L2 replay parse errors")
    report["validation_failures"] = failures
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Passive Kalshi raw market-data capture utilities.")
    subcommands = parser.add_subparsers(dest="command", required=True)
    verify = subcommands.add_parser("verify-env", help="Verify required credential variables without printing values.")
    verify.set_defaults(handler=lambda _: verify_environment())
    capture = subcommands.add_parser("capture", help="Passively capture raw order-book and trade messages.")
    capture.add_argument("--ticker", required=True)
    capture.add_argument("--duration", required=True, type=int, help="Capture duration in seconds.")
    capture.add_argument("--output", required=True, type=Path, help="New output directory beneath this repository.")
    capture.set_defaults(handler=run_capture_command)
    inspect = subcommands.add_parser("inspect", help="Inspect and replay recorded observed L2 frames.")
    inspect.add_argument("--input", required=True, type=Path)
    inspect.add_argument("--require-subscription", action="store_true")
    inspect.add_argument("--require-snapshot", action="store_true")
    inspect.add_argument("--require-delta", action="store_true")
    inspect.add_argument("--require-trade", action="store_true")
    inspect.add_argument("--require-contiguous-sequences", action="store_true")
    inspect.add_argument("--require-clean-shutdown", action="store_true")
    inspect.set_defaults(handler=inspect_capture_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        return args.handler(args)
    except (RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
