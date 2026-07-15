"""Fixture-driven conformance tests; the Python model is test-only."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
import unittest
from typing import Any

from python import pmm_phase7 as phase7
from python.tests.risk_conformance_reference import ReferenceRisk, UnsupportedSharedOperation


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "risk_conformance" / "v1"
MANIFEST_SCHEMA = "pmm.risk_conformance_fixture_manifest.v1"
FIXTURE_SCHEMA = "pmm.risk_conformance_fixture.v1"
TRACE_SCHEMA = "pmm.risk_conformance_expected_trace.v1"
EXECUTORS = {"direct_cpp", "python_reference", "v1_oracle"}
ADMISSION_REJECTION_CODES = {
    "kill_switch_active": 0,
    "contract_mismatch": 1,
    "order_quantity_limit": 2,
    "active_order_limit": 3,
    "buy_exposure_limit": 4,
    "sell_exposure_limit": 5,
    "pending_exposure_limit": 6,
    "position_limit": 7,
    "duplicate_client_intent": 8,
}
OPERATION_FIELDS = {
    "admit": {"operation", "client_intent_id", "contract_id", "side", "quantity_contracts", "limit_price_cents"},
    "bind_ingress": {"operation", "client_intent_id", "ingress_sequence"},
    "acknowledge": {"operation", "sequence", "ingress_sequence", "order_id", "side", "quantity_contracts", "limit_price_cents", "time_utc_ns"},
    "fill": {"operation", "sequence", "order_id", "side", "quantity_contracts", "time_utc_ns"},
    "cancel": {"operation", "sequence", "order_id", "time_utc_ns"},
    "logical_expiry": {"operation", "sequence", "order_id", "time_utc_ns"},
    "command_rejected": {"operation", "sequence", "ingress_sequence", "time_utc_ns"},
    "kill_switch": {"operation", "active"},
}
RESULTS = {"approved", "applied", "domain_error", *ADMISSION_REJECTION_CODES}
UNSIGNED_DECIMAL = re.compile(r"0|[1-9][0-9]*\Z")
SIGNED_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*|-[1-9][0-9]*)\Z")


class RiskConformanceTests(unittest.TestCase):
    def _canonical_document(self, path: Path) -> tuple[bytes, dict[str, Any]]:
        raw = path.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), path)
        self.assertTrue(raw.endswith(b"\n"), path)
        parsed = json.loads(raw)
        self.assertIsInstance(parsed, dict, path)
        self.assertEqual(raw.decode("utf-8"), phase7.canonical_json(parsed) + "\n", path)
        return raw, parsed

    def _exact_keys(self, value: object, required: set[str], optional: set[str], context: str) -> dict[str, Any]:
        self.assertIsInstance(value, dict, context)
        object_value = value
        self.assertTrue(set(object_value) <= required | optional, context)
        self.assertTrue(required <= set(object_value), context)
        return object_value

    def _unsigned(self, value: object, context: str, *, positive: bool = False) -> int:
        self.assertIsInstance(value, str, context)
        self.assertRegex(value, UNSIGNED_DECIMAL, context)
        parsed = int(value)
        self.assertLessEqual(parsed, 2**63 - 1, context)
        if positive:
            self.assertGreater(parsed, 0, context)
        return parsed

    def _signed(self, value: object, context: str) -> int:
        self.assertIsInstance(value, str, context)
        self.assertRegex(value, SIGNED_DECIMAL, context)
        parsed = int(value)
        self.assertGreaterEqual(parsed, -(2**63), context)
        self.assertLessEqual(parsed, 2**63 - 1, context)
        return parsed

    def _validate_state(self, state: object, context: str) -> None:
        value = self._exact_keys(
            state,
            {"event_watermark", "kill_switch_active", "live_orders", "net_position_contracts", "open_buy_contracts", "open_sell_contracts", "pending_buy_contracts", "pending_orders", "pending_sell_contracts"},
            set(), context,
        )
        self._unsigned(value["event_watermark"], f"{context}.event_watermark")
        self._signed(value["net_position_contracts"], f"{context}.net_position_contracts")
        self.assertIsInstance(value["kill_switch_active"], bool, context)
        self.assertIsInstance(value["live_orders"], list, context)
        self.assertIsInstance(value["pending_orders"], list, context)
        open_totals = {"buy": 0, "sell": 0}
        prior_order = 0
        for index, order in enumerate(value["live_orders"]):
            item = self._exact_keys(order, {"acknowledged_at_utc_ns", "limit_price_cents", "order_id", "remaining_quantity_contracts", "side"}, set(), f"{context}.live_orders[{index}]")
            order_id = self._unsigned(item["order_id"], f"{context}.live_orders[{index}].order_id", positive=True)
            self.assertGreater(order_id, prior_order, context)
            prior_order = order_id
            self.assertIn(item["side"], {"buy", "sell"}, context)
            open_totals[item["side"]] += self._unsigned(item["remaining_quantity_contracts"], f"{context}.live_orders[{index}].remaining_quantity_contracts", positive=True)
            self._unsigned(item["limit_price_cents"], f"{context}.live_orders[{index}].limit_price_cents")
            self._signed(item["acknowledged_at_utc_ns"], f"{context}.live_orders[{index}].acknowledged_at_utc_ns")
        pending_totals = {"buy": 0, "sell": 0}
        prior_client = 0
        for index, order in enumerate(value["pending_orders"]):
            item = self._exact_keys(order, {"client_intent_id", "contract_id", "ingress_sequence", "limit_price_cents", "post_only", "quantity_contracts", "side"}, set(), f"{context}.pending_orders[{index}]")
            client_id = self._unsigned(item["client_intent_id"], f"{context}.pending_orders[{index}].client_intent_id", positive=True)
            self.assertGreater(client_id, prior_client, context)
            prior_client = client_id
            self._unsigned(item["contract_id"], f"{context}.pending_orders[{index}].contract_id", positive=True)
            if item["ingress_sequence"] is not None:
                self._unsigned(item["ingress_sequence"], f"{context}.pending_orders[{index}].ingress_sequence")
            self.assertTrue(item["post_only"], context)
            self.assertIn(item["side"], {"buy", "sell"}, context)
            pending_totals[item["side"]] += self._unsigned(item["quantity_contracts"], f"{context}.pending_orders[{index}].quantity_contracts", positive=True)
            self._unsigned(item["limit_price_cents"], f"{context}.pending_orders[{index}].limit_price_cents")
        self.assertEqual(open_totals["buy"], self._unsigned(value["open_buy_contracts"], f"{context}.open_buy_contracts"), context)
        self.assertEqual(open_totals["sell"], self._unsigned(value["open_sell_contracts"], f"{context}.open_sell_contracts"), context)
        self.assertEqual(pending_totals["buy"], self._unsigned(value["pending_buy_contracts"], f"{context}.pending_buy_contracts"), context)
        self.assertEqual(pending_totals["sell"], self._unsigned(value["pending_sell_contracts"], f"{context}.pending_sell_contracts"), context)

    def _validate_fixture(self, fixture: object, filename: str) -> dict[str, Any]:
        value = self._exact_keys(fixture, {"schema", "fixture_id", "operations"}, {"contract_id", "executors", "limits"}, filename)
        self.assertEqual(value["schema"], FIXTURE_SCHEMA, filename)
        self.assertIsInstance(value["fixture_id"], str, filename)
        self.assertRegex(value["fixture_id"], r"[a-z0-9_]+\Z", filename)
        self.assertEqual(filename, f"{value['fixture_id']}.json", filename)
        if "contract_id" in value:
            self._unsigned(value["contract_id"], f"{filename}.contract_id", positive=True)
        if "executors" in value:
            self.assertIsInstance(value["executors"], list, filename)
            self.assertTrue(value["executors"], filename)
            self.assertEqual(len(value["executors"]), len(set(value["executors"])), filename)
            self.assertTrue(set(value["executors"]) <= EXECUTORS, filename)
        else:
            value["executors"] = ["direct_cpp", "python_reference", "v1_oracle"]
        limits = value.get("limits", {})
        self.assertIsInstance(limits, dict, filename)
        self.assertTrue(set(limits) <= {"maximum_order_quantity_contracts", "maximum_absolute_position_contracts", "maximum_buy_exposure_contracts", "maximum_sell_exposure_contracts", "maximum_pending_exposure_contracts", "maximum_active_orders"}, filename)
        for key, limit in limits.items():
            if key == "maximum_active_orders":
                self.assertIsInstance(limit, int, f"{filename}.{key}")
                self.assertGreater(limit, 0, f"{filename}.{key}")
            else:
                self._unsigned(limit, f"{filename}.{key}", positive=True)
        self.assertIsInstance(value["operations"], list, filename)
        self.assertTrue(value["operations"], filename)
        for index, operation in enumerate(value["operations"]):
            self.assertIsInstance(operation, dict, f"{filename}.operations[{index}]")
            kind = operation.get("operation")
            self.assertIn(kind, OPERATION_FIELDS, f"{filename}.operations[{index}]")
            self.assertEqual(set(operation), OPERATION_FIELDS[kind], f"{filename}.operations[{index}]")
        if "v1_oracle" in value["executors"]:
            bound_contract = str(value.get("contract_id", "1"))
            for operation in value["operations"]:
                if operation["operation"] == "admit":
                    self.assertEqual(operation["contract_id"], bound_contract, filename)
        return value

    def _manifest_entries(self) -> list[dict[str, Any]]:
        raw, manifest = self._canonical_document(FIXTURE_ROOT / "manifest.json")
        del raw
        root = self._exact_keys(manifest, {"schema", "payload", "payload_sha256"}, set(), "manifest")
        self.assertEqual(root["schema"], MANIFEST_SCHEMA)
        payload = self._exact_keys(root["payload"], {"schema", "entries"}, set(), "manifest.payload")
        self.assertEqual(payload["schema"], MANIFEST_SCHEMA)
        self.assertEqual(root["payload_sha256"], hashlib.sha256((phase7.canonical_json(payload) + "\n").encode("utf-8")).hexdigest())
        self.assertIsInstance(payload["entries"], list)
        self.assertTrue(payload["entries"])
        expected_members = {"manifest.json"}
        prior_fixture = ""
        entries: list[dict[str, Any]] = []
        for index, entry in enumerate(payload["entries"]):
            value = self._exact_keys(entry, {"fixture", "fixture_sha256", "expected_trace", "expected_trace_sha256"}, set(), f"manifest.entries[{index}]")
            fixture_name, trace_name = value["fixture"], value["expected_trace"]
            self.assertIsInstance(fixture_name, str)
            self.assertIsInstance(trace_name, str)
            self.assertEqual(Path(fixture_name).name, fixture_name)
            self.assertEqual(Path(trace_name).name, trace_name)
            self.assertGreater(fixture_name, prior_fixture)
            prior_fixture = fixture_name
            self.assertNotIn(fixture_name, expected_members)
            expected_members.add(fixture_name)
            self.assertNotIn(trace_name, expected_members)
            expected_members.add(trace_name)
            for name, hash_name in ((fixture_name, "fixture_sha256"), (trace_name, "expected_trace_sha256")):
                member_path = FIXTURE_ROOT / name
                self.assertTrue(member_path.is_file() and not member_path.is_symlink(), member_path)
                member_raw, _ = self._canonical_document(member_path)
                self.assertRegex(value[hash_name], r"[0-9a-f]{64}\Z")
                self.assertEqual(hashlib.sha256(member_raw).hexdigest(), value[hash_name])
            entries.append(value)
        self.assertEqual(expected_members, {path.name for path in FIXTURE_ROOT.glob("*.json")})
        return entries

    def _fixture(self, entry: dict[str, Any]) -> dict[str, Any]:
        _, fixture = self._canonical_document(FIXTURE_ROOT / entry["fixture"])
        return self._validate_fixture(fixture, entry["fixture"])

    def _expected_trace(self, entry: dict[str, Any], fixture: dict[str, Any]) -> dict[str, Any]:
        _, trace = self._canonical_document(FIXTURE_ROOT / entry["expected_trace"])
        value = self._exact_keys(trace, {"schema", "fixture_id", "transitions"}, set(), entry["expected_trace"])
        self.assertEqual(value["schema"], TRACE_SCHEMA)
        self.assertEqual(value["fixture_id"], fixture["fixture_id"])
        self.assertEqual(len(value["transitions"]), len(fixture["operations"]))
        for index, transition in enumerate(value["transitions"]):
            step = self._exact_keys(transition, {"result", "state"}, set(), f"{entry['expected_trace']}[{index}]")
            self.assertIn(step["result"], RESULTS)
            self._validate_state(step["state"], f"{entry['expected_trace']}[{index}].state")
        return value

    def test_manifest_and_reviewed_trace_are_canonical(self) -> None:
        self.assertEqual(len(self._manifest_entries()), 16)

    def test_python_reference_matches_every_reviewed_transition(self) -> None:
        for entry in self._manifest_entries():
            fixture = self._fixture(entry)
            if "python_reference" not in fixture["executors"]:
                continue
            expected = self._expected_trace(entry, fixture)
            risk = ReferenceRisk.from_fixture(fixture)
            actual = [risk.apply(operation) for operation in fixture["operations"]]
            self.assertEqual(actual, expected["transitions"], fixture["fixture_id"])

    def test_repeated_fixture_replay_is_byte_identical(self) -> None:
        for entry in self._manifest_entries():
            fixture = self._fixture(entry)
            if "python_reference" not in fixture["executors"]:
                continue
            traces = []
            for _ in range(2):
                risk = ReferenceRisk.from_fixture(fixture)
                trace = {"fixture_id": fixture["fixture_id"], "transitions": [risk.apply(operation) for operation in fixture["operations"]]}
                traces.append((phase7.canonical_json(trace) + "\n").encode("utf-8"))
            self.assertEqual(traces[0], traces[1], fixture["fixture_id"])

    def test_cxx_oracle_matches_python_reference_after_every_transition(self) -> None:
        if not (phase7.REPOSITORY_ROOT / "build" / "CMakeCache.txt").is_file():
            self.skipTest("CMake build directory has not been configured")
        for entry in self._manifest_entries():
            fixture = self._fixture(entry)
            if "v1_oracle" not in fixture["executors"]:
                continue
            expected_trace = self._expected_trace(entry, fixture)
            limits = fixture.get("limits", {})
            config = {"oracle": {"schema": "pmm.risk_oracle_launcher.v1", "build_dir": "build", "cmake_target": "pmm_risk_oracle"},
                      "limits": {"maximum_order_quantity_contracts": str(limits.get("maximum_order_quantity_contracts", 5)),
                                 "maximum_absolute_position_contracts": str(limits.get("maximum_absolute_position_contracts", 5)),
                                 "maximum_buy_exposure_contracts": str(limits.get("maximum_buy_exposure_contracts", 5)),
                                 "maximum_sell_exposure_contracts": str(limits.get("maximum_sell_exposure_contracts", 5)),
                                 "maximum_pending_exposure_contracts": str(limits.get("maximum_pending_exposure_contracts", 5)),
                                 "maximum_active_orders": limits.get("maximum_active_orders", 4)}}
            oracle = phase7.CxxRiskOracle(config, canonical_trace=True)
            try:
                for operation, expected in zip(fixture["operations"], expected_trace["transitions"], strict=True):
                    kind = operation["operation"]
                    if kind == "admit":
                        oracle._send(f"ADMIT {operation['client_intent_id']} {operation['side']} {operation['quantity_contracts']} {operation['limit_price_cents']} 0")
                    elif kind == "bind_ingress":
                        oracle._send(f"BIND {operation['client_intent_id']} {operation['ingress_sequence']}")
                    elif kind == "acknowledge":
                        oracle._send(f"ACK {operation['sequence']} {operation['ingress_sequence']} {operation['order_id']} {operation['side']} {operation['quantity_contracts']} {operation['limit_price_cents']} {operation['time_utc_ns']}")
                    elif kind == "fill":
                        oracle._send(f"FILL {operation['sequence']} {operation['order_id']} {operation['side']} {operation['quantity_contracts']} 50 {operation['time_utc_ns']}")
                    elif kind == "command_rejected":
                        oracle._send(f"REJECT {operation['sequence']} {operation['ingress_sequence']} {operation['time_utc_ns']}")
                    elif kind == "kill_switch":
                        oracle._send(f"KILL {'on' if operation['active'] else 'off'}")
                    else:
                        oracle._send(f"CANCEL {operation['sequence']} {operation['order_id']} {operation['time_utc_ns']}")
                    if expected["result"] == "domain_error":
                        with self.assertRaises(ValueError):
                            oracle._receive()
                    else:
                        response = oracle._receive()
                        if expected["result"] == "approved":
                            self.assertEqual(response, f"ADMISSION approved {operation['client_intent_id']}")
                        elif expected["result"] in ADMISSION_REJECTION_CODES:
                            self.assertEqual(response.split(), ["ADMISSION", "rejected", str(operation["client_intent_id"]), str(ADMISSION_REJECTION_CODES[expected["result"]])])
                        else:
                            self.assertTrue(response)
                    cxx_state = oracle.view()
                    cxx_state["event_watermark"] = str(cxx_state["event_watermark"])
                    self.assertEqual(cxx_state, expected["state"], fixture["fixture_id"])
            finally:
                oracle.close()

    def test_reference_refuses_cxx_only_operations(self) -> None:
        for operation in ("order_outcome", "exchange_event", "foreign_trader", "observed_event", "checkpoint", "restore", "portfolio"):
            with self.assertRaises(UnsupportedSharedOperation):
                ReferenceRisk().apply({"operation": operation})


if __name__ == "__main__":
    unittest.main()
