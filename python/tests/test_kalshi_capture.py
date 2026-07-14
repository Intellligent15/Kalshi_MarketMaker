from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest


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


if __name__ == "__main__":
    unittest.main()
