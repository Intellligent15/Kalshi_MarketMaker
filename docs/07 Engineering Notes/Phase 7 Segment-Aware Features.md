# Phase 7 Segment-Aware Features

## Delivered B2b-1 boundary

B2b-1 adds deterministic per-market feature artifacts for complete normalization V3 input. It
stops before replay, strategy scheduling, fills, or backtesting.

```sh
uv run python python/pmm_phase7.py features-v3 \
  --input data/processed/kalshi/two-market-normalized-v3 \
  --output data/processed/kalshi/two-market-features-v3
```

Success returns zero, writes the JSON manifest to stdout, and leaves stderr empty. Expected input
refusals return two with empty stdout. Unexpected failures return one. Interruption returns 130.
The command never overwrites final output and removes only partial output that it created.

## Projection contract

- One cursor owns one product ticker.
- Mutable book and last-trade state belongs to one current book segment.
- A segment boundary and snapshot share raw ingress but have distinct normalization ordinals.
- Deltas require the current ticker, current segment, and valid book state.
- Discontinuities invalidate every conservatively affected cursor.
- Trades observed while invalid do not restore book continuity or seed a later segment.
- Source timestamps never reorder normalized ingress.

## Artifact contract

`features.jsonl` contains `pmm.historical.feature_row.v2`. Each row names one product and segment,
the triggering event, logical time, global and product-local watermarks, truth/fidelity,
completeness, limitations, exact upstream lineage, and the existing spread, top-level depth,
imbalance, midpoint, and last-trade values.

`manifest.json` contains `pmm.historical.feature_manifest.v3`. It binds the normalization manifest,
records, scope map, product map, stable capture hashes, per-product reviewed lineage, feature
definitions, row count, output hash, and deterministic ordering policy.

## Eligibility and non-goals

Only `complete_observed_interval` is accepted. Discontinuous and incomplete V3 inputs refuse before
publication. No joined cross-market feature, replay configuration, result format, fill behavior,
accounting, settlement, or risk behavior is added. Legacy `features` and replay/backtest behavior
remain unchanged.
