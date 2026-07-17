# Configuration

This directory holds explicit, versioned runtime and experiment configuration.

`phase7/kalshi_wsh_tor_v1.json` is the deterministic Level-2 V1 experiment for the captured
Washington–Toronto contract. It uses only local normalized data/features, explicit logical
latencies, external synthetic risk admission, and the `trade_touch_v1` fill model.
`phase7/kalshi_wsh_tor_no_fill_v1.json` is its no-fill control. Neither configuration implies
queue-position, venue-acknowledgement, fee, PnL, collateral, settlement, paper-trading, or live
execution realism.

`phase7/kalshi_wsh_tor_no_fill_cxx_oracle_v2.json` is the runnable canonical-risk control. It
uses `pmm.backtest.v2`, `cxx_oracle_v2`, and a repository-relative CMake target launcher rather
than a machine-specific oracle path. Build first with `./scripts/build.sh`, then run:

```sh
uv run python python/pmm_phase7.py backtest \
  --config configs/phase7/kalshi_wsh_tor_no_fill_cxx_oracle_v2.json \
  --output results/kalshi-wsh-tor-no-fill-cxx-oracle-v2
```

The source data remains local and ignored, so the command is runnable only after the documented
capture/normalization steps. V2 emits a hashed `risk-trace.jsonl` artifact and refuses a Python
risk fallback. `python_reference_v1` remains only for V1 configuration compatibility. An optional
`pmm.accounting_policy.v1` block currently supports only unresolved model-fill cash flows and
fees; it must not be interpreted as PnL or settlement.

`product_catalog/` owns immutable reviewed product revisions, retained first-party source bytes,
formal source/terms/review hashes, and conversion policies. The first catalog entry covers the
captured Washington–Toronto market retrospectively. Its review limitations are part of its exact
identity. Never edit a reviewed revision in place; add a new package and non-overlapping catalog
entry.

The second entry covers `KXHMONTH-26JUL` contemporaneously. Its opening and closing observations
are retained under one source-manifest V3 package, use the immutable
`acquisition_policies/kalshi_first_party_v1.json` policy, and carry field-level evidence anchors
plus review V2. The official empty secondary rule is represented by product-terms V2 rather than
invented text or a weakened V1 rule.

`product_catalog/acquisition_spec.example.json` is the source-manifest V2 operator template. Copy
it outside the reviewed catalog, replace placeholders, add required linked documents, and fetch to
a new revision directory. It declares requested source roles/URLs/paths only; the tool records
observed timestamps, redirects, final URL, response metadata, byte count, hash, and tool version.
Acquisition is explicit and networked; normalization, backtesting, verification, and tests remain
offline.

`phase7/kalshi_wsh_tor_no_fill_product_terms_v3.json` is the authoritative-terms no-fill control.
It requires normalization/feature V2 artifacts and names the exact product terms, retained source,
review, and conversion-policy hashes. It applies neither fees nor settlement. The older V1/V2
configs remain unchanged compatibility examples and are not silently upgraded.
