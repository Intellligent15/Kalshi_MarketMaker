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
    def test_manifest_and_reviewed_trace_are_canonical(self) -> None:
        manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], "pmm.risk_conformance_fixture_manifest.v1")
        for entry in manifest["entries"]:
            for name, hash_name in ((entry["fixture"], "fixture_sha256"),
                                    (entry["expected_trace"], "expected_trace_sha256")):
                raw = (FIXTURE_ROOT / name).read_bytes()
                self.assertTrue(raw.endswith(b"\n"))
                self.assertEqual(hashlib.sha256(raw).hexdigest(), entry[hash_name])
                parsed = json.loads(raw)
                self.assertEqual(raw.decode("utf-8").strip(), phase7.canonical_json(parsed))

    def test_python_reference_matches_every_reviewed_transition(self) -> None:
        fixture = json.loads((FIXTURE_ROOT / "lifecycle.json").read_text(encoding="utf-8"))
        expected = json.loads((FIXTURE_ROOT / "lifecycle.expected.json").read_text(encoding="utf-8"))
        risk = ReferenceRisk()
        actual = [risk.apply(operation) for operation in fixture["operations"]]
        self.assertEqual(actual, expected["transitions"])

    def test_cxx_oracle_matches_python_reference_after_every_transition(self) -> None:
        if not (phase7.REPOSITORY_ROOT / "build" / "CMakeCache.txt").is_file():
            self.skipTest("CMake build directory has not been configured")
        fixture = json.loads((FIXTURE_ROOT / "lifecycle.json").read_text(encoding="utf-8"))
        reference = ReferenceRisk()
        config = {"oracle": {"schema": "pmm.risk_oracle_launcher.v1", "build_dir": "build", "cmake_target": "pmm_risk_oracle"},
                  "limits": {"maximum_order_quantity_contracts": "5", "maximum_absolute_position_contracts": "5",
                             "maximum_buy_exposure_contracts": "5", "maximum_sell_exposure_contracts": "5",
                             "maximum_pending_exposure_contracts": "5", "maximum_active_orders": 4}}
        oracle = phase7.CxxRiskOracle(config, canonical_trace=True)
        try:
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
                else:
                    oracle._send(f"CANCEL {operation['sequence']} {operation['order_id']} {operation['time_utc_ns']}")
                response = oracle._receive()
                self.assertFalse(response.startswith("ERROR"))
                cxx_state = oracle.view()
                cxx_state["event_watermark"] = str(cxx_state["event_watermark"])
                self.assertEqual(cxx_state, expected["state"])
        finally:
            oracle.close()

    def test_reference_refuses_cxx_only_operations(self) -> None:
        with self.assertRaises(UnsupportedSharedOperation):
            ReferenceRisk().apply({"operation": "order_outcome"})


if __name__ == "__main__":
    unittest.main()
