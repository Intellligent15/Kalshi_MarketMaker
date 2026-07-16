# Authoritative Product Terms Explained

## The problem in plain language

Before B1a, the historical pipeline knew which WebSocket stream it had recorded, but it did not
independently prove the rules of the product carried by that stream.

Those are different facts:

- “These messages say they belong to ticker X and market UUID Y” is capture identity.
- “Ticker X trades on this price grid, in these quantity increments, under this payout and
  lifecycle, with these settlement and fee terms” is product authority.

A WebSocket recording is excellent evidence of what messages were observed. It is not enough to
prove every venue rule. If the research system assumes one-cent prices and one-contract quantities
because its C++ types use integers, it can produce perfectly deterministic results for the wrong
economic contract. Deterministic wrong answers are still wrong.

B1a makes the product rules an explicit, reviewed input to the research pipeline.

## The design in one picture

```text
official first-party source bytes
        |
        v
source_manifest.json -----> product_terms.json -----> review.json
        |                         |                       |
        +-------------------------+-----------------------+
                                  |
                                  v
                         product catalog revision
                                  |
raw capture ----------------------+
    | ticker + capture time       |
    v                             v
normalized events + product map + copied reviewed package + conversion policy
                                  |
                                  v
                         causal feature manifest
                                  |
                                  v
                         pmm.backtest.v3 config
                                  |
                                  v
                   result artifacts + result manifest
```

Every arrow is enforced by identity, time, or a cryptographic hash. A later stage does not merely
say “I used product terms.” It says exactly which terms, which source bundle, which review, which
conversion policy, and which upstream manifest it used.

## Why we chose a separate immutable package

We considered three places to own the terms.

### Put everything in `product.json`

This looked simple because normalization already wrote that file. The problem is ownership.
`product.json` was built from capture metadata and messages. Adding official API records and legal
documents would mix two evidence sources and make refresh behavior unclear. Did the product change
because the capture changed, because Kalshi changed a term, or because our review changed?

### Put everything in the backtest configuration

This would make each experiment explicit, but configurations are easy to copy and hand-edit. The
normalized events and features could be produced under one interpretation and then run under a
different terms block. Validation would happen too late.

### Use a separate reviewed package

This adds several small files, but it gives each concern one owner:

- the capture owns observed messages and capture-only identity;
- retained source files own exact first-party evidence;
- `product_terms.json` owns the canonical market-specific projection;
- `review.json` owns the approval decision, effective time, and limitations;
- the catalog owns revision selection;
- the conversion policy owns what this repository can represent; and
- manifests own the exact dependency chain.

That separation is the foundation of auditability. We chose it even though it creates more visible
artifacts because the alternative hides complexity inside ambiguous files.

## The product package, file by file

### Retained source files

The package stores the exact response or document bytes used during review. The first package
contains market, series, and event-metadata REST responses plus Kalshi's fixed-point, settlement,
and fee-rounding documentation.

The source URL is useful provenance, but the local bytes are the evidence. A URL can change or
disappear. A search snippet can be incomplete. A retained file with its hash can be verified years
later without calling the venue.

### `source_manifest.json`

This file inventories every retained source:

- a stable source ID and role;
- exact first-party URL;
- retrieval time;
- local safe path;
- media type and optional encoding;
- byte length;
- source SHA-256; and
- venue update time when available.

The source manifest has its own canonical payload hash. The package rejects an unlisted extra file,
a missing file, a symlink, an escaping path, changed bytes, a stale byte count, a stale hash, or an
unapproved host.

### `product_terms.json`

This is the small, stable projection that deterministic code can understand. It records:

- venue and environment;
- effective interval and why that interval is believed;
- series, event, market, and binary contract identities;
- exact price representation and ranges;
- quantity unit and increment;
- payout bounds;
- primary and secondary rules;
- open, close, expiration, early-close, and settlement timing;
- settlement sources;
- fee identity and rounding source; and
- the retained source IDs supporting the projection.

For JSON API records, the loader mechanically compares important projected fields with the retained
responses. A reviewer cannot change a market ticker, rule, lifecycle time, price range, notional,
settlement source, or fee type in the terms document while leaving the source evidence unchanged.

### `review.json`

Evidence and interpretation are not the same thing. The review document records that a specific
terms hash and source-manifest hash were approved for a specific effective-time basis. It also
carries limitations that follow the data into result manifests.

For the first market, those limitations say that the REST record was obtained after settlement,
the linked contract PDFs were identified but not retained, fees and settlement are not applied,
and the WebSocket UUID is capture-derived. Keeping those caveats attached to the hash prevents a
later presentation from accidentally losing them.

### Catalog manifest

The catalog maps a venue market ticker and time interval to one immutable reviewed package. During
normalization, the complete capture interval must be covered by exactly one review. No match fails;
multiple matches fail; overlapping catalog revisions fail.

This is how a later venue refresh becomes additive. We create a new package and interval rather
than editing history.

### Conversion policy

Venue facts and repository limitations must not be confused. Kalshi uses fixed-point decimal
strings and can represent fractional contract quantities. The current core risk interface uses
integer cents and whole contracts.

The policy therefore says:

- preserve observed prices exactly and validate them against the venue grid;
- preserve observed quantities exactly and validate the venue increment;
- convert a core price only when dollars × 100 is an exact integer;
- convert a core quantity only when it is an exact whole contract;
- do not apply fees; and
- do not apply settlement.

There is no rounding. `0.50` becomes 50 cents. `0.505` refuses. `2.00` becomes two contracts.
`2.25` refuses at the core boundary even if it was a valid observed venue quantity.

This is a crucial distinction: refusal does not call the venue value invalid. It says the current
research core cannot represent it honestly.

## Canonical JSON and content identity

Hashes are useful only if every implementation agrees on the bytes being hashed. Control documents
therefore use one canonical encoding:

- UTF-8;
- lexicographically sorted object keys;
- compact separators;
- no NaN or infinity;
- Unicode preserved rather than ASCII-escaped;
- decimal values represented as plain strings; and
- exactly one final line feed.

Each envelope contains a schema name, payload, and SHA-256 of the canonical payload bytes. The
loader also requires the envelope file itself to be canonically encoded. Reformatting a reviewed
file is not harmless: immutable artifact bytes must remain exact.

Source hashes work differently. They cover the exact retained source bytes, because changing an
official response's whitespace or transport representation is still a different retained record.

## How normalization binds a capture to terms

Normalization V2 receives three inputs:

1. the immutable raw capture;
2. the reviewed product catalog; and
3. the explicit conversion policy.

It checks that the capture ticker equals the reviewed market ticker and that the review covers the
capture's start and end. It then validates every observed price and quantity against the reviewed
venue grid and increment. For trades, YES and NO prices must sum exactly to one dollar.

The resulting product map deliberately has two identities:

- `capture_identity` contains the ticker and observed WebSocket market UUID;
- `authoritative_identity` contains the source-backed series, event, market, and contract terms.

The UUID is labelled `capture_only_not_in_terms_source`, so nobody can mistake it for a REST-backed
product identifier.

Normalization writes to a temporary directory. Only after every input, event, package copy, policy,
and output hash succeeds does the directory receive its final name. On failure, the partial output
is removed. An existing final directory is never overwritten.

## How identity travels through the pipeline

### Normalization manifest V2

It hashes the capture, canonical events, product map, catalog, product terms, source manifest,
review, conversion policy, and copied files. This is the main evidence bundle.

### Feature manifest V2

It hashes the feature rows, repeats the exact product identities, and hashes the complete
normalization manifest. A feature dataset cannot silently move to different terms.

### Backtest configuration V3

It names both upstream manifests and explicitly declares the expected terms, source, review, and
conversion-policy hashes. It also requires the canonical C++ risk oracle. The configuration is not
allowed to discover or substitute “current” venue terms.

### Result manifest V3

It repeats the verified lineage and embeds the small product identity, effective-time information,
review limitations, and fee/settlement non-application status. It also hashes orders, fills, ledger,
and risk trace. This lets a reviewer inspect important facts quickly and then follow hashes to the
full authority.

### Offline verification

`verify-lineage` recomputes the chain. With a result directory, it also verifies the configuration
hash, upstream manifests, and each result artifact. No network call is needed.

## What failure looks like

Fail-closed behavior is more important than a convenient fallback.

| Situation | Outcome |
|---|---|
| No reviewed package covers the capture | normalization refuses |
| Capture ticker differs from terms | normalization refuses |
| Source byte or byte count changes | package verification refuses |
| Terms change without a new matching review | review-hash verification refuses |
| Terms disagree with retained JSON evidence | source/terms verification refuses |
| Catalog revisions overlap or lookup is ambiguous | catalog verification/selection refuses |
| Observed price is off the venue grid | normalization refuses |
| Observed quantity violates the venue increment | normalization refuses |
| Valid venue value is not an exact cent/whole contract at the core boundary | V3 backtest refuses |
| Config names the wrong terms, source, review, or policy hash | V3 lineage refuses |
| Event, feature, manifest, or result bytes change | offline lineage refuses |
| Final output already exists | command refuses rather than overwriting it |

There is intentionally no fallback to inferred capture terms, live network metadata, rounding, or
the old V1 product map.

## How legacy artifacts are preserved

Existing normalized V1 artifacts and backtest V1/V2 configurations still mean exactly what they
meant when created. B1a does not edit them or attach a new authoritative interpretation after the
fact.

`assess-legacy` can check whether an old event stream is compatible with a reviewed package and
current conversion policy. A successful assessment says regeneration is supported; it does not
relabel the old directory. The correct migration is to create a new normalized V2 artifact.

This matters for scientific honesty. Reproducibility means preserving old assumptions, including
their limitations, rather than rewriting history to match a better current design.

## What the completed run proves

The final full-capture V3 control processed:

- 19,958 normalized observed events;
- 19,958 causal feature rows;
- 1,213 strategy decisions;
- 2,426 accepted model-derived orders;
- 2,424 cancellations; and
- zero fills under `no_fill_v1`.

The normalized events, features, and orders retained their established byte hashes. That shows the
new metadata lineage wrapped the existing deterministic behavior without changing market data,
strategy scheduling, or risk results.

It proves that the product-bound control path is deterministic and auditable for this reviewed
market. It does not prove that every Kalshi product is supported, that the retrospective review is
as strong as a pre-capture snapshot, or that the fill/accounting system is economically realistic.

## Why this work makes later hard work easier

Fees, settlement, accounting, calibrated execution, and ML labels all depend on knowing the exact
product. Without B1a, each later component would need to invent its own answer to basic questions:

- What does one price unit mean?
- What quantity is legal?
- What is the payout?
- When can the market close?
- Which rule and settlement source apply?
- Did two experiments use the same contract terms?

Now those questions have one versioned boundary. A future fee engine can refuse incompatible fee
terms. A settlement engine can name the exact rules it implements. A dataset can hash the terms
used to create its labels. A comparison tool can detect different economic inputs.

The system still has hard work ahead, but that work can build on explicit evidence rather than
hidden assumptions.

## What remains incomplete

The accompanying critique records the detailed debt. The most important items are:

- make terms, review, and catalog effective intervals one enforced contract;
- validate redirect destinations and bound acquisition size;
- make formal JSON Schemas as strict as runtime validation;
- retain linked contract/certification bytes and acquire before capture;
- add reviewer identity, revocation, and supersession policy;
- add a second market/product family and multi-revision tests;
- deepen negative end-to-end lineage and public CLI coverage; and
- plan content-addressed evidence storage before document duplication becomes large.

Those are reasons for a bounded B1b package, not reasons to weaken B1a's exact refusal behavior.

## Non-claims

B1a does not calculate fees, maintain double-entry accounts, calculate PnL, process settlement,
model collateral or margin, calibrate fills, infer queue position, model hidden liquidity, recover
multi-market connections, place paper or live orders, or begin ML work. It does not change Phase 3
matching, core integer types, `AccountRiskProjection`, risk rejection categories or ordering,
post-only behavior, watermarks, kill switches, or closed risk fixtures.

The product metadata is authoritative within the retained evidence and documented review boundary.
The overall system is still a research platform, not evidence of profitability, paper readiness,
live readiness, or venue-equivalent execution.
