# Product Terms Refusal Codes

## Compatibility policy

`ProductTermsError.code` is a public product-package, acquisition, conversion, and offline-lineage
compatibility surface. Existing names and meanings may not be removed, renamed, or repurposed
without an explicitly versioned successor. New codes may be added. Human-readable text may gain
paths and field context and is not byte-stable.

The product-term and Phase 7 CLIs use:

| Outcome | Exit | stdout | stderr |
|---|---:|---|---|
| Success | 0 | one JSON result | empty |
| Expected refusal | 2 | empty | `error: CODE: diagnostic` |
| Argument usage error | 2 | empty | argparse usage text |
| Unexpected programming failure | 1 | unspecified | traceback |

Automation should match the code and exit status, not the complete diagnostic. A retry is useful
only when the table identifies an external or transient condition. Retrying an unchanged invalid
artifact must produce the same refusal.

## Acquisition codes

| Code | Meaning | Retry guidance |
|---|---|---|
| `AcquisitionUrlRejected` | A requested or observed URL is outside the approved HTTPS boundary or has unsafe authority/fragment syntax. | Correct the specification or first-party destination. |
| `AcquisitionRedirectRejected` | A redirect is missing, unsupported, unrecorded, downgraded, or leaves the approved boundary. | Inspect the retained diagnostic; do not bypass validation. |
| `AcquisitionRedirectLimit` | More than five redirect hops were required. | Retry only after the official chain is corrected. |
| `AcquisitionHttpStatusRejected` | The final response was not 2xx. | Retry may help for a transient official error. |
| `AcquisitionTimeout` | Connect, read, per-source, or package deadline expired. | Retry may help; never raise limits silently. |
| `AcquisitionTransportFailure` | The HTTP transport failed before a validated response completed. | Retry may help for a transient network failure. |
| `AcquisitionSourceTooLarge` | Declared or streamed source bytes exceeded the role/specification limit. | Review the source and policy; do not truncate it. |
| `AcquisitionPackageTooLarge` | Total retained package bytes exceeded 64 MiB. | Review package composition and policy. |
| `AcquisitionMediaTypeMismatch` | Response media type is not allowed for the declared role. | Correct the URL/role or investigate an error page. |
| `AcquisitionContentInvalid` | Encoding, length, JSON, UTF-8, PDF signature, or retained content validation failed. | Reacquire only after identifying the official-source problem. |
| `AcquisitionCleanupFailed` | The tool could not remove a partial acquisition after another failure. | Operator cleanup is required before reuse. |
| `AcquisitionPolicyMismatch` | A V2/V3 acquisition names a missing, changed, or unsupported immutable policy identity. | Use the exact supported policy or design a versioned successor; do not reinterpret old evidence. |

## Package, review, and catalog codes

| Code | Meaning |
|---|---|
| `SourceMissing` | A required source, package member, safe path, catalog root, or immutable output precondition is absent. |
| `SourceHashMismatch` | Retained source bytes, decoded length, or source-manifest payload no longer match their digest. |
| `SourceTermsMismatch` | Canonical product terms disagree with mechanically projected retained venue records. |
| `PackageMembershipMismatch` | Package files differ from the exact source-manifest plus terms/review membership. |
| `TermsHashMismatch` | Product-term payload/file identity is stale or changed. |
| `TermsNoncanonical` | JSON shape, keys, scalar representation, timestamp, ordering, or canonical bytes violate the format. |
| `UnsupportedTermsSchema` | The named schema/version is not supported at that boundary. |
| `ReviewMissing` | A package has no review envelope. |
| `ReviewNotApproved` | The runtime package review status is not `reviewed`. |
| `ReviewHashMismatch` | Review input hashes do not name the package's exact terms and source manifest. |
| `CatalogHashMismatch` | A catalog payload or entry names stale package hashes. |
| `CatalogAmbiguous` | Catalog ordering/membership is duplicated or more than one revision matches. |
| `EffectiveWindowMismatch` | Terms, review, and catalog endpoints or terms/review basis differ. |
| `EffectiveWindowGap` | An interval is empty/invalid or no catalog revision covers the requested capture. |
| `EffectiveWindowOverlap` | Two revisions for one market overlap. |
| `EvidenceAnchorMismatch` | A JSON pointer, Markdown heading, PDF page/section, source hash, or endpoint binding does not resolve to the retained evidence. |
| `EvidenceIncomplete` | Required sources, both observations, anchors, responsibilities, or review checklist coverage are incomplete. |
| `EvidenceProfileMismatch` | A successor package names a missing, stale, unsupported, or cross-artifact-inconsistent immutable evidence-profile identity. |
| `CaptureOutsideEffectiveWindow` | Capture time is reversed or outside the selected exact interval. |
| `SeriesTickerMismatch` | Catalog and reviewed series identity differ. |
| `EventTickerMismatch` | Catalog and reviewed event identity differ. |
| `MarketTickerMismatch` | Capture, catalog, legacy artifact, or reviewed market identity differ. |

## Economic-shape and conversion codes

| Code | Meaning |
|---|---|
| `InvalidPriceRange` | Price representation, bounds, steps, contiguity, or complete 0–1 coverage is invalid. |
| `PriceOffVenueGrid` | An observed price is not on the reviewed venue grid. |
| `InvalidQuantityIncrement` | Quantity representation or positive increment is invalid. |
| `QuantityOffVenueIncrement` | An observed quantity is not divisible by the reviewed venue increment. |
| `ComplementaryPriceMismatch` | A trade's exact YES and NO prices do not sum to one dollar. |
| `UnsupportedMarketType` | The product is not the supported binary market type. |
| `UnsupportedPayout` | Payout/settlement shape exceeds the current one-dollar unsupported-settlement boundary. |
| `FeeTermsMissing` | Required fee identity is absent or malformed. |
| `FeePolicyUnsupported` | A path attempts to apply fees/accounting where B1 explicitly forbids it. |
| `ConversionPolicyMismatch` | The repository conversion policy is absent, stale, or unsupported. |
| `CorePriceNotRepresentable` | A valid venue price cannot be converted to exact integer cents. |
| `CoreQuantityNotRepresentable` | A valid venue quantity cannot be converted to exact whole contracts. |

## Offline lineage code

| Code | Meaning |
|---|---|
| `UpstreamManifestMismatch` | A normalization, product-map, package, policy, feature, configuration, result metadata, or result-artifact hash/binding is stale. |

The registry does not claim that every ordinary Phase 7 `ValueError` is a product-term refusal.
Only product package, acquisition, exact conversion, and authoritative V3 lineage failures belong
to this compatibility surface.

`EvidenceProfileMismatch` is deliberately narrow. Missing, duplicate, asymmetric, or
not-applicable-but-present roles remain `EvidenceIncomplete`; document extraction, page, section,
ambiguity, normalization, or fingerprint defects remain `EvidenceAnchorMismatch`; and acquisition
media/content failures retain their existing acquisition codes. The new profile code must not be
used as a generic replacement for those categories.
