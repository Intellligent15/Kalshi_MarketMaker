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
from pathlib import Path
import shutil
from typing import Any, Iterable
from urllib.parse import urlparse

import requests


SOURCE_MANIFEST_SCHEMA = "pmm.product_terms_source_manifest.v1"
PRODUCT_TERMS_SCHEMA = "pmm.venue_product_terms.v1"
PRODUCT_REVIEW_SCHEMA = "pmm.product_terms_review.v1"
PRODUCT_CATALOG_SCHEMA = "pmm.product_catalog.v1"
CONVERSION_POLICY_SCHEMA = "pmm.product_conversion_policy.v1"
COMPATIBILITY_REPORT_SCHEMA = "pmm.product_compatibility_report.v1"

SHA256_LENGTH = 64
ALLOWED_SOURCE_HOSTS = {
    "api.elections.kalshi.com",
    "external-api.kalshi.com",
    "docs.kalshi.com",
    "kalshi.com",
    "www.kalshi.com",
    "kalshi-public-docs.s3.amazonaws.com",
    "kalshi-public-docs.s3.us-east-1.amazonaws.com",
}


class ProductTermsError(ValueError):
    """Stable refusal category plus a human-readable diagnostic."""

    def __init__(self, code: str, message: str) -> None:
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


@dataclass(frozen=True)
class SourceEvidence:
    payload: dict[str, Any]
    payload_sha256: str
    file_sha256: str
    source_hashes: dict[str, str]

    @classmethod
    def load(cls, package: Path) -> "SourceEvidence":
        path = package / "source_manifest.json"
        if not path.is_file():
            fail("SourceMissing", f"{path} is missing")
        payload, payload_hash = validate_envelope(path, SOURCE_MANIFEST_SCHEMA, "SourceHashMismatch")
        require_keys(payload, {"venue", "environment", "retrieved_at_utc", "sources"}, set(), "source payload")
        if payload["venue"] != "kalshi" or payload["environment"] != "production":
            fail("TermsNoncanonical", "source venue/environment must be kalshi/production")
        parse_utc(payload["retrieved_at_utc"], "source.retrieved_at_utc")
        sources = payload["sources"]
        if not isinstance(sources, list) or not sources:
            fail("SourceMissing", "source payload must list retained sources")
        identities: list[str] = []
        hashes: dict[str, str] = {}
        for index, source in enumerate(sources):
            context = f"source.sources[{index}]"
            if not isinstance(source, dict):
                fail("TermsNoncanonical", f"{context} must be an object")
            require_keys(
                source,
                {"id", "role", "url", "retrieved_at_utc", "media_type", "path", "byte_length", "sha256"},
                {"content_encoding", "venue_updated_at"},
                context,
            )
            identity = require_string(source["id"], f"{context}.id")
            identities.append(identity)
            require_string(source["role"], f"{context}.role")
            url = require_string(source["url"], f"{context}.url")
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.hostname not in ALLOWED_SOURCE_HOSTS:
                fail("SourceMissing", f"{context}.url is not an approved first-party source")
            parse_utc(source["retrieved_at_utc"], f"{context}.retrieved_at_utc")
            require_string(source["media_type"], f"{context}.media_type")
            path_value = safe_member(package, source["path"], f"{context}.path")
            raw = path_value.read_bytes()
            if source.get("content_encoding") == "base64":
                try:
                    raw = base64.b64decode(raw, validate=True)
                except ValueError as error:
                    fail("SourceHashMismatch", f"{context} has invalid base64: {error}")
            elif source.get("content_encoding") not in {None, "identity"}:
                fail("TermsNoncanonical", f"{context}.content_encoding is unsupported")
            if require_integer(source["byte_length"], f"{context}.byte_length") != len(raw):
                fail("SourceHashMismatch", f"{context} byte length is stale")
            expected = require_hash(source["sha256"], f"{context}.sha256")
            if sha256_bytes(raw) != expected:
                fail("SourceHashMismatch", f"{context} content hash is stale")
            hashes[identity] = expected
        if identities != sorted(identities) or len(identities) != len(set(identities)):
            fail("TermsNoncanonical", "source identifiers must be unique and sorted")
        return cls(payload, payload_hash, sha256_file(path), hashes)


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
    if not isinstance(refs, list) or refs != sorted(refs) or len(refs) != len(set(refs)):
        fail("TermsNoncanonical", "terms.source_refs must be a sorted unique list")
    if not refs or any(reference not in evidence.source_hashes for reference in refs):
        fail("SourceMissing", "terms reference missing retained source evidence")


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
            fail("ReviewHashMismatch", "review and terms effective-time basis differ")
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
        if not isinstance(entries, list):
            fail("TermsNoncanonical", "catalog entries must be a list")
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
            if entry["effective_until_utc"] is not None:
                parse_utc(entry["effective_until_utc"], f"catalog entry {index}.effective_until_utc")
            for name in ("product_terms_sha256", "source_manifest_sha256", "review_sha256"):
                require_hash(entry[name], f"catalog entry {index}.{name}")
            keys.append((entry["market_ticker"], entry["effective_from_utc"]))
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            fail("CatalogAmbiguous", "catalog entries must be uniquely sorted by market and effective time")
        catalog = cls(resolved, payload, payload_hash, sha256_file(path))
        catalog.verify()
        return catalog

    def _package_for(self, entry: dict[str, Any]) -> ProductPackage:
        package_path = (self.root / entry["package"]).resolve()
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
        matches: list[ProductPackage] = []
        for entry in self.payload["entries"]:
            if entry["market_ticker"] != ticker:
                continue
            package = self._package_for(entry)
            if package.review.covers(started, ended):
                matches.append(package)
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


def fetch_sources(spec_path: Path, output: Path) -> None:
    spec = read_object(spec_path)
    require_keys(spec, {"venue", "environment", "retrieved_at_utc", "sources"}, set(), "fetch spec")
    if spec["venue"] != "kalshi" or spec["environment"] != "production":
        fail("SourceMissing", "fetch supports only kalshi production sources")
    parse_utc(spec["retrieved_at_utc"], "fetch.retrieved_at_utc")
    if output.exists() or output.with_name(output.name + ".partial").exists():
        fail("SourceMissing", f"fetch output already exists: {output}")
    partial = output.with_name(output.name + ".partial")
    partial.mkdir(parents=True)
    retained: list[dict[str, Any]] = []
    try:
        for index, item in enumerate(spec["sources"]):
            if not isinstance(item, dict):
                fail("TermsNoncanonical", f"fetch source {index} must be an object")
            require_keys(item, {"id", "role", "url", "path"}, set(), f"fetch source {index}")
            url = require_string(item["url"], f"fetch source {index}.url")
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.hostname not in ALLOWED_SOURCE_HOSTS:
                fail("SourceMissing", f"fetch source {index} is not an approved first-party URL")
            response = requests.get(url, timeout=30, allow_redirects=True)
            response.raise_for_status()
            relative = Path(require_string(item["path"], f"fetch source {index}.path"))
            if relative.is_absolute() or ".." in relative.parts:
                fail("SourceMissing", f"fetch source {index} path is unsafe")
            destination = partial / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(response.content)
            retained.append({
                "id": require_string(item["id"], f"fetch source {index}.id"),
                "role": require_string(item["role"], f"fetch source {index}.role"),
                "url": url,
                "retrieved_at_utc": spec["retrieved_at_utc"],
                "media_type": response.headers.get("Content-Type", "application/octet-stream").split(";", 1)[0],
                "path": relative.as_posix(),
                "byte_length": len(response.content),
                "sha256": sha256_bytes(response.content),
            })
        retained.sort(key=lambda value: value["id"])
        payload = {"venue": "kalshi", "environment": "production", "retrieved_at_utc": spec["retrieved_at_utc"], "sources": retained}
        _write_new_canonical(partial / "source_manifest.json", build_envelope(SOURCE_MANIFEST_SCHEMA, payload))
        SourceEvidence.load(partial)
        partial.rename(output)
    except Exception:
        shutil.rmtree(partial, ignore_errors=True)
        raise


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
        fail("ReviewHashMismatch", "review basis must match the terms payload")
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
