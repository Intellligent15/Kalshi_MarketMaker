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

## Known limitations and next evidence package

The first market record was retrieved after settlement, so its effective coverage is a reviewed
retrospective conclusion rather than a contemporaneous pre-capture snapshot. The retained series
record names official contract-terms and certification PDFs, but their bytes are not in this first
package. Only one market/product family is reviewed.

B1b-2 closes those linked-document and second-family gaps. Before B2, B1c must make PDF/Markdown
anchor claims and the generic required-source profile match runtime enforcement. B2 then designs
broader multi-market/reconnect/gap-recovery evidence separately. Metadata work remains outside
runtime and does not establish accounting, settlement, calibrated execution, multi-market replay,
or live trading.
