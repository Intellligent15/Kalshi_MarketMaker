# ADR-010: Authoritative product terms and artifact lineage

- Status: Accepted
- Date: 2026-07-16
- Scope: Phase 7 Track B1a

## Context and alternatives

The V1 normalizer writes `pmm.historical.product_map.v1` from raw-capture metadata and WebSocket
messages. Its ticker and venue market UUID identify the captured stream, but they do not establish
the venue contract's price grid, quantity increment, payout, lifecycle, settlement sources, fees,
or event/series identity. Treating that projection as authoritative would give captured identity
and independently sourced terms the same owner.

Three ownership models were considered:

| Model | Provenance and refresh | Determinism and coupling | Duplication and migration | Multi-market/testability |
|---|---|---|---|---|
| Extend `product.json` | Blends capture evidence with venue records and obscures which source changed | Offline after normalization, but normalization owns unrelated acquisition concerns | Least files, highest risk of silently reinterpreting V1 | Awkward to review or reuse one terms revision across captures |
| Separate immutable terms artifact | Preserves retained source bytes, review, effective time, and independent hashes | Offline runtime; capture and terms are joined by identity and time | Small copied bundle per normalized dataset; V1 remains untouched | Reusable catalog revisions and mutation-focused fixtures |
| Configuration-owned terms | Explicit for a run, but easy for configurations to duplicate or hand-edit venue facts | Backtest becomes the first validation point and normalization can remain ambiguous | Low normalized duplication, high config drift | Weak binding between features and the terms under which they were normalized |

## Decision

Use the second model. A reviewed product package is the smallest auditable ownership boundary. It
contains retained first-party source bytes, a source manifest, a canonical projection of the terms,
and a separate human review decision. A catalog selects exactly one revision by venue market ticker
and capture interval. A conversion-policy artifact separately states what the current integer core
can represent. Network retrieval is an explicit operator command and is never part of
normalization, feature generation, backtesting, lineage verification, or tests.

The schemas are:

- `pmm.product_terms_source_manifest.v1`: exact source URLs, retrieval times, paths, byte lengths,
  media types, and SHA-256 digests;
- `pmm.venue_product_terms.v1`: the reviewed, market-specific canonical projection;
- `pmm.product_terms_review.v1`: approval, effective-time basis, exact input hashes, and limitations;
- `pmm.product_catalog.v1`: deterministic revision lookup;
- `pmm.product_conversion_policy.v1`: repository conversion and unsupported-behavior policy; and
- `pmm.product_compatibility_report.v1`: explicit comparison outcome and mismatch reasons.

Formal JSON Schemas live under `schemas/product_terms/`; the Python loader additionally enforces
canonical bytes, exact fields, semantic relationships, safe paths, package membership, source-to-
terms agreement, non-overlapping catalog windows, and cross-artifact hashes.

## Field contract

| Product-term field | Type and unit | Required | Authority and version semantics | Validation and absence behavior |
|---|---|---:|---|---|
| `venue`, `environment` | identifiers | yes | package/source manifest; revision-wide | exactly `kalshi`/`production`; refuse otherwise |
| `revision_label` | string | yes | repository review identity | descriptive only; content hash is exact identity; refuse if absent |
| `effective.{from_utc,until_utc,basis}` | RFC3339 UTC interval | yes | retained timestamps plus review conclusion | non-empty interval; complete capture must be covered; unknown basis refuses |
| `identity.series_ticker` | venue ticker | yes | retained series response | exact source/catalog match; refuse mismatch |
| `identity.event_ticker` | venue ticker | yes | retained market response | exact source/catalog match; refuse mismatch |
| `identity.market_ticker` | venue ticker | yes | retained market response | exact capture/source/catalog match; refuse mismatch |
| `identity.market_type` | enum | yes | retained market response | B1a accepts `binary` only |
| `identity.{title,yes_sub_title,no_sub_title}` | strings | yes | retained market response | exact source match; refuse mismatch |
| `identity.contracts[]` | ordered side/id/label | yes | repository projection of the source-backed binary sides | exactly `no`, then `yes`; absence refuses |
| `price.representation` | enum | yes | official fixed-point API contract | `fixed_point_dollars`; absence/other representation refuses |
| `price.maximum_decimal_places` | integer | yes | official fixed-point API contract | positive; observed values remain exact decimal strings |
| `price.level_structure` | string | yes | retained market response | exact source match |
| `price.ranges[]` | decimal dollars and inclusive flags | yes | retained market response; inclusivity is the reviewed projection | ordered contiguous coverage from 0 to 1; positive step; off-grid values refuse |
| `quantity.unit` | enum | yes | venue fixed-point contract | `contract`; other units refuse |
| `quantity.representation` | enum | yes | official fixed-point API contract | `fixed_point_contracts`; other forms refuse |
| `quantity.maximum_decimal_places` | integer | yes | official fixed-point API contract | positive |
| `quantity.increment_contracts` | decimal contracts | yes | official fixed-point documentation and reviewed venue policy | positive; nonmultiples refuse; no inference from capture |
| `payout.*` | decimal dollars and boolean | yes | retained notional plus official settlement semantics | B1a accepts one-dollar binary bounds; contingent value is retained, not processed |
| `rules.{primary,secondary}` | strings | yes | retained market response | exact source match; absence refuses |
| `rules.contract_terms_source` | source id | yes | repository provenance link | missing retained source refuses |
| `lifecycle.*` | RFC3339 UTC, seconds, boolean/string | yes | retained market response | exact source match and ordered times; absence refuses |
| `settlement.sources[]` | name/URL | yes | retained event metadata and series response | both sources must agree; settlement remains unsupported/not applied |
| `settlement.rules_source` | source id | yes | retained official settlement document | missing source refuses |
| `fees.*` | type, multiplier, statuses, source ids | yes | retained series response and official rounding document | type/multiplier must match; fees remain unsupported/not applied |
| `source_refs[]` | sorted source ids | yes | terms author | every id must exist in the retained source manifest |

An unsupported field is represented explicitly where the fact is useful for compatibility, for
example `implementation_status: unsupported_not_applied`. A missing required fact is never treated
as a default.

## Identity and provenance

The normalized V2 product map keeps two identities. `capture_identity` contains the WebSocket
ticker and market UUID with `capture_only_not_in_terms_source` authority for the UUID.
`authoritative_identity` contains the reviewed series, event, market, and contract projection.
The ticker must agree and the entire capture interval must fall within one reviewed catalog
revision. This preserves the distinction between observed capture evidence and source-backed venue
facts.

Every retained source has an exact HTTPS first-party URL, retrieval timestamp, local path, media
type, byte length, and SHA-256 digest. The source manifest itself has a canonical payload hash. The
terms document references retained source IDs and has an independent canonical payload hash. The
review names both hashes. A URL without retained bytes and hashes is not evidence. Review
limitations distinguish retrospective evidence, unretained linked documents, capture-only UUIDs,
and deliberately unsupported behavior.

## Canonical JSON and hashing

Identity hashes use SHA-256 over the canonical payload bytes: UTF-8 JSON, object keys sorted
lexicographically, compact separators, Unicode unescaped, no NaN/infinity, and one final line feed.
Envelope documents contain exactly `schema`, `payload`, and `payload_sha256`; the complete file
must itself use the same canonical encoding. Decimal quantities and prices are plain canonical
strings, never binary floats. Source content hashes cover the exact decoded source bytes. Artifact
file hashes cover exact file bytes.

## Lineage and runtime behavior

`pmm.historical.normalization_manifest.v2` carries catalog, source-manifest, terms, review,
conversion-policy, copied product-package, product-map, source-capture, and event hashes. The copied
package and policy make the normalized artifact independently verifiable offline.
`pmm.historical.feature_manifest.v2` binds its input normalization manifest and repeats the exact
product lineage. `pmm.backtest.v3` must name normalization/feature manifests and all product/policy
hashes. `pmm.backtest_result_manifest.v3` records the same hashes, product identity, effective
window, review limitations, fee/settlement non-application, and every result-artifact hash.

Manifests reference large terms by hash and also embed the small identity/effective/non-claim
projection needed for inspection. The authoritative bundle is copied once beside normalized data;
features and results do not duplicate it. `verify-lineage` recomputes the complete chain and can
optionally verify a result directory.

Observed venue prices and quantities are preserved as exact decimals after venue grid/increment
validation. Before the current C++ risk core receives a value, the conversion policy requires an
exact integer-cent price and exact whole-contract quantity. There is no rounding. Sub-cent grid
points, fractional strategy quantities, non-unit payout, unknown quantity units, and any other
nonrepresentable value refuse before a final directory is published. Trade yes/no prices must sum
exactly to one dollar.

Failure categories cover missing sources/terms/review, noncanonical bytes, unsafe paths or
symlinks, unreviewed package members, stale source/terms/review/catalog hashes, source-to-terms
disagreement, ticker mismatch, effective-window gaps/overlap, unsupported schemas/market/payout,
off-grid price or quantity, nonrepresentable core conversion, unsupported fee/accounting policy,
and upstream/result manifest mismatch. Partial output directories are removed on processing
failure; immutable final directories are never overwritten.

## Compatibility and migration

Existing `pmm.historical.product_map.v1`, normalization/feature V1 artifacts, `pmm.backtest.v1`,
and `pmm.backtest.v2` retain their exact interpretation and remain reproducible. They are not
silently assigned new terms. `assess-legacy` reports their missing lineage and whether deterministic
regeneration is possible. New authoritative runs use normalize V2, feature V2, and backtest V3.
The checked-in V1/V2 examples remain compatibility examples; the new V3 no-fill example is the
terms-bound path. Comparison reports name terms, source, review, and conversion-policy mismatches;
callers must not compare incompatible runs as equivalent experiments.

Tests use reviewed checked-in source bytes only. They cover canonical positive loading, exact
conversion boundaries, byte-identical repeated artifacts, source mutation, source/terms drift,
stale review, extra package members, wrong ticker, uncovered effective time, off-grid prices,
fractional/nonrepresentable core values, complete V3 lineage, and result hashing. No test or
deterministic runtime command calls the network.

## B1b-1 integrity and acquisition amendment

B1b-1 keeps the B1a ownership model and makes four previously implicit boundaries explicit.

First, terms, review, and catalog use one half-open effective interval `[from_utc, until_utc)`.
Their endpoints must be exactly equal, and the review basis must equal the terms basis. Catalog
selection uses the verified catalog interval. Adjacent revisions are allowed, gaps produce an
explicit refusal, overlaps are forbidden, and an open-ended revision cannot have a successor.
The first reviewed package already satisfied this rule, so its bytes and hashes remain unchanged.

Second, new network acquisition uses `pmm.product_acquisition_spec.v1` and emits
`pmm.product_terms_source_manifest.v2`. The specification contains operator intent: source ID,
role, requested first-party URL, retained path, and optional stricter limits. The source manifest
contains tool-observed retrieval start/end, elapsed time, every redirect, final URL, HTTP status,
selected response headers, media type, byte count, SHA-256, and tool version. V1 source manifests
remain valid compatibility evidence; they are not rewritten to claim observations they never
recorded.

Acquisition manually follows at most five redirects and validates every requested, intermediate,
and final URL as approved HTTPS with no credentials, fragments, non-default port other than 443,
or hostname escape. Responses stream in 64 KiB chunks through temporary files. JSON sources are
limited to 2 MiB, Markdown/text sources to 4 MiB, PDFs to 32 MiB, and a complete package to 64 MiB.
Connect, read-inactivity, per-source, and package deadlines are explicit. Role/media validation,
incremental hashing, exact byte counting, and cleanup occur before atomic final publication.

Third, handwritten Draft 2020-12 schemas remain reviewable artifacts. A shared positive/negative
acceptance matrix requires schema and runtime agreement for every schema-addressable rule.
Canonical bytes, content hashes, filesystem safety, cross-document interval equality, retained
source agreement, and arithmetic relationships remain explicitly runtime-only because an
individual JSON Schema cannot establish them.

Fourth, `ProductTermsError.code` is a public compatibility surface. Existing codes retain their
meaning; new codes may be added but existing codes may not be removed, renamed, or repurposed
without a versioned successor. Successful CLIs return zero with JSON on stdout and empty stderr.
Expected refusals return two with empty stdout and a coded diagnostic on stderr. Diagnostic prose
may gain context and is not byte-stable.

Normalization V2, feature V2, backtest V3, and result V3 need no successor for this amendment.
Their hash-based lineage accepts either verified source-manifest version, and offline V3
verification now rechecks the normalized product map, copied terms and conversion-policy files,
feature/product binding, result upstream hashes, embedded product metadata, and every result
artifact. Existing reviewed packages, generated artifacts, configurations, and results retain
their prior identity and interpretation.

## Consequences and non-goals

The separate bundle adds deliberate artifact bytes and review work, but allows source refreshes,
historical revisions, multi-market catalogs, offline audits, and exact experiment identity without
coupling the runtime to Kalshi. A new venue revision is additive: fetch to a new directory, build,
review, verify, then add a non-overlapping catalog entry.

B1a does not charge fees; implement accounting, collateral, margin, settlement, or PnL; calibrate
fills, model queues or hidden liquidity; add paper trading, gateways, live orders, reconnect/multi-
market recovery, experiment grids, reporting, or ML; change Phase 3 matching, integer core types,
`AccountRiskProjection`, rejection categories/ordinals, first-failure ordering, post-only behavior,
watermarks, kill switches, or the closed lifecycle/checkpoint corpora. It makes no claim of venue-
equivalent execution, profitability, paper readiness, or live readiness. `Observed`,
`Reconstructed`, `Synthetic`, and `ModelDerived` remain distinct.

See [[07 Engineering Notes/Authoritative Product Terms Explained]] for the plain-language
walkthrough, [[07 Engineering Notes/Product Terms Source and Review Guide]] for the operator and
evidence boundary, and [[07 Engineering Notes/Authoritative Product Terms Critique]] for the
severity-ranked remaining debt.

## B2b-2 result-lineage amendment

V4 names the exact normalization V3 manifest, records, source-scope map, product map, feature
manifest, feature rows, canonical feature definitions, and each product's
terms/source/review/conversion hashes. Result V4 repeats those identities, binds every per-contract
risk trace, hashes every typed result artifact, and verifies aggregate counts. No accepted package
or V1/V2/V3 artifact is rewritten or assigned a stronger meaning.
