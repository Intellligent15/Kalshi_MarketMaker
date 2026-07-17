from __future__ import annotations

import base64
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid

from jsonschema import Draft202012Validator, FormatChecker, RefResolver, ValidationError

from python import pmm_phase7 as phase7
from python import pmm_product_terms as terms


CATALOG_ROOT = phase7.REPOSITORY_ROOT / "configs" / "product_catalog"
POLICY_PATH = CATALOG_ROOT / "conversion_policies" / "integer_cents_whole_contracts_v1.json"
PACKAGE_RELATIVE = Path(
    "kalshi/production/markets/KXWNBASPREAD-26JUL14WSHTOR-WSH2/"
    "2026-07-16-reviewed-retrospective"
)
TICKER = "KXWNBASPREAD-26JUL14WSHTOR-WSH2"
HMONTH_RELATIVE = Path(
    "kalshi/production/markets/KXHMONTH-26JUL/"
    "2026-07-17T150716Z-150837Z-contemporaneous-bracketed"
)
B1C_FIXTURES = Path(__file__).parent / "fixtures" / "product_terms"


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
    def message(
        message_type: str, sequence: int, ticker: str = TICKER
    ) -> dict[str, object]:
        if message_type == "orderbook_snapshot":
            payload: dict[str, object] = {
                "market_ticker": ticker,
                "market_id": "d94606bd-2027-4ab9-bee7-05cfe97c9fb2",
                "yes_dollars_fp": [["0.5000", "3.25"]],
                "no_dollars_fp": [["0.5100", "4.00"]],
            }
        else:
            payload = {
                "market_ticker": ticker,
                "market_id": "d94606bd-2027-4ab9-bee7-05cfe97c9fb2",
                "trade_id": "trade-1",
                "yes_price_dollars": "0.5000",
                "no_price_dollars": "0.5000",
                "count_fp": "1.00",
                "ts_ms": 1_784_047_975_000,
            }
        return {"type": message_type, "sid": 1 if message_type == "orderbook_snapshot" else 2,
                "seq": sequence, "msg": payload}

    def make_capture(
        self,
        *,
        ticker: str = TICKER,
        off_grid: bool = False,
        capture_started_ns: int | None = None,
    ) -> Path:
        capture = self.generated_root / f"capture-{uuid.uuid4()}"
        capture.mkdir()
        metadata = self.metadata(ticker)
        if capture_started_ns is not None:
            metadata["capture_started_at_utc_ns"] = capture_started_ns
            metadata["capture_ended_at_utc_ns"] = capture_started_ns + 1_000_000_000
        (capture / "metadata.json").write_text(
            json.dumps(metadata, sort_keys=True) + "\n", encoding="utf-8"
        )
        messages = [
            self.message("orderbook_snapshot", 1, ticker),
            self.message("trade", 1, ticker),
        ]
        if off_grid:
            messages[0]["msg"]["yes_dollars_fp"][0][0] = "0.5050"  # type: ignore[index]
        with (capture / "frames.jsonl").open("w", encoding="utf-8") as destination:
            for line_number, message in enumerate(messages, start=1):
                destination.write(json.dumps({
                    "kind": "inbound_frame",
                    "received_at_utc_ns": (
                        capture_started_ns
                        if capture_started_ns is not None
                        else 1_784_047_974_100_000_000
                    ) + line_number,
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

    def acquisition_spec_v2(
        self,
        observation_id: str,
        *,
        source_path: str = "sources/market.response.json",
    ) -> Path:
        policy = CATALOG_ROOT / "acquisition_policies" / "kalshi_first_party_v1.json"
        shutil.copyfile(policy, self.generated_root / "acquisition-policy.json")
        loaded_policy = terms.AcquisitionPolicy.load(policy)
        path = self.generated_root / f"acquisition-{observation_id}.json"
        path.write_text(json.dumps({
            "schema": terms.ACQUISITION_SPEC_V2_SCHEMA,
            "venue": "kalshi",
            "environment": "production",
            "observation_id": observation_id,
            "acquisition_policy": "acquisition-policy.json",
            "acquisition_policy_sha256": loaded_policy.payload_sha256,
            "sources": [{
                "id": "market_record",
                "role": "market_record",
                "url": "https://external-api.kalshi.com/market",
                "path": source_path,
            }],
        }), encoding="utf-8")
        return path

    def acquisition_spec_v3(
        self,
        observation_id: str,
    ) -> tuple[Path, list[FakeResponse]]:
        policy_source = CATALOG_ROOT / "acquisition_policies" / "kalshi_first_party_v1.json"
        policy_path = self.generated_root / f"acquisition-policy-{observation_id}.json"
        shutil.copyfile(policy_source, policy_path)
        loaded_policy = terms.AcquisitionPolicy.load(policy_path)
        profile_path, profile_document = self.write_evidence_profile(
            f"acquisition-{observation_id}"
        )
        pdf_bytes = base64.b64decode(
            (B1C_FIXTURES / "b1c-two-page.pdf.base64").read_text().strip(),
            validate=True,
        )
        sources = []
        responses = []
        for role in profile_document["payload"]["roles"]:  # type: ignore[index]
            source_key = role["source_key"]
            url = f"https://external-api.kalshi.com/{source_key}"
            content_kind = role["content_kind"]
            if content_kind == "json":
                body = b"{}"
                media_type = "application/json"
                suffix = "json"
            elif content_kind == "text":
                body = b"# Synthetic evidence\n\nOffline only.\n"
                media_type = "text/markdown"
                suffix = "md"
            else:
                body = pdf_bytes
                media_type = "application/pdf"
                suffix = "pdf"
            sources.append({
                "id": source_key,
                "role": role["role"],
                "url": url,
                "path": f"sources/{source_key}/source.{suffix}",
            })
            responses.append(FakeResponse(
                url=url,
                body=body,
                headers={"Content-Type": media_type, "Content-Length": str(len(body))},
            ))
        spec_path = self.generated_root / f"acquisition-v3-{observation_id}.json"
        spec_path.write_text(json.dumps({
            "schema": terms.ACQUISITION_SPEC_V3_SCHEMA,
            "venue": "kalshi",
            "environment": "production",
            "observation_id": observation_id,
            "acquisition_policy": policy_path.name,
            "acquisition_policy_sha256": loaded_policy.payload_sha256,
            "evidence_profile": profile_path.name,
            "evidence_profile_sha256": profile_document["payload_sha256"],
            "sources": sources,
        }), encoding="utf-8")
        return spec_path, responses

    @staticmethod
    def advancing_clock(start_second: int) -> object:
        current = start_second

        def now() -> datetime:
            nonlocal current
            value = datetime(2026, 7, 17, 12, 0, current, tzinfo=timezone.utc)
            current += 1
            return value

        return now

    @staticmethod
    def fixed_clock() -> datetime:
        return datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)

    @staticmethod
    def schema_validator(name: str) -> Draft202012Validator:
        path = phase7.REPOSITORY_ROOT / "schemas" / "product_terms" / name
        schema = json.loads(path.read_text())
        return Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
            resolver=RefResolver(base_uri=path.parent.as_uri() + "/", referrer=schema),
        )

    @staticmethod
    def evidence_profile_document() -> dict[str, object]:
        roles = []
        for role, (_, media_types, content_kind) in sorted(terms.ROLE_POLICIES.items()):
            roles.append({
                "source_key": role,
                "role": role,
                "applicability": "required",
                "reason": None,
                "cardinality_per_observation": {"minimum": 1, "maximum": 1},
                "media_types": sorted(media_types),
                "content_kind": content_kind,
                "mutability": (
                    "mutable_endpoint" if content_kind == "json" else "static_document"
                ),
                "linked_source_keys": [],
            })
        payload = {
            "venue": "kalshi",
            "environment": "production",
            "profile_id": "synthetic_complete_binary.v1",
            "observations": ["opening", "closing"],
            "roles": roles,
            "field_coverage": [{
                "term_pointer": "/payload/identity/market_ticker",
                "coverage_class": "mechanically_projected",
            }],
        }
        return {
            "schema": terms.EVIDENCE_PROFILE_SCHEMA,
            "payload": payload,
            "payload_sha256": terms.sha256_bytes(terms.canonical_json_bytes(payload)),
        }

    def write_evidence_profile(
        self,
        label: str,
        mutate: object | None = None,
    ) -> tuple[Path, dict[str, object]]:
        document = self.evidence_profile_document()
        if mutate is not None:
            mutate(document)  # type: ignore[operator]
        path = self.generated_root / f"evidence-profile-{label}.json"
        self.write_envelope(path, document)
        return path, document

    @staticmethod
    def profile_sources(profile: terms.EvidenceProfile) -> list[dict[str, object]]:
        sources = []
        for observation in profile.payload["observations"]:
            for role in profile.payload["roles"]:
                if role["applicability"] == "not_applicable":
                    continue
                sources.append({
                    "id": f"{observation}_{role['source_key']}",
                    "observation_id": observation,
                    "source_key": role["source_key"],
                    "role": role["role"],
                    "media_type": role["media_types"][0],
                })
        return sources

    def make_successor_hmonth_package(self, label: str) -> Path:
        package = self.generated_root / f"successor-{label}"
        shutil.copytree(CATALOG_ROOT / HMONTH_RELATIVE, package)
        manifest_path = package / "source_manifest.json"
        manifest = json.loads(manifest_path.read_text())

        role_templates: dict[str, dict[str, object]] = {}
        for source in manifest["payload"]["sources"]:
            observation = source["observation_id"]
            prefix = f"{observation}_"
            self.assertTrue(source["id"].startswith(prefix))
            source_key = source["id"][len(prefix):]
            source["source_key"] = source_key
            source["tool_version"] = terms.ACQUISITION_TOOL_V4_VERSION
            _, allowed_media, content_kind = terms.ROLE_POLICIES[source["role"]]
            role_templates[source_key] = {
                "source_key": source_key,
                "role": source["role"],
                "applicability": "required",
                "reason": None,
                "cardinality_per_observation": {"minimum": 1, "maximum": 1},
                "media_types": sorted(allowed_media),
                "content_kind": content_kind,
                "mutability": (
                    "mutable_endpoint" if content_kind == "json" else "static_document"
                ),
                "linked_source_keys": [],
            }
        for acquisition in manifest["payload"]["acquisitions"]:
            acquisition["tool_version"] = terms.ACQUISITION_TOOL_V4_VERSION

        product = json.loads((package / "product_terms.json").read_text())
        leaf_pointers = sorted(terms._term_leaf_pointers(product["payload"]))
        title_pointer = "/payload/identity/title"
        field_coverage = [{
            "term_pointer": pointer,
            "coverage_class": (
                "mechanically_projected" if pointer == title_pointer
                else "repository_local_policy"
            ),
        } for pointer in leaf_pointers]
        profile_payload = {
            "venue": "kalshi",
            "environment": "production",
            "profile_id": "synthetic_hmonth_successor.v1",
            "observations": ["opening", "closing"],
            "roles": [role_templates[key] for key in sorted(role_templates)],
            "field_coverage": field_coverage,
        }
        profile = terms.build_envelope(terms.EVIDENCE_PROFILE_SCHEMA, profile_payload)
        (package / "evidence_profile.json").write_bytes(terms.canonical_json_bytes(profile))

        manifest["schema"] = terms.SOURCE_MANIFEST_V4_SCHEMA
        manifest["payload"]["evidence_profile_sha256"] = profile["payload_sha256"]
        self.write_envelope(manifest_path, manifest)

        source_by_id = {
            source["id"]: source for source in manifest["payload"]["sources"]
        }
        evidence_entries = []
        for pointer in leaf_pointers:
            if pointer == title_pointer:
                anchors = [{
                    "source_id": source_id,
                    "source_sha256": source_by_id[source_id]["sha256"],
                    "locator": {"kind": "json_pointer", "pointer": "/market/title"},
                } for source_id in ("opening_market_record", "closing_market_record")]
                entry = {
                    "term_pointer": pointer,
                    "coverage_class": "mechanically_projected",
                    "anchors": anchors,
                    "dependency_pointers": [],
                    "policy_id": None,
                    "reason": None,
                }
            else:
                entry = {
                    "term_pointer": pointer,
                    "coverage_class": "repository_local_policy",
                    "anchors": [],
                    "dependency_pointers": [],
                    "policy_id": "synthetic_test_authoring.v1",
                    "reason": None,
                }
            evidence_entries.append(entry)
        extractor = {
            "policy_id": "poppler_page_text.v1",
            "pdfinfo_executable": "pdfinfo",
            "pdfinfo_version": terms.SUPPORTED_PDFINFO_VERSION,
            "pdftotext_executable": "pdftotext",
            "pdftotext_version": terms.SUPPORTED_PDFTOTEXT_VERSION,
            "pdftotext_arguments": terms.PDFTOTEXT_ARGUMENTS,
            "nixpkgs_revision": terms.SUPPORTED_EXTRACTOR_NIXPKGS_REVISION,
            "poppler_package_version": terms.SUPPORTED_POPPLER_VERSION,
            "normalization_policy": terms.DOCUMENT_NORMALIZATION_POLICY["policy_id"],
            "normalization_policy_sha256": terms.DOCUMENT_NORMALIZATION_POLICY_SHA256,
        }
        evidence_payload = {
            "effective_interval_evidence": {
                "opening_observation_id": "opening",
                "closing_observation_id": "closing",
            },
            "evidence_profile_sha256": profile["payload_sha256"],
            "extractor_policy": extractor,
            "entries": evidence_entries,
        }
        evidence_map = terms.build_envelope(terms.EVIDENCE_MAP_V2_SCHEMA, evidence_payload)
        (package / "evidence_anchors.json").write_bytes(
            terms.canonical_json_bytes(evidence_map)
        )

        review_path = package / "review.json"
        review = json.loads(review_path.read_text())
        review["schema"] = terms.PRODUCT_REVIEW_V3_SCHEMA
        review["payload"]["source_manifest_sha256"] = manifest["payload_sha256"]
        review["payload"]["evidence_profile_sha256"] = profile["payload_sha256"]
        review["payload"]["evidence_map_sha256"] = evidence_map["payload_sha256"]
        self.write_envelope(review_path, review)
        return package

    @staticmethod
    def package_tree_fingerprint(path: Path) -> tuple[int, str]:
        """Hash names and bytes so compatibility tests detect any package rewrite."""
        digest = hashlib.sha256()
        files = sorted(candidate for candidate in path.rglob("*") if candidate.is_file())
        for candidate in files:
            relative = candidate.relative_to(path).as_posix().encode("utf-8")
            data = candidate.read_bytes()
            digest.update(len(relative).to_bytes(8, "big"))
            digest.update(relative)
            digest.update(len(data).to_bytes(8, "big"))
            digest.update(data)
        return len(files), digest.hexdigest()

    def test_accepted_package_bytes_are_frozen_across_b1c(self) -> None:
        self.assertEqual(
            self.package_tree_fingerprint(CATALOG_ROOT / HMONTH_RELATIVE),
            (21, "ebb859a8af47c6c8e6c1c231af2b05bdf5c48a338b77c4f2cb4757d598640d84"),
        )
        self.assertEqual(
            self.package_tree_fingerprint(CATALOG_ROOT / PACKAGE_RELATIVE),
            (9, "c46c9c9075c67909e898aeb6f92667659a7c19a1122fd31b51e49ff77c3ab3a7"),
        )

    def test_legacy_package_meanings_remain_version_specific(self) -> None:
        hmonth = terms.ProductPackage.load(CATALOG_ROOT / HMONTH_RELATIVE)
        wnba = terms.ProductPackage.load(CATALOG_ROOT / PACKAGE_RELATIVE)
        self.assertEqual(hmonth.evidence.schema, terms.SOURCE_MANIFEST_V3_SCHEMA)
        self.assertEqual(hmonth.review.schema, terms.PRODUCT_REVIEW_V2_SCHEMA)
        self.assertEqual(
            json.loads((hmonth.path / "evidence_anchors.json").read_text())["schema"],
            terms.EVIDENCE_MAP_SCHEMA,
        )
        self.assertEqual(wnba.evidence.schema, terms.SOURCE_MANIFEST_SCHEMA)
        self.assertEqual(wnba.review.schema, terms.PRODUCT_REVIEW_SCHEMA)
        self.assertIsNone(wnba.review.evidence_map)
        hmonth_roles = {
            observation: {
                source["role"]
                for source in hmonth.evidence.payload["sources"]
                if source["observation_id"] == observation
            }
            for observation in ("opening", "closing")
        }
        self.assertEqual(hmonth_roles["opening"], set(terms.ROLE_POLICIES))
        self.assertEqual(hmonth_roles["closing"], set(terms.ROLE_POLICIES))
        self.assertEqual(len(wnba.evidence.payload["sources"]), 6)

    def test_successor_package_verifies_profile_manifest_map_and_review(self) -> None:
        package_path = self.make_successor_hmonth_package("valid")
        with mock.patch.object(
            terms,
            "_tool_version",
            side_effect=[terms.SUPPORTED_PDFINFO_VERSION, terms.SUPPORTED_PDFTOTEXT_VERSION],
        ):
            package = terms.ProductPackage.load(package_path)
        self.assertEqual(package.evidence.schema, terms.SOURCE_MANIFEST_V4_SCHEMA)
        self.assertEqual(package.review.schema, terms.PRODUCT_REVIEW_V3_SCHEMA)
        self.assertEqual(package.review.evidence_map.schema, terms.EVIDENCE_MAP_V2_SCHEMA)
        self.assertIsNotNone(package.evidence.evidence_profile)

    def test_successor_profile_hash_mutations_refuse_at_each_boundary(self) -> None:
        cases = (
            ("manifest", "source_manifest.json", "evidence_profile_sha256"),
            ("evidence-map", "evidence_anchors.json", "evidence_profile_sha256"),
            ("review", "review.json", "evidence_profile_sha256"),
        )
        for label, filename, field in cases:
            with self.subTest(label=label):
                package = self.make_successor_hmonth_package(label)
                path = package / filename
                document = json.loads(path.read_text())
                document["payload"][field] = "0" * 64
                self.write_envelope(path, document)
                with mock.patch.object(
                    terms,
                    "_tool_version",
                    side_effect=[
                        terms.SUPPORTED_PDFINFO_VERSION,
                        terms.SUPPORTED_PDFTOTEXT_VERSION,
                    ],
                ):
                    with self.assertRaisesRegex(
                        terms.ProductTermsError,
                        "EvidenceProfileMismatch",
                    ):
                        terms.ProductPackage.load(package)

    def test_review_v3_duplicate_checklist_refuses_in_schema_and_runtime(self) -> None:
        package = self.make_successor_hmonth_package("review-v3-duplicate")
        review_path = package / "review.json"
        review = json.loads(review_path.read_text())
        review["payload"]["checklist"].append(dict(review["payload"]["checklist"][0]))
        self.write_envelope(review_path, review)
        with self.assertRaises(ValidationError):
            self.schema_validator("review-v3.schema.json").validate(review)
        with self.assertRaisesRegex(terms.ProductTermsError, "TermsNoncanonical"):
            terms.ProductPackage.load(package)

    def test_successor_public_cli_success_and_refusal_streams(self) -> None:
        package = self.make_successor_hmonth_package("cli")
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(
            terms,
            "_tool_version",
            side_effect=[terms.SUPPORTED_PDFINFO_VERSION, terms.SUPPORTED_PDFTOTEXT_VERSION],
        ), redirect_stdout(stdout), redirect_stderr(stderr):
            status = terms.main(["verify-package", "--package", str(package)])
        self.assertEqual(status, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(json.loads(stdout.getvalue())["status"], "valid")

        review_path = package / "review.json"
        review = json.loads(review_path.read_text())
        review["payload"]["evidence_profile_sha256"] = "0" * 64
        self.write_envelope(review_path, review)
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(
            terms,
            "_tool_version",
            side_effect=[terms.SUPPORTED_PDFINFO_VERSION, terms.SUPPORTED_PDFTOTEXT_VERSION],
        ), redirect_stdout(stdout), redirect_stderr(stderr):
            status = terms.main(["verify-package", "--package", str(package)])
        self.assertEqual(status, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("error: EvidenceProfileMismatch:", stderr.getvalue())

    def test_evidence_profile_schema_and_runtime_one_defect_matrix(self) -> None:
        valid_path, valid_document = self.write_evidence_profile("valid")
        validator = self.schema_validator("evidence-profile-v1.schema.json")
        validator.validate(valid_document)
        profile = terms.EvidenceProfile.load(valid_path)
        self.assertEqual(profile.payload["observations"], ["opening", "closing"])

        def role(document: dict[str, object], name: str) -> dict[str, object]:
            return next(
                item for item in document["payload"]["roles"]  # type: ignore[index]
                if item["role"] == name
            )

        cases = {
            "missing-role": lambda document: document["payload"]["roles"].pop(),  # type: ignore[index]
            "duplicate-source-key": lambda document: role(
                document, "market_record"
            ).update({"source_key": "event_metadata_record"}),
            "optional-empty-reason": lambda document: role(
                document, "market_record"
            ).update({
                "applicability": "optional",
                "reason": "",
                "cardinality_per_observation": {"minimum": 0, "maximum": 1},
            }),
            "not-applicable-wrong-cardinality": lambda document: role(
                document, "market_record"
            ).update({
                "applicability": "not_applicable",
                "reason": "not used by this synthetic family",
            }),
            "wrong-media": lambda document: role(
                document, "market_record"
            ).update({"media_types": ["application/pdf"]}),
            "wrong-mutability": lambda document: role(
                document, "market_record"
            ).update({"mutability": "static_document"}),
            "unknown-link": lambda document: role(
                document, "market_record"
            ).update({"linked_source_keys": ["missing"]}),
        }
        schema_structural = {
            "missing-role",
            "optional-empty-reason",
        }
        for label, mutation in cases.items():
            with self.subTest(label=label):
                path, document = self.write_evidence_profile(label, mutation)
                if label in schema_structural:
                    self.assertFalse(validator.is_valid(document))
                with self.assertRaisesRegex(terms.ProductTermsError, "EvidenceProfileMismatch"):
                    terms.EvidenceProfile.load(path)

    def test_profile_source_membership_required_optional_and_not_applicable(self) -> None:
        for applicability, cardinality, reason in (
            ("required", {"minimum": 1, "maximum": 1}, None),
            ("optional", {"minimum": 0, "maximum": 1}, "optional test role"),
            ("not_applicable", {"minimum": 0, "maximum": 0}, "not applicable here"),
        ):
            with self.subTest(applicability=applicability):
                def mutate(document: dict[str, object]) -> None:
                    target = next(
                        item for item in document["payload"]["roles"]  # type: ignore[index]
                        if item["role"] == "market_record"
                    )
                    target.update({
                        "applicability": applicability,
                        "cardinality_per_observation": cardinality,
                        "reason": reason,
                    })

                path, _ = self.write_evidence_profile(applicability, mutate)
                profile = terms.EvidenceProfile.load(path)
                sources = self.profile_sources(profile)
                if applicability == "optional":
                    sources = [
                        source for source in sources if source["source_key"] != "market_record"
                    ]
                profile.verify_sources(sources, ["opening", "closing"])

                if applicability == "required":
                    missing = [
                        source for source in sources
                        if not (
                            source["observation_id"] == "opening"
                            and source["source_key"] == "market_record"
                        )
                    ]
                    with self.assertRaisesRegex(terms.ProductTermsError, "EvidenceIncomplete"):
                        profile.verify_sources(missing, ["opening", "closing"])
                elif applicability == "optional":
                    opening_only = sources + [{
                        "id": "opening_market_record",
                        "observation_id": "opening",
                        "source_key": "market_record",
                        "role": "market_record",
                        "media_type": "application/json",
                    }]
                    with self.assertRaisesRegex(terms.ProductTermsError, "EvidenceIncomplete"):
                        profile.verify_sources(opening_only, ["opening", "closing"])
                else:
                    present = sources + [{
                        "id": "opening_market_record",
                        "observation_id": "opening",
                        "source_key": "market_record",
                        "role": "market_record",
                        "media_type": "application/json",
                    }]
                    with self.assertRaisesRegex(terms.ProductTermsError, "EvidenceIncomplete"):
                        profile.verify_sources(present, ["opening", "closing"])

    def test_profile_source_membership_refuses_one_defect_at_a_time(self) -> None:
        path, _ = self.write_evidence_profile("membership")
        profile = terms.EvidenceProfile.load(path)
        donors = self.profile_sources(profile)
        cases = {
            "duplicate-required": lambda sources: sources.append(dict(sources[0])),
            "wrong-source-id": lambda sources: sources[0].update({"id": "wrong"}),
            "wrong-role": lambda sources: sources[0].update({"role": "market_record"}),
            "wrong-media": lambda sources: sources[0].update({"media_type": "application/pdf"}),
        }
        expected = {
            "duplicate-required": "EvidenceIncomplete",
            "wrong-source-id": "EvidenceIncomplete",
            "wrong-role": "EvidenceIncomplete",
            "wrong-media": "AcquisitionMediaTypeMismatch",
        }
        for label, mutation in cases.items():
            with self.subTest(label=label):
                sources = [dict(source) for source in donors]
                mutation(sources)
                with self.assertRaisesRegex(terms.ProductTermsError, expected[label]):
                    profile.verify_sources(sources, ["opening", "closing"])

    def test_document_normalization_is_unicode_and_line_ending_stable(self) -> None:
        decomposed = "  Cafe\u0301\u00a0terms\t\r\n\r\n\r\n  second  line  \r\n"
        self.assertEqual(
            terms._normalize_document_text(decomposed, pdf=False),
            "Caf\u00e9 terms\n\nsecond line",
        )
        self.assertEqual(
            terms._normalize_document_text("o\ufb03cial \ufb02ow", pdf=True),
            "official flow",
        )
        self.assertEqual(
            terms._normalize_document_text("o\ufb03cial \ufb02ow", pdf=False),
            "o\ufb03cial \ufb02ow",
        )

    def test_markdown_structural_sections_ignore_body_text_and_fences(self) -> None:
        fixture = (B1C_FIXTURES / "b1c-sections.md").read_text(encoding="utf-8")
        sections = terms._markdown_sections(fixture)
        settlement = next(
            section for section in sections
            if section[0][-1] == {"level": 2, "text": "Settlement Rules"}
        )
        normalized = terms._normalize_document_text(fixture, pdf=False)
        lines = normalized.split("\n")
        bounded = "\n".join(lines[settlement[1]:settlement[2]])
        self.assertIn("### Contingencies", bounded)
        self.assertNotIn("## Fee Rules", bounded)

        lookalikes = """Settlement Rules in body text

```markdown
## Settlement Rules
```

Settlement Rules
----------------
"""
        self.assertEqual(terms._markdown_sections(lookalikes), [])

    def test_pdf_page_extraction_bounds_textless_and_repetition_offline(self) -> None:
        pdf_path = self.generated_root / "two-page.pdf"
        encoded = (B1C_FIXTURES / "b1c-two-page.pdf.base64").read_text().strip()
        pdf_bytes = base64.b64decode(encoded, validate=True)
        pdf_path.write_bytes(pdf_bytes)
        extractor = {
            "policy_id": "poppler_page_text.v1",
            "pdfinfo_executable": "pdfinfo",
            "pdfinfo_version": terms.SUPPORTED_PDFINFO_VERSION,
            "pdftotext_executable": "pdftotext",
            "pdftotext_version": terms.SUPPORTED_PDFTOTEXT_VERSION,
            "pdftotext_arguments": terms.PDFTOTEXT_ARGUMENTS,
            "nixpkgs_revision": terms.SUPPORTED_EXTRACTOR_NIXPKGS_REVISION,
            "poppler_package_version": terms.SUPPORTED_POPPLER_VERSION,
            "normalization_policy": terms.DOCUMENT_NORMALIZATION_POLICY["policy_id"],
            "normalization_policy_sha256": terms.DOCUMENT_NORMALIZATION_POLICY_SHA256,
        }
        with mock.patch.object(
            terms,
            "_tool_version",
            side_effect=[terms.SUPPORTED_PDFINFO_VERSION, terms.SUPPORTED_PDFTOTEXT_VERSION],
        ):
            self.assertEqual(terms._verify_extractor_policy(extractor), extractor)
        first = terms._extract_pdf_page(pdf_path, 2, extractor)
        second = terms._extract_pdf_page(pdf_path, 2, extractor)
        self.assertEqual(first, second)
        self.assertEqual(first[0], 2)
        self.assertIn("Settlement Rules", first[1])
        for page in (0, 3):
            with self.subTest(page=page):
                with self.assertRaisesRegex(terms.ProductTermsError, "EvidenceAnchorMismatch"):
                    terms._extract_pdf_page(pdf_path, page, extractor)

        malformed = self.generated_root / "malformed.pdf"
        malformed.write_bytes(pdf_bytes[:80])
        with self.assertRaisesRegex(terms.ProductTermsError, "EvidenceAnchorMismatch"):
            terms._extract_pdf_page(malformed, 1, extractor)

        textless = self.generated_root / "textless.pdf"
        textless_bytes = bytearray(pdf_bytes)
        for match in list(re.finditer(b"stream\n(.*?)\nendstream", pdf_bytes, re.DOTALL)):
            textless_bytes[match.start(1):match.end(1)] = b" " * (match.end(1) - match.start(1))
        textless.write_bytes(textless_bytes)
        with self.assertRaisesRegex(terms.ProductTermsError, "EvidenceAnchorMismatch"):
            terms._extract_pdf_page(textless, 1, extractor)

    def test_extractor_policy_refuses_every_unpinned_identity(self) -> None:
        donor = {
            "policy_id": "poppler_page_text.v1",
            "pdfinfo_executable": "pdfinfo",
            "pdfinfo_version": terms.SUPPORTED_PDFINFO_VERSION,
            "pdftotext_executable": "pdftotext",
            "pdftotext_version": terms.SUPPORTED_PDFTOTEXT_VERSION,
            "pdftotext_arguments": terms.PDFTOTEXT_ARGUMENTS,
            "nixpkgs_revision": terms.SUPPORTED_EXTRACTOR_NIXPKGS_REVISION,
            "poppler_package_version": terms.SUPPORTED_POPPLER_VERSION,
            "normalization_policy": terms.DOCUMENT_NORMALIZATION_POLICY["policy_id"],
            "normalization_policy_sha256": terms.DOCUMENT_NORMALIZATION_POLICY_SHA256,
        }
        cases = {
            "nixpkgs-revision": ("nixpkgs_revision", "0" * 40),
            "poppler-package": ("poppler_package_version", "26.07.0"),
            "pdfinfo-declaration": ("pdfinfo_version", "pdfinfo version 26.07.0"),
            "pdftotext-declaration": (
                "pdftotext_version",
                "pdftotext version 26.07.0",
            ),
            "normalization-hash": ("normalization_policy_sha256", "0" * 64),
        }
        for label, (field, value) in cases.items():
            with self.subTest(label=label):
                changed = dict(donor)
                changed[field] = value
                with mock.patch.object(
                    terms,
                    "_tool_version",
                    side_effect=[
                        terms.SUPPORTED_PDFINFO_VERSION,
                        terms.SUPPORTED_PDFTOTEXT_VERSION,
                    ],
                ):
                    with self.assertRaisesRegex(
                        terms.ProductTermsError,
                        "EvidenceAnchorMismatch",
                    ):
                        terms._verify_extractor_policy(changed)

    def test_encrypted_pdf_refuses_at_offline_process_boundary(self) -> None:
        pdf_path = self.generated_root / "encrypted.pdf"
        pdf_path.write_bytes(b"%PDF-1.7\nsynthetic encrypted boundary\n")
        extractor = {
            "pdfinfo_executable": "pdfinfo",
            "pdftotext_executable": "pdftotext",
            "pdftotext_arguments": terms.PDFTOTEXT_ARGUMENTS,
        }
        encrypted_result = subprocess.CompletedProcess(
            ["pdfinfo", str(pdf_path)],
            1,
            stdout=b"",
            stderr=b"Command Line Error: Incorrect password\n",
        )
        with mock.patch.object(terms.subprocess, "run", return_value=encrypted_result):
            with self.assertRaisesRegex(
                terms.ProductTermsError,
                "EvidenceAnchorMismatch: PDF is malformed, encrypted, or unreadable",
            ):
                terms._extract_pdf_page(pdf_path, 1, extractor)

    def test_section_fingerprints_bind_boundaries_and_normalized_content(self) -> None:
        boundary = {"page": 2, "start": "Settlement Rules", "end": "Fee Rules"}
        text = "Settlement Rules\nSecond page evidence."
        fingerprint = terms._section_fingerprint("pdf_section", boundary, text)
        self.assertEqual(
            fingerprint,
            terms._section_fingerprint("pdf_section", dict(boundary), text),
        )
        self.assertNotEqual(
            fingerprint,
            terms._section_fingerprint("pdf_section", {**boundary, "page": 1}, text),
        )
        self.assertNotEqual(
            fingerprint,
            terms._section_fingerprint("pdf_section", boundary, text + " changed"),
        )

    def test_reviewed_catalog_and_conversion_policy_are_canonical(self) -> None:
        catalog, policy, package = self.load()
        self.assertEqual(len(catalog.payload["entries"]), 2)
        self.assertEqual(package.terms.market_ticker, TICKER)
        self.assertEqual(package.review.payload["effective_time_basis"], "reviewed_retrospective")
        self.assertEqual(policy.convert_price_to_cents(package.terms.validate_price("0.5000", "price"), "price"), 50)
        self.assertEqual(policy.convert_quantity_to_contracts(terms.Decimal("2.00"), "quantity"), 2)
        with self.assertRaisesRegex(terms.ProductTermsError, "CoreQuantityNotRepresentable"):
            policy.convert_quantity_to_contracts(terms.Decimal("0.25"), "quantity")

    def test_hmonth_bracketed_package_has_v2_reviewed_evidence(self) -> None:
        catalog = terms.ProductCatalog.load(CATALOG_ROOT)
        package = terms.ProductPackage.load(CATALOG_ROOT / HMONTH_RELATIVE)
        policy = terms.ConversionPolicy.load(POLICY_PATH)
        self.assertEqual(package.terms.market_ticker, "KXHMONTH-26JUL")
        self.assertEqual(package.review.schema, terms.PRODUCT_REVIEW_V2_SCHEMA)
        self.assertEqual(package.review.payload["reviewer"]["identity"], "ronit")
        self.assertEqual(package.evidence.schema, terms.SOURCE_MANIFEST_V3_SCHEMA)
        self.assertIsNotNone(package.review.evidence_map)
        self.assertEqual(
            package.terms.payload["rules"]["secondary"], ""
        )
        policy.require_core_compatible(package.terms)
        with self.assertRaisesRegex(terms.ProductTermsError, "CoreQuantityNotRepresentable"):
            policy.convert_quantity_to_contracts(terms.Decimal("0.01"), "quantity")
        capture_start = datetime(2026, 7, 17, 15, 7, 30, tzinfo=timezone.utc)
        metadata = {
            "ticker": "KXHMONTH-26JUL",
            "capture_started_at_utc_ns": int(capture_start.timestamp() * 1_000_000_000),
            "capture_ended_at_utc_ns": int(capture_start.timestamp() * 1_000_000_000) + 1_000_000_000,
        }
        self.assertEqual(catalog.resolve(metadata).path, package.path)

    def test_hmonth_field_anchor_mutation_refuses_after_complete_rehash(self) -> None:
        copied = self.generated_root / "hmonth-anchor-mutation"
        shutil.copytree(CATALOG_ROOT / HMONTH_RELATIVE, copied)
        evidence_path = copied / "evidence_anchors.json"
        evidence = json.loads(evidence_path.read_text())
        title_entry = next(
            item for item in evidence["payload"]["entries"]
            if item["term_pointer"] == "/payload/identity/title"
        )
        title_entry["anchors"][0]["locator"]["pointer"] = "/market/ticker"
        self.write_envelope(evidence_path, evidence)
        review_path = copied / "review.json"
        review = json.loads(review_path.read_text())
        review["payload"]["evidence_map_sha256"] = evidence["payload_sha256"]
        self.write_envelope(review_path, review)
        snapshot = {
            path.relative_to(copied): path.read_bytes()
            for path in copied.rglob("*") if path.is_file()
        }
        with self.assertRaisesRegex(terms.ProductTermsError, "EvidenceAnchorMismatch"):
            terms.ProductPackage.load(copied)
        self.assertEqual(snapshot, {
            path.relative_to(copied): path.read_bytes()
            for path in copied.rglob("*") if path.is_file()
        })

    def test_review_v2_responsibility_and_checklist_one_defect_matrix(self) -> None:
        cases = {
            "empty-reviewer": (
                lambda payload: payload["reviewer"].update({"identity": ""}),
                "TermsNoncanonical",
            ),
            "duplicate-responsibility": (
                lambda payload: payload["responsibilities"].append(
                    payload["responsibilities"][0]
                ),
                "TermsNoncanonical",
            ),
            "unaccepted-checklist-item": (
                lambda payload: payload["checklist"][0].update({"status": "rejected"}),
                "ReviewNotApproved",
            ),
        }
        for label, (mutation, expected) in cases.items():
            with self.subTest(label=label):
                package = self.generated_root / f"review-v2-{label}"
                shutil.copytree(CATALOG_ROOT / HMONTH_RELATIVE, package)
                review_path = package / "review.json"
                review = json.loads(review_path.read_text())
                mutation(review["payload"])
                self.write_envelope(review_path, review)
                with self.assertRaisesRegex(terms.ProductTermsError, expected):
                    terms.ProductPackage.load(package)

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
                    entry = next(
                        item for item in document["payload"]["entries"]
                        if item["market_ticker"] == TICKER
                    )
                    entry["effective_from_utc"] = "2026-07-12T23:31:00Z"
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
        second_entry = dict(next(
            item for item in manifest["payload"]["entries"]
            if item["market_ticker"] == TICKER
        ))
        second_entry.update({
            "effective_from_utc": boundary,
            "effective_until_utc": second_end,
            "package": second_relative.as_posix(),
            "product_terms_sha256": terms_document["payload_sha256"],
            "review_sha256": review_document["payload_sha256"],
        })
        manifest["payload"]["entries"].append(second_entry)
        manifest["payload"]["entries"].sort(
            key=lambda item: (item["market_ticker"], item["effective_from_utc"])
        )
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
                changed_entry = next(
                    item for item in changed_manifest["payload"]["entries"]
                    if item["package"] == second_relative.as_posix()
                )
                changed_entry["effective_from_utc"] = changed_start
                changed_entry["product_terms_sha256"] = changed_terms["payload_sha256"]
                changed_entry["review_sha256"] = changed_review["payload_sha256"]
                changed_manifest["payload"]["entries"].sort(
                    key=lambda item: (item["market_ticker"], item["effective_from_utc"])
                )
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

    def test_profile_bound_v3_spec_fetches_complete_v4_observation_offline(self) -> None:
        spec_path, responses = self.acquisition_spec_v3("opening")
        output = self.generated_root / "profile-bound-opening"
        terms.fetch_sources(
            spec_path,
            output,
            session=FakeSession(responses),
            now=self.advancing_clock(0),  # type: ignore[arg-type]
            monotonic=lambda: 0.0,
        )
        evidence = terms.SourceEvidence.load(output)
        self.assertEqual(evidence.schema, terms.SOURCE_MANIFEST_V4_SCHEMA)
        self.assertIsNotNone(evidence.evidence_profile)
        self.assertEqual(len(evidence.payload["sources"]), len(terms.ROLE_POLICIES))
        self.assertTrue(all(
            source["id"] == f"opening_{source['source_key']}"
            for source in evidence.payload["sources"]
        ))

    def test_profile_bound_fetch_refuses_missing_role_and_interrupts_cleanly(self) -> None:
        spec_path, responses = self.acquisition_spec_v3("opening")
        document = json.loads(spec_path.read_text())
        document["sources"].pop()
        spec_path.write_text(json.dumps(document), encoding="utf-8")
        missing_output = self.generated_root / "profile-missing-role"
        with self.assertRaisesRegex(terms.ProductTermsError, "EvidenceIncomplete"):
            terms.fetch_sources(
                spec_path,
                missing_output,
                session=FakeSession(responses),
                now=self.advancing_clock(0),  # type: ignore[arg-type]
                monotonic=lambda: 0.0,
            )
        self.assertFalse(missing_output.exists())
        self.assertEqual(
            list(self.generated_root.glob(f".{missing_output.name}.*.partial")),
            [],
        )

        interrupt_spec, interrupt_responses = self.acquisition_spec_v3("closing")
        interrupt_responses[0].interruption = KeyboardInterrupt()
        interrupted_output = self.generated_root / "profile-interrupted"
        with self.assertRaises(KeyboardInterrupt):
            terms.fetch_sources(
                interrupt_spec,
                interrupted_output,
                session=FakeSession(interrupt_responses),
                now=self.advancing_clock(20),  # type: ignore[arg-type]
                monotonic=lambda: 0.0,
            )
        self.assertFalse(interrupted_output.exists())
        self.assertEqual(
            list(self.generated_root.glob(f".{interrupted_output.name}.*.partial")),
            [],
        )

    def test_v3_policy_observations_assemble_into_exact_time_bracket(self) -> None:
        opening = self.generated_root / "opening"
        closing = self.generated_root / "closing"
        body = b'{"market":{"ticker":"KXTEST"}}'
        terms.fetch_sources(
            self.acquisition_spec_v2("opening"),
            opening,
            session=FakeSession([
                FakeResponse(url="https://external-api.kalshi.com/market", body=body)
            ]),
            now=self.advancing_clock(0),  # type: ignore[arg-type]
            monotonic=lambda: 0.0,
        )
        terms.fetch_sources(
            self.acquisition_spec_v2("closing"),
            closing,
            session=FakeSession([
                FakeResponse(url="https://external-api.kalshi.com/market", body=body)
            ]),
            now=self.advancing_clock(20),  # type: ignore[arg-type]
            monotonic=lambda: 0.0,
        )
        output = self.generated_root / "assembled"
        terms.assemble_observations(opening, closing, output)
        evidence = terms.SourceEvidence.load(output)
        self.assertEqual(evidence.schema, terms.SOURCE_MANIFEST_V3_SCHEMA)
        self.assertEqual(
            [item["observation_id"] for item in evidence.payload["acquisitions"]],
            ["opening", "closing"],
        )
        self.assertEqual(
            [item["id"] for item in evidence.payload["sources"]],
            ["closing_market_record", "opening_market_record"],
        )
        self.assertLess(
            terms.parse_utc(
                evidence.payload["acquisitions"][0]["completed_at_utc"], "opening"
            ),
            terms.parse_utc(
                evidence.payload["acquisitions"][1]["started_at_utc"], "closing"
            ),
        )

        changed_policy = json.loads((output / "acquisition_policy.json").read_text())
        changed_policy["payload"]["maximum_redirects"] = 4
        self.write_envelope(output / "acquisition_policy.json", changed_policy)
        with self.assertRaisesRegex(terms.ProductTermsError, "AcquisitionPolicyMismatch"):
            terms.SourceEvidence.load(output)

    def test_assembly_preserves_full_paths_when_basenames_match(self) -> None:
        opening = self.generated_root / "opening-nested"
        closing = self.generated_root / "closing-nested"
        body = b'{"market":{"ticker":"KXTEST"}}'
        for observation, output, source_path, second in (
            ("opening", opening, "sources/first/shared.json", 0),
            ("closing", closing, "sources/second/shared.json", 20),
        ):
            terms.fetch_sources(
                self.acquisition_spec_v2(observation, source_path=source_path),
                output,
                session=FakeSession([
                    FakeResponse(url="https://external-api.kalshi.com/market", body=body)
                ]),
                now=self.advancing_clock(second),  # type: ignore[arg-type]
                monotonic=lambda: 0.0,
            )

        assembled = self.generated_root / "assembled-nested"
        terms.assemble_observations(opening, closing, assembled)
        manifest = json.loads((assembled / "source_manifest.json").read_text())
        paths = {source["id"]: source["path"] for source in manifest["payload"]["sources"]}
        self.assertEqual(paths, {
            "closing_market_record": "sources/closing/second/shared.json",
            "opening_market_record": "sources/opening/first/shared.json",
        })
        self.assertEqual(
            (assembled / paths["opening_market_record"]).read_bytes(),
            body,
        )
        self.assertEqual(
            (assembled / paths["closing_market_record"]).read_bytes(),
            body,
        )

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
        hmonth = terms.ProductPackage.load(CATALOG_ROOT / HMONTH_RELATIVE)
        successor = self.make_successor_hmonth_package("schema-parity")
        successor_profile = json.loads((successor / "evidence_profile.json").read_text())
        acquisition_v3_path = self.generated_root / "acquisition-v3.json"
        acquisition_v3_path.write_text(json.dumps({
            "schema": terms.ACQUISITION_SPEC_V3_SCHEMA,
            "venue": "kalshi",
            "environment": "production",
            "observation_id": "opening",
            "acquisition_policy": "acquisition_policy.json",
            "acquisition_policy_sha256": json.loads(
                (successor / "acquisition_policy.json").read_text()
            )["payload_sha256"],
            "evidence_profile": "evidence_profile.json",
            "evidence_profile_sha256": successor_profile["payload_sha256"],
            "sources": [{
                "id": role["source_key"],
                "role": role["role"],
                "url": f"https://external-api.kalshi.com/{role['source_key']}",
                "path": f"sources/{role['source_key']}.source",
            } for role in successor_profile["payload"]["roles"]],
        }), encoding="utf-8")
        positive_documents = {
            "acquisition-spec-v1.schema.json": CATALOG_ROOT / "acquisition_spec.example.json",
            "acquisition-policy-v1.schema.json": CATALOG_ROOT / "acquisition_policies" / "kalshi_first_party_v1.json",
            "acquisition-spec-v2.schema.json": self.acquisition_spec_v2("opening"),
            "source-manifest-v1.schema.json": package.path / "source_manifest.json",
            "source-manifest-v3.schema.json": hmonth.path / "source_manifest.json",
            "source-manifest-v4.schema.json": successor / "source_manifest.json",
            "acquisition-spec-v3.schema.json": acquisition_v3_path,
            "evidence-profile-v1.schema.json": successor / "evidence_profile.json",
            "product-terms-v1.schema.json": package.path / "product_terms.json",
            "product-terms-v2.schema.json": hmonth.path / "product_terms.json",
            "review-v1.schema.json": package.path / "review.json",
            "review-v2.schema.json": hmonth.path / "review.json",
            "evidence-map-v1.schema.json": hmonth.path / "evidence_anchors.json",
            "evidence-map-v2.schema.json": successor / "evidence_anchors.json",
            "review-v3.schema.json": successor / "review.json",
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

    def test_hmonth_two_market_selection_normalizes_and_features_offline(self) -> None:
        catalog = terms.ProductCatalog.load(CATALOG_ROOT)
        policy = terms.ConversionPolicy.load(POLICY_PATH)
        package = terms.ProductPackage.load(CATALOG_ROOT / HMONTH_RELATIVE)
        capture_start = datetime(2026, 7, 17, 15, 7, 30, tzinfo=timezone.utc)
        capture = self.make_capture(
            ticker="KXHMONTH-26JUL",
            capture_started_ns=int(capture_start.timestamp() * 1_000_000_000),
        )
        normalized = self.generated_root / "hmonth-normalized"
        manifest = phase7.normalize_capture(
            capture,
            normalized,
            product_catalog=catalog,
            conversion_policy=policy,
        )
        self.assertEqual(manifest["product_terms_sha256"], package.terms.payload_sha256)
        copied_review = json.loads(
            (normalized / "product_terms" / "review.json").read_text()
        )
        self.assertEqual(copied_review["schema"], terms.PRODUCT_REVIEW_V2_SCHEMA)
        features = self.generated_root / "hmonth-features"
        feature_manifest = phase7.materialize_features(normalized, features)
        self.assertEqual(feature_manifest["product_terms_sha256"], package.terms.payload_sha256)
        self.assertEqual(
            (normalized / "product_terms" / "evidence_anchors.json").read_bytes(),
            (package.path / "evidence_anchors.json").read_bytes(),
        )

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
