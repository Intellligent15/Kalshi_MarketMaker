from __future__ import annotations

import importlib.util
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid

from jsonschema import Draft202012Validator


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

    def make_v2_capture(
        self,
        *,
        reconnect: bool = False,
        missing_recovery_snapshot: bool = False,
        delta_before_recovery: bool = False,
    ) -> Path:
        capture = self.generated_root / f"capture-v2-{uuid.uuid4()}"
        capture.mkdir()
        tickers = ["KX-A", "KX-B"]
        metadata = {
            "schema": phase7.RAW_CAPTURE_V2_SCHEMA,
            "source": "kalshi",
            "environment": "production",
            "market_tickers": tickers,
            "capture_started_at_utc_ns": 1,
            "capture_ended_at_utc_ns": 10_000_000_000,
            "truth_category": "Synthetic",
            "source_fidelity": "level_2",
            "requested_duration_seconds": 10,
            "connection_strategy": "single_connection_v1",
            "websocket_endpoint": "wss://fixture",
            "subscription_template": {
                "id": 1,
                "cmd": "subscribe",
                "params": {
                    "channels": ["orderbook_delta", "trade"],
                    "market_tickers": tickers,
                    "use_yes_price": True,
                },
            },
            "sequence_domain": {
                "status": "fixture_declared",
                "topology": "shared",
                "components": ["connection_segment_id", "venue_subscription_id"],
                "mechanical_validation_key": ["connection_segment_id", "venue_subscription_id"],
                "limitation": "Synthetic fixture scope.",
            },
            "credential_environment_variables": [],
            "credential_values_persisted": False,
            "git_revision": None,
            "package_versions": {},
            "message_counts_by_type": {},
            "message_counts_by_market": {},
            "connections": 2 if reconnect else 1,
            "disconnects": 1 if reconnect else 0,
            "connection_segments": [],
            "sequence_gaps": [],
            "non_monotonic_sequences": [],
            "capture_continuity": "observed_discontinuous" if reconnect else "continuous_within_recorded_mechanical_scopes",
            "data_usability": "record_only" if reconnect else "strict_eligible",
            "shutdown": {"status": "completed", "clean": True},
        }
        (capture / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        records: list[dict[str, object]] = []

        def add(kind: str, connection: int, **values: object) -> None:
            records.append(
                {
                    "schema": phase7.RAW_CAPTURE_RECORD_V2_SCHEMA,
                    "kind": kind,
                    "raw_ingress_ordinal": len(records) + 1,
                    "received_at_utc_ns": 1_000_000_000 + len(records),
                    "connection_segment_id": connection,
                    **values,
                }
            )

        def inbound(connection: int, message: dict[str, object]) -> None:
            add(
                "inbound_frame",
                connection,
                message_type=message["type"],
                subscription_id=message.get("sid"),
                source_sequence=message.get("seq"),
                market_ticker=(message.get("msg") or {}).get("market_ticker"),  # type: ignore[union-attr]
                venue_market_id=(message.get("msg") or {}).get("market_id"),  # type: ignore[union-attr]
                raw_frame_utf8=json.dumps(message),
            )

        def connection_prefix(connection: int, orderbook_sid: int, trade_sid: int) -> None:
            add("connection_attempt", connection, websocket_url="wss://fixture")
            add("connection_opened", connection, websocket_url="wss://fixture")
            subscription = {
                "id": connection,
                "cmd": "subscribe",
                "params": {
                    "channels": ["orderbook_delta", "trade"],
                    "market_tickers": tickers,
                    "use_yes_price": True,
                },
            }
            add(
                "subscription_sent",
                connection,
                subscription_request_id=f"c{connection}:r1",
                wire_request_id=connection,
                subscription=subscription,
            )
            for channel, sid in (("orderbook_delta", orderbook_sid), ("trade", trade_sid)):
                inbound(
                    connection,
                    {"id": connection, "type": "subscribed", "msg": {"channel": channel, "sid": sid}},
                )
                add(
                    "subscription_acknowledged",
                    connection,
                    subscription_request_id=f"c{connection}:r1",
                    wire_request_id=connection,
                    channel=channel,
                    venue_subscription_id=str(sid),
                    requested_market_tickers=tickers,
                    membership_claim="request_bound_not_echoed_by_acknowledgement",
                )

        def snapshot(connection: int, sid: int, ticker: str, market_id: str, sequence: int) -> None:
            inbound(
                connection,
                {
                    "type": "orderbook_snapshot",
                    "sid": sid,
                    "seq": sequence,
                    "msg": {
                        "market_ticker": ticker,
                        "market_id": market_id,
                        "yes_dollars_fp": [["0.50", "3"]],
                        "no_dollars_fp": [["0.51", "4"]],
                    },
                },
            )

        def delta(connection: int, sid: int, ticker: str, market_id: str, sequence: int) -> None:
            inbound(
                connection,
                {
                    "type": "orderbook_delta",
                    "sid": sid,
                    "seq": sequence,
                    "msg": {
                        "market_ticker": ticker,
                        "market_id": market_id,
                        "side": "yes",
                        "price_dollars": "0.50",
                        "delta_fp": "1",
                        "ts_ms": 1000 + sequence,
                    },
                },
            )

        connection_prefix(1, 11, 12)
        snapshot(1, 11, "KX-A", "market-a", 1)
        snapshot(1, 11, "KX-B", "market-b", 2)
        delta(1, 11, "KX-A", "market-a", 3)
        inbound(
            1,
            {
                "type": "trade",
                "sid": 12,
                "seq": 1,
                "msg": {
                    "market_ticker": "KX-B",
                    "market_id": "market-b",
                    "trade_id": "trade-1",
                    "yes_price_dollars": "0.50",
                    "no_price_dollars": "0.50",
                    "count_fp": "1",
                    "ts_ms": 999,
                },
            },
        )
        if reconnect:
            add(
                "connection_gap",
                1,
                failure_phase="receive",
                error_type="ConnectionError",
                error_code="TransportDisconnected",
                reconnect_delay_seconds=1,
            )
            connection_prefix(2, 21, 22)
            if delta_before_recovery:
                delta(2, 21, "KX-A", "market-a", 1)
            if not missing_recovery_snapshot:
                snapshot(2, 21, "KX-A", "market-a", 1 if not delta_before_recovery else 2)
                snapshot(2, 21, "KX-B", "market-b", 2 if not delta_before_recovery else 3)
                delta(2, 21, "KX-B", "market-b", 3 if not delta_before_recovery else 4)
            add("connection_closed", 2, close_reason="capture_deadline", clean=True)
        else:
            add("connection_closed", 1, close_reason="capture_deadline", clean=True)
        with (capture / "frames.jsonl").open("w", encoding="utf-8") as destination:
            for record in records:
                destination.write(json.dumps(record, separators=(",", ":")) + "\n")
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

    def test_cxx_risk_oracle_and_unresolved_ledger_are_explicit(self) -> None:
        oracle = phase7.REPOSITORY_ROOT / "build" / "cpp" / "pmm_risk_oracle"
        if not oracle.is_file():
            self.skipTest("C++ risk oracle has not been built")
        capture = self.make_capture([self.snapshot(), self.trade()])
        normalized = self.generated_root / "normalized"
        phase7.normalize_capture(capture, normalized)
        features = self.generated_root / "features"
        phase7.materialize_features(normalized, features)
        relative = self.generated_root.relative_to(phase7.REPOSITORY_ROOT)
        config = {
            "schema": phase7.BACKTEST_SCHEMA, "run_id": "cxx-risk", "seed": 7,
            "normalized_events": str(relative / "normalized" / "events.jsonl"),
            "features": str(relative / "features" / "features.jsonl"),
            "latency": {"market_data_ns": 0, "decision_ns": 0, "order_ns": 0},
            "strategy": {"decision_interval_ns": 1_000_000_000, "order_lifetime_ns": 10_000_000_000,
                         "minimum_spread_dollars": "0.01", "quote_quantity_contracts": "1"},
            "risk": {
                "engine": "cxx_oracle_v1", "oracle_executable": "build/cpp/pmm_risk_oracle",
                "limits": {"maximum_order_quantity_contracts": "2", "maximum_absolute_position_contracts": "2",
                           "maximum_buy_exposure_contracts": "2", "maximum_sell_exposure_contracts": "2",
                           "maximum_pending_exposure_contracts": "2", "maximum_active_orders": 2},
            },
            "accounting": {"schema": "pmm.accounting_policy.v1", "fee_per_contract_dollars": "0.01",
                           "settlement_status": "unresolved"},
            "fill_model": "trade_touch_v1",
        }
        config_path = self.generated_root / "cxx-config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        manifest = phase7.run_backtest(config_path, self.generated_root / "run")
        self.assertEqual(manifest["risk_engine"], "cxx_oracle_v1")
        self.assertTrue(manifest["accounting"]["enabled"])
        self.assertEqual(manifest["metrics"]["model_derived_fills"], 1)
        ledger = list(phase7.iter_jsonl(self.generated_root / "run" / "ledger.jsonl"))
        self.assertEqual(len(ledger), 1)
        self.assertEqual(ledger[0]["fee_dollars"], "0.01")

    def test_cxx_oracle_v2_uses_portable_cmake_launcher_and_writes_identical_trace(self) -> None:
        build_dir = phase7.REPOSITORY_ROOT / "build"
        if not (build_dir / "CMakeCache.txt").is_file():
            self.skipTest("CMake build directory has not been configured")
        capture = self.make_capture([self.snapshot(), self.trade()])
        normalized = self.generated_root / "normalized"
        phase7.normalize_capture(capture, normalized)
        features = self.generated_root / "features"
        phase7.materialize_features(normalized, features)
        relative = self.generated_root.relative_to(phase7.REPOSITORY_ROOT)
        config = {
            "schema": phase7.BACKTEST_V2_SCHEMA, "run_id": "cxx-risk-v2", "seed": 7,
            "normalized_events": str(relative / "normalized" / "events.jsonl"),
            "features": str(relative / "features" / "features.jsonl"),
            "latency": {"market_data_ns": 0, "decision_ns": 0, "order_ns": 0},
            "strategy": {"decision_interval_ns": 1_000_000_000, "order_lifetime_ns": 10_000_000_000,
                         "minimum_spread_dollars": "0.01", "quote_quantity_contracts": "1"},
            "risk": {
                "engine": "cxx_oracle_v2",
                "oracle": {"schema": "pmm.risk_oracle_launcher.v1", "build_dir": "build",
                           "cmake_target": "pmm_risk_oracle"},
                "risk_contract": {"schema": "pmm.research_risk_contract.v1",
                                  "quantity_unit": "whole_contract", "price_unit": "cent",
                                  "post_only": True},
                "limits": {"maximum_order_quantity_contracts": "2", "maximum_absolute_position_contracts": "2",
                           "maximum_buy_exposure_contracts": "2", "maximum_sell_exposure_contracts": "2",
                           "maximum_pending_exposure_contracts": "2", "maximum_active_orders": 2},
            },
            "fill_model": "no_fill_v1",
        }
        config_path = self.generated_root / "v2-config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        first = phase7.run_backtest(config_path, self.generated_root / "run-one")
        second = phase7.run_backtest(config_path, self.generated_root / "run-two")
        self.assertEqual(first["schema"], "pmm.backtest_result_manifest.v2")
        self.assertEqual(first["risk_trace_schema"], phase7.RISK_TRACE_SCHEMA)
        self.assertEqual((self.generated_root / "run-one" / "risk-trace.jsonl").read_bytes(),
                         (self.generated_root / "run-two" / "risk-trace.jsonl").read_bytes())
        self.assertEqual((self.generated_root / "run-one" / "manifest.json").read_bytes(),
                         (self.generated_root / "run-two" / "manifest.json").read_bytes())
        legacy = {
            "schema": phase7.BACKTEST_SCHEMA, "run_id": "python-reference-shared-subset", "seed": 7,
            "normalized_events": config["normalized_events"], "features": config["features"],
            "latency": config["latency"], "strategy": config["strategy"],
            "risk": {"maximum_absolute_position_contracts": "2", "maximum_active_orders": 2},
            "fill_model": "no_fill_v1",
        }
        legacy_path = self.generated_root / "legacy-config.json"
        legacy_path.write_text(json.dumps(legacy), encoding="utf-8")
        phase7.run_backtest(legacy_path, self.generated_root / "legacy-run")
        self.assertEqual((self.generated_root / "legacy-run" / "orders.jsonl").read_bytes(),
                         (self.generated_root / "run-one" / "orders.jsonl").read_bytes())

    def test_backtest_v2_refuses_python_compatibility_risk(self) -> None:
        config = {"schema": phase7.BACKTEST_V2_SCHEMA, "risk": {"engine": "python_reference_v1"}}
        config_path = self.generated_root / "invalid-v2-config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "requires risk.engine cxx_oracle_v2"):
            phase7.run_backtest(config_path, self.generated_root / "run")

    def test_cxx_oracle_rejects_malformed_command_without_advancing_state(self) -> None:
        if not (phase7.REPOSITORY_ROOT / "build" / "CMakeCache.txt").is_file():
            self.skipTest("CMake build directory has not been configured")
        config = {
            "oracle": {"schema": "pmm.risk_oracle_launcher.v1", "build_dir": "build",
                       "cmake_target": "pmm_risk_oracle"},
            "limits": {"maximum_order_quantity_contracts": "2", "maximum_absolute_position_contracts": "2",
                       "maximum_buy_exposure_contracts": "2", "maximum_sell_exposure_contracts": "2",
                       "maximum_pending_exposure_contracts": "2", "maximum_active_orders": 2},
        }
        oracle = phase7.CxxRiskOracle(config, canonical_trace=True)
        try:
            oracle._send("ACK malformed")
            with self.assertRaisesRegex(ValueError, "invalid_ack"):
                oracle._receive()
            self.assertEqual(oracle.view()["event_watermark"], 0)
            self.assertEqual(oracle.view()["net_position_contracts"], "0")
        finally:
            oracle.close()

    def test_v3_normalizes_two_markets_in_shared_scope_deterministically(self) -> None:
        capture = self.make_v2_capture()
        first = self.generated_root / "normalized-v3-one"
        second = self.generated_root / "normalized-v3-two"
        first_manifest = phase7.normalize_capture_v3(capture, first)
        second_manifest = phase7.normalize_capture_v3(capture, second)
        self.assertEqual(first_manifest, second_manifest)
        self.assertEqual(first_manifest["completeness"], "complete_observed_interval")
        self.assertEqual(first_manifest["event_counts"]["book_snapshot"], 2)
        for filename in ("records.jsonl", "source_scopes.json", "product.json", "manifest.json"):
            self.assertEqual((first / filename).read_bytes(), (second / filename).read_bytes())
        products = json.loads((first / "product.json").read_text())["products"]
        self.assertEqual([product["ticker"] for product in products], ["KX-A", "KX-B"])
        records = list(phase7.iter_jsonl(first / "records.jsonl"))
        market_records = [record for record in records if record["kind"] == "market_event"]
        self.assertEqual(
            [record["raw_ingress_ordinal"] for record in market_records],
            sorted(record["raw_ingress_ordinal"] for record in market_records),
        )
        self.assertTrue(all(record["truth_category"] == "Synthetic" for record in records))

    def test_v3_retained_offline_scenario_matrix(self) -> None:
        fixture = json.loads(
            (
                Path(__file__).parent
                / "fixtures"
                / "phase7_b2a"
                / "scenarios.json"
            ).read_text()
        )
        self.assertEqual(fixture["schema"], "pmm.historical.b2a_fixture_scenarios.v1")
        for scenario in fixture["scenarios"]:
            with self.subTest(scenario=scenario["id"]):
                capture = self.make_v2_capture(
                    reconnect=scenario["reconnect"],
                    missing_recovery_snapshot=scenario["missing_recovery_snapshot"],
                    delta_before_recovery=scenario["delta_before_recovery"],
                )
                manifest = phase7.normalize_capture_v3(
                    capture,
                    self.generated_root / f"scenario-{scenario['id']}",
                    continuity_policy="record",
                )
                self.assertEqual(manifest["completeness"], scenario["expected_completeness"])

    def test_v3_shared_and_independent_sequence_scopes_do_not_collide(self) -> None:
        capture = self.make_v2_capture()
        output = self.generated_root / "normalized-v3"
        phase7.normalize_capture_v3(capture, output)
        records = list(phase7.iter_jsonl(output / "records.jsonl"))
        events = [record for record in records if record["kind"] == "market_event"]
        self.assertEqual(
            [(event["subscription_id"], event["source_sequence"]) for event in events],
            [("11", 1), ("11", 2), ("11", 3), ("12", 1)],
        )

    def test_v3_reconnect_snapshot_starts_new_discontinuous_segment(self) -> None:
        capture = self.make_v2_capture(reconnect=True)
        with self.assertRaisesRegex(phase7.HistoricalDataError, "DiscontinuousInput"):
            phase7.normalize_capture_v3(capture, self.generated_root / "refused")
        output = self.generated_root / "recorded"
        manifest = phase7.normalize_capture_v3(capture, output, continuity_policy="record")
        self.assertEqual(manifest["completeness"], "observed_discontinuous")
        records = list(phase7.iter_jsonl(output / "records.jsonl"))
        gaps = [record for record in records if record.get("control_type") == "connection_gap"]
        self.assertEqual(len(gaps), 2)
        starts = [record for record in records if record["kind"] == "segment_boundary"]
        self.assertEqual(len(starts), 4)
        self.assertTrue(all(start["continuity_claim"] == "valid_from_observed_snapshot_only" for start in starts))

    def test_v3_missing_recovery_snapshot_is_incomplete(self) -> None:
        capture = self.make_v2_capture(reconnect=True, missing_recovery_snapshot=True)
        output = self.generated_root / "recorded"
        manifest = phase7.normalize_capture_v3(capture, output, continuity_policy="record")
        self.assertEqual(manifest["completeness"], "incomplete")
        codes = {reason["code"] for reason in manifest["incomplete_reasons"]}
        self.assertIn("RecoverySnapshotMissing", codes)
        self.assertIn("SnapshotCardinalityMismatch", codes)

    def test_v3_per_scope_sequence_gap_and_regression_are_fail_closed(self) -> None:
        capture = self.make_v2_capture()
        frames = capture / "frames.jsonl"
        records = [json.loads(line) for line in frames.read_text().splitlines()]
        target = next(record for record in records if record.get("message_type") == "orderbook_delta")
        message = json.loads(target["raw_frame_utf8"])
        message["seq"] = 4
        target["source_sequence"] = 4
        target["raw_frame_utf8"] = json.dumps(message)
        frames.write_text("".join(json.dumps(record) + "\n" for record in records))
        output = self.generated_root / "gap-recorded"
        manifest = phase7.normalize_capture_v3(capture, output, continuity_policy="record")
        self.assertEqual(manifest["discontinuity_counts"], {"sequence_gap": 1})
        self.assertIn("DeltaBeforeRecovery", {item["code"] for item in manifest["incomplete_reasons"]})

        capture = self.make_v2_capture()
        frames = capture / "frames.jsonl"
        records = [json.loads(line) for line in frames.read_text().splitlines()]
        target = next(record for record in records if record.get("message_type") == "orderbook_delta")
        message = json.loads(target["raw_frame_utf8"])
        message["seq"] = 0
        target["source_sequence"] = 0
        target["raw_frame_utf8"] = json.dumps(message)
        frames.write_text("".join(json.dumps(record) + "\n" for record in records))
        with self.assertRaisesRegex(phase7.HistoricalDataError, "SourceSequenceRegression"):
            phase7.normalize_capture_v3(capture, self.generated_root / "regression")

    def test_v3_duplicate_recovery_snapshot_and_missing_ack_are_refused(self) -> None:
        capture = self.make_v2_capture(reconnect=True)
        frames = capture / "frames.jsonl"
        records = [json.loads(line) for line in frames.read_text().splitlines()]
        second_snapshots = [
            record
            for record in records
            if record.get("connection_segment_id") == 2
            and record.get("message_type") == "orderbook_snapshot"
        ]
        target = second_snapshots[1]
        message = json.loads(target["raw_frame_utf8"])
        message["msg"]["market_ticker"] = "KX-A"
        message["msg"]["market_id"] = "market-a"
        target["market_ticker"] = "KX-A"
        target["venue_market_id"] = "market-a"
        target["raw_frame_utf8"] = json.dumps(message)
        frames.write_text("".join(json.dumps(record) + "\n" for record in records))
        with self.assertRaisesRegex(phase7.HistoricalDataError, "RecoverySnapshotDuplicate"):
            phase7.normalize_capture_v3(capture, self.generated_root / "duplicate-recovery")

        capture = self.make_v2_capture()
        frames = capture / "frames.jsonl"
        records = [json.loads(line) for line in frames.read_text().splitlines()]
        records = [
            record
            for record in records
            if not (
                record.get("kind") == "subscription_acknowledged"
                and record.get("channel") == "trade"
            )
        ]
        for ordinal, record in enumerate(records, start=1):
            record["raw_ingress_ordinal"] = ordinal
        frames.write_text("".join(json.dumps(record) + "\n" for record in records))
        with self.assertRaisesRegex(phase7.HistoricalDataError, "UnboundSourceScope"):
            phase7.normalize_capture_v3(capture, self.generated_root / "missing-ack")

    def test_v3_delta_before_recovery_refuses_or_records_unsupported_state(self) -> None:
        capture = self.make_v2_capture(reconnect=True, delta_before_recovery=True)
        with self.assertRaisesRegex(phase7.HistoricalDataError, "DeltaBeforeRecovery"):
            phase7.normalize_capture_v3(capture, self.generated_root / "refused")
        output = self.generated_root / "recorded"
        manifest = phase7.normalize_capture_v3(capture, output, continuity_policy="record")
        self.assertEqual(manifest["completeness"], "incomplete")
        unsupported = [
            record
            for record in phase7.iter_jsonl(output / "records.jsonl")
            if record["kind"] == "market_event" and not record["book_state_valid"]
        ]
        self.assertEqual(len(unsupported), 1)

    def test_v3_identical_and_conflicting_duplicates_are_distinct(self) -> None:
        capture = self.make_v2_capture()
        frames = capture / "frames.jsonl"
        records = [json.loads(line) for line in frames.read_text().splitlines()]
        donor_index = next(
            index
            for index, record in enumerate(records)
            if record.get("message_type") == "orderbook_delta"
        )
        duplicate = dict(records[donor_index])
        records.insert(donor_index + 1, duplicate)
        for index, record in enumerate(records, start=1):
            record["raw_ingress_ordinal"] = index
        frames.write_text("".join(json.dumps(record) + "\n" for record in records))
        output = self.generated_root / "deduplicated"
        manifest = phase7.normalize_capture_v3(capture, output)
        self.assertEqual(manifest["identical_duplicates_skipped"], 1)

        conflicting_capture = self.make_v2_capture()
        conflicting_frames = conflicting_capture / "frames.jsonl"
        conflicting = [json.loads(line) for line in conflicting_frames.read_text().splitlines()]
        donor = next(record for record in conflicting if record.get("message_type") == "orderbook_delta")
        collision = dict(donor)
        message = json.loads(collision["raw_frame_utf8"])
        message["msg"]["delta_fp"] = "2"
        collision["raw_frame_utf8"] = json.dumps(message)
        insert_at = conflicting.index(donor) + 1
        conflicting.insert(insert_at, collision)
        for index, record in enumerate(conflicting, start=1):
            record["raw_ingress_ordinal"] = index
        conflicting_frames.write_text("".join(json.dumps(record) + "\n" for record in conflicting))
        with self.assertRaisesRegex(phase7.HistoricalDataError, "ConflictingDuplicate"):
            phase7.normalize_capture_v3(conflicting_capture, self.generated_root / "conflict")

    def test_v3_refuses_ingress_ordinal_and_membership_defects(self) -> None:
        capture = self.make_v2_capture()
        frames = capture / "frames.jsonl"
        records = [json.loads(line) for line in frames.read_text().splitlines()]
        records[1]["raw_ingress_ordinal"] = 1
        frames.write_text("".join(json.dumps(record) + "\n" for record in records))
        with self.assertRaisesRegex(phase7.HistoricalDataError, "IngressOrdinalMismatch"):
            phase7.normalize_capture_v3(capture, self.generated_root / "ordinal")

        capture = self.make_v2_capture()
        frames = capture / "frames.jsonl"
        records = [json.loads(line) for line in frames.read_text().splitlines()]
        target = next(record for record in records if record.get("message_type") == "trade")
        message = json.loads(target["raw_frame_utf8"])
        message["msg"]["market_ticker"] = "KX-OUTSIDE"
        target["raw_frame_utf8"] = json.dumps(message)
        frames.write_text("".join(json.dumps(record) + "\n" for record in records))
        with self.assertRaisesRegex(phase7.HistoricalDataError, "MarketMembershipMismatch"):
            phase7.normalize_capture_v3(capture, self.generated_root / "membership")

    def test_v3_schema_runtime_parity_for_generated_formats(self) -> None:
        capture = self.make_v2_capture()
        output = self.generated_root / "normalized-v3"
        phase7.normalize_capture_v3(capture, output)
        schema_root = phase7.REPOSITORY_ROOT / "schemas" / "historical"
        pairs = {
            "raw-capture-v2.schema.json": capture / "metadata.json",
            "source-scope-map-v1.schema.json": output / "source_scopes.json",
            "product-map-v3.schema.json": output / "product.json",
            "normalization-manifest-v3.schema.json": output / "manifest.json",
        }
        config_schema = json.loads((schema_root / "capture-config-v2.schema.json").read_text())
        Draft202012Validator(config_schema).validate(
            {
                "schema": "pmm.kalshi.capture_config.v2",
                "market_tickers": ["KX-A", "KX-B"],
                "channels": ["orderbook_delta", "trade"],
                "connection_strategy": "single_connection_v1",
                "use_yes_price": True,
                "duration_seconds": 30,
            }
        )
        for schema_name, document_path in pairs.items():
            with self.subTest(schema=schema_name):
                schema = json.loads((schema_root / schema_name).read_text())
                Draft202012Validator(schema).validate(json.loads(document_path.read_text()))
        raw_schema = Draft202012Validator(
            json.loads((schema_root / "raw-capture-record-v2.schema.json").read_text())
        )
        for record in phase7.iter_jsonl(capture / "frames.jsonl"):
            raw_schema.validate(record)
        normalized_schema = Draft202012Validator(
            json.loads((schema_root / "normalized-record-v2.schema.json").read_text())
        )
        for record in phase7.iter_jsonl(output / "records.jsonl"):
            normalized_schema.validate(record)

        bad_metadata = json.loads((capture / "metadata.json").read_text())
        bad_metadata["schema"] = "pmm.kalshi.raw_capture.v3"
        metadata_schema = Draft202012Validator(
            json.loads((schema_root / "raw-capture-v2.schema.json").read_text())
        )
        self.assertFalse(metadata_schema.is_valid(bad_metadata))
        (capture / "metadata.json").write_text(json.dumps(bad_metadata))
        with self.assertRaisesRegex(phase7.HistoricalDataError, "CaptureSchemaMismatch"):
            phase7.normalize_capture_v3(capture, self.generated_root / "bad-schema")

    def test_v3_interrupt_removes_partial_output_and_downstream_refuses(self) -> None:
        capture = self.make_v2_capture()
        interrupted = self.generated_root / "interrupted"
        with mock.patch.object(phase7, "normalized_payload", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                phase7.normalize_capture_v3(capture, interrupted)
        self.assertFalse(interrupted.exists())
        self.assertFalse(interrupted.with_name("interrupted.partial").exists())

        normalized = self.generated_root / "normalized-v3"
        phase7.normalize_capture_v3(capture, normalized)
        with self.assertRaisesRegex(phase7.HistoricalDataError, "DownstreamContinuityRequired"):
            phase7.materialize_features(normalized, self.generated_root / "features")

    def test_v3_cli_success_and_expected_refusal_stream_contract(self) -> None:
        capture = self.make_v2_capture()
        output = self.generated_root / "cli-success"
        command = [
            sys.executable,
            str(phase7.MODULE_PATH) if hasattr(phase7, "MODULE_PATH") else str(phase7.REPOSITORY_ROOT / "python" / "pmm_phase7.py"),
            "normalize-v3",
            "--input",
            str(capture),
            "--output",
            str(output),
        ]
        success = subprocess.run(command, text=True, capture_output=True, check=False)
        self.assertEqual(success.returncode, 0)
        self.assertEqual(success.stderr, "")
        self.assertEqual(json.loads(success.stdout)["completeness"], "complete_observed_interval")
        snapshot = {path.name: path.read_bytes() for path in output.iterdir() if path.is_file()}
        repeated = subprocess.run(command, text=True, capture_output=True, check=False)
        self.assertEqual(repeated.returncode, 2)
        self.assertEqual(repeated.stdout, "")
        self.assertEqual(
            snapshot, {path.name: path.read_bytes() for path in output.iterdir() if path.is_file()}
        )

        reconnect = self.make_v2_capture(reconnect=True)
        refused_output = self.generated_root / "cli-refused"
        refused = subprocess.run(
            command[:3]
            + ["--input", str(reconnect), "--output", str(refused_output)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(refused.returncode, 2)
        self.assertEqual(refused.stdout, "")
        self.assertIn("DiscontinuousInput", refused.stderr)
        self.assertFalse(refused_output.exists())

    def test_v3_cli_programming_failure_and_interruption_are_distinct(self) -> None:
        arguments = ["normalize-v3", "--input", "input", "--output", "output"]
        for error, expected_status, expected_text in (
            (OSError("disk"), 1, "programming failure"),
            (KeyboardInterrupt(), 130, "interrupted"),
        ):
            with self.subTest(status=expected_status), mock.patch.object(
                phase7, "normalize_capture_v3", side_effect=error
            ):
                stdout = io.StringIO()
                stderr = io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    status = phase7.main(arguments)
                self.assertEqual(status, expected_status)
                self.assertEqual(stdout.getvalue(), "")
                self.assertIn(expected_text, stderr.getvalue())

    def test_v3_shared_gap_names_and_invalidates_every_possible_market(self) -> None:
        capture = self.make_v2_capture()
        frames = capture / "frames.jsonl"
        records = [json.loads(line) for line in frames.read_text().splitlines()]
        target = next(record for record in records if record.get("message_type") == "orderbook_delta")
        message = json.loads(target["raw_frame_utf8"])
        message["seq"] = 4
        target["source_sequence"] = 4
        target["raw_frame_utf8"] = json.dumps(message)
        frames.write_text("".join(json.dumps(record) + "\n" for record in records))

        output = self.generated_root / "shared-gap"
        manifest = phase7.normalize_capture_v3(capture, output, continuity_policy="record")
        self.assertEqual(manifest["completeness"], "incomplete")
        normalized = list(phase7.iter_jsonl(output / "records.jsonl"))
        gap = next(record for record in normalized if record.get("control_type") == "sequence_gap")
        self.assertIsNone(gap["ticker"])
        self.assertEqual(gap["details"]["observed_post_gap_ticker"], "KX-A")
        self.assertEqual(gap["details"]["affected_market_tickers"], ["KX-A", "KX-B"])
        self.assertIn(
            "RecoverySnapshotMissing", {reason["code"] for reason in manifest["incomplete_reasons"]}
        )

    def test_v3_independent_gap_invalidates_only_observed_market(self) -> None:
        capture = self.make_v2_capture()
        metadata_path = capture / "metadata.json"
        metadata = json.loads(metadata_path.read_text())
        metadata["sequence_domain"]["topology"] = "independent"
        metadata["sequence_domain"]["mechanical_validation_key"].append("market_ticker")
        metadata_path.write_text(json.dumps(metadata))
        frames = capture / "frames.jsonl"
        records = [json.loads(line) for line in frames.read_text().splitlines()]
        target = next(record for record in records if record.get("message_type") == "orderbook_delta")
        message = json.loads(target["raw_frame_utf8"])
        message["seq"] = 4
        target["source_sequence"] = 4
        target["raw_frame_utf8"] = json.dumps(message)
        frames.write_text("".join(json.dumps(record) + "\n" for record in records))
        output = self.generated_root / "independent-gap"
        phase7.normalize_capture_v3(capture, output, continuity_policy="record")
        gap = next(
            record
            for record in phase7.iter_jsonl(output / "records.jsonl")
            if record.get("control_type") == "sequence_gap"
        )
        self.assertEqual(gap["details"]["affected_market_tickers"], ["KX-A"])

    def test_v3_requires_book_sequence_but_allows_sequence_less_trade(self) -> None:
        for message_type in ("orderbook_snapshot", "orderbook_delta"):
            with self.subTest(message_type=message_type):
                capture = self.make_v2_capture()
                frames = capture / "frames.jsonl"
                records = [json.loads(line) for line in frames.read_text().splitlines()]
                target = next(record for record in records if record.get("message_type") == message_type)
                message = json.loads(target["raw_frame_utf8"])
                message.pop("seq")
                target["source_sequence"] = None
                target["raw_frame_utf8"] = json.dumps(message)
                frames.write_text("".join(json.dumps(record) + "\n" for record in records))
                with self.assertRaisesRegex(
                    phase7.HistoricalDataError, "RequiredSourceSequenceMissing"
                ):
                    phase7.normalize_capture_v3(
                        capture, self.generated_root / f"missing-{message_type}"
                    )

        capture = self.make_v2_capture()
        frames = capture / "frames.jsonl"
        records = [json.loads(line) for line in frames.read_text().splitlines()]
        target = next(record for record in records if record.get("message_type") == "trade")
        message = json.loads(target["raw_frame_utf8"])
        message.pop("seq")
        target["source_sequence"] = None
        target["raw_frame_utf8"] = json.dumps(message)
        frames.write_text("".join(json.dumps(record) + "\n" for record in records))
        manifest = phase7.normalize_capture_v3(capture, self.generated_root / "trade-without-seq")
        self.assertEqual(manifest["completeness"], "complete_observed_interval")

    def test_v3_refuses_requested_market_that_never_establishes_identity(self) -> None:
        capture = self.make_v2_capture()
        frames = capture / "frames.jsonl"
        records = [
            record
            for record in (json.loads(line) for line in frames.read_text().splitlines())
            if record.get("market_ticker") is None
            or (
                record.get("market_ticker") == "KX-A"
                and record.get("message_type") == "orderbook_snapshot"
            )
        ]
        for ordinal, record in enumerate(records, start=1):
            record["raw_ingress_ordinal"] = ordinal
        frames.write_text("".join(json.dumps(record) + "\n" for record in records))
        for policy in ("refuse", "record"):
            with self.subTest(policy=policy), self.assertRaisesRegex(
                phase7.HistoricalDataError, "MarketIdentityMissing"
            ):
                phase7.normalize_capture_v3(
                    capture,
                    self.generated_root / f"missing-identity-{policy}",
                    continuity_policy=policy,
                )

    def test_v3_reproves_logical_ack_identity_and_channel_cardinality(self) -> None:
        capture = self.make_v2_capture()
        frames = capture / "frames.jsonl"
        records = [json.loads(line) for line in frames.read_text().splitlines()]
        acknowledgement = next(
            record for record in records if record.get("kind") == "subscription_acknowledged"
        )
        acknowledgement["subscription_request_id"] = "c1:wrong"
        frames.write_text("".join(json.dumps(record) + "\n" for record in records))
        with self.assertRaisesRegex(phase7.HistoricalDataError, "SubscriptionAckMismatch"):
            phase7.normalize_capture_v3(capture, self.generated_root / "logical-id")

        capture = self.make_v2_capture()
        frames = capture / "frames.jsonl"
        records = [json.loads(line) for line in frames.read_text().splitlines()]
        acknowledgement = next(
            record
            for record in records
            if record.get("kind") == "subscription_acknowledged"
            and record.get("channel") == "orderbook_delta"
        )
        duplicate = dict(acknowledgement)
        duplicate["venue_subscription_id"] = "99"
        records.insert(records.index(acknowledgement) + 1, duplicate)
        for ordinal, record in enumerate(records, start=1):
            record["raw_ingress_ordinal"] = ordinal
        frames.write_text("".join(json.dumps(record) + "\n" for record in records))
        with self.assertRaisesRegex(phase7.HistoricalDataError, "SubscriptionAckMismatch"):
            phase7.normalize_capture_v3(capture, self.generated_root / "duplicate-channel")

    def test_v3_disconnect_before_first_snapshot_remains_incomplete_prefix(self) -> None:
        capture = self.make_v2_capture(reconnect=True)
        frames = capture / "frames.jsonl"
        records = [json.loads(line) for line in frames.read_text().splitlines()]
        records = [
            record
            for record in records
            if not (
                record.get("connection_segment_id") == 1
                and record.get("kind") == "inbound_frame"
                and record.get("message_type") in {"orderbook_snapshot", "orderbook_delta", "trade"}
            )
        ]
        for ordinal, record in enumerate(records, start=1):
            record["raw_ingress_ordinal"] = ordinal
        frames.write_text("".join(json.dumps(record) + "\n" for record in records))
        output = self.generated_root / "incomplete-prefix"
        manifest = phase7.normalize_capture_v3(capture, output, continuity_policy="record")
        self.assertEqual(manifest["completeness"], "incomplete")
        starts = [
            record
            for record in phase7.iter_jsonl(output / "records.jsonl")
            if record["kind"] == "segment_boundary"
        ]
        self.assertTrue(starts)
        self.assertTrue(all(start["start_evidence"] == "initial_snapshot" for start in starts))

    def test_v3_connect_and_pre_ack_failures_are_incomplete_prefixes(self) -> None:
        for phase in ("connect", "subscribe", "receive"):
            with self.subTest(phase=phase):
                capture = self.make_v2_capture(reconnect=True)
                frames = capture / "frames.jsonl"
                records = [json.loads(line) for line in frames.read_text().splitlines()]
                first_gap_index = next(
                    index
                    for index, record in enumerate(records)
                    if record.get("connection_segment_id") == 1
                    and record.get("kind") == "connection_gap"
                )
                first_connection = records[:first_gap_index]
                if phase == "connect":
                    first_connection = [
                        record for record in first_connection if record["kind"] == "connection_attempt"
                    ]
                elif phase == "subscribe":
                    first_connection = [
                        record
                        for record in first_connection
                        if record["kind"] in {"connection_attempt", "connection_opened"}
                    ]
                else:
                    first_connection = [
                        record
                        for record in first_connection
                        if record["kind"]
                        in {"connection_attempt", "connection_opened", "subscription_sent"}
                    ]
                gap = records[first_gap_index]
                gap["failure_phase"] = phase
                records = first_connection + [gap] + records[first_gap_index + 1 :]
                for ordinal, record in enumerate(records, start=1):
                    record["raw_ingress_ordinal"] = ordinal
                frames.write_text("".join(json.dumps(record) + "\n" for record in records))
                output = self.generated_root / f"prefix-{phase}"
                manifest = phase7.normalize_capture_v3(
                    capture, output, continuity_policy="record"
                )
                self.assertEqual(manifest["completeness"], "incomplete")
                starts = [
                    record
                    for record in phase7.iter_jsonl(output / "records.jsonl")
                    if record["kind"] == "segment_boundary"
                ]
                self.assertTrue(starts)
                self.assertTrue(
                    all(start["start_evidence"] == "initial_snapshot" for start in starts)
                )

    def test_v3_disconnect_after_one_market_snapshot_keeps_other_prefix_incomplete(self) -> None:
        capture = self.make_v2_capture(reconnect=True)
        frames = capture / "frames.jsonl"
        records = [json.loads(line) for line in frames.read_text().splitlines()]
        records = [
            record
            for record in records
            if not (
                record.get("connection_segment_id") == 1
                and record.get("kind") == "inbound_frame"
                and record.get("market_ticker") in {"KX-A", "KX-B"}
                and not (
                    record.get("market_ticker") == "KX-A"
                    and record.get("message_type") == "orderbook_snapshot"
                )
            )
        ]
        for ordinal, record in enumerate(records, start=1):
            record["raw_ingress_ordinal"] = ordinal
        frames.write_text("".join(json.dumps(record) + "\n" for record in records))
        output = self.generated_root / "partial-initial-snapshots"
        manifest = phase7.normalize_capture_v3(capture, output, continuity_policy="record")
        self.assertEqual(manifest["completeness"], "incomplete")
        starts = [
            record
            for record in phase7.iter_jsonl(output / "records.jsonl")
            if record["kind"] == "segment_boundary"
        ]
        evidence = {(start["ticker"], start["start_evidence"]) for start in starts}
        self.assertIn(("KX-A", "recovery_snapshot"), evidence)
        self.assertIn(("KX-B", "initial_snapshot"), evidence)

    def test_v3_successor_schema_one_defect_negative_matrix(self) -> None:
        capture = self.make_v2_capture()
        output = self.generated_root / "schema-matrix"
        phase7.normalize_capture_v3(capture, output)
        schema_root = phase7.HISTORICAL_SCHEMA_ROOT

        config = {
            "schema": "pmm.kalshi.capture_config.v2",
            "market_tickers": ["KX-A", "KX-B"],
            "channels": ["orderbook_delta", "trade"],
            "connection_strategy": "single_connection_v1",
            "use_yes_price": True,
            "duration_seconds": 30,
        }
        bad_config = dict(config)
        bad_config["market_tickers"] = ["KX-A", "KX-A"]
        self.assertFalse(
            Draft202012Validator(
                json.loads((schema_root / "capture-config-v2.schema.json").read_text())
            ).is_valid(bad_config)
        )

        cases: list[tuple[str, dict[str, object], str]] = []
        metadata = json.loads((capture / "metadata.json").read_text())
        del metadata["sequence_domain"]["topology"]
        cases.append(("raw-capture-v2.schema.json", metadata, "CaptureSchemaMismatch"))

        raw_record = next(
            record
            for record in phase7.iter_jsonl(capture / "frames.jsonl")
            if record["kind"] == "subscription_sent"
        )
        del raw_record["subscription_request_id"]
        cases.append(
            ("raw-capture-record-v2.schema.json", raw_record, "CaptureRecordSchemaMismatch")
        )

        scope_map = json.loads((output / "source_scopes.json").read_text())
        del scope_map["scopes"][0]["sequence_domain_topology"]
        cases.append(("source-scope-map-v1.schema.json", scope_map, "SourceScopeSchemaMismatch"))

        product_map = json.loads((output / "product.json").read_text())
        product_map["products"][0]["venue_market_id"] = None
        cases.append(("product-map-v3.schema.json", product_map, "ProductMapSchemaMismatch"))

        normalized_record = next(
            record
            for record in phase7.iter_jsonl(output / "records.jsonl")
            if record["kind"] == "market_event"
        )
        del normalized_record["event_type"]
        cases.append(
            ("normalized-record-v2.schema.json", normalized_record, "NormalizedRecordSchemaMismatch")
        )

        manifest = json.loads((output / "manifest.json").read_text())
        manifest["incomplete_reasons"] = [{"code": "UnknownReason"}]
        cases.append(
            ("normalization-manifest-v3.schema.json", manifest, "NormalizationManifestSchemaMismatch")
        )

        for schema_name, document, expected_code in cases:
            with self.subTest(schema=schema_name):
                validator = Draft202012Validator(
                    json.loads((schema_root / schema_name).read_text())
                )
                self.assertFalse(validator.is_valid(document))
                with self.assertRaisesRegex(phase7.HistoricalDataError, expected_code):
                    phase7.validate_historical_schema(document, schema_name, expected_code)

    def test_feature_v3_projects_two_products_and_segments_independently(self) -> None:
        normalized = self.generated_root / "normalized-v3"
        phase7.normalize_capture_v3(self.make_v2_capture(), normalized)
        first = self.generated_root / "features-v3-one"
        second = self.generated_root / "features-v3-two"
        first_manifest = phase7.materialize_features_v3(normalized, first)
        second_manifest = phase7.materialize_features_v3(normalized, second)
        self.assertEqual(first_manifest, second_manifest)
        for filename in ("features.jsonl", "manifest.json"):
            self.assertEqual((first / filename).read_bytes(), (second / filename).read_bytes())
        self.assertEqual(first_manifest["schema"], phase7.FEATURE_MANIFEST_V3_SCHEMA)
        self.assertEqual(first_manifest["output"]["feature_row_count"], 4)
        rows = list(phase7.iter_jsonl(first / "features.jsonl"))
        self.assertEqual(
            [row["product_identity"]["ticker"] for row in rows],
            ["KX-A", "KX-B", "KX-A", "KX-B"],
        )
        a_rows = [row for row in rows if row["product_identity"]["ticker"] == "KX-A"]
        b_rows = [row for row in rows if row["product_identity"]["ticker"] == "KX-B"]
        self.assertEqual(a_rows[-1]["values"]["best_bid_quantity_contracts"], "4")
        self.assertEqual(b_rows[0]["values"]["best_bid_quantity_contracts"], "3")
        self.assertEqual(b_rows[-1]["values"]["last_trade_yes_price_dollars"], "0.50")
        self.assertIsNone(a_rows[-1]["values"]["last_trade_yes_price_dollars"])
        self.assertEqual(
            rows[0]["segment_identity"]["snapshot_seed_watermark"]["raw_ingress_ordinal"],
            rows[0]["segment_identity"]["valid_from_watermark"]["raw_ingress_ordinal"],
        )
        self.assertLess(
            rows[0]["segment_identity"]["snapshot_seed_watermark"]["normalization_ordinal"],
            rows[0]["segment_identity"]["valid_from_watermark"]["normalization_ordinal"],
        )

    def test_feature_v3_refuses_discontinuous_and_incomplete_inputs_without_output(self) -> None:
        for name, kwargs in (
            ("discontinuous", {"reconnect": True}),
            ("incomplete", {"reconnect": True, "missing_recovery_snapshot": True}),
        ):
            with self.subTest(name=name):
                normalized = self.generated_root / f"normalized-{name}"
                phase7.normalize_capture_v3(
                    self.make_v2_capture(**kwargs), normalized, continuity_policy="record"
                )
                output = self.generated_root / f"features-{name}"
                with self.assertRaisesRegex(
                    phase7.HistoricalDataError, "FeatureInputContinuityRequired"
                ):
                    phase7.materialize_features_v3(normalized, output)
                self.assertFalse(output.exists())
                self.assertFalse(output.with_name(f"{output.name}.partial").exists())

    def test_segment_cursor_rejects_cross_segment_delta_and_ignores_invalid_trade(self) -> None:
        cursor = phase7.SegmentAwareProductCursor("KX-A", "market-a")
        boundary = {
            "ticker": "KX-A", "book_segment_id": "KX-A:segment:1",
            "start_evidence": "initial_snapshot", "continuity_claim": "valid_from_observed_snapshot_only",
            "source_scope_id": "scope", "raw_ingress_ordinal": 1, "normalization_ordinal": 1,
        }
        snapshot = {
            "ticker": "KX-A", "venue_market_id": "market-a", "book_segment_id": "KX-A:segment:1",
            "source_scope_id": "scope", "raw_ingress_ordinal": 1, "normalization_ordinal": 2,
            "event_type": "book_snapshot", "book_state_valid": True,
            "payload": {"yes_bids": [{"price_dollars": "0.50", "quantity_contracts": "1"}],
                        "yes_asks": [{"price_dollars": "0.51", "quantity_contracts": "1"}]},
        }
        cursor.start_segment(boundary)
        self.assertTrue(cursor.apply_market_event(snapshot))
        gap = {"raw_ingress_ordinal": 2, "normalization_ordinal": 3}
        cursor.invalidate(gap)
        trade = {
            "ticker": "KX-A", "venue_market_id": "market-a", "book_segment_id": "KX-A:segment:1",
            "raw_ingress_ordinal": 3, "normalization_ordinal": 4, "event_type": "trade",
            "book_state_valid": False, "payload": {"yes_price_dollars": "0.49"},
        }
        self.assertFalse(cursor.apply_market_event(trade))
        self.assertEqual(cursor.state, "invalid_awaiting_recovery")
        self.assertIsNone(cursor.projection.last_trade_price)
        delta = {**trade, "normalization_ordinal": 5, "event_type": "book_delta", "book_state_valid": True,
                 "payload": {"book_side": "yes", "price_dollars": "0.50", "quantity_delta_contracts": "1"}}
        with self.assertRaisesRegex(phase7.HistoricalDataError, "FeatureBookStateInvalid"):
            cursor.apply_market_event(delta)

    def test_feature_v3_schema_runtime_parity_and_hash_refusal(self) -> None:
        normalized = self.generated_root / "normalized-v3"
        phase7.normalize_capture_v3(self.make_v2_capture(), normalized)
        output = self.generated_root / "features-v3"
        phase7.materialize_features_v3(normalized, output)
        schema_root = phase7.REPOSITORY_ROOT / "schemas" / "historical"
        row = next(phase7.iter_jsonl(output / "features.jsonl"))
        manifest = json.loads((output / "manifest.json").read_text())
        for schema_name, document in (
            ("feature-row-v2.schema.json", row),
            ("feature-manifest-v3.schema.json", manifest),
        ):
            validator = Draft202012Validator(json.loads((schema_root / schema_name).read_text()))
            self.assertTrue(validator.is_valid(document), list(validator.iter_errors(document)))
            mutated = json.loads(json.dumps(document))
            mutated["schema"] = "wrong"
            self.assertFalse(validator.is_valid(mutated))
            with self.assertRaises(phase7.HistoricalDataError):
                phase7.validate_historical_schema(mutated, schema_name, "FeatureSchemaMismatch")
        records = normalized / "records.jsonl"
        records.write_text(records.read_text() + "\n", encoding="utf-8")
        with self.assertRaisesRegex(phase7.HistoricalDataError, "FeatureInputHashMismatch"):
            phase7.materialize_features_v3(normalized, self.generated_root / "stale")

    def test_feature_v3_cli_status_cleanup_output_exists_and_legacy_refusal(self) -> None:
        normalized = self.generated_root / "normalized-v3"
        phase7.normalize_capture_v3(self.make_v2_capture(), normalized)
        output = self.generated_root / "features-v3"
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = phase7.main(["features-v3", "--input", str(normalized), "--output", str(output)])
        self.assertEqual(status, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(json.loads(stdout.getvalue())["schema"], phase7.FEATURE_MANIFEST_V3_SCHEMA)
        before = {path.name: path.read_bytes() for path in output.iterdir()}
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = phase7.main(["features-v3", "--input", str(normalized), "--output", str(output)])
        self.assertEqual(status, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("output already exists", stderr.getvalue())
        self.assertEqual(before, {path.name: path.read_bytes() for path in output.iterdir()})
        with self.assertRaisesRegex(phase7.HistoricalDataError, "DownstreamContinuityRequired"):
            phase7.materialize_features(normalized, self.generated_root / "legacy-refusal")

    def test_feature_v3_cli_programming_failure_and_interruption_clean_partial(self) -> None:
        normalized = self.generated_root / "normalized-v3"
        phase7.normalize_capture_v3(self.make_v2_capture(), normalized)
        for exception, expected_status, diagnostic in (
            (OSError("boom"), 1, "programming failure"),
            (KeyboardInterrupt(), 130, "interrupted"),
        ):
            output = self.generated_root / f"failure-{expected_status}"
            original = phase7.validate_historical_schema
            calls = 0

            def fail_after_creation(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls > 4:
                    raise exception
                return original(*args, **kwargs)

            stdout, stderr = io.StringIO(), io.StringIO()
            with mock.patch.object(phase7, "validate_historical_schema", side_effect=fail_after_creation), redirect_stdout(stdout), redirect_stderr(stderr):
                status = phase7.main(["features-v3", "--input", str(normalized), "--output", str(output)])
            self.assertEqual(status, expected_status)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(diagnostic, stderr.getvalue())
            self.assertFalse(output.exists())
            self.assertFalse(output.with_name(f"{output.name}.partial").exists())


if __name__ == "__main__":
    unittest.main()
