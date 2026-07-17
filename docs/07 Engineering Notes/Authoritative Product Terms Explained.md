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

## How B1b-1 hardens the boundary

B1a established the artifact chain. B1b-1 removes ambiguity at the two places where outside facts
enter it—time selection and network acquisition—and then strengthens every downstream check that
depends on those facts.

### What changed, in one picture

```text
operator acquisition intent
        |
        v
validated first-party HTTPS request
        |
        +--> validate and record every redirect
        |
        v
bounded temporary file -- incremental SHA-256 --> observed source-manifest V2
        |                                              |
        +---------------- atomic package --------------+
                                                       |
                                                       v
terms interval == review interval == catalog interval
                                                       |
                                                       v
normalization V2 -> features V2 -> config V3 -> result V3
       ^                 ^             ^            ^
       +---------------- offline hash verification --+
```

The important idea is that acquisition is a transaction, not a download, and time coverage is one
contract, not three similar claims.

### One temporal contract

Terms, review, and catalog used to carry three interval copies that could disagree. The catalog
also selected packages by asking whether the review covered a capture rather than by applying its
own advertised interval. A package could therefore be internally reviewed for one period while the
catalog appeared to publish it for another.

B1b-1 uses exact equality. Each document must carry the same half-open interval:

```text
[effective_from_utc, effective_until_utc)
```

The start belongs to the revision; the end belongs to the next revision. Adjacent revisions can
therefore meet at one timestamp without overlapping. A gap means there is no approved evidence for
that period. An overlap is invalid rather than a priority rule. An open-ended revision cannot have
a later revision because it already claims all future time.

We considered containment: the review or catalog could advertise a narrower interval inside the
terms interval. That supports flexible approval windows, but it makes selection depend on which
document a caller treats as authoritative. We also considered separately versioned declared and
approved intervals. That is expressive, but it requires explicit transition semantics and a
reason for every difference. The current evidence does not need either complexity. Exact equality
is the smallest rule that makes disagreement impossible and makes mutation failures obvious.

The loader enforces this in layers:

1. `ProductReview.load` checks the review basis and both endpoints against the terms.
2. `ProductCatalog._package_for` checks the catalog endpoints against both terms and review.
3. `ProductCatalog.verify` rejects overlapping revisions for one market.
4. `ProductCatalog.resolve` selects using the catalog's own verified interval.
5. `ProductPackage.verify_capture` independently confirms that the selected review covers the full
   capture.

The repeated final check is deliberate defense in depth. Selection and package validity cannot
silently diverge after a future refactor.

### Acquisition is an all-or-nothing transaction

The new fetch path begins from `pmm.product_acquisition_spec.v1`. That document is a request, not
evidence. It tells the tool which source role to fetch, the requested URL, the retained relative
path, and optional limits that may only narrow the built-in policy.

For each source, the tool performs this sequence:

1. Validate the requested URL before making a request. It must use HTTPS, have an exact approved
   hostname, contain no credentials or fragment, and use only the default port or explicit 443.
2. Send a streaming request with automatic redirects disabled and identity content encoding.
3. If the response is a redirect, require a `Location`, resolve relative locations, validate the
   destination, record the status and both raw and resolved location, close the response, and make
   the next request. At most five hops are allowed.
4. Require a final 2xx response whose observed response URL is exactly the URL the tool requested
   for that hop. This catches a client or test double that changed destinations invisibly.
5. Require an allowed media type for the declared role and reject compressed transport content,
   so byte counts and retained hashes refer to the received identity bytes.
6. Reject a declared `Content-Length` that is invalid, exceeds the source limit, or would exceed
   the package limit.
7. Stream into a sibling `.download` file in 64 KiB chunks. After every chunk, update the source
   byte count and SHA-256 and recheck source, package, and deadline bounds.
8. Flush and fsync the source file, require the streamed count to equal `Content-Length` when one
   was supplied, and validate the retained content as a JSON object, UTF-8 text, or PDF signature.
9. Rename the validated `.download` file to its retained path and record observed metadata.

The built-in ceilings are intentionally conservative:

| Source role | Maximum |
|---|---:|
| JSON API record | 2 MiB |
| Official Markdown or text | 4 MiB |
| Official contract/certification PDF | 32 MiB |
| Complete retained package | 64 MiB |

Connect timeout is 5 seconds, read inactivity timeout is 15 seconds, the per-source deadline is 60
seconds, and the package deadline is 180 seconds. These values prevent an acquisition command from
waiting or consuming resources without bound. They are policy defaults, not evidence that every
future venue document will fit; B1b-2 should measure real source sizes before any adjustment.

All sources are first written beneath a unique sibling directory such as
`.candidate.<random>.partial`. Only after every source, the canonical manifest, total package size,
and a complete `SourceEvidence.load` verification succeed does that directory receive the requested
final name. Expected failures, transport errors, timeouts, and Python-level interrupts remove the
partial directory. Existing output is never overwritten.

This is atomic publication, not full crash durability. SIGKILL or power loss can leave the uniquely
named partial directory because no cleanup handler can run. The current package documents that as
operational debt rather than claiming more than the code proves.

### Declared facts and observed facts are separate

Source-manifest V1 used an operator-supplied retrieval timestamp. That was sufficient to bind bytes
retrospectively, but it could not prove what the acquisition tool itself saw.

Source-manifest V2 records the boundary explicitly:

| Operator declares | Tool observes and records |
|---|---|
| source ID | retrieval start and completion UTC |
| semantic role | monotonic elapsed milliseconds |
| requested URL | final URL and every redirect hop |
| retained relative path | final HTTP status |
| optional stricter byte limit | selected response headers |
| optional narrower media allowlist | normalized media type |
| venue/environment intent | exact byte count and SHA-256 |
| | acquisition tool name and version |

This matters because labels and observations have different trust. An operator can say “this is the
market record,” but the tool must say which endpoint actually answered, when it answered, what it
returned, and which bytes were retained.

The existing retrospective reviewed package remains V1. Converting it to V2 would require making
up redirect, response, and timing observations that were never retained. Compatibility is stronger
when old evidence keeps its honest limitations.

### Schema and runtime now have a shared acceptance boundary

JSON Schema is useful to editors and external tools, but it cannot by itself prove that a file is
canonically encoded, that a hash matches another file, that a retained path is safe, that source
bytes agree with projected terms, or that decimal arithmetic is exact.

B1b-1 therefore keeps handwritten Draft 2020-12 schemas and handwritten runtime validation, but
uses the same reviewed examples to test their overlap:

- a positive document must pass both;
- a schema-addressable one-defect mutation must fail both; and
- cross-file, filesystem, hash, canonical-byte, source-projection, and arithmetic rules are named
  as runtime-only rather than pretending the schema enforces them.

Handwritten schemas were retained because they expose policy directly during review. Generating
them from Python types now would create a third abstraction before a second real product proves
which structures are stable. The critique records broader parity matrices as follow-up work; the
current matrix establishes the method and closes the material nested-schema gap.

### Refusal codes are part of the interface

Before B1b-1, callers often had to match human-readable exception text. The module now raises
`ProductTermsError` with a registered stable code. Constructing the exception with an unregistered
code is a programming error.

The CLI contract is:

| Outcome | Exit status | stdout | stderr |
|---|---:|---|---|
| Success | 0 | one JSON result | empty |
| Expected refusal | 2 | empty | `error: CODE: diagnostic` |
| Unexpected failure | 1 | unspecified | traceback |

Code names and meanings are compatibility promises. Diagnostic prose may become clearer and is not
byte-stable. This lets scripts branch on `AcquisitionTimeout` versus `SourceHashMismatch` without
depending on a path or sentence.

### Offline verification follows the complete V3 chain

Hashing an artifact at creation is not enough if later verification skips one link. B1b-1 expands
`verify-lineage` so a result verification checks:

- the V3 configuration hash;
- normalization and feature manifests;
- normalized events and feature rows;
- normalized `product.json`;
- copied `product_terms.json` and conversion policy;
- product identity and hash binding between normalization and features;
- terms, source, review, and conversion hashes declared by the configuration;
- result-manifest upstream hashes and embedded product metadata; and
- orders, fills, ledger, and risk-trace bytes.

Each check is offline. A mutable venue endpoint is never consulted to decide whether an old result
is still valid. Tampering tests change one layer at a time and require refusal. Separate tests feed
valid venue values that the integer core cannot represent and prove that the backtest leaves no
final or partial output instead of rounding.

### How the tests avoid false confidence

Acquisition tests use fake sessions, fake responses, and injected clocks. They exercise redirect,
media, size, timeout, content, interruption, and cleanup behavior without trusting a live network
or today's venue behavior. The positive acquisition still streams through the same production
function and then loads and schema-validates the resulting source-manifest V2.

Temporal tests copy the reviewed catalog into temporary directories and introduce one interval
defect at a time. Schema parity tests use reviewed positives and one-defect negatives. V3 lineage
tests build deterministic normalization, feature, and result artifacts, copy them, mutate one
artifact or manifest, and require the intended refusal.

This style matters: a live request test could pass today and fail tomorrow for reasons unrelated to
the code, while a broad happy-path test might fail without identifying which invariant mattered.
Offline one-defect tests make both cause and expected refusal reviewable.

### Why we did not broaden the package

B1b-1 deliberately did not add a second reviewed market, refactor the module around an imagined
adapter, introduce content-addressed storage, or add fee and settlement behavior.

- A real second product belongs in B1b-2 because its evidence should shape the abstraction.
- Content-addressed storage solves a measured duplication problem; the current one-package catalog
  does not provide that measurement.
- Fee, accounting, and settlement correctness depend on stronger reviewed legal evidence and are
  independent economic packages.
- Live-network tests would weaken reproducibility and make normalization or backtesting depend on
  external state.

The result is intentionally strict and somewhat repetitive. At the present scale, visible checks
and exact hashes are easier to audit than a generalized metadata platform.

## B1b-2 in plain language

B1a answered, “Can one historical market be tied to reviewed product rules?” B1b-1 answered, “Can
that evidence be acquired and verified without loose redirects, unbounded downloads, ambiguous
time intervals, or shallow lineage checks?” B1b-2 asks the next question:

> Does the boundary still work when the product is genuinely different and the complete linked
> document set is retained at the time of review?

The answer is yes, within a carefully limited claim. We added the climate-family market
`KXHMONTH-26JUL`, retained all eight required first-party sources twice, projected its terms,
recorded field-level evidence addresses, declared review responsibility, added it to the catalog,
and selected it through offline normalization and feature lineage. We did not implement climate
settlement, fees, PnL, or multi-market replay.

## What we added

The immutable package is:

```text
configs/product_catalog/kalshi/production/markets/KXHMONTH-26JUL/
  2026-07-17T150716Z-150837Z-contemporaneous-bracketed/
```

It contains two observations of these official sources:

| Source | Why it is present |
|---|---|
| Market JSON | Market identity, rules, price grid, lifecycle, payout, and labels |
| Event metadata JSON | Event membership and settlement-source identity |
| Series JSON | Series identity, fees, settlement source, and linked-document identities |
| Fixed-point Markdown | Venue price and quantity representation context |
| Fee-rounding Markdown | Fee-rounding identity; fees remain unapplied |
| Settlement Markdown | General settlement context; settlement remains unapplied |
| HMONTH contract-terms PDF | Product-specific legal/economic terms for human review |
| HMONTH certification PDF | First-party certification evidence for human review |

Every opening source was byte-identical to its closing counterpart. The combined package is about
484 KiB. Its key canonical payload hashes are:

| Artifact | Payload SHA-256 |
|---|---|
| Source manifest V3 | `d2dd466010b27750f39a980bd2afc3b4f320702cea7e7a27eeb152f5ab8921d8` |
| Product terms V2 | `f755e613ac77f093710e532b9a94e9937a125b9c7da75ef56945d5b4a1266e2c` |
| Evidence map V1 | `9401ca5b8acfa3f274cf3fa24a6231ca0eae64b537e8211d7d8028307c70a2b1` |
| Review V2 | `73c62a0d5b00bfee4067cbf4c64eefa26cfb41bff95cf74a0a40ee8b048b867b` |

These hashes are identities, not claims of correctness by themselves. They let every later verifier
answer “are these exactly the bytes that were reviewed?” The source projection and human review
answer the separate question “do these bytes support these terms?”

## How the two-observation bracket works

A single retrieval instant cannot support both endpoints of an interval. We therefore acquired the
same complete source inventory twice:

```text
opening acquisition                              closing acquisition
started -------- completed                       started -------- completed
                    |                              |
                    +------ accepted interval -----+
                    [                              )
       2026-07-17T15:07:16.002543Z    2026-07-17T15:08:37.512205Z
```

The left endpoint is the completion of the opening acquisition. Before that moment, not every
opening source had been observed. The right endpoint is the start of the closing acquisition. Once
that acquisition began, we no longer treat the earlier observation as the sole endpoint evidence.
The interval is half-open, so a capture exactly at the right endpoint belongs to a later revision or
to a catalog gap—not to this package.

Assembly refuses if the observations use different policies, have different source membership,
roles, requested URLs, or media, or have invalid time ordering. Static Markdown and PDF sources
must have identical hashes. Market, event, and series JSON may legitimately change, but every
mechanically projected field must still support the reviewed terms at both endpoints.

This is conservative but not magical. Two equal observations do not prove that a mutable endpoint
could not have changed and changed back during the 81-second gap. The package proves two complete
endpoint observations under one policy, not continuous monitoring.

## Why acquisition policy became an artifact

Source-manifest V2 recorded what happened, but the meaning of “acceptable acquisition” lived in
Python constants: approved hosts, redirect statuses, media types, byte limits, timeouts, and chunk
sizes. If those constants changed later, an old manifest could be interpreted under new rules.

B1b-2 adds `pmm.product_acquisition_policy.v1`. Its canonical payload hash is
`583204c3d5a177d6247c20d1c3b12543aab6b454c8066bb3ee4943d974d3792b`. Acquisition-spec V2 names
that exact identity, and source-manifest V3 carries it forward. Runtime accepts only the frozen
supported payload.

We considered three approaches:

| Approach | Benefit | Problem | Decision |
|---|---|---|---|
| Keep only tool-version/constants | Few files | Old evidence can drift when constants change | Rejected for new acquisitions |
| Add immutable policy identity | Old evidence names exact rules without changing all formats | Adds one artifact and runtime branch | Chosen for B1b-2 |
| Version every schema immediately | Maximum explicit separation | Needlessly changes terms, catalog, normalization, features, and results that already carry exact hashes | Use only where semantics actually change |

The important compatibility rule is that old V2 manifests remain under their frozen legacy
interpretation. A future policy change must add a new identity, and a semantic shape change must add
a successor schema. It must never edit the meaning of this policy in place.

## The complete artifact chain

```text
acquisition policy
       |
       +--> opening acquisition --+
       |                           +--> source manifest V3
       +--> closing acquisition --+          |
                                               +--> product terms V2
                                               |          |
                                               +--> evidence map V1
                                                          |
                                                          +--> review V2
                                                                 |
                                                                 +--> catalog V1
                                                                        |
raw/synthetic capture + capture time -----------------------------------+
                                                                        |
                                                                        v
                                                        normalization/product map V2
                                                                        |
                                                                        v
                                                               feature manifest V2
                                                                        |
                                                                        v
                                                        backtest/result V3 lineage
```

Each stage names exact upstream hashes. This makes refresh additive: a changed source, policy,
terms projection, evidence map, or review creates a new identity and package. It does not rewrite a
past normalized dataset or result.

## What evidence anchors really verify

The HMONTH evidence map contains 30 sorted product-term pointers. Every entry is supported by an
opening and closing anchor. The behavior depends on source type:

| Locator | Runtime guarantee | Human responsibility |
|---|---|---|
| JSON pointer, mechanically projected | The source pointer and term pointer both resolve and their JSON values are exactly equal. | Decide that the selected source field has the intended venue meaning. |
| JSON pointer, human reviewed | Both pointers resolve and the retained source hash matches; values are not required to be literally equal. | Interpret transformations or multi-field meaning. |
| Markdown section | The retained hash matches and the named text occurs in the document. | Confirm the occurrence is the intended heading/section and supports the claim. |
| PDF page/section | The retained hash matches; the locator has a positive page and nonempty section; the file begins with a PDF signature. | Open the retained PDF and confirm that the page/section exists and supports the claim. |

That last row is deliberately precise. The current runtime does not extract a PDF page or search
for the section text. Therefore a PDF locator is a durable human review address bound to exact
bytes, not machine proof of legal prose. Similarly, Markdown uses text occurrence rather than a
full Markdown-section parser. The critique ranks stronger document-anchor verification as the
highest-impact follow-up.

Evidence-map V1 is also selective rather than a complete anchor for every leaf of product-terms
V2. Important projected identity, price, lifecycle, fee, settlement, rule, and payout fields are
represented, while other fields are protected by product validation, source projection, or local
policy. A future coverage profile should make those categories mechanically explicit.

## Why product-terms V2 was necessary

The real HMONTH market record contains an empty `rules_secondary` string. Product-terms V1 requires
that string to be nonempty. Three responses were possible:

1. invent secondary text;
2. weaken V1 for every historical package; or
3. add a successor that can represent the observed value.

We chose the third. Invented text would be false evidence. Weakening V1 would silently change the
meaning of an accepted historical format. Product-terms V2 differs only where the new evidence
requires it: secondary rules may be empty. All other current binary, one-dollar, fixed-point, fee,
settlement, and exact-conversion boundaries remain in force.

This is the central schema-evolution rule: preserve old meanings, and create a successor only for a
real value the old schema cannot represent honestly.

## What review V2 means—and does not mean

Review V1 bound terms and source hashes but did not name responsibility. Review V2 adds:

- reviewer identity `ronit`, classified as `repository_declared`;
- responsibilities for linked-document completeness, product projection, evidence interpretation,
  and interval consistency;
- five accepted checklist items;
- acquisition-policy and evidence-map hashes; and
- the same exact effective interval as terms and catalog.

This improves accountability: Git history and the review document show which repository identity
accepted which bytes and responsibilities. It is not a signature, independent legal approval,
separation of duties, or an organizational role system. There is also no append-only runtime
revocation/supersession record yet. Those controls should be added only after the real human process
exists.

## How the catalog and downstream pipeline use the package

Catalog V1 did not need a successor. Its entry already names the market, exact interval, package
path, and source/terms/review hashes. It now has two entries: the original retrospective WNBA
package and the contemporaneous HMONTH package. Selection uses market ticker plus complete capture
interval; gaps, overlaps, and ambiguity refuse.

Normalization/product-map V2 and feature V2 also needed no schema change. They copy and bind the
selected package identities. Backtest/result V3 already carries those identities through
configuration, results, and every result artifact. This is additive compatibility: downstream
formats did not need to understand the internal difference between terms V1 and V2 because they
bind the exact reviewed package.

The HMONTH-specific focused test currently proves catalog selection, synthetic-capture
normalization, and feature lineage. The older WNBA fixture still exercises the complete V3
configuration/result mutation chain. A complete HMONTH V3 result-chain test remains useful future
coverage; the current work does not claim that a real HMONTH market-data capture was made inside
the short evidence interval.

## Failure and publication behavior

Acquisition streams bytes into an unpublished temporary directory, hashes incrementally, checks
redirects manually, validates role/media/content, applies per-source and cumulative limits, and
publishes by rename only after the source manifest reloads successfully. Expected exceptions and
interruptions remove the partial directory. Terms, evidence, and review builders similarly remove
their final file if post-write validation fails.

Assembly also writes to an unpublished directory and publishes only after loading the combined V3
manifest. One known debt is that it currently flattens each source path to its basename; future
inputs with two equal basenames need explicit collision refusal or full-path preservation.

Process termination or power loss can still leave a stale hidden partial directory because no
exception handler can run. That is an operational cleanup/scavenging question, not a reason to
weaken atomic final publication.

## How we tested it without depending on today's internet

The checked-in source bytes came from explicit operator acquisition. Tests never fetch them again.
They use retained fixtures, fake HTTP sessions/responses, injected clocks, temporary directories,
and minimal synthetic captures.

The four new focused cases prove:

- the checked-in HMONTH package, review V2, evidence map, policy, catalog interval, and conversion
  refusal load together;
- a changed JSON field anchor still refuses after the evidence and review hashes are recomputed;
- separate fake opening and closing acquisitions assemble into the exact bracket; and
- a synthetic HMONTH capture selects the second catalog entry and propagates normalization/feature
  lineage offline.

Those tests build on the B1b-1 matrix for redirects, media, streamed/cumulative size, timeout,
interruption, cleanup, semantic source mutation, interval adjacency/gap/overlap, public CLI behavior,
schema/runtime checks, nonrepresentable values, and complete WNBA V3 result lineage. The closeout
baseline is 22 focused product-term tests, 81 total Python tests, and 78 CTest tests.

The remaining gaps are important: PDF and Markdown semantic mutations, exact required-role
completeness, deeper new-schema parity, assembly basename collisions, Review V2 mutations, the new
CLI commands, and a complete HMONTH V3 result chain. The critique rates and prioritizes each one.

## Why we stopped here

The package proves the narrow thing B1b-2 needed to prove: the hardened metadata boundary can
support a complete, contemporaneous, genuinely different second product without rewriting old
artifacts or rounding values the core cannot represent.

We did not add fees or settlement because retaining the documents is not the same as implementing
their economics. We did not add multi-market replay because a two-entry metadata catalog is not a
replay scheduler or reconnect protocol. We did not add content-addressed storage, concurrency,
indexes, signatures, or universal venue adapters because the present scale and governance process
do not justify those abstractions yet.

## B1c: why stronger evidence needs successor formats

The B1b-2 package used honest but deliberately narrow evidence-map V1 semantics. A JSON pointer was
mechanical, a Markdown heading was a text occurrence, and a PDF page and section were an address for
the human reviewer. Source-manifest V3 also proved that opening and closing had equal membership,
but it did not know which roles the product family required. Two equally incomplete observations
could therefore agree with each other.

Changing those rules under the same schema names would make old evidence appear stronger than it
was. B1c instead freezes the old paths and adds a complete successor chain:

```text
evidence-profile V1
        |
        +--> acquisition-spec V3 --> source-manifest V4
        |                                  |
        +--> evidence-map V2 --------------+
        |                                  |
        +--> review V3 ---------------------+
                                           |
                              product-terms V1 or V2
```

The profile answers “what must exist and how is every term classified?” The manifest answers “what
did the acquisition tool actually retain?” The evidence map answers “where is the exact support?”
The review answers “which repository identity accepted these exact inputs and limitations?” Keeping
those questions separate prevents a role label, URL, or human checklist sentence from masquerading
as generic runtime enforcement.

### How PDF verification becomes deterministic

Extractor policy `poppler_page_text.v1` uses Poppler `pdfinfo` and `pdftotext` from the locked Nix
development environment. `pdfinfo` supplies page count; page extraction is exactly
`pdftotext -f {page} -l {page} -enc UTF-8 -nopgbrk {source} -`. The lock chooses the Nixpkgs
revision and Poppler build, and evidence-map V2 records both exact executable/version identities
plus normalization policy `pmm.document_text_normalization.v1` and its policy hash. Verification
fails if that identity is unavailable or different; it does not silently use Homebrew, a browser,
a Python PDF package, or OCR.

The first accepted lock selects Nixpkgs revision
`59682e0069f0ed0a452e2179a7f4c1f247027b9e` and `poppler-utils` 26.06.0. Runtime compares the
complete first version line from each tool's `-v` output, not a loose compatible-version range.

Human-facing PDF page numbers stay one-based. Runtime checks that the page exists, extracts only
that page, normalizes its text, finds one exact start marker and an optional unique later end marker,
and hashes canonical JSON containing the locator kind, normalization-policy identity, boundary, and
bounded text. The section includes its start line and excludes its end line. The full PDF still has
its independent source hash. Consequently, changing a page number, boundary, section contents,
source PDF, or extractor identity cannot preserve the old claim after outer hashes are recomputed.

This is still not legal reasoning. A matching fingerprint proves that the retained page contains
the reviewed exact section under the pinned extractor. The repository-declared reviewer remains
responsible for the meaning assigned to that section.

Malformed or extraction-blocked encrypted PDFs refuse. Scanned/image-only and textless pages refuse
because B1c has no OCR design. Normalization uses strict UTF-8, Unicode NFC, LF (including form-feed
conversion), NBSP-to-space conversion, collapsed horizontal whitespace and blank runs, trimmed line
edges, no surrounding blank line, and explicit mappings for the common `ff`, `fi`, `fl`, `ffi`, and
`ffl` Unicode presentation ligatures. Poppler's remaining font decoding and reading order belong to
the extractor identity.

### How Markdown verification differs from substring search

Evidence-map V2 recognizes only ATX headings outside fenced code blocks: at most three leading
spaces, one through six `#` characters, then whitespace. A locator contains the complete ancestor
path of exact level/NFC-text pairs. That path must be unique, and its body continues through child
headings until the next heading of the same or shallower level. A body-text lookalike, duplicate
path, changed level, renamed heading, or changed bounded contents refuses.

Markdown and PDF use the same common normalization policy, with the PDF ligature mappings added for
extracted text. The control artifact stores a SHA-256 fingerprint rather than copying source prose,
which avoids turning an evidence map into a second copyrighted document corpus.

### How generic completeness works

Each profile lists stable logical source keys. Required means one per endpoint. Optional means zero
at both or one at both. Not applicable means zero at both plus an explicit reason. Runtime compares
each endpoint with the profile, so equal-but-incomplete observations fail. Static documents must be
byte-identical. Mutable JSON may change, but projected values must still equal the reviewed terms at
both endpoints.

The profile ties linked contract and certification roles to series-record co-presence. It does not
silently parse and compare document URLs; that stronger identity claim needs a mechanically
projected evidence entry or a review limitation. Source IDs and full relative paths remain unique;
preserving the complete path below each observation removes the old same-basename assembly hazard.

Every product-term leaf is then classified as mechanically projected, human-reviewed, derived,
repository/local policy, unsupported, or not applicable. Only the first two need source anchors.
Derived facts need complete named inputs. Local and unsupported facts must remain visibly repository
policy or non-claims. Not applicable must be declared, never guessed from absence.

### Why existing artifacts still verify

HMONTH remains source-manifest V3, evidence-map V1, and review V2. Its bytes already contain all
eight roles, so a compatibility test can compare that observed set with the new profile, but the
test does not rewrite the package or upgrade its PDF semantics. WNBA remains retrospective V1 with
six retained sources and explicit missing-linked-document limitations. Catalog V1 and downstream
V2/V3 artifacts keep working because they bind exact package hashes rather than assuming one
internal package version.

`EvidenceProfileMismatch` is added only for profile identity failures. Missing roles remain
`EvidenceIncomplete`; document extraction or fingerprint failures remain `EvidenceAnchorMismatch`.
Keeping those categories distinct gives callers stable recovery guidance.

B2 should begin separately with multi-market observed-data ordering and recovery. Stronger metadata
does not itself provide broader observed data, continuous source history, execution calibration, or
economic accounting.

## Non-claims

B1 does not calculate fees, maintain double-entry accounts, calculate PnL, process settlement,
model collateral or margin, calibrate fills, infer queue position, model hidden liquidity, recover
multi-market connections, place paper or live orders, or begin ML work. It does not change Phase 3
matching, core integer types, `AccountRiskProjection`, risk rejection categories or ordering,
post-only behavior, watermarks, kill switches, or closed risk fixtures.

The product metadata is authoritative within the retained evidence and documented review boundary.
The overall system is still a research platform, not evidence of profitability, paper readiness,
live readiness, or venue-equivalent execution.
