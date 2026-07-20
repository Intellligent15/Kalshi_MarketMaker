# Phase 7: Historical replay, feature extraction, and backtesting

## Goal

Add an auditable, deterministic research pipeline for normalized historical market data without
changing Phase 3 matching semantics or treating reconstructed data as observed exchange truth.

## Foundation completed first

- Opt-in versioned/checksummed write-ahead exchange journal.
- Prepared command and committed event-batch records, with fail-closed exchange behavior.
- Atomic, checksummed exchange checkpoint persistence and recovery through ordinary matching.
- Recovery verification against persisted event payloads.

This is exchange-only durability. Agent, risk, market-maker, accounting, and gateway recovery are
still separate work.

## Planned scope

- Separate raw/external, normalized, feature, configuration, and result-artifact layouts.
- Product mapping, UTC/unit normalization, source-sequence/gap validation, and provenance
  manifests.
- Cursor-driven observed-market projections with snapshots, stable watermarks, and explicit gaps.
- Causal, versioned features and materialized feature datasets.
- Deterministic strategy scheduling, synthetic fill models, latency assumptions, event-fed
  inventory/exposure, and experiment manifests.
- Fidelity labels for market-by-order, level-2, and trade-only input.

## V1 implemented

- Immutable Kalshi raw-capture normalization with hashes, fixed-point values, identity provenance, duplicate/gap validation, UTC logical ordering, and fidelity labels.
- Cursor-ordered Level-2 projection and causal best-bid/ask, spread, depth, imbalance, midpoint, and last-trade features.
- Checkpointable in-memory observed-market cursor with stable applied-event watermarks and verified continuation.
- Versioned touch-fill and no-fill configs, logical latency, external synthetic risk limits, append-only result artifacts, hashes, assumptions, and model-truth labels.

## Product-term lineage implemented

- Reviewed, immutable product packages retain exact first-party source bytes, source hashes,
  effective-time review, canonical venue terms, and review limitations.
- Normalization V2 binds capture-derived UUID/ticker identity to source-backed series, event,
  market, contract, price-grid, quantity, payout, lifecycle, settlement, and fee identities.
- Feature V2 and backtest V3 propagate exact terms, source, review, catalog, conversion-policy,
  and upstream-manifest hashes; offline verification rejects tampered lineage.
- Venue fixed-point values are preserved exactly. The current integer core accepts only exact cents
  and whole contracts; it never rounds a nonrepresentable value.

See [[02 Architecture/ADR-010 Authoritative Product Terms and Artifact Lineage]].

## Product-term integrity and acquisition hardening implemented

- Terms, review, and catalog revisions now share one exact half-open effective interval; catalog
  gaps, adjacency, overlap, ambiguity, and capture selection have focused tests.
- Explicit acquisition streams approved first-party sources through bounded temporary files,
  validates every redirect and final URL, records observed HTTP provenance, hashes incrementally,
  validates role/media content, and removes partial output on expected failure or interruption.
- Source-manifest V2 records observed acquisition facts while source-manifest V1 remains valid for
  the existing retrospective reviewed package.
- Formal schemas and runtime validation share a positive/negative parity matrix, and public CLIs
  expose stable coded refusals with tested exit/stdout/stderr behavior.
- V3 offline verification covers upstream manifests, normalized and feature artifacts, embedded
  product metadata, result manifests, and every result artifact.

## Contemporaneous second-product evidence implemented

- A complete climate-family HMONTH package retains two observations of every required JSON,
  Markdown, and linked PDF source.
- Source-manifest V3 binds the immutable acquisition policy and both endpoints; evidence-map V1 and
  review V2 retain field anchors and repository-declared responsibility.
- Product-terms V2 preserves an official empty secondary-rules value without weakening V1.
- The two-market catalog and downstream normalization/feature V2 lineage verify entirely offline.

## Document-anchor and generic completeness hardening implemented

- ADR-012 freezes the accepted V1/V2/V3 adapters and adds a profile-bound successor chain for new
  packages: evidence-profile V1, acquisition-spec V3, source-manifest V4, evidence-map V2, and
  review V3.
- Poppler extraction is an offline, Nix-pinned dependency. PDF page/section and Markdown heading
  locators now have explicit structural, normalization, ambiguity, and SHA-256 fingerprint rules;
  scanned/image-only PDFs remain unsupported without an existing text layer.
- The immutable evidence profile owns required, optional, and explicitly not-applicable roles,
  per-endpoint cardinality, static/mutable behavior, linked-document relationships, and complete
  product-field coverage classes.
- `EvidenceProfileMismatch` is additive and limited to profile identity defects. Existing missing-
  evidence, document-anchor, source-hash, source-projection, and acquisition codes keep their prior
  meanings.
- The accepted HMONTH and WNBA packages retain their exact bytes, hashes, catalog identities, and
  meanings. HMONTH's V1 PDF locators remain human-review addresses; WNBA remains retrospective and
  does not acquire evidence it never retained.

B2 broader observed-market coverage and recovery follows this bounded hardening gate. B1c does not
make the short HMONTH bracket continuous source history or add OCR, fee/settlement processing,
accounting, execution calibration, or multi-market replay.

See [[02 Architecture/ADR-012 Deterministic Document Evidence and Completeness Profiles]].

## Multi-scope capture and reconnect-aware normalization implemented

- Raw capture V2 accepts deterministically sorted multiple tickers on one connection attempt and
  binds request, channel, venue SID, connection segment, and unknown/documented sequence scope.
- Every raw record has a capture-global ingress ordinal; normalization never creates cross-scope
  causality from timestamps.
- Normalized record V2 keeps market events, connection/sequence discontinuities, and segment starts
  in one ordered stream, with product-map V3 and source-scope-map V1 side artifacts.
- A connection gap invalidates prior book state. The post-implementation review found that a
  sequence gap on a shared/unknown scope currently under-propagates invalidation and must be fixed
  in B2a-1. A later snapshot starts a new valid observed segment but does not recover the missing
  interval.
- Normalization manifest V3 distinguishes complete observed intervals, observed discontinuity, and
  incomplete evidence. Current feature/backtest consumers refuse it pending B2b.
- Formal schemas and offline fake-transport tests cover the main scope, acknowledgement, duplicate,
  gap, recovery, ordering, cleanup, determinism, legacy compatibility, and product-lineage paths.
  B2a-1 must complete the one-defect schema/runtime matrix and missing identity/scope edges before
  projection consumes V3.

See [[02 Architecture/ADR-013 Multi-Scope Capture and Reconnect-Aware Normalization]].

## Explicitly deferred

- PnL, fees, collateral, settlement, margin, and paper-trading claims.
- Exact queue-position or execution-reality claims without an appropriate source and tested fill
  model.
- Portfolio risk, account sharing, live gateways, fanout backpressure, retention compaction,
  sharding, and machine-learning models.
- Multi-market capture truth-boundary hardening, per-market features, and deterministic
  multi-market replay/backtesting are complete within B2a-1, B2b-1, and B2b-2 respectively.
  Retained long-capture regression evidence remains B2c.

See [[02 Architecture/ADR-007 Deterministic Historical Replay and Backtesting]].

## Segment-aware multi-market features implemented

- One product-owned cursor consumes each ticker without sharing mutable book or last-trade state.
- Normalized segment boundaries are revalidated and snapshots seed only their named product and
  segment.
- Raw ingress, normalization ordinal, product-local applied watermark, snapshot seed, and valid-
  from positions remain distinct.
- Feature row V2 and feature manifest V3 bind exact product/segment identity, definitions, units,
  completeness, limitations, lineage, and artifact hashes.
- `features-v3` accepts only complete normalization V3 and cleans derived partial output on every
  failure or interruption.
- Cross-market joins remain outside B2b-1. Replay/backtest integration is complete in B2b-2.

## Multi-market replay and backtesting implemented

B2b-2 adds one global causal coordinator with independent per-product strategy and execution state,
explicit latency stages, one canonical C++ projection per contract, additive V4 configuration and
result contracts, typed product/contract/segment-aware artifacts, complete-input refusal, and
offline result verification. Cross-market signals and portfolio risk remain excluded.

Focused B2b-2, Phase 7, capture, product-term, checkpoint-reader, fixture-integrity, formatting,
full Python, and CTest gates pass. The accidental retained-package deletions were restored exactly
from Git and B2b-2 is closed. B2c retained full-capture regression evidence is the next read-only
design gate; no capture or retained acquisition should occur before that design is approved.

## B2c evidence tooling implemented; retained run pending

The approved B2c design fixes one twelve-hour, three-market, single-connection attempt and adds an
offline evidence policy/index/verifier, process-tree and disk measurement, output-budget
interruption, duplicate-table telemetry, per-contract oracle telemetry, and one-defect acceptance
coverage. These are additive control-plane formats; accepted raw, normalized, feature, backtest,
result, product, conversion, risk, and refusal contracts retain their meanings.

No B2c product evidence or venue capture has been acquired. A deeper implementation review found
that measurement-wrapper interruption does not yet guarantee child-process teardown and that
repetition/lineage claims are not all independently rebuilt from mounted bytes. B2c-H must close
those blockers, full mounted-member schema validation, outcome/stage rules, resource enforcement,
sampler validity, and credential-scan binding first. B2c-P must then separately pin and approve
the actual candidate snapshot, activity field, three distinct-series markets, opening/closing
acquisition plan, reviewer, durable storage ownership, capture window, and operator. B3 remains
blocked until applicable retained-evidence gates actually close.

The B2c-H design packet is recorded in the hardening design, explanation, and critique and was
approved for bounded implementation handoff on 2026-07-20.
That documentation fixes the intended process state machine, additive schema boundary, independent
inventory and lineage reconstruction, role matrix, scanner contract, and acceptance gates. It does
not implement or close B2c-H; implementation remains the next bounded package.
