"""Checkpoint conformance corpus tests; the Python model is test-only evidence."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

from python import pmm_phase7 as phase7
from python.tests.risk_checkpoint_reference import (
    CHECKPOINT_SCHEMA,
    capture,
    restore_reference,
    validate_checkpoint,
)
from python.tests.risk_conformance_reference import ReferenceRisk, UnsupportedSharedOperation

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "risk_conformance" / "checkpoint_v1"
MANIFEST_SCHEMA = "pmm.risk_checkpoint_conformance_fixture_manifest.v1"
FIXTURE_SCHEMA = "pmm.risk_checkpoint_conformance_fixture.v1"
TRACE_SCHEMA = "pmm.risk_checkpoint_conformance_expected_trace.v1"
EXECUTORS = {"direct_cpp", "python_reference"}
CHECKPOINT_REJECTIONS = {
    "checkpoint_active_order_limit",
    "checkpoint_buy_exposure_limit",
    "checkpoint_contract_mismatch",
    "checkpoint_duplicate_client_intent",
    "checkpoint_duplicate_ingress",
    "checkpoint_duplicate_order_id",
    "checkpoint_non_post_only",
    "checkpoint_order_quantity_limit",
    "checkpoint_pending_exposure_limit",
    "checkpoint_position_limit",
    "checkpoint_sell_exposure_limit",
    "checkpoint_zero_ingress",
    "checkpoint_zero_live_quantity",
    "checkpoint_zero_pending_quantity",
}
LIFECYCLE_RESULTS = {
    "active_order_limit", "applied", "approved", "buy_exposure_limit", "contract_mismatch",
    "domain_error", "duplicate_client_intent", "kill_switch_active", "order_quantity_limit",
    "pending_exposure_limit", "position_limit", "sell_exposure_limit",
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
LIMIT_KEYS = {
    "maximum_order_quantity_contracts", "maximum_absolute_position_contracts",
    "maximum_buy_exposure_contracts", "maximum_sell_exposure_contracts",
    "maximum_pending_exposure_contracts", "maximum_active_orders",
}
UNSIGNED_DECIMAL = re.compile(r"\A(?:0|[1-9][0-9]*)\Z")
SIGNED_DECIMAL = re.compile(r"\A(?:0|[1-9][0-9]*|-[1-9][0-9]*)\Z")


def fixture_limits_document(fixture: dict[str, Any]) -> dict[str, Any]:
    limits = fixture.get("limits", {})
    return {
        "maximum_absolute_position_contracts": str(limits.get("maximum_absolute_position_contracts", 5)),
        "maximum_active_orders": limits.get("maximum_active_orders", 4),
        "maximum_buy_exposure_contracts": str(limits.get("maximum_buy_exposure_contracts", 5)),
        "maximum_order_quantity_contracts": str(limits.get("maximum_order_quantity_contracts", 5)),
        "maximum_pending_exposure_contracts": str(limits.get("maximum_pending_exposure_contracts", 5)),
        "maximum_sell_exposure_contracts": str(limits.get("maximum_sell_exposure_contracts", 5)),
    }


class RiskCheckpointConformanceTests(unittest.TestCase):
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

    def _validate_checkpoint_document(self, document: object, context: str, *, strict: bool) -> dict[str, Any]:
        value = self._exact_keys(
            document,
            {"account_id", "contract_id", "event_watermark", "kill_switch_active", "limits", "live_orders", "net_position_contracts", "pending_orders", "schema", "strategy_id", "trader_id"},
            set(), context,
        )
        self.assertEqual(value["schema"], CHECKPOINT_SCHEMA, context)
        for key in ("account_id", "strategy_id", "trader_id", "contract_id"):
            self._unsigned(value[key], f"{context}.{key}", positive=True)
        limits = self._exact_keys(value["limits"], LIMIT_KEYS, set(), f"{context}.limits")
        for key in LIMIT_KEYS - {"maximum_active_orders"}:
            self._unsigned(limits[key], f"{context}.limits.{key}", positive=True)
        self.assertIsInstance(limits["maximum_active_orders"], int, context)
        self.assertNotIsInstance(limits["maximum_active_orders"], bool, context)
        self.assertGreater(limits["maximum_active_orders"], 0, context)
        self._unsigned(value["event_watermark"], f"{context}.event_watermark")
        self._signed(value["net_position_contracts"], f"{context}.net_position_contracts")
        self.assertIsInstance(value["kill_switch_active"], bool, context)
        self.assertIsInstance(value["live_orders"], list, context)
        self.assertIsInstance(value["pending_orders"], list, context)
        prior_order = 0
        for index, order in enumerate(value["live_orders"]):
            item_context = f"{context}.live_orders[{index}]"
            item = self._exact_keys(order, {"acknowledged_at_utc_ns", "limit_price_cents", "order_id", "remaining_quantity_contracts", "side"}, set(), item_context)
            order_id = self._unsigned(item["order_id"], f"{item_context}.order_id", positive=True)
            if index:
                self.assertTrue(order_id > prior_order if strict else order_id >= prior_order, item_context)
            prior_order = order_id
            self.assertIn(item["side"], {"buy", "sell"}, item_context)
            self._unsigned(item["remaining_quantity_contracts"], f"{item_context}.remaining_quantity_contracts", positive=strict)
            self._unsigned(item["limit_price_cents"], f"{item_context}.limit_price_cents")
            self._signed(item["acknowledged_at_utc_ns"], f"{item_context}.acknowledged_at_utc_ns")
        prior_client = 0
        for index, order in enumerate(value["pending_orders"]):
            item_context = f"{context}.pending_orders[{index}]"
            item = self._exact_keys(order, {"client_intent_id", "contract_id", "ingress_sequence", "limit_price_cents", "post_only", "quantity_contracts", "side"}, set(), item_context)
            client_id = self._unsigned(item["client_intent_id"], f"{item_context}.client_intent_id", positive=True)
            if index:
                self.assertTrue(client_id > prior_client if strict else client_id >= prior_client, item_context)
            prior_client = client_id
            self._unsigned(item["contract_id"], f"{item_context}.contract_id", positive=True)
            self.assertIsInstance(item["post_only"], bool, item_context)
            if strict:
                self.assertTrue(item["post_only"], item_context)
            if item["ingress_sequence"] is not None:
                self._unsigned(item["ingress_sequence"], f"{item_context}.ingress_sequence", positive=strict)
            self.assertIn(item["side"], {"buy", "sell"}, item_context)
            self._unsigned(item["quantity_contracts"], f"{item_context}.quantity_contracts", positive=strict)
            self._unsigned(item["limit_price_cents"], f"{item_context}.limit_price_cents")
        return value

    def _validate_fixture(self, fixture: object, filename: str) -> dict[str, Any]:
        value = self._exact_keys(fixture, {"schema", "fixture_id", "kind"}, {"checkpoint", "contract_id", "executors", "limits", "operations"}, filename)
        self.assertEqual(value["schema"], FIXTURE_SCHEMA, filename)
        self.assertIsInstance(value["fixture_id"], str, filename)
        self.assertRegex(value["fixture_id"], r"[a-z0-9_]+\Z", filename)
        self.assertEqual(filename, f"{value['fixture_id']}.json", filename)
        self.assertIn(value["kind"], {"roundtrip", "document_restore"}, filename)
        if "executors" in value:
            self.assertIsInstance(value["executors"], list, filename)
            self.assertTrue(value["executors"], filename)
            self.assertEqual(len(value["executors"]), len(set(value["executors"])), filename)
            self.assertTrue(set(value["executors"]) <= EXECUTORS, filename)
        else:
            value["executors"] = ["direct_cpp", "python_reference"]
        if value["kind"] == "roundtrip":
            self.assertNotIn("checkpoint", value, filename)
            self.assertIn("operations", value, filename)
            if "contract_id" in value:
                self._unsigned(value["contract_id"], f"{filename}.contract_id", positive=True)
            limits = value.get("limits", {})
            self.assertIsInstance(limits, dict, filename)
            self.assertTrue(set(limits) <= LIMIT_KEYS, filename)
        else:
            self.assertNotIn("contract_id", value, filename)
            self.assertNotIn("limits", value, filename)
            self.assertIn("checkpoint", value, filename)
            self._validate_checkpoint_document(value["checkpoint"], f"{filename}.checkpoint", strict=False)
        operations = value.get("operations", [])
        self.assertIsInstance(operations, list, filename)
        saw_capture = False
        previous_was_capture = False
        for index, operation in enumerate(operations):
            self.assertIsInstance(operation, dict, f"{filename}.operations[{index}]")
            kind = operation.get("operation")
            if kind in {"checkpoint", "restore"}:
                self.assertEqual(value["kind"], "roundtrip", f"{filename}.operations[{index}]")
                self.assertEqual(set(operation), {"operation"}, f"{filename}.operations[{index}]")
                if kind == "restore":
                    self.assertTrue(previous_was_capture, f"{filename}.operations[{index}]")
                saw_capture = saw_capture or kind == "checkpoint"
                previous_was_capture = kind == "checkpoint"
                continue
            previous_was_capture = False
            self.assertIn(kind, OPERATION_FIELDS, f"{filename}.operations[{index}]")
            self.assertEqual(set(operation), OPERATION_FIELDS[kind], f"{filename}.operations[{index}]")
        if value["kind"] == "roundtrip":
            self.assertTrue(operations, filename)
            self.assertTrue(saw_capture, filename)
        return value

    def _validate_trace(self, trace: object, fixture: dict[str, Any], filename: str) -> dict[str, Any]:
        value = self._exact_keys(trace, {"schema", "fixture_id", "transitions"}, set(), filename)
        self.assertEqual(value["schema"], TRACE_SCHEMA, filename)
        self.assertEqual(value["fixture_id"], fixture["fixture_id"], filename)
        self.assertIsInstance(value["transitions"], list, filename)
        operations = fixture.get("operations", [])
        if fixture["kind"] == "roundtrip":
            self.assertEqual(len(value["transitions"]), len(operations), filename)
            expected_limits = fixture_limits_document(fixture)
            expected_contract = str(fixture.get("contract_id", "1"))
            for index, (operation, transition) in enumerate(zip(operations, value["transitions"], strict=True)):
                context = f"{filename}[{index}]"
                kind = operation["operation"]
                if kind == "checkpoint":
                    step = self._exact_keys(transition, {"checkpoint", "result", "state"}, set(), context)
                    self.assertEqual(step["result"], "captured", context)
                    document = self._validate_checkpoint_document(step["checkpoint"], f"{context}.checkpoint", strict=True)
                    for key in ("account_id", "strategy_id", "trader_id"):
                        self.assertEqual(document[key], "1", context)
                    self.assertEqual(document["contract_id"], expected_contract, context)
                    self.assertEqual(document["limits"], expected_limits, context)
                elif kind == "restore":
                    step = self._exact_keys(transition, {"result", "state"}, set(), context)
                    self.assertEqual(step["result"], "restored", context)
                else:
                    step = self._exact_keys(transition, {"result", "state"}, set(), context)
                    self.assertIn(step["result"], LIFECYCLE_RESULTS, context)
                self._validate_state(step["state"], f"{context}.state")
            return value
        self.assertEqual(len(value["transitions"]), len(operations) + 1, filename)
        first = value["transitions"][0]
        result = first.get("result")
        if result in CHECKPOINT_REJECTIONS:
            self._exact_keys(first, {"result"}, set(), f"{filename}[0]")
            self.assertEqual(operations, [], filename)
        else:
            step = self._exact_keys(first, {"result", "state"}, set(), f"{filename}[0]")
            self.assertEqual(step["result"], "restored", f"{filename}[0]")
            self._validate_state(step["state"], f"{filename}[0].state")
        for index, transition in enumerate(value["transitions"][1:], start=1):
            step = self._exact_keys(transition, {"result", "state"}, set(), f"{filename}[{index}]")
            self.assertIn(step["result"], LIFECYCLE_RESULTS, f"{filename}[{index}]")
            self._validate_state(step["state"], f"{filename}[{index}].state")
        return value

    def _manifest_entries(self, root: Path) -> list[dict[str, Any]]:
        raw, manifest = self._canonical_document(root / "manifest.json")
        del raw
        top = self._exact_keys(manifest, {"schema", "payload", "payload_sha256"}, set(), "manifest")
        self.assertEqual(top["schema"], MANIFEST_SCHEMA)
        payload = self._exact_keys(top["payload"], {"schema", "entries"}, set(), "manifest.payload")
        self.assertEqual(payload["schema"], MANIFEST_SCHEMA)
        self.assertEqual(top["payload_sha256"], hashlib.sha256((phase7.canonical_json(payload) + "\n").encode("utf-8")).hexdigest())
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
                member_path = root / name
                self.assertTrue(member_path.is_file() and not member_path.is_symlink(), member_path)
                member_raw, _ = self._canonical_document(member_path)
                self.assertRegex(value[hash_name], r"[0-9a-f]{64}\Z")
                self.assertEqual(hashlib.sha256(member_raw).hexdigest(), value[hash_name])
            entries.append(value)
        self.assertEqual(expected_members, {path.name for path in root.glob("*.json")})
        return entries

    def _verify_corpus(self, root: Path) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        verified = []
        for entry in self._manifest_entries(root):
            _, fixture = self._canonical_document(root / entry["fixture"])
            fixture = self._validate_fixture(fixture, entry["fixture"])
            _, trace = self._canonical_document(root / entry["expected_trace"])
            trace = self._validate_trace(trace, fixture, entry["expected_trace"])
            verified.append((fixture, trace))
        return verified

    def _run_fixture(self, fixture: dict[str, Any], trace: dict[str, Any]) -> list[Any]:
        log: list[Any] = []
        operations = fixture.get("operations", [])
        if fixture["kind"] == "roundtrip":
            reference = ReferenceRisk.from_fixture(fixture)
            restored = None
            last_capture = None
            for operation, expected in zip(operations, trace["transitions"], strict=True):
                kind = operation["operation"]
                if kind == "checkpoint":
                    captured = capture(reference)
                    self.assertEqual(captured, expected["checkpoint"], fixture["fixture_id"])
                    self.assertEqual(phase7.canonical_json(captured), phase7.canonical_json(expected["checkpoint"]), fixture["fixture_id"])
                    if restored is not None:
                        self.assertEqual(capture(restored), expected["checkpoint"], fixture["fixture_id"])
                    last_capture = expected["checkpoint"]
                    self.assertEqual(reference.snapshot(), expected["state"], fixture["fixture_id"])
                    log.append(captured)
                elif kind == "restore":
                    self.assertIsNotNone(last_capture, fixture["fixture_id"])
                    self.assertIsNone(validate_checkpoint(last_capture), fixture["fixture_id"])
                    restored = restore_reference(last_capture)
                    self.assertEqual(restored.snapshot(), expected["state"], fixture["fixture_id"])
                    self.assertEqual(reference.snapshot(), expected["state"], fixture["fixture_id"])
                    self.assertEqual(capture(restored), capture(reference), fixture["fixture_id"])
                    log.append("restored")
                else:
                    result = reference.apply(operation)
                    self.assertEqual(result, {"result": expected["result"], "state": expected["state"]}, fixture["fixture_id"])
                    if restored is not None:
                        self.assertEqual(restored.apply(operation), result, fixture["fixture_id"])
                        self.assertEqual(capture(restored), capture(reference), fixture["fixture_id"])
                    log.append(result)
                if restored is not None and kind != "restore":
                    self.assertEqual(restored.snapshot(), expected["state"], fixture["fixture_id"])
            return log
        document = fixture["checkpoint"]
        code = validate_checkpoint(document)
        first = trace["transitions"][0]
        if first["result"] in CHECKPOINT_REJECTIONS:
            self.assertEqual(code, first["result"], fixture["fixture_id"])
            log.append(code)
            return log
        self.assertIsNone(code, fixture["fixture_id"])
        restored = restore_reference(document)
        self.assertEqual(restored.snapshot(), first["state"], fixture["fixture_id"])
        log.append(capture(restored))
        for operation, expected in zip(operations, trace["transitions"][1:], strict=True):
            result = restored.apply(operation)
            self.assertEqual(result, {"result": expected["result"], "state": expected["state"]}, fixture["fixture_id"])
            log.append(result)
        return log

    def test_manifest_and_reviewed_documents_are_canonical(self) -> None:
        self.assertEqual(len(self._verify_corpus(FIXTURE_ROOT)), 26)

    def test_python_reference_matches_every_reviewed_transition(self) -> None:
        for fixture, trace in self._verify_corpus(FIXTURE_ROOT):
            if "python_reference" not in fixture["executors"]:
                continue
            self._run_fixture(fixture, trace)

    def test_repeated_replay_is_byte_identical(self) -> None:
        for fixture, trace in self._verify_corpus(FIXTURE_ROOT):
            if "python_reference" not in fixture["executors"]:
                continue
            first = phase7.canonical_json(self._run_fixture(fixture, trace))
            second = phase7.canonical_json(self._run_fixture(fixture, trace))
            self.assertEqual(first.encode("utf-8"), second.encode("utf-8"), fixture["fixture_id"])

    def test_reference_apply_still_refuses_checkpoint_operations(self) -> None:
        for operation in ("checkpoint", "restore"):
            with self.assertRaises(UnsupportedSharedOperation):
                ReferenceRisk().apply({"operation": operation})

    # --- negative matrix: one broken verifier rule per test -----------------------------

    def _mutated_corpus_fails(self, mutate) -> None:
        with tempfile.TemporaryDirectory(prefix="pmm-risk-checkpoint-") as scratch:
            root = Path(scratch) / "checkpoint_v1"
            shutil.copytree(FIXTURE_ROOT, root)
            mutate(root)
            with self.assertRaises(AssertionError):
                self._verify_corpus(root)

    @staticmethod
    def _write(root: Path, name: str, document: dict[str, Any]) -> None:
        (root / name).write_bytes((phase7.canonical_json(document) + "\n").encode("utf-8"))

    @staticmethod
    def _load(root: Path, name: str) -> dict[str, Any]:
        return json.loads((root / name).read_bytes())

    @classmethod
    def _rehash(cls, root: Path) -> None:
        manifest = cls._load(root, "manifest.json")
        for entry in manifest["payload"]["entries"]:
            entry["fixture_sha256"] = hashlib.sha256((root / entry["fixture"]).read_bytes()).hexdigest()
            entry["expected_trace_sha256"] = hashlib.sha256((root / entry["expected_trace"]).read_bytes()).hexdigest()
        manifest["payload_sha256"] = hashlib.sha256((phase7.canonical_json(manifest["payload"]) + "\n").encode("utf-8")).hexdigest()
        cls._write(root, "manifest.json", manifest)

    def test_rejects_tampered_noncanonical_member(self) -> None:
        def mutate(root: Path) -> None:
            with (root / "roundtrip_empty_state.json").open("ab") as member:
                member.write(b" ")
        self._mutated_corpus_fails(mutate)

    def test_rejects_unknown_fixture_field(self) -> None:
        def mutate(root: Path) -> None:
            fixture = self._load(root, "roundtrip_empty_state.json")
            fixture["surprise"] = "1"
            self._write(root, "roundtrip_empty_state.json", fixture)
            self._rehash(root)
        self._mutated_corpus_fails(mutate)

    def test_rejects_bad_member_hash(self) -> None:
        def mutate(root: Path) -> None:
            manifest = self._load(root, "manifest.json")
            manifest["payload"]["entries"][0]["fixture_sha256"] = "a" * 64
            manifest["payload_sha256"] = hashlib.sha256((phase7.canonical_json(manifest["payload"]) + "\n").encode("utf-8")).hexdigest()
            self._write(root, "manifest.json", manifest)
        self._mutated_corpus_fails(mutate)

    def test_rejects_unsafe_member_path(self) -> None:
        def mutate(root: Path) -> None:
            manifest = self._load(root, "manifest.json")
            manifest["payload"]["entries"][0]["fixture"] = "../escape.json"
            manifest["payload_sha256"] = hashlib.sha256((phase7.canonical_json(manifest["payload"]) + "\n").encode("utf-8")).hexdigest()
            self._write(root, "manifest.json", manifest)
        self._mutated_corpus_fails(mutate)

    def test_rejects_frozen_v1_oracle_executor(self) -> None:
        def mutate(root: Path) -> None:
            fixture = self._load(root, "roundtrip_empty_state.json")
            fixture["executors"] = ["v1_oracle"]
            self._write(root, "roundtrip_empty_state.json", fixture)
            self._rehash(root)
        self._mutated_corpus_fails(mutate)

    def test_rejects_state_on_rejected_restore(self) -> None:
        def mutate(root: Path) -> None:
            donor = self._load(root, "document_restore_unbound_pending.expected.json")
            trace = self._load(root, "checkpoint_zero_ingress.expected.json")
            trace["transitions"][0]["state"] = donor["transitions"][0]["state"]
            self._write(root, "checkpoint_zero_ingress.expected.json", trace)
            self._rehash(root)
        self._mutated_corpus_fails(mutate)

    def test_rejects_restore_without_preceding_checkpoint(self) -> None:
        def mutate(root: Path) -> None:
            fixture = self._load(root, "roundtrip_empty_state.json")
            fixture["operations"].insert(0, {"operation": "restore"})
            self._write(root, "roundtrip_empty_state.json", fixture)
            self._rehash(root)
        self._mutated_corpus_fails(mutate)

    def test_rejects_noncanonical_decimal(self) -> None:
        def mutate(root: Path) -> None:
            fixture = self._load(root, "checkpoint_zero_ingress.json")
            fixture["checkpoint"]["event_watermark"] = "01"
            self._write(root, "checkpoint_zero_ingress.json", fixture)
            self._rehash(root)
        self._mutated_corpus_fails(mutate)

    def test_rejects_unreferenced_document(self) -> None:
        def mutate(root: Path) -> None:
            (root / "extra.json").write_bytes(b"{}\n")
        self._mutated_corpus_fails(mutate)


if __name__ == "__main__":
    unittest.main()
