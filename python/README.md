# Python support

This directory is reserved for data preparation, research analysis, and later ML workflows.
Keep environments, generated caches, and credentials out of version control.

## Kalshi L2 capture

`kalshi_capture.py` is a passive raw recorder. Ticker, duration, and output path are required
runtime arguments; it has no market-specific defaults. It reads `KALSHI_API_KEY_ID` and
`KALSHI_PRIVATE_KEY_PATH` only from the local environment and never writes either value to disk.
Dependencies are defined in `pyproject.toml` and managed with uv.

Verify the local environment without printing either credential:

```sh
uv run --env-file .env python python/kalshi_capture.py verify-env
```

Smoke test a market before a longer capture:

```sh
uv run --env-file .env python python/kalshi_capture.py capture \
  --ticker KXWNBASPREAD-26JUL14WSHTOR-WSH2 \
  --duration 300 \
  --output data/raw/smoke-test

uv run python python/kalshi_capture.py inspect \
  --input data/raw/smoke-test \
  --require-subscription --require-snapshot --require-delta --require-trade \
  --require-contiguous-sequences --require-clean-shutdown
```

After the smoke test validates, the passive three-hour command is:

```sh
uv run --env-file .env python python/kalshi_capture.py capture \
  --ticker KXWNBASPREAD-26JUL14WSHTOR-WSH2 \
  --duration 10800 \
  --output data/raw/wsh-tor-wsh2-3h
```

The recorder writes append-only `frames.jsonl` plus separate `metadata.json` in the specified
directory. It subscribes only to `orderbook_delta` and `trade`, requests unified YES-leg pricing,
preserves the raw WebSocket payload and local receive timestamp for every inbound frame, records
source sequence values where provided, and does not normalize data, model fills, or place orders.
`inspect` performs a best-effort observed-L2 snapshot/delta replay; it is not an execution replay.

## Phase 7 local historical pipeline

After validating a capture, normalize it once into immutable canonical events, materialize causal features, then run both the synthetic-fill experiment and its no-fill control:

```sh
uv run python python/pmm_phase7.py normalize \
  --input data/raw/wsh-tor-wsh2-3h \
  --output data/processed/kalshi/wsh-tor-wsh2-normalized-v1

uv run python python/pmm_phase7.py features \
  --input data/processed/kalshi/wsh-tor-wsh2-normalized-v1 \
  --output data/processed/kalshi/wsh-tor-wsh2-features-v1

uv run python python/pmm_phase7.py backtest \
  --config configs/phase7/kalshi_wsh_tor_v1.json \
  --output results/kalshi/wsh-tor-wsh2-v1

uv run python python/pmm_phase7.py backtest \
  --config configs/phase7/kalshi_wsh_tor_no_fill_v1.json \
  --output results/kalshi/wsh-tor-wsh2-no-fill-v1
```

The normalizer fails closed on corrupt records, conflicting duplicate source events, and sequence gaps by default. It preserves source file hashes, fixed-point decimal strings, local receive timestamps, source sequences, and source-versus-receive-time ordering basis. The Level-2 observed projection is authoritative historical input; it is never replayed through `ExchangeSimulator`.

`trade_touch_v1` allocates qualifying public-trade quantity to simulated quotes in deterministic order-ID order. It deliberately has no queue position, hidden liquidity, venue acknowledgement, fees, PnL, collateral, or settlement model. Its fills are `ModelDerived`, not observed fills or execution-realism claims. `no_fill_v1` is the execution-free control.

### Reviewed product-term pipeline

New product-bound research uses the offline catalog and exact conversion policy:

```sh
uv run python python/pmm_product_terms.py verify-catalog \
  --catalog configs/product_catalog

uv run python python/pmm_phase7.py normalize-v2 \
  --input data/raw/wsh-tor-wsh2-3h \
  --output data/processed/kalshi/wsh-tor-wsh2-normalized-v2-product-terms \
  --catalog configs/product_catalog \
  --conversion-policy configs/product_catalog/conversion_policies/integer_cents_whole_contracts_v1.json

uv run python python/pmm_phase7.py features \
  --input data/processed/kalshi/wsh-tor-wsh2-normalized-v2-product-terms \
  --output data/processed/kalshi/wsh-tor-wsh2-features-v2-product-terms

uv run python python/pmm_phase7.py backtest \
  --config configs/phase7/kalshi_wsh_tor_no_fill_product_terms_v3.json \
  --output results/kalshi/wsh-tor-wsh2-no-fill-product-terms-v3

uv run python python/pmm_phase7.py verify-lineage \
  --config configs/phase7/kalshi_wsh_tor_no_fill_product_terms_v3.json \
  --result results/kalshi/wsh-tor-wsh2-no-fill-product-terms-v3
```

`pmm_product_terms.py` also provides explicit `fetch`, `build`, `review`, `inspect`, `compare`,
`diff`, and `assess-legacy` operator commands. Only `fetch` uses the network. Deterministic runtime
and tests consume reviewed local bytes. Final artifact directories are immutable and are not
overwritten; choose a new revision path for a source or policy refresh.
