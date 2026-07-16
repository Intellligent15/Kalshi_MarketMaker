from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest
import uuid

from python import pmm_phase7 as phase7
from python import pmm_product_terms as terms


CATALOG_ROOT = phase7.REPOSITORY_ROOT / "configs" / "product_catalog"
POLICY_PATH = CATALOG_ROOT / "conversion_policies" / "integer_cents_whole_contracts_v1.json"
PACKAGE_RELATIVE = Path(
    "kalshi/production/markets/KXWNBASPREAD-26JUL14WSHTOR-WSH2/"
    "2026-07-16-reviewed-retrospective"
)
TICKER = "KXWNBASPREAD-26JUL14WSHTOR-WSH2"


class ProductTermsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.generated_root = (
            phase7.REPOSITORY_ROOT / "data" / "processed" / f"product-terms-test-{uuid.uuid4()}"
        )
        self.generated_root.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.generated_root, ignore_errors=True)

    @staticmethod
    def metadata(ticker: str = TICKER) -> dict[str, object]:
        return {
            "schema": "pmm.kalshi.raw_capture.v1",
            "ticker": ticker,
            "capture_started_at_utc_ns": 1_784_047_974_008_456_000,
            "capture_ended_at_utc_ns": 1_784_058_774_095_115_000,
        }

    @staticmethod
    def message(message_type: str, sequence: int) -> dict[str, object]:
        if message_type == "orderbook_snapshot":
            payload: dict[str, object] = {
                "market_ticker": TICKER,
                "market_id": "d94606bd-2027-4ab9-bee7-05cfe97c9fb2",
                "yes_dollars_fp": [["0.5000", "3.25"]],
                "no_dollars_fp": [["0.5100", "4.00"]],
            }
        else:
            payload = {
                "market_ticker": TICKER,
                "market_id": "d94606bd-2027-4ab9-bee7-05cfe97c9fb2",
                "trade_id": "trade-1",
                "yes_price_dollars": "0.5000",
                "no_price_dollars": "0.5000",
                "count_fp": "1.00",
                "ts_ms": 1_784_047_975_000,
            }
        return {"type": message_type, "sid": 1 if message_type == "orderbook_snapshot" else 2,
                "seq": sequence, "msg": payload}

    def make_capture(self, *, ticker: str = TICKER, off_grid: bool = False) -> Path:
        capture = self.generated_root / f"capture-{uuid.uuid4()}"
        capture.mkdir()
        (capture / "metadata.json").write_text(
            json.dumps(self.metadata(ticker), sort_keys=True) + "\n", encoding="utf-8"
        )
        messages = [self.message("orderbook_snapshot", 1), self.message("trade", 1)]
        if off_grid:
            messages[0]["msg"]["yes_dollars_fp"][0][0] = "0.5050"  # type: ignore[index]
        with (capture / "frames.jsonl").open("w", encoding="utf-8") as destination:
            for line_number, message in enumerate(messages, start=1):
                destination.write(json.dumps({
                    "kind": "inbound_frame",
                    "received_at_utc_ns": 1_784_047_974_100_000_000 + line_number,
                    "connection_id": 1,
                    "message_type": message["type"],
                    "subscription_id": message["sid"],
                    "source_sequence": message["seq"],
                    "raw_frame_utf8": json.dumps(message, separators=(",", ":")),
                }, separators=(",", ":")) + "\n")
        return capture

    def load(self) -> tuple[terms.ProductCatalog, terms.ConversionPolicy, terms.ProductPackage]:
        catalog = terms.ProductCatalog.load(CATALOG_ROOT)
        policy = terms.ConversionPolicy.load(POLICY_PATH)
        package = catalog.resolve(self.metadata())
        return catalog, policy, package

    def test_reviewed_catalog_and_conversion_policy_are_canonical(self) -> None:
        catalog, policy, package = self.load()
        self.assertEqual(len(catalog.payload["entries"]), 1)
        self.assertEqual(package.terms.market_ticker, TICKER)
        self.assertEqual(package.review.payload["effective_time_basis"], "reviewed_retrospective")
        self.assertEqual(policy.convert_price_to_cents(package.terms.validate_price("0.5000", "price"), "price"), 50)
        self.assertEqual(policy.convert_quantity_to_contracts(terms.Decimal("2.00"), "quantity"), 2)
        with self.assertRaisesRegex(terms.ProductTermsError, "CoreQuantityNotRepresentable"):
            policy.convert_quantity_to_contracts(terms.Decimal("0.25"), "quantity")

    def test_source_mutation_is_specific_and_verification_is_read_only(self) -> None:
        copied_catalog = self.generated_root / "catalog"
        shutil.copytree(CATALOG_ROOT, copied_catalog)
        market = copied_catalog / PACKAGE_RELATIVE / "sources" / "market.response.json"
        market.write_bytes(market.read_bytes() + b" ")
        snapshot = {path.relative_to(copied_catalog): path.read_bytes()
                    for path in copied_catalog.rglob("*") if path.is_file()}
        with self.assertRaisesRegex(terms.ProductTermsError, "SourceHashMismatch"):
            terms.ProductCatalog.load(copied_catalog)
        self.assertEqual(snapshot, {path.relative_to(copied_catalog): path.read_bytes()
                                    for path in copied_catalog.rglob("*") if path.is_file()})

    def test_catalog_refuses_wrong_identity_and_uncovered_time(self) -> None:
        catalog = terms.ProductCatalog.load(CATALOG_ROOT)
        with self.assertRaisesRegex(terms.ProductTermsError, "EffectiveWindowGap"):
            catalog.resolve(self.metadata("WRONG"))
        after_close = self.metadata()
        after_close["capture_started_at_utc_ns"] = 1_784_100_000_000_000_000
        after_close["capture_ended_at_utc_ns"] = 1_784_100_001_000_000_000
        with self.assertRaisesRegex(terms.ProductTermsError, "EffectiveWindowGap"):
            catalog.resolve(after_close)

    def test_terms_cannot_diverge_from_sources_and_subcent_core_refuses(self) -> None:
        _, policy, package = self.load()
        copied = self.generated_root / "subcent"
        shutil.copytree(package.path, copied)
        document = json.loads((copied / "product_terms.json").read_text())
        document["payload"]["price"]["level_structure"] = "deci_cent"
        document["payload"]["price"]["ranges"][0]["step_dollars"] = "0.0010"
        document["payload_sha256"] = terms.sha256_bytes(
            terms.canonical_json_bytes(document["payload"])
        )
        (copied / "product_terms.json").write_bytes(terms.canonical_json_bytes(document))
        review = json.loads((copied / "review.json").read_text())
        review["payload"]["product_terms_sha256"] = document["payload_sha256"]
        review["payload_sha256"] = terms.sha256_bytes(terms.canonical_json_bytes(review["payload"]))
        (copied / "review.json").write_bytes(terms.canonical_json_bytes(review))
        with self.assertRaisesRegex(terms.ProductTermsError, "SourceTermsMismatch"):
            terms.ProductPackage.load(copied)
        subcent = terms.ProductTerms(
            document["payload"], document["payload_sha256"], "0" * 64
        )
        self.assertEqual(
            subcent.validate_price("0.5050", "price"), terms.Decimal("0.5050")
        )
        with self.assertRaisesRegex(terms.ProductTermsError, "CorePriceNotRepresentable"):
            policy.require_core_compatible(subcent)

    def test_package_refuses_unreviewed_extra_bytes(self) -> None:
        _, _, package = self.load()
        copied = self.generated_root / "extra-file"
        shutil.copytree(package.path, copied)
        (copied / "unreviewed.txt").write_text("not in manifest\n", encoding="utf-8")
        with self.assertRaisesRegex(terms.ProductTermsError, "PackageMembershipMismatch"):
            terms.ProductPackage.load(copied)

    def test_review_hash_refuses_stale_terms_approval(self) -> None:
        _, _, package = self.load()
        copied = self.generated_root / "stale-review"
        shutil.copytree(package.path, copied)
        review_path = copied / "review.json"
        review = json.loads(review_path.read_text())
        review["payload"]["product_terms_sha256"] = "0" * 64
        review["payload_sha256"] = terms.sha256_bytes(
            terms.canonical_json_bytes(review["payload"])
        )
        review_path.write_bytes(terms.canonical_json_bytes(review))
        with self.assertRaisesRegex(terms.ProductTermsError, "ReviewHashMismatch"):
            terms.ProductPackage.load(copied)

    def test_compatibility_report_names_terms_and_policy_mismatches(self) -> None:
        _, policy, package = self.load()
        report = terms.compatibility_report(package, package, policy, policy)
        self.assertEqual(report, {
            "schema": terms.COMPATIBILITY_REPORT_SCHEMA, "compatible": True, "reasons": []
        })
        changed = terms.ConversionPolicy(policy.path, policy.payload, "a" * 64, policy.file_sha256)
        report = terms.compatibility_report(package, package, policy, changed)
        self.assertFalse(report["compatible"])
        self.assertEqual(report["reasons"][0]["code"], "ConversionPolicyMismatch")

    def test_normalization_v2_binds_and_propagates_reviewed_terms(self) -> None:
        catalog, policy, package = self.load()
        capture = self.make_capture()
        first = self.generated_root / "normalized-one"
        second = self.generated_root / "normalized-two"
        first_manifest = phase7.normalize_capture(
            capture, first, product_catalog=catalog, conversion_policy=policy
        )
        second_manifest = phase7.normalize_capture(
            capture, second, product_catalog=catalog, conversion_policy=policy
        )
        self.assertEqual(first_manifest, second_manifest)
        self.assertEqual(first_manifest["schema"], "pmm.historical.normalization_manifest.v2")
        self.assertEqual(first_manifest["product_terms_sha256"], package.terms.payload_sha256)
        product = json.loads((first / "product.json").read_text())
        self.assertEqual(product["schema"], "pmm.historical.product_map.v2")
        self.assertEqual(
            product["capture_identity"]["venue_market_id_authority"],
            "capture_only_not_in_terms_source",
        )
        self.assertEqual(
            (first / "product_terms" / "product_terms.json").read_bytes(),
            (second / "product_terms" / "product_terms.json").read_bytes(),
        )
        first_features = self.generated_root / "features-one"
        second_features = self.generated_root / "features-two"
        feature_manifest = phase7.materialize_features(first, first_features)
        self.assertEqual(
            feature_manifest, phase7.materialize_features(second, second_features)
        )
        self.assertEqual(feature_manifest["schema"], "pmm.historical.feature_manifest.v2")
        self.assertEqual(feature_manifest["product_terms_sha256"], package.terms.payload_sha256)

    def test_normalization_v2_refuses_off_grid_price_without_output(self) -> None:
        catalog, policy, _ = self.load()
        output = self.generated_root / "normalized"
        with self.assertRaisesRegex(terms.ProductTermsError, "PriceOffVenueGrid"):
            phase7.normalize_capture(
                self.make_capture(off_grid=True), output,
                product_catalog=catalog, conversion_policy=policy,
            )
        self.assertFalse(output.exists())

    def test_backtest_v3_verifies_complete_lineage_and_is_byte_identical(self) -> None:
        if not (phase7.REPOSITORY_ROOT / "build" / "CMakeCache.txt").is_file():
            self.skipTest("CMake build directory has not been configured")
        catalog, policy, package = self.load()
        normalized = self.generated_root / "normalized"
        phase7.normalize_capture(
            self.make_capture(), normalized, product_catalog=catalog, conversion_policy=policy
        )
        features = self.generated_root / "features"
        phase7.materialize_features(normalized, features)
        relative = self.generated_root.relative_to(phase7.REPOSITORY_ROOT)
        config = {
            "schema": phase7.BACKTEST_V3_SCHEMA, "run_id": "terms-v3", "seed": 7,
            "normalized_events": str(relative / "normalized" / "events.jsonl"),
            "normalization_manifest": str(relative / "normalized" / "manifest.json"),
            "features": str(relative / "features" / "features.jsonl"),
            "feature_manifest": str(relative / "features" / "manifest.json"),
            "product_terms": {
                "product_terms_sha256": package.terms.payload_sha256,
                "source_manifest_sha256": package.evidence.payload_sha256,
                "review_sha256": package.review.payload_sha256,
                "conversion_policy_sha256": policy.payload_sha256,
            },
            "latency": {"market_data_ns": 0, "decision_ns": 0, "order_ns": 0},
            "strategy": {"decision_interval_ns": 1_000_000_000,
                         "order_lifetime_ns": 10_000_000_000,
                         "minimum_spread_dollars": "0.01",
                         "quote_quantity_contracts": "1"},
            "risk": {
                "engine": "cxx_oracle_v2",
                "oracle": {"schema": "pmm.risk_oracle_launcher.v1", "build_dir": "build",
                           "cmake_target": "pmm_risk_oracle"},
                "risk_contract": {"schema": "pmm.research_risk_contract.v1",
                                  "quantity_unit": "whole_contract", "price_unit": "cent",
                                  "post_only": True},
                "limits": {"maximum_order_quantity_contracts": "2",
                           "maximum_absolute_position_contracts": "2",
                           "maximum_buy_exposure_contracts": "2",
                           "maximum_sell_exposure_contracts": "2",
                           "maximum_pending_exposure_contracts": "2",
                           "maximum_active_orders": 2},
            },
            "fill_model": "no_fill_v1",
        }
        config_path = self.generated_root / "config.json"
        config_path.write_text(json.dumps(config, sort_keys=True) + "\n", encoding="utf-8")
        first = phase7.run_backtest(config_path, self.generated_root / "run-one")
        second = phase7.run_backtest(config_path, self.generated_root / "run-two")
        self.assertEqual(first["schema"], "pmm.backtest_result_manifest.v3")
        self.assertEqual(first["product_terms_sha256"], package.terms.payload_sha256)
        self.assertEqual(
            (self.generated_root / "run-one" / "manifest.json").read_bytes(),
            (self.generated_root / "run-two" / "manifest.json").read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
