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
        manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))["payload"]
        entry = manifest["entries"][0]
        for name, hash_name in ((entry["fixture"], "fixture_sha256"),
                                (entry["expected_trace"], "expected_trace_sha256")):
            raw = (FIXTURE_ROOT / name).read_bytes()
            tampered = raw[:-2] + (b"0" if raw[-2:-1] != b"0" else b"1") + b"\n"
            self.assertNotEqual(hashlib.sha256(tampered).hexdigest(), entry[hash_name])

    def test_python_reference_matches_every_reviewed_transition(self) -> None:
        manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))["payload"]
        for entry in manifest["entries"]:
            fixture = json.loads((FIXTURE_ROOT / entry["fixture"]).read_text(encoding="utf-8"))
            expected = json.loads((FIXTURE_ROOT / entry["expected_trace"]).read_text(encoding="utf-8"))
            risk = ReferenceRisk()
            actual = [risk.apply(operation) for operation in fixture["operations"]]
            self.assertEqual(actual, expected["transitions"], fixture["fixture_id"])

    def test_repeated_fixture_replay_is_byte_identical(self) -> None:
        fixture = json.loads((FIXTURE_ROOT / "lifecycle.json").read_text(encoding="utf-8"))
        traces = []
        for _ in range(2):
            risk = ReferenceRisk()
            trace = {"fixture_id": fixture["fixture_id"],
                     "transitions": [risk.apply(operation) for operation in fixture["operations"]]}
            traces.append((phase7.canonical_json(trace) + "\n").encode("utf-8"))
        self.assertEqual(traces[0], traces[1])

    def test_cxx_oracle_matches_python_reference_after_every_transition(self) -> None:
        if not (phase7.REPOSITORY_ROOT / "build" / "CMakeCache.txt").is_file():
            self.skipTest("CMake build directory has not been configured")
        config = {"oracle": {"schema": "pmm.risk_oracle_launcher.v1", "build_dir": "build", "cmake_target": "pmm_risk_oracle"},
                  "limits": {"maximum_order_quantity_contracts": "5", "maximum_absolute_position_contracts": "5",
                             "maximum_buy_exposure_contracts": "5", "maximum_sell_exposure_contracts": "5",
                             "maximum_pending_exposure_contracts": "5", "maximum_active_orders": 4}}
        oracle = phase7.CxxRiskOracle(config, canonical_trace=True)
        try:
            manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))["payload"]
            for entry in manifest["entries"]:
                fixture = json.loads((FIXTURE_ROOT / entry["fixture"]).read_text(encoding="utf-8"))
                reference = ReferenceRisk()
                oracle._send("INIT 1 1 1 1 5 5 5 5 5 4")
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
                    else:
                        oracle._send(f"CANCEL {operation['sequence']} {operation['order_id']} {operation['time_utc_ns']}")
                    if expected["result"] == "domain_error":
                        with self.assertRaises(ValueError):
                            oracle._receive()
                    else:
                        self.assertTrue(oracle._receive())
                    cxx_state = oracle.view()
                    cxx_state["event_watermark"] = str(cxx_state["event_watermark"])
                    self.assertEqual(cxx_state, expected["state"], fixture["fixture_id"])
        finally:
            oracle.close()

    def test_reference_refuses_cxx_only_operations(self) -> None:
        with self.assertRaises(UnsupportedSharedOperation):
            ReferenceRisk().apply({"operation": "order_outcome"})


if __name__ == "__main__":
    unittest.main()
