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

## Explicitly deferred

- PnL, fees, collateral, settlement, margin, and paper-trading claims.
- Exact queue-position or execution-reality claims without an appropriate source and tested fill
  model.
- Portfolio risk, account sharing, live gateways, fanout backpressure, retention compaction,
  sharding, and machine-learning models.

See [[02 Architecture/ADR-007 Deterministic Historical Replay and Backtesting]].
