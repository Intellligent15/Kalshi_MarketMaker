"""Fixture-driven conformance tests; the Python model is test-only."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
import unittest

from python import pmm_phase7 as phase7
from python.tests.risk_conformance_reference import ReferenceRisk, UnsupportedSharedOperation


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "risk_conformance" / "v1"


class RiskConformanceTests(unittest.TestCase):
    def _manifest_entries(self) -> list[dict[str, object]]:
        return json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))["payload"]["entries"]

    def _fixture(self, entry: dict[str, object]) -> dict[str, object]:
        fixture = json.loads((FIXTURE_ROOT / str(entry["fixture"])).read_text(encoding="utf-8"))
        self._validate_fixture(fixture)
        return fixture

    def _validate_fixture(self, fixture: dict[str, object]) -> None:
        self.assertEqual(fixture["schema"], "pmm.risk_conformance_fixture.v1")
        self.assertIsInstance(fixture["fixture_id"], str)
        self.assertIsInstance(fixture["operations"], list)
        for operation in fixture["operations"]:
            self.assertIn(operation["operation"], {"admit", "bind_ingress", "acknowledge", "fill",
                                                      "cancel", "logical_expiry", "command_rejected",
                                                      "kill_switch"})

    def test_manifest_and_reviewed_trace_are_canonical(self) -> None:
        manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], "pmm.risk_conformance_fixture_manifest.v1")
        payload = manifest["payload"]
        self.assertEqual(payload["schema"], manifest["schema"])
        self.assertEqual(
            manifest["payload_sha256"],
            hashlib.sha256((phase7.canonical_json(payload) + "\n").encode("utf-8")).hexdigest(),
        )
        for entry in payload["entries"]:
            for name, hash_name in ((entry["fixture"], "fixture_sha256"),
                                    (entry["expected_trace"], "expected_trace_sha256")):
                raw = (FIXTURE_ROOT / name).read_bytes()
                self.assertTrue(raw.endswith(b"\n"))
                self.assertEqual(hashlib.sha256(raw).hexdigest(), entry[hash_name])
                parsed = json.loads(raw)
                self.assertEqual(raw.decode("utf-8").strip(), phase7.canonical_json(parsed))

    def test_fixture_or_trace_tampering_changes_its_digest(self) -> None:
        entry = self._manifest_entries()[0]
        for name, hash_name in ((entry["fixture"], "fixture_sha256"),
                                (entry["expected_trace"], "expected_trace_sha256")):
            raw = (FIXTURE_ROOT / name).read_bytes()
            tampered = raw[:-2] + (b"0" if raw[-2:-1] != b"0" else b"1") + b"\n"
            self.assertNotEqual(hashlib.sha256(tampered).hexdigest(), entry[hash_name])

        manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
        tampered_payload = dict(manifest["payload"])
        tampered_payload["entries"] = list(reversed(tampered_payload["entries"]))
        self.assertNotEqual(
            manifest["payload_sha256"],
            hashlib.sha256((phase7.canonical_json(tampered_payload) + "\n").encode("utf-8")).hexdigest(),
        )

    def test_fixture_schema_rejects_malformed_documents(self) -> None:
        valid = {"schema": "pmm.risk_conformance_fixture.v1", "fixture_id": "valid",
                 "operations": [{"operation": "admit"}]}
        self._validate_fixture(valid)
        for malformed in (
            {"schema": "wrong", "fixture_id": "bad", "operations": []},
            {"schema": "pmm.risk_conformance_fixture.v1", "fixture_id": 1, "operations": []},
            {"schema": "pmm.risk_conformance_fixture.v1", "fixture_id": "bad",
             "operations": [{"operation": "not_an_operation"}]},
        ):
            with self.assertRaises(AssertionError):
                self._validate_fixture(malformed)

    def test_python_reference_matches_every_reviewed_transition(self) -> None:
        for entry in self._manifest_entries():
            fixture = self._fixture(entry)
            expected = json.loads((FIXTURE_ROOT / entry["expected_trace"]).read_text(encoding="utf-8"))
            risk = ReferenceRisk.from_fixture(fixture)
            actual = [risk.apply(operation) for operation in fixture["operations"]]
            self.assertEqual(actual, expected["transitions"], fixture["fixture_id"])

    def test_repeated_fixture_replay_is_byte_identical(self) -> None:
        for entry in self._manifest_entries():
            fixture = self._fixture(entry)
            traces = []
            for _ in range(2):
                risk = ReferenceRisk.from_fixture(fixture)
                trace = {"fixture_id": fixture["fixture_id"],
                         "transitions": [risk.apply(operation) for operation in fixture["operations"]]}
                traces.append((phase7.canonical_json(trace) + "\n").encode("utf-8"))
            self.assertEqual(traces[0], traces[1], fixture["fixture_id"])

    def test_cxx_oracle_matches_python_reference_after_every_transition(self) -> None:
        if not (phase7.REPOSITORY_ROOT / "build" / "CMakeCache.txt").is_file():
            self.skipTest("CMake build directory has not been configured")
        for entry in self._manifest_entries():
            fixture = self._fixture(entry)
            if "v1_oracle" not in fixture.get("executors", ["v1_oracle"]):
                continue
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
                reference = ReferenceRisk.from_fixture(fixture)
                l = config["limits"]
                oracle._send(f"INIT 1 1 1 1 {l['maximum_order_quantity_contracts']} {l['maximum_absolute_position_contracts']} {l['maximum_buy_exposure_contracts']} {l['maximum_sell_exposure_contracts']} {l['maximum_pending_exposure_contracts']} {l['maximum_active_orders']}")
                self.assertEqual(oracle._receive(), "READY")
                for operation in fixture["operations"]:
                    expected = reference.apply(operation)
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
                            self.assertTrue(response.startswith("ADMISSION approved"))
                        elif expected["result"].endswith("_limit") or expected["result"] in {"kill_switch_active", "duplicate_client_intent"}:
                            self.assertTrue(response.startswith("ADMISSION rejected"))
                        else:
                            self.assertTrue(response)
                    cxx_state = oracle.view()
                    cxx_state["event_watermark"] = str(cxx_state["event_watermark"])
                    self.assertEqual(cxx_state, expected["state"], fixture["fixture_id"])
            finally:
                oracle.close()

    def test_reference_refuses_cxx_only_operations(self) -> None:
        for operation in ("order_outcome", "exchange_event", "foreign_trader", "observed_event",
                          "checkpoint", "restore", "portfolio"):
            with self.assertRaises(UnsupportedSharedOperation):
                ReferenceRisk().apply({"operation": operation})


if __name__ == "__main__":
    unittest.main()
