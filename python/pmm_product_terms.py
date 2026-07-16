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
import shutil
import tempfile
import time
from typing import Any, Callable, Iterable
from urllib.parse import urljoin, urlparse

import requests


SOURCE_MANIFEST_SCHEMA = "pmm.product_terms_source_manifest.v1"
SOURCE_MANIFEST_V2_SCHEMA = "pmm.product_terms_source_manifest.v2"
ACQUISITION_SPEC_SCHEMA = "pmm.product_acquisition_spec.v1"
PRODUCT_TERMS_SCHEMA = "pmm.venue_product_terms.v1"
PRODUCT_REVIEW_SCHEMA = "pmm.product_terms_review.v1"
PRODUCT_CATALOG_SCHEMA = "pmm.product_catalog.v1"
CONVERSION_POLICY_SCHEMA = "pmm.product_conversion_policy.v1"
COMPATIBILITY_REPORT_SCHEMA = "pmm.product_compatibility_report.v1"

SHA256_LENGTH = 64
ACQUISITION_TOOL_NAME = "pmm_product_terms"
ACQUISITION_TOOL_VERSION = "product-acquisition.v2"
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


def _validate_acquisition_summary(value: Any) -> None:
    if not isinstance(value, dict):
        fail("TermsNoncanonical", "source acquisition summary must be an object")
    require_keys(
        value,
        {"started_at_utc", "completed_at_utc", "tool_name", "tool_version"},
        set(),
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
    source: dict[str, Any], context: str, role: str
) -> None:
    if role not in ROLE_POLICIES:
        fail("TermsNoncanonical", f"{context}.role is unsupported")
    requested_url = approved_source_url(source["requested_url"], f"{context}.requested_url")
    final_url = approved_source_url(source["final_url"], f"{context}.final_url")
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
        resolved_url = approved_source_url(
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

    @classmethod
    def load(cls, package: Path) -> "SourceEvidence":
        path = package / "source_manifest.json"
        if not path.is_file():
            fail("SourceMissing", f"{path} is missing")
        document = read_object(path)
        schema = document.get("schema")
        if schema not in {SOURCE_MANIFEST_SCHEMA, SOURCE_MANIFEST_V2_SCHEMA}:
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
        else:
            require_keys(
                payload,
                {"venue", "environment", "acquisition", "sources"},
                set(),
                "source payload",
            )
            _validate_acquisition_summary(payload["acquisition"])
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
                require_keys(
                    source,
                    {
                        "id", "role", "requested_url", "final_url", "redirect_history",
                        "http_status", "media_type", "retrieval_started_at_utc",
                        "retrieval_completed_at_utc", "elapsed_milliseconds", "path",
                        "byte_length", "sha256", "tool_name", "tool_version",
                        "response_headers",
                    },
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
                _validate_acquired_source_metadata(source, context, role)
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
        return cls(payload, payload_hash, sha256_file(path), hashes, schema)


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
        payload, payload_hash = validate_envelope(path, PRODUCT_TERMS_SCHEMA, "TermsHashMismatch")
        _validate_terms_payload(payload, evidence)
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


def _validate_terms_payload(payload: dict[str, Any], evidence: SourceEvidence) -> None:
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
    _validate_rules_lifecycle_settlement_fees(payload)
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

    market_document = _retained_json(package, evidence, "market_record")
    series_document = _retained_json(package, evidence, "series_record")
    metadata = _retained_json(package, evidence, "event_metadata")
    market = market_document.get("market")
    series = series_document.get("series")
    if not isinstance(market, dict) or not isinstance(series, dict):
        fail("SourceTermsMismatch", "retained market or series response has an unexpected shape")

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
        _require_source_equal(identity[term_field], market.get(source_field), f"identity.{term_field}")
    _require_source_equal(identity["series_ticker"], series.get("ticker"), "identity.series_ticker")

    price = payload["price"]
    _require_source_equal(price["level_structure"], market.get("price_level_structure"), "price.level_structure")
    source_ranges = market.get("price_ranges")
    projected_ranges = [
        {"start": item["start_dollars"], "end": item["end_dollars"], "step": item["step_dollars"]}
        for item in price["ranges"]
    ]
    _require_source_equal(projected_ranges, source_ranges, "price.ranges")

    payout = payload["payout"]
    _require_source_equal(
        payout["notional_value_dollars"], market.get("notional_value_dollars"),
        "payout.notional_value_dollars",
    )
    rules = payload["rules"]
    _require_source_equal(rules["primary"], market.get("rules_primary"), "rules.primary")
    _require_source_equal(rules["secondary"], market.get("rules_secondary"), "rules.secondary")
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
        _require_source_equal(payload["lifecycle"][term_field], market.get(source_field), f"lifecycle.{term_field}")

    _require_source_equal(payload["settlement"]["sources"], metadata.get("settlement_sources"), "settlement.sources")
    _require_source_equal(payload["settlement"]["sources"], series.get("settlement_sources"), "settlement.sources")
    _require_source_equal(payload["fees"]["series_fee_type"], series.get("fee_type"), "fees.series_fee_type")
    try:
        source_multiplier = Decimal(str(series.get("fee_multiplier")))
    except InvalidOperation:
        fail("SourceTermsMismatch", "retained series fee multiplier is invalid")
    if Decimal(payload["fees"]["series_fee_multiplier"]) != source_multiplier:
        fail("SourceTermsMismatch", "reviewed terms fees.series_fee_multiplier differs from retained source evidence")


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


def _validate_rules_lifecycle_settlement_fees(payload: dict[str, Any]) -> None:
    rules = payload["rules"]
    if not isinstance(rules, dict):
        fail("TermsNoncanonical", "terms.rules must be an object")
    require_keys(rules, {"primary", "secondary", "contract_terms_source"}, set(), "terms.rules")
    require_string(rules["primary"], "terms.rules.primary")
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


@dataclass(frozen=True)
class ProductReview:
    payload: dict[str, Any]
    payload_sha256: str
    file_sha256: str

    @classmethod
    def load(cls, package: Path, terms: ProductTerms, evidence: SourceEvidence) -> "ProductReview":
        path = package / "review.json"
        if not path.is_file():
            fail("ReviewMissing", f"{path} is missing")
        payload, payload_hash = validate_envelope(path, PRODUCT_REVIEW_SCHEMA, "ReviewHashMismatch")
        require_keys(payload, {"status", "reviewed_at_utc", "product_terms_sha256", "source_manifest_sha256", "effective_from_utc", "effective_until_utc", "effective_time_basis", "limitations"}, set(), "review payload")
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
        return cls(payload, payload_hash, sha256_file(path))

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
            "tool_version": ACQUISITION_TOOL_VERSION,
            "response_headers": _selected_headers(response.headers),
        }
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
    require_keys(spec, {"schema", "venue", "environment", "sources"}, set(), "fetch spec")
    if spec["schema"] != ACQUISITION_SPEC_SCHEMA:
        fail("UnsupportedTermsSchema", f"fetch spec must use {ACQUISITION_SPEC_SCHEMA}")
    if spec["venue"] != "kalshi" or spec["environment"] != "production":
        fail("SourceMissing", "fetch supports only kalshi production sources")
    sources = spec["sources"]
    if not isinstance(sources, list) or not sources:
        fail("SourceMissing", "fetch spec must list at least one source")
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
            )
            total_bytes += added_bytes
            retained.append(source_record)
        retained.sort(key=lambda value: value["id"])
        payload = {
            "venue": "kalshi",
            "environment": "production",
            "acquisition": {
                "started_at_utc": format_utc(acquisition_started_utc),
                "completed_at_utc": format_utc(clock()),
                "tool_name": ACQUISITION_TOOL_NAME,
                "tool_version": ACQUISITION_TOOL_VERSION,
            },
            "sources": retained,
        }
        _write_new_canonical(
            partial / "source_manifest.json",
            build_envelope(SOURCE_MANIFEST_V2_SCHEMA, payload),
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


def build_terms(payload_path: Path, package: Path) -> None:
    payload = read_object(payload_path)
    evidence = SourceEvidence.load(package)
    _validate_terms_payload(payload, evidence)
    destination = package / "product_terms.json"
    _write_new_canonical(destination, build_envelope(PRODUCT_TERMS_SCHEMA, payload))
    ProductTerms.load(package, evidence)


def review_terms(
    package: Path,
    *,
    reviewed_at_utc: str,
    effective_from_utc: str,
    effective_until_utc: str | None,
    effective_time_basis: str,
    limitations: list[str],
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
    payload = {
        "status": "reviewed",
        "reviewed_at_utc": reviewed_at_utc,
        "product_terms_sha256": product.payload_sha256,
        "source_manifest_sha256": evidence.payload_sha256,
        "effective_from_utc": effective_from_utc,
        "effective_until_utc": effective_until_utc,
        "effective_time_basis": effective_time_basis,
        "limitations": limitations,
    }
    destination = package / "review.json"
    _write_new_canonical(destination, build_envelope(PRODUCT_REVIEW_SCHEMA, payload))
    ProductReview.load(package, product, evidence)


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
    build = commands.add_parser("build")
    build.add_argument("--payload", required=True, type=Path)
    build.add_argument("--package", required=True, type=Path)
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
        elif args.command == "build":
            build_terms(args.payload, args.package)
            result = {"status": "built", "package": str(args.package)}
        elif args.command == "review":
            review_terms(
                args.package,
                reviewed_at_utc=args.reviewed_at,
                effective_from_utc=args.effective_from,
                effective_until_utc=args.effective_until,
                effective_time_basis=args.basis,
                limitations=args.limitation,
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
