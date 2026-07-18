# Phase 7 Multi-Scope Capture Critique

## Review scope and conclusion

This is the post-implementation review of B2a commits `520d0a0`, `399e500`, `48f2a25`,
`a04b0c1`, and `8036eb9`. It reviews the code, schemas, offline fixtures, tests, ADR, operator
guide, explanation, and roadmap closure.

The architectural direction is sound: B2a preserves raw ingress order, separates request/channel/
SID identity, refuses to invent venue sequence scope, makes reconnect discontinuities explicit,
and leaves accepted artifacts unchanged. Those choices are worth keeping.

The implementation is not yet a safe base for B2b. This deeper review found two impact-5 defects
and several impact-4 gaps that the first critique missed. They do not corrupt accepted legacy
artifacts, but they weaken the new V3 truth boundary. A small B2a-1 hardening package should close
them before multi-market projection begins.

## Impact scale

| Impact | Meaning |
| ---: | --- |
| 1 | Cosmetic or local maintainability issue with no meaningful correctness effect. |
| 2 | Minor operational or maintainability debt; safe to defer until the containing code changes. |
| 3 | Material debt or coverage gap that can cause confusion, cost, or a bounded unsupported case. |
| 4 | High research-validity, compatibility, or operational risk; should be closed before broader use. |
| 5 | Truth-boundary or contract blocker; downstream work must not rely on the affected behavior. |

Impact rates consequence, not implementation effort. A five-line fix can still have impact 5.

## Consolidated finding register

| ID | Category | Finding | Impact | Current evidence and consequence | Required follow-up |
| --- | --- | --- | ---: | --- | --- |
| B2A-01 | Correctness, missing test | A sequence gap on a shared order-book SID invalidates only the ticker carried by the first post-gap message. | 5 | `normalize_capture_v3` records the scope as covering every requested ticker, but its gap branch changes only `market_state[ticker]`. The missing sequence could belong to any member of an unknown/shared domain. Other books can therefore remain falsely valid. | Invalidate every possibly affected market in the represented scope, record the affected membership explicitly, and add shared-scope gap tests where the missing event's market is unknowable. |
| B2A-02 | Schema parity, missing test | Record mode can publish a product-map V3 document that fails its own schema when a requested ticker never establishes `market_id`. | 5 | Runtime writes `market_ids.get(ticker)`, which can be `null`; the schema requires a non-empty string. Existing fixtures always establish every market ID before exercising incompleteness. | Decide whether incomplete product identity is representable or must refuse before publication. Align runtime and schema, then add a no-frame/no-market-ID one-defect test. |
| B2A-03 | Correctness, missing test | Missing source sequences do not make a capture incomplete. | 4 | Sequence validation is skipped when both the retained field and source message omit a sequence. A book delta can then contribute to `complete_observed_interval` without a usable mechanical continuity key. | Define sequence-required message types from primary protocol evidence. Refuse or mark incomplete when required sequence evidence is absent; test snapshot, delta, and trade cases separately. |
| B2A-04 | Schema parity, missing tests | The claimed schema/runtime parity is much narrower than the approved one-defect matrix. | 4 | Tests validate generated happy-path documents and one wrong metadata schema. Raw-record variants lack kind-specific `required` rules; source-scope sequence-domain shape and manifest reason/product-lineage shapes are loose. | Add discriminated schemas and one-defect negative tests for every affected format without tightening accepted legacy formats. |
| B2A-05 | Acknowledgement binding, missing tests | Offline normalization does not fully re-prove the live capture's acknowledgement invariants. | 4 | It does not verify `subscription_request_id` against the sent record and can accept two different SIDs for the same channel because final validation reduces channels to a set. | Require exactly one acknowledgement per expected channel/request, validate both request identities and declared membership, and test duplicate-channel/different-SID and string-ID mismatch defects. |
| B2A-06 | CLI, documentation, missing tests | Capture V2 completion and refusal semantics are ambiguous. | 4 | Protocol/data errors are recorded as connection gaps and retried. The command can reach its deadline, report shutdown `completed`, print metadata, and exit 0 while continuity is `incomplete`; ADR-013's generic expected-refusal code 2 does not explain this distinction. | Specify whether exit 0 means operational completion or usable data. Prefer a distinct additive diagnostic/status contract and test venue refusal, repeated acknowledgement mismatch, exhausted reconnects, and partial retained output. |
| B2A-07 | Protocol uncertainty | Venue sequence-domain scope remains unsupported by retained primary evidence. | 4 | Production truthfully records `unknown`, but the mechanical `(connection segment, SID)` key may be wider or narrower than the venue's actual domain. It can conservatively refuse valid data or localize a gap incorrectly. | Retain an official specification if one becomes available. Until then, treat every scope inference as mechanical and propagate uncertainty to all possible members. |
| B2A-08 | Missing test, completeness semantics | Disconnect-before-first-snapshot is not isolated in the corpus. | 4 | The current state machine converts `initial_snapshot` to `recovery_snapshot` on any gap. A later snapshot can yield `observed_discontinuous` even though no valid pre-gap segment existed, conflicting with the guide's definition of valid segments around a missing interval. | Decide whether this is incomplete prefix evidence or a discontinuous interval, encode the rule, and test connect failure, post-ack/pre-snapshot failure, and one-market-only initial snapshots. |
| B2A-09 | Downstream boundary | Feature and backtest consumers cannot read even complete normalized V3 data. | 4 | They correctly fail closed with `DownstreamContinuityRequired`; B2a is therefore a truth boundary, not yet a usable multi-market research path. | Keep refusal until B2b implements per-product, per-segment cursors and explicit incomplete-interval propagation. |
| B2A-10 | Scalability, optimization | Duplicate tracking grows linearly with every sequenced event. | 4 | `sequence_payloads` retains one hash for every `(scope, sequence)` for the full run. Streaming JSONL output therefore does not make normalization memory-bounded for long captures. | Measure on B2c evidence, then use a bounded policy justified by monotonicity or a disk-backed/content-indexed duplicate table. Preserve non-adjacent identical/conflicting duplicate semantics. |
| B2A-11 | Evidence, missing test | There is no retained long-duration, real reconnect regression. | 4 | Fake transports prove deterministic mechanics but not venue message diversity, rate limits, long-run resource use, or real reconnect cadence. | B2c should retain a reviewed local capture with pinned hashes/counts. Do not use a live sample to infer undocumented sequence scope. |
| B2A-12 | Unnecessary complexity, maintainability | Successor logic was appended to two already broad modules as large parallel code paths. | 3 | B2a added roughly 1,100 implementation lines; `kalshi_capture.py` is about 1,000 lines, `pmm_phase7.py` about 2,100, and `normalize_capture_v3` combines parsing, validation, state transitions, lineage, publication, and manifest assembly. | During B2a-1/B2b, extract new internal state machines and artifact writers behind frozen public adapters. Do not rewrite V1/V2 compatibility behavior merely for symmetry. |
| B2A-13 | Missing tooling, documentation | The public `inspect` command is V1-specific and cannot validate or summarize V2 scopes and discontinuities. | 3 | It reads `connection_id` and one metadata ticker, so operators must run normalization to understand a V2 capture. The operator guide does not call this limitation out. | Add an offline `inspect-v2` or version-dispatching inspector with no derived-output side effects; document its completeness vocabulary and exit contract. |
| B2A-14 | Missing tests | V3 ordering coverage does not isolate equal timestamps, timestamp/ingress tie boundaries, or V3 late events. | 3 | Repeated-byte and ingress-order tests exist, while the explicit late-time assertion remains on legacy normalization. Cross-scope equal-time cases are implicit rather than one-defect named tests. | Add named V3 cases for equal source times, equal receive times, source-time regression within one scope, global lateness across scopes, and receive-time fallback. |
| B2A-15 | Durability | Raw metadata is finalized in place and derived publication lacks file/directory fsync. | 3 | Raw frames are fsynced on close, but a crash can tear `metadata.json`; normalized output relies on rename without a complete durability protocol. This is adequate for local research, not durable operational capture. | Define atomic metadata snapshots and directory fsync with full-run recovery work. Preserve partial raw evidence rather than deleting it. |
| B2A-16 | Fidelity | Binary frames are counted and rejected without retaining their bytes. | 3 | The capture becomes incomplete, but forensic source fidelity is lost for the triggering frame. | Retain bounded base64 bytes or retain primary evidence that binary frames are impossible before making forensic-completeness claims. |
| B2A-17 | Determinism, portability | Manifest bytes depend on the input capture's repository-relative directory. | 3 | Identical input bytes normalize identically only when read from the same relative path. Moving the same capture changes `input_capture_directory` and therefore the manifest hash. | Decide whether the path is identity or annotation. Prefer content identity plus a non-hashed/local locator if location-independent reproduction is required. |
| B2A-18 | Scalability, partial failure | One request contains every ticker and both channels on one connection. | 3 | This is simple and deterministic, but has no declared ticker limit, batching, or per-market failure isolation. One malformed/unbound event reconnects the entire set. | Before large market sets, retain venue limits, design deterministic batching, and define cross-connection ingress ownership. Do not add multiple sockets ad hoc. |
| B2A-19 | Scalability, artifact size | Scope membership and gap evidence expand with market count and reconnect count. | 2 | Every scope repeats the full ticker list and every connection gap emits one discontinuity row per ticker, producing approximately `markets × reconnects` control data. | Measure first. If material, normalize request membership once and reference it; keep affected-market interpretation explicit. |
| B2A-20 | Optimization | Normalization rereads completed outputs for hashing and recopies immutable product packages. | 2 | This adds I/O but does not alter correctness at current fixture sizes. | Hash while writing and consider content-addressed reuse only after B2c measurements show value. |
| B2A-21 | Documentation | Protocol claims, refusal codes, and field semantics do not yet have one stable reference. | 3 | ADR-013 summarizes official behavior without durable citations; the guide has commands and layouts but no record-by-record field table or complete diagnostic inventory. | Add a B2a format/refusal reference with primary links or retained evidence status, examples, and compatibility guarantees. |
| B2A-22 | Minor complexity | `finalize_capture_v2_metadata` assigns the successful continuity string twice. | 1 | This has no runtime consequence but indicates the successor path needs a focused cleanup pass. | Remove it when B2a-1 edits the containing function; do not create a standalone commit solely for this line. |

## Requested-category summary

### Unnecessary complexity

The main avoidable complexity is structural, not conceptual. Version successors were necessary,
but placing capture V2 and normalization V3 beside legacy implementations in two monolithic files
created duplicated orchestration and made the new state machine harder to audit. Repeated scope
membership and per-market gap expansion also trade simple consumers for larger artifacts. The
right response is selective extraction around the successor path, not a broad legacy rewrite.

Highest relevant findings: B2A-12 (3), B2A-19 (2), and B2A-22 (1).

### Future technical debt

The largest debt is the mismatch between the intended truth contract and a few runtime/schema
edges: shared-scope gap propagation, incomplete identity representation, missing sequences, and
partial acknowledgement re-validation. Durability, portable manifest identity, and the lack of a
V2 inspector become more important once captures are retained or exchanged between machines.

Highest relevant findings: B2A-01 (5), B2A-02 (5), B2A-03 (4), B2A-05 (4), B2A-15 (3), and
B2A-17 (3).

### Missing tests

The test suite is broad but concentrated in happy-path generated documents and a few compound
mutations. Missing named one-defect cases include:

- a shared sequence gap whose missing market cannot be identified;
- a requested market with no frame and therefore no market ID;
- missing sequence on each sequenced message type;
- duplicate channel acknowledgements with distinct SIDs;
- mismatched logical `subscription_request_id` with a matching wire ID;
- disconnect before connect, acknowledgement, first snapshot, and after only one market snapshot;
- V3 equal-time and late-time tie boundaries;
- binary-frame retention/status behavior;
- repeated venue refusal through reconnect exhaustion;
- same input bytes at different repository-relative paths; and
- a measured large-event/large-market synthetic normalization.

These are B2A-01 through B2A-08, B2A-10, B2A-14, and B2A-17/18 in the register.

### Missing documentation

The conceptual ADR and explanation are strong, but operator and format references remain thin.
There is no V2 inspection guide, stable B2a refusal-code table, kind-by-kind raw/normalized record
reference, or durable primary-source citation for protocol assertions. The guide also needs to say
plainly that capture exit 0 can currently mean “the requested duration ended and raw evidence was
finalized,” not “the capture is complete enough to normalize strictly.”

Highest relevant findings: B2A-06 (4), B2A-13 (3), and B2A-21 (3).

### Possible optimizations

Optimization should follow correctness. The first meaningful optimization is bounding duplicate
state; the current normalizer streams files but still retains one hash per sequence. Hashing while
writing, content-addressed product-package reuse, and membership de-duplication are secondary.
None should land before B2A-01 through B2A-05 are correct and tested.

Highest relevant findings: B2A-10 (4), B2A-19 (2), and B2A-20 (2).

### Future scalability concerns

The single-connection/single-request model is a good B2a boundary, but it cannot simply be enlarged
indefinitely. Venue subscription limits, one-market faults affecting all markets, `markets × gaps`
control records, repeated membership, and linear duplicate memory will dominate before Python JSON
parsing itself. B2c should provide measurements before multiple sockets or a streaming rewrite is
designed.

Highest relevant findings: B2A-10 (4), B2A-11 (4), B2A-18 (3), and B2A-19/20 (2).

## What was done well

- Accepted capture, normalized, feature, configuration, result, and product-term artifacts were
  not reinterpreted.
- Raw ingress order is explicit and deterministic across incomparable scopes.
- Request ID, channel, SID, market membership, and reconnect segment are no longer collapsed.
- A reconnect snapshot starts a new segment and never repairs the missing interval.
- Identical and conflicting duplicates have different outcomes.
- Default downstream behavior fails closed.
- Synthetic tests remain labelled `Synthetic`; real-source conclusions remain Observed or
  Reconstructed as appropriate.
- Normalization removes partial derived output on interruption.
- No live capture, network-dependent test, execution claim, accounting claim, or risk/matching
  change entered B2a.

## Priority and bounded follow-up

1. **B2a-1 truth-boundary hardening:** close B2A-01 through B2A-06 and B2A-08 with one-defect
   offline tests and schema/runtime parity. This blocks B2b.
2. **B2b multi-market projection/features/replay:** consume only corrected scope membership and
   segment validity; retain `DownstreamContinuityRequired` until then.
3. **B2c retained full-capture evidence:** close B2A-10/11 with measured memory, counts, and hashes.
4. **Operational durability and inspection:** B2A-13/15/16/21 before capture is presented as an
   operationally durable or forensically complete tool.

The implementation still makes no queue, hidden-liquidity, venue-equivalent execution, fee,
accounting, settlement, paper-readiness, live-readiness, or profitability claim.

## B2a-1 closure review

B2a-1 closes B2A-01 through B2A-06 and B2A-08:

| Finding | Closure evidence |
| --- | --- |
| B2A-01 | Gap records separate the observed post-gap ticker from a sorted possible affected set; shared and unknown order-book scopes invalidate all possible members. |
| B2A-02 | Both continuity policies refuse before publication when any requested ticker lacks stable capture identity. |
| B2A-03 | Snapshots and deltas require integer sequence evidence; sequence-less trades remain valid under the documented public-trade shape. |
| B2A-04 | Runtime validates all seven successor schemas and the tests include generated positives and one-defect negatives. |
| B2A-05 | Offline normalization revalidates one canonical request, exact logical/wire identity, one acknowledgement per channel, membership, claim, and connection-local SID uniqueness. |
| B2A-06 | Capture metadata separates shutdown, continuity, and usability; exit zero is strict-eligible, while finalized record-only/unusable evidence exits two and remains retained. |
| B2A-08 | A gap before any valid snapshot preserves `initial_snapshot` state and incomplete-prefix classification rather than claiming recovered continuity. |

B2A-07 remains an honest protocol unknown: current official material documents order-book message
sequence fields but does not establish the comparison domain. Unknown topology therefore retains
conservative all-possible-member propagation. B2A-09 remains the intended B2b boundary. B2A-10
through B2A-22 remain deferred according to the roadmap; this package does not claim to close
inspection, durability, binary retention, portable identity, memory bounds, batching, long-capture
evidence, performance, or comprehensive public format-reference debt.
