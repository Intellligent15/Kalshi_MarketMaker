# Phase 7 Multi-Market Replay and Backtesting

## Delivered B2b-2 implementation boundary

B2b-2 adds `backtest-v4` and `verify-backtest-v4` without changing the legacy runner. The new path
accepts only normalization manifest V3 plus feature row V2/manifest V3 whose hash graph, product
order, segment membership, causal watermarks, and reviewed lineage agree.

One coordinator owns the global normalized order. Each declared product owns its strategy clock,
current segment, pending/live orders, contract inventory view, latency policy, and canonical C++
risk process. No strategy reads another product's feature.

## Scheduling contract

Actions are ordered by effective time, originating normalization ordinal, lifecycle stage, product
declaration ordinal, product-local ordinal, and global ordinal. They cannot execute before their
global input or product-local watermark. Market/trade visibility precedes any decision derived
from the same record. Only already acknowledged same-product/same-segment orders are fill-eligible.

The last canonical input time is the replay horizon. Later decisions and fills are not created;
remaining model state is cancelled with `end_of_run`.

## Artifacts and compatibility

V4 emits decisions, submitted orders, cancellations, acknowledgements, rejections, fills,
exposure, risk events, summaries, one unchanged risk trace per contract, and a V4 result manifest.
Every row names product, contract, segment, strategy instance, causal watermark, truth/fidelity,
configuration hash, and feature-definition hash.

Configurations and results V1/V2/V3, legacy commands, product packages, conversion policies,
refusal codes, risk checkpoints, and conformance fixtures retain their bytes and meanings.

## Validation status

The focused B2b-2 suite passes 9 tests and the frozen Phase 7 suite passes 42 tests. The 13 capture,
42 product-term, 17 checkpoint-reader, and 17 fixture-integrity tests pass, as do formatting, all
145 Python tests, and all 78 CTests. Seventeen accidentally deleted retained-package files were
restored byte-for-byte from `HEAD`; catalog and frozen package-tree verification pass without
reacquisition or rewriting accepted bytes.
