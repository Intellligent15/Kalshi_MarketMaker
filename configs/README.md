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
