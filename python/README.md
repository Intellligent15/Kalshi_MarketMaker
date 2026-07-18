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

### Multi-market and reconnect-aware successor

`capture-v2` is additive; the original `capture` command remains the frozen single-market path.
The successor accepts repeated tickers, sorts them deterministically, binds subscription
acknowledgements to request/channel/SID identities, and records explicit connection segments and
raw ingress ordinals:

```sh
uv run --env-file .env python python/kalshi_capture.py capture-v2 \
  --ticker MARKET-A --ticker MARKET-B \
  --duration 300 \
  --output data/raw/two-market-smoke
```

Normalize the capture with the successor contract:

```sh
uv run python python/pmm_phase7.py normalize-v3 \
  --input data/raw/two-market-smoke \
  --output data/processed/kalshi/two-market-normalized-v3
```

Default normalization refuses discontinuous or incomplete input. `--continuity-policy record`
retains explicit evidence for audit, but it still refuses a requested market that never establishes
a stable venue market ID. Current feature and backtest commands deliberately refuse normalization
V3; B2b may implement segment-aware multi-market projection only against the hardened boundary.

For `capture-v2`, exit 0 means the finalized capture is eligible for strict normalization. Exit 2
may still leave valuable finalized raw evidence when the operation completed but its
`data_usability` is `record_only` or `unusable`; the diagnostic is written to stderr and metadata
records operational shutdown separately from continuity and usability.

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

uv run python python/pmm_phase7.py features-v3 \
  --input data/processed/kalshi/two-market-normalized-v3 \
  --output data/processed/kalshi/two-market-features-v3

uv run python python/pmm_phase7.py backtest \
  --config configs/phase7/kalshi_wsh_tor_no_fill_product_terms_v3.json \
  --output results/kalshi/wsh-tor-wsh2-no-fill-product-terms-v3

uv run python python/pmm_phase7.py verify-lineage \
  --config configs/phase7/kalshi_wsh_tor_no_fill_product_terms_v3.json \
  --result results/kalshi/wsh-tor-wsh2-no-fill-product-terms-v3
```

`features-v3` is additive. It accepts only normalization V3 artifacts whose completeness is
`complete_observed_interval`, verifies the normalization, records, scope-map, and product-map
hashes, and writes one segment-aware feature row per valid product event. It refuses discontinuous
or incomplete V3 evidence with exit 2, removes its own partial output on failure or interruption,
and never overwrites a final directory. The legacy `features` command and replay/backtest paths
retain their existing meanings; replay/backtest still does not accept normalization V3.

`pmm_product_terms.py` also provides explicit `fetch`, `build`, `review`, `inspect`, `compare`,
`diff`, and `assess-legacy` operator commands. Only `fetch` uses the network. Deterministic runtime
and tests consume reviewed local bytes. Final artifact directories are immutable and are not
overwritten; choose a new revision path for a source or policy refresh.

For a new acquisition, copy `configs/product_catalog/acquisition_spec.example.json`, replace its
ticker placeholders, add every linked document required for review, and fetch to a new directory.
The fetcher validates every redirect and final host, streams in 64 KiB chunks, applies 2 MiB JSON,
4 MiB text, 32 MiB PDF, and 64 MiB package limits, hashes incrementally, records observed V2 HTTP
provenance, and removes partial output on expected failure or interruption. The existing reviewed
source-manifest V1 remains valid and is not rewritten.

For bracketed evidence, acquisition-spec V2 names the immutable acquisition-policy hash and one
`opening` or `closing` observation. Fetch each observation independently, then use
`assemble-observations` offline. The assembled source-manifest V3 interval starts at opening
completion and ends at closing start. `build-evidence` adds field-level JSON, Markdown, and PDF
anchors before review V2 can be created. Review V2 requires a repository-declared reviewer,
responsibilities, and an accepted checklist; it is not a signature.

Future packages that claim generic completeness use evidence-profile V1, acquisition-spec V3,
source-manifest V4, evidence-map V2, and review V3. Run their offline document verification inside
`nix develop`: the evidence map pins nixpkgs revision
`59682e0069f0ed0a452e2179a7f4c1f247027b9e` and Poppler `26.06.0`, including the exact `pdfinfo`
and `pdftotext` version lines. Evidence-map V1 remains a hash-bound human-review address format;
it is not reinterpreted through the V2 extractor.

Focused product-term validation commands are:

```sh
UV_CACHE_DIR=/tmp/pmm-uv-cache \
  nix develop --command uv run python -m unittest python.tests.test_product_terms

UV_CACHE_DIR=/tmp/pmm-uv-cache \
  uv run python -m unittest \
  python.tests.test_product_terms.ProductTermsTests.test_reviewed_schema_runtime_parity_matrix

UV_CACHE_DIR=/tmp/pmm-uv-cache \
  uv run python -m unittest \
  python.tests.test_product_terms.ProductTermsTests.test_acquisition_streams_observed_v2_metadata_through_allowed_redirect \
  python.tests.test_product_terms.ProductTermsTests.test_acquisition_refuses_redirect_size_media_and_interruption_without_partial_output

UV_CACHE_DIR=/tmp/pmm-uv-cache \
  uv run python -m unittest \
  python.tests.test_product_terms.ProductTermsTests.test_public_cli_has_stable_status_and_stream_contract
```

See `docs/07 Engineering Notes/Product Terms Refusal Codes.md` for stable codes, exit statuses,
and stdout/stderr ownership.

## Multi-market replay and backtesting

The additive B2b-2 path consumes the approved normalization/feature successors:

```sh
uv run python python/pmm_phase7.py backtest-v4 \
  --config path/to/multi-market-v4.json \
  --output results/kalshi/multi-market-v4

uv run python python/pmm_phase7.py verify-backtest-v4 \
  --config path/to/multi-market-v4.json \
  --result results/kalshi/multi-market-v4
```

V4 is complete-input only. It uses one global causal coordinator, independent per-product state,
and one unchanged C++ risk projection per contract. Per-contract risk is not portfolio
aggregation. The original `backtest` and `verify-lineage` commands retain V1/V2/V3 behavior.
