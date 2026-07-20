# Current State and Remaining Work

## Purpose and authority

This is the living execution roadmap for the repository. It tells maintainers and coding agents:

- what is implemented now;
- what the implementation actually proves;
- what remains unfinished;
- which work should happen next;
- which dependencies must be satisfied before later phases begin; and
- how to update the roadmap without turning aspiration into a current capability claim.

Use this document after `AGENTS.md`, `PROJECT_CHARTER.md`, and the accepted ADRs. The charter owns
the long-term vision. ADRs own architectural decisions. This document owns current status,
remaining-work order, and the handoff between bounded implementation packages.

When this document disagrees with a current accepted ADR, the ADR wins and this file must be
corrected. When an older engineering note calls something "next" but this document records it as
complete, this current-state document wins; the older note remains useful historical reasoning.

## Status snapshot

| Field | Current value |
| --- | --- |
| Last reviewed | 2026-07-20 |
| B2c tooling status | Offline V1 tooling plus initial additive B2c-H V2 supervisor/verifier slice implemented; complete B2c-H acceptance matrix remains open |
| B2c retained evidence status | Not acquired; B2A-10/11 and B2B2-05/06 remain open or measurement-pending |
| B2c tooling implementation and test commits | `e6a211b` and `4f77020` |
| B2c deeper review commit | `bdb5ea1` |
| B2c-H implementation commits | `842db83`, `d19ac3b`, and `38fb667` |
| B2c-H design and critique commit | `580da7a` |
| Baseline before B2c-H implementation handoff | `5d4da2d`; clean `main`; ten commits ahead of `origin/main` |
| Graphify workflow integration commit | `39b57c0` |
| Baseline before B2c-H design review | `343cbbc`; clean `main`; seven commits ahead of `origin/main` |
| B2b-2 implementation status | Complete |
| Last completed package | B2c offline evidence and measurement tooling implementation; B2c-H remains current |
| B2b-2 implementation and test commits | `a0faa89` and `77cf533` |
| B2b-2 documentation and review commits | `9f8e3a4` and `025508e` |
| Baseline before B2c roadmap handoff | `025508e`; clean `main`; synchronized with `origin/main` |
| B2b-1 implementation and test commits | `edf3b44` and `dd3dc74` |
| B2b-1 documentation and review commit | `fce665f` |
| B2b-1 closure baseline before this roadmap handoff | `fce665f`; clean `main`; four commits ahead of `origin/main` |
| B2a-1 implementation and test commits | `b68f42b` and `981f744` |
| B2a implementation commits | `520d0a0`, `399e500`, `48f2a25`, and `a04b0c1` |
| B2a documentation and review commits | `8036eb9`, `17e15bc`, and `0c1da77` |
| Branch state before B2a-1 implementation | `main` sixteen commits ahead of `origin/main` |
| Recent B1c closure commits | `f826fae`, `8262c2c`, and `4825aa5` |
| Recent B1b-2 implementation commits | `b3da27e`, `b28a3ad`, `4ba99a6`, and `ff9dbe6` |
| Recent B1b-2 review commits | `73dc566`, `6e22b27`, and `61a2188` |
| Recent B1b-1 commits | `902a2df`, `5d40d64`, `e33885a`, `3d6bf54`, `6d489e3`, and `dbd6fd8` |
| Recent B1a commits | `ba01e9f`, `113a4bd`, `8a867d7`, `fc2dd88`, and `6dc3000` |
| C++/CTest validation | 78 tests passing (post-V2 slice) |
| Python validation | 171 tests passing (post-V2 slice) |
| Focused capture validation | 15 tests passing |
| Focused Phase 7 validation | 43 tests passing |
| Focused B2b-2 validation | 10 tests passing |
| Focused B2c evidence and measurement validation | 22 tests passing |
| Focused product-term validation | 42 tests passing |
| Focused checkpoint-reader validation | 17 tests passing |
| Focused fixture-integrity validation | 17 tests passing |
| Lifecycle conformance corpus | 16 reviewed fixture pairs |
| Checkpoint conformance corpus | 26 reviewed fixture pairs |
| Local Graphify navigation | Refreshed at `5d4da2d`: 6,120 nodes, 9,236 built edges, 475 communities; advisory only, and earlier raw-extraction health warnings are not claimed closed |
| Current roadmap phase | Phase 7 foundation implemented; research-validity work remains |
| Next bounded package | B2c-H evidence-verifier and measurement-lifecycle hardening |
| Immediate next action | Complete the remaining approved B2c-H named role, lineage, inventory, and scanner matrix; do not acquire product evidence or capture |

These counts and commit references are evidence snapshots, not timeless guarantees. The next agent
must verify the current git state and test counts rather than copying them forward blindly.

## Status vocabulary

Use these terms consistently when updating the roadmap:

| Status | Meaning |
| --- | --- |
| Complete | Implemented, validated, documented, and within the stated boundary. |
| Current | Implemented and supported now, without implying broader roadmap completion. |
| Next | The single recommended bounded package after current work. |
| Planned | Ordered work with a known dependency and acceptance boundary. |
| Deferred | Deliberately outside the current package; not forgotten and not implied. |
| Blocked | Cannot be completed credibly without external evidence, data, authority, or infrastructure. |
| Aspirational | Part of the charter but not yet designed or implemented. |

Never use "complete" to mean that a demo exists. Never use "production" to describe a test-only
format, model-derived fill, local oracle adapter, research ledger, or exchange-only recovery path.

## Source map

Use these documents to verify or deepen a claim in this roadmap:

- [Project charter and long-term phases](../../PROJECT_CHARTER.md)
- [[00 Project Hub/Project Hub|Project navigation and working agreements]]
- [[01 Roadmap/Phase 7 Historical Replay and Backtesting|Phase 7 roadmap boundary]]
- [[02 Architecture/ADR-007 Deterministic Historical Replay and Backtesting|Historical replay architecture]]
- [[02 Architecture/ADR-008 Calibrated Execution Accounting and Research Evaluation|Execution, accounting, and evaluation boundary]]
- [[02 Architecture/ADR-009 Canonical Risk Conformance and Research Oracle Migration|Canonical C++ risk migration]]
- [[02 Architecture/ADR-010 Authoritative Product Terms and Artifact Lineage|Authoritative product terms and lineage]]
- [[02 Architecture/ADR-013 Multi-Scope Capture and Reconnect-Aware Normalization|Multi-scope capture and recovery boundary]]
- [[07 Engineering Notes/Phase 7 B2c-H Hardening Design|Reviewed B2c-H implementation design]]
- [[07 Engineering Notes/Phase 7 B2c-H Hardening Explained|B2c-H plain-language explanation]]
- [[07 Engineering Notes/Phase 7 B2c-H Hardening Critique|B2c-H design critique and debt register]]
- [[02 Architecture/ADR-011 Bracketed Product Evidence and Review Responsibility|Bracketed evidence and review responsibility]]
- [[02 Architecture/ADR-012 Deterministic Document Evidence and Completeness Profiles|Deterministic document evidence and completeness profiles]]
- [[07 Engineering Notes/Phase 7 Critique|Original Phase 7 critique]]
- [[07 Engineering Notes/Product Terms Source and Review Guide|Product-term source and review guide]]
- [[07 Engineering Notes/Product Terms Refusal Codes|Product-term refusal-code compatibility reference]]
- [[07 Engineering Notes/Authoritative Product Terms Explained|Product-term implementation walkthrough]]
- [[07 Engineering Notes/Authoritative Product Terms Critique|Product-term severity-ranked critique]]
- [[07 Engineering Notes/Research Execution Foundation Critique|Research execution critique]]
- [[07 Engineering Notes/Canonical Risk Conformance Critique|Current risk-conformance debt and reviews]]
- [[07 Engineering Notes/Canonical Risk Conformance Explained|Risk-conformance walkthroughs]]
- [[07 Engineering Notes/Risk Conformance Fixture Guide|Fixture and integrity authoring guide]]

Some critique documents are chronological and intentionally retain findings that later work closed.
In particular, older Phase 7 and research-execution notes describe Python-versus-C++ risk drift,
missing canonical risk traces, and missing runnable C++-oracle examples. ADR-009 and later
conformance work closed those gaps for new V2 research configurations. The Python implementation
remains only a V1 compatibility path and test-only reference; it is not the default for new V2
runs. Do not reopen a closed finding without checking the current implementation and later notes.

## Executive summary

The repository has a strong deterministic systems foundation:

- Phases 1 through 6 are complete within their documented boundaries.
- Phase 7 has a working V1 historical-research foundation.
- New V2 backtests use canonical C++ account risk and emit hashed risk traces.
- New normalization V2, feature V2, and backtest V3 artifacts carry reviewed authoritative
  product-term lineage and exact conversion policy.
- Product-term acquisition now has exact three-way time consistency, bounded first-party redirect
  validation, observed source-manifest V2 provenance, schema/runtime parity, stable refusal codes,
  and deeper offline lineage mutation evidence.
- Future reviewed packages now have profile-bound source completeness and deterministic structural
  document anchors without changing the bytes or meaning of either accepted package.
- Lifecycle and checkpoint conformance evidence is broad and reviewed.

The repository is not yet a credible profitability, paper-trading, or live-trading system. Its
largest remaining gaps are no longer basic matching or simulation mechanics. They are:

1. broader contemporaneous authoritative product evidence across markets;
2. broader and recoverable observed-market data;
3. calibrated or sensitivity-tested execution assumptions;
4. real accounting, collateral, fees, and settlement;
5. compatible experiment comparison and reporting;
6. full-run recovery beyond the exchange boundary;
7. machine-learning datasets, baselines, training, and evaluation;
8. operational gateways, reconciliation, monitoring, and safety controls.

The immediate risk-conformance tail should be finished, but it must not consume the project
indefinitely. After the two highest-value remaining parity packages, work should return to Phase 7
research validity.

## What is complete now

### Phase 1: repository foundation — complete

Current evidence includes:

- CMake-based C++20 build;
- GoogleTest/CTest integration;
- formatting and test scripts;
- Python/uv workflow;
- documented repository layout and engineering standards; and
- an Obsidian-compatible documentation vault.

Boundary: this establishes reproducible local development, not deployment packaging or hosted CI
operations for every target platform.

### Phase 2: core domain types — complete

Current evidence includes:

- strongly typed identifiers;
- binary-market and contract rules;
- fixed integer price and quantity vocabulary;
- orders, trades, fills, inventory, and validation results; and
- separation between immutable domain facts and mutable matching state.

Boundary: fees, collateral, settlement, product-term ingestion, and accounting remain outside the
core types implemented in this phase.

### Phase 3: limit order book — complete

Current evidence includes:

- deterministic price-time priority;
- matching, cancellation, partial fills, and market-order expiry;
- self-trade prevention;
- dense bounded price ladders for binary prices;
- reservation of execution identifiers before mutation; and
- deterministic and randomized reference-model tests.

Boundary: the book owns live matching state only. It does not own strategy, inventory, risk,
historical-market truth, durable persistence, or venue connectivity.

### Phase 4: exchange simulator and exchange-only durability — complete

Current evidence includes:

- one book per registered contract;
- deterministic logical-time command ordering;
- global order, trade, and event identifiers;
- market lifecycle gates;
- sequenced event journals;
- checkpoints and deterministic replay;
- opt-in checksummed write-ahead command/event records;
- atomic exchange checkpoint replacement; and
- recovery through the normal matching path.

Boundary: durability protects the exchange boundary only. Coordinator, strategy, risk,
market-maker, accounting, gateway, portfolio, and complete process recovery remain separate.

### Phase 5: deterministic baseline agents — complete

Current evidence includes:

- seeded noise, momentum, mean-reversion, informed, and liquidity-taking agents;
- a deterministic coordinator and schedule;
- pull-based projections of the sequenced exchange journal; and
- checkpoint continuation for agent schedule and random state.

Boundary: agents produce intents and do not call the order book directly. They do not own risk,
inventory truth, accounting, or gateway state.

### Phase 6: baseline market making and account risk — complete

Current evidence includes:

- fixed-spread passive quoting;
- integer inventory skew;
- stale-quote cancellation and replacement;
- external account-risk admission;
- pending reservations and ingress binding;
- event-fed inventory and exposure;
- kill-switch behavior;
- checkpoint continuation; and
- ingress-correlated exchange rejection handling.

Boundary: this is a deterministic systems baseline. It does not establish optimal quoting,
calibrated fills, PnL, collateral, settlement, or venue-ready execution.

### Phase 7 foundation: historical replay and research orchestration — current

Implemented surfaces include:

- passive Kalshi raw capture;
- immutable normalization with hashes and provenance;
- fixed-point observed values and UTC logical ordering;
- duplicate and gap validation;
- Level-2 cursor projection and snapshots;
- causal spread, depth, imbalance, midpoint, and last-trade features;
- deterministic strategy scheduling;
- `no_fill_v1` and `trade_touch_v1` execution assumptions;
- explicit logical latency;
- append-only result artifacts and manifests;
- `Observed`, `Reconstructed`, `Synthetic`, and `ModelDerived` truth labels;
- canonical C++ risk for new `pmm.backtest.v2` configurations;
- hashed complete risk traces;
- an opt-in unresolved-settlement cash-flow ledger; and
- deterministic configuration and artifact hashing;
- immutable reviewed first-party product-source bundles and formal schemas;
- source-backed price, quantity, payout, lifecycle, settlement, fee, and identity projections;
- exact refusal of lossy cent/whole-contract conversion; and
- offline-verifiable V2/V3 product lineage through result artifacts.

Boundary: Phase 7 is not complete as a credible research platform. The current data, execution,
accounting, compatibility, and recovery limitations below remain material.

### Canonical risk-conformance foundation — current

Implemented evidence includes:

- 16 reviewed lifecycle fixture pairs;
- direct C++, test-only Python, and frozen-V1 eligibility boundaries;
- 26 reviewed checkpoint fixture pairs;
- typed checkpoint rejection categories and fixed first-failure ordering;
- strict captured-checkpoint validation in independent C++ and Python readers;
- canonical JSON and manifest SHA-256 verification;
- a fixed-root fixture integrity authoring tool;
- named parser-refusal coverage; and
- real copied-script subprocess coverage for public CLI statuses, streams, selection, repair, and
  idempotence.

Boundary: checkpoint serialization and the Python checkpoint model remain test-only. The frozen V1
oracle remains a compatibility adapter and is ineligible for checkpoint fixtures.

## Remaining work by track

## Track A: close the current conformance tail

This track is small, local, and should end after the highest-value parity gaps are closed.

### A1. Lifecycle-V1 mutation-and-repair cycle — complete

Goal: prove that the copied public integrity CLI performs the complete lifecycle-root write path,
not only lifecycle selection and stale reporting.

Required evidence:

- copy the real script and lifecycle corpus to a temporary repository;
- deliberately edit and noncanonically serialize one temporary lifecycle member;
- run `--corpus v1 --write`;
- require exact exit, stdout, and stderr behavior;
- prove only the intended member and manifest changed;
- prove canonical member bytes;
- prove the member and manifest-payload hashes;
- verify the repaired corpus successfully; and
- prove repeated `--write` is byte-identical.

Non-goal: do not change a reviewed lifecycle fixture, generate an expected trace, or duplicate the
checkpoint refusal matrix.

Completion evidence:

- commit `4e6336b` parameterizes the copied-script write cycle over the existing checkpoint donor
  and the explicit temporary lifecycle donor `v1/lifecycle.json`;
- the lifecycle row changes the authored temporary `fixture_id` to `lifecycle_cli_edited`, uses
  noncanonical indentation, and leaves its manifest stale before invoking the writer;
- exact status and stream assertions require only `v1/lifecycle.json` and `v1/manifest.json` to be
  reported and changed;
- repaired bytes preserve the authored identifier and equal the canonical authored document;
- member and manifest-payload SHA-256 values are reconstructed independently;
- ordinary verification preserves the repaired snapshot; and
- repeated `--write` is byte-identical;
- commit `54d030b` records the completed guide, explanation, critique, and roadmap promotion;
- commit `7f8b2bc` adds the severity-ranked post-implementation critique; and
- commit `7642969` adds the deep what/how/why walkthrough and maintainer checklist.

Boundary: this is temporary integrity-repair evidence. It does not change or execute a reviewed
lifecycle pair, generate a semantic trace, or expand the integrity tool or frozen V1 adapter.

### A2. Remaining Python checkpoint-reader mutation parity — complete

Goal: close schema-specific rejection cases that the C++ checkpoint reader covers but the Python
reader does not yet mirror.

Completed approach:

- use the completed C++/Python inventory below rather than repeating a broad rediscovery pass;
- keep C++ and Python implementations independent;
- use canonical temporary documents with current hashes;
- require field-specific diagnostics; and
- preserve checkpoint rejection semantics and first-failure ordering.

The asymmetric inventory recorded at `7642969` is now mirrored by one named Python matrix:

| Mirrored refusal | Donor and single temporary mutation |
| --- | --- |
| Missing fixture `kind` | Remove `kind` from `roundtrip_empty_state.json`. |
| Numeric JSON where a decimal string is required | Set `checkpoint_zero_ingress.json` `checkpoint.net_position_contracts` to numeric `1`. |
| Unknown checkpoint side | Set the first live order side in `checkpoint_buy_exposure_limit.json` to `hold`. |
| Decreasing checkpoint identifiers | Swap the first two live orders in `checkpoint_active_order_limit.json`. |
| Wrong checkpoint schema | Set `checkpoint_zero_ingress.json` `checkpoint.schema` to `pmm.risk_checkpoint.v2`. |
| Bad manifest payload hash | Replace top-level `payload_sha256` with 64 `a` characters without rehashing it. |
| Symlink manifest member | Replace temporary `roundtrip_empty_state.json` with a symlink to renamed real bytes. |
| Duplicate manifest member | Make the second entry reuse the first entry's expected-trace name and digest, then rehash the payload. |
| Continuation after rejected restore | Give `checkpoint_zero_ingress` one kill-switch operation and append a matching continuation transition after its rejected restore. |

Completion evidence in `ecca209`:

- `test_rejects_every_remaining_cpp_reader_mutation` executes the nine rows as named subtests,
  with explicit local mutation functions rather than a generic mutation framework;
- every row starts from a fresh temporary copy of `checkpoint_v1`;
- member changes use canonical UTF-8 sorted-key JSON with exactly one final LF;
- member mutations receive a complete manifest rehash, the duplicate-member row receives only a
  payload rehash, the bad-payload row deliberately leaves only that digest stale, and the symlink
  row preserves the real target bytes and current member digest;
- field and rule diagnostics identify the missing `kind`, decimal-string field, side, identifier,
  checkpoint schema, payload hash, non-symlink rule, duplicate membership, and rejected-restore
  continuation respectively;
- `_mutated_corpus_fails` snapshots every regular file byte plus symlink identity and target after
  mutation and proves verification is read-only; and
- focused validation passes 17 tests, the full Python suite passes 59 tests, all 78 CTest tests
  pass, and all three integrity selections report canonical/current.

The earlier Python mutation tests for unknown fields, noncanonical decimals, member hashes, unsafe
paths, unreferenced JSON, restore placement, rejected-restore state, and frozen-V1 eligibility
remain separate. The strict captured-checkpoint matrix and position-independent donor coverage
also remain unchanged.

Non-goal: do not expand production checkpoint semantics or convert the test-only JSON into a
durable production format.

### A3. Small conformance hardening — deferred

Lower-priority items:

- explicit 16-row cardinality assertions for both strict matrices;
- accepted signed and unsigned integer endpoints;
- compact current-state navigation for the long risk notes;
- a supported-platform note and Windows-specific path setup if Windows becomes supported;
- root README checkpoint discoverability;
- `--help` fragments;
- successful `all --write` coverage;
- injected subprocess translation of an atomic write failure;
- additional SHA padding-boundary vectors; and
- fuzz or property testing.

Track A exit: A1 and A2 are complete. Return to Phase 7 research validity unless new evidence
shows a higher-impact conformance defect. A3 remains deliberately deferred and is not a reason to
keep the conformance tail active.

## Track B: finish Phase 7 research validity

This is the highest-value project track after the conformance tail.

### B1. Authoritative product metadata — current, high priority

The repository needs versioned venue product terms for every researched contract:

- tick and price grid;
- lot size and quantity unit;
- payout terms;
- market lifecycle and expiration;
- settlement source and rules;
- fee schedule and rounding;
- market/event/contract identity; and
- provenance and content hashes.

Acceptance gate:

- normalization and backtest manifests identify the exact product-term version;
- price and quantity conversion refuses unsupported values;
- results with incompatible product terms cannot be compared silently; and
- tests cover missing terms, incompatible terms, and boundary values.

Why it comes first: execution, accounting, and ML labels can all be internally consistent while
still being wrong for the actual venue contract if product terms are missing.

#### B1a. Product-term schema and identity integration — complete

The first B1 package was design-first. The following pre-implementation boundary and questions are
retained as the acceptance record.

Pre-B1a implementation boundary:

- normalization writes `product.json` with schema `pmm.historical.product_map.v1` from capture and
  message identity;
- that document records ticker, venue market identity, and provenance, but it is not an
  independently sourced product-term record;
- normalized and backtest manifests do not yet require the exact tick, lot, payout, lifecycle,
  settlement, and fee-term identity described by ADR-007 and ADR-008; and
- current integer-cent and whole-contract behavior is a declared research limitation, not proof
  that every venue product has those terms.

Resolved B1a design questions:

1. Compare extending `product.json`, adding a separate immutable `product_terms.json`, and making
   product terms a configuration-owned input.
2. Decide which fields are authoritative venue facts, which are local conversion policy, and which
   are unsupported until sourced.
3. Define schema versioning, effective-time/version identity, source URL or document provenance,
   retrieval time, raw-source content hash, and canonical product-term content hash.
4. Define how ticker, event, market, and contract identity bind the terms to normalized records.
5. Define how normalization, feature, configuration, and result manifests carry or reference the
   exact terms hash without silently copying incompatible values.
6. Define deterministic price-grid and quantity-unit conversion, including refusal of unsupported
   or nonrepresentable values before a final artifact is published.
7. Define compatibility rules so runs with different product terms, fee schedules, or conversion
   policies cannot be compared silently.
8. Decide how tests use reviewed local source fixtures without network access or mutable current
   venue state.
9. Identify whether an ADR-007/ADR-008 amendment or a new ADR is warranted before implementation.

The approved design keeps capture-derived identity separate from an immutable source-backed
product-term document, references the latter by canonical content hash, and keeps network retrieval
outside deterministic normalization and backtest execution. ADR-010 records the alternatives and
selected ownership boundary.

B1a non-goals:

- do not implement fees, double-entry accounting, collateral, settlement processing, or PnL;
- do not add calibrated fills, queue priority, paper trading, gateways, or live order behavior;
- do not broaden Phase 3 matching or replace fixed integer core types in this first package;
- do not silently infer venue terms from one captured WebSocket stream;
- do not make tests depend on live network responses;
- do not treat a source URL without retained content and hashes as reproducible provenance;
- do not mix B2 multi-market/reconnect recovery or B3 experiment reporting into B1a; and
- do not reopen closed Track A work unless new evidence shows a higher-impact defect.

B1a evidence:

- ADR-010 selects a separate reviewed immutable product package after comparing extension and
  configuration-owned alternatives.
- `pmm.venue_product_terms.v1` and companion source, review, catalog, conversion, and compatibility
  schemas retain exact local first-party evidence and canonical hashes.
- runtime validation mechanically compares market-specific reviewed fields with retained market,
  series, and event records and refuses stale hashes, unsafe paths, extra bytes, identity/time
  mismatch, incompatible grids/units/policies, and tampered lineage;
- normalization/feature V2 and backtest/result V3 propagate the complete exact lineage while V1/V2
  compatibility artifacts retain their old meaning; and
- focused validation passes 10 product-term tests, the full Python suite passes 69 tests, and all
  78 CTest tests pass. The implementation commit is `6dc3000`.

The post-implementation review is recorded in
[[07 Engineering Notes/Authoritative Product Terms Critique]]. Its highest-impact findings are
effective-interval consistency, redirect/fetch provenance hardening, schema/runtime parity,
reviewer governance, linked-document evidence, and deeper end-to-end negative tests. The
plain-language system walkthrough is
[[07 Engineering Notes/Authoritative Product Terms Explained]].

Boundary: the first reviewed package is explicitly retrospective. It retains the official linked
contract-document identities but not the linked PDF bytes, and it covers one market. Fee and
settlement identities are retained but neither behavior is applied.

#### B1b. Contemporaneous source acquisition and second-market evidence — complete

Close the remaining high-value provenance and generality gaps before treating B1 as complete. The
post-B1a critique makes the dependency order explicit: harden the integrity/acquisition contract
before using it to approve a second product.

##### B1b-1. Product-term integrity and acquisition hardening — complete

Completion evidence:

- commit `dbd6fd8` enforces exact half-open terms/review/catalog interval equality and makes
  catalog lookup select by its verified interval;
- the same commit adds acquisition-spec V1 and source-manifest V2, validates every requested,
  redirect, and final first-party HTTPS URL, and records observed timing, redirects, status,
  selected headers, media, byte count, incremental hash, and tool version;
- acquisition streams in 64 KiB chunks with 2 MiB JSON, 4 MiB text, 32 MiB PDF, 64 MiB package,
  five-hop redirect, connect/read, per-source, and package limits;
- role/media/content validation and temporary-file/directory cleanup precede atomic final
  publication; deterministic runtime and tests remain offline;
- V1 reviewed source manifests remain valid and unchanged, while new acquisition requires V2;
- handwritten schemas now specify all schema-addressable nested V1/V2 rules, with runtime-only
  cross-file/hash/arithmetic rules documented explicitly;
- product and Phase 7 CLIs expose a documented stable refusal-code and stream/exit policy;
- V3 verification additionally checks normalized product identity, copied terms/policy files,
  feature/product binding, embedded result metadata, and result artifacts;
- commit `6d489e3` adds interval, catalog adjacency/gap/overlap, redirect, size, media, timeout,
  interruption, cleanup, recomputed-source-hash, schema parity, public CLI, V3 mutation, and exact
  nonrepresentable-output tests;
- commits `e33885a` and `5d40d64` record the current category-by-category critique, impact ratings,
  ranked follow-up, and a detailed plain-language explanation of the temporal, acquisition,
  provenance, schema, refusal, lineage, compatibility, and testing design; and
- validation passes 18 focused product-term tests, 77 total Python tests, and all 78 CTest tests.

Boundary preserved: no second reviewed market, linked-document corpus, content-addressed storage,
fees, accounting, settlement, execution calibration, reconnect/multi-market replay, ML, or
paper/live behavior was added. The reviewed B1a bytes, hashes, risk behavior, and conformance
corpora remain unchanged.

##### B1b-2. Contemporaneous linked-document and second-product evidence — complete

Completion evidence:

- ADR-011 freezes the acquisition-policy identity and selects paired complete observations,
  field-level evidence anchors, and repository-declared review responsibility without signatures;
- the climate-family `KXHMONTH-26JUL` package retains opening and closing observations of all eight
  required market, event, series, representation, fee, settlement, contract, and certification
  sources; all source bytes were identical at both observations;
- its exact half-open interval is `[2026-07-17T15:07:16.002543Z,
  2026-07-17T15:08:37.512205Z)`, bounded by opening completion and closing start;
- acquisition-spec V2 and source-manifest V3 bind an immutable checked-in policy; evidence-map V1
  resolves JSON pointers, checks Markdown text occurrence, and retains hash-bound PDF page/section
  addresses for human review;
- review V2 records repository-declared reviewer responsibility, accepted checklist items, exact
  hashes, and the exact bracket without implying signatures or organizational controls;
- product-terms V2 preserves the official empty secondary-rules value honestly while leaving V1
  semantics unchanged; catalog V1 and downstream V2/V3 formats remain additive;
- focused offline tests cover the paired observation, recomputed-hash anchor mutation, two-market
  selection, normalization, and feature lineage; and
- the retrospective B1a package and its existing artifacts remain unchanged.

Boundary preserved: this package does not charge fees, process settlement, calculate accounting or
PnL, add calibrated fills, broaden replay/reconnect behavior, change core numeric types, or make
paper/live/readiness/profitability claims. The bracket proves two complete endpoint observations,
not continuous source immutability between them.

### B1c. Document-anchor truth and generic source completeness — complete

Completion evidence:

- ADR-012 freezes acquisition-policy V1, acquisition-spec V1/V2, source-manifest V1/V2/V3,
  evidence-map V1, and review V1/V2, then introduces evidence-profile V1, acquisition-spec V3,
  source-manifest V4, evidence-map V2, and review V3 for stronger future claims;
- evidence-profile V1 classifies all eight semantic roles as required, optional, or explicitly
  not applicable, fixes per-observation cardinality/media/content/mutability/link rules, and
  classifies every product-term leaf by its evidence-coverage class;
- evidence-map V2 verifies exact Markdown heading paths and bounded contents, plus one-based PDF
  page bounds and exact section markers, under normalized SHA-256 fingerprints;
- PDF extraction is pinned to nixpkgs revision
  `59682e0069f0ed0a452e2179a7f4c1f247027b9e` and Poppler `26.06.0`; malformed, encrypted,
  scanned/image-only, textless, ambiguous, or out-of-range evidence refuses without OCR fallback;
- source-manifest V4 enforces complete endpoint membership, static-document equality, optional
  symmetry, linked-source co-presence, full retained paths, and collision-safe assembly;
- `EvidenceProfileMismatch` is the only additive public refusal code; existing codes and CLI
  success/refusal/programming-failure stream contracts retain their meanings;
- commits `f826fae` and `8262c2c` implement the successor runtime/schemas, Nix lock, synthetic
  fixtures, and one-defect offline compatibility/anchor/completeness tests; and
- validation passes 78 CTest tests, 100 Python tests, 41 focused product-term tests, 17 focused
  checkpoint-reader tests, and 17 focused fixture-integrity tests.

The accepted HMONTH and WNBA packages, catalog, and downstream artifacts remain byte-identical and
retain their original narrower meanings. HMONTH evidence-map V1 PDF locators remain human-review
addresses; neither package is silently upgraded. B1c adds no OCR, continuous-source-history proof,
fees, settlement, accounting, execution calibration, reconnect recovery, or multi-market replay.

### B2. Broader observed-market coverage and recovery — current track

The current single-observed-market replay foundation must expand to evidence that the pipeline
generalizes:

- multiple contracts and markets;
- simultaneous source scopes;
- reconnect snapshots;
- sequence gaps and explicit recovery;
- conflicting duplicates;
- late and out-of-order records;
- longer captures;
- source-schema migration fixtures; and
- cross-market deterministic ordering.

Acceptance gate:

- every gap is either recovered with explicit evidence or propagated as incomplete data;
- a reconnect cannot silently erase provenance;
- multi-market ordering is deterministic; and
- a full-capture regression fixture pins known counts and hashes.

#### B2a. Multi-scope capture and reconnect-aware normalization — complete

B2a establishes the raw-capture and normalization truth boundary without widening feature or
backtest consumers:

- capture V2 accepts a sorted multi-ticker set, emits deterministic subscription requests, binds
  acknowledgements to requests/channels/SIDs, and assigns explicit ingress, connection, request,
  and reconnect-segment identities;
- sequence-domain scope remains explicitly `unknown` unless evidence proves a narrower or shared
  domain; the implementation never infers global continuity from equal sequence values;
- normalization V3 emits one ordered record stream containing market events, discontinuities, and
  segment boundaries, plus source-scope map V1, product-map V3, and manifest V3 lineage;
- receive order is authoritative across incomparable scopes, logical time is monotonic, and late
  source events are labelled without reordering;
- disconnects and gaps invalidate book state; a required recovery snapshot may start a new valid
  segment but cannot heal or erase the preceding discontinuity;
- strict mode refuses gaps, missing or duplicate recovery snapshots, pre-recovery deltas, identity
  conflicts, conflicting duplicates, and acknowledgement mismatches; record mode may publish only
  an explicitly discontinuous or incomplete result;
- legacy capture, normalization V1/V2, product-map V1/V2, feature V1/V2, configuration V1/V2/V3,
  and result artifacts retain their original bytes and meanings; existing feature generation
  refuses V3 with `DownstreamContinuityRequired`; and
- all new acceptance evidence is offline: injected clocks, fake transports, minimal synthetic JSONL,
  schema/runtime parity checks, byte-identical repetition, cleanup checks, and legacy compatibility.

Commits `520d0a0`, `399e500`, `48f2a25`, and `a04b0c1` implement the bounded package. ADR-013 is the
architectural authority. B2a does not prove continuous venue history, multi-market features or
backtesting, long-capture stability, queue position, hidden liquidity, fills, fees, accounting,
settlement, profitability, or venue equivalence.

The B2a post-implementation review found two impact-5 and five impact-4 successor defects. B2a-1
closed those blockers before B2b: shared/unknown gap propagation, missing identity, required
sequence evidence, schema/runtime parity, acknowledgement re-validation, capture CLI status, and
disconnect-before-initial-snapshot semantics. See
[[07 Engineering Notes/Phase 7 Multi-Scope Capture Critique]] for the chronological audit and its
closure appendix.

#### B2a-1. Multi-scope truth-boundary hardening — complete

B2a-1 remained smaller than projection or backtesting and delivered:

- conservative affected-market propagation for a gap in an unknown/shared sequence scope;
- fail-closed refusal when a requested market never establishes stable identity;
- which message types require source sequence evidence;
- exact request/channel/SID acknowledgement cardinality and identity validation;
- disconnect-before-initial-snapshot completeness semantics;
- one-defect schema/runtime parity for every successor format; and
- capture exit/status wording that separates operational completion from data usability.

Implementation used only offline synthetic fixtures and preserved every accepted legacy byte and
meaning. It did not add projection, features, backtesting, a live capture, multi-connection
operation, or performance redesign.

B2a-1 completion evidence:

- commits `b68f42b` and `981f744` implement the corrected runtime/schema boundary and its offline
  one-defect acceptance matrix;

- a sequence gap in an unknown/shared scope invalidates or marks incomplete every market that the
  missing event could have affected, without pretending the missing ticker is known;
- every published product-map V3 artifact satisfies its schema when identity is complete, while a
  requested market with no stable market ID follows one explicit refusal or incomplete-identity
  contract shared by runtime and schema;
- required source-sequence evidence is defined per message type and missing evidence has a named,
  deterministic outcome;
- normalization proves exactly one acknowledgement for each expected channel and validates both
  logical and wire request identities, SID uniqueness, and declared membership;
- disconnects before connect, acknowledgement, first snapshot, and after only a subset of market
  snapshots have explicit completeness semantics;
- every successor schema has generated positive coverage and one-defect runtime/schema negative
  parity, including record-mode incomplete outputs;
- `capture-v2` exit status, shutdown status, continuity status, stdout, stderr, retained partial
  evidence, and cleanup behavior are unambiguous and tested;
- repeated offline normalization remains byte-identical and accepted legacy artifacts remain
  byte-identical with their original meanings;
- the full validation baseline is rerun without making deterministic tests network-dependent; and
- ADR-013, the operator guide, explanation, critique, README surfaces, and this roadmap are updated
  to distinguish closed B2a-1 findings from deferred B2b/B2c debt.

The seven reviewed findings B2A-01 through B2A-06 and B2A-08 are closed. The post-review findings
intentionally deferred beyond B2a-1 remain tracked: a V2 inspector and
format/refusal reference, metadata/directory durability, binary-frame retention, path-independent
manifest identity, bounded duplicate memory, deterministic subscription batching, and retained
long-capture evidence. They should not be pulled into B2a-1 unless a concrete correctness
dependency is demonstrated.

#### B2b. Multi-market projection, features, and replay — current; B2b-1 complete

B2b is split into two bounded packages so projection truth is fixed before replay and backtest
orchestration depend on it. Both packages must consume B2a-1 records without merging incomparable
sequence domains, hiding discontinuities, or treating a recovery snapshot as proof of a missing
interval. Accepted single-product feature, configuration, and result artifacts remain frozen.

##### B2b-1. Segment-aware multi-market projection and feature artifacts — complete

Goal: define and implement one deterministic projection cursor per product and valid book segment,
then materialize additive multi-market feature successors without widening replay or backtesting.

The design gate must resolve:

- how normalized V3 market events, discontinuities, affected-market sets, and segment boundaries
  advance or invalidate each product cursor;
- whether only `complete_observed_interval` input is feature-eligible initially, or whether an
  explicitly incomplete/discontinuous feature artifact is representable without becoming
  backtest-eligible;
- exact cursor watermarks, snapshot seeding, delta application, trade association, source-scope
  identity, global ingress ordering, and per-product causal visibility;
- the feature-row and feature-manifest successor schemas, including product identity, segment ID,
  `as_of_time`, raw/normalization watermark, truth category, fidelity, completeness, limitations,
  product lineage, and artifact hashes;
- whether cross-market features are intentionally absent from B2b-1 or require an explicit
  causality contract rather than an implicit latest-value join;
- public CLI success/refusal/cleanup/output-exists behavior and byte-identical repetition; and
- exact offline positive, one-defect negative, schema/runtime parity, legacy compatibility, and
  product-lineage tests.

Recommended smallest policy: B2b-1 should first support per-market features from a complete
normalization V3 interval, preserve the capture-global ingress watermark, and refuse
discontinuous/incomplete V3 inputs. Segment/discontinuity-aware representation should still be
designed now so B2b-2 cannot mistake a later snapshot for recovered continuity. Cross-market
joined features should remain outside B2b-1 unless the design proves exact visibility and missing-
market semantics.

B2b-1 is complete only when:

- every requested product owns independent book state, segment identity, and cursor watermark;
- snapshots seed only their named product/segment and deltas cannot cross product or segment
  boundaries;
- trades update only their named product and never manufacture book continuity;
- discontinuity and affected-market evidence is impossible for the feature path to ignore;
- feature rows are deterministic in normalized ingress order and carry exact causal watermarks;
- every new schema has generated-positive and one-defect-negative runtime parity;
- repeated offline materialization is byte-identical;
- accepted feature V1/V2, configuration V1/V2/V3, result V1/V2/V3, product packages, conversion
  policies, and refusal meanings retain their original bytes and meanings;
- current V3 replay/backtest refusal remains in place; and
- ADR-007/ADR-013, the Phase 7 guide/explanation/critique, README surfaces, and this roadmap are
  updated after validation and review.

B2b-1 must not implement replay or backtesting, strategy scheduling, cross-market strategies,
execution calibration, fills, accounting, fees, PnL, collateral, settlement, B2c retained capture,
B3 reporting, ML, paper trading, gateways, or live orders. It must not change matching, risk,
checkpoint, core integer types, accepted product packages, or exact-conversion refusal.

B2b-1 completion evidence:

- commit `edf3b44` adds one product-owned cursor per ticker, segment-bound snapshot/delta/trade
  application, distinct raw/normalization/product-local watermarks, additive feature row V2 and
  feature manifest V3 schemas, exact upstream hashes and lineage, and the `features-v3` command;
- commit `dd3dc74` adds deterministic offline multi-product isolation, segment invalidity,
  complete-input refusal, byte-identical repetition, schema/runtime parity, CLI status/cleanup,
  output-exists, legacy-refusal, and reviewed-lineage tests;
- only `complete_observed_interval` normalization V3 is feature-eligible; discontinuous and
  incomplete input refuses before publication;
- segment identifiers are revalidated through boundary/snapshot adjacency and product identity;
  deltas cannot cross products or segments, and invalid-period trades cannot create continuity;
- every output row belongs to one product and contains stable capture identity, segment identity,
  logical time, global and product-local causal positions, fidelity/truth, completeness,
  limitations, hashes, and optional reviewed lineage;
- repeated offline materialization is byte-identical and partial derived output is removed on
  expected failure, programming failure, and interruption;
- accepted feature V1/V2, configuration V1/V2/V3, result V1/V2/V3, product packages, conversion
  policies, and refusal meanings retain their existing bytes and interpretation; and
- replay/backtest still refuses normalization V3 and the successor features pending B2b-2.

The post-implementation critique intentionally leaves B2b-2 replay/backtest integration,
discontinuous feature publication, cross-market joins, module extraction, durable feature
checkpoints, and measured performance outside this package.

##### B2b-2. Multi-market replay and backtest integration — complete

Goal: consume the approved B2b-1 projection/feature successors through additive configuration and
result formats with explicit per-product/per-segment causality, latency, compatibility, and
incomplete-interval refusal. Its first turn must also be a read-only design gate. It must not be
folded into B2b-1 merely because the legacy single-market orchestration already exists.

What B2b-2 inherits as complete:

- normalization V3 supplies one deterministic ingress-ordered stream, explicit source scopes,
  product-map V3, discontinuities, affected-market sets, and snapshot-seeded book segments;
- feature row V2 belongs to exactly one product and segment and carries logical time, capture-global
  raw ingress, normalization ordinal, product-local applied position, snapshot seed, valid-from
  position, truth/fidelity, completeness, limitations, hashes, and reviewed lineage;
- feature manifest V3 binds exact normalization, records, scope-map, product-map, capture, product,
  feature-definition, ordering, and output identity;
- `features-v3` publishes only from `complete_observed_interval`; discontinuous and incomplete
  normalization V3 remains ineligible;
- existing replay/backtest accepts only the frozen single-product normalized/feature/configuration
  chain and intentionally refuses the B2b-1 successors; and
- accepted normalization V1/V2, feature row V1, feature manifest V1/V2, configuration V1/V2/V3,
  result V1/V2/V3, product packages, conversion policies, and refusal meanings are compatibility
  surfaces, not migration targets.

The B2b-2 design gate must resolve:

- the smallest additive multi-product backtest configuration and result-manifest successors;
- whether B2b-2 initially runs one declared per-market strategy instance per product, a portfolio
  coordinator with no cross-market signals, or a still smaller replay-only orchestration boundary;
- exact scheduling across interleaved product rows, including equal logical times, raw-ingress and
  normalization-order ties, per-product feature availability, and deterministic decision order;
- how market-data, decision, order, acknowledgement, and fill latency is expressed per product
  without creating cross-product time travel;
- whether orders, cancellations, model-derived fills, inventory, risk admission, and result rows
  require additive product and segment identity, and how those identities propagate end to end;
- account-risk ownership across multiple contracts without changing `AccountRiskProjection`, its
  checkpoint formats, rejection enums/ordinals, or first-failure ordering;
- behavior at segment starts and any impossible discontinuity evidence, including refusal rather
  than treating a later snapshot as recovered history;
- exact product-lineage, conversion-policy, feature-definition, configuration, risk-trace, and
  result-artifact hashes for every product;
- public CLI success, expected refusal, programming failure, interruption, cleanup, output-exists,
  and repeated-invocation behavior; and
- an offline one-defect acceptance matrix plus frozen legacy compatibility evidence.

Recommended smallest policy: keep B2b-2 per-market and configuration-explicit. Reuse the current
baseline strategy and execution assumptions independently per product only if deterministic
scheduling, product/segment identity, and account-risk ownership are proven. Do not add cross-
market signals or implicit latest-value joins. Accept only complete normalization V3 plus matching
feature row V2/manifest V3, and fail closed on every hash, lineage, product, segment, watermark, or
completeness mismatch.

B2b-2 is complete only when:

- additive configuration and result successors represent every product and retain exact upstream
  normalization/feature/product/policy identity;
- replay consumes feature rows in one documented deterministic order without merging product or
  segment state;
- strategy decisions and model-derived execution artifacts name their exact product, contract,
  segment, and causal feature watermark;
- latency never exposes a feature, trade, order, acknowledgement, or fill before its declared
  product-local and global availability;
- discontinuous/incomplete input and every cross-artifact mismatch refuse before final publication;
- risk behavior remains canonical and product-aware without changing the accepted risk contract;
- repeated offline runs are byte-identical and cleanup/status behavior is exact;
- generated-positive and one-defect-negative schema/runtime parity covers every new discriminator;
- all accepted legacy artifacts, examples, commands, and refusal codes retain their bytes and
  meanings; and
- ADRs, guides, explanation, critique, README surfaces, and this roadmap are updated after complete
  focused and full validation.

B2b-2 must not implement cross-market strategies or joined features, new fill calibration, queue
position, hidden liquidity, fees, accounting, PnL, collateral, margin, settlement, B2c retained
capture, B3 experiment reporting, Phase 8 ML, paper trading, authenticated gateways, live orders,
multiple concurrent WebSocket connections, performance redesign, matching changes, core
`Price`/`Quantity` replacement, `AccountRiskProjection` semantic changes, checkpoint rejection
changes, weakened exact-conversion refusal, or rewrites of accepted product packages/artifacts.

The B2b-1 closure baseline before this package was `fce665f`: `main` was clean and four commits
ahead of `origin/main`, with 78 CTests and 136 Python tests passing. The B2b-2 closure evidence
below supersedes that historical snapshot.

B2b-2 implementation evidence:

- `pmm.backtest.v4` and Result V4 are additive schemas with a separate `backtest-v4` and
  `verify-backtest-v4` command;
- one global coordinator preserves causal interleaving while each product owns independent
  strategy, segment, pending/live order, latency, and execution state;
- one unchanged canonical C++ projection is launched per declared contract, with explicit stable
  bindings and separate contract-bound V2 traces;
- typed decisions, submissions, cancellations, acknowledgements, rejections, fills, exposure,
  risk events, and summaries carry product, contract, segment, causal watermark, truth/fidelity,
  configuration, and feature-definition identity;
- only complete normalization V3 plus matching feature row V2/manifest V3 is eligible; input,
  lineage, ordering, segment, watermark, result-hash, count, cleanup, and repetition defects fail
  closed;
- focused B2b-2 validation passes 9 tests, frozen Phase 7 validation passes 42 tests, the 13
  capture + 42 product-term + 17 checkpoint-reader + 17 fixture-integrity tests pass, formatting
  passes, all 145 Python tests pass, and all 78 CTests pass; and
- the 17 accidentally deleted retained-package files were restored byte-for-byte from `HEAD`, not
  regenerated or reacquired. Catalog verification returns the accepted two-entry catalog hash,
  and the frozen HMONTH and WNBA package-tree tests pass.

B2b-2 therefore satisfies its closure rule. See
[[07 Engineering Notes/Phase 7 Multi-Market Replay and Backtesting]], the explanation, and the
severity-ranked critique.

#### B2c. Retained full-capture regression evidence — tooling implemented; hardening and evidence pending

Goal: design and, only after approval, retain reviewed longer-duration multi-market Capture V2
evidence, then exercise the accepted normalization V3, feature V2/manifest V3, and Backtest V4
chain as far as the observed completeness permits. Pin raw and derived hashes, counts, lineage,
resource measurements, and repeated offline results without turning deterministic tests into
network-dependent tests.

The read-only design gate approved a fixed twelve-hour, three-market, single-connection attempt with
one attempt after the first raw record, a 1 GiB raw budget, a 5 GiB total budget, and a 10 GiB free-
space preflight. It also split contemporaneous product acquisition/review into B2c-P. No retained
product bytes or venue capture were acquired while implementing the tooling.

Implemented B2c tooling includes:

- immutable `pmm.phase7.b2c_evidence_policy.v1`, including selection, stopping, anti-bias, outcome,
  retention, and Git-size rules;
- additive evidence-index, measurement, normalization-telemetry, and risk-telemetry schemas without
  changing accepted Capture V2, normalization V3, feature V3, Backtest V4, or Result V4 schemas;
- an offline index/full-package verifier for exact membership, safe paths, hashes, parsed counts,
  reviewed interval coverage, lineage, repetition claims, typed V4 artifacts, traces, and credential
  exclusion;
- a fresh-process measurement harness for wall time, process-tree RSS/count, disk growth, machine
  context, scrubbed stream hashes, identities, and output-budget interruption;
- opt-in duplicate-table and per-contract oracle telemetry that does not change canonical artifact
  bytes;
- characterization of Capture V2 output-exists, interruption, failure, retention, and cleanup; and
- an operator guide, plain-language explanation, and severity-ranked tooling critique.

This implementation does not close the retained-evidence acceptance gate. B2A-10/11 and B2B2-05/06
remain open or measurement-pending until reviewed artifacts and actual measurements exist.

Commits `842db83`, `d19ac3b`, and `38fb667` address an initial process-supervision, bounded-stream,
sampler-validity, successor-schema, and verifier-helper slice. The full mounted repetition/lineage,
schema-parity, stage membership, and scanner acceptance matrix remains open. The documented live
command is therefore still not operator-ready, and B2c-H remains current before B2c-P acquisition
or capture approval.

The B2c-H design is documented in
[[07 Engineering Notes/Phase 7 B2c-H Hardening Design]], its plain-language explanation, and its
severity-ranked design critique. The design selects one bounded process supervisor, additive V2
control-plane documents, independent repetition and lineage reconstruction, exact stage/outcome
membership, explicit sampler validity, complete storage accounting, and a retained deterministic
credential-scan result. The user approved this bounded design for implementation handoff on
2026-07-20. The initial V2 slice is current behavior; no finding is closed merely by approval, and
the full named matrix remains required before B2c-H can close.

Post-slice validation passes 22 focused B2c evidence/measurement tests, 144 focused compatibility
tests, formatting, all 171 Python tests, and all 78 CTests. Every added test is offline and bounded.

What B2c inherits as complete:

- Capture V2 uses one deterministic multi-ticker request on one WebSocket, explicit request/channel/
  SID scope identity, global ingress order, reconnect segments, strict usability status, and
  immutable retained raw evidence;
- normalization V3 conservatively propagates unknown/shared scope gaps, preserves discontinuity
  and segment starts in-band, and never treats a later snapshot as recovered history;
- features V3 and backtest V4 accept only `complete_observed_interval` inputs and preserve exact
  product, contract, segment, watermark, lineage, configuration, result, and risk-trace identity;
- B2a-1 closes the correctness blockers required for downstream consumption, while B2A-07 and
  B2A-10 through B2A-22 remain explicitly classified debt;
- B2b-2 closes deterministic multi-product replay/backtest integration but has no checked-in
  retained V4 run and launches one synchronous canonical risk process per contract; and
- the existing ignored three-hour WNBA capture is single-market V1 evidence, not a checked-in B2c
  multi-market Capture V2 regression package.

The original B2c design gate resolved:

- the exact evidence claim, duration, market count, market-selection rule, stopping rule, disk
  budget, and success/refusal criteria for a longer Capture V2 run;
- whether new contemporaneous reviewed product packages are prerequisites for the selected
  capture interval, and whether that acquisition/review must be a separately approved prerequisite
  package rather than being silently folded into capture;
- the immutable retention layout and ownership for raw frames, metadata, capture configuration,
  product packages, normalized V3, features V3, Backtest V4 configuration/results, measurement
  reports, compact checked-in manifests, and any deliberately external large bytes;
- how a complete observed interval, a natural reconnect/discontinuity, an incomplete prefix,
  interruption, and operational refusal are retained and reported without recapturing until a
  preferred outcome or relabelling a later snapshot as continuity;
- which recovery evidence must remain synthetic because a real reconnect cannot be demanded or
  injected into an Observed capture, and how synthetic and observed artifacts stay separate;
- exact pinned counts and SHA-256 identities for records, scopes, products, segments,
  discontinuities, features, typed backtest outputs, risk traces, and manifests;
- reproducible measurement of wall time, peak memory, disk growth, duplicate-tracking growth,
  normalization/features/backtest throughput, and per-contract oracle overhead, including machine
  and toolchain context and byte-identical repeated offline runs;
- what small deterministic fixture or manifest is appropriate for version control, given that
  `data/` and `results/` are ignored by default and large captures must not be committed casually;
- offline one-defect tests for stale hashes/counts/lineage, truncation, missing members,
  discontinuity refusal, repeated invocation, output existence, interruption, cleanup, and frozen
  legacy compatibility; and
- documentation, critique, validation, and commit boundaries required to close B2c credibly.

Recommended smallest policy: B2c should be an evidence and measurement package, not a capture or
streaming redesign. Use the existing single-connection Capture V2 and strict complete-input
consumer chain. Retain any natural discontinuity honestly; do not require or manufacture a venue
reconnect. If current reviewed product terms do not cover the chosen markets and interval, stop and
split out an explicitly approved contemporaneous product-evidence prerequisite before capture.

B2c is complete only when:

- the approved capture/evidence specification identifies the exact markets, interval, product-term
  coverage, storage destination, retention policy, machine context, and expected claims;
- retained raw bytes and metadata are immutable, hash-pinned, credential-free, and reviewable;
- every observed completeness or discontinuity outcome remains truthful and downstream strict
  consumers either run or refuse exactly as specified;
- eligible input produces normalization V3, features V3, and Backtest V4 artifacts with complete
  lineage and byte-identical repeated offline results;
- pinned counts and hashes detect truncation, mutation, missing members, and stale derived output;
- measurements answer B2A-10/11 and inform B2B2-05 without using performance results to justify an
  unapproved redesign;
- deterministic CI remains offline and uses only bounded retained fixtures, manifests, or injected
  state approved for version control;
- all accepted capture, normalization, feature, configuration, result, product, conversion, risk,
  refusal-code, and conformance artifacts retain their original bytes and meanings; and
- the guide, explanation, severity-ranked critique, README surfaces, and this roadmap distinguish
  closed B2c evidence from deferred operational, calibration, accounting, and performance work.

B2c must not add multiple concurrent WebSocket connections, infer undocumented venue sequence
scope, manufacture a reconnect, weaken completeness refusal, add cross-market signals, change fill
calibration, add fees/PnL/accounting/settlement, change risk or checkpoint semantics, redesign
streaming for aesthetics, add live orders or authenticated gateways, or make deterministic tests
network-dependent.

### B3. Experiment compatibility and reporting — planned

Build a research-control layer that can:

- run declared parameter grids;
- compare only compatible manifests;
- reject mismatched product, execution, risk, latency, or accounting contracts;
- preserve seeds and input hashes;
- produce compact experiment reports;
- retain baseline and no-fill controls; and
- report sensitivity instead of only a headline result.

Acceptance gate:

- two compatible runs can be compared reproducibly;
- incompatible runs fail with a specific reason;
- reports distinguish system metrics from economic claims; and
- identical inputs and implementation produce byte-identical artifacts.

### B4. Execution-model sensitivity and calibration — partly blocked

Before calibration, add declared sensitivity experiments across:

- acknowledgement latency;
- cancellation latency;
- fill probability;
- queue assumptions;
- partial-fill behavior;
- quote lifetime; and
- risk limits.

Credible calibration requires timestamped own-order evidence:

```text
submission -> acknowledgement -> market evolution -> fill/cancel outcome
```

Required external evidence:

- own submissions and client-order identifiers;
- venue acknowledgements and rejections;
- partial/full fills;
- cancellations and expiries;
- fees; and
- synchronized market data.

Until that evidence exists, parameters must remain `Assumed` or sensitivity-tested and fills must
remain `ModelDerived`.

Acceptance gate for calibration:

- chronological train/validation/test partitions;
- censoring-aware treatment of cancels and expiries;
- frozen parameters evaluated on later data;
- calibration and reliability metrics; and
- explicit comparison with `no_fill_v1` and `trade_touch_v1`.

### B5. Real accounting, collateral, fees, and settlement — planned, high priority

The current ledger records unresolved modeled cash flows. A credible accounting subsystem needs:

- double-entry cash and position ledgers;
- deterministic fee calculation and rounding;
- realized and unrealized PnL policy;
- marking policy;
- binary payout and settlement processing;
- collateral and buying power;
- venue sell/short semantics;
- reconciliation invariants; and
- compatibility with product-term hashes.

Acceptance gate:

- every fill and settlement balances under declared invariants;
- fee and rounding examples match sourced venue rules;
- incompatible accounting policies cannot be compared silently;
- restart/replay reproduces identical ledger state; and
- PnL is not exposed before these conditions hold.

### B6. Durable full-run continuation — planned

Exchange-only durability is insufficient for a long research run. A complete runner checkpoint
must cover:

- observed-market cursor and watermark;
- feature state;
- scheduled decisions;
- active modeled orders;
- market-maker state;
- canonical risk state;
- accounting state;
- input and configuration hashes; and
- output progress.

Acceptance gate:

- an interrupted run resumes without reinterpreting earlier data;
- later orders, fills, risk traces, ledger entries, and manifests are byte-identical to an
  uninterrupted run; and
- incompatible code, configuration, input, or product terms fail closed.

### B7. Formal schemas and protocol evolution — planned

The local whitespace oracle is intentionally narrow and frozen. Before broader process-boundary or
portfolio use, define:

- a versioned account-event request schema;
- versioned response and error categories;
- explicit escaping and framing;
- multi-account/product identity rules;
- compatibility fixtures; and
- migration behavior.

Non-goal: do not retrofit new semantics into the frozen V1 adapter.

### B8. Phase 7 performance and scale — deferred until measured

Candidate optimizations:

- streaming feature input;
- incremental order/fill/ledger/risk-trace output;
- stable priority queue for scheduled decisions;
- incremental artifact hashing;
- batched oracle requests or a native binding;
- corpus and manifest sharding; and
- multi-market worker isolation.

Gate: profile representative larger captures first. Preserve deterministic ordering and auditability
before reducing memory or process overhead.

## Track C: Phase 8 machine learning

Phase 8 is aspirational until Phase 7 data, execution, and comparison gates are credible.

### C1. Versioned ML datasets

Required work:

- dataset builders tied to normalized source and product-term hashes;
- feature-availability timestamps;
- chronological train/validation/test splits;
- leakage checks;
- missing-data and gap policies;
- label provenance; and
- dataset manifests.

### C2. Targets and non-ML baselines

Candidate targets:

- future midpoint or fair value;
- short-horizon markout;
- adverse selection;
- volatility;
- fill probability;
- order toxicity;
- spread width; and
- quote size.

Every target requires a meaningful simple baseline, such as current midpoint, rolling imbalance,
fixed volatility, historical frequency, logistic regression, or a rule-based quoting policy.

Gate: no model advances because it beats zero or a deliberately weak comparator.

### C3. Reproducible training and evaluation

Required work:

- explicit training configurations and seeds;
- chronological cross-validation;
- calibration metrics;
- cost-sensitive evaluation;
- regime and market breakdowns;
- hyperparameter records;
- model and feature compatibility hashes;
- deterministic inference fixtures; and
- drift and stability reports.

Gate: a model must improve a declared baseline on held-out data without leakage and with uncertainty
reported.

### C4. Model registry and lifecycle

Required work:

- immutable model artifacts;
- training-data and feature-schema lineage;
- approval state;
- rollback target;
- inference compatibility checks; and
- deprecation/migration rules.

## Track D: Phase 9 ML market maker

This phase integrates approved models without giving them ownership of exchange or risk state.

Planned capabilities:

- learned fair-value adjustment;
- dynamic spread width;
- inventory-aware learned skew;
- adaptive quote size;
- volatility-aware quoting;
- adverse-selection avoidance;
- confidence-aware fallback to the deterministic baseline;
- inference timeout and invalid-output handling; and
- shadow comparison against the baseline maker.

Architecture gate:

- models recommend quote parameters;
- the strategy remains deterministic for fixed inputs/model artifacts;
- external risk admission remains authoritative;
- the model cannot call the order book or gateway directly; and
- invalid or unavailable inference falls back safely.

Research gate: promotion requires held-out improvement under compatible execution and accounting
assumptions, not only better model loss.

## Track E: Phase 10 paper trading

Paper trading requires a real-time operational system, not merely a live-data backtest.

Required work:

- public live market-data gateway;
- authenticated private-account stream where available;
- venue product metadata refresh;
- real-time feature computation;
- wall-clock strategy scheduling;
- paper-order gateway;
- acknowledgement, rejection, cancellation, and fill reconciliation;
- connection-loss and reconnect handling;
- rate limits and backoff;
- clock synchronization;
- persistent audit records;
- full-process checkpoint/restart;
- monitoring and alerts;
- operator kill switch; and
- daily risk and accounting reports.

Gate: paper fills must remain explicitly labelled as paper-environment behavior. They are not live
execution evidence.

## Track F: Phase 11 demo exchange integration

Required work:

- credential and secret management;
- request signing;
- idempotent client-order identifiers;
- REST/WebSocket state reconciliation;
- retry classification;
- duplicate-request protection;
- unknown-order-state handling;
- cancel-all and emergency shutdown;
- venue rate-limit enforcement;
- startup account reconciliation;
- continuous local-versus-venue comparison; and
- retained demo execution evidence.

Gate: the system must fail closed on ambiguous remote order state and must never infer successful
cancellation or rejection without venue evidence.

## Track G: Phase 12 limited live deployment

This phase remains aspirational and requires explicit human authorization beyond repository
implementation.

Required work includes:

- small explicit capital and position limits;
- independent hard risk caps;
- verified collateral and settlement;
- cash and position reconciliation;
- operational dashboards and paging;
- incident response and runbooks;
- credential rotation;
- deployment rollback;
- process supervision;
- disaster recovery;
- audit retention;
- manual intervention controls;
- compliance and venue-rule review; and
- sustained paper/demo evidence.

Gate: live trading must not begin merely because the software builds or a demo environment works.

## Cross-cutting work

### Testing and compatibility

- Formal schema compatibility fixtures as formats mature.
- Multi-platform CI only for platforms the project intends to support.
- Deterministic replay and byte-identity tests at every persistence boundary.
- Property/fuzz testing for parsers after explicit matrices stabilize.
- Result-manifest compatibility validation.

### Security

- No credentials in configuration, fixtures, logs, or result artifacts.
- Scoped secret loading and rotation before authenticated gateways.
- Signed-request and replay protection.
- Audit-safe error reporting.
- Dependency and supply-chain review before deployment.

### Observability and operations

- Structured logs with stable event identity.
- Metrics for input gaps, decision latency, order state, reconciliation, and risk.
- Health checks and liveness/readiness policy.
- Alerts that distinguish data, strategy, risk, gateway, and accounting failures.
- Runbooks for kill switch, disconnect, inconsistent state, and recovery.

### Documentation and navigation

- Keep this file current after each bounded package.
- Add a compact risk current-state index when the long conformance notes next change materially.
- Keep root README navigation concise.
- Preserve historical critiques instead of rewriting them as if old gaps never existed.
- State observed, reconstructed, synthetic, and model-derived boundaries explicitly.

### Performance

- Benchmark before optimizing.
- Preserve deterministic order and correctness before concurrency.
- Do not introduce caches that weaken input/version identity.
- Treat throughput targets as workload-specific, not abstract claims.

## Dependency map

```text
Track A conformance tail (closed)
        |
        v
B1 product metadata -----> B5 accounting and settlement
        |                         |
        v                         v
B2 broader data -------> B3 comparison/reporting
        |                         |
        +-------> B4 execution sensitivity/calibration
                                  |
                                  v
                         credible Phase 7 research
                                  |
                                  v
                     C Phase 8 ML datasets/models
                                  |
                                  v
                     D Phase 9 ML market maker
                                  |
                                  v
                       E Phase 10 paper trading
                                  |
                                  v
                        F Phase 11 demo gateway
                                  |
                                  v
                     G Phase 12 limited live use
```

B6 full-run recovery, B7 protocol evolution, and measured B8 scaling can proceed alongside later
Phase 7 work when their dependencies become active, but paper/demo readiness requires them to be
closed at the appropriate operational boundary.

## Recommended execution order

| Order | Package | Why now |
| ---: | --- | --- |
| 1 | B2c-H evidence and measurement hardening | Live operation is unsafe until interrupt teardown and independent lineage/repetition verification close. |
| 2 | B2c-P product evidence and capture execution | After hardening, current product intervals and durable storage still require separate approval. |
| 3 | Experiment compatibility and report tooling | Makes later sensitivity and model results comparable. |
| 4 | Execution sensitivity grid | Produces honest bounds before calibration data exists. |
| 5 | Own-execution capture and calibrated fill research | High value but externally evidence-dependent. |
| 6 | Accounting, fees, collateral, and settlement | Required before economic or PnL claims. |
| 7 | Durable full-run continuation | Required for long and operationally reliable experiments. |
| 8 | ML datasets and non-ML baselines | Begins Phase 8 on credible research inputs. |
| 9 | Predictive models and model registry | Follows held-out baseline evidence and safe fallback design. |
| 10 | ML market-maker integration | Follows approved model evidence and safe fallback design. |
| 11 | Paper trading | Follows accounting, recovery, gateways, and monitoring. |
| 12 | Demo exchange integration | Follows stable paper operations and reconciliation. |
| 13 | Limited live deployment | Requires explicit human authorization and sustained evidence. |

This order is a default, not a prohibition on discovery work. A prototype may explore a later idea,
but it must remain labelled experimental and must not bypass its promotion gates.

## Current next package

The next bounded package is **B2c-H evidence-verifier and measurement-lifecycle hardening**. It must
guarantee bounded termination and reaping of the measured process group on operator interruption or
budget stop; independently rebuild repetition inventories and the complete mounted lineage graph;
validate every new B2c member against its runtime schema; enforce exact outcome/stage membership,
free-space and aggregate-budget rules; distinguish invalid sampling from real zero RSS; and bind a
specified credential scan to retained evidence. Each defect requires a named offline test. Do not
acquire product bytes or start a venue capture during B2c-H.

The read-only B2c-H review produced a consolidated design, and the user approved it for bounded
implementation handoff on 2026-07-20. It preserves existing artifact and refusal meanings while
fixing the process-ownership, schema, lineage, repetition, storage, sampling, credential, CLI, test,
and documentation boundaries. The explanation makes the reasoning operator-readable; the critique
rates implementation risks and deferred debt. Implementation begins test-first with the named
lifecycle and verifier failures, then follows the design's measurement, evidence/lineage,
compatibility, and documentation commit boundaries. Approval does not close any finding. Closure
still requires implemented named tests, compatibility gates, validation evidence, updated operator
docs, and a post-implementation critique.

Tests must be written first and observed failing locally within each slice, but every recorded commit
must pass its scoped gates. New V2 refusal codes must be additive and documented; accepted V1 codes,
stdout/stderr behavior, exit meanings, and first-failure ordering remain frozen.

The implementation agent should use a hub-and-spoke review with bounded sub-agents for measurement
lifecycle, evidence/schema/lineage, and compatibility/security/documentation. Graphify is the first
navigation index, but source, tests, accepted ADRs, and this roadmap remain authority. The Graphify,
test-driven-development, and systematic-debugging skills are applicable; external connectors are
not needed because B2c-H is an offline repository package.

Graphify is advisory navigation only. Version-controlled hooks now refresh code navigation after
commits and branch changes, while material documentation changes still require a manual semantic
`$graphify . --update` before final handoff. A refresh does not approve implementation or close a
roadmap gate.

After B2c-H closes, **B2c-P contemporaneous product evidence and capture execution** becomes next.
Its first turn must remain an approval packet, not an acquisition: pin one candidate-selection
timestamp, one venue activity field, three eligible distinct-series markets, the complete
opening/closing source plan, reviewer responsibility, durable storage owner/location/read/backup
policy, scheduled capture window, and operator. Do not acquire bytes or capture until that packet is
explicitly approved.

After approval, B2c-P opening evidence must complete before the one fixed capture attempt. Closing
evidence begins immediately afterward. The strict chain runs only if every reviewed effective
interval covers the exact capture; otherwise retain the raw outcome honestly and stop at its eligible
boundary. Do not promote B3 until the applicable B2c evidence gates actually close.

B2a establishes explicit multi-scope capture and reconnect-aware normalization successors. B2a-1
closes their reviewed truth-contract blockers. B2b-1 now consumes that boundary for complete-input
per-market features, but does not prove replay/backtesting, long-capture behavior, cross-market
causality, or continuous venue-global market-data completeness.

Track A is closed by `4e6336b` for A1 and `ecca209` for A2, with their documentation packages.
Deferred A3 hardening remains available only when evidence raises its impact or its containing
tests are already changing.

## Non-claims that must remain explicit

Current implementation does not establish:

- calibrated fills;
- queue position or venue-equivalent execution;
- realistic cancellation priority or hidden liquidity;
- PnL correctness;
- fee, collateral, margin, or settlement correctness;
- durable full-run research recovery;
- portfolio or multi-account recovery;
- paper-trading readiness;
- authenticated gateway readiness;
- live-trading readiness; or
- profitability.

Do not remove these non-claims because a new test, fixture, model, or adapter lands. Remove or narrow
one only when its own acceptance gate has been implemented, validated, documented, and reviewed.

## Update protocol for future agents

Every bounded milestone that changes project status must update this file in its documentation
commit.

### Required update steps

1. Read `AGENTS.md`, the charter, applicable ADRs, this document, and the active implementation
   notes.
2. Verify current git status, branch relationship, tests, and relevant artifact counts.
3. Change the snapshot date and baseline commit only after the milestone commits exist.
4. Move the completed item from `Next` or `Planned` to `Complete`; do not delete its boundary.
5. Promote exactly one bounded item to `Next`.
6. Rerank work if new evidence changes impact or dependencies.
7. Preserve deferred items unless they are explicitly rejected with documented reasoning.
8. Update validation counts and corpus/artifact counts from actual commands.
9. Add links to new ADRs, guides, critiques, or explanations where they materially help navigation.
10. Recheck every readiness and economic claim before committing.

### Evidence rule

Every status promotion should name evidence such as:

- commit hashes;
- passing test commands and counts;
- reviewed fixture or data counts;
- manifest or artifact identities;
- accepted ADRs; and
- explicit limitations.

Do not use planned code, a design proposal, or a passing happy-path demo as completion evidence.

### Agent handoff checklist

A handoff prompt should include:

- repository path and `AGENTS.md` requirement;
- current clean/dirty state and recent commits;
- exact next bounded package;
- minimum files to read;
- design questions that require approval;
- acceptance conditions;
- validation commands;
- non-goals and deferred follow-ups;
- expected logical commits; and
- instruction to update this document after completion.

When `graphify-out/graph.json` is available, a handoff may also recommend a focused Graphify query
for initial navigation and `$graphify . --update` after meaningful code or documentation changes.
The prompt must still require direct inspection of named source files and authoritative ADR/roadmap
documents; graph output is never completion evidence by itself.

## How to place a new idea on the roadmap

For any new idea, answer these questions before implementation:

1. Which track and phase owns it?
2. Which current boundary does it improve?
3. What evidence or dependency must exist first?
4. Is it production behavior, test-only evidence, research infrastructure, or an experiment?
5. What claim becomes newly justified if it succeeds?
6. What claims remain unjustified?
7. Can it be completed as one bounded package with explicit acceptance tests?
8. Does it displace the current `Next` item, and if so, why is its impact higher?

Ideas may be explored out of order, but promotion into the supported system must follow the
dependency and evidence gates above.
