from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import uuid


MODULE_PATH = Path(__file__).resolve().parents[1] / "pmm_phase7.py"
SPEC = importlib.util.spec_from_file_location("pmm_phase7", MODULE_PATH)
assert SPEC and SPEC.loader
phase7 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = phase7
SPEC.loader.exec_module(phase7)


class Phase7Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.generated_root = phase7.REPOSITORY_ROOT / "data" / "processed" / f"phase7-test-{uuid.uuid4()}"
        self.generated_root.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.generated_root, ignore_errors=True)

    @staticmethod
    def raw_record(message: dict[str, object], line: int) -> dict[str, object]:
        return {
            "kind": "inbound_frame",
            "received_at_utc_ns": 1_000_000_000 + line,
            "connection_id": 1,
            "message_type": message["type"],
            "subscription_id": message.get("sid"),
            "source_sequence": message.get("seq"),
            "raw_frame_utf8": json.dumps(message),
        }

    def make_capture(self, messages: list[dict[str, object]]) -> Path:
        capture = self.generated_root / "capture"
        capture.mkdir()
        (capture / "metadata.json").write_text(json.dumps({"ticker": "KXTEST"}), encoding="utf-8")
        with (capture / "frames.jsonl").open("w", encoding="utf-8") as destination:
            for line, message in enumerate(messages, start=1):
                destination.write(json.dumps(self.raw_record(message, line)) + "\n")
        return capture

    @staticmethod
    def snapshot(sequence: int = 1) -> dict[str, object]:
        return {
            "type": "orderbook_snapshot", "sid": 1, "seq": sequence,
            "msg": {"market_ticker": "KXTEST", "market_id": "market-1",
                    "yes_dollars_fp": [["0.50", "3"]], "no_dollars_fp": [["0.51", "4"]]},
        }

    @staticmethod
    def delta(sequence: int = 2) -> dict[str, object]:
        return {
            "type": "orderbook_delta", "sid": 1, "seq": sequence,
            "msg": {"market_ticker": "KXTEST", "market_id": "market-1", "side": "yes",
                    "price_dollars": "0.50", "delta_fp": "2", "ts_ms": 1001},
        }

    @staticmethod
    def trade(sequence: int = 1) -> dict[str, object]:
        return {
            "type": "trade", "sid": 2, "seq": sequence,
            "msg": {"market_ticker": "KXTEST", "market_id": "market-1", "trade_id": "trade-1",
                    "yes_price_dollars": "0.50", "no_price_dollars": "0.50", "count_fp": "1",
                    "ts_ms": 1002},
        }

    def test_normalization_preserves_provenance_and_fixed_point_values(self) -> None:
        capture = self.make_capture([self.snapshot(), self.delta(), self.trade()])
        output = self.generated_root / "normalized"
        manifest = phase7.normalize_capture(capture, output)
        self.assertEqual(manifest["event_counts"], {"book_delta": 1, "book_snapshot": 1, "trade": 1})
        events = list(phase7.iter_jsonl(output / "events.jsonl"))
        self.assertEqual(events[0]["payload"]["yes_bids"][0]["price_dollars"], "0.50")
        self.assertEqual(events[1]["event_time_basis"], "source_ts_ms")
        self.assertEqual(events[2]["truth_category"], "Observed")
        self.assertEqual(events[2]["logical_time_utc_ns"], 1_002_000_000)

    def test_normalization_binds_trade_without_market_id_to_capture_identity(self) -> None:
        trade = self.trade()
        del trade["msg"]["market_id"]  # type: ignore[index]
        capture = self.make_capture([self.snapshot(), trade])
        output = self.generated_root / "normalized"
        phase7.normalize_capture(capture, output)
        event = list(phase7.iter_jsonl(output / "events.jsonl"))[1]
        self.assertEqual(event["venue_market_id"], "market-1")
        self.assertEqual(event["venue_market_id_provenance"], "capture_bound")

    def test_normalization_rejects_source_sequence_gap_by_default(self) -> None:
        capture = self.make_capture([self.snapshot(), self.delta(sequence=3)])
        with self.assertRaisesRegex(ValueError, "sequence gaps"):
            phase7.normalize_capture(capture, self.generated_root / "normalized")
        self.assertFalse((self.generated_root / "normalized").exists())

    def test_normalization_skips_identical_duplicate_source_event(self) -> None:
        capture = self.make_capture([self.snapshot(), self.snapshot(), self.delta()])
        output = self.generated_root / "normalized"
        manifest = phase7.normalize_capture(capture, output)
        self.assertEqual(manifest["identical_duplicates_skipped"], 1)
        self.assertEqual(len(list(phase7.iter_jsonl(output / "events.jsonl"))), 2)

    def test_normalization_marks_late_source_time_without_reordering_ingress(self) -> None:
        delta = self.delta()
        delta["msg"]["ts_ms"] = 999  # type: ignore[index]
        capture = self.make_capture([self.snapshot(), delta])
        output = self.generated_root / "normalized"
        manifest = phase7.normalize_capture(capture, output)
        events = list(phase7.iter_jsonl(output / "events.jsonl"))
        self.assertEqual(manifest["late_source_events"], 1)
        self.assertTrue(events[1]["source_time_late"])
        self.assertEqual(events[1]["logical_time_utc_ns"], events[0]["logical_time_utc_ns"])

    def test_features_are_causal_book_state(self) -> None:
        capture = self.make_capture([self.snapshot(), self.delta(), self.trade()])
        normalized = self.generated_root / "normalized"
        phase7.normalize_capture(capture, normalized)
        features = self.generated_root / "features"
        manifest = phase7.materialize_features(normalized, features)
        self.assertEqual(manifest["feature_count"], 3)
        rows = list(phase7.iter_jsonl(features / "features.jsonl"))
        self.assertEqual(rows[0]["values"]["spread_dollars"], "0.01")
        self.assertEqual(rows[1]["values"]["best_bid_quantity_contracts"], "5")
        self.assertEqual(rows[2]["values"]["last_trade_yes_price_dollars"], "0.50")
        self.assertEqual(rows[2]["as_of_watermark"], 3)

    def test_cursor_checkpoint_restores_identical_continuation(self) -> None:
        capture = self.make_capture([self.snapshot(), self.delta(), self.trade()])
        normalized = self.generated_root / "normalized"
        phase7.normalize_capture(capture, normalized)
        events = list(phase7.iter_jsonl(normalized / "events.jsonl"))
        original = phase7.ObservedMarketCursor()
        original.advance(events[0])
        restored = phase7.ObservedMarketCursor.restore(original.checkpoint())
        original.advance(events[1])
        restored.advance(events[1])
        original.advance(events[2])
        restored.advance(events[2])
        self.assertEqual(original.watermark, restored.watermark)
        self.assertEqual(original.projection.feature_values(), restored.projection.feature_values())

    def test_trade_touch_backtest_is_deterministic_and_model_derived(self) -> None:
        capture = self.make_capture([self.snapshot(), self.trade()])
        normalized = self.generated_root / "normalized"
        phase7.normalize_capture(capture, normalized)
        features = self.generated_root / "features"
        phase7.materialize_features(normalized, features)
        relative = self.generated_root.relative_to(phase7.REPOSITORY_ROOT)
        config = {
            "schema": phase7.BACKTEST_SCHEMA, "run_id": "test", "seed": 7,
            "normalized_events": str(relative / "normalized" / "events.jsonl"),
            "features": str(relative / "features" / "features.jsonl"),
            "latency": {"market_data_ns": 0, "decision_ns": 0, "order_ns": 0},
            "strategy": {"decision_interval_ns": 1_000_000_000, "order_lifetime_ns": 10_000_000_000,
                         "minimum_spread_dollars": "0.01", "quote_quantity_contracts": "1"},
            "risk": {"maximum_absolute_position_contracts": "2", "maximum_active_orders": 2},
            "fill_model": "trade_touch_v1",
        }
        config_path = self.generated_root / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        first = phase7.run_backtest(config_path, self.generated_root / "run-one")
        second = phase7.run_backtest(config_path, self.generated_root / "run-two")
        self.assertEqual(first["metrics"], second["metrics"])
        self.assertEqual(first["metrics"]["model_derived_fills"], 1)
        fills = list(phase7.iter_jsonl(self.generated_root / "run-one" / "fills.jsonl"))
        self.assertEqual(fills[0]["truth_category"], "ModelDerived")

    def test_no_fill_control_never_creates_model_fills(self) -> None:
        capture = self.make_capture([self.snapshot(), self.trade()])
        normalized = self.generated_root / "normalized"
        phase7.normalize_capture(capture, normalized)
        features = self.generated_root / "features"
        phase7.materialize_features(normalized, features)
        relative = self.generated_root.relative_to(phase7.REPOSITORY_ROOT)
        config = {
            "schema": phase7.BACKTEST_SCHEMA, "run_id": "no-fill", "seed": 7,
            "normalized_events": str(relative / "normalized" / "events.jsonl"),
            "features": str(relative / "features" / "features.jsonl"),
            "latency": {"market_data_ns": 0, "decision_ns": 0, "order_ns": 0},
            "strategy": {"decision_interval_ns": 1_000_000_000, "order_lifetime_ns": 10_000_000_000,
                         "minimum_spread_dollars": "0.01", "quote_quantity_contracts": "1"},
            "risk": {"maximum_absolute_position_contracts": "2", "maximum_active_orders": 2},
            "fill_model": "no_fill_v1",
        }
        config_path = self.generated_root / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        manifest = phase7.run_backtest(config_path, self.generated_root / "run")
        self.assertEqual(manifest["metrics"]["model_derived_fills"], 0)
        self.assertIn("never creates", manifest["assumptions"][-1])


if __name__ == "__main__":
    unittest.main()
