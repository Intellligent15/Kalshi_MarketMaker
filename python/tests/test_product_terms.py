from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

from jsonschema import Draft202012Validator, FormatChecker

from python import pmm_phase7 as phase7
from python import pmm_product_terms as terms


CATALOG_ROOT = phase7.REPOSITORY_ROOT / "configs" / "product_catalog"
POLICY_PATH = CATALOG_ROOT / "conversion_policies" / "integer_cents_whole_contracts_v1.json"
PACKAGE_RELATIVE = Path(
    "kalshi/production/markets/KXWNBASPREAD-26JUL14WSHTOR-WSH2/"
    "2026-07-16-reviewed-retrospective"
)
TICKER = "KXWNBASPREAD-26JUL14WSHTOR-WSH2"


class FakeResponse:
    def __init__(
        self,
        *,
        url: str,
        status: int = 200,
        body: bytes = b'{"market":{}}',
        headers: dict[str, str] | None = None,
        interruption: BaseException | None = None,
    ) -> None:
        self.url = url
        self.status_code = status
        self.body = body
        self.headers = headers or {
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
        }
        self.interruption = interruption
        self.closed = False

    def iter_content(self, chunk_size: int) -> object:
        del chunk_size
        if self.interruption is not None:
            raise self.interruption
        yield self.body

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, responses: list[FakeResponse | BaseException]) -> None:
        self.responses = responses
        self.requests: list[dict[str, object]] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.requests.append({"url": url, **kwargs})
        if not self.responses:
            raise AssertionError("fake session exhausted")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


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

    @staticmethod
    def write_envelope(path: Path, document: dict[str, object]) -> None:
        document["payload_sha256"] = terms.sha256_bytes(
            terms.canonical_json_bytes(document["payload"])
        )
        path.write_bytes(terms.canonical_json_bytes(document))

    def acquisition_spec(self, *, url: str = "https://api.elections.kalshi.com/market") -> Path:
        path = self.generated_root / f"acquisition-{uuid.uuid4()}.json"
        path.write_text(json.dumps({
            "schema": terms.ACQUISITION_SPEC_SCHEMA,
            "venue": "kalshi",
            "environment": "production",
            "sources": [{
                "id": "market_record",
                "role": "market_record",
                "url": url,
                "path": "sources/market.response.json",
            }],
        }), encoding="utf-8")
        return path

    @staticmethod
    def fixed_clock() -> datetime:
        return datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    @staticmethod
    def schema_validator(name: str) -> Draft202012Validator:
        schema = json.loads(
            (phase7.REPOSITORY_ROOT / "schemas" / "product_terms" / name).read_text()
        )
        return Draft202012Validator(schema, format_checker=FormatChecker())

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

    def test_terms_review_and_catalog_require_exact_interval_equality(self) -> None:
        for target in ("review", "catalog"):
            with self.subTest(target=target):
                copied_catalog = self.generated_root / f"interval-{target}"
                shutil.copytree(CATALOG_ROOT, copied_catalog)
                if target == "review":
                    path = copied_catalog / PACKAGE_RELATIVE / "review.json"
                    document = json.loads(path.read_text())
                    document["payload"]["effective_from_utc"] = "2026-07-12T23:31:00Z"
                else:
                    path = copied_catalog / "manifest.json"
                    document = json.loads(path.read_text())
                    document["payload"]["entries"][0]["effective_from_utc"] = (
                        "2026-07-12T23:31:00Z"
                    )
                self.write_envelope(path, document)
                with self.assertRaisesRegex(terms.ProductTermsError, "EffectiveWindowMismatch"):
                    terms.ProductCatalog.load(copied_catalog)

    def test_catalog_allows_adjacency_and_refuses_gap_or_overlap(self) -> None:
        copied_catalog = self.generated_root / "two-revisions"
        shutil.copytree(CATALOG_ROOT, copied_catalog)
        first_package = copied_catalog / PACKAGE_RELATIVE
        second_relative = PACKAGE_RELATIVE.with_name("2026-07-17-reviewed-retrospective")
        second_package = copied_catalog / second_relative
        shutil.copytree(first_package, second_package)
        boundary = "2026-07-15T01:32:55Z"
        second_end = "2026-07-16T01:32:55Z"

        terms_path = second_package / "product_terms.json"
        terms_document = json.loads(terms_path.read_text())
        terms_document["payload"]["revision_label"] = "second synthetic revision"
        terms_document["payload"]["effective"]["from_utc"] = boundary
        terms_document["payload"]["effective"]["until_utc"] = second_end
        self.write_envelope(terms_path, terms_document)
        review_path = second_package / "review.json"
        review_document = json.loads(review_path.read_text())
        review_document["payload"]["product_terms_sha256"] = terms_document["payload_sha256"]
        review_document["payload"]["effective_from_utc"] = boundary
        review_document["payload"]["effective_until_utc"] = second_end
        self.write_envelope(review_path, review_document)

        manifest_path = copied_catalog / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        second_entry = dict(manifest["payload"]["entries"][0])
        second_entry.update({
            "effective_from_utc": boundary,
            "effective_until_utc": second_end,
            "package": second_relative.as_posix(),
            "product_terms_sha256": terms_document["payload_sha256"],
            "review_sha256": review_document["payload_sha256"],
        })
        manifest["payload"]["entries"].append(second_entry)
        self.write_envelope(manifest_path, manifest)
        catalog = terms.ProductCatalog.load(copied_catalog)
        second_metadata = self.metadata()
        second_metadata["capture_started_at_utc_ns"] = 1_784_100_000_000_000_000
        second_metadata["capture_ended_at_utc_ns"] = 1_784_100_001_000_000_000
        self.assertEqual(catalog.resolve(second_metadata).terms.payload["revision_label"],
                         "second synthetic revision")

        for label, changed_start, expected in (
            ("gap", "2026-07-15T02:32:55Z", "EffectiveWindowGap"),
            ("overlap", "2026-07-15T00:32:55Z", "EffectiveWindowOverlap"),
        ):
            with self.subTest(label=label):
                changed = self.generated_root / f"two-revisions-{label}"
                shutil.copytree(copied_catalog, changed)
                changed_terms_path = changed / second_relative / "product_terms.json"
                changed_terms = json.loads(changed_terms_path.read_text())
                changed_terms["payload"]["effective"]["from_utc"] = changed_start
                self.write_envelope(changed_terms_path, changed_terms)
                changed_review_path = changed / second_relative / "review.json"
                changed_review = json.loads(changed_review_path.read_text())
                changed_review["payload"]["product_terms_sha256"] = changed_terms["payload_sha256"]
                changed_review["payload"]["effective_from_utc"] = changed_start
                self.write_envelope(changed_review_path, changed_review)
                changed_manifest_path = changed / "manifest.json"
                changed_manifest = json.loads(changed_manifest_path.read_text())
                changed_manifest["payload"]["entries"][1]["effective_from_utc"] = changed_start
                changed_manifest["payload"]["entries"][1]["product_terms_sha256"] = changed_terms["payload_sha256"]
                changed_manifest["payload"]["entries"][1]["review_sha256"] = changed_review["payload_sha256"]
                self.write_envelope(changed_manifest_path, changed_manifest)
                if label == "overlap":
                    with self.assertRaisesRegex(terms.ProductTermsError, expected):
                        terms.ProductCatalog.load(changed)
                else:
                    gap_catalog = terms.ProductCatalog.load(changed)
                    gap_metadata = self.metadata()
                    gap_start = datetime(2026, 7, 15, 2, 0, tzinfo=timezone.utc)
                    gap_metadata["capture_started_at_utc_ns"] = int(gap_start.timestamp() * 1_000_000_000)
                    gap_metadata["capture_ended_at_utc_ns"] = (
                        gap_metadata["capture_started_at_utc_ns"] + 1_000_000_000
                    )
                    with self.assertRaisesRegex(terms.ProductTermsError, expected):
                        gap_catalog.resolve(gap_metadata)

    def test_acquisition_streams_observed_v2_metadata_through_allowed_redirect(self) -> None:
        requested = "https://api.elections.kalshi.com/market"
        final = "https://external-api.kalshi.com/market"
        session = FakeSession([
            FakeResponse(url=requested, status=302, headers={"Location": final}),
            FakeResponse(url=final),
        ])
        output = self.generated_root / "fetched"
        spec_path = self.acquisition_spec(url=requested)
        self.schema_validator("acquisition-spec-v1.schema.json").validate(
            json.loads(spec_path.read_text())
        )
        terms.fetch_sources(
            spec_path, output, session=session,
            now=self.fixed_clock, monotonic=lambda: 0.0,
        )
        evidence = terms.SourceEvidence.load(output)
        self.schema_validator("source-manifest-v2.schema.json").validate(
            json.loads((output / "source_manifest.json").read_text())
        )
        self.assertEqual(evidence.schema, terms.SOURCE_MANIFEST_V2_SCHEMA)
        source = evidence.payload["sources"][0]
        self.assertEqual(source["requested_url"], requested)
        self.assertEqual(source["final_url"], final)
        self.assertEqual(source["redirect_history"][0]["resolved_url"], final)
        self.assertEqual(source["byte_length"], len(b'{"market":{}}'))
        self.assertEqual(len(session.requests), 2)
        self.assertTrue(all(request["allow_redirects"] is False for request in session.requests))

    def test_acquisition_refuses_redirect_size_media_and_interruption_without_partial_output(self) -> None:
        cases = (
            (
                "redirect",
                FakeSession([FakeResponse(
                    url="https://api.elections.kalshi.com/market", status=302,
                    headers={"Location": "https://example.com/not-first-party"},
                )]),
                {},
                terms.ProductTermsError,
                "AcquisitionRedirectRejected",
            ),
            (
                "oversized",
                FakeSession([FakeResponse(
                    url="https://api.elections.kalshi.com/market",
                    headers={"Content-Type": "application/json", "Content-Length": "10"},
                )]),
                {"maximum_bytes": 4},
                terms.ProductTermsError,
                "AcquisitionSourceTooLarge",
            ),
            (
                "wrong-media",
                FakeSession([FakeResponse(
                    url="https://api.elections.kalshi.com/market",
                    headers={"Content-Type": "text/html", "Content-Length": "5"},
                )]),
                {},
                terms.ProductTermsError,
                "AcquisitionMediaTypeMismatch",
            ),
            (
                "timeout",
                FakeSession([terms.requests.Timeout("offline timeout")]),
                {},
                terms.ProductTermsError,
                "AcquisitionTimeout",
            ),
            (
                "invalid-json",
                FakeSession([FakeResponse(
                    url="https://api.elections.kalshi.com/market", body=b"not-json",
                )]),
                {},
                terms.ProductTermsError,
                "AcquisitionContentInvalid",
            ),
            (
                "interrupted",
                FakeSession([FakeResponse(
                    url="https://api.elections.kalshi.com/market",
                    interruption=KeyboardInterrupt(),
                )]),
                {},
                KeyboardInterrupt,
                "",
            ),
        )
        for label, session, overrides, error_type, pattern in cases:
            with self.subTest(label=label):
                spec_path = self.acquisition_spec()
                spec = json.loads(spec_path.read_text())
                spec["sources"][0].update(overrides)
                spec_path.write_text(json.dumps(spec), encoding="utf-8")
                output = self.generated_root / f"fetch-{label}"
                with self.assertRaisesRegex(error_type, pattern):
                    terms.fetch_sources(
                        spec_path, output, session=session,
                        now=self.fixed_clock, monotonic=lambda: 0.0,
                    )
                self.assertFalse(output.exists())
                self.assertEqual(list(self.generated_root.glob(f".{output.name}.*.partial")), [])

    def test_acquisition_enforces_total_package_limit(self) -> None:
        spec_path = self.acquisition_spec()
        output = self.generated_root / "package-too-large"
        original = terms.MAX_PACKAGE_BYTES
        terms.MAX_PACKAGE_BYTES = 4
        try:
            with self.assertRaisesRegex(terms.ProductTermsError, "AcquisitionPackageTooLarge"):
                terms.fetch_sources(
                    spec_path,
                    output,
                    session=FakeSession([FakeResponse(
                        url="https://api.elections.kalshi.com/market",
                    )]),
                    now=self.fixed_clock,
                    monotonic=lambda: 0.0,
                )
        finally:
            terms.MAX_PACKAGE_BYTES = original
        self.assertFalse(output.exists())
        self.assertEqual(list(self.generated_root.glob(f".{output.name}.*.partial")), [])

    def test_semantic_source_mutation_with_recomputed_hash_still_refuses(self) -> None:
        _, _, package = self.load()
        copied = self.generated_root / "semantic-source-mutation"
        shutil.copytree(package.path, copied)
        market_path = copied / "sources" / "market.response.json"
        market = json.loads(market_path.read_text())
        market["market"]["title"] = "mutated official title"
        market_path.write_bytes(terms.canonical_json_bytes(market))
        manifest_path = copied / "source_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        source = next(item for item in manifest["payload"]["sources"]
                      if item["id"] == "market_record")
        source["byte_length"] = len(market_path.read_bytes())
        source["sha256"] = terms.sha256_file(market_path)
        self.write_envelope(manifest_path, manifest)
        review_path = copied / "review.json"
        review = json.loads(review_path.read_text())
        review["payload"]["source_manifest_sha256"] = manifest["payload_sha256"]
        self.write_envelope(review_path, review)
        with self.assertRaisesRegex(terms.ProductTermsError, "SourceTermsMismatch"):
            terms.ProductPackage.load(copied)

    def test_public_cli_has_stable_status_and_stream_contract(self) -> None:
        command = [sys.executable, str(phase7.REPOSITORY_ROOT / "python" / "pmm_product_terms.py")]
        success = subprocess.run(
            command + ["verify-catalog", "--catalog", str(CATALOG_ROOT)],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(success.returncode, 0)
        self.assertEqual(success.stderr, "")
        self.assertEqual(json.loads(success.stdout)["status"], "valid")
        refused = subprocess.run(
            command + ["fetch", "--spec", str(self.acquisition_spec(url="https://example.com/bad")),
                       "--output", str(self.generated_root / "cli-refused")],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(refused.returncode, 2)
        self.assertEqual(refused.stdout, "")
        self.assertIn("error: AcquisitionUrlRejected:", refused.stderr)

    def test_reviewed_schema_runtime_parity_matrix(self) -> None:
        _, policy, package = self.load()
        positive_documents = {
            "acquisition-spec-v1.schema.json": CATALOG_ROOT / "acquisition_spec.example.json",
            "source-manifest-v1.schema.json": package.path / "source_manifest.json",
            "product-terms-v1.schema.json": package.path / "product_terms.json",
            "review-v1.schema.json": package.path / "review.json",
            "catalog-v1.schema.json": CATALOG_ROOT / "manifest.json",
            "conversion-policy-v1.schema.json": policy.path,
        }
        for schema_name, document_path in positive_documents.items():
            with self.subTest(kind="positive", schema=schema_name):
                self.schema_validator(schema_name).validate(json.loads(document_path.read_text()))

        cases = (
            ("source-manifest-v1.schema.json", "source_manifest.json", "SourceMissing"),
            ("product-terms-v1.schema.json", "product_terms.json", "TermsNoncanonical"),
            ("review-v1.schema.json", "review.json", "ReviewNotApproved"),
            ("catalog-v1.schema.json", "manifest.json", "TermsNoncanonical"),
            ("conversion-policy-v1.schema.json", "conversion_policy.json", "ConversionPolicyMismatch"),
        )
        for schema_name, filename, expected_code in cases:
            with self.subTest(kind="negative", schema=schema_name):
                root = self.generated_root / f"parity-{schema_name}"
                if filename == "manifest.json":
                    shutil.copytree(CATALOG_ROOT, root)
                    path = root / filename
                elif filename == "conversion_policy.json":
                    root.mkdir()
                    path = root / filename
                    shutil.copy2(policy.path, path)
                else:
                    shutil.copytree(package.path, root)
                    path = root / filename
                document = json.loads(path.read_text())
                if filename == "source_manifest.json":
                    document["payload"]["sources"][0]["url"] = "https://example.com/source"
                elif filename == "product_terms.json":
                    document["payload"]["identity"]["contracts"].reverse()
                elif filename == "review.json":
                    document["payload"]["status"] = "revoked"
                elif filename == "manifest.json":
                    document["payload"]["entries"] = []
                else:
                    document["payload"]["fee_application"] = "applied"
                self.write_envelope(path, document)
                self.assertFalse(self.schema_validator(schema_name).is_valid(document))
                with self.assertRaisesRegex(terms.ProductTermsError, expected_code):
                    if filename == "manifest.json":
                        terms.ProductCatalog.load(root)
                    elif filename == "conversion_policy.json":
                        terms.ConversionPolicy.load(path)
                    else:
                        terms.ProductPackage.load(root)

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
        phase7.verify_lineage(config_path, self.generated_root / "run-one")
        lineage_command = [
            sys.executable,
            str(phase7.REPOSITORY_ROOT / "python" / "pmm_phase7.py"),
            "verify-lineage",
            "--config", str(config_path),
            "--result", str(self.generated_root / "run-one"),
        ]
        lineage_success = subprocess.run(
            lineage_command, text=True, capture_output=True, check=False
        )
        self.assertEqual(lineage_success.returncode, 0)
        self.assertEqual(lineage_success.stderr, "")
        self.assertEqual(json.loads(lineage_success.stdout)["status"], "valid")

        for filename in ("orders.jsonl", "fills.jsonl", "ledger.jsonl", "risk-trace.jsonl"):
            with self.subTest(tamper=filename):
                copied_result = self.generated_root / f"tampered-{filename}"
                shutil.copytree(self.generated_root / "run-one", copied_result)
                artifact = copied_result / filename
                artifact.write_bytes(artifact.read_bytes() + b" ")
                with self.assertRaisesRegex(terms.ProductTermsError, "UpstreamManifestMismatch"):
                    phase7.verify_lineage(config_path, copied_result)
                if filename == "orders.jsonl":
                    refused_command = lineage_command[:-1] + [str(copied_result)]
                    lineage_refused = subprocess.run(
                        refused_command, text=True, capture_output=True, check=False
                    )
                    self.assertEqual(lineage_refused.returncode, 2)
                    self.assertEqual(lineage_refused.stdout, "")
                    self.assertIn("error: UpstreamManifestMismatch:", lineage_refused.stderr)

        tampered_result = self.generated_root / "tampered-manifest"
        shutil.copytree(self.generated_root / "run-one", tampered_result)
        result_manifest_path = tampered_result / "manifest.json"
        result_manifest = json.loads(result_manifest_path.read_text())
        result_manifest["orders_sha256"] = "0" * 64
        result_manifest_path.write_text(json.dumps(result_manifest), encoding="utf-8")
        with self.assertRaisesRegex(terms.ProductTermsError, "UpstreamManifestMismatch"):
            phase7.verify_lineage(config_path, tampered_result)

        changed_config = dict(config)
        changed_config["seed"] = 8
        changed_config_path = self.generated_root / "changed-config.json"
        changed_config_path.write_text(json.dumps(changed_config, sort_keys=True) + "\n")
        with self.assertRaisesRegex(terms.ProductTermsError, "UpstreamManifestMismatch"):
            phase7.verify_lineage(changed_config_path, self.generated_root / "run-one")

        for manifest_path, field in (
            (normalized / "manifest.json", "product_terms_sha256"),
            (features / "manifest.json", "product_terms_sha256"),
        ):
            with self.subTest(tamper=manifest_path.parent.name):
                original = manifest_path.read_bytes()
                document = json.loads(original)
                document[field] = "0" * 64
                manifest_path.write_text(json.dumps(document), encoding="utf-8")
                try:
                    with self.assertRaisesRegex(
                        terms.ProductTermsError,
                        "TermsHashMismatch|UpstreamManifestMismatch",
                    ):
                        phase7.verify_lineage(config_path)
                finally:
                    manifest_path.write_bytes(original)

        for artifact_path in (normalized / "events.jsonl", normalized / "product.json",
                              features / "features.jsonl"):
            with self.subTest(tamper=artifact_path.name):
                original = artifact_path.read_bytes()
                artifact_path.write_bytes(original + b" ")
                try:
                    with self.assertRaisesRegex(terms.ProductTermsError, "UpstreamManifestMismatch"):
                        phase7.verify_lineage(config_path)
                finally:
                    artifact_path.write_bytes(original)

        for label, strategy_field, value, expected in (
            ("fractional-quantity", "quote_quantity_contracts", "0.25", "CoreQuantityNotRepresentable"),
            ("subcent-spread", "minimum_spread_dollars", "0.005", "CorePriceNotRepresentable"),
        ):
            with self.subTest(nonrepresentable=label):
                changed = json.loads(json.dumps(config))
                changed["strategy"][strategy_field] = value
                changed_path = self.generated_root / f"{label}.json"
                changed_path.write_text(json.dumps(changed, sort_keys=True) + "\n")
                output = self.generated_root / f"run-{label}"
                with self.assertRaisesRegex(terms.ProductTermsError, expected):
                    phase7.run_backtest(changed_path, output)
                self.assertFalse(output.exists())
                self.assertFalse(output.with_name(output.name + ".partial").exists())


if __name__ == "__main__":
    unittest.main()
