# ADR-013: Multi-scope capture and reconnect-aware normalization

- Status: Accepted
- Date: 2026-07-17
- Scope: Phase 7 Track B2a

## Context

Raw-capture V1 accepts one ticker and sends one two-channel request per connection. It retains
connection gaps and raw acknowledgements, but normalization V1/V2 ignores lifecycle records and
uses `(connection_id, sid, sequence)` only as a mechanical sequence and duplicate key. A reconnect
therefore starts a new mechanical scope without proving continuity, while the single-book feature
projection could otherwise apply post-reconnect deltas to pre-gap state.

Official Kalshi documentation supports multi-ticker subscriptions, identifies acknowledgements by
request ID, channel, and venue SID, and describes an order-book snapshot before incremental deltas.
The reviewed documentation does not establish a general global, per-market, per-channel, or
reconnect-spanning sequence domain. The implementation must retain that uncertainty rather than
infer a broader guarantee.

Tightening accepted capture, normalized-event, manifest, or product-map formats would assign facts
to old bytes that they never carried. A sidecar-only discontinuity file would allow a consumer to
read market events while accidentally ignoring book invalidation.

## Decision

Add a frozen successor chain:

- `pmm.kalshi.capture_config.v2` defines sorted unique tickers, fixed channel order, unified YES
  pricing, and `single_connection_v1`;
- `pmm.kalshi.raw_capture.v2` separates operational shutdown from bounded continuity assessment;
- `pmm.kalshi.raw_capture_record.v2` gives every lifecycle or inbound record one capture-global raw
  ingress ordinal;
- `pmm.historical.source_scope_map.v1` binds connection segment, request identity, channel, venue
  SID, requested membership, and explicit sequence-domain status;
- `pmm.historical.normalized_record.v2` is an ordered union of market events, discontinuities, and
  segment boundaries;
- `pmm.historical.product_map.v3` owns an ordered multi-product collection with independent
  reviewed lineage when a catalog is supplied; and
- `pmm.historical.normalization_manifest.v3` hashes the complete successor boundary and records
  completeness, limitations, event counts, and discontinuity counts.

The capture runtime uses one WebSocket at a time and one deterministic request containing both
channels and every sorted ticker. Reconnects create sequential connection segments. Concurrent
multi-connection capture remains unsupported and is refused rather than inferred.

## Acknowledgement and membership rules

Request identity and venue SID are separate. Every `subscribed` response is bound by connection
segment, wire request ID, expected channel, and unique SID. Both `orderbook_delta` and `trade`
acknowledgements are required. An unexpected request ID or channel, duplicate channel, conflicting
SID, unbound data SID, or observed ticker outside requested membership is an expected data refusal.

The acknowledgement documents channel success but does not echo per-market membership. The scope
map therefore labels membership `request_bound_not_echoed_by_acknowledgement`; it never claims that
every requested market produced activity.

## Sequence and ordering rules

The retained source evidence does not prove the venue sequence domain. Production capture records
`unknown`; synthetic fixtures may use `fixture_declared`, and future primary evidence may justify
`documented`.

The conservative mechanical validation key is connection segment plus venue SID. Sequence values
validate progression and duplicate identity only inside that represented scope. The same numeric
value after reconnect is a different identity. Exact duplicate payloads are idempotent; conflicting
payloads at the same scoped identity refuse. Regressions refuse and forward jumps create explicit
sequence-gap records.

Raw ingress ordinal is the authoritative cross-scope total order. Normalization never sorts by
sequence or source timestamp. Source time remains an observed attribute; equal timestamps and all
other cross-scope ties retain ingress order. Logical time is monotonic through
`max(previous_logical_time, event_time)`, and lateness is recorded both within a source scope and
against the global presentation clock.

This clarifies ADR-007's statement that source time merges scopes: source time supplies event time
when present, but it does not reorder incomparable scopes or establish cross-scope causality.

## Reconnect and recovery

A connection gap invalidates every affected book segment. No pre-gap book state survives. The new
connection, request, acknowledgements, SIDs, and sequence scopes are new mechanical identities.

Each requested market requires exactly one order-book snapshot per connection segment. A qualifying
snapshot starts a new segment labelled `valid_from_observed_snapshot_only`. It does not reconstruct
the missing interval or prove continuity. Deltas before the required snapshot are retained only in
`record` mode with `book_state_valid: false`; default normalization refuses them. Missing or
duplicate recovery snapshots refuse or produce explicit incompleteness according to policy.

Default `normalize-v3` publishes only `complete_observed_interval`. Explicit
`--continuity-policy record` may publish `observed_discontinuous` or `incomplete` evidence. Current
feature generation refuses normalization V3 with `DownstreamContinuityRequired`; segment-aware
projection belongs to B2b.

## Truth and fidelity

Real venue frames remain `Observed`; deterministic test captures remain `Synthetic`; scope and
continuity assessments derived from real operational evidence are `Reconstructed`. B2a creates no
`ModelDerived` execution fact. Level-2 limitations remain unchanged: no queue, individual-order,
hidden-liquidity, cancellation, own-fill, or venue-equivalent execution truth is implied.

## Compatibility

Raw capture V1, normalized event V1, normalization manifests V1/V2, product maps V1/V2, feature row
V1, feature manifests V1/V2, backtest configurations V1/V2/V3, result manifests V1/V2/V3, and all
accepted product packages retain their exact bytes and meanings. Compatibility readers do not
synthesize missing scopes, acknowledgements, segments, or recovery evidence.

## CLI and cleanup

Legacy commands retain their public behavior. Additive `capture-v2` and `normalize-v3` distinguish
success `0`, expected input refusal `2`, unexpected programming failure `1`, and interruption
`130`. Raw capture retains and finalizes valuable partial bytes on interruption/failure. Derived
normalization removes `.partial` output for every `BaseException`, including interruption.

## Consequences and non-goals

The successor has more explicit records and schemas, but prevents reconnect provenance from being
lost and gives B2b a deterministic contract. It does not implement multi-market projections,
features, backtests, long-capture evidence, streaming optimization, calibrated fills, queues,
fees, accounting, settlement, ML, paper trading, gateways, or live orders. Matching, core integer
types, account risk, checkpoint categories/ordinals, risk first-failure order, and accepted product
evidence remain unchanged.

## B2a-1 truth-boundary hardening amendment

B2a-1 closes the reviewed successor defects before any projection consumes normalization V3.
Sequence-domain evidence now declares both status and topology. A documented or fixture-declared
independent scope affects its one represented market; shared scopes affect their exact membership;
an unknown scope conservatively affects every requested market that its mechanical connection,
channel, and SID could carry. A gap records the observed post-gap ticker separately from the sorted
possible affected set. Order-book gaps invalidate every possibly affected book and require a new
snapshot for each one. Raw ingress order remains authoritative and a later snapshot still cannot
repair the missing interval.

Official order-book message documentation includes sequences on snapshots and deltas, while the
public-trade contract does not. The successor therefore requires an integer sequence on
`orderbook_snapshot` and `orderbook_delta`, validates a trade sequence when present, and does not
require source sequences on acknowledgements or lifecycle records. Missing required sequence
evidence is an explicit incomplete reason and a default refusal.

Each connection must contain exactly one canonical request and exactly one acknowledgement for
each expected channel. Normalization revalidates logical and wire request identities, exact sorted
membership, the non-echoed membership claim, channel cardinality, and SID uniqueness within the
connection. SID reuse after reconnect remains valid because connection segment is part of scope
identity. An acknowledgement proves request/channel success, not per-market activity.

A disconnect before a market's first valid snapshot is an incomplete prefix, not recovery between
two valid segments. Only a market that previously had valid snapshot-seeded state can enter
`recovery_snapshot`. A requested market that never establishes one stable non-empty venue market
ID refuses in both continuity policies; record mode represents continuity defects, not unidentified
products.

Runtime now validates all seven successor schemas at their read/write boundaries. Raw and
normalized record kinds are discriminated, sequence domains and gap details have exact shapes,
lineage is all-or-none, and generated positives plus one-defect negatives prove schema/runtime
agreement. These changes harden only the B2a successor formats; accepted legacy formats and
retained product packages keep their bytes and meanings.

`capture-v2` exit zero now means finalized evidence is eligible for strict normalization.
Operationally completed but record-only or unusable evidence is retained with finalized metadata,
an explicit `data_usability` value, a diagnostic on stderr, empty stdout, and exit two. Unexpected
programming failure remains one and interruption remains 130. `normalize-v3` retains the same
0/2/1/130 distinction and removes derived partial output on every failure or interruption.

## B2b-1 downstream-consumer amendment

The additive `features-v3` consumer revalidates the V3 cross-record state machine instead of
trusting segment strings as sufficient proof. It preserves normalization order, binds every event
to its product-map identity, requires boundary/snapshot adjacency, consumes conservative affected
market sets, and clears mutable book and last-trade state on invalidation. A recovery snapshot may
start a new segment but never changes the missing interval into continuous evidence.

Initial publication is deliberately narrower than the representational V3 boundary:
`features-v3` accepts only `complete_observed_interval`. `observed_discontinuous` and `incomplete`
artifacts remain inspectable normalization evidence but are not feature-eligible. This does not
reinterpret normalization V3, and accepted raw, normalized, feature, configuration, result, or
product artifacts remain unchanged.

## B2b-2 replay-consumer amendment

The V4 replay path revalidates normalization order, nondecreasing raw ingress and logical time,
boundary/snapshot adjacency, product membership, feature-row bijection, segment identity, global
and product-local watermarks, completeness, and every declared input hash. It refuses any
discontinuity or incomplete input before publication. A later snapshot remains a new segment and
never becomes evidence that a missing interval was recovered.

Cross-market features and strategies remain excluded. Interleaving supplies deterministic
visibility order, not an implicit latest-value join.

## B2c retained-evidence tooling amendment

B2c adds an evidence control plane around the accepted successor chain without changing its bytes or
eligibility rules. A fixed policy declares one twelve-hour, three-market, single-connection attempt,
one-attempt anti-selection behavior, disk ceilings, truthful outcome retention, and no manufactured
reconnect. A separately approved B2c-P package must establish contemporaneous reviewed product
coverage and durable storage ownership before capture.

The additive evidence index binds exact member paths, sizes, hashes, counts, lineage, reviewed
effective intervals, observed outcome, repetition inventories, measurements, and credential scan.
Index-only verification does not claim absent large bytes were checked; mounted verification requires
exact safe membership and reconciles parsed counts and cross-document identities.

Measurement remains outside deterministic artifacts. A fresh-process wrapper measures process-tree
resources and disk growth. Optional normalization telemetry counts the full-run duplicate table, and
optional Backtest V4 telemetry measures each synchronous contract oracle. Instrumentation on or off
must produce identical normalization, feature, result, and risk-trace bytes. Measurements may justify
a later optimization proposal but do not themselves alter duplicate, reconnect, streaming, or risk
semantics.
