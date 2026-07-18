# Phase 7 Multi-Market Replay Critique

## Review summary

The implementation closes the unsafe orchestration gap: products and segments are isolated,
latency stages are explicit, risk remains canonical, artifacts are auditable, and the new path is
additive. The retained product-file deletions were confirmed accidental, restored exactly from
`HEAD`, and the full offline validation gate was rerun successfully.

## Finding register

| ID | Finding | Impact | Status and follow-up |
| --- | --- | ---: | --- |
| B2B2-01 | The full product-term suite could not run against the dirty retained packages. | 5 | Closed: 17 accidental deletions were restored byte-for-byte from `HEAD`; catalog, frozen package-tree, focused product-term, and full Python validation pass. |
| B2B2-02 | Risk is independent per contract, not portfolio-wide. | 4 | Deliberately deferred; requires separately approved semantics. |
| B2B2-03 | Execution remains `no_fill_v1` or uncalibrated `trade_touch_v1`. | 4 | Deliberately deferred to execution sensitivity/calibration. |
| B2B2-04 | Discontinuous feature/replay publication is unsupported. | 3 | Correctly refused; later snapshots never recover missing history. |
| B2B2-05 | V4 launches one synchronous oracle per contract. | 3 | Measure with B2c before batching or native redesign. |
| B2B2-06 | No checked-in retained V4 run exists. | 2 | Add only after a reviewed complete multi-product input is retained. |

## What was done well

- One global schedule preserves interleaved causality.
- Product and segment identity is present on every derived artifact.
- Risk traces retain accepted V2 meaning and are bound per contract by Result V4.
- The replay horizon prevents post-input strategy or fill creation.
- Runtime and schemas share positive and one-defect-negative coverage.
- Cleanup owns only the partial directory created by the current invocation.
- Legacy commands and tests remain unchanged.

## Non-claims

B2b-2 does not establish cross-market alpha, portfolio risk, execution realism, accounting,
profitability, durable continuation, paper readiness, or live readiness.
