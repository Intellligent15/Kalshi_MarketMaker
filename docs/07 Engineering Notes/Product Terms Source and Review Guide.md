# Product Terms Source and Review Guide

## Evidence classes

Review every field into one of four classes. Do not collapse them:

| Class | Meaning | B1a example |
|---|---|---|
| Current official venue fact | A fact returned or documented by a first-party Kalshi source at retrieval time | the REST market reports `linear_cent` and a `0.0100` step |
| Retained source evidence | Exact local bytes plus URL, retrieval time, byte length, media type, and SHA-256 | `sources/market.response.json` and its source-manifest entry |
| Repository conversion policy | A PM MarketMaker decision about representability, not a venue claim | exact integer cents and whole contracts only; never round |
| Assumption or unsupported field | Not established or deliberately not executed | WebSocket UUID is capture-only; fee charging and settlement are not applied |

A current URL or search result is discovery, not reproducible evidence. Approval requires retained
content. Linked documents that were not retained must be named in review limitations.

## First reviewed package

The package for `KXWNBASPREAD-26JUL14WSHTOR-WSH2` retains these exact first-party sources:

| Source | Exact URL | Retained fact or role |
|---|---|---|
| Market REST record | https://api.elections.kalshi.com/trade-api/v2/markets/KXWNBASPREAD-26JUL14WSHTOR-WSH2 | ticker/event identity, binary type, labels, rules, linear-cent grid, one-dollar notional, lifecycle, early close, settlement timer |
| Series REST record | https://api.elections.kalshi.com/trade-api/v2/series/KXWNBASPREAD | series identity, fee type/multiplier, settlement source, and official linked document identities |
| Event metadata REST record | https://api.elections.kalshi.com/trade-api/v2/events/KXWNBASPREAD-26JUL14WSHTOR/metadata | market membership and settlement source |
| Fixed-point migration documentation | https://docs.kalshi.com/getting_started/fixed_point_migration.md | current fixed-point price/quantity API representation and fractional-contract context |
| Market settlement documentation | https://docs.kalshi.com/getting_started/market_settlement.md | current general settlement mechanics and contingent-value context |
| Fee rounding documentation | https://docs.kalshi.com/getting_started/fee_rounding.md | current fee rounding semantics; identity only in B1a |

The source files are the evidence used by runtime verification and tests. The URLs above help a
reviewer understand their origin; they are not substitutes for the retained bytes or hashes.

## What is official, projected, and local

At the recorded retrieval time, the official market response reported a binary market, a one-dollar
notional, `linear_cent`, and one inclusive repository-projected range from `0.0000` through `1.0000`
with `0.0100` steps. The official fixed-point documentation states that the API uses fixed-point
string fields and supports fractional contract quantities. The reviewed terms therefore preserve
prices and quantities exactly as decimals and declare a `0.01` contract increment.

The terms document is a canonical reviewed projection of those sources. Contract IDs such as
`market-ticker#yes` and `market-ticker#no` are repository identities for the two binary legs; they
are not claimed as venue-issued UUIDs. The captured WebSocket market UUID is retained separately
because the REST evidence does not establish it.

The integer-cent/whole-contract policy belongs to this repository. It does not claim all Kalshi
products have those units. A valid venue value that is not exactly representable refuses at the
current core boundary.

Fees, fee waivers, contingent settlement, actual settlement processing, accounting, collateral,
and PnL are unsupported. Their source identity is retained so a later implementation can detect
incompatible terms, not so the current result can claim economic completeness.

## Review workflow

1. Acquire into a new immutable directory with the explicit `fetch` command or another documented
   byte-preserving operator process. Never fetch during deterministic runtime.
2. Verify HTTPS first-party origins, exact byte hashes, response shape, venue update timestamps,
   and whether every linked authoritative document needed for approval was retained.
3. Build a terms projection and mechanically compare its market-specific values with the retained
   JSON records.
4. Record effective-time basis and every limitation. A retrospective conclusion must say so.
5. Create a review envelope naming the exact source-manifest and terms hashes.
6. Verify the package offline, add a non-overlapping catalog entry, and run positive and mutation
   tests before use.
7. Refresh additively. Never edit an approved revision or reinterpret an old normalized artifact.

The `build` and `review` commands create new files only. `verify-package` and `verify-catalog` are
read-only. `compare` reports exact compatibility identities; `diff` shows field-level changes;
`assess-legacy` identifies missing lineage without rewriting the artifact.

## Hardened acquisition workflow

Copy `configs/product_catalog/acquisition_spec.example.json` to an untracked operator path, replace
the ticker placeholders, add every required linked document, and fetch into a new revision path:

```sh
uv run python python/pmm_product_terms.py fetch \
  --spec path/to/acquisition-spec.json \
  --output path/to/new-product-revision
```

The specification is operator intent, not observed provenance. It declares source IDs, roles,
requested URLs, retained paths, and optional limits that may only narrow repository policy. Do not
put retrieval timestamps, response status, final URLs, or hashes in the specification. The tool
observes and writes those fields into source-manifest V2.

Every URL and redirect must remain approved first-party HTTPS. The redirect limit is five. JSON
sources are limited to 2 MiB, Markdown/text to 4 MiB, PDFs to 32 MiB, and the complete retained
package to 64 MiB. Acquisition uses 64 KiB chunks, a five-second connect timeout, a fifteen-second
read-inactivity timeout, a sixty-second per-source deadline, and a 180-second package deadline.
HTML, unexpected content encoding, wrong role/media combinations, invalid JSON/UTF-8/PDF content,
size disagreement, timeout, and interruption refuse before final publication.

New acquisition emits `pmm.product_terms_source_manifest.v2`. Existing reviewed V1 manifests stay
valid and must not be rewritten. Tests use fake sessions and clocks; normalization, backtesting,
verification, and tests never depend on a live network response.

Terms, review, and catalog endpoints must be byte-for-byte equal after canonical parsing and use
the same terms/review basis. Their interval is half-open. Adjacent revisions are allowed, gaps have
no selected package, and overlap refuses. See
[[07 Engineering Notes/Product Terms Refusal Codes]] for the stable public error categories and
CLI compatibility policy.

## Contemporaneous HMONTH package

The second reviewed package is the climate-family market `KXHMONTH-26JUL`. Its immutable directory
contains two complete observations of eight sources: market, event metadata, series, fixed-point
representation, fee rounding, settlement guidance, HMONTH contract terms, and HMONTH certification.
The observations are byte-identical and establish the exact interval
`[2026-07-17T15:07:16.002543Z, 2026-07-17T15:08:37.512205Z)`. This brackets two observations; it
does not prove that no source changed between them.

Acquisition-spec V2 names the immutable policy file. Each fetch emits source-manifest V3 with an
observation identity. `assemble-observations` refuses different membership, source bytes, policy,
or invalid acquisition ordering and combines the endpoint evidence. Product-terms V2 is required
because the official HMONTH market record contains an empty secondary-rules string that V1 cannot
represent honestly.

Evidence-map V1 anchors mechanically projected JSON values by RFC 6901 pointer, checks Markdown
text occurrence, and records hash-bound PDF page/section addresses for human review. Runtime does
not yet extract the named PDF page or confirm the section text. Review V2 binds those anchors, the
policy, both observations, the terms, a repository-declared reviewer, responsibilities, and
accepted checklist items. This identity is accountability metadata in version control, not a
signature.

Approval is all-or-nothing. A missing, mutable between endpoints, unretainable, redirected outside
policy, wrong-media, structurally invalid, or semantically insufficient required source refuses the
package. A URL alone is never evidence. Refreshes create adjacent or otherwise non-overlapping
immutable revisions; they do not edit this package.

## B1c successor package workflow

New packages that claim generic source completeness and mechanically fingerprinted document
sections use this complete chain:

1. select immutable acquisition-policy V1 and product-evidence-profile V1 identities;
2. author one acquisition-spec V3 for `opening` and one for `closing`;
3. acquire each observation into source-manifest V4 without network access in later verification;
4. assemble only after both observations exactly satisfy the profile;
5. build product-terms V1 or V2 according to the observed market value;
6. build evidence-map V2 with complete field coverage and document-section fingerprints;
7. create review V3 binding policy, profile, sources, terms, evidence, interval, responsibilities,
   and checklist; and
8. verify offline before adding a non-overlapping catalog V1 entry.

The retained filenames are `evidence_profile.json`, `source_manifest.json`,
`evidence_anchors.json`, and `review.json`. Existing package filenames are not renamed. Catalog V1
and downstream normalization/product-map V2, feature V2, and configuration/result V3 continue to
bind exact package hashes and do not need successors.

### Required, optional, and not-applicable roles

The profile, not an operator's omission, decides applicability:

- a required logical source appears exactly once at opening and exactly once at closing;
- an optional logical source is absent at both endpoints or appears exactly once at both;
- a not-applicable source appears at neither endpoint and carries a nonempty reason.

Opening and closing must independently equal the declared profile. Equal but incomplete endpoint
sets are invalid. IDs are deterministically derived from observation plus logical source key, and
paths are safe and unique while preserving the complete relative path below the observation
directory. Assembly must not flatten basenames.

Static Markdown and PDF documents are byte-identical at both endpoints. Mutable JSON sources may
change, but every mechanically projected term must agree at both endpoints. Contract and
certification roles declare their required co-presence with the series record through
`linked_source_keys`. That relationship does not itself compare a URL inside series JSON; a package
that claims exact linked-document identity needs a separate mechanically projected anchor or an
explicit review limitation. A source with the expected role and media type is still insufficient
when its declared co-presence or required field coverage cannot be established.

The initial Kalshi binary profile requires the same eight roles retained by HMONTH: market, event
metadata, series, fixed-point representation, fee rounding, settlement guidance, contract terms,
and certification. A real product-family exception requires a new immutable profile identity; it
does not weaken the accepted profile.

### Document anchors

Run document verification inside the repository Nix environment. Extractor policy
`poppler_page_text.v1` uses `pdfinfo` for page count and invokes exactly
`pdftotext -f {page} -l {page} -enc UTF-8 -nopgbrk {source} -`. The locked Nixpkgs revision owns
both Poppler executables, and evidence-map V2 records both executable names and exact reported
versions plus normalization policy `pmm.document_text_normalization.v1` and its policy SHA-256.
Verification does not fall back to another host extractor or OCR.

The normalization-policy SHA-256 is
`72399c0afa2e001111d26de14503ab817507fa4800a5497636d0e5fe20660d5f`.

The accepted lock is Nixpkgs revision `59682e0069f0ed0a452e2179a7f4c1f247027b9e` with
`poppler-utils` 26.06.0. Verification requires the complete first version lines
`pdfinfo version 26.06.0` and `pdftotext version 26.06.0`; another Poppler release is not treated as
equivalent merely because the source PDF is unchanged.

PDF pages are one-based. The selected page must exist and contain extractable text. Its exact
normalized start marker must occur once; an optional end marker must occur once after it. The
bounded section includes the start line and excludes the end line, or continues to the page boundary.
The exact locator fields are `kind`, `page`, `section_start`, `section_end`, and `section_sha256`.
Malformed, extraction-blocked encrypted, scanned/image-only, textless, out-of-range, missing-marker,
duplicate-marker, or fingerprint-mismatched PDFs refuse. A scanned PDF is valid only when the
selected page already has a usable text layer; B1c never synthesizes one.

Markdown locators name the complete ancestor path of exact ATX heading levels and NFC text. ATX
headings allow at most three leading spaces and are ignored inside fenced code blocks. A body-text
phrase is not a heading. The body begins after the selected heading and ends before the next heading
of the same or shallower level. Missing, duplicate-path, renamed, re-leveled, or changed sections
refuse. The exact locator fields are `kind`, `heading_path`, and `section_sha256`; every heading-path
member contains exactly `level` and `text`.

Canonical text is strict UTF-8 with Unicode NFC, LF line endings, NBSP-to-space conversion, collapsed
tab/vertical-tab/space runs, trimmed line edges, collapsed blank-line runs, and no leading or
trailing blank line. PDF text additionally maps the common `ff`, `fi`, `fl`, `ffi`, and `ffl`
presentation ligatures to ASCII sequences. The fingerprint hashes canonical JSON containing the
locator kind, normalization-policy identity, exact boundary object, and normalized text; the map
does not copy prose. Exact source hashes still bind the complete retained document. Poppler's
remaining font decoding and reading order belong to the pinned extractor identity.

### Product-field coverage

Every product-term leaf is classified exactly once:

| Class | Requires source anchor | Examples |
|---|---:|---|
| Mechanically projected | yes, both endpoints | source-backed identity, grid, notional, rules, lifecycle, settlement sources, series fee type/multiplier |
| Human-reviewed | yes, both endpoints | contract meaning, representation/precision, quantity increment, payout semantics, maker/waiver conclusions |
| Derived | complete named dependencies | bracket endpoints, repository contract IDs, provenance links, sorted source references |
| Repository/local policy | no | venue/environment restriction, revision identity, canonical ordering/representation |
| Unsupported | no; explicit status | fee and settlement application and other deliberately unimplemented economics |
| Not applicable | explicit profile/coverage reason | package-specific absent fact or role; never inferred from omission |

Mechanically projected anchors require exact source/term equality. Human-reviewed anchors prove that
the cited exact section exists and is unchanged; they do not automate legal interpretation.
Derived fields are recomputed from covered inputs. The remaining classes are checked against exact
profile/schema rules rather than disguised as venue facts.

### Compatibility and refresh

Source-manifest V1, frozen acquisition/source-manifest V2, source-manifest V3, evidence-map V1, and
review V1/V2 retain their original meanings. The accepted HMONTH package may be exercised against
the new role profile as compatibility evidence, but its PDF addresses do not become V2 fingerprints.
The WNBA package remains an honest six-source retrospective package. Neither directory is edited.

A changed host, redirect, timeout, media, role, completeness, extraction, or fingerprint policy
creates a new immutable identity and, when meaning changes, a versioned successor. Old verification
dispatches through its frozen adapter and never consults the new policy implicitly.

## Known limitations and next evidence package

The first market record was retrieved after settlement, so its effective coverage is a reviewed
retrospective conclusion rather than a contemporaneous pre-capture snapshot. The retained series
record names official contract-terms and certification PDFs, but their bytes are not in this first
package. Only one market/product family is reviewed.

B1b-2 closes those linked-document and second-family gaps. B1c adds successor formats for exact
PDF/Markdown anchors and generic required-source enforcement without upgrading accepted artifacts.
B2 then designs broader multi-market/reconnect/gap-recovery evidence separately. Metadata work remains outside
runtime and does not establish accounting, settlement, calibrated execution, multi-market replay,
or live trading.
