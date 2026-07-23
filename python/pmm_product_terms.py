#!/usr/bin/env python3
"""Authoritative, offline-verifiable venue product-term packages.

Network access is confined to the explicit ``fetch`` command.  Normalization,
feature generation, backtesting, package verification, and compatibility checks
consume only reviewed local bytes.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any, Callable, Iterable
import unicodedata
from urllib.parse import urljoin, urlparse

import requests


SOURCE_MANIFEST_SCHEMA = "pmm.product_terms_source_manifest.v1"
SOURCE_MANIFEST_V2_SCHEMA = "pmm.product_terms_source_manifest.v2"
SOURCE_MANIFEST_V3_SCHEMA = "pmm.product_terms_source_manifest.v3"
SOURCE_MANIFEST_V4_SCHEMA = "pmm.product_terms_source_manifest.v4"
ACQUISITION_SPEC_SCHEMA = "pmm.product_acquisition_spec.v1"
ACQUISITION_SPEC_V2_SCHEMA = "pmm.product_acquisition_spec.v2"
ACQUISITION_SPEC_V3_SCHEMA = "pmm.product_acquisition_spec.v3"
ACQUISITION_POLICY_SCHEMA = "pmm.product_acquisition_policy.v1"
EVIDENCE_PROFILE_SCHEMA = "pmm.product_evidence_profile.v1"
SUPPORTED_ACQUISITION_POLICY_SHA256 = (
    "583204c3d5a177d6247c20d1c3b12543aab6b454c8066bb3ee4943d974d3792b"
)
PRODUCT_TERMS_SCHEMA = "pmm.venue_product_terms.v1"
PRODUCT_TERMS_V2_SCHEMA = "pmm.venue_product_terms.v2"
PRODUCT_REVIEW_SCHEMA = "pmm.product_terms_review.v1"
PRODUCT_REVIEW_V2_SCHEMA = "pmm.product_terms_review.v2"
PRODUCT_REVIEW_V3_SCHEMA = "pmm.product_terms_review.v3"
EVIDENCE_MAP_SCHEMA = "pmm.product_evidence_map.v1"
EVIDENCE_MAP_V2_SCHEMA = "pmm.product_evidence_map.v2"
PRODUCT_CATALOG_SCHEMA = "pmm.product_catalog.v1"
CONVERSION_POLICY_SCHEMA = "pmm.product_conversion_policy.v1"
COMPATIBILITY_REPORT_SCHEMA = "pmm.product_compatibility_report.v1"

SHA256_LENGTH = 64
ACQUISITION_TOOL_NAME = "pmm_product_terms"
ACQUISITION_TOOL_VERSION = "product-acquisition.v2"
ACQUISITION_TOOL_V3_VERSION = "product-acquisition.v3"
ACQUISITION_TOOL_V4_VERSION = "product-acquisition.v4"
STREAM_CHUNK_BYTES = 64 * 1024
MAX_PACKAGE_BYTES = 64 * 1024 * 1024
MAX_REDIRECTS = 5
CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 15
SOURCE_DEADLINE_SECONDS = 60
PACKAGE_DEADLINE_SECONDS = 180
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
ALLOWED_SOURCE_HOSTS = {
    "api.elections.kalshi.com",
    "external-api.kalshi.com",
    "docs.kalshi.com",
    "kalshi.com",
    "www.kalshi.com",
    "kalshi-public-docs.s3.amazonaws.com",
    "kalshi-public-docs.s3.us-east-1.amazonaws.com",
}

ROLE_POLICIES = {
    "event_metadata_record": (2 * 1024 * 1024, frozenset({"application/json"}), "json"),
    "market_record": (2 * 1024 * 1024, frozenset({"application/json"}), "json"),
    "series_record_and_contract_document_identity": (
        2 * 1024 * 1024,
        frozenset({"application/json"}),
        "json",
    ),
    "official_fee_rounding_document": (
        4 * 1024 * 1024,
        frozenset({"text/markdown", "text/plain"}),
        "text",
    ),
    "official_fixed_point_document": (
        4 * 1024 * 1024,
        frozenset({"text/markdown", "text/plain"}),
        "text",
    ),
    "official_settlement_document": (
        4 * 1024 * 1024,
        frozenset({"text/markdown", "text/plain"}),
        "text",
    ),
    "official_contract_terms_document": (
        32 * 1024 * 1024,
        frozenset({"application/pdf"}),
        "pdf",
    ),
    "official_certification_document": (
        32 * 1024 * 1024,
        frozenset({"application/pdf"}),
        "pdf",
    ),
}

REFUSAL_CODES = frozenset({
    "AcquisitionCleanupFailed",
    "AcquisitionContentInvalid",
    "AcquisitionHttpStatusRejected",
    "AcquisitionMediaTypeMismatch",
    "AcquisitionPolicyMismatch",
    "AcquisitionPackageTooLarge",
    "AcquisitionRedirectLimit",
    "AcquisitionRedirectRejected",
    "AcquisitionSourceTooLarge",
    "AcquisitionTimeout",
    "AcquisitionTransportFailure",
    "AcquisitionUrlRejected",
    "CaptureOutsideEffectiveWindow",
    "CatalogAmbiguous",
    "CatalogHashMismatch",
    "ComplementaryPriceMismatch",
    "ConversionPolicyMismatch",
    "CorePriceNotRepresentable",
    "CoreQuantityNotRepresentable",
    "EffectiveWindowGap",
    "EffectiveWindowMismatch",
    "EffectiveWindowOverlap",
    "EvidenceAnchorMismatch",
    "EvidenceIncomplete",
    "EvidenceProfileMismatch",
    "EventTickerMismatch",
    "FeePolicyUnsupported",
    "FeeTermsMissing",
    "InvalidPriceRange",
    "InvalidQuantityIncrement",
    "MarketTickerMismatch",
    "PackageMembershipMismatch",
    "PriceOffVenueGrid",
    "QuantityOffVenueIncrement",
    "ReviewHashMismatch",
    "ReviewMissing",
    "ReviewNotApproved",
    "SeriesTickerMismatch",
    "SourceHashMismatch",
    "SourceMissing",
    "SourceTermsMismatch",
    "TermsHashMismatch",
    "TermsNoncanonical",
    "UnsupportedMarketType",
    "UnsupportedPayout",
    "UnsupportedTermsSchema",
    "UpstreamManifestMismatch",
})


class ProductTermsError(ValueError):
    """Stable refusal category plus a human-readable diagnostic."""

    def __init__(self, code: str, message: str) -> None:
        if code not in REFUSAL_CODES:
            raise AssertionError(f"unregistered product-term refusal code: {code}")
        self.code = code
        super().__init__(f"{code}: {message}")


def fail(code: str, message: str) -> None:
    raise ProductTermsError(code, message)


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            separators=(",", ":"),
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        fail("TermsNoncanonical", str(error))


def canonical_json_bytes(value: Any) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as error:
        fail("TermsNoncanonical", f"{path} is not UTF-8: {error}")
    except json.JSONDecodeError as error:
        fail("TermsNoncanonical", f"{path} is not valid JSON: {error}")
    if not isinstance(value, dict):
        fail("TermsNoncanonical", f"{path} must contain a JSON object")
    return value


def require_keys(
    value: dict[str, Any], required: set[str], optional: set[str], context: str
) -> None:
    missing = sorted(required - value.keys())
    unknown = sorted(value.keys() - required - optional)
    if missing:
        fail("TermsNoncanonical", f"{context} is missing {missing}")
    if unknown:
        fail("TermsNoncanonical", f"{context} has unknown fields {unknown}")


def require_string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        fail("TermsNoncanonical", f"{context} must be a non-empty string")
    return value


def require_bool(value: Any, context: str) -> bool:
    if not isinstance(value, bool):
        fail("TermsNoncanonical", f"{context} must be a boolean")
    return value


def require_integer(value: Any, context: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        fail("TermsNoncanonical", f"{context} must be an integer >= {minimum}")
    return value


def require_hash(value: Any, context: str) -> str:
    parsed = require_string(value, context)
    if len(parsed) != SHA256_LENGTH or any(character not in "0123456789abcdef" for character in parsed):
        fail("TermsNoncanonical", f"{context} must be a lowercase SHA-256 digest")
    return parsed


def decimal_value(value: Any, context: str, *, allow_negative: bool = False) -> Decimal:
    if not isinstance(value, str) or not value or value != value.strip():
        fail("TermsNoncanonical", f"{context} must be a canonical decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        fail("TermsNoncanonical", f"{context} is not a decimal: {error}")
    if not parsed.is_finite() or "e" in value.lower() or value.startswith("+"):
        fail("TermsNoncanonical", f"{context} must be a finite plain decimal")
    if not allow_negative and parsed < 0:
        fail("TermsNoncanonical", f"{context} must not be negative")
    if format(parsed, "f") != value:
        fail("TermsNoncanonical", f"{context} is not canonically formatted")
    return parsed


def parse_utc(value: Any, context: str) -> datetime:
    text = require_string(value, context)
    if not text.endswith("Z"):
        fail("TermsNoncanonical", f"{context} must be RFC3339 UTC ending in Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as error:
        fail("TermsNoncanonical", f"{context} is invalid: {error}")
    if parsed.tzinfo != timezone.utc:
        fail("TermsNoncanonical", f"{context} must be UTC")
    return parsed


def format_utc(value: datetime) -> str:
    if value.tzinfo != timezone.utc:
        fail("TermsNoncanonical", "observed acquisition time must be UTC")
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def approved_source_url(value: Any, context: str) -> str:
    url = require_string(value, context)
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError as error:
        fail("AcquisitionUrlRejected", f"{context} has an invalid port: {error}")
    approved_netlocs = ALLOWED_SOURCE_HOSTS | {
        f"{hostname}:443" for hostname in ALLOWED_SOURCE_HOSTS
    }
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_SOURCE_HOSTS
        or parsed.netloc not in approved_netlocs
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        fail("AcquisitionUrlRejected", f"{context} is not an approved first-party HTTPS URL")
    return url


def synthetic_source_url(value: Any, context: str) -> str:
    url = require_string(value, context)
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError as error:
        fail("AcquisitionUrlRejected", f"{context} has an invalid port: {error}")
    if (
        parsed.scheme != "https"
        or parsed.hostname != "synthetic.invalid"
        or parsed.netloc not in {"synthetic.invalid", "synthetic.invalid:443"}
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        fail(
            "AcquisitionUrlRejected",
            f"{context} is not an approved synthetic.invalid HTTPS URL",
        )
    return url


def utc_ns_to_datetime(value: Any, context: str) -> datetime:
    if isinstance(value, bool):
        fail("TermsNoncanonical", f"{context} must be an integer nanosecond timestamp")
    try:
        nanoseconds = int(value)
    except (TypeError, ValueError) as error:
        fail("TermsNoncanonical", f"{context} must be an integer: {error}")
    return datetime.fromtimestamp(nanoseconds / 1_000_000_000, tz=timezone.utc)


def safe_member(root: Path, member: Any, context: str) -> Path:
    name = require_string(member, context)
    candidate = Path(name)
    if candidate.is_absolute() or ".." in candidate.parts or "\\" in name:
        fail("SourceMissing", f"{context} must stay inside the package")
    unresolved = root / candidate
    if unresolved.is_symlink():
        fail("SourceMissing", f"{context} must not be a symlink")
    resolved_root = root.resolve()
    resolved = unresolved.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        fail("SourceMissing", f"{context} escapes the package")
    if not resolved.is_file():
        fail("SourceMissing", f"{context} does not name a regular file")
    return resolved


def validate_envelope(path: Path, schema: str, mismatch_code: str) -> tuple[dict[str, Any], str]:
    document = read_object(path)
    require_keys(document, {"schema", "payload", "payload_sha256"}, set(), str(path))
    if document["schema"] != schema:
        fail("UnsupportedTermsSchema", f"{path} uses {document['schema']!r}, expected {schema}")
    payload = document["payload"]
    if not isinstance(payload, dict):
        fail("TermsNoncanonical", f"{path}.payload must be an object")
    expected = sha256_bytes(canonical_json_bytes(payload))
    declared = require_hash(document["payload_sha256"], f"{path}.payload_sha256")
    if declared != expected:
        fail(mismatch_code, f"{path} payload hash is stale")
    if path.read_bytes() != canonical_json_bytes(document):
        fail("TermsNoncanonical", f"{path} bytes are not canonical JSON")
    return payload, declared


def _historical_acquisition_policy_payload() -> dict[str, Any]:
    return {
        "venue": "kalshi",
        "environment": "production",
        "allowed_hosts": sorted(ALLOWED_SOURCE_HOSTS),
        "allowed_redirect_statuses": sorted(REDIRECT_STATUSES),
        "maximum_redirects": MAX_REDIRECTS,
        "stream_chunk_bytes": STREAM_CHUNK_BYTES,
        "maximum_package_bytes": MAX_PACKAGE_BYTES,
        "connect_timeout_seconds": CONNECT_TIMEOUT_SECONDS,
        "read_timeout_seconds": READ_TIMEOUT_SECONDS,
        "source_deadline_seconds": SOURCE_DEADLINE_SECONDS,
        "package_deadline_seconds": PACKAGE_DEADLINE_SECONDS,
        "role_policies": {
            role: {
                "maximum_bytes": maximum_bytes,
                "media_types": sorted(media_types),
                "content_kind": content_kind,
            }
            for role, (maximum_bytes, media_types, content_kind) in sorted(ROLE_POLICIES.items())
        },
    }


@dataclass(frozen=True)
class AcquisitionPolicy:
    path: Path
    payload: dict[str, Any]
    payload_sha256: str
    file_sha256: str

    @classmethod
    def load(cls, path: Path) -> "AcquisitionPolicy":
        payload, payload_hash = validate_envelope(
            path, ACQUISITION_POLICY_SCHEMA, "AcquisitionPolicyMismatch"
        )
        if payload_hash != SUPPORTED_ACQUISITION_POLICY_SHA256:
            fail(
                "AcquisitionPolicyMismatch",
                "acquisition policy identity is not the frozen supported policy",
            )
        if payload != _historical_acquisition_policy_payload():
            fail(
                "AcquisitionPolicyMismatch",
                "acquisition policy is not the supported immutable Kalshi first-party policy",
            )
        return cls(path, payload, payload_hash, sha256_file(path))


@dataclass(frozen=True)
class EvidenceProfile:
    """Immutable semantic-source membership contract for successor packages."""

    path: Path
    payload: dict[str, Any]
    payload_sha256: str
    file_sha256: str

    @classmethod
    def load(cls, path: Path) -> "EvidenceProfile":
        try:
            return cls._load_unwrapped(path)
        except ProductTermsError as error:
            if error.code == "EvidenceProfileMismatch":
                raise
            fail("EvidenceProfileMismatch", str(error))

    @classmethod
    def _load_unwrapped(cls, path: Path) -> "EvidenceProfile":
        if not path.is_file():
            fail("EvidenceProfileMismatch", f"{path} is missing")
        payload, payload_hash = validate_envelope(
            path, EVIDENCE_PROFILE_SCHEMA, "EvidenceProfileMismatch"
        )
        require_keys(
            payload,
            {"venue", "environment", "profile_id", "observations", "roles", "field_coverage"},
            set(),
            "evidence profile payload",
        )
        if payload["venue"] != "kalshi" or payload["environment"] != "production":
            fail("EvidenceProfileMismatch", "evidence profile venue/environment is unsupported")
        require_string(payload["profile_id"], "evidence profile id")
        if payload["observations"] != ["opening", "closing"]:
            fail("EvidenceProfileMismatch", "evidence profile observations must be opening then closing")
        roles = payload["roles"]
        if not isinstance(roles, list):
            fail("EvidenceProfileMismatch", "evidence profile roles must be an array")
        source_keys: list[str] = []
        role_names: list[str] = []
        for index, item in enumerate(roles):
            context = f"evidence profile roles[{index}]"
            if not isinstance(item, dict):
                fail("EvidenceProfileMismatch", f"{context} must be an object")
            require_keys(
                item,
                {
                    "source_key", "role", "applicability", "reason",
                    "cardinality_per_observation", "media_types", "content_kind",
                    "mutability", "linked_source_keys",
                },
                set(),
                context,
            )
            source_key = require_string(item["source_key"], f"{context}.source_key")
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", source_key) is None:
                fail("EvidenceProfileMismatch", f"{context}.source_key is not portable")
            role = require_string(item["role"], f"{context}.role")
            if role not in ROLE_POLICIES:
                fail("EvidenceProfileMismatch", f"{context}.role is unsupported")
            source_keys.append(source_key)
            role_names.append(role)
            applicability = item["applicability"]
            if applicability not in {"required", "optional", "not_applicable"}:
                fail("EvidenceProfileMismatch", f"{context}.applicability is unsupported")
            reason = item["reason"]
            if applicability == "required":
                if reason is not None:
                    fail("EvidenceProfileMismatch", f"{context}.reason must be null for a required role")
                expected_cardinality = {"minimum": 1, "maximum": 1}
            elif applicability == "optional":
                require_string(reason, f"{context}.reason")
                expected_cardinality = {"minimum": 0, "maximum": 1}
            else:
                require_string(reason, f"{context}.reason")
                expected_cardinality = {"minimum": 0, "maximum": 0}
            if item["cardinality_per_observation"] != expected_cardinality:
                fail("EvidenceProfileMismatch", f"{context} cardinality disagrees with applicability")
            maximum_bytes, allowed_media, content_kind = ROLE_POLICIES[role]
            del maximum_bytes
            media_types = item["media_types"]
            if (
                not isinstance(media_types, list)
                or not media_types
                or media_types != sorted(set(media_types))
                or not set(media_types).issubset(allowed_media)
            ):
                fail("EvidenceProfileMismatch", f"{context}.media_types do not narrow the acquisition policy")
            if item["content_kind"] != content_kind:
                fail("EvidenceProfileMismatch", f"{context}.content_kind disagrees with the role policy")
            expected_mutability = "mutable_endpoint" if content_kind == "json" else "static_document"
            if item["mutability"] != expected_mutability:
                fail("EvidenceProfileMismatch", f"{context}.mutability is inconsistent with its content kind")
            links = item["linked_source_keys"]
            if (
                not isinstance(links, list)
                or links != sorted(set(links))
                or any(not isinstance(link, str) or not link for link in links)
                or source_key in links
            ):
                fail("EvidenceProfileMismatch", f"{context}.linked_source_keys must be sorted, unique, and exclude itself")
        if source_keys != sorted(source_keys) or len(source_keys) != len(set(source_keys)):
            fail("EvidenceProfileMismatch", "profile source keys must be unique and sorted")
        if set(role_names) != set(ROLE_POLICIES) or len(role_names) != len(set(role_names)):
            fail("EvidenceProfileMismatch", "profile must classify every semantic role exactly once")
        known_keys = set(source_keys)
        for item in roles:
            if not set(item["linked_source_keys"]).issubset(known_keys):
                fail("EvidenceProfileMismatch", f"{item['source_key']} links an unknown source key")
        coverage = payload["field_coverage"]
        if not isinstance(coverage, list) or not coverage:
            fail("EvidenceProfileMismatch", "evidence profile field coverage must not be empty")
        coverage_pointers: list[str] = []
        for index, item in enumerate(coverage):
            context = f"evidence profile field_coverage[{index}]"
            if not isinstance(item, dict):
                fail("EvidenceProfileMismatch", f"{context} must be an object")
            require_keys(item, {"term_pointer", "coverage_class"}, set(), context)
            pointer = require_string(item["term_pointer"], f"{context}.term_pointer")
            if not pointer.startswith("/payload/"):
                fail("EvidenceProfileMismatch", f"{context}.term_pointer must begin /payload/")
            if item["coverage_class"] not in {
                "mechanically_projected", "human_reviewed", "derived",
                "repository_local_policy", "unsupported", "not_applicable",
            }:
                fail("EvidenceProfileMismatch", f"{context}.coverage_class is unsupported")
            coverage_pointers.append(pointer)
        if coverage_pointers != sorted(coverage_pointers) or len(coverage_pointers) != len(set(coverage_pointers)):
            fail("EvidenceProfileMismatch", "field coverage pointers must be unique and sorted")
        return cls(path, payload, payload_hash, sha256_file(path))

    def verify_sources(self, sources: list[dict[str, Any]], observations: list[str]) -> None:
        role_by_key = {item["source_key"]: item for item in self.payload["roles"]}
        counts = {(observation, key): 0 for observation in observations for key in role_by_key}
        present = {(observation, key): False for observation in observations for key in role_by_key}
        for source in sources:
            observation = source["observation_id"]
            source_key = require_string(source.get("source_key"), "source source_key")
            profile_role = role_by_key.get(source_key)
            if profile_role is None:
                fail("EvidenceIncomplete", f"source key {source_key!r} is not declared by the evidence profile")
            if source["id"] != f"{observation}_{source_key}":
                fail("EvidenceIncomplete", f"source {source['id']!r} does not use its observation/source-key identity")
            if source["role"] != profile_role["role"]:
                fail("EvidenceIncomplete", f"source {source['id']!r} has the wrong semantic role")
            if source["media_type"] not in profile_role["media_types"]:
                fail("AcquisitionMediaTypeMismatch", f"source {source['id']!r} has media outside its evidence profile")
            counts[(observation, source_key)] += 1
            present[(observation, source_key)] = True
        for observation in observations:
            for source_key, role in role_by_key.items():
                count = counts[(observation, source_key)]
                expected = role["cardinality_per_observation"]
                if not expected["minimum"] <= count <= expected["maximum"]:
                    fail("EvidenceIncomplete", f"{observation}/{source_key} cardinality is {count}, expected {expected}")
                if count:
                    for linked_key in role["linked_source_keys"]:
                        if not present[(observation, linked_key)]:
                            fail("EvidenceIncomplete", f"{observation}/{source_key} is missing linked source {linked_key}")
        if observations == ["opening", "closing"]:
            for source_key, role in role_by_key.items():
                if role["applicability"] == "optional" and (
                    present[("opening", source_key)] != present[("closing", source_key)]
                ):
                    fail("EvidenceIncomplete", f"optional source {source_key} is asymmetric across observations")

    def verify_spec_sources(self, sources: Any) -> None:
        if not isinstance(sources, list):
            fail("EvidenceIncomplete", "acquisition spec sources must be an array")
        role_by_key = {item["source_key"]: item for item in self.payload["roles"]}
        seen: set[str] = set()
        for index, source in enumerate(sources):
            if not isinstance(source, dict):
                fail("EvidenceIncomplete", f"acquisition spec source {index} must be an object")
            source_key = source.get("id")
            if not isinstance(source_key, str) or source_key not in role_by_key or source_key in seen:
                fail("EvidenceIncomplete", f"acquisition spec source {index} has an unknown or duplicate source key")
            seen.add(source_key)
            profile_role = role_by_key[source_key]
            if source.get("role") != profile_role["role"]:
                fail("EvidenceIncomplete", f"acquisition spec source {source_key} has the wrong role")
            requested_media = source.get("media_types", profile_role["media_types"])
            if (
                not isinstance(requested_media, list)
                or not requested_media
                or not set(requested_media).issubset(profile_role["media_types"])
            ):
                fail("AcquisitionMediaTypeMismatch", f"acquisition spec source {source_key} has media outside its profile")
        for source_key, role in role_by_key.items():
            present = source_key in seen
            if role["applicability"] == "required" and not present:
                fail("EvidenceIncomplete", f"acquisition spec is missing required source {source_key}")
            if role["applicability"] == "not_applicable" and present:
                fail("EvidenceIncomplete", f"acquisition spec includes not-applicable source {source_key}")


def _validate_acquisition_summary(value: Any) -> None:
    if not isinstance(value, dict):
        fail("TermsNoncanonical", "source acquisition summary must be an object")
    require_keys(
        value,
        {"started_at_utc", "completed_at_utc", "tool_name", "tool_version"},
        {"observation_id"},
        "source acquisition",
    )
    started = parse_utc(value["started_at_utc"], "source acquisition.started_at_utc")
    completed = parse_utc(value["completed_at_utc"], "source acquisition.completed_at_utc")
    if completed < started:
        fail("TermsNoncanonical", "source acquisition completion precedes its start")
    if value["tool_name"] != ACQUISITION_TOOL_NAME:
        fail("TermsNoncanonical", "source acquisition tool name is unsupported")
    require_string(value["tool_version"], "source acquisition.tool_version")


def _validate_acquired_source_metadata(
    source: dict[str, Any], context: str, role: str, truth_category: str = "Observed"
) -> None:
    if role not in ROLE_POLICIES:
        fail("TermsNoncanonical", f"{context}.role is unsupported")
    url_validator = synthetic_source_url if truth_category == "Synthetic" else approved_source_url
    requested_url = url_validator(source["requested_url"], f"{context}.requested_url")
    final_url = url_validator(source["final_url"], f"{context}.final_url")
    redirects = source["redirect_history"]
    if not isinstance(redirects, list) or len(redirects) > MAX_REDIRECTS:
        fail("TermsNoncanonical", f"{context}.redirect_history is invalid")
    current_url = requested_url
    for index, redirect in enumerate(redirects):
        redirect_context = f"{context}.redirect_history[{index}]"
        if not isinstance(redirect, dict):
            fail("TermsNoncanonical", f"{redirect_context} must be an object")
        require_keys(
            redirect,
            {"status_code", "location", "resolved_url"},
            set(),
            redirect_context,
        )
        if require_integer(redirect["status_code"], f"{redirect_context}.status_code") not in REDIRECT_STATUSES:
            fail("TermsNoncanonical", f"{redirect_context}.status_code is not a supported redirect")
        require_string(redirect["location"], f"{redirect_context}.location")
        resolved_url = url_validator(
            redirect["resolved_url"], f"{redirect_context}.resolved_url"
        )
        if urljoin(current_url, redirect["location"]) != resolved_url:
            fail("TermsNoncanonical", f"{redirect_context} does not resolve from the prior URL")
        current_url = resolved_url
    if final_url != current_url:
        fail("TermsNoncanonical", f"{context}.final_url does not match the redirect chain")
    status = require_integer(source["http_status"], f"{context}.http_status")
    if status < 200 or status >= 300:
        fail("TermsNoncanonical", f"{context}.http_status is not successful")
    started = parse_utc(source["retrieval_started_at_utc"], f"{context}.retrieval_started_at_utc")
    completed = parse_utc(source["retrieval_completed_at_utc"], f"{context}.retrieval_completed_at_utc")
    if completed < started:
        fail("TermsNoncanonical", f"{context} retrieval completion precedes its start")
    require_integer(source["elapsed_milliseconds"], f"{context}.elapsed_milliseconds")
    if source["tool_name"] != ACQUISITION_TOOL_NAME:
        fail("TermsNoncanonical", f"{context}.tool_name is unsupported")
    require_string(source["tool_version"], f"{context}.tool_version")
    headers = source["response_headers"]
    if not isinstance(headers, dict):
        fail("TermsNoncanonical", f"{context}.response_headers must be an object")
    require_keys(
        headers,
        {"content_type", "content_length", "etag", "last_modified", "date"},
        set(),
        f"{context}.response_headers",
    )
    for name, header in headers.items():
        if header is not None:
            require_string(header, f"{context}.response_headers.{name}")
    maximum_bytes, media_types, _ = ROLE_POLICIES[role]
    media_type = require_string(source["media_type"], f"{context}.media_type")
    if media_type not in media_types:
        fail("TermsNoncanonical", f"{context}.media_type is not permitted for {role}")
    if require_integer(source["byte_length"], f"{context}.byte_length") > maximum_bytes:
        fail("TermsNoncanonical", f"{context}.byte_length exceeds the role policy")


@dataclass(frozen=True)
class SourceEvidence:
    payload: dict[str, Any]
    payload_sha256: str
    file_sha256: str
    source_hashes: dict[str, str]
    schema: str
    acquisition_policy: AcquisitionPolicy | None
    evidence_profile: EvidenceProfile | None
    truth_category: str

    @classmethod
    def load(cls, package: Path) -> "SourceEvidence":
        path = package / "source_manifest.json"
        if not path.is_file():
            fail("SourceMissing", f"{path} is missing")
        document = read_object(path)
        schema = document.get("schema")
        if schema not in {
            SOURCE_MANIFEST_SCHEMA,
            SOURCE_MANIFEST_V2_SCHEMA,
            SOURCE_MANIFEST_V3_SCHEMA,
            SOURCE_MANIFEST_V4_SCHEMA,
        }:
            fail("UnsupportedTermsSchema", f"{path} uses unsupported source schema {schema!r}")
        payload, payload_hash = validate_envelope(path, schema, "SourceHashMismatch")
        if schema == SOURCE_MANIFEST_SCHEMA:
            require_keys(
                payload,
                {"venue", "environment", "retrieved_at_utc", "sources"},
                set(),
                "source payload",
            )
            parse_utc(payload["retrieved_at_utc"], "source.retrieved_at_utc")
        elif schema == SOURCE_MANIFEST_V2_SCHEMA:
            require_keys(
                payload,
                {"venue", "environment", "acquisition", "sources"},
                set(),
                "source payload",
            )
            _validate_acquisition_summary(payload["acquisition"])
        elif schema == SOURCE_MANIFEST_V3_SCHEMA:
            require_keys(
                payload,
                {
                    "venue",
                    "environment",
                    "acquisition_policy_sha256",
                    "acquisitions",
                    "sources",
                },
                set(),
                "source payload",
            )
        else:
            require_keys(
                payload,
                {
                    "venue", "environment", "acquisition_policy_sha256",
                    "evidence_profile_sha256", "acquisitions", "sources",
                },
                {"truth_category"},
                "source payload",
            )
        truth_category = payload.get("truth_category", "Observed")
        if truth_category not in {"Observed", "Synthetic"}:
            fail("TermsNoncanonical", "source truth_category must be Observed or Synthetic")
        if payload["venue"] != "kalshi" or payload["environment"] != "production":
            fail("TermsNoncanonical", "source venue/environment must be kalshi/production")
        sources = payload["sources"]
        if not isinstance(sources, list) or not sources:
            fail("SourceMissing", "source payload must list retained sources")
        identities: list[str] = []
        hashes: dict[str, str] = {}
        for index, source in enumerate(sources):
            context = f"source.sources[{index}]"
            if not isinstance(source, dict):
                fail("TermsNoncanonical", f"{context} must be an object")
            if schema == SOURCE_MANIFEST_SCHEMA:
                require_keys(
                    source,
                    {"id", "role", "url", "retrieved_at_utc", "media_type", "path", "byte_length", "sha256"},
                    {"content_encoding", "venue_updated_at"},
                    context,
                )
            else:
                required = {
                    "id", "role", "requested_url", "final_url", "redirect_history",
                    "http_status", "media_type", "retrieval_started_at_utc",
                    "retrieval_completed_at_utc", "elapsed_milliseconds", "path",
                    "byte_length", "sha256", "tool_name", "tool_version",
                    "response_headers",
                }
                if schema in {SOURCE_MANIFEST_V3_SCHEMA, SOURCE_MANIFEST_V4_SCHEMA}:
                    required.add("observation_id")
                if schema == SOURCE_MANIFEST_V4_SCHEMA:
                    required.add("source_key")
                require_keys(
                    source,
                    required,
                    {"venue_updated_at"},
                    context,
                )
            identity = require_string(source["id"], f"{context}.id")
            identities.append(identity)
            role = require_string(source["role"], f"{context}.role")
            if schema == SOURCE_MANIFEST_SCHEMA:
                try:
                    approved_source_url(source["url"], f"{context}.url")
                except ProductTermsError as error:
                    fail("SourceMissing", str(error))
                parse_utc(source["retrieved_at_utc"], f"{context}.retrieved_at_utc")
            else:
                _validate_acquired_source_metadata(
                    source, context, role, truth_category
                )
            require_string(source["media_type"], f"{context}.media_type")
            if source.get("venue_updated_at") is not None:
                parse_utc(source["venue_updated_at"], f"{context}.venue_updated_at")
            path_value = safe_member(package, source["path"], f"{context}.path")
            raw = path_value.read_bytes()
            if schema == SOURCE_MANIFEST_SCHEMA and source.get("content_encoding") == "base64":
                try:
                    raw = base64.b64decode(raw, validate=True)
                except ValueError as error:
                    fail("SourceHashMismatch", f"{context} has invalid base64: {error}")
            elif schema == SOURCE_MANIFEST_SCHEMA and source.get("content_encoding") not in {None, "identity"}:
                fail("TermsNoncanonical", f"{context}.content_encoding is unsupported")
            if require_integer(source["byte_length"], f"{context}.byte_length") != len(raw):
                fail("SourceHashMismatch", f"{context} byte length is stale")
            expected = require_hash(source["sha256"], f"{context}.sha256")
            if sha256_bytes(raw) != expected:
                fail("SourceHashMismatch", f"{context} content hash is stale")
            hashes[identity] = expected
        if identities != sorted(identities) or len(identities) != len(set(identities)):
            fail("TermsNoncanonical", "source identifiers must be unique and sorted")
        acquisition_policy: AcquisitionPolicy | None = None
        if schema == SOURCE_MANIFEST_V2_SCHEMA:
            acquisition = payload["acquisition"]
            acquisition_started = parse_utc(
                acquisition["started_at_utc"], "source acquisition.started_at_utc"
            )
            acquisition_completed = parse_utc(
                acquisition["completed_at_utc"], "source acquisition.completed_at_utc"
            )
            total_bytes = 0
            for index, source in enumerate(sources):
                source_started = parse_utc(
                    source["retrieval_started_at_utc"],
                    f"source.sources[{index}].retrieval_started_at_utc",
                )
                source_completed = parse_utc(
                    source["retrieval_completed_at_utc"],
                    f"source.sources[{index}].retrieval_completed_at_utc",
                )
                if source_started < acquisition_started or source_completed > acquisition_completed:
                    fail("TermsNoncanonical", "source retrieval lies outside package acquisition time")
                if source["tool_version"] != acquisition["tool_version"]:
                    fail("TermsNoncanonical", "source and package acquisition tool versions differ")
                total_bytes += source["byte_length"]
            if total_bytes > MAX_PACKAGE_BYTES:
                fail("TermsNoncanonical", "retained package exceeds its byte limit")
        elif schema in {SOURCE_MANIFEST_V3_SCHEMA, SOURCE_MANIFEST_V4_SCHEMA}:
            acquisition_policy = AcquisitionPolicy.load(package / "acquisition_policy.json")
            if acquisition_policy.payload_sha256 != require_hash(
                payload["acquisition_policy_sha256"], "source acquisition policy hash"
            ):
                fail("AcquisitionPolicyMismatch", "source manifest names a different policy")
            acquisitions = payload["acquisitions"]
            if not isinstance(acquisitions, list) or not acquisitions:
                fail("EvidenceIncomplete", "source manifest has no acquisitions")
            observation_ids: list[str] = []
            acquisition_by_id: dict[str, tuple[datetime, datetime]] = {}
            for acquisition in acquisitions:
                _validate_acquisition_summary(acquisition)
                observation_id = require_string(
                    acquisition.get("observation_id"), "source acquisition observation_id"
                )
                if observation_id not in {"opening", "closing"}:
                    fail("EvidenceIncomplete", "acquisition observation must be opening or closing")
                expected_tool_version = (
                    ACQUISITION_TOOL_V4_VERSION
                    if schema == SOURCE_MANIFEST_V4_SCHEMA
                    else ACQUISITION_TOOL_V3_VERSION
                )
                if acquisition["tool_version"] != expected_tool_version:
                    fail("AcquisitionPolicyMismatch", f"{schema} acquisition tool version is unsupported")
                observation_ids.append(observation_id)
                acquisition_by_id[observation_id] = (
                    parse_utc(acquisition["started_at_utc"], "acquisition start"),
                    parse_utc(acquisition["completed_at_utc"], "acquisition completion"),
                )
            valid_observations = (
                observation_ids in (["opening"], ["closing"])
                if len(acquisitions) == 1
                else observation_ids == ["opening", "closing"]
            )
            if not valid_observations or len(set(observation_ids)) != len(observation_ids):
                fail("EvidenceIncomplete", "acquisitions must be ordered opening then closing")
            total_bytes = 0
            for index, source in enumerate(sources):
                observation_id = require_string(
                    source.get("observation_id"),
                    f"source.sources[{index}].observation_id",
                )
                if observation_id not in acquisition_by_id:
                    fail("EvidenceIncomplete", "source names an unknown observation")
                started, completed = acquisition_by_id[observation_id]
                source_started = parse_utc(
                    source["retrieval_started_at_utc"],
                    f"source.sources[{index}].retrieval_started_at_utc",
                )
                source_completed = parse_utc(
                    source["retrieval_completed_at_utc"],
                    f"source.sources[{index}].retrieval_completed_at_utc",
                )
                if source_started < started or source_completed > completed:
                    fail("TermsNoncanonical", "source retrieval lies outside its acquisition")
                expected_tool_version = (
                    ACQUISITION_TOOL_V4_VERSION
                    if schema == SOURCE_MANIFEST_V4_SCHEMA
                    else ACQUISITION_TOOL_V3_VERSION
                )
                if source["tool_version"] != expected_tool_version:
                    fail("AcquisitionPolicyMismatch", "source tool version differs from its manifest version")
                total_bytes += source["byte_length"]
            if total_bytes > acquisition_policy.payload["maximum_package_bytes"]:
                fail("TermsNoncanonical", "retained package exceeds its policy byte limit")
        evidence_profile: EvidenceProfile | None = None
        if schema == SOURCE_MANIFEST_V4_SCHEMA:
            evidence_profile = EvidenceProfile.load(package / "evidence_profile.json")
            if evidence_profile.payload_sha256 != require_hash(
                payload["evidence_profile_sha256"], "source evidence profile hash"
            ):
                fail("EvidenceProfileMismatch", "source manifest names a different evidence profile")
            evidence_profile.verify_sources(sources, [item["observation_id"] for item in payload["acquisitions"]])
            source_by_observation_key = {
                (source["observation_id"], source["source_key"]): source for source in sources
            }
            for role in evidence_profile.payload["roles"]:
                if role["mutability"] != "static_document":
                    continue
                opening = source_by_observation_key.get(("opening", role["source_key"]))
                closing = source_by_observation_key.get(("closing", role["source_key"]))
                if opening is not None and closing is not None and opening["sha256"] != closing["sha256"]:
                    fail("EvidenceAnchorMismatch", f"static source {role['source_key']} changed across observations")
        return cls(
            payload,
            payload_hash,
            sha256_file(path),
            hashes,
            schema,
            acquisition_policy,
            evidence_profile,
            truth_category,
        )


@dataclass(frozen=True)
class ProductTerms:
    payload: dict[str, Any]
    payload_sha256: str
    file_sha256: str

    @property
    def identity(self) -> dict[str, Any]:
        return self.payload["identity"]

    @property
    def market_ticker(self) -> str:
        return self.identity["market_ticker"]

    @classmethod
    def load(cls, package: Path, evidence: SourceEvidence) -> "ProductTerms":
        path = package / "product_terms.json"
        if not path.is_file():
            fail("SourceMissing", f"{path} is missing")
        document = read_object(path)
        schema = document.get("schema")
        if schema not in {PRODUCT_TERMS_SCHEMA, PRODUCT_TERMS_V2_SCHEMA}:
            fail("UnsupportedTermsSchema", f"{path} uses unsupported terms schema {schema!r}")
        payload, payload_hash = validate_envelope(path, schema, "TermsHashMismatch")
        _validate_terms_payload(payload, evidence, schema)
        _validate_terms_against_retained_sources(package, payload, evidence)
        return cls(payload, payload_hash, sha256_file(path))

    def validate_price(self, value: Any, context: str) -> Decimal:
        price = decimal_value(str(value), context)
        ranges = self.payload["price"]["ranges"]
        for item in ranges:
            start = Decimal(item["start_dollars"])
            end = Decimal(item["end_dollars"])
            above_start = price >= start if item["start_inclusive"] else price > start
            below_end = price <= end if item["end_inclusive"] else price < end
            if above_start and below_end and (price - start) % Decimal(item["step_dollars"]) == 0:
                return price
        fail("PriceOffVenueGrid", f"{context}={value!r} is not on the declared venue grid")

    def validate_quantity(self, value: Any, context: str, *, allow_negative: bool = False) -> Decimal:
        quantity = decimal_value(str(value), context, allow_negative=allow_negative)
        increment = Decimal(self.payload["quantity"]["increment_contracts"])
        if quantity % increment != 0:
            fail("QuantityOffVenueIncrement", f"{context}={value!r} is not divisible by {increment}")
        return quantity


def _validate_terms_payload(
    payload: dict[str, Any], evidence: SourceEvidence, schema: str = PRODUCT_TERMS_SCHEMA
) -> None:
    require_keys(
        payload,
        {"venue", "environment", "revision_label", "effective", "identity", "price", "quantity", "payout", "rules", "lifecycle", "settlement", "fees", "source_refs"},
        set(),
        "product terms payload",
    )
    if payload["venue"] != "kalshi" or payload["environment"] != "production":
        fail("TermsNoncanonical", "terms venue/environment must be kalshi/production")
    require_string(payload["revision_label"], "terms.revision_label")
    effective = payload["effective"]
    if not isinstance(effective, dict):
        fail("TermsNoncanonical", "terms.effective must be an object")
    require_keys(effective, {"from_utc", "until_utc", "basis"}, set(), "terms.effective")
    start = parse_utc(effective["from_utc"], "terms.effective.from_utc")
    end = None if effective["until_utc"] is None else parse_utc(effective["until_utc"], "terms.effective.until_utc")
    if end is not None and end <= start:
        fail("TermsNoncanonical", "terms effective interval is empty")
    if effective["basis"] not in {"venue_explicit", "source_revision_timestamp", "contemporaneous_snapshot", "reviewed_retrospective"}:
        fail("EffectiveWindowGap", "terms effective basis is unsupported or unknown")
    identity = payload["identity"]
    if not isinstance(identity, dict):
        fail("TermsNoncanonical", "terms.identity must be an object")
    require_keys(identity, {"series_ticker", "event_ticker", "market_ticker", "market_type", "title", "yes_sub_title", "no_sub_title", "contracts"}, set(), "terms.identity")
    for name in ("series_ticker", "event_ticker", "market_ticker", "title", "yes_sub_title", "no_sub_title"):
        require_string(identity[name], f"terms.identity.{name}")
    if identity["market_type"] != "binary":
        fail("UnsupportedMarketType", f"{identity['market_type']!r} is not supported")
    contracts = identity["contracts"]
    if not isinstance(contracts, list) or [item.get("side") for item in contracts if isinstance(item, dict)] != ["no", "yes"]:
        fail("TermsNoncanonical", "terms contracts must be ordered no, yes")
    for item in contracts:
        require_keys(item, {"side", "contract_id", "label"}, set(), "terms contract")
        require_string(item["contract_id"], "terms contract id")
        require_string(item["label"], "terms contract label")
    _validate_price_terms(payload["price"])
    _validate_quantity_terms(payload["quantity"])
    _validate_payout_terms(payload["payout"])
    _validate_rules_lifecycle_settlement_fees(
        payload, allow_empty_secondary=schema == PRODUCT_TERMS_V2_SCHEMA
    )
    refs = payload["source_refs"]
    if (
        not isinstance(refs, list)
        or any(not isinstance(reference, str) or not reference for reference in refs)
        or refs != sorted(refs)
        or len(refs) != len(set(refs))
    ):
        fail("TermsNoncanonical", "terms.source_refs must be a sorted unique list")
    if not refs or any(reference not in evidence.source_hashes for reference in refs):
        fail("SourceMissing", "terms reference missing retained source evidence")
    direct_refs = {
        payload["rules"]["contract_terms_source"],
        payload["settlement"]["rules_source"],
        payload["fees"]["schedule_source"],
        payload["fees"]["rounding_source"],
    }
    if any(reference not in evidence.source_hashes for reference in direct_refs):
        fail("SourceMissing", "a direct terms source reference is not retained")
    if not direct_refs.issubset(set(refs)):
        fail("SourceMissing", "direct terms source references must appear in source_refs")


def _retained_json(package: Path, evidence: SourceEvidence, source_id: str) -> dict[str, Any]:
    source = next(
        (item for item in evidence.payload["sources"] if item["id"] == source_id),
        None,
    )
    if source is None or source["media_type"] != "application/json":
        fail("SourceMissing", f"required retained JSON source {source_id!r} is missing")
    return read_object(safe_member(package, source["path"], f"source {source_id}.path"))


def _require_source_equal(actual: Any, expected: Any, field: str) -> None:
    if actual != expected:
        fail("SourceTermsMismatch", f"reviewed terms {field} differs from retained source evidence")


def _validate_terms_against_retained_sources(
    package: Path, payload: dict[str, Any], evidence: SourceEvidence
) -> None:
    """Bind the reviewed projection to independently retained venue records.

    Markdown sources establish general venue semantics but are intentionally not
    scraped here. Market-specific values must match the retained API objects
    exactly; changing either side therefore requires a new review revision.
    """

    observations = [None]
    if evidence.schema in {SOURCE_MANIFEST_V3_SCHEMA, SOURCE_MANIFEST_V4_SCHEMA}:
        observations = ["opening", "closing"]
    profile_keys_by_role: dict[str, str] = {}
    if evidence.evidence_profile is not None:
        profile_keys_by_role = {
            item["role"]: item["source_key"] for item in evidence.evidence_profile.payload["roles"]
        }
    for observation in observations:
        prefix = "" if observation is None else f"{observation}_"
        market_key = profile_keys_by_role.get("market_record", "market_record")
        series_key = profile_keys_by_role.get(
            "series_record_and_contract_document_identity", "series_record"
        )
        metadata_key = profile_keys_by_role.get("event_metadata_record", "event_metadata")
        market_document = _retained_json(package, evidence, f"{prefix}{market_key}")
        series_document = _retained_json(package, evidence, f"{prefix}{series_key}")
        metadata = _retained_json(package, evidence, f"{prefix}{metadata_key}")
        market = market_document.get("market")
        series = series_document.get("series")
        if not isinstance(market, dict) or not isinstance(series, dict):
            fail(
                "SourceTermsMismatch",
                "retained market or series response has an unexpected shape",
            )

        identity = payload["identity"]
        identity_fields = {
            "market_ticker": "ticker",
            "event_ticker": "event_ticker",
            "market_type": "market_type",
            "title": "title",
            "yes_sub_title": "yes_sub_title",
            "no_sub_title": "no_sub_title",
        }
        for term_field, source_field in identity_fields.items():
            _require_source_equal(
                identity[term_field],
                market.get(source_field),
                f"{observation or 'single'}.identity.{term_field}",
            )
        _require_source_equal(
            identity["series_ticker"],
            series.get("ticker"),
            f"{observation or 'single'}.identity.series_ticker",
        )

        price = payload["price"]
        _require_source_equal(
            price["level_structure"],
            market.get("price_level_structure"),
            f"{observation or 'single'}.price.level_structure",
        )
        projected_ranges = [
            {
                "start": item["start_dollars"],
                "end": item["end_dollars"],
                "step": item["step_dollars"],
            }
            for item in price["ranges"]
        ]
        _require_source_equal(
            projected_ranges,
            market.get("price_ranges"),
            f"{observation or 'single'}.price.ranges",
        )
        _require_source_equal(
            payload["payout"]["notional_value_dollars"],
            market.get("notional_value_dollars"),
            f"{observation or 'single'}.payout.notional_value_dollars",
        )
        _require_source_equal(
            payload["rules"]["primary"],
            market.get("rules_primary"),
            f"{observation or 'single'}.rules.primary",
        )
        _require_source_equal(
            payload["rules"]["secondary"],
            market.get("rules_secondary"),
            f"{observation or 'single'}.rules.secondary",
        )
        lifecycle_fields = {
            "open_time": "open_time",
            "close_time": "close_time",
            "expected_expiration_time": "expected_expiration_time",
            "latest_expiration_time": "latest_expiration_time",
            "can_close_early": "can_close_early",
            "early_close_condition": "early_close_condition",
            "settlement_timer_seconds": "settlement_timer_seconds",
        }
        for term_field, source_field in lifecycle_fields.items():
            _require_source_equal(
                payload["lifecycle"][term_field],
                market.get(source_field),
                f"{observation or 'single'}.lifecycle.{term_field}",
            )
        _require_source_equal(
            payload["settlement"]["sources"],
            metadata.get("settlement_sources"),
            f"{observation or 'single'}.settlement.sources",
        )
        _require_source_equal(
            payload["settlement"]["sources"],
            series.get("settlement_sources"),
            f"{observation or 'single'}.series.settlement_sources",
        )
        _require_source_equal(
            payload["fees"]["series_fee_type"],
            series.get("fee_type"),
            f"{observation or 'single'}.fees.series_fee_type",
        )
        try:
            source_multiplier = Decimal(str(series.get("fee_multiplier")))
        except InvalidOperation:
            fail("SourceTermsMismatch", "retained series fee multiplier is invalid")
        if Decimal(payload["fees"]["series_fee_multiplier"]) != source_multiplier:
            fail(
                "SourceTermsMismatch",
                f"{observation or 'single'} series fee multiplier differs from terms",
            )


def _validate_price_terms(price: Any) -> None:
    if not isinstance(price, dict):
        fail("InvalidPriceRange", "terms.price must be an object")
    require_keys(price, {"representation", "maximum_decimal_places", "level_structure", "ranges"}, set(), "terms.price")
    if price["representation"] != "fixed_point_dollars":
        fail("InvalidPriceRange", "price representation is unsupported")
    require_integer(price["maximum_decimal_places"], "terms.price.maximum_decimal_places", minimum=1)
    require_string(price["level_structure"], "terms.price.level_structure")
    ranges = price["ranges"]
    if not isinstance(ranges, list) or not ranges:
        fail("InvalidPriceRange", "price ranges must be a non-empty list")
    prior_end: Decimal | None = None
    for index, item in enumerate(ranges):
        if not isinstance(item, dict):
            fail("InvalidPriceRange", f"price range {index} must be an object")
        require_keys(item, {"start_dollars", "end_dollars", "step_dollars", "start_inclusive", "end_inclusive"}, set(), f"price range {index}")
        start = decimal_value(item["start_dollars"], f"price range {index}.start")
        end = decimal_value(item["end_dollars"], f"price range {index}.end")
        step = decimal_value(item["step_dollars"], f"price range {index}.step")
        require_bool(item["start_inclusive"], f"price range {index}.start_inclusive")
        require_bool(item["end_inclusive"], f"price range {index}.end_inclusive")
        if start < 0 or end > 1 or end < start or step <= 0 or (end - start) % step != 0:
            fail("InvalidPriceRange", f"price range {index} has invalid bounds or step")
        if prior_end is not None and start != prior_end:
            fail("InvalidPriceRange", f"price range {index} is not contiguous")
        prior_end = end
    if Decimal(ranges[0]["start_dollars"]) != 0 or prior_end != 1:
        fail("InvalidPriceRange", "price ranges must cover 0 through 1")


def _validate_quantity_terms(quantity: Any) -> None:
    if not isinstance(quantity, dict):
        fail("InvalidQuantityIncrement", "terms.quantity must be an object")
    require_keys(quantity, {"unit", "representation", "maximum_decimal_places", "increment_contracts"}, set(), "terms.quantity")
    if quantity["unit"] != "contract" or quantity["representation"] != "fixed_point_contracts":
        fail("InvalidQuantityIncrement", "quantity unit or representation is unsupported")
    require_integer(quantity["maximum_decimal_places"], "terms.quantity.maximum_decimal_places", minimum=1)
    if decimal_value(quantity["increment_contracts"], "terms.quantity.increment_contracts") <= 0:
        fail("InvalidQuantityIncrement", "quantity increment must be positive")


def _validate_payout_terms(payout: Any) -> None:
    if not isinstance(payout, dict):
        fail("UnsupportedPayout", "terms.payout must be an object")
    require_keys(payout, {"notional_value_dollars", "ordinary_yes_value_dollars", "ordinary_no_value_dollars", "settlement_value_min_dollars", "settlement_value_max_dollars", "contingent_nonbinary_value_possible"}, set(), "terms.payout")
    values = {name: decimal_value(payout[name], f"terms.payout.{name}") for name in ("notional_value_dollars", "ordinary_yes_value_dollars", "ordinary_no_value_dollars", "settlement_value_min_dollars", "settlement_value_max_dollars")}
    require_bool(payout["contingent_nonbinary_value_possible"], "terms.payout.contingent_nonbinary_value_possible")
    if values["notional_value_dollars"] != 1 or values["ordinary_yes_value_dollars"] != 1 or values["ordinary_no_value_dollars"] != 1 or values["settlement_value_min_dollars"] != 0 or values["settlement_value_max_dollars"] != 1:
        fail("UnsupportedPayout", "B1a supports only one-dollar binary payout bounds")


def _validate_rules_lifecycle_settlement_fees(
    payload: dict[str, Any], *, allow_empty_secondary: bool = False
) -> None:
    rules = payload["rules"]
    if not isinstance(rules, dict):
        fail("TermsNoncanonical", "terms.rules must be an object")
    require_keys(rules, {"primary", "secondary", "contract_terms_source"}, set(), "terms.rules")
    require_string(rules["primary"], "terms.rules.primary")
    if allow_empty_secondary and rules["secondary"] == "":
        pass
    else:
        require_string(rules["secondary"], "terms.rules.secondary")
    require_string(rules["contract_terms_source"], "terms.rules.contract_terms_source")
    lifecycle = payload["lifecycle"]
    if not isinstance(lifecycle, dict):
        fail("TermsNoncanonical", "terms.lifecycle must be an object")
    require_keys(lifecycle, {"open_time", "close_time", "expected_expiration_time", "latest_expiration_time", "can_close_early", "early_close_condition", "settlement_timer_seconds"}, set(), "terms.lifecycle")
    open_time = parse_utc(lifecycle["open_time"], "terms.lifecycle.open_time")
    close_time = parse_utc(lifecycle["close_time"], "terms.lifecycle.close_time")
    expected = parse_utc(lifecycle["expected_expiration_time"], "terms.lifecycle.expected_expiration_time")
    latest = parse_utc(lifecycle["latest_expiration_time"], "terms.lifecycle.latest_expiration_time")
    if not open_time <= close_time <= latest or expected > latest:
        fail("TermsNoncanonical", "lifecycle times are inconsistent")
    require_bool(lifecycle["can_close_early"], "terms.lifecycle.can_close_early")
    if lifecycle["early_close_condition"] is not None:
        require_string(lifecycle["early_close_condition"], "terms.lifecycle.early_close_condition")
    require_integer(lifecycle["settlement_timer_seconds"], "terms.lifecycle.settlement_timer_seconds")
    settlement = payload["settlement"]
    if not isinstance(settlement, dict):
        fail("TermsNoncanonical", "terms.settlement must be an object")
    require_keys(settlement, {"sources", "rules_source", "implementation_status"}, set(), "terms.settlement")
    sources = settlement["sources"]
    if not isinstance(sources, list) or not sources:
        fail("SourceMissing", "settlement sources are required")
    for source in sources:
        require_keys(source, {"name", "url"}, set(), "settlement source")
        require_string(source["name"], "settlement source name")
        require_string(source["url"], "settlement source url")
    require_string(settlement["rules_source"], "terms.settlement.rules_source")
    if settlement["implementation_status"] != "unsupported_not_applied":
        fail("UnsupportedPayout", "settlement implementation must remain unsupported_not_applied")
    fees = payload["fees"]
    if not isinstance(fees, dict):
        fail("FeeTermsMissing", "terms.fees must be an object")
    require_keys(fees, {"series_fee_type", "series_fee_multiplier", "maker_fee_status", "waiver_status", "schedule_source", "rounding_source", "implementation_status"}, set(), "terms.fees")
    require_string(fees["series_fee_type"], "terms.fees.series_fee_type")
    decimal_value(fees["series_fee_multiplier"], "terms.fees.series_fee_multiplier")
    require_string(fees["maker_fee_status"], "terms.fees.maker_fee_status")
    require_string(fees["waiver_status"], "terms.fees.waiver_status")
    require_string(fees["schedule_source"], "terms.fees.schedule_source")
    require_string(fees["rounding_source"], "terms.fees.rounding_source")
    if fees["implementation_status"] != "unsupported_not_applied":
        fail("FeePolicyUnsupported", "fees must remain unsupported_not_applied")


def _json_pointer(value: Any, pointer: Any, context: str) -> Any:
    text = require_string(pointer, context)
    if text == "":
        return value
    if not text.startswith("/"):
        fail("EvidenceAnchorMismatch", f"{context} must be an RFC 6901 JSON pointer")
    current = value
    for raw_part in text[1:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            fail("EvidenceAnchorMismatch", f"{context} does not resolve at {part!r}")
    return current


DOCUMENT_NORMALIZATION_POLICY = {
    "policy_id": "pmm.document_text_normalization.v1",
    "unicode_form": "NFC",
    "line_endings": "LF",
    "nbsp_to_space": True,
    "collapse_horizontal_whitespace": True,
    "collapse_blank_lines": True,
    "pdf_ligatures": {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl"},
}
DOCUMENT_NORMALIZATION_POLICY_SHA256 = sha256_bytes(
    canonical_json_bytes(DOCUMENT_NORMALIZATION_POLICY)
)
PDFTOTEXT_ARGUMENTS = [
    "-f", "{page}", "-l", "{page}", "-enc", "UTF-8", "-nopgbrk", "{source}", "-",
]
SUPPORTED_EXTRACTOR_NIXPKGS_REVISION = "59682e0069f0ed0a452e2179a7f4c1f247027b9e"
SUPPORTED_POPPLER_VERSION = "26.06.0"
SUPPORTED_PDFINFO_VERSION = f"pdfinfo version {SUPPORTED_POPPLER_VERSION}"
SUPPORTED_PDFTOTEXT_VERSION = f"pdftotext version {SUPPORTED_POPPLER_VERSION}"


def _normalize_document_text(raw: str, *, pdf: bool) -> str:
    text = raw.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    text = unicodedata.normalize("NFC", text).replace("\u00a0", " ")
    if pdf:
        for ligature, replacement in DOCUMENT_NORMALIZATION_POLICY["pdf_ligatures"].items():
            text = text.replace(ligature, replacement)
    normalized_lines: list[str] = []
    prior_blank = False
    for line in text.split("\n"):
        line = re.sub(r"[\t\v ]+", " ", line).strip(" ")
        blank = not line
        if blank and prior_blank:
            continue
        normalized_lines.append(line)
        prior_blank = blank
    while normalized_lines and not normalized_lines[0]:
        normalized_lines.pop(0)
    while normalized_lines and not normalized_lines[-1]:
        normalized_lines.pop()
    return "\n".join(normalized_lines)


def _tool_version(executable: str, context: str) -> str:
    try:
        completed = subprocess.run(
            [executable, "-v"], capture_output=True, check=False, timeout=10
        )
    except (OSError, subprocess.SubprocessError) as error:
        fail("EvidenceAnchorMismatch", f"{context} is unavailable: {error}")
    output = completed.stdout + completed.stderr
    try:
        lines = output.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError as error:
        fail("EvidenceAnchorMismatch", f"{context} version is not UTF-8: {error}")
    if completed.returncode not in {0, 99} or not lines:
        fail("EvidenceAnchorMismatch", f"{context} version probe failed")
    return lines[0].strip()


def _verify_extractor_policy(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail("EvidenceAnchorMismatch", "extractor policy must be an object")
    require_keys(
        value,
        {
            "policy_id", "pdfinfo_executable", "pdfinfo_version",
            "pdftotext_executable", "pdftotext_version", "pdftotext_arguments",
            "nixpkgs_revision", "poppler_package_version", "normalization_policy",
            "normalization_policy_sha256",
        },
        set(),
        "extractor policy",
    )
    if value["policy_id"] != "poppler_page_text.v1":
        fail("EvidenceAnchorMismatch", "extractor policy id is unsupported")
    if value["pdfinfo_executable"] != "pdfinfo" or value["pdftotext_executable"] != "pdftotext":
        fail("EvidenceAnchorMismatch", "extractor executable names are unsupported")
    if value["pdftotext_arguments"] != PDFTOTEXT_ARGUMENTS:
        fail("EvidenceAnchorMismatch", "pdftotext arguments differ from the immutable policy")
    if value["nixpkgs_revision"] != SUPPORTED_EXTRACTOR_NIXPKGS_REVISION:
        fail("EvidenceAnchorMismatch", "extractor nixpkgs revision is unsupported")
    if value["poppler_package_version"] != SUPPORTED_POPPLER_VERSION:
        fail("EvidenceAnchorMismatch", "extractor Poppler version is unsupported")
    if value["pdfinfo_version"] != SUPPORTED_PDFINFO_VERSION:
        fail("EvidenceAnchorMismatch", "declared pdfinfo version is unsupported")
    if value["pdftotext_version"] != SUPPORTED_PDFTOTEXT_VERSION:
        fail("EvidenceAnchorMismatch", "declared pdftotext version is unsupported")
    if value["normalization_policy"] != DOCUMENT_NORMALIZATION_POLICY["policy_id"]:
        fail("EvidenceAnchorMismatch", "document normalization policy is unsupported")
    if require_hash(value["normalization_policy_sha256"], "normalization policy hash") != DOCUMENT_NORMALIZATION_POLICY_SHA256:
        fail("EvidenceAnchorMismatch", "document normalization policy hash is stale")
    if _tool_version("pdfinfo", "pdfinfo") != value["pdfinfo_version"]:
        fail("EvidenceAnchorMismatch", "pdfinfo version differs from the evidence-map identity")
    if _tool_version("pdftotext", "pdftotext") != value["pdftotext_version"]:
        fail("EvidenceAnchorMismatch", "pdftotext version differs from the evidence-map identity")
    return value


def _extract_pdf_page(path: Path, page: int, policy: dict[str, Any]) -> tuple[int, str]:
    try:
        info = subprocess.run(
            [policy["pdfinfo_executable"], str(path)], capture_output=True, check=False, timeout=30
        )
    except (OSError, subprocess.SubprocessError) as error:
        fail("EvidenceAnchorMismatch", f"PDF metadata extraction failed: {error}")
    if info.returncode != 0:
        fail("EvidenceAnchorMismatch", "PDF is malformed, encrypted, or unreadable")
    try:
        info_text = info.stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        fail("EvidenceAnchorMismatch", f"PDF metadata is not UTF-8: {error}")
    match = re.search(r"(?m)^Pages:\s+([0-9]+)\s*$", info_text)
    if match is None:
        fail("EvidenceAnchorMismatch", "PDF page count is unavailable")
    page_count = int(match.group(1))
    if page < 1 or page > page_count:
        fail("EvidenceAnchorMismatch", f"PDF page {page} is outside 1..{page_count}")
    arguments = [
        token.replace("{page}", str(page)).replace("{source}", str(path))
        for token in policy["pdftotext_arguments"]
    ]
    try:
        extracted = subprocess.run(
            [policy["pdftotext_executable"], *arguments],
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        fail("EvidenceAnchorMismatch", f"PDF text extraction failed: {error}")
    if extracted.returncode != 0:
        fail("EvidenceAnchorMismatch", "PDF text extraction refused the selected page")
    try:
        text = extracted.stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        fail("EvidenceAnchorMismatch", f"PDF extracted text is not UTF-8: {error}")
    normalized = _normalize_document_text(text, pdf=True)
    if not normalized:
        fail("EvidenceAnchorMismatch", "PDF selected page is scanned, image-only, or textless")
    return page_count, normalized


def _bounded_lines(text: str, start: str, end: str | None, context: str) -> str:
    lines = text.split("\n")
    starts = [index for index, line in enumerate(lines) if line == start]
    if len(starts) != 1:
        fail("EvidenceAnchorMismatch", f"{context} start marker must occur exactly once")
    start_index = starts[0]
    if end is None:
        selected = lines[start_index:]
    else:
        ends = [index for index, line in enumerate(lines) if index > start_index and line == end]
        if len(ends) != 1:
            fail("EvidenceAnchorMismatch", f"{context} end marker must occur exactly once after the start")
        selected = lines[start_index:ends[0]]
    return "\n".join(selected)


def _section_fingerprint(kind: str, boundary: Any, text: str) -> str:
    return sha256_bytes(canonical_json_bytes({
        "kind": kind,
        "normalization_policy": DOCUMENT_NORMALIZATION_POLICY["policy_id"],
        "boundary": boundary,
        "text": text,
    }))


def _markdown_sections(text: str) -> list[tuple[list[dict[str, Any]], int, int]]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    headings: list[tuple[int, str, int]] = []
    fence: str | None = None
    for index, line in enumerate(lines):
        fence_match = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence_match:
            marker = fence_match.group(1)
            if fence is None:
                fence = marker[0]
            elif marker[0] == fence:
                fence = None
            continue
        if fence is not None:
            continue
        match = re.match(r"^ {0,3}(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$", line)
        if match:
            headings.append((len(match.group(1)), unicodedata.normalize("NFC", match.group(2)), index))
    result: list[tuple[list[dict[str, Any]], int, int]] = []
    stack: list[tuple[int, str]] = []
    for position, (level, title, line_index) in enumerate(headings):
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        end = len(lines)
        for later_level, _, later_index in headings[position + 1:]:
            if later_level <= level:
                end = later_index
                break
        result.append(([{"level": item_level, "text": item_title} for item_level, item_title in stack], line_index + 1, end))
    return result


def _term_leaf_pointers(value: Any, prefix: str = "/payload") -> list[str]:
    if isinstance(value, dict):
        result: list[str] = []
        for key, child in value.items():
            escaped = key.replace("~", "~0").replace("/", "~1")
            result.extend(_term_leaf_pointers(child, f"{prefix}/{escaped}"))
        return result
    if isinstance(value, list):
        result = []
        for index, child in enumerate(value):
            result.extend(_term_leaf_pointers(child, f"{prefix}/{index}"))
        return result
    return [prefix]


@dataclass(frozen=True)
class EvidenceMap:
    payload: dict[str, Any]
    payload_sha256: str
    file_sha256: str
    schema: str = EVIDENCE_MAP_SCHEMA

    @classmethod
    def load(
        cls, package: Path, terms: ProductTerms, evidence: SourceEvidence
    ) -> "EvidenceMap":
        path = package / "evidence_anchors.json"
        if not path.is_file():
            fail("EvidenceIncomplete", f"{path} is missing")
        document = read_object(path)
        if document.get("schema") == EVIDENCE_MAP_V2_SCHEMA:
            return cls._load_v2(path, package, terms, evidence)
        payload, payload_hash = validate_envelope(
            path, EVIDENCE_MAP_SCHEMA, "EvidenceAnchorMismatch"
        )
        require_keys(
            payload,
            {"effective_interval_evidence", "entries"},
            set(),
            "evidence map payload",
        )
        interval = payload["effective_interval_evidence"]
        if interval != {
            "opening_observation_id": "opening",
            "closing_observation_id": "closing",
        }:
            fail("EvidenceIncomplete", "evidence map must bracket opening and closing")
        entries = payload["entries"]
        if not isinstance(entries, list) or not entries:
            fail("EvidenceIncomplete", "evidence map must contain field anchors")
        pointers: list[str] = []
        source_by_id = {item["id"]: item for item in evidence.payload["sources"]}
        for index, entry in enumerate(entries):
            context = f"evidence.entries[{index}]"
            if not isinstance(entry, dict):
                fail("EvidenceAnchorMismatch", f"{context} must be an object")
            require_keys(
                entry,
                {"term_pointer", "support_mode", "anchors"},
                set(),
                context,
            )
            pointer = require_string(entry["term_pointer"], f"{context}.term_pointer")
            term_value = _json_pointer(
                {"payload": terms.payload}, pointer, f"{context}.term_pointer"
            )
            pointers.append(pointer)
            if entry["support_mode"] not in {"mechanically_projected", "human_reviewed"}:
                fail("EvidenceAnchorMismatch", f"{context}.support_mode is unsupported")
            anchors = entry["anchors"]
            if not isinstance(anchors, list) or not anchors:
                fail("EvidenceIncomplete", f"{context} has no anchors")
            observations: set[str] = set()
            for anchor_index, anchor in enumerate(anchors):
                anchor_context = f"{context}.anchors[{anchor_index}]"
                if not isinstance(anchor, dict):
                    fail("EvidenceAnchorMismatch", f"{anchor_context} must be an object")
                require_keys(
                    anchor,
                    {"source_id", "source_sha256", "locator"},
                    {"claim"},
                    anchor_context,
                )
                source_id = require_string(anchor["source_id"], f"{anchor_context}.source_id")
                source = source_by_id.get(source_id)
                if source is None:
                    fail("EvidenceIncomplete", f"{anchor_context} names a missing source")
                if require_hash(anchor["source_sha256"], f"{anchor_context}.source_sha256") != source["sha256"]:
                    fail("EvidenceAnchorMismatch", f"{anchor_context} source hash is stale")
                observation = source.get("observation_id")
                if observation in {"opening", "closing"}:
                    observations.add(observation)
                locator = anchor["locator"]
                if not isinstance(locator, dict):
                    fail("EvidenceAnchorMismatch", f"{anchor_context}.locator must be an object")
                kind = locator.get("kind")
                retained_path = safe_member(
                    package, source["path"], f"{anchor_context}.source path"
                )
                if kind == "json_pointer":
                    require_keys(locator, {"kind", "pointer"}, set(), f"{anchor_context}.locator")
                    source_value = _json_pointer(
                        read_object(retained_path),
                        locator["pointer"],
                        f"{anchor_context}.locator.pointer",
                    )
                    if (
                        entry["support_mode"] == "mechanically_projected"
                        and source_value != term_value
                    ):
                        fail("EvidenceAnchorMismatch", f"{anchor_context} value differs from terms")
                elif kind == "markdown_section":
                    require_keys(locator, {"kind", "heading"}, set(), f"{anchor_context}.locator")
                    heading = require_string(locator["heading"], f"{anchor_context}.heading")
                    text = retained_path.read_text(encoding="utf-8")
                    if heading not in text:
                        fail("EvidenceAnchorMismatch", f"{anchor_context} heading is absent")
                elif kind == "pdf_section":
                    require_keys(locator, {"kind", "page", "section"}, set(), f"{anchor_context}.locator")
                    require_integer(locator["page"], f"{anchor_context}.page", minimum=1)
                    require_string(locator["section"], f"{anchor_context}.section")
                    if retained_path.read_bytes()[:5] != b"%PDF-":
                        fail("EvidenceAnchorMismatch", f"{anchor_context} source is not a PDF")
                else:
                    fail("EvidenceAnchorMismatch", f"{anchor_context} locator kind is unsupported")
                if anchor.get("claim") is not None:
                    require_string(anchor["claim"], f"{anchor_context}.claim")
            if observations != {"opening", "closing"}:
                fail("EvidenceIncomplete", f"{context} is not supported at both interval endpoints")
        if pointers != sorted(pointers) or len(pointers) != len(set(pointers)):
            fail("EvidenceAnchorMismatch", "term pointers must be unique and sorted")
        return cls(payload, payload_hash, sha256_file(path))

    @classmethod
    def _load_v2(
        cls, path: Path, package: Path, terms: ProductTerms, evidence: SourceEvidence
    ) -> "EvidenceMap":
        if evidence.schema != SOURCE_MANIFEST_V4_SCHEMA or evidence.evidence_profile is None:
            fail("EvidenceProfileMismatch", "evidence-map V2 requires source-manifest V4 and its profile")
        payload, payload_hash = validate_envelope(path, EVIDENCE_MAP_V2_SCHEMA, "EvidenceAnchorMismatch")
        require_keys(
            payload,
            {"effective_interval_evidence", "evidence_profile_sha256", "extractor_policy", "entries"},
            set(),
            "evidence map V2 payload",
        )
        if payload["effective_interval_evidence"] != {
            "opening_observation_id": "opening", "closing_observation_id": "closing"
        }:
            fail("EvidenceIncomplete", "evidence map V2 must bracket opening and closing")
        if require_hash(payload["evidence_profile_sha256"], "evidence map profile hash") != evidence.evidence_profile.payload_sha256:
            fail("EvidenceProfileMismatch", "evidence map names a different evidence profile")
        extractor_policy = _verify_extractor_policy(payload["extractor_policy"])
        entries = payload["entries"]
        if not isinstance(entries, list) or not entries:
            fail("EvidenceIncomplete", "evidence map V2 must contain a complete coverage ledger")
        source_by_id = {source["id"]: source for source in evidence.payload["sources"]}
        profile_coverage = {
            item["term_pointer"]: item["coverage_class"]
            for item in evidence.evidence_profile.payload["field_coverage"]
        }
        expected_leaves = sorted(_term_leaf_pointers(terms.payload))
        if sorted(profile_coverage) != expected_leaves:
            fail("EvidenceIncomplete", "evidence profile does not classify every product-term leaf exactly once")
        pointers: list[str] = []
        for index, entry in enumerate(entries):
            context = f"evidence.entries[{index}]"
            if not isinstance(entry, dict):
                fail("EvidenceAnchorMismatch", f"{context} must be an object")
            require_keys(
                entry,
                {"term_pointer", "coverage_class", "anchors", "dependency_pointers", "policy_id", "reason"},
                set(),
                context,
            )
            pointer = require_string(entry["term_pointer"], f"{context}.term_pointer")
            _json_pointer({"payload": terms.payload}, pointer, f"{context}.term_pointer")
            pointers.append(pointer)
            coverage_class = entry["coverage_class"]
            if profile_coverage.get(pointer) != coverage_class:
                fail("EvidenceProfileMismatch", f"{context} coverage class differs from the profile")
            anchors = entry["anchors"]
            dependencies = entry["dependency_pointers"]
            if not isinstance(anchors, list) or not isinstance(dependencies, list):
                fail("EvidenceAnchorMismatch", f"{context} anchors and dependencies must be arrays")
            if dependencies != sorted(set(dependencies)):
                fail("EvidenceAnchorMismatch", f"{context} dependencies must be unique and sorted")
            for dependency in dependencies:
                _json_pointer({"payload": terms.payload}, dependency, f"{context}.dependency")
            policy_id = entry["policy_id"]
            reason = entry["reason"]
            if coverage_class in {"mechanically_projected", "human_reviewed"}:
                if not anchors or dependencies or policy_id is not None or reason is not None:
                    fail("EvidenceIncomplete", f"{context} source-backed coverage has invalid metadata")
            elif coverage_class == "derived":
                if anchors or not dependencies or policy_id is not None or reason is not None:
                    fail("EvidenceIncomplete", f"{context} derived coverage must name dependencies only")
            elif coverage_class == "repository_local_policy":
                if anchors or dependencies or reason is not None:
                    fail("EvidenceIncomplete", f"{context} repository policy coverage has invalid metadata")
                require_string(policy_id, f"{context}.policy_id")
            else:
                if anchors or dependencies or policy_id is not None:
                    fail("EvidenceIncomplete", f"{context} unsupported/N-A coverage has invalid metadata")
                require_string(reason, f"{context}.reason")
            observations: set[str] = set()
            for anchor_index, anchor in enumerate(anchors):
                anchor_context = f"{context}.anchors[{anchor_index}]"
                if not isinstance(anchor, dict):
                    fail("EvidenceAnchorMismatch", f"{anchor_context} must be an object")
                require_keys(anchor, {"source_id", "source_sha256", "locator"}, {"claim"}, anchor_context)
                source_id = require_string(anchor["source_id"], f"{anchor_context}.source_id")
                source = source_by_id.get(source_id)
                if source is None:
                    fail("EvidenceIncomplete", f"{anchor_context} names a missing source")
                if require_hash(anchor["source_sha256"], f"{anchor_context}.source_sha256") != source["sha256"]:
                    fail("EvidenceAnchorMismatch", f"{anchor_context} source hash is stale")
                observations.add(source["observation_id"])
                locator = anchor["locator"]
                if not isinstance(locator, dict):
                    fail("EvidenceAnchorMismatch", f"{anchor_context}.locator must be an object")
                retained_path = safe_member(package, source["path"], f"{anchor_context}.source path")
                kind = locator.get("kind")
                if kind == "json_pointer":
                    require_keys(locator, {"kind", "pointer"}, set(), f"{anchor_context}.locator")
                    source_value = _json_pointer(read_object(retained_path), locator["pointer"], f"{anchor_context}.pointer")
                    if coverage_class != "mechanically_projected":
                        fail("EvidenceAnchorMismatch", f"{anchor_context} JSON pointer is only valid for projected coverage")
                    if source_value != _json_pointer({"payload": terms.payload}, pointer, f"{context}.term_pointer"):
                        fail("EvidenceAnchorMismatch", f"{anchor_context} value differs from terms")
                elif kind == "pdf_section":
                    require_keys(
                        locator,
                        {"kind", "page", "section_start", "section_end", "section_sha256"},
                        set(),
                        f"{anchor_context}.locator",
                    )
                    if coverage_class != "human_reviewed" or source["media_type"] != "application/pdf":
                        fail("EvidenceAnchorMismatch", f"{anchor_context} PDF locator has incompatible coverage/media")
                    page = require_integer(locator["page"], f"{anchor_context}.page", minimum=1)
                    start = require_string(locator["section_start"], f"{anchor_context}.section_start")
                    end = locator["section_end"]
                    if end is not None:
                        end = require_string(end, f"{anchor_context}.section_end")
                    _, page_text = _extract_pdf_page(retained_path, page, extractor_policy)
                    section = _bounded_lines(page_text, _normalize_document_text(start, pdf=True), None if end is None else _normalize_document_text(end, pdf=True), anchor_context)
                    fingerprint = _section_fingerprint("pdf_section", {"page": page, "section_start": start, "section_end": end}, section)
                    if require_hash(locator["section_sha256"], f"{anchor_context}.section_sha256") != fingerprint:
                        fail("EvidenceAnchorMismatch", f"{anchor_context} PDF section fingerprint differs")
                elif kind == "markdown_section":
                    require_keys(locator, {"kind", "heading_path", "section_sha256"}, set(), f"{anchor_context}.locator")
                    if coverage_class != "human_reviewed" or source["media_type"] not in {"text/markdown", "text/plain"}:
                        fail("EvidenceAnchorMismatch", f"{anchor_context} Markdown locator has incompatible coverage/media")
                    heading_path = locator["heading_path"]
                    if not isinstance(heading_path, list) or not heading_path:
                        fail("EvidenceAnchorMismatch", f"{anchor_context}.heading_path must not be empty")
                    normalized_path: list[dict[str, Any]] = []
                    for heading in heading_path:
                        if not isinstance(heading, dict):
                            fail("EvidenceAnchorMismatch", f"{anchor_context}.heading_path item must be an object")
                        require_keys(heading, {"level", "text"}, set(), f"{anchor_context}.heading")
                        normalized_path.append({
                            "level": require_integer(heading["level"], f"{anchor_context}.heading.level", minimum=1),
                            "text": unicodedata.normalize("NFC", require_string(heading["text"], f"{anchor_context}.heading.text")),
                        })
                    matches = [item for item in _markdown_sections(retained_path.read_text(encoding="utf-8")) if item[0] == normalized_path]
                    if len(matches) != 1:
                        fail("EvidenceAnchorMismatch", f"{anchor_context} heading path must resolve exactly once")
                    _, start_line, end_line = matches[0]
                    raw_lines = retained_path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n").split("\n")
                    section = _normalize_document_text("\n".join(raw_lines[start_line:end_line]), pdf=False)
                    fingerprint = _section_fingerprint("markdown_section", {"heading_path": normalized_path}, section)
                    if require_hash(locator["section_sha256"], f"{anchor_context}.section_sha256") != fingerprint:
                        fail("EvidenceAnchorMismatch", f"{anchor_context} Markdown section fingerprint differs")
                else:
                    fail("EvidenceAnchorMismatch", f"{anchor_context} locator kind is unsupported")
                if anchor.get("claim") is not None:
                    require_string(anchor["claim"], f"{anchor_context}.claim")
            if anchors and observations != {"opening", "closing"}:
                fail("EvidenceIncomplete", f"{context} is not supported at both interval endpoints")
        if pointers != sorted(pointers) or len(pointers) != len(set(pointers)) or pointers != expected_leaves:
            fail("EvidenceIncomplete", "evidence map V2 must classify every product-term leaf once in sorted order")
        return cls(payload, payload_hash, sha256_file(path), EVIDENCE_MAP_V2_SCHEMA)


@dataclass(frozen=True)
class ProductReview:
    payload: dict[str, Any]
    payload_sha256: str
    file_sha256: str
    schema: str
    evidence_map: EvidenceMap | None

    @classmethod
    def load(cls, package: Path, terms: ProductTerms, evidence: SourceEvidence) -> "ProductReview":
        path = package / "review.json"
        if not path.is_file():
            fail("ReviewMissing", f"{path} is missing")
        document = read_object(path)
        schema = document.get("schema")
        if schema not in {PRODUCT_REVIEW_SCHEMA, PRODUCT_REVIEW_V2_SCHEMA, PRODUCT_REVIEW_V3_SCHEMA}:
            fail("UnsupportedTermsSchema", f"{path} uses unsupported review schema {schema!r}")
        payload, payload_hash = validate_envelope(path, schema, "ReviewHashMismatch")
        required = {
            "status", "reviewed_at_utc", "product_terms_sha256",
            "source_manifest_sha256", "effective_from_utc", "effective_until_utc",
            "effective_time_basis", "limitations",
        }
        if schema in {PRODUCT_REVIEW_V2_SCHEMA, PRODUCT_REVIEW_V3_SCHEMA}:
            required.update({
                "reviewer", "responsibilities", "checklist",
                "acquisition_policy_sha256", "evidence_map_sha256",
            })
        if schema == PRODUCT_REVIEW_V3_SCHEMA:
            required.add("evidence_profile_sha256")
        require_keys(payload, required, set(), "review payload")
        if payload["status"] != "reviewed":
            fail("ReviewNotApproved", f"review status is {payload['status']!r}")
        parse_utc(payload["reviewed_at_utc"], "review.reviewed_at_utc")
        if require_hash(payload["product_terms_sha256"], "review.product_terms_sha256") != terms.payload_sha256:
            fail("ReviewHashMismatch", "review names a different product terms revision")
        if require_hash(payload["source_manifest_sha256"], "review.source_manifest_sha256") != evidence.payload_sha256:
            fail("ReviewHashMismatch", "review names a different source bundle")
        start = parse_utc(payload["effective_from_utc"], "review.effective_from_utc")
        end = None if payload["effective_until_utc"] is None else parse_utc(payload["effective_until_utc"], "review.effective_until_utc")
        if end is not None and end <= start:
            fail("EffectiveWindowGap", "review effective interval is empty")
        if payload["effective_time_basis"] != terms.payload["effective"]["basis"]:
            fail("EffectiveWindowMismatch", "review and terms effective-time basis differ")
        terms_effective = terms.payload["effective"]
        if (
            payload["effective_from_utc"] != terms_effective["from_utc"]
            or payload["effective_until_utc"] != terms_effective["until_utc"]
        ):
            fail("EffectiveWindowMismatch", "review and terms effective intervals differ")
        if not isinstance(payload["limitations"], list) or any(not isinstance(item, str) for item in payload["limitations"]):
            fail("TermsNoncanonical", "review limitations must be strings")
        evidence_map: EvidenceMap | None = None
        if schema in {PRODUCT_REVIEW_V2_SCHEMA, PRODUCT_REVIEW_V3_SCHEMA}:
            expected_manifest_schema = (
                SOURCE_MANIFEST_V4_SCHEMA if schema == PRODUCT_REVIEW_V3_SCHEMA
                else SOURCE_MANIFEST_V3_SCHEMA
            )
            if evidence.schema != expected_manifest_schema or evidence.acquisition_policy is None:
                fail("AcquisitionPolicyMismatch", f"{schema} requires {expected_manifest_schema}")
            reviewer = payload["reviewer"]
            if not isinstance(reviewer, dict):
                fail("TermsNoncanonical", "reviewer must be an object")
            require_keys(reviewer, {"identity", "identity_kind"}, set(), "review reviewer")
            require_string(reviewer["identity"], "review reviewer identity")
            if reviewer["identity_kind"] != "repository_declared":
                fail("TermsNoncanonical", "review identity kind must be repository_declared")
            responsibilities = payload["responsibilities"]
            if (
                not isinstance(responsibilities, list)
                or not responsibilities
                or any(not isinstance(item, str) or not item for item in responsibilities)
                or responsibilities != sorted(set(responsibilities))
            ):
                fail("TermsNoncanonical", "review responsibilities must be sorted and unique")
            checklist = payload["checklist"]
            if not isinstance(checklist, list) or not checklist:
                fail("TermsNoncanonical", "review checklist must not be empty")
            checklist_names: list[str] = []
            for item in checklist:
                if not isinstance(item, dict):
                    fail("TermsNoncanonical", "review checklist item must be an object")
                require_keys(item, {"item", "status"}, set(), "review checklist item")
                checklist_names.append(require_string(item["item"], "review checklist item"))
                if item["status"] != "accepted":
                    fail("ReviewNotApproved", "review checklist contains an unaccepted item")
            if schema == PRODUCT_REVIEW_V3_SCHEMA and len(checklist_names) != len(set(checklist_names)):
                fail("TermsNoncanonical", "review V3 checklist item names must be unique")
            if require_hash(
                payload["acquisition_policy_sha256"], "review acquisition policy hash"
            ) != evidence.acquisition_policy.payload_sha256:
                fail("AcquisitionPolicyMismatch", "review names a different acquisition policy")
            if schema == PRODUCT_REVIEW_V3_SCHEMA:
                if evidence.evidence_profile is None:
                    fail("EvidenceProfileMismatch", "review V3 requires an evidence profile")
                if require_hash(
                    payload["evidence_profile_sha256"], "review evidence profile hash"
                ) != evidence.evidence_profile.payload_sha256:
                    fail("EvidenceProfileMismatch", "review names a different evidence profile")
            evidence_map = EvidenceMap.load(package, terms, evidence)
            if require_hash(payload["evidence_map_sha256"], "review evidence map hash") != evidence_map.payload_sha256:
                fail("ReviewHashMismatch", "review names a different evidence map")
            acquisitions = evidence.payload["acquisitions"]
            if len(acquisitions) != 2:
                fail("EvidenceIncomplete", f"{schema} requires opening and closing observations")
            bracket_from = acquisitions[0]["completed_at_utc"]
            bracket_until = acquisitions[1]["started_at_utc"]
            if payload["effective_from_utc"] != bracket_from or payload["effective_until_utc"] != bracket_until:
                fail("EffectiveWindowMismatch", "review interval does not equal the observed bracket")
            if parse_utc(bracket_until, "closing acquisition start") <= parse_utc(
                bracket_from, "opening acquisition completion"
            ):
                fail("EffectiveWindowGap", "opening and closing acquisitions do not bracket time")
        return cls(payload, payload_hash, sha256_file(path), schema, evidence_map)

    def covers(self, started: datetime, ended: datetime) -> bool:
        start = parse_utc(self.payload["effective_from_utc"], "review.effective_from_utc")
        end_value = self.payload["effective_until_utc"]
        end = None if end_value is None else parse_utc(end_value, "review.effective_until_utc")
        return started >= start and (end is None or ended < end)


@dataclass(frozen=True)
class ConversionPolicy:
    path: Path
    payload: dict[str, Any]
    payload_sha256: str
    file_sha256: str

    @classmethod
    def load(cls, path: Path) -> "ConversionPolicy":
        payload, payload_hash = validate_envelope(path, CONVERSION_POLICY_SCHEMA, "ConversionPolicyMismatch")
        require_keys(payload, {"observed_price_policy", "observed_quantity_policy", "core_price_policy", "core_quantity_policy", "fee_application", "settlement_application"}, set(), "conversion policy")
        expected = {
            "observed_price_policy": "preserve_exact_validate_grid",
            "observed_quantity_policy": "preserve_exact_validate_increment",
            "core_price_policy": "integer_cents_exact_only",
            "core_quantity_policy": "whole_contracts_exact_only",
            "fee_application": "not_applied",
            "settlement_application": "not_applied",
        }
        if payload != expected:
            fail("ConversionPolicyMismatch", "conversion policy is unsupported by B1a")
        return cls(path, payload, payload_hash, sha256_file(path))

    def require_core_compatible(self, terms: ProductTerms) -> None:
        for index, item in enumerate(terms.payload["price"]["ranges"]):
            for name in ("start_dollars", "end_dollars", "step_dollars"):
                if Decimal(item[name]) * 100 % 1 != 0:
                    fail("CorePriceNotRepresentable", f"price range {index}.{name} is not cent aligned")
        if terms.payload["payout"]["notional_value_dollars"] != "1.0000":
            fail("UnsupportedPayout", "current core supports one-dollar notional only")

    def convert_price_to_cents(self, value: Decimal, context: str) -> int:
        cents = value * 100
        if cents % 1 != 0:
            fail("CorePriceNotRepresentable", f"{context}={value} is not an exact cent value")
        return int(cents)

    def convert_quantity_to_contracts(self, value: Decimal, context: str) -> int:
        if value % 1 != 0:
            fail("CoreQuantityNotRepresentable", f"{context}={value} is not a whole contract")
        return int(value)


@dataclass(frozen=True)
class ProductPackage:
    path: Path
    evidence: SourceEvidence
    terms: ProductTerms
    review: ProductReview

    @classmethod
    def load(cls, path: Path) -> "ProductPackage":
        if path.is_symlink():
            fail("SourceMissing", f"{path} must not be a symlink")
        resolved = path.resolve()
        if not resolved.is_dir():
            fail("SourceMissing", f"{path} is not a regular package directory")
        evidence = SourceEvidence.load(resolved)
        expected_files = {"source_manifest.json", "product_terms.json", "review.json"}
        review_document = read_object(resolved / "review.json")
        review_schema = review_document.get("schema")
        if evidence.schema in {SOURCE_MANIFEST_V3_SCHEMA, SOURCE_MANIFEST_V4_SCHEMA}:
            expected_files.add("acquisition_policy.json")
        if evidence.schema == SOURCE_MANIFEST_V4_SCHEMA:
            expected_files.add("evidence_profile.json")
        if review_schema in {PRODUCT_REVIEW_V2_SCHEMA, PRODUCT_REVIEW_V3_SCHEMA}:
            expected_files.add("evidence_anchors.json")
        expected_files.update(source["path"] for source in evidence.payload["sources"])
        actual_files: set[str] = set()
        for member in resolved.rglob("*"):
            if member.is_symlink():
                fail("SourceMissing", f"product package contains symlink {member.relative_to(resolved)}")
            if member.is_file():
                actual_files.add(member.relative_to(resolved).as_posix())
        if actual_files != expected_files:
            missing = sorted(expected_files - actual_files)
            unexpected = sorted(actual_files - expected_files)
            fail("PackageMembershipMismatch", f"package files differ; missing={missing}, unexpected={unexpected}")
        terms = ProductTerms.load(resolved, evidence)
        review = ProductReview.load(resolved, terms, evidence)
        return cls(resolved, evidence, terms, review)

    def verify_capture(self, metadata: dict[str, Any]) -> None:
        ticker = metadata.get("ticker")
        if ticker != self.terms.market_ticker:
            fail("MarketTickerMismatch", f"capture {ticker!r} != terms {self.terms.market_ticker!r}")
        started = utc_ns_to_datetime(metadata.get("capture_started_at_utc_ns"), "capture_started_at_utc_ns")
        ended = utc_ns_to_datetime(metadata.get("capture_ended_at_utc_ns"), "capture_ended_at_utc_ns")
        if ended < started or not self.review.covers(started, ended):
            fail("CaptureOutsideEffectiveWindow", "reviewed revision does not cover the complete capture")


@dataclass(frozen=True)
class ProductCatalog:
    root: Path
    payload: dict[str, Any]
    payload_sha256: str
    file_sha256: str

    @classmethod
    def load(cls, root: Path) -> "ProductCatalog":
        if root.is_symlink():
            fail("SourceMissing", f"catalog root {root} must not be a symlink")
        resolved = root.resolve()
        if not resolved.is_dir():
            fail("SourceMissing", f"catalog root {root} is not a regular directory")
        path = resolved / "manifest.json"
        payload, payload_hash = validate_envelope(path, PRODUCT_CATALOG_SCHEMA, "CatalogHashMismatch")
        require_keys(payload, {"entries"}, set(), "catalog payload")
        entries = payload["entries"]
        if not isinstance(entries, list) or not entries:
            fail("TermsNoncanonical", "catalog entries must be a non-empty list")
        keys: list[tuple[str, str]] = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                fail("TermsNoncanonical", f"catalog entry {index} must be an object")
            require_keys(entry, {"venue", "environment", "series_ticker", "event_ticker", "market_ticker", "effective_from_utc", "effective_until_utc", "package", "product_terms_sha256", "source_manifest_sha256", "review_sha256"}, set(), f"catalog entry {index}")
            if entry["venue"] != "kalshi" or entry["environment"] != "production":
                fail("TermsNoncanonical", f"catalog entry {index} has unsupported venue/environment")
            for name in ("series_ticker", "event_ticker", "market_ticker", "package"):
                require_string(entry[name], f"catalog entry {index}.{name}")
            parse_utc(entry["effective_from_utc"], f"catalog entry {index}.effective_from_utc")
            catalog_start = parse_utc(
                entry["effective_from_utc"], f"catalog entry {index}.effective_from_utc"
            )
            if entry["effective_until_utc"] is not None:
                catalog_end = parse_utc(
                    entry["effective_until_utc"], f"catalog entry {index}.effective_until_utc"
                )
                if catalog_end <= catalog_start:
                    fail("EffectiveWindowGap", f"catalog entry {index} interval is empty")
            for name in ("product_terms_sha256", "source_manifest_sha256", "review_sha256"):
                require_hash(entry[name], f"catalog entry {index}.{name}")
            keys.append((entry["market_ticker"], entry["effective_from_utc"]))
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            fail("CatalogAmbiguous", "catalog entries must be uniquely sorted by market and effective time")
        catalog = cls(resolved, payload, payload_hash, sha256_file(path))
        catalog.verify()
        return catalog

    def _package_for(self, entry: dict[str, Any]) -> ProductPackage:
        relative = Path(entry["package"])
        if relative.is_absolute() or ".." in relative.parts or "\\" in entry["package"]:
            fail("SourceMissing", "catalog package path is unsafe")
        unresolved = self.root / relative
        candidate = self.root
        for part in relative.parts:
            candidate = candidate / part
            if candidate.is_symlink():
                fail("SourceMissing", "catalog package path must not contain a symlink")
        package_path = unresolved.resolve()
        try:
            package_path.relative_to(self.root)
        except ValueError:
            fail("SourceMissing", "catalog package escapes the catalog root")
        package = ProductPackage.load(package_path)
        if package.terms.payload_sha256 != entry["product_terms_sha256"] or package.evidence.payload_sha256 != entry["source_manifest_sha256"] or package.review.payload_sha256 != entry["review_sha256"]:
            fail("CatalogHashMismatch", f"catalog entry for {entry['market_ticker']} has stale hashes")
        identity = package.terms.identity
        for name in ("series_ticker", "event_ticker", "market_ticker"):
            if identity[name] != entry[name]:
                fail(f"{name.split('_')[0].title()}TickerMismatch", f"catalog entry {name} differs from package")
        terms_effective = package.terms.payload["effective"]
        review = package.review.payload
        catalog_interval = (entry["effective_from_utc"], entry["effective_until_utc"])
        terms_interval = (terms_effective["from_utc"], terms_effective["until_utc"])
        review_interval = (review["effective_from_utc"], review["effective_until_utc"])
        if catalog_interval != terms_interval or catalog_interval != review_interval:
            fail(
                "EffectiveWindowMismatch",
                f"catalog entry for {entry['market_ticker']} differs from its terms or review interval",
            )
        return package

    def verify(self) -> None:
        by_market: dict[str, list[tuple[datetime, datetime | None]]] = {}
        for entry in self.payload["entries"]:
            self._package_for(entry)
            start = parse_utc(entry["effective_from_utc"], "catalog effective_from")
            end = None if entry["effective_until_utc"] is None else parse_utc(entry["effective_until_utc"], "catalog effective_until")
            intervals = by_market.setdefault(entry["market_ticker"], [])
            if intervals and (intervals[-1][1] is None or start < intervals[-1][1]):
                fail("EffectiveWindowOverlap", f"{entry['market_ticker']} has overlapping revisions")
            intervals.append((start, end))

    def resolve(self, metadata: dict[str, Any]) -> ProductPackage:
        ticker = metadata.get("ticker")
        started = utc_ns_to_datetime(metadata.get("capture_started_at_utc_ns"), "capture_started_at_utc_ns")
        ended = utc_ns_to_datetime(metadata.get("capture_ended_at_utc_ns"), "capture_ended_at_utc_ns")
        if ended < started:
            fail("CaptureOutsideEffectiveWindow", "capture completion precedes its start")
        matches: list[ProductPackage] = []
        for entry in self.payload["entries"]:
            if entry["market_ticker"] != ticker:
                continue
            start = parse_utc(entry["effective_from_utc"], "catalog effective_from")
            end_value = entry["effective_until_utc"]
            end = None if end_value is None else parse_utc(end_value, "catalog effective_until")
            if started >= start and (end is None or ended < end):
                matches.append(self._package_for(entry))
        if not matches:
            fail("EffectiveWindowGap", f"no reviewed terms cover {ticker!r} for the capture interval")
        if len(matches) != 1:
            fail("CatalogAmbiguous", f"multiple reviewed terms cover {ticker!r}")
        matches[0].verify_capture(metadata)
        return matches[0]


def compatibility_report(left: ProductPackage, right: ProductPackage, left_policy: ConversionPolicy, right_policy: ConversionPolicy) -> dict[str, Any]:
    reasons: list[dict[str, str]] = []
    comparisons = (
        ("MarketTickerMismatch", left.terms.market_ticker, right.terms.market_ticker),
        ("TermsHashMismatch", left.terms.payload_sha256, right.terms.payload_sha256),
        ("SourceHashMismatch", left.evidence.payload_sha256, right.evidence.payload_sha256),
        ("ReviewHashMismatch", left.review.payload_sha256, right.review.payload_sha256),
        ("ConversionPolicyMismatch", left_policy.payload_sha256, right_policy.payload_sha256),
    )
    for code, left_value, right_value in comparisons:
        if left_value != right_value:
            reasons.append({"code": code, "left": left_value, "right": right_value})
    return {"schema": COMPATIBILITY_REPORT_SCHEMA, "compatible": not reasons, "reasons": reasons}


def copy_package(package: ProductPackage, output: Path) -> None:
    if output.exists():
        fail("SourceMissing", f"package output already exists: {output}")
    shutil.copytree(package.path, output, symlinks=False)
    copied = ProductPackage.load(output)
    if copied.terms.payload_sha256 != package.terms.payload_sha256 or copied.evidence.payload_sha256 != package.evidence.payload_sha256 or copied.review.payload_sha256 != package.review.payload_sha256:
        fail("TermsHashMismatch", "copied product package changed identity")


def _write_new_canonical(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        fail("SourceMissing", f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def build_envelope(schema: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"schema": schema, "payload": payload, "payload_sha256": sha256_bytes(canonical_json_bytes(payload))}


def _safe_output_path(root: Path, value: Any, context: str) -> tuple[Path, Path]:
    text = require_string(value, context)
    relative = Path(text)
    if relative.is_absolute() or ".." in relative.parts or "\\" in text:
        fail("SourceMissing", f"{context} path is unsafe")
    return relative, root / relative


def _media_type(headers: Any) -> str:
    content_type = str(headers.get("Content-Type", "")).strip()
    return content_type.split(";", 1)[0].strip().lower()


def _selected_headers(headers: Any) -> dict[str, str | None]:
    return {
        "content_type": headers.get("Content-Type"),
        "content_length": headers.get("Content-Length"),
        "etag": headers.get("ETag"),
        "last_modified": headers.get("Last-Modified"),
        "date": headers.get("Date"),
    }


def _validate_retained_content(path: Path, content_kind: str, context: str) -> None:
    try:
        if content_kind == "json":
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                fail("AcquisitionContentInvalid", f"{context} JSON must contain an object")
        elif content_kind == "text":
            path.read_text(encoding="utf-8")
        elif content_kind == "pdf":
            with path.open("rb") as source:
                if source.read(5) != b"%PDF-":
                    fail("AcquisitionContentInvalid", f"{context} has no PDF signature")
        else:
            raise AssertionError(f"unsupported acquisition content kind: {content_kind}")
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        fail("AcquisitionContentInvalid", f"{context} content is invalid: {error}")


def _request_source(
    session: Any,
    item: dict[str, Any],
    destination: Path,
    *,
    package_bytes: int,
    package_started: float,
    now: Callable[[], datetime],
    monotonic: Callable[[], float],
    observation_id: str | None = None,
    tool_version: str = ACQUISITION_TOOL_VERSION,
) -> tuple[dict[str, Any], int]:
    role = require_string(item["role"], "fetch source role")
    if role not in ROLE_POLICIES:
        fail("TermsNoncanonical", f"fetch source role {role!r} is unsupported")
    role_limit, role_media, content_kind = ROLE_POLICIES[role]
    declared_limit = item.get("maximum_bytes", role_limit)
    maximum_bytes = require_integer(declared_limit, "fetch source maximum_bytes", minimum=1)
    if maximum_bytes > role_limit:
        fail("TermsNoncanonical", "fetch source maximum_bytes may not exceed the role policy")
    declared_media = item.get("media_types", sorted(role_media))
    if (
        not isinstance(declared_media, list)
        or not declared_media
        or any(not isinstance(value, str) or value not in role_media for value in declared_media)
    ):
        fail("TermsNoncanonical", "fetch source media_types must narrow the role policy")
    allowed_media = frozenset(declared_media)
    requested_url = approved_source_url(item["url"], "fetch source url")
    current_url = requested_url
    redirect_history: list[dict[str, Any]] = []
    source_started_utc = now()
    source_started = monotonic()
    response: Any = None
    try:
        while True:
            if monotonic() - source_started > SOURCE_DEADLINE_SECONDS:
                fail("AcquisitionTimeout", "source acquisition exceeded its wall-clock deadline")
            if monotonic() - package_started > PACKAGE_DEADLINE_SECONDS:
                fail("AcquisitionTimeout", "package acquisition exceeded its wall-clock deadline")
            try:
                response = session.get(
                    current_url,
                    timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
                    allow_redirects=False,
                    stream=True,
                    headers={"Accept-Encoding": "identity"},
                )
            except requests.Timeout as error:
                fail("AcquisitionTimeout", f"request timed out: {error}")
            except requests.RequestException as error:
                fail("AcquisitionTransportFailure", f"request failed: {error}")
            response_url = str(getattr(response, "url", current_url) or current_url)
            approved_source_url(response_url, "response final url")
            if response_url != current_url:
                fail("AcquisitionRedirectRejected", "response URL changed without a recorded redirect")
            status = require_integer(response.status_code, "response status")
            if status in REDIRECT_STATUSES:
                location = response.headers.get("Location")
                if not isinstance(location, str) or not location:
                    fail("AcquisitionRedirectRejected", "redirect response has no Location header")
                if len(redirect_history) >= MAX_REDIRECTS:
                    fail("AcquisitionRedirectLimit", "source exceeded the redirect-hop limit")
                resolved = urljoin(response_url, location)
                try:
                    approved_source_url(resolved, "redirect destination")
                except ProductTermsError as error:
                    fail("AcquisitionRedirectRejected", str(error))
                redirect_history.append({
                    "status_code": status,
                    "location": location,
                    "resolved_url": resolved,
                })
                response.close()
                response = None
                current_url = resolved
                continue
            if 300 <= status < 400:
                fail("AcquisitionRedirectRejected", f"unsupported redirect status {status}")
            if status < 200 or status >= 300:
                fail("AcquisitionHttpStatusRejected", f"source returned HTTP status {status}")
            break

        encoding = response.headers.get("Content-Encoding")
        if encoding not in {None, "", "identity"}:
            fail("AcquisitionContentInvalid", f"unsupported HTTP content encoding {encoding!r}")
        media_type = _media_type(response.headers)
        if media_type not in allowed_media:
            fail(
                "AcquisitionMediaTypeMismatch",
                f"role {role} does not permit response media type {media_type!r}",
            )
        content_length = response.headers.get("Content-Length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except (TypeError, ValueError):
                fail("AcquisitionContentInvalid", "response Content-Length is not an integer")
            if declared_length < 0:
                fail("AcquisitionContentInvalid", "response Content-Length is negative")
            if declared_length > maximum_bytes:
                fail("AcquisitionSourceTooLarge", "declared response exceeds the source limit")
            if package_bytes + declared_length > MAX_PACKAGE_BYTES:
                fail("AcquisitionPackageTooLarge", "declared response exceeds the package limit")

        digest = hashlib.sha256()
        byte_count = 0
        destination.parent.mkdir(parents=True, exist_ok=True)
        download = destination.with_name(destination.name + ".download")
        with download.open("xb") as retained:
            try:
                for chunk in response.iter_content(chunk_size=STREAM_CHUNK_BYTES):
                    if not chunk:
                        continue
                    if monotonic() - source_started > SOURCE_DEADLINE_SECONDS:
                        fail("AcquisitionTimeout", "source acquisition exceeded its wall-clock deadline")
                    if monotonic() - package_started > PACKAGE_DEADLINE_SECONDS:
                        fail("AcquisitionTimeout", "package acquisition exceeded its wall-clock deadline")
                    byte_count += len(chunk)
                    if byte_count > maximum_bytes:
                        fail("AcquisitionSourceTooLarge", "streamed response exceeds the source limit")
                    if package_bytes + byte_count > MAX_PACKAGE_BYTES:
                        fail("AcquisitionPackageTooLarge", "streamed response exceeds the package limit")
                    digest.update(chunk)
                    retained.write(chunk)
                retained.flush()
                os.fsync(retained.fileno())
            except requests.Timeout as error:
                download.unlink(missing_ok=True)
                fail("AcquisitionTimeout", f"response stream timed out: {error}")
            except requests.RequestException as error:
                download.unlink(missing_ok=True)
                fail("AcquisitionTransportFailure", f"response stream failed: {error}")
            except BaseException:
                download.unlink(missing_ok=True)
                raise
        if content_length is not None and byte_count != declared_length:
            download.unlink(missing_ok=True)
            fail("AcquisitionContentInvalid", "retained byte count differs from Content-Length")
        _validate_retained_content(download, content_kind, f"source {item['id']}")
        download.rename(destination)
        source_completed_utc = now()
        elapsed_milliseconds = int((monotonic() - source_started) * 1000)
        final_url = str(getattr(response, "url", current_url) or current_url)
        approved_source_url(final_url, "response final url")
        retained = {
            "id": require_string(item["id"], "fetch source id"),
            "role": role,
            "requested_url": requested_url,
            "final_url": final_url,
            "redirect_history": redirect_history,
            "http_status": int(response.status_code),
            "media_type": media_type,
            "retrieval_started_at_utc": format_utc(source_started_utc),
            "retrieval_completed_at_utc": format_utc(source_completed_utc),
            "elapsed_milliseconds": elapsed_milliseconds,
            "path": item["path"],
            "byte_length": byte_count,
            "sha256": digest.hexdigest(),
            "tool_name": ACQUISITION_TOOL_NAME,
            "tool_version": tool_version,
            "response_headers": _selected_headers(response.headers),
        }
        if observation_id is not None:
            retained["observation_id"] = observation_id
        return retained, byte_count
    finally:
        if response is not None:
            response.close()


def fetch_sources(
    spec_path: Path,
    output: Path,
    *,
    session: Any | None = None,
    now: Callable[[], datetime] | None = None,
    monotonic: Callable[[], float] | None = None,
) -> None:
    spec = read_object(spec_path)
    schema = spec.get("schema")
    if schema == ACQUISITION_SPEC_SCHEMA:
        require_keys(
            spec,
            {"schema", "venue", "environment", "sources"},
            set(),
            "fetch spec",
        )
        observation_id: str | None = None
        acquisition_policy: AcquisitionPolicy | None = None
        evidence_profile: EvidenceProfile | None = None
        tool_version = ACQUISITION_TOOL_VERSION
    elif schema == ACQUISITION_SPEC_V2_SCHEMA:
        require_keys(
            spec,
            {
                "schema", "venue", "environment", "observation_id",
                "acquisition_policy", "acquisition_policy_sha256", "sources",
            },
            set(),
            "fetch spec",
        )
        observation_id = require_string(spec["observation_id"], "fetch observation_id")
        if observation_id not in {"opening", "closing"}:
            fail("EvidenceIncomplete", "fetch observation must be opening or closing")
        policy_relative = Path(require_string(spec["acquisition_policy"], "fetch policy path"))
        if policy_relative.is_absolute() or ".." in policy_relative.parts:
            fail("AcquisitionPolicyMismatch", "fetch policy path must be relative to its spec")
        acquisition_policy = AcquisitionPolicy.load(spec_path.parent / policy_relative)
        if acquisition_policy.payload_sha256 != require_hash(
            spec["acquisition_policy_sha256"], "fetch policy hash"
        ):
            fail("AcquisitionPolicyMismatch", "fetch spec names a different policy")
        tool_version = ACQUISITION_TOOL_V3_VERSION
        evidence_profile = None
    elif schema == ACQUISITION_SPEC_V3_SCHEMA:
        require_keys(
            spec,
            {
                "schema", "venue", "environment", "observation_id",
                "acquisition_policy", "acquisition_policy_sha256",
                "evidence_profile", "evidence_profile_sha256", "sources",
            },
            set(),
            "fetch spec",
        )
        observation_id = require_string(spec["observation_id"], "fetch observation_id")
        if observation_id not in {"opening", "closing"}:
            fail("EvidenceIncomplete", "fetch observation must be opening or closing")
        policy_relative = Path(require_string(spec["acquisition_policy"], "fetch policy path"))
        profile_relative = Path(require_string(spec["evidence_profile"], "fetch profile path"))
        if policy_relative.is_absolute() or ".." in policy_relative.parts:
            fail("AcquisitionPolicyMismatch", "fetch policy path must be relative to its spec")
        if profile_relative.is_absolute() or ".." in profile_relative.parts:
            fail("EvidenceProfileMismatch", "fetch profile path must be relative to its spec")
        acquisition_policy = AcquisitionPolicy.load(spec_path.parent / policy_relative)
        if acquisition_policy.payload_sha256 != require_hash(
            spec["acquisition_policy_sha256"], "fetch policy hash"
        ):
            fail("AcquisitionPolicyMismatch", "fetch spec names a different policy")
        evidence_profile = EvidenceProfile.load(spec_path.parent / profile_relative)
        if evidence_profile.payload_sha256 != require_hash(
            spec["evidence_profile_sha256"], "fetch profile hash"
        ):
            fail("EvidenceProfileMismatch", "fetch spec names a different evidence profile")
        tool_version = ACQUISITION_TOOL_V4_VERSION
    else:
        fail("UnsupportedTermsSchema", f"fetch spec uses unsupported schema {schema!r}")
    if spec["venue"] != "kalshi" or spec["environment"] != "production":
        fail("SourceMissing", "fetch supports only kalshi production sources")
    sources = spec["sources"]
    if not isinstance(sources, list) or not sources:
        fail("SourceMissing", "fetch spec must list at least one source")
    if evidence_profile is not None:
        evidence_profile.verify_spec_sources(sources)
    if output.exists():
        fail("SourceMissing", f"fetch output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = Path(tempfile.mkdtemp(
        prefix=f".{output.name}.", suffix=".partial", dir=output.parent
    ))
    request_session = requests.Session() if session is None else session
    clock = (lambda: datetime.now(timezone.utc)) if now is None else now
    timer = time.monotonic if monotonic is None else monotonic
    acquisition_started_utc = clock()
    package_started = timer()
    retained: list[dict[str, Any]] = []
    total_bytes = 0
    identities: set[str] = set()
    paths: set[str] = set()
    try:
        for index, item in enumerate(sources):
            if not isinstance(item, dict):
                fail("TermsNoncanonical", f"fetch source {index} must be an object")
            require_keys(
                item,
                {"id", "role", "url", "path"},
                {"maximum_bytes", "media_types"},
                f"fetch source {index}",
            )
            identity = require_string(item["id"], f"fetch source {index}.id")
            relative, destination = _safe_output_path(
                partial, item["path"], f"fetch source {index}"
            )
            relative_text = relative.as_posix()
            if identity in identities or relative_text in paths:
                fail("TermsNoncanonical", "fetch source identifiers and paths must be unique")
            if relative_text == "source_manifest.json":
                fail("SourceMissing", "fetch source path collides with source_manifest.json")
            identities.add(identity)
            paths.add(relative_text)
            normalized_item = dict(item)
            normalized_item["path"] = relative_text
            source_record, added_bytes = _request_source(
                request_session,
                normalized_item,
                destination,
                package_bytes=total_bytes,
                package_started=package_started,
                now=clock,
                monotonic=timer,
                observation_id=observation_id,
                tool_version=tool_version,
            )
            if evidence_profile is not None:
                source_record["source_key"] = identity
                source_record["id"] = f"{observation_id}_{identity}"
            total_bytes += added_bytes
            retained.append(source_record)
        retained.sort(key=lambda value: value["id"])
        acquisition = {
            "started_at_utc": format_utc(acquisition_started_utc),
            "completed_at_utc": format_utc(clock()),
            "tool_name": ACQUISITION_TOOL_NAME,
            "tool_version": tool_version,
        }
        if observation_id is None:
            payload = {
                "venue": "kalshi",
                "environment": "production",
                "acquisition": acquisition,
                "sources": retained,
            }
            manifest_schema = SOURCE_MANIFEST_V2_SCHEMA
        elif evidence_profile is None:
            assert acquisition_policy is not None
            acquisition["observation_id"] = observation_id
            payload = {
                "venue": "kalshi",
                "environment": "production",
                "acquisition_policy_sha256": acquisition_policy.payload_sha256,
                "acquisitions": [acquisition],
                "sources": retained,
            }
            manifest_schema = SOURCE_MANIFEST_V3_SCHEMA
            shutil.copyfile(
                acquisition_policy.path, partial / "acquisition_policy.json"
            )
        else:
            assert acquisition_policy is not None
            acquisition["observation_id"] = observation_id
            payload = {
                "venue": "kalshi",
                "environment": "production",
                "acquisition_policy_sha256": acquisition_policy.payload_sha256,
                "evidence_profile_sha256": evidence_profile.payload_sha256,
                "acquisitions": [acquisition],
                "sources": retained,
            }
            manifest_schema = SOURCE_MANIFEST_V4_SCHEMA
            shutil.copyfile(acquisition_policy.path, partial / "acquisition_policy.json")
            shutil.copyfile(evidence_profile.path, partial / "evidence_profile.json")
        _write_new_canonical(
            partial / "source_manifest.json",
            build_envelope(manifest_schema, payload),
        )
        retained_package_bytes = sum(
            member.stat().st_size for member in partial.rglob("*") if member.is_file()
        )
        if retained_package_bytes > MAX_PACKAGE_BYTES:
            fail("AcquisitionPackageTooLarge", "retained package exceeds the package limit")
        SourceEvidence.load(partial)
        partial.rename(output)
    except BaseException as original:
        try:
            shutil.rmtree(partial)
        except OSError as cleanup_error:
            raise ProductTermsError(
                "AcquisitionCleanupFailed",
                f"failed to remove partial acquisition {partial}: {cleanup_error}",
            ) from original
        raise
    finally:
        if session is None:
            request_session.close()


def assemble_observations(opening: Path, closing: Path, output: Path) -> None:
    opening_evidence = SourceEvidence.load(opening)
    closing_evidence = SourceEvidence.load(closing)
    if (
        opening_evidence.schema == SOURCE_MANIFEST_V4_SCHEMA
        and closing_evidence.schema == SOURCE_MANIFEST_V4_SCHEMA
    ):
        _assemble_profile_observations(
            opening, closing, output, opening_evidence, closing_evidence
        )
        return
    if (
        opening_evidence.schema != SOURCE_MANIFEST_V3_SCHEMA
        or closing_evidence.schema != SOURCE_MANIFEST_V3_SCHEMA
        or [item["observation_id"] for item in opening_evidence.payload["acquisitions"]]
        != ["opening"]
        or [item["observation_id"] for item in closing_evidence.payload["acquisitions"]]
        != ["closing"]
    ):
        fail("EvidenceIncomplete", "assembly requires one opening and one closing V3 observation")
    opening_policy = opening_evidence.acquisition_policy
    closing_policy = closing_evidence.acquisition_policy
    assert opening_policy is not None and closing_policy is not None
    if opening_policy.payload_sha256 != closing_policy.payload_sha256:
        fail("AcquisitionPolicyMismatch", "opening and closing use different policies")
    opening_completed = parse_utc(
        opening_evidence.payload["acquisitions"][0]["completed_at_utc"],
        "opening acquisition completion",
    )
    closing_started = parse_utc(
        closing_evidence.payload["acquisitions"][0]["started_at_utc"],
        "closing acquisition start",
    )
    if closing_started <= opening_completed:
        fail("EffectiveWindowGap", "opening and closing observations do not bracket time")
    opening_sources = {item["id"]: item for item in opening_evidence.payload["sources"]}
    closing_sources = {item["id"]: item for item in closing_evidence.payload["sources"]}
    if opening_sources.keys() != closing_sources.keys():
        fail("EvidenceIncomplete", "opening and closing source membership differs")
    for source_id in sorted(opening_sources):
        left = opening_sources[source_id]
        right = closing_sources[source_id]
        for field in ("role", "requested_url", "media_type"):
            if left[field] != right[field]:
                fail("EvidenceIncomplete", f"{source_id} {field} differs across observations")
        if left["role"] not in {
            "event_metadata_record",
            "market_record",
            "series_record_and_contract_document_identity",
        } and left["sha256"] != right["sha256"]:
            fail("EvidenceAnchorMismatch", f"static source {source_id} changed across observations")
    if output.exists():
        fail("SourceMissing", f"assembly output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = Path(tempfile.mkdtemp(
        prefix=f".{output.name}.", suffix=".partial", dir=output.parent
    ))
    try:
        shutil.copyfile(opening_policy.path, partial / "acquisition_policy.json")
        assembled_sources: list[dict[str, Any]] = []
        for observation_id, root, source_map in (
            ("opening", opening, opening_sources),
            ("closing", closing, closing_sources),
        ):
            for source_id, source in sorted(source_map.items()):
                source_path = safe_member(root, source["path"], f"{observation_id} source path")
                original = Path(source["path"])
                parts = list(original.parts)
                if parts and parts[0] == "sources":
                    parts.pop(0)
                if not parts:
                    fail("SourceMissing", f"{observation_id}/{source_id} has no retained relative path")
                relative = Path("sources") / observation_id / Path(*parts)
                destination = partial / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_path, destination)
                assembled = dict(source)
                assembled["id"] = f"{observation_id}_{source_id}"
                assembled["path"] = relative.as_posix()
                assembled_sources.append(assembled)
        payload = {
            "venue": "kalshi",
            "environment": "production",
            "acquisition_policy_sha256": opening_policy.payload_sha256,
            "acquisitions": [
                opening_evidence.payload["acquisitions"][0],
                closing_evidence.payload["acquisitions"][0],
            ],
            "sources": sorted(assembled_sources, key=lambda item: item["id"]),
        }
        _write_new_canonical(
            partial / "source_manifest.json",
            build_envelope(SOURCE_MANIFEST_V3_SCHEMA, payload),
        )
        SourceEvidence.load(partial)
        partial.rename(output)
    except BaseException as original:
        try:
            shutil.rmtree(partial)
        except OSError as cleanup_error:
            raise ProductTermsError(
                "AcquisitionCleanupFailed",
                f"failed to remove partial assembly {partial}: {cleanup_error}",
            ) from original
        raise


def _assemble_profile_observations(
    opening: Path,
    closing: Path,
    output: Path,
    opening_evidence: SourceEvidence,
    closing_evidence: SourceEvidence,
) -> None:
    if (
        [item["observation_id"] for item in opening_evidence.payload["acquisitions"]] != ["opening"]
        or [item["observation_id"] for item in closing_evidence.payload["acquisitions"]] != ["closing"]
    ):
        fail("EvidenceIncomplete", "V4 assembly requires one opening and one closing observation")
    opening_policy = opening_evidence.acquisition_policy
    closing_policy = closing_evidence.acquisition_policy
    opening_profile = opening_evidence.evidence_profile
    closing_profile = closing_evidence.evidence_profile
    assert opening_policy is not None and closing_policy is not None
    assert opening_profile is not None and closing_profile is not None
    if opening_policy.payload_sha256 != closing_policy.payload_sha256:
        fail("AcquisitionPolicyMismatch", "opening and closing use different policies")
    if opening_profile.payload_sha256 != closing_profile.payload_sha256:
        fail("EvidenceProfileMismatch", "opening and closing use different evidence profiles")
    opening_completed = parse_utc(
        opening_evidence.payload["acquisitions"][0]["completed_at_utc"],
        "opening acquisition completion",
    )
    closing_started = parse_utc(
        closing_evidence.payload["acquisitions"][0]["started_at_utc"],
        "closing acquisition start",
    )
    if closing_started <= opening_completed:
        fail("EffectiveWindowGap", "opening and closing observations do not bracket time")
    opening_sources = {item["source_key"]: item for item in opening_evidence.payload["sources"]}
    closing_sources = {item["source_key"]: item for item in closing_evidence.payload["sources"]}
    for source_key in sorted(set(opening_sources) & set(closing_sources)):
        left = opening_sources[source_key]
        right = closing_sources[source_key]
        for field in ("role", "requested_url", "media_type"):
            if left[field] != right[field]:
                fail("EvidenceIncomplete", f"{source_key} {field} differs across observations")
    if output.exists():
        fail("SourceMissing", f"assembly output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = Path(tempfile.mkdtemp(
        prefix=f".{output.name}.", suffix=".partial", dir=output.parent
    ))
    try:
        shutil.copyfile(opening_policy.path, partial / "acquisition_policy.json")
        shutil.copyfile(opening_profile.path, partial / "evidence_profile.json")
        assembled_sources: list[dict[str, Any]] = []
        destinations: set[str] = set()
        for observation_id, root, source_map in (
            ("opening", opening, opening_sources),
            ("closing", closing, closing_sources),
        ):
            for source_key, source in sorted(source_map.items()):
                source_path = safe_member(root, source["path"], f"{observation_id} source path")
                original = Path(source["path"])
                parts = list(original.parts)
                if parts and parts[0] == "sources":
                    parts.pop(0)
                if not parts:
                    fail("SourceMissing", f"{observation_id}/{source_key} has no retained relative path")
                relative = Path("sources") / observation_id / Path(*parts)
                relative_text = relative.as_posix()
                if relative_text in destinations:
                    fail("PackageMembershipMismatch", f"assembled path collision at {relative_text}")
                destinations.add(relative_text)
                destination = partial / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_path, destination)
                assembled = dict(source)
                assembled["id"] = f"{observation_id}_{source_key}"
                assembled["observation_id"] = observation_id
                assembled["path"] = relative_text
                assembled_sources.append(assembled)
        payload = {
            "venue": "kalshi",
            "environment": "production",
            "acquisition_policy_sha256": opening_policy.payload_sha256,
            "evidence_profile_sha256": opening_profile.payload_sha256,
            "acquisitions": [
                opening_evidence.payload["acquisitions"][0],
                closing_evidence.payload["acquisitions"][0],
            ],
            "sources": sorted(assembled_sources, key=lambda item: item["id"]),
        }
        _write_new_canonical(
            partial / "source_manifest.json",
            build_envelope(SOURCE_MANIFEST_V4_SCHEMA, payload),
        )
        SourceEvidence.load(partial)
        partial.rename(output)
    except BaseException as original:
        try:
            shutil.rmtree(partial)
        except OSError as cleanup_error:
            raise ProductTermsError(
                "AcquisitionCleanupFailed",
                f"failed to remove partial assembly {partial}: {cleanup_error}",
            ) from original
        raise


def build_terms(
    payload_path: Path, package: Path, schema: str = PRODUCT_TERMS_SCHEMA
) -> None:
    payload = read_object(payload_path)
    evidence = SourceEvidence.load(package)
    if schema not in {PRODUCT_TERMS_SCHEMA, PRODUCT_TERMS_V2_SCHEMA}:
        fail("UnsupportedTermsSchema", f"cannot build unsupported terms schema {schema!r}")
    _validate_terms_payload(payload, evidence, schema)
    destination = package / "product_terms.json"
    _write_new_canonical(destination, build_envelope(schema, payload))
    try:
        ProductTerms.load(package, evidence)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def build_evidence_map(payload_path: Path, package: Path) -> None:
    evidence = SourceEvidence.load(package)
    product = ProductTerms.load(package, evidence)
    payload = read_object(payload_path)
    destination = package / "evidence_anchors.json"
    schema = (
        EVIDENCE_MAP_V2_SCHEMA
        if evidence.schema == SOURCE_MANIFEST_V4_SCHEMA
        else EVIDENCE_MAP_SCHEMA
    )
    _write_new_canonical(destination, build_envelope(schema, payload))
    try:
        EvidenceMap.load(package, product, evidence)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def review_terms(
    package: Path,
    *,
    reviewed_at_utc: str,
    effective_from_utc: str,
    effective_until_utc: str | None,
    effective_time_basis: str,
    limitations: list[str],
    reviewer: str | None = None,
    responsibilities: list[str] | None = None,
    checklist: list[str] | None = None,
) -> None:
    evidence = SourceEvidence.load(package)
    product = ProductTerms.load(package, evidence)
    parse_utc(reviewed_at_utc, "reviewed_at_utc")
    parse_utc(effective_from_utc, "effective_from_utc")
    if effective_until_utc is not None:
        parse_utc(effective_until_utc, "effective_until_utc")
    if effective_time_basis != product.payload["effective"]["basis"]:
        fail("EffectiveWindowMismatch", "review basis must match the terms payload")
    if (
        effective_from_utc != product.payload["effective"]["from_utc"]
        or effective_until_utc != product.payload["effective"]["until_utc"]
    ):
        fail("EffectiveWindowMismatch", "review interval must match the terms payload")
    payload: dict[str, Any] = {
        "status": "reviewed",
        "reviewed_at_utc": reviewed_at_utc,
        "product_terms_sha256": product.payload_sha256,
        "source_manifest_sha256": evidence.payload_sha256,
        "effective_from_utc": effective_from_utc,
        "effective_until_utc": effective_until_utc,
        "effective_time_basis": effective_time_basis,
        "limitations": limitations,
    }
    schema = PRODUCT_REVIEW_SCHEMA
    if evidence.schema in {SOURCE_MANIFEST_V3_SCHEMA, SOURCE_MANIFEST_V4_SCHEMA}:
        if evidence.acquisition_policy is None:
            fail("AcquisitionPolicyMismatch", "source manifest V3 has no policy")
        if reviewer is None:
            fail("ReviewMissing", "review V2 requires a repository-declared reviewer")
        evidence_map = EvidenceMap.load(package, product, evidence)
        sorted_responsibilities = sorted(set(responsibilities or []))
        checklist_items = checklist or []
        if not sorted_responsibilities or not checklist_items:
            fail("ReviewMissing", "review V2 requires responsibilities and checklist")
        payload.update({
            "reviewer": {
                "identity": reviewer,
                "identity_kind": "repository_declared",
            },
            "responsibilities": sorted_responsibilities,
            "checklist": [
                {"item": item, "status": "accepted"} for item in checklist_items
            ],
            "acquisition_policy_sha256": evidence.acquisition_policy.payload_sha256,
            "evidence_map_sha256": evidence_map.payload_sha256,
        })
        if evidence.schema == SOURCE_MANIFEST_V4_SCHEMA:
            if evidence.evidence_profile is None:
                fail("EvidenceProfileMismatch", "source manifest V4 has no profile")
            payload["evidence_profile_sha256"] = evidence.evidence_profile.payload_sha256
            schema = PRODUCT_REVIEW_V3_SCHEMA
        else:
            schema = PRODUCT_REVIEW_V2_SCHEMA
    destination = package / "review.json"
    _write_new_canonical(destination, build_envelope(schema, payload))
    try:
        ProductReview.load(package, product, evidence)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def _diff_values(left: Any, right: Any, path: str = "$") -> list[dict[str, Any]]:
    if type(left) is not type(right):
        return [{"path": path, "left": left, "right": right}]
    if isinstance(left, dict):
        changes: list[dict[str, Any]] = []
        for key in sorted(set(left) | set(right)):
            if key not in left:
                changes.append({"path": f"{path}.{key}", "left": None, "right": right[key]})
            elif key not in right:
                changes.append({"path": f"{path}.{key}", "left": left[key], "right": None})
            else:
                changes.extend(_diff_values(left[key], right[key], f"{path}.{key}"))
        return changes
    if isinstance(left, list):
        changes = []
        for index in range(max(len(left), len(right))):
            if index >= len(left):
                changes.append({"path": f"{path}[{index}]", "left": None, "right": right[index]})
            elif index >= len(right):
                changes.append({"path": f"{path}[{index}]", "left": left[index], "right": None})
            else:
                changes.extend(_diff_values(left[index], right[index], f"{path}[{index}]"))
        return changes
    return [] if left == right else [{"path": path, "left": left, "right": right}]


def diff_packages(left: ProductPackage, right: ProductPackage) -> dict[str, Any]:
    return {
        "schema": "pmm.product_terms_diff.v1",
        "left_product_terms_sha256": left.terms.payload_sha256,
        "right_product_terms_sha256": right.terms.payload_sha256,
        "changes": _diff_values(left.terms.payload, right.terms.payload),
    }


def assess_legacy(normalized: Path, package: ProductPackage, policy: ConversionPolicy) -> dict[str, Any]:
    manifest_path = normalized / "manifest.json"
    product_path = normalized / "product.json"
    events_path = normalized / "events.jsonl"
    if not manifest_path.is_file() or not product_path.is_file() or not events_path.is_file():
        fail("SourceMissing", "legacy normalized directory is incomplete")
    manifest = read_object(manifest_path)
    product = read_object(product_path)
    if manifest.get("schema") != "pmm.historical.normalization_manifest.v1" or product.get("schema") != "pmm.historical.product_map.v1":
        fail("UnsupportedTermsSchema", "assess-legacy requires normalization/product V1")
    ticker_match = product.get("ticker") == package.terms.market_ticker == manifest.get("ticker")
    if not ticker_match:
        fail("MarketTickerMismatch", "legacy product, manifest, and reviewed terms differ")
    event_count = 0
    for line_number, line in enumerate(events_path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            fail("TermsNoncanonical", f"legacy event line {line_number} is invalid: {error}")
        payload = event.get("payload")
        if not isinstance(payload, dict):
            fail("TermsNoncanonical", f"legacy event line {line_number} has no payload")
        event_type = event.get("event_type")
        if event_type == "book_snapshot":
            for side in ("yes_bids", "yes_asks"):
                for index, level in enumerate(payload.get(side, [])):
                    package.terms.validate_price(level.get("price_dollars"), f"line {line_number}.{side}[{index}].price")
                    package.terms.validate_quantity(level.get("quantity_contracts"), f"line {line_number}.{side}[{index}].quantity")
        elif event_type == "book_delta":
            package.terms.validate_price(payload.get("price_dollars"), f"line {line_number}.price")
            package.terms.validate_quantity(payload.get("quantity_delta_contracts"), f"line {line_number}.quantity", allow_negative=True)
        elif event_type == "trade":
            package.terms.validate_price(payload.get("yes_price_dollars"), f"line {line_number}.yes_price")
            package.terms.validate_price(payload.get("no_price_dollars"), f"line {line_number}.no_price")
            package.terms.validate_quantity(payload.get("quantity_contracts"), f"line {line_number}.quantity")
        else:
            fail("TermsNoncanonical", f"legacy event line {line_number} has an unsupported type")
        event_count += 1
    policy.require_core_compatible(package.terms)
    return {
        "schema": "pmm.legacy_product_terms_assessment.v1",
        "status": "regeneration_supported",
        "market_ticker": package.terms.market_ticker,
        "event_count": event_count,
        "product_terms_sha256": package.terms.payload_sha256,
        "conversion_policy_sha256": policy.payload_sha256,
        "missing_legacy_lineage": [
            "source_manifest_sha256",
            "product_terms_sha256",
            "review_sha256",
            "conversion_policy_sha256",
            "product_identity_sha256",
        ],
        "required_action": "Regenerate a new V2 artifact; never relabel or edit this V1 directory.",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Authoritative product-term package tools.")
    commands = parser.add_subparsers(dest="command", required=True)
    verify_package = commands.add_parser("verify-package")
    verify_package.add_argument("--package", required=True, type=Path)
    verify_catalog = commands.add_parser("verify-catalog")
    verify_catalog.add_argument("--catalog", required=True, type=Path)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--package", required=True, type=Path)
    fetch = commands.add_parser("fetch")
    fetch.add_argument("--spec", required=True, type=Path)
    fetch.add_argument("--output", required=True, type=Path)
    assemble = commands.add_parser("assemble-observations")
    assemble.add_argument("--opening", required=True, type=Path)
    assemble.add_argument("--closing", required=True, type=Path)
    assemble.add_argument("--output", required=True, type=Path)
    build = commands.add_parser("build")
    build.add_argument("--payload", required=True, type=Path)
    build.add_argument("--package", required=True, type=Path)
    build.add_argument(
        "--schema",
        choices=(PRODUCT_TERMS_SCHEMA, PRODUCT_TERMS_V2_SCHEMA),
        default=PRODUCT_TERMS_SCHEMA,
    )
    build_evidence = commands.add_parser("build-evidence")
    build_evidence.add_argument("--payload", required=True, type=Path)
    build_evidence.add_argument("--package", required=True, type=Path)
    review = commands.add_parser("review")
    review.add_argument("--package", required=True, type=Path)
    review.add_argument("--reviewed-at", required=True)
    review.add_argument("--effective-from", required=True)
    review.add_argument("--effective-until")
    review.add_argument(
        "--basis",
        required=True,
        choices=("venue_explicit", "source_revision_timestamp", "contemporaneous_snapshot", "reviewed_retrospective"),
    )
    review.add_argument("--limitation", action="append", default=[])
    review.add_argument("--reviewer")
    review.add_argument("--responsibility", action="append", default=[])
    review.add_argument("--checklist-item", action="append", default=[])
    compare = commands.add_parser("compare")
    compare.add_argument("--left", required=True, type=Path)
    compare.add_argument("--right", required=True, type=Path)
    compare.add_argument("--left-policy", required=True, type=Path)
    compare.add_argument("--right-policy", required=True, type=Path)
    diff = commands.add_parser("diff")
    diff.add_argument("--left", required=True, type=Path)
    diff.add_argument("--right", required=True, type=Path)
    assess = commands.add_parser("assess-legacy")
    assess.add_argument("--normalized", required=True, type=Path)
    assess.add_argument("--package", required=True, type=Path)
    assess.add_argument("--conversion-policy", required=True, type=Path)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.command == "verify-package":
            package = ProductPackage.load(args.package)
            result = {"status": "valid", "market_ticker": package.terms.market_ticker, "product_terms_sha256": package.terms.payload_sha256}
        elif args.command == "verify-catalog":
            catalog = ProductCatalog.load(args.catalog)
            result = {"status": "valid", "entries": len(catalog.payload["entries"]), "catalog_sha256": catalog.payload_sha256}
        elif args.command == "inspect":
            package = ProductPackage.load(args.package)
            result = {"identity": package.terms.identity, "effective": package.terms.payload["effective"], "hashes": {"terms": package.terms.payload_sha256, "sources": package.evidence.payload_sha256, "review": package.review.payload_sha256}, "limitations": package.review.payload["limitations"]}
        elif args.command == "fetch":
            fetch_sources(args.spec, args.output)
            result = {"status": "fetched", "output": str(args.output)}
        elif args.command == "assemble-observations":
            assemble_observations(args.opening, args.closing, args.output)
            result = {"status": "assembled", "output": str(args.output)}
        elif args.command == "build":
            build_terms(args.payload, args.package, args.schema)
            result = {"status": "built", "package": str(args.package)}
        elif args.command == "build-evidence":
            build_evidence_map(args.payload, args.package)
            result = {"status": "built", "package": str(args.package)}
        elif args.command == "review":
            review_terms(
                args.package,
                reviewed_at_utc=args.reviewed_at,
                effective_from_utc=args.effective_from,
                effective_until_utc=args.effective_until,
                effective_time_basis=args.basis,
                limitations=args.limitation,
                reviewer=args.reviewer,
                responsibilities=args.responsibility,
                checklist=args.checklist_item,
            )
            result = {"status": "reviewed", "package": str(args.package)}
        elif args.command == "compare":
            result = compatibility_report(ProductPackage.load(args.left), ProductPackage.load(args.right), ConversionPolicy.load(args.left_policy), ConversionPolicy.load(args.right_policy))
        elif args.command == "diff":
            result = diff_packages(ProductPackage.load(args.left), ProductPackage.load(args.right))
        else:
            result = assess_legacy(
                args.normalized,
                ProductPackage.load(args.package),
                ConversionPolicy.load(args.conversion_policy),
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, requests.RequestException, ProductTermsError) as error:
        print(f"error: {error}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
