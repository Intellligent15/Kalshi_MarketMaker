# Phase 7 Multi-Scope Capture Explained

## The short version

B2a changed the historical-data boundary from “a file of market messages” into “an auditable
record of what the recorder received, which subscription scope it came from, and where continuity
stopped being supportable.”

It did not add a multi-market strategy or backtest. It built the evidence contract those consumers
will eventually need.

The central rule is:

> Preserve what was observed, reconstruct only what the evidence supports, and make every unknown
> or missing interval impossible for a downstream reader to ignore.

That rule explains the versioned artifacts, ingress ordinals, explicit source scopes, reconnect
segments, recovery snapshots, truth labels, and current downstream refusal.

## What problem were we solving?

The original recorder was useful for one ticker. It retained raw WebSocket frames and noted when a
connection ended. The original normalizer then focused on market messages and discarded most of
that lifecycle context.

That becomes unsafe once there are multiple markets or reconnects. Consider this timeline:

| Step | What happens | What is actually known |
| ---: | --- | --- |
| 1 | A book snapshot arrives. | The published Level-2 book is known at that point. |
| 2 | Several deltas arrive. | The displayed book can be advanced within the represented sequence scope. |
| 3 | The WebSocket disconnects. | Some unknown amount of source history may be missing. |
| 4 | A new WebSocket subscribes. | This is a new mechanical connection and request identity. |
| 5 | A new snapshot arrives. | The later published book is known, but the missing interval is still unknown. |

If step 3 disappears during normalization, a consumer can accidentally treat steps 2 and 5 as one
continuous history. That can create features from a book state the source never proved. B2a makes
the disconnect and the new segment part of the normalized contract.

## What we built

B2a introduced an additive successor chain:

| Layer | Successor | Responsibility |
| --- | --- | --- |
| Capture configuration | `pmm.kalshi.capture_config.v2` | Sorted multi-ticker membership, fixed channels, one declared connection strategy. |
| Raw capture metadata | `pmm.kalshi.raw_capture.v2` | Capture identity, environment, truth/fidelity, connection summaries, shutdown, and bounded continuity assessment. |
| Raw records | `pmm.kalshi.raw_capture_record.v2` | Every lifecycle action and inbound frame in one capture-global ingress order. |
| Source scopes | `pmm.historical.source_scope_map.v1` | Connection, request, channel, venue SID, membership, and explicit sequence-domain status. |
| Normalized records | `pmm.historical.normalized_record.v2` | Market events, discontinuities, and segment boundaries in one ordered stream. |
| Product identity | `pmm.historical.product_map.v3` | One product entry per ticker with optional reviewed product-term lineage. |
| Normalization manifest | `pmm.historical.normalization_manifest.v3` | Input/output hashes, counts, policy, completeness, limitations, and lineage. |

The command names are `capture-v2` and `normalize-v3`. The row schema is called normalized-record
V2 because row and package versions evolve independently: legacy normalization V1 used normalized
event V1, while the package-level manifest is now on its third version.

## How capture V2 works

### 1. Canonicalize configuration

The CLI accepts repeated `--ticker` arguments. It rejects empty or duplicate values, sorts the
tickers, fixes channel order as `orderbook_delta` then `trade`, and currently accepts only
`single_connection_v1`.

Sorting matters because two users who provide the same set in different argument order should send
the same subscription request and produce the same declared membership.

### 2. Open one connection segment

Each connection attempt receives a monotonically increasing `connection_segment_id`. Within the
current strategy, that connection sends one request containing both channels and all requested
tickers.

The client-side logical request identity and the venue wire request ID are recorded separately.
That separation leaves room for future batching without pretending that a WebSocket SID is the
same thing as the command that requested it.

### 3. Bind acknowledgements

The venue acknowledgement binds:

- connection segment;
- logical subscription request;
- wire request ID;
- channel; and
- venue subscription ID, or SID.

The acknowledgement does not prove that every requested market will produce data. B2a therefore
uses the deliberately narrow membership claim
`request_bound_not_echoed_by_acknowledgement`.

### 4. Assign ingress ordinals

Every record—connection attempt, open, request, acknowledgement, source frame, gap, close, or
binary-frame rejection—gets one increasing `raw_ingress_ordinal` from the single writer.

This ordinal is the recorder's strongest cross-scope ordering fact. It says “the recorder wrote A
before B.” It does not say the venue created A before B, nor that two network streams are globally
causal.

### 5. Preserve partial raw evidence

On interruption or failure, raw bytes that were already recorded are flushed and retained with an
explicit shutdown status. Raw evidence is valuable even when it is incomplete. Derived
normalization is different: it is built in a `.partial` directory and removed on any exception or
interruption, so a half-published derived artifact cannot look complete.

## The identity model

Several identifiers that look similar answer different questions:

| Identity | Question answered | Reused after reconnect? |
| --- | --- | --- |
| Venue/environment | Which source system produced the evidence? | Yes. |
| Connection segment | Which continuous local socket attempt received it? | No. |
| Subscription request | Which client command requested the stream? | No. |
| Wire request ID | Which request did the venue acknowledgement answer? | May repeat on another connection, so connection remains part of identity. |
| Channel | Was this order-book or trade data? | Yes, but bound again per request. |
| Venue SID | Which acknowledged subscription carried the message? | May change or repeat after reconnect. |
| Ticker/market ID | Which product does the payload describe? | Stable only when the retained payloads prove it. |
| Message type | Snapshot, delta, trade, or control evidence? | Per record. |
| Sequence domain | Across which messages can sequence values be compared? | Unknown in current retained primary evidence. |
| Book segment | Within which snapshot-seeded interval is book state supported? | A reconnect or book-scope gap starts a new one only after a snapshot. |

The important design choice was not to compress these into one “stream ID.” Compression would be
convenient but would erase exactly the uncertainty B2a exists to preserve.

## Why sequence scope is recorded as unknown

A sequence number is useful only after its comparison domain is known. The value `42` might be the
42nd message for one market, one channel, one subscription, one socket, or the entire venue.

The reviewed official documentation did not establish a general domain broad enough to encode as
a durable guarantee. B2a therefore distinguishes:

- `documented`: retained primary evidence defines the domain;
- `fixture_declared`: a synthetic test declares its own domain; and
- `unknown`: production evidence does not establish it.

The current mechanical validation key is connection segment plus SID. This is useful for detecting
potential gaps and duplicates, but it is not a claim about venue-global history.

The post-implementation critique found an important consequence: when one such scope covers
multiple tickers, a gap cannot safely be attributed only to the ticker on the next message. The
missing message may have belonged to any scope member. That impact-5 defect must be corrected in
B2a-1 before B2b consumes the records.

## How normalization V3 works

Normalization reads raw JSONL once in ingress order and maintains a small logical state model:

- known subscription requests;
- acknowledged channel/SID scopes;
- last sequence and duplicate identity per represented scope;
- stable market ID per ticker;
- last source time per scope;
- global monotonic logical time; and
- book validity and segment number per ticker.

For each raw record it either validates lifecycle evidence, emits a normalized market event, emits
a discontinuity, emits a segment boundary, or ignores a known non-market lifecycle record after
its evidence has been accounted for.

### Ordering and time

Normalization does not sort by timestamp or sequence. It preserves raw ingress order.

Each market event carries:

- raw ingress ordinal;
- normalization ordinal;
- source time when present;
- local receive time;
- monotonic logical time;
- whether source time was late relative to its scope; and
- whether it was late relative to the global presentation clock.

Logical time is:

```text
max(previous logical time, current event time)
```

This keeps consumers monotonic without moving late events. A late message stays where it was
received and is labelled late instead of being rewritten into an invented order.

### Duplicate handling

Within the represented mechanical scope, `(source scope, sequence)` is the duplicate identity.

- Same identity and same canonical payload: idempotent duplicate; skip it and count it.
- Same identity and different payload: conflicting duplicate; refuse.
- Sequence decreases: regression; refuse.
- Sequence jumps forward: emit a gap and invalidate affected supported state.

The current implementation retains every sequence payload hash, which makes duplicate semantics
easy to audit but memory use linear in event count. B2c measurements should drive a bounded or
disk-backed successor.

## Reconnect and recovery as a state machine

Each market's book state is intended to follow this model:

| Current state | Evidence | Next state | Meaning |
| --- | --- | --- | --- |
| Awaiting initial snapshot | Snapshot | Valid segment 1 | Book is supported from this observed snapshot onward. |
| Awaiting initial snapshot | Delta | Still invalid | Source message exists, but no supported book can apply it. |
| Valid segment | Contiguous delta | Same valid segment | Apply within supported mechanical continuity. |
| Valid segment | Connection or relevant sequence gap | Awaiting recovery snapshot | Prior book is invalidated; missing interval begins. |
| Awaiting recovery snapshot | Delta | Still invalid | Retain only in record mode with `book_state_valid: false`; strict mode refuses. |
| Awaiting recovery snapshot | Snapshot | New valid segment | Later book is supported from the snapshot, but the gap remains. |

A later snapshot answers “what was the displayed book then?” It does not answer “what happened in
the missing interval?” That is why the capture may be `observed_discontinuous` even after every
market has a new valid segment.

The deeper audit found a second semantic edge that needs an explicit decision: a disconnect before
any initial snapshot may be an incomplete prefix, not “two valid observed segments around a gap.”
The current corpus does not isolate that case.

## Completeness categories

| Category | Supported claim | Unsupported claim |
| --- | --- | --- |
| `complete_observed_interval` | Required acknowledgements/snapshots exist and no represented defect was found inside the bounded input, subject to declared limitations. | Venue-global completeness, hidden orders, queues, or executions. |
| `observed_discontinuous` | One or more observed segments are valid, with an explicit missing interval. | Continuous history or reconstruction of the gap. |
| `incomplete` | Raw evidence exists but required identity, acknowledgement, snapshot, sequence, frame, or valid state is missing. | A projection-ready interval. |

Default normalization publishes only the first category. `--continuity-policy record` is an audit
mode that can preserve the other two. It is not an instruction to treat them as backtest-ready.

The review found that record mode can currently publish `venue_market_id: null` for a ticker that
never establishes identity even though product-map V3 requires a string. That impact-5
schema/runtime mismatch must be fixed before incomplete V3 output is treated as a valid artifact.

## Truth and fidelity

B2a keeps two different axes explicit:

| Evidence | Truth category | Why |
| --- | --- | --- |
| A retained real venue frame | `Observed` | The recorder directly received these bytes. |
| A deterministic fixture frame | `Synthetic` | The test constructed it. |
| “This gap invalidates supported book state” | `Reconstructed` for real input | It is a deterministic conclusion from observed lifecycle evidence, not a venue frame. |
| A simulated fill | `ModelDerived` | Outside B2a; no such execution fact is created here. |

Source fidelity remains Level 2. A displayed price level is not an individual order. B2a does not
prove queue position, FIFO ownership, cancellations behind a level change, hidden liquidity,
counterfactual fills, or venue-equivalent execution.

## Product-term lineage

Product-map V3 contains one ordered product entry per ticker. When a reviewed catalog and conversion
policy are supplied, each entry binds exact hashes for:

- authoritative product terms;
- source manifest;
- human review record; and
- conversion policy.

The normalizer copies the immutable package bytes into the derived artifact. This allows two
markets to retain independent terms/review lineage without weakening exact-conversion refusal.

B2a did not change fees, settlement, payout interpretation, accounting, collateral, margin, or
PnL. Carrying a product package proves which reviewed terms were used; it does not mean every
economic policy has been implemented.

## Why we used version successors

Four alternatives were considered:

| Alternative | Why it was not chosen |
| --- | --- |
| Tighten existing V1/V2 rows and manifests | Old accepted bytes never carried scopes or discontinuities. Assigning new meaning to them would break reproducibility. |
| Add only a gap sidecar | A consumer could read market events and silently ignore invalidation evidence. |
| Sort all markets by source timestamp | Clock precision, lateness, and incomparable scopes would create causality the source does not prove. |
| Treat the first post-reconnect snapshot as recovery of continuity | It proves only the later displayed state, not the missing path. |

The successor chain costs more code and more version names, but it preserves accepted artifacts and
makes the dangerous evidence impossible to omit accidentally from the new main record stream.

## Compatibility boundary

| Existing artifact | B2a treatment |
| --- | --- |
| Raw capture V1 | Unchanged; legacy command and bytes retain their meaning. |
| Normalization V1/V2 | Unchanged; no synthetic scopes or recovery claims are inserted. |
| Product-map V1/V2 | Unchanged. |
| Feature V1/V2 | Unchanged; current feature materialization rejects normalization V3. |
| Backtest configuration V1/V2/V3 | Unchanged. |
| Result artifacts | Unchanged. |
| Accepted retained product packages | Byte-identical and interpreted by their original version contracts. |

This refusal is deliberate. “Can parse a new row” is not the same as “knows how to maintain one
projection per product and segment.” B2b must add that support explicitly.

## How we tested it

All B2a tests are offline. They use:

- fake asynchronous transports;
- injected monotonic and UTC clocks;
- minimal synthetic JSONL captures;
- a retained small scenario matrix;
- schema validation;
- repeated normalization with byte comparisons;
- interruption injection;
- legacy artifact checks; and
- reviewed product-package lineage.

The implemented tests cover two markets, shared mechanical scopes, independent channel scopes,
request/channel/SID acknowledgement binding, reconnect snapshots, missing and duplicate recovery
snapshots, deltas before recovery, sequence gaps/regressions, identical/conflicting duplicates,
membership/ordinal defects, cleanup, CLI success/refusal, downstream refusal, and lineage.

The post-implementation critique is intentionally candid about what that list does not prove.
Happy-path schema validation is not a one-defect parity matrix, V3 time ties are not isolated, a
disconnect before the first snapshot is absent, and the two impact-5 cases were not represented.

## What the implementation currently proves

It proves that the repository can deterministically:

- configure and record a sorted multi-ticker request on one connection at a time;
- retain lifecycle and raw source evidence in one ingress order;
- bind common acknowledgement identities;
- normalize multiple requested tickers without merging their product identity;
- preserve late events without reordering;
- expose reconnect gaps and snapshot-started segments;
- refuse known discontinuous/incomplete inputs by default;
- keep legacy artifact bytes and meanings unchanged; and
- repeat supported offline normalization byte-for-byte for the same input path and bytes.

It does not yet prove every shared-scope gap is propagated to every possibly affected market, that
every record-mode output satisfies every successor schema, that capture exit status communicates
data usability unambiguously, or that resource use is bounded for long captures. Those are current
debt, not hidden assumptions.

## Why B2a-1 now comes before B2b

B2b will build projections and features from `book_state_valid`, book segments, scope membership,
and completeness. If those facts under-propagate a shared gap or an incomplete artifact violates
its declared schema, downstream code would formalize the wrong boundary.

The smallest responsible next step is therefore B2a-1:

1. propagate unknown/shared gaps to every possibly affected member;
2. resolve missing market-ID representation/refusal;
3. enforce required sequence and acknowledgement invariants;
4. define disconnect-before-initial-snapshot semantics;
5. complete one-defect schema/runtime tests; and
6. clarify capture CLI status versus data usability.

Only after that should B2b implement per-product, per-segment projection, features, replay, and
backtest orchestration.

## Non-claims

B2a remains a historical evidence boundary. It does not provide:

- multi-market feature generation or backtesting;
- a retained long-duration capture;
- calibrated fills or queue position;
- hidden-liquidity or cancellation truth;
- fees, accounting, PnL, collateral, margin, or settlement;
- profitability evidence;
- paper trading, authenticated order gateways, or live order behavior; or
- operational durability, reconciliation, monitoring, or venue equivalence.

See [[02 Architecture/ADR-013 Multi-Scope Capture and Reconnect-Aware Normalization]],
[[07 Engineering Notes/Phase 7 Multi-Scope Capture and Recovery]], and
[[07 Engineering Notes/Phase 7 Multi-Scope Capture Critique]].

## B2a-1: what changed after the critique

The B2a critique found that the architecture was conservative in principle but not at every edge.
B2a-1 closes those edges without adding a consumer.

The most important correction is the difference between the ticker that reveals a gap and the
markets the missing event could have affected. A post-gap message can identify itself, but it
cannot identify the absent message. The normalized gap therefore carries both
`observed_post_gap_ticker` and a sorted `affected_market_tickers` set. Shared and unknown
order-book scopes invalidate every possible member; an independently declared scope invalidates
only its member.

The sequence contract is now type-specific. Order-book snapshots and deltas require an integer
sequence. Public trades do not, because the official public-trade message contract does not carry
one; a trade sequence is still validated when present. Acknowledgements and lifecycle records use
their explicit request, connection, SID, and ingress identities instead.

Record mode remains an evidence-preservation policy, not a schema escape hatch. It can publish
honest discontinuity and incomplete-prefix evidence, but it cannot publish an unidentified
product. Every requested ticker must establish one stable capture market ID before final output.

Recovery now distinguishes two histories:

- a valid observed segment, a gap, and a later snapshot-started segment is discontinuous; and
- a disconnect before any valid snapshot leaves an incomplete prefix, even if a later snapshot
  establishes the first valid observed segment.

Finally, normalization re-proves the complete subscription transaction instead of trusting the
capture writer: one canonical request, one acknowledgement per channel, matching logical and wire
IDs, exact declared membership, and connection-local SID uniqueness. Runtime schema validation and
one-defect tests make malformed successor records fail at the same boundary as semantic defects.

These corrections make normalization V3 safe to design against. They do not implement B2b's
multi-market projection, causal features, replay, or backtesting.
