# Phase 7 Segment-Aware Features Critique

## Review summary

B2b-1 closes the unsafe gap between multi-market normalization and feature projection. Product and
segment ownership, causal watermarks, complete-input refusal, schema/runtime validation, lineage,
cleanup, repetition, and frozen legacy behavior are explicit and tested.

## Finding register

| ID | Finding | Impact | Status and follow-up |
| --- | --- | ---: | --- |
| B2B1-01 | Replay/backtest cannot consume normalization V3 or the new feature successors. | 4 | Deliberately open for B2b-2; retaining refusal is a B2b-1 acceptance requirement. |
| B2B1-02 | Discontinuous/incomplete feature publication is not supported. | 3 | Deliberately deferred. Cursor invalidation exists, but downstream eligibility needs a separate contract. |
| B2B1-03 | Cross-market joined features have no staleness or missing-market contract. | 3 | Correctly excluded; require a separately approved causal join design. |
| B2B1-04 | Projection and artifact orchestration remain in the broad `pmm_phase7.py` module. | 3 | Maintainability debt. Extract only when B2b-2 provides a concrete interface boundary; do not rewrite legacy adapters. |
| B2B1-05 | Projection checkpoints are internal/in-memory only. | 2 | Durable feature continuation is not needed for current deterministic full replay and remains deferred. |
| B2B1-06 | Input hashes are recomputed during local materialization. | 2 | Correct but not optimized. Measure with B2c retained evidence before redesign. |

## What was done well

- Every row is owned by one product and segment.
- Boundary/snapshot adjacency and product identity are revalidated at runtime.
- Raw, normalization, and product-local causal positions remain distinct.
- Invalidation clears mutable book and segment-local last-trade state.
- Complete-only eligibility fails closed without weakening V3 representation.
- The new formats are additive and legacy bytes, meanings, and refusals remain unchanged.
- Tests are deterministic, offline, and include output repetition, CLI cleanup, schema parity, and
  reviewed product-lineage propagation.

## Non-claims

B2b-1 does not prove recovered missing history, cross-market causality, execution realism, queue
position, hidden liquidity, fills, fees, accounting, settlement, PnL, profitability, paper
readiness, or live readiness.
