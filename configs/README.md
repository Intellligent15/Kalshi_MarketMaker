# Configuration

This directory holds explicit, versioned runtime and experiment configuration.

`phase7/kalshi_wsh_tor_v1.json` is the deterministic Level-2 V1 experiment for the captured
Washington–Toronto contract. It uses only local normalized data/features, explicit logical
latencies, external synthetic risk admission, and the `trade_touch_v1` fill model.
`phase7/kalshi_wsh_tor_no_fill_v1.json` is its no-fill control. Neither configuration implies
queue-position, venue-acknowledgement, fee, PnL, collateral, settlement, paper-trading, or live
execution realism.

New research configurations may set `risk.engine` to `cxx_oracle_v1` and provide an explicit
`risk.limits` block plus the local `pmm_risk_oracle` executable path. This is the canonical C++
admission path for research. `python_reference_v1` remains only for V1 configuration compatibility
and conformance testing. An optional `pmm.accounting_policy.v1` block currently supports only
unresolved model-fill cash flows and fees; it must not be interpreted as PnL or settlement.
