"""Build truthful offline-only product packages for mounted integration tests."""

from __future__ import annotations

import json
from pathlib import Path
import shutil

from python import pmm_phase7 as phase7
from python import pmm_product_terms as terms


_SOURCE_PACKAGE = (
    phase7.REPOSITORY_ROOT
    / "configs/product_catalog/kalshi/production/markets/KXHMONTH-26JUL/"
    "2026-07-17T150716Z-150837Z-contemporaneous-bracketed"
)
_POLICY_SOURCE = (
    phase7.REPOSITORY_ROOT
    / "configs/product_catalog/acquisition_policies/kalshi_first_party_v1.json"
)
_OPENING_START = "2025-12-31T23:59:00.000000Z"
_OPENING_END = "2026-01-01T00:00:00.000000Z"
_CLOSING_START = "2026-01-01T13:00:00.000000Z"
_CLOSING_END = "2026-01-01T13:01:00.000000Z"


def _write_envelope(path: Path, schema: str, payload: dict[str, object]) -> None:
    path.write_bytes(terms.canonical_json_bytes(terms.build_envelope(schema, payload)))


def _profile_payload(
    product: dict[str, object], sources: list[dict[str, object]]
) -> dict[str, object]:
    role_by_key: dict[str, str] = {}
    for source in sources:
        observation = str(source["observation_id"])
        prefix = f"{observation}_"
        role_by_key[str(source["id"])[len(prefix):]] = str(source["role"])
    roles = []
    for source_key, role in sorted(role_by_key.items()):
        _, media_types, content_kind = terms.ROLE_POLICIES[role]
        roles.append({
            "source_key": source_key,
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
    return {
        "venue": "kalshi",
        "environment": "production",
        "profile_id": "synthetic_three_market_fixture.v1",
        "observations": ["opening", "closing"],
        "roles": roles,
        "field_coverage": [
            {
                "term_pointer": pointer,
                "coverage_class": "repository_local_policy",
            }
            for pointer in sorted(terms._term_leaf_pointers(product))
        ],
    }


def _extractor_policy() -> dict[str, object]:
    return {
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


def _mutate_retained_identity(package: Path, suffix: str) -> None:
    market_ticker = f"SYNTH-{suffix}"
    event_ticker = f"SYNTH-EVENT-{suffix}"
    series_ticker = f"SYNTH-SERIES-{suffix}"
    for observation in ("opening", "closing"):
        source_root = package / "sources" / observation
        market_path = source_root / "market.response.json"
        market_document = json.loads(market_path.read_text(encoding="utf-8"))
        market = market_document["market"]
        market.update({
            "ticker": market_ticker,
            "event_ticker": event_ticker,
            "title": f"Synthetic market {suffix}",
            "yes_sub_title": f"Synthetic yes {suffix}",
            "no_sub_title": f"Synthetic no {suffix}",
        })
        market_path.write_bytes(terms.canonical_json_bytes(market_document))

        series_path = source_root / "series.response.json"
        series_document = json.loads(series_path.read_text(encoding="utf-8"))
        series_document["series"]["ticker"] = series_ticker
        series_path.write_bytes(terms.canonical_json_bytes(series_document))

        event_path = source_root / "event-metadata.response.json"
        event_document = json.loads(event_path.read_text(encoding="utf-8"))
        for detail in event_document.get("market_details", []):
            detail["market_ticker"] = market_ticker
        event_path.write_bytes(terms.canonical_json_bytes(event_document))


def _build_package(root: Path, suffix: str) -> terms.ProductPackage:
    package = root / "packages" / f"SYNTH-{suffix}"
    shutil.copytree(_SOURCE_PACKAGE, package)
    _mutate_retained_identity(package, suffix)

    product_path = package / "product_terms.json"
    product_document = json.loads(product_path.read_text(encoding="utf-8"))
    product = product_document["payload"]
    market_ticker = f"SYNTH-{suffix}"
    product["revision_label"] = "synthetic-three-market-fixture-v1"
    product["effective"] = {
        "from_utc": _OPENING_END,
        "until_utc": _CLOSING_START,
        "basis": "contemporaneous_snapshot",
    }
    product["identity"].update({
        "series_ticker": f"SYNTH-SERIES-{suffix}",
        "event_ticker": f"SYNTH-EVENT-{suffix}",
        "market_ticker": market_ticker,
        "title": f"Synthetic market {suffix}",
        "yes_sub_title": f"Synthetic yes {suffix}",
        "no_sub_title": f"Synthetic no {suffix}",
        "contracts": [
            {"side": "no", "contract_id": f"{market_ticker}#no", "label": f"Synthetic no {suffix}"},
            {"side": "yes", "contract_id": f"{market_ticker}#yes", "label": f"Synthetic yes {suffix}"},
        ],
    })
    _write_envelope(product_path, terms.PRODUCT_TERMS_V2_SCHEMA, product)
    product_document = json.loads(product_path.read_text(encoding="utf-8"))

    shutil.copyfile(_POLICY_SOURCE, package / "acquisition_policy.json")
    policy = terms.AcquisitionPolicy.load(package / "acquisition_policy.json")
    legacy_manifest = json.loads((package / "source_manifest.json").read_text())
    profile_payload = _profile_payload(product, legacy_manifest["payload"]["sources"])
    _write_envelope(package / "evidence_profile.json", terms.EVIDENCE_PROFILE_SCHEMA, profile_payload)
    profile_document = json.loads((package / "evidence_profile.json").read_text())

    manifest_path = package / "source_manifest.json"
    manifest_document = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_payload = manifest_document["payload"]
    source_payload.update({
        "truth_category": "Synthetic",
        "acquisition_policy_sha256": policy.payload_sha256,
        "evidence_profile_sha256": profile_document["payload_sha256"],
        "acquisitions": [
            {"observation_id": "opening", "started_at_utc": _OPENING_START, "completed_at_utc": _OPENING_END, "tool_name": terms.ACQUISITION_TOOL_NAME, "tool_version": terms.ACQUISITION_TOOL_V4_VERSION},
            {"observation_id": "closing", "started_at_utc": _CLOSING_START, "completed_at_utc": _CLOSING_END, "tool_name": terms.ACQUISITION_TOOL_NAME, "tool_version": terms.ACQUISITION_TOOL_V4_VERSION},
        ],
    })
    for source in source_payload["sources"]:
        observation = source["observation_id"]
        prefix = f"{observation}_"
        source["source_key"] = source["id"][len(prefix):]
        source["tool_version"] = terms.ACQUISITION_TOOL_V4_VERSION
        source["requested_url"] = f"https://synthetic.invalid/{suffix}/{source['id']}"
        source["final_url"] = source["requested_url"]
        source["redirect_history"] = []
        if observation == "opening":
            source["retrieval_started_at_utc"] = _OPENING_START
            source["retrieval_completed_at_utc"] = _OPENING_END
        else:
            source["retrieval_started_at_utc"] = _CLOSING_START
            source["retrieval_completed_at_utc"] = _CLOSING_END
        retained = package / source["path"]
        source["byte_length"] = retained.stat().st_size
        source["sha256"] = terms.sha256_file(retained)
    _write_envelope(manifest_path, terms.SOURCE_MANIFEST_V4_SCHEMA, source_payload)
    manifest_document = json.loads(manifest_path.read_text(encoding="utf-8"))

    evidence_entries = [{
        "term_pointer": pointer,
        "coverage_class": "repository_local_policy",
        "anchors": [],
        "dependency_pointers": [],
        "policy_id": "synthetic_fixture_authoring.v1",
        "reason": None,
    } for pointer in sorted(terms._term_leaf_pointers(product))]
    evidence_payload = {
        "effective_interval_evidence": {
            "opening_observation_id": "opening",
            "closing_observation_id": "closing",
        },
        "evidence_profile_sha256": profile_document["payload_sha256"],
        "extractor_policy": _extractor_policy(),
        "entries": evidence_entries,
    }
    _write_envelope(package / "evidence_anchors.json", terms.EVIDENCE_MAP_V2_SCHEMA, evidence_payload)
    evidence_document = json.loads((package / "evidence_anchors.json").read_text())

    review_path = package / "review.json"
    review_document = json.loads(review_path.read_text(encoding="utf-8"))
    review = review_document["payload"]
    review.update({
        "status": "reviewed",
        "reviewed_at_utc": "2026-01-01T13:02:00Z",
        "reviewer": {"identity": "synthetic-test-builder", "identity_kind": "repository_declared"},
        "product_terms_sha256": product_document["payload_sha256"],
        "source_manifest_sha256": manifest_document["payload_sha256"],
        "acquisition_policy_sha256": policy.payload_sha256,
        "evidence_profile_sha256": profile_document["payload_sha256"],
        "evidence_map_sha256": evidence_document["payload_sha256"],
        "effective_from_utc": _OPENING_END,
        "effective_until_utc": _CLOSING_START,
        "limitations": [
            "Synthetic test-only package; it establishes no venue facts or production observations."
        ],
    })
    _write_envelope(review_path, terms.PRODUCT_REVIEW_V3_SCHEMA, review)
    return terms.ProductPackage.load(package)


def build_synthetic_product_catalog(root: Path) -> terms.ProductCatalog:
    """Create and validate a three-market, distinct-series Synthetic catalog."""
    root.mkdir(parents=True, exist_ok=False)
    packages = [_build_package(root, suffix) for suffix in ("A", "B", "C")]
    entries = []
    for package in packages:
        identity = package.terms.identity
        entries.append({
            "venue": "kalshi",
            "environment": "production",
            "series_ticker": identity["series_ticker"],
            "event_ticker": identity["event_ticker"],
            "market_ticker": identity["market_ticker"],
            "effective_from_utc": _OPENING_END,
            "effective_until_utc": _CLOSING_START,
            "package": package.path.relative_to(root).as_posix(),
            "product_terms_sha256": package.terms.payload_sha256,
            "source_manifest_sha256": package.evidence.payload_sha256,
            "review_sha256": package.review.payload_sha256,
        })
    _write_envelope(root / "manifest.json", terms.PRODUCT_CATALOG_SCHEMA, {"entries": entries})
    return terms.ProductCatalog.load(root)
