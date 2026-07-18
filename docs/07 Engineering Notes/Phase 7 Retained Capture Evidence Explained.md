# Phase 7 Retained Capture Evidence Explained

## What B2c tooling adds

The historical pipeline already knows how to capture several markets, normalize their source scopes,
materialize per-market features, and run a complete-input multi-market backtest. What it lacked was
one auditable wrapper that answers: which exact files belong to this evidence package, are their
counts and hashes still true, did reviewed product terms cover the run, how much resource did each
stage use, and did repeated offline processing produce the same bytes?

B2c adds that wrapper without changing the accepted market-data or research formats.

The fixed policy says what must be decided before looking at the outcome: twelve hours, three
markets, one connection, one attempt, fixed storage ceilings, no manufactured reconnect, and no
recapture until clean. The evidence index then records what actually happened. Policy is prospective;
evidence is retrospective. Keeping them separate prevents the result from rewriting the experiment.

## Why there are three measurement layers

The generic measurement process observes the whole process tree. That matters because Backtest V4
starts C++ risk children, so Python RSS alone is incomplete. It also records disk growth, wall time,
machine context, and scrubbed stream hashes.

Normalization telemetry observes the one important internal owner that RSS cannot identify:
`sequence_payloads`. The table holds one payload hash per scoped sequence identity. Its entries grow
monotonically today, so current, peak, and final entry counts plus power-of-two samples make the
linear relationship reviewable without generating another event-sized log.

Risk telemetry observes each contract separately. It separates executable resolution/build checking,
spawn-to-READY, process lifetime, request count, response count, blocking response time, and trace
size. These measurements inform B2B2-05; they do not authorize batching or a native rewrite.

All telemetry is sidecar data. Turning it on cannot change normalization, feature, result, or risk
trace bytes, and tests compare instrumentation-on and instrumentation-off artifacts directly.

## Truthful partial evidence

A capture does not become worthless because it disconnected, was interrupted, or lacked compatible
closing product evidence. Raw frames and finalized metadata remain observed evidence. The index can
record a product lineage as unavailable with a reason, but it cannot claim Backtest V4 eligibility
unless all three reviewed intervals cover the complete capture.

Likewise, a natural reconnect is useful evidence of a missing interval. It is not evidence that the
later snapshot reconstructed the gap. The strict feature and backtest stages therefore remain
ineligible. Synthetic fixtures continue to test forced recovery mechanics separately and never enter
an Observed package.

## What the verifier proves

Index-only verification proves that the compact claim is well-formed and internally consistent. It
does not pretend that absent large bytes were checked.

Mounted verification proves exact membership, byte lengths, SHA-256 identities, JSONL counts, raw
metadata reconciliation, normalization event/discontinuity counts, feature totals, Result V4 typed
artifact membership, risk-trace cardinality, and the key lineage hashes between stages. It also
rejects unsafe paths, symlinks, undeclared files, and private-key material.

It still does not prove venue-global sequence scope, hidden orders, queues, calibrated fills, fees,
PnL, settlement, portfolio risk, durability, or profitability.
