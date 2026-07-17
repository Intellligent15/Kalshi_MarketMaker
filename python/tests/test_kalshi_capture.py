from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "kalshi_capture.py"
SPEC = importlib.util.spec_from_file_location("kalshi_capture", MODULE_PATH)
assert SPEC and SPEC.loader
kalshi_capture = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = kalshi_capture
SPEC.loader.exec_module(kalshi_capture)


class KalshiCaptureTests(unittest.TestCase):
    def test_capture_configuration_is_runtime_supplied_and_repository_scoped(self) -> None:
        output = Path("data/raw/test-runtime-config")
        config = kalshi_capture.parse_capture_config(
            SimpleNamespace(ticker="KXTEST", duration=300, output=output)
        )
        self.assertEqual(config.ticker, "KXTEST")
        self.assertEqual(config.duration_seconds, 300)
        self.assertEqual(config.output, (Path.cwd() / output).resolve())

    def test_subscription_is_passive_yes_price_subscription(self) -> None:
        payload = kalshi_capture.subscription_payload("KXTEST", 7)
        self.assertEqual(payload["cmd"], "subscribe")
        self.assertEqual(payload["params"]["channels"], ["orderbook_delta", "trade"])
        self.assertTrue(payload["params"]["use_yes_price"])
        self.assertEqual(payload["params"]["market_tickers"], ["KXTEST"])

    def test_jsonl_serialization_preserves_raw_message_and_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "frames.jsonl"
            recorder = kalshi_capture.JsonlCapture(path)
            raw = json.dumps({"type": "orderbook_delta", "sid": 9, "seq": 11, "msg": {}})
            recorder.inbound_frame(1, raw)
            recorder.close()
            record = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(record["raw_frame_utf8"], raw)
        self.assertEqual(record["source_sequence"], 11)
        self.assertIsInstance(record["received_at_utc_ns"], int)

    def test_jsonl_classifies_subscription_acknowledgement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            recorder = kalshi_capture.JsonlCapture(Path(temporary) / "frames.jsonl")
            message_type = recorder.inbound_frame(1, json.dumps({"type": "subscribed", "sid": 3}))
            recorder.close()
        self.assertEqual(message_type, "subscribed")
        self.assertEqual(recorder.message_counts["subscribed"], 1)

    def test_sequence_tracker_reports_gap(self) -> None:
        tracker = kalshi_capture.SequenceTracker()
        tracker.observe(1, 2, 10)
        tracker.observe(1, 2, 12)
        self.assertEqual(tracker.gaps[0]["expected_sequence"], 11)

    def test_observed_l2_replay_applies_snapshot_and_delta(self) -> None:
        replay = kalshi_capture.ObservedBookReplay()
        replay.apply(
            {
                "type": "orderbook_snapshot",
                "msg": {"yes_dollars": [["0.50", "20"]], "no_dollars": [["0.49", "10"]]},
            }
        )
        replay.apply(
            {
                "type": "orderbook_delta",
                "msg": {"side": "yes", "price_dollars": "0.50", "delta_fp": "-20"},
            }
        )
        self.assertEqual(replay.snapshots, 1)
        self.assertEqual(replay.deltas, 1)
        self.assertEqual(replay.levels["yes"], {})
        self.assertEqual(replay.parse_errors, 0)

    def test_inspection_flags_delta_before_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            capture = Path(temporary)
            (capture / kalshi_capture.METADATA_FILE).write_text(
                json.dumps({"ticker": "KXTEST", "shutdown": {"status": "completed", "clean": True}}),
                encoding="utf-8",
            )
            record = {
                "kind": "inbound_frame",
                "connection_id": 1,
                "message_type": "orderbook_delta",
                "raw_frame_utf8": json.dumps(
                    {"type": "orderbook_delta", "msg": {"side": "yes", "price_dollars": "0.5", "delta_fp": "1"}}
                ),
            }
            (capture / kalshi_capture.FRAMES_FILE).write_text(json.dumps(record) + "\n", encoding="utf-8")
            report = kalshi_capture.inspect_capture(capture)
        self.assertEqual(report["observed_l2_replay"]["deltas_before_snapshot"], 1)

    def test_v2_configuration_sorts_multiple_markets_and_rejects_duplicates(self) -> None:
        config = kalshi_capture.parse_capture_v2_config(
            SimpleNamespace(
                ticker=["KX-B", "KX-A"],
                duration=30,
                output=Path("data/raw/test-v2-config"),
                connection_strategy="single_connection_v1",
            )
        )
        self.assertEqual(config.tickers, ("KX-A", "KX-B"))
        self.assertEqual(
            kalshi_capture.subscription_payload_v2(config.tickers, 4)["params"]["market_tickers"],
            ["KX-A", "KX-B"],
        )
        with self.assertRaisesRegex(kalshi_capture.CaptureV2Error, "must be unique"):
            kalshi_capture.parse_capture_v2_config(
                SimpleNamespace(
                    ticker=["KX-A", "KX-A"],
                    duration=30,
                    output=Path("data/raw/test-v2-duplicate"),
                    connection_strategy="single_connection_v1",
                )
            )

    def test_v2_acknowledgement_binds_request_channel_and_sid(self) -> None:
        binding = kalshi_capture.SubscriptionBinding(
            1, 9, ("orderbook_delta", "trade"), ("KX-A", "KX-B")
        )
        self.assertEqual(
            binding.observe_acknowledgement(
                {"id": 9, "type": "subscribed", "msg": {"channel": "orderbook_delta", "sid": 2}}
            ),
            ("orderbook_delta", "2"),
        )
        with self.assertRaisesRegex(kalshi_capture.CaptureV2Error, "request id"):
            binding.observe_acknowledgement(
                {"id": 8, "type": "subscribed", "msg": {"channel": "trade", "sid": 3}}
            )
        with self.assertRaisesRegex(kalshi_capture.CaptureV2Error, "duplicate acknowledgement"):
            binding.observe_acknowledgement(
                {"id": 9, "type": "subscribed", "msg": {"channel": "orderbook_delta", "sid": 4}}
            )

    def test_v2_recorder_assigns_explicit_ingress_ordinals(self) -> None:
        times = iter((100, 101))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "frames.jsonl"
            recorder = kalshi_capture.JsonlCaptureV2(path, utc_clock=lambda: next(times))
            recorder.write_record("connection_attempt", connection_segment_id=1)
            recorder.write_record("connection_opened", connection_segment_id=1)
            recorder.close()
            records = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual([record["raw_ingress_ordinal"] for record in records], [1, 2])
        self.assertTrue(
            all(record["schema"] == kalshi_capture.CAPTURE_V2_RECORD_SCHEMA for record in records)
        )

    def test_v2_fake_transport_captures_two_markets_and_binds_both_channels(self) -> None:
        class Clock:
            def __init__(self) -> None:
                self.value = 0.0

            def monotonic(self) -> float:
                return self.value

        class Transport:
            def __init__(self, clock: Clock, messages: list[str]) -> None:
                self.clock = clock
                self.messages = iter(messages)
                self.sent: list[str] = []
                self.closed = False

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                self.closed = True

            async def send(self, value: str) -> None:
                self.sent.append(value)

            async def recv(self) -> str:
                value = next(self.messages)
                if '"type": "trade"' in value:
                    self.clock.value = 31.0
                return value

        messages = [
            json.dumps({"id": 1, "type": "subscribed", "msg": {"channel": "orderbook_delta", "sid": 11}}),
            json.dumps({"id": 1, "type": "subscribed", "msg": {"channel": "trade", "sid": 12}}),
            json.dumps({"type": "orderbook_snapshot", "sid": 11, "seq": 1, "msg": {"market_ticker": "KX-A", "market_id": "a", "yes_dollars_fp": [], "no_dollars_fp": []}}),
            json.dumps({"type": "orderbook_snapshot", "sid": 11, "seq": 2, "msg": {"market_ticker": "KX-B", "market_id": "b", "yes_dollars_fp": [], "no_dollars_fp": []}}),
            json.dumps({"type": "trade", "sid": 12, "seq": 1, "msg": {"market_ticker": "KX-A", "market_id": "a"}}),
        ]
        clock = Clock()
        transport = Transport(clock, messages)
        fake_serialization = SimpleNamespace(
            load_pem_private_key=lambda *_args, **_kwargs: object()
        )
        fake_websockets = SimpleNamespace(exceptions=SimpleNamespace())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            key = root / "key.pem"
            key.write_bytes(b"fixture")
            recorder = kalshi_capture.JsonlCaptureV2(root / "frames.jsonl", utc_clock=lambda: 1)
            config = kalshi_capture.CaptureV2Config(("KX-A", "KX-B"), 30, root / "output")
            with mock.patch.object(
                kalshi_capture,
                "load_runtime_dependencies",
                return_value=(fake_websockets, object(), fake_serialization, object()),
            ), mock.patch.object(kalshi_capture, "signed_headers", return_value={}):
                summary = asyncio.run(
                    kalshi_capture.run_capture_v2(
                        config,
                        "key",
                        key,
                        recorder,
                        transport_factory=lambda _headers: transport,
                        monotonic_clock=clock.monotonic,
                    )
                )
            recorder.close()
        self.assertEqual(summary["connections"], 1)
        self.assertEqual(
            summary["connection_segments"][0]["channel_sids"],
            {"orderbook_delta": "11", "trade": "12"},
        )
        self.assertEqual(
            summary["connection_segments"][0]["snapshots_by_ticker"],
            {"KX-A": 1, "KX-B": 1},
        )
        self.assertTrue(transport.closed)


if __name__ == "__main__":
    unittest.main()
