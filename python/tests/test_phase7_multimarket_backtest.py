from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import shutil
import sys
import unittest
from unittest import mock
import uuid

from jsonschema import Draft202012Validator

from python.tests import test_phase7 as phase7_tests

phase7 = phase7_tests.phase7

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))
import pmm_phase7_multimarket as multimarket


class MultiMarketBacktestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.generated_root = phase7.REPOSITORY_ROOT / "data" / "processed" / f"b2b2-test-{uuid.uuid4()}"
        self.generated_root.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.generated_root, ignore_errors=True)

    def make_v2_capture(self, **kwargs):
        return phase7_tests.Phase7Tests.make_v2_capture(self, **kwargs)

    def build_inputs(self) -> tuple[Path, Path]:
        normalized = self.generated_root / "normalized"
        phase7.normalize_capture_v3(self.make_v2_capture(), normalized)
        fake = {
            "product_terms_sha256": "1" * 64,
            "source_manifest_sha256": "2" * 64,
            "review_sha256": "3" * 64,
        }
        policy_hash = "4" * 64
        product = json.loads((normalized / "product.json").read_text())
        for entry in product["products"]:
            entry.update({"authoritative_identity": {"market_ticker": entry["ticker"]}, **fake, "conversion_policy_sha256": policy_hash})
        phase7.write_json(normalized / "product.json", product)
        manifest = json.loads((normalized / "manifest.json").read_text())
        manifest["output_product_sha256"] = phase7.sha256_file(normalized / "product.json")
        manifest["product_catalog_sha256"] = "5" * 64
        manifest["conversion_policy_sha256"] = policy_hash
        manifest["product_lineage"] = [{"ticker": ticker, **fake} for ticker in manifest["market_tickers"]]
        phase7.write_json(normalized / "manifest.json", manifest)
        features = self.generated_root / "features"
        phase7.materialize_features_v3(normalized, features)
        return normalized, features

    def make_config(self) -> tuple[Path, dict]:
        normalized, features = self.build_inputs()
        relative = lambda path: str(path.relative_to(phase7.REPOSITORY_ROOT))
        feature_manifest = json.loads((features / "manifest.json").read_text())
        products = []
        for ordinal, item in enumerate(feature_manifest["products"], start=1):
            identity = item["product_identity"]
            products.append(
                {
                    "product_identity": {
                        "venue": "kalshi", "environment": "production",
                        "ticker": identity["ticker"], "venue_market_id": identity["venue_market_id"],
                        "input_product_entry_sha256": item["input_product_entry_sha256"],
                    },
                    "contract_identity": {"contract_id": ordinal, "side": "yes"},
                    "strategy": {
                        "schema": "pmm.baseline_market_maker.v1", "strategy_instance_id": f"strategy-{ordinal}",
                        "decision_interval_ns": 1, "order_lifetime_ns": 1_000_000_000,
                        "minimum_spread_dollars": "0.01", "quote_quantity_contracts": "1",
                    },
                    "latency": {"market_data_ns": 0, "decision_ns": 0, "order_ns": 0, "acknowledgement_ns": 0, "cancellation_ns": 0, "fill_ns": 0},
                    "reviewed_lineage": item["reviewed_lineage"],
                    "risk_binding": {"account_id": 1, "strategy_id": ordinal, "trader_id": ordinal, "contract_id": ordinal},
                }
            )
        config = {
            "schema": multimarket.CONFIG_SCHEMA, "run_id": "two-market", "seed": 7,
            "inputs": {
                "normalization": {
                    "manifest_path": relative(normalized / "manifest.json"), "manifest_sha256": phase7.sha256_file(normalized / "manifest.json"),
                    "records_path": relative(normalized / "records.jsonl"), "records_sha256": phase7.sha256_file(normalized / "records.jsonl"),
                    "source_scopes_path": relative(normalized / "source_scopes.json"), "source_scopes_sha256": phase7.sha256_file(normalized / "source_scopes.json"),
                    "product_map_path": relative(normalized / "product.json"), "product_map_sha256": phase7.sha256_file(normalized / "product.json"),
                },
                "features": {
                    "manifest_path": relative(features / "manifest.json"), "manifest_sha256": phase7.sha256_file(features / "manifest.json"),
                    "rows_path": relative(features / "features.jsonl"), "rows_sha256": phase7.sha256_file(features / "features.jsonl"),
                    "feature_definition_sha256": multimarket._sha256_value(feature_manifest["feature_definitions"]),
                },
            },
            "products": products,
            "execution": {"model": "no_fill_v1", "truth_category": "ModelDerived", "scheduling_policy": multimarket.SCHEDULING_POLICY},
            "risk": {
                "engine": "cxx_oracle_v2", "ownership": "per_contract_projection",
                "launcher": {"schema": "pmm.risk_oracle_launcher.v1", "build_dir": "build", "cmake_target": "pmm_risk_oracle"},
                "risk_contract": {"schema": "pmm.research_risk_contract.v1", "quantity_unit": "whole_contract", "price_unit": "cent", "post_only": True},
                "limits_by_contract": [
                    {"contract_id": ordinal, "limits": {"maximum_order_quantity_contracts": "2", "maximum_absolute_position_contracts": "10", "maximum_buy_exposure_contracts": "10", "maximum_sell_exposure_contracts": "10", "maximum_pending_exposure_contracts": "10", "maximum_active_orders": 4}}
                    for ordinal in (1, 2)
                ],
            },
            "completeness": {"required": "complete_observed_interval"},
            "limitations": ["Independent per-contract risk; no portfolio aggregation."],
        }
        path = self.generated_root / "config.json"
        phase7.write_json(path, config)
        return path, config

    def test_two_products_are_isolated_and_repeated_runs_are_byte_identical(self) -> None:
        config_path, _ = self.make_config()
        first = self.generated_root / "run-one"
        second = self.generated_root / "run-two"
        first_manifest = multimarket.run_backtest_v4(config_path, first)
        second_manifest = multimarket.run_backtest_v4(config_path, second)
        self.assertEqual(first_manifest, second_manifest)
        self.assertEqual(first_manifest["schema"], multimarket.RESULT_SCHEMA)
        self.assertEqual([item["contract_identity"]["contract_id"] for item in first_manifest["products"]], [1, 2])
        for path in first.iterdir():
            self.assertEqual(path.read_bytes(), (second / path.name).read_bytes())
        orders = list(phase7.iter_jsonl(first / "submitted-orders.jsonl"))
        self.assertEqual({row["product_identity"]["ticker"] for row in orders}, {"KX-A", "KX-B"})
        self.assertTrue(all(row["segment_identity"]["book_segment_id"].startswith(row["product_identity"]["ticker"]) for row in orders))
        verified = multimarket.verify_backtest_v4(config_path, first)
        self.assertTrue(verified["verified"])
        all_rows = [row for name in multimarket.ARTIFACT_SCHEMAS for row in phase7.iter_jsonl(first / f"{name}.jsonl")]
        ordinals = [row["artifact_ordinal"] for row in all_rows]
        self.assertEqual(len(ordinals), len(set(ordinals)))

    def test_one_defect_input_hash_and_completeness_refuse_without_output(self) -> None:
        for name, mutate, code in (
            ("hash", lambda config: config["inputs"]["features"].__setitem__("rows_sha256", "0" * 64), "BacktestInputHashMismatch"),
            ("completeness", lambda config: config["completeness"].__setitem__("required", "incomplete"), "BacktestConfigSchemaMismatch"),
            ("binding", lambda config: config["products"][1]["risk_binding"].__setitem__("contract_id", 1), "BacktestRiskBindingMismatch"),
        ):
            with self.subTest(name=name):
                config_path, config = self.make_config()
                mutate(config)
                phase7.write_json(config_path, config)
                output = self.generated_root / f"refused-{name}"
                with self.assertRaisesRegex(ValueError, code):
                    multimarket.run_backtest_v4(config_path, output)
                self.assertFalse(output.exists())
                self.assertFalse(output.with_name(f"{output.name}.partial").exists())
                shutil.rmtree(self.generated_root)
                self.generated_root.mkdir()

    def test_schema_runtime_parity_and_cli_cleanup_contract(self) -> None:
        config_path, config = self.make_config()
        validator = Draft202012Validator(json.loads((phase7.HISTORICAL_SCHEMA_ROOT / "backtest-v4.schema.json").read_text()))
        self.assertTrue(validator.is_valid(config), list(validator.iter_errors(config)))
        wrong = json.loads(json.dumps(config))
        wrong["schema"] = "wrong"
        self.assertFalse(validator.is_valid(wrong))
        output = self.generated_root / "cli-run"
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = phase7.main(["backtest-v4", "--config", str(config_path), "--output", str(output)])
        self.assertEqual(status, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(json.loads(stdout.getvalue())["schema"], multimarket.RESULT_SCHEMA)
        before = {path.name: path.read_bytes() for path in output.iterdir()}
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = phase7.main(["backtest-v4", "--config", str(config_path), "--output", str(output)])
        self.assertEqual(status, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("output already exists", stderr.getvalue())
        self.assertEqual(before, {path.name: path.read_bytes() for path in output.iterdir()})

    def test_programming_failure_and_interruption_remove_owned_partial(self) -> None:
        for exception, expected_status in ((RuntimeError("boom"), 1), (KeyboardInterrupt(), 130)):
            with self.subTest(status=expected_status):
                config_path, _ = self.make_config()
                output = self.generated_root / f"failure-{expected_status}"
                stdout, stderr = io.StringIO(), io.StringIO()
                with mock.patch.object(phase7, "CxxRiskOracle", side_effect=exception), redirect_stdout(stdout), redirect_stderr(stderr):
                    status = phase7.main(["backtest-v4", "--config", str(config_path), "--output", str(output)])
                self.assertEqual(status, expected_status)
                self.assertEqual(stdout.getvalue(), "")
                self.assertFalse(output.exists())
                self.assertFalse(output.with_name(f"{output.name}.partial").exists())
                shutil.rmtree(self.generated_root)
                self.generated_root.mkdir()

    def test_trade_touch_fills_only_the_named_product_and_segment(self) -> None:
        config_path, config = self.make_config()
        config["execution"]["model"] = "trade_touch_v1"
        phase7.write_json(config_path, config)
        output = self.generated_root / "trade-touch"
        multimarket.run_backtest_v4(config_path, output)
        fills = list(phase7.iter_jsonl(output / "fills.jsonl"))
        self.assertEqual({row["product_identity"]["ticker"] for row in fills}, {"KX-B"})
        self.assertTrue(all(row["contract_identity"]["contract_id"] == 2 for row in fills))
        self.assertTrue(all(row["segment_identity"]["book_segment_id"].startswith("KX-B") for row in fills))

    def test_latency_and_interleaved_tie_order_are_explicit(self) -> None:
        config_path, config = self.make_config()
        for product in config["products"]:
            product["latency"].update({"market_data_ns": 2, "decision_ns": 3, "order_ns": 5, "acknowledgement_ns": 7})
        phase7.write_json(config_path, config)
        output = self.generated_root / "latency"
        multimarket.run_backtest_v4(config_path, output)
        submissions = {row["client_intent_id"]: row for row in phase7.iter_jsonl(output / "submitted-orders.jsonl")}
        acknowledgements = list(phase7.iter_jsonl(output / "acknowledgements.jsonl"))
        self.assertGreater(len(acknowledgements), 0)
        for acknowledgement in acknowledgements:
            submitted = submissions[acknowledgement["order_id"]]
            self.assertEqual(acknowledgement["effective_time_utc_ns"], submitted["effective_time_utc_ns"] + 7)
            self.assertEqual(acknowledgement["product_identity"], submitted["product_identity"])
            self.assertEqual(acknowledgement["causal_watermark"], submitted["causal_watermark"])
        decisions = list(phase7.iter_jsonl(output / "decisions.jsonl"))
        causal_ordinals = [row["causal_watermark"]["normalization_watermark"] for row in decisions]
        self.assertEqual(causal_ordinals, sorted(causal_ordinals))

    def test_each_declared_input_and_lineage_hash_fails_closed(self) -> None:
        mutations = (
            ("normalization_manifest", lambda value: value["inputs"]["normalization"].__setitem__("manifest_sha256", "0" * 64)),
            ("records", lambda value: value["inputs"]["normalization"].__setitem__("records_sha256", "0" * 64)),
            ("scopes", lambda value: value["inputs"]["normalization"].__setitem__("source_scopes_sha256", "0" * 64)),
            ("product_map", lambda value: value["inputs"]["normalization"].__setitem__("product_map_sha256", "0" * 64)),
            ("feature_manifest", lambda value: value["inputs"]["features"].__setitem__("manifest_sha256", "0" * 64)),
            ("feature_rows", lambda value: value["inputs"]["features"].__setitem__("rows_sha256", "0" * 64)),
            ("feature_definition", lambda value: value["inputs"]["features"].__setitem__("feature_definition_sha256", "0" * 64)),
            ("product_entry", lambda value: value["products"][0]["product_identity"].__setitem__("input_product_entry_sha256", "0" * 64)),
            ("terms", lambda value: value["products"][0]["reviewed_lineage"].__setitem__("product_terms_sha256", "0" * 64)),
            ("source", lambda value: value["products"][0]["reviewed_lineage"].__setitem__("source_manifest_sha256", "0" * 64)),
            ("review", lambda value: value["products"][0]["reviewed_lineage"].__setitem__("review_sha256", "0" * 64)),
            ("policy", lambda value: value["products"][0]["reviewed_lineage"].__setitem__("conversion_policy_sha256", "0" * 64)),
        )
        for name, mutation in mutations:
            with self.subTest(defect=name):
                config_path, config = self.make_config()
                mutation(config)
                phase7.write_json(config_path, config)
                output = self.generated_root / f"stale-{name}"
                with self.assertRaises(phase7.HistoricalDataError):
                    multimarket.run_backtest_v4(config_path, output)
                self.assertFalse(output.exists())
                shutil.rmtree(self.generated_root)
                self.generated_root.mkdir()

    def test_result_verifier_refuses_one_tampered_artifact_trace_count_and_identity(self) -> None:
        cases = ("artifact", "trace", "count", "identity")
        for name in cases:
            with self.subTest(defect=name):
                config_path, _ = self.make_config()
                output = self.generated_root / f"result-{name}"
                multimarket.run_backtest_v4(config_path, output)
                manifest_path = output / "manifest.json"
                manifest = json.loads(manifest_path.read_text())
                if name == "artifact":
                    path = output / manifest["artifacts"][0]["path"]
                    path.write_text(path.read_text() + "\n")
                elif name == "trace":
                    path = output / manifest["products"][0]["risk_trace"]["path"]
                    path.write_text(path.read_text() + "\n")
                elif name == "count":
                    manifest["aggregate_counts"]["decisions"] += 1
                    phase7.write_json(manifest_path, manifest)
                else:
                    manifest["products"][0]["product_identity"]["ticker"] = "WRONG"
                    phase7.write_json(manifest_path, manifest)
                with self.assertRaises(phase7.HistoricalDataError):
                    multimarket.verify_backtest_v4(config_path, output)
                shutil.rmtree(self.generated_root)
                self.generated_root.mkdir()

    def test_every_emitted_schema_discriminator_has_runtime_schema_parity(self) -> None:
        config_path, _ = self.make_config()
        output = self.generated_root / "schemas"
        manifest = multimarket.run_backtest_v4(config_path, output)
        result_validator = Draft202012Validator(json.loads((phase7.HISTORICAL_SCHEMA_ROOT / "backtest-result-manifest-v4.schema.json").read_text()))
        artifact_validator = Draft202012Validator(json.loads((phase7.HISTORICAL_SCHEMA_ROOT / "backtest-artifact-v1.schema.json").read_text()))
        self.assertTrue(result_validator.is_valid(manifest))
        wrong_manifest = json.loads(json.dumps(manifest))
        wrong_manifest["schema"] = "wrong"
        self.assertFalse(result_validator.is_valid(wrong_manifest))
        observed = set()
        donor = None
        for name in multimarket.ARTIFACT_SCHEMAS:
            for row in phase7.iter_jsonl(output / f"{name}.jsonl"):
                donor = donor or row
                observed.add(row["schema"])
                self.assertTrue(artifact_validator.is_valid(row), list(artifact_validator.iter_errors(row)))
                wrong = json.loads(json.dumps(row))
                wrong["schema"] = "wrong"
                self.assertFalse(artifact_validator.is_valid(wrong))
        assert donor is not None
        required_by_name = {
            "decisions": {"decision_id": 1},
            "submitted-orders": {"client_intent_id": 1, "side": "buy", "price_dollars": "0.50", "quantity_contracts": "1", "planned_expires_at_utc_ns": 1},
            "cancellations": {"order_id": 1, "reason": "fixture"},
            "acknowledgements": {"order_id": 1, "expires_at_utc_ns": 1},
            "rejections": {"stage": "fixture", "reason": "fixture"},
            "fills": {"order_id": 1, "side": "buy", "price_dollars": "0.50", "quantity_contracts": "1", "public_trade_event_id": "trade", "fill_model": "trade_touch_v1"},
            "exposure": {"risk_view": {}},
            "risk-events": {"operation": "admit", "order_id": 1, "result": "approved"},
            "summary": {"scope": "product", "counts": {}},
        }
        common_names = set(artifact_validator.schema["required"])
        for name, schema in multimarket.ARTIFACT_SCHEMAS.items():
            positive = {key: value for key, value in donor.items() if key in common_names}
            positive["schema"] = schema
            positive.update(required_by_name[name])
            self.assertTrue(artifact_validator.is_valid(positive), list(artifact_validator.iter_errors(positive)))


if __name__ == "__main__":
    unittest.main()
