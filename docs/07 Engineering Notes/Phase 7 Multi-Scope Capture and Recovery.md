# Phase 7 Multi-Scope Capture and Recovery

## Delivered B2a boundary

B2a adds an offline-testable capture and normalization truth boundary for multiple requested
markets and sequential reconnects. It stops before multi-market feature generation or backtesting.

The additive commands are:

```sh
uv run python python/kalshi_capture.py capture-v2 \
  --ticker MARKET-A --ticker MARKET-B \
  --duration 300 \
  --output data/raw/two-market-capture

uv run python python/pmm_phase7.py normalize-v3 \
  --input data/raw/two-market-capture \
  --output data/processed/two-market-normalized-v3
```

`normalize-v3` refuses discontinuous or incomplete input by default. For evidence inspection only:

```sh
uv run python python/pmm_phase7.py normalize-v3 \
  --input data/raw/two-market-capture \
  --output data/processed/two-market-normalized-v3-incomplete \
  --continuity-policy record
```

That output is not accepted by current feature or backtest consumers.

## Artifact layout

Raw V2 contains `metadata.json` and `frames.jsonl`. Every raw record carries an explicit ingress
ordinal and includes lifecycle, request, acknowledgement, or source-frame evidence.

Normalized V3 contains:

- `records.jsonl`: market events, discontinuities, and segment starts in ingress order;
- `source_scopes.json`: request/channel/SID/membership and sequence-domain identity;
- `product.json`: deterministic multi-product capture identity and optional reviewed lineage;
- `manifest.json`: complete hashes, counts, continuity status, and limitations;
- optional copied `product_terms/<ticker>/` packages; and
- optional copied `conversion_policy.json`.

## Operator interpretation

`complete_observed_interval` means every requested market received one required snapshot and no
recorded defect was found inside the bounded capture, subject to unknown sequence scope and Level-2
limitations. `observed_discontinuous` means valid observed segments exist around a missing interval.
`incomplete` means a required acknowledgement, snapshot, sequence, frame, or valid book segment is
missing.

A later snapshot never repairs the gap. It starts a new segment only.

## Offline validation

The acceptance corpus uses injected clocks, scripted transports, temporary captures, and the small
retained `python/tests/fixtures/phase7_b2a/scenarios.json` matrix. No test contacts Kalshi.

Focused commands:

```sh
UV_CACHE_DIR=/tmp/pmm-uv-cache uv run python -m unittest python.tests.test_kalshi_capture
UV_CACHE_DIR=/tmp/pmm-uv-cache uv run python -m unittest python.tests.test_phase7
UV_CACHE_DIR=/tmp/pmm-uv-cache uv run python -m unittest python.tests.test_product_terms
```

See [[02 Architecture/ADR-013 Multi-Scope Capture and Reconnect-Aware Normalization]] and
[[07 Engineering Notes/Phase 7 Multi-Scope Capture Explained]].
