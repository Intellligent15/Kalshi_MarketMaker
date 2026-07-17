# ADR-012: Deterministic document evidence and completeness profiles

- Status: Accepted
- Date: 2026-07-17
- Scope: Phase 7 Track B1c

## Context

ADR-011 added bracketed first-party evidence without pretending that all anchors were mechanically
verified. Evidence-map V1 resolves JSON pointers, checks a Markdown heading as a text occurrence,
and treats a positive PDF page plus nonempty section name as an exact-byte-bound human review
address. Source-manifest V3 binds a frozen acquisition policy and observation IDs, but it does not
require a complete semantic role set. The reviewed HMONTH package happens to contain all eight
intended roles at both endpoints; two equally incomplete future observations could still satisfy
the generic V3 membership checks.

Tightening V1 or V3 in place would change what accepted schema identities mean. HMONTH would appear
to gain machine-verified document claims it did not originally carry, while the retrospective WNBA
package would appear to owe evidence that its review explicitly says was not retained.

## Decision

Keep every accepted format as a frozen compatibility adapter and add one profile-bound successor
chain for new complete packages:

- `pmm.product_evidence_profile.v1`, retained as `evidence_profile.json`, owns role applicability,
  endpoint cardinality, role/media/content rules, mutability, linked-document relationships, and
  the complete product-field coverage ledger;
- `pmm.product_acquisition_spec.v3` binds the acquisition policy and evidence profile for one
  `opening` or `closing` observation;
- `pmm.product_terms_source_manifest.v4` binds both immutable identities and records the observed
  profile-complete source set;
- `pmm.product_evidence_map.v2` must exactly realize that coverage ledger and binds structurally
  resolved Markdown sections and deterministically extracted PDF sections through normalized
  SHA-256 fingerprints; and
- `pmm.product_terms_review.v3` binds policy, profile, manifest, terms, evidence map, exact interval,
  repository-declared responsibility, and the accepted checklist.

Product-terms V1/V2, catalog V1, conversion-policy V1, normalization/product-map V2, feature V2,
and configuration/result V3 do not need successors. They already bind the selected package through
exact terms, source-manifest, review, policy, and copied-package identities.

## Frozen adapters and accepted artifacts

Version dispatch is semantic, not merely structural:

- source-manifest V1 remains retrospective retained-byte evidence;
- source-manifest V2 remains the observed `product-acquisition.v2` adapter whose host, redirect,
  role/media, size, streaming, and timeout behavior is frozen independently of later policies;
- source-manifest V3, evidence-map V1, and review V2 retain ADR-011 semantics, including human-review
  PDF addresses and substring Markdown checks; and
- the new V4/V2/V3 chain is the only chain that claims generic profile completeness and mechanically
  fingerprinted document sections.

The accepted HMONTH and WNBA directories are not rewritten. Their bytes, hashes, catalog entries,
and downstream artifact meanings remain unchanged. HMONTH may be checked in a compatibility test
to show that its existing role set matches the new eight-role profile, but that test does not
upgrade its evidence-map V1 anchors. WNBA remains an honest retrospective six-source package whose
review records that linked contract and certification PDF bytes were not retained.

## Deterministic PDF extraction

PDF verification is offline and fail closed. Extractor policy `poppler_page_text.v1` uses Poppler
`pdfinfo` and `pdftotext` from the repository's Nix development environment. `flake.lock` pins the
Nixpkgs revision and therefore both Poppler executables; evidence-map V2 records both executable
names and exact reported versions. Verification refuses if either executable is absent or its
identity differs. It never falls back to a host tool, another PDF library, browser rendering, or
OCR.

The accepted environment identity is Nixpkgs revision
`59682e0069f0ed0a452e2179a7f4c1f247027b9e` with `poppler-utils` 26.06.0. The evidence map records
the complete first version lines `pdfinfo version 26.06.0` and `pdftotext version 26.06.0` rather
than accepting a version range.

Page extraction is exactly:

```text
pdftotext -f {page} -l {page} -enc UTF-8 -nopgbrk {source} -
```

`pdfinfo` supplies the page count before extraction. The extractor record also binds normalization
policy `pmm.document_text_normalization.v1`; its canonical policy SHA-256 is
`72399c0afa2e001111d26de14503ab817507fa4800a5497636d0e5fe20660d5f`.

PDF pages are one-based, matching a human review address. Runtime obtains the document page count
from the pinned toolchain and refuses page zero, a page beyond the document, malformed input,
encryption that prevents extraction, extraction errors, and a page with no extractable text. A
scanned or image-only PDF is unsupported unless its selected page already contains an extractable
text layer; B1c adds no OCR contract.

For the selected page, the locator's exact normalized start marker must occur once. An optional
exact end marker must occur once after it. The bounded section includes the start-marker line and
ends immediately before the end-marker line, or at the page boundary when no end is declared.
The locator fields are exactly `kind`, `page`, `section_start`, `section_end`, and `section_sha256`.
Repeated or missing boundary markers refuse. The evidence map records the SHA-256 of canonical JSON
containing the locator kind, normalization-policy identity, exact boundary object, and normalized
bounded text, not a quotation. Exact retained PDF bytes remain separately bound by the source
manifest, so replacing a document and recomputing its outer hashes cannot preserve an old section
fingerprint silently.

Canonical extracted text uses strict UTF-8, Unicode NFC, LF line endings (including form-feed
conversion), NBSP-to-space conversion, collapsed tab/vertical-tab/space runs, trimmed line edges,
collapsed blank-line runs, and no leading or trailing blank line. PDF normalization additionally
maps the common `ff`, `fi`, `fl`, `ffi`, and `ffl` Unicode presentation ligatures to their ASCII
letter sequences. Poppler's remaining font decoding and reading order are part of the pinned
extractor identity; runtime does not guess a different character when extraction output changes.

## Deterministic Markdown sections

Markdown verification decodes exact retained bytes as UTF-8, normalizes CRLF/CR to LF, and recognizes
only ATX headings outside fenced code blocks, with at most three leading spaces and one to six `#`
characters followed by required whitespace. Closing `#` characters are removed and heading text is
Unicode NFC. A locator names the complete ordered ancestor path of exact heading level/text pairs.
Its fields are exactly `kind`, `heading_path`, and `section_sha256`, where each path member contains
exactly `level` and `text`.

The complete heading path must resolve exactly once. The bounded body starts after that heading and
ends before the next heading of the same or shallower level, or at end of file. A phrase in body text
or a heading-like line inside a fenced block does not match; a deeper child heading remains inside
the section; duplicate complete paths refuse. The body uses the common normalization policy and its
canonical fingerprint includes the exact heading path. Missing, duplicate, re-leveled, renamed, or
content-mutated sections refuse with `EvidenceAnchorMismatch` after all outer hashes are recomputed.

## Completeness profile

Each profile declares stable logical source keys and exactly one applicability state:

- `required`: exactly one source for the role at each observation;
- `optional`: zero at both observations or exactly one at both; one-sided presence is invalid; or
- `not_applicable`: zero at both observations and a nonempty reviewed reason.

Absence never implies optionality or non-applicability. Source IDs are deterministic from observation
and logical source key, unique, and sorted. Retained paths remain safe and unique and preserve the
full relative path below `sources/<observation>/`; assembly must not flatten basenames. Opening and
closing membership must equal the profile, not merely each other.

The profile narrows acquisition-policy role/media/content rules. Static documents must have equal
bytes at both endpoints. Mutable JSON endpoints may differ, but every mechanically projected value
must equal the reviewed terms at both endpoints. `linked_source_keys` enforces declared co-presence
at each observation; it does not, by itself, parse a series record and compare document URLs. Any
claimed linked-document identity must be separately mechanically covered in the evidence map or
recorded as a review limitation. A correctly labelled role that cannot satisfy its declared
co-presence or field obligations is incomplete.

The initial Kalshi binary profile requires exactly one market record, event metadata record, series
record, fixed-point document, fee-rounding document, settlement document, contract-terms PDF, and
certification PDF at both observations. A product family with a genuine optional or not-applicable
role uses a new immutable profile identity; operators do not edit this profile in place.

## Product-field coverage classes

Every product-term leaf belongs to exactly one class:

| Class | Typical fields | Verification |
|---|---|---|
| Mechanically projected | source-backed identity, price grid, notional, rules, lifecycle, settlement sources, series fee type/multiplier | Exact JSON pointer and value equality at both endpoints. |
| Human-reviewed | binary contract meaning/labels, range inclusivity, representation and decimal precision, quantity increment, payout semantics, maker/waiver conclusions | Structurally resolved Markdown/PDF fingerprint at both endpoints plus review responsibility. |
| Derived | evidence-bracket interval, repository contract IDs, provenance links, sorted `source_refs` | Deterministic derivation from completely covered inputs; no invented direct anchor. |
| Repository/local policy | venue/environment restriction, revision label, canonical representation and ordering | Exact schema/profile rule; not presented as a venue statement. |
| Unsupported | fee and settlement application and other deliberately unimplemented economics | Explicit unsupported/non-applied status; evidence cannot turn it into an implementation claim. |
| Not applicable | package-specific nullable fact or profile-declared absent role | Explicit profile/coverage entry and reason; never inferred from omission. |

Evidence-map V2 and the profile jointly require leaf-complete classification. Only mechanically
projected and human-reviewed fields require source anchors. Derived fields require complete named
dependencies; local-policy, unsupported, and not-applicable fields require exact declared rules.
Mechanically projected JSON anchors retain the exact `kind` and `pointer` locator fields and require
source/term equality at both observations.

## Refusal compatibility

Existing refusal codes retain their meanings. B1c adds only `EvidenceProfileMismatch`, for a
missing, stale, unsupported, or cross-artifact-inconsistent evidence-profile identity.

- missing, duplicate, asymmetric, or not-applicable-but-present roles use `EvidenceIncomplete`;
- source bytes or length drift uses `SourceHashMismatch`;
- source-to-terms JSON disagreement uses `SourceTermsMismatch`;
- document extraction, page, section, ambiguity, normalization, or fingerprint defects use
  `EvidenceAnchorMismatch`; and
- acquisition media/content defects continue to use `AcquisitionMediaTypeMismatch` or
  `AcquisitionContentInvalid`.

Public CLI behavior remains exit 0 with one JSON result on stdout and empty stderr for success;
exit 2 with empty stdout and a coded diagnostic on stderr for expected refusal; and exit 1 for an
unexpected programming failure.

## Verification and tests

All deterministic verification remains offline. Tests use retained fixtures, fake sessions,
injected clocks, minimal synthetic UTF-8 Markdown and PDFs, and the pinned extractor. One-defect
cases cover schema/runtime parity, every required role, optional and not-applicable cardinality,
endpoint-specific mutations, wrong role/media/content, linked-document disagreement, same-basename
assembly, malformed/encrypted/scanned/textless PDFs, page and section bounds, repeated headings,
Unicode/ligature/line-ending/whitespace normalization, document replacement with recomputed outer
hashes, review/profile mutations, CLI streams/statuses, interruption cleanup, repeated offline byte
identity, legacy V2/V3 adapters, both accepted packages, and downstream V2/V3 lineage.

## Consequences and non-goals

The successor chain adds several small control artifacts and a pinned external extractor. That cost
is justified because package completeness and document anchors become explicit versioned claims
instead of conventions. Verification stays portable through Nix on supported systems and auditable
through exact identities, but arbitrary host Poppler versions are intentionally not compatible.

B1c does not add OCR, legal interpretation automation, continuous source immutability, review
signatures/revocation, content-addressed storage, live-network verification, fees, accounting, PnL,
collateral, margin, settlement processing, calibrated fills, queue or hidden-liquidity assumptions,
multi-market replay, reconnect recovery, experiment grids, ML, paper trading, gateways, live orders,
or venue-equivalent/readiness/profitability claims. Existing risk, matching, integer conversion, and
truth-category boundaries remain unchanged.
