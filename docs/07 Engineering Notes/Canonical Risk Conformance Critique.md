# Canonical Risk Conformance Critique

## Rating method

Impact rates the consequence if the issue remains: 1 is minor and 5 blocks trustworthy research.
Ease rates the expected containment of the next corrective increment: 1 is broad or externally
blocked and 5 is small and local. Priority favors correctness and claim discipline over convenience.

## Ingress-safety and fixture-integrity increment critique

This increment made one reservation-to-ingress invariant explicit, rejected zero fills, hardened
checkpoint validation, added a reviewed duplicate-ingress fixture, and made the standard test
script run the Python suite. It is useful foundation work, not the complete conformance milestone.

| Priority | Finding | Category | Impact | Ease | Why it matters | Recommended handling |
| ---: | --- | --- | ---: | ---: | --- | --- |
| P1 | The corpus still has only two fixtures and does not cover the approved rejection, ordering, kill-switch, or restore matrix. | Missing tests | 5 | 3 | Passing the current suite proves two paths, not lifecycle-wide parity. | Add the focused reviewed fixtures from the approved matrix before calling this complete conformance. |
| P1 | Checkpoint/restore has stronger direct C++ validation but no shared fixture protocol or Python-reference parity. | Missing tests / interface debt | 5 | 3 | Restore is precisely where a second implementation and serialized state need comparison. | Add the separate versioned, test-only checkpoint fixture harness; keep the V1 oracle frozen. |
| P1 | Direct C++ tests and Python fixture tests still encode scenarios separately. | Future technical debt | 4 | 3 | A future change can update one representation but omit the other. | Make a test-only C++ fixture executor consume the same reviewed fixture documents. |
| P2 | The Python oracle integration treats any oracle `ERROR` as a generic domain failure. | Unnecessary complexity / test precision | 3 | 4 | It proves unchanged state, but not a stable typed error contract. | Keep V1 behaviour as a transport regression; use typed fixture-harness results for the full suite. |
| P2 | `restore` reports the existing generic "duplicate client intents" message for several new invalid-checkpoint cases. | Future technical debt | 2 | 5 | Tests correctly use success/failure, but diagnosis is less clear. | Return stable checkpoint-validation categories only in the future test harness; do not make V1 error text a public contract. |
| P2 | The fixture manifest now has a payload hash and member hashes, but no standalone replay/verification command. | Missing documentation / tooling | 3 | 4 | Verification logic is embedded in unittest rather than reusable by a reviewer or CI job. | Add a small test-only verifier after the V2 corpus exists. |
| P3 | The test script invokes `uv`, so a developer without the managed uv cache receives an environment error before Python validation. | Operational friction | 2 | 4 | The standard project workflow uses uv, but the failure is environmental rather than a test failure. | Document `uv sync --locked`; keep cache permissions outside repository logic. |
| P3 | Full snapshots after every transition intentionally repeat live and pending records. | Future scalability concern | 2 | 3 | Trace size grows with open state times transitions. | Retain full snapshots for fixtures; consider verified compact deltas only after a replayer exists. |

### Debt order in plain language

1. **Finish the shared fixture matrix.** This is the highest-value missing proof.
2. **Add test-only checkpoint/restore parity.** It is the main remaining state-serialization gap.
3. **Make direct C++ consume the reviewed fixtures.** This removes duplicate scenario definitions.
4. **Add a reusable manifest/trace verifier.** It makes the current hash rules easier to audit.
5. **Optimize only after correctness coverage is complete.** Batching, caching, and compact traces
   are not justified before then.

## Findings

| Finding | Category | Impact | Ease | Why it matters | Recommended handling |
| --- | --- | ---: | ---: | --- | --- |
| V2 writes a Python-owned JSONL risk trace, but the oracle transport is still the unversioned whitespace protocol from V1. | Interface debt | 4 | 3 | The artifact is versioned, but request/response syntax, field escaping, and protocol capability are not. Calling the engine `v2` can overstate the boundary. | Specify and implement a versioned oracle request/response schema, or rename V2 as a runner/artifact migration until that protocol exists. |
| The trace contains aggregate risk view only; it omits canonical live-order and pending-reservation identities. | Auditability | 4 | 3 | A reviewer cannot independently confirm ingress correlation, individual remaining quantity, or reservation release from the trace alone. | Serialize stable live and pending records from `RiskCheckpoint` into trace state and add a trace replayer. |
| The only Python/C++ parity assertion covers the safe no-fill shared subset by comparing orders. | Correctness debt | 5 | 3 | It does not prove transition-by-transition equivalence for admission rejects, partial fills, command rejection, cancellation, expiry, or restore. | Add versioned fixtures with expected state after every operation and a test-only Python reference for the intentionally shared subset. |
| The V2 runner cannot exercise command rejection, kill switch, or checkpoint/restore through the oracle. | Lifecycle coverage | 4 | 3 | C++ supports these boundaries, but V2 research traces cannot demonstrate them. | Extend the oracle adapter only after its protocol is versioned; add dedicated fixture coverage before exposing those operations to experiments. |
| The V2 example uses `no_fill_v1` only. | Research coverage | 3 | 3 | This is the safe migration starting point, but it does not prove exact conversion and lifecycle behavior for `trade_touch_v1` fills. | Add a small synthetic integer-fill fixture before allowing a checked-in V2 trade-touch configuration. |
| The risk contract declares only whole contracts and cents, not product terms, lot rules, or a price grid. | Product-metadata debt | 5 | 2 | Risk can be internally consistent while accepting values that an actual venue contract would reject. | Ingest, hash, and validate explicit product terms before treating V2 results as broader than the fixed integer baseline. |
| The portable launcher rebuilds `pmm_risk_oracle` for every V2 run. | Unnecessary work | 2 | 4 | It is deterministic and safe, but slows parameter grids and couples a research run to local build availability. | Add a verified already-built mode keyed by target/source identity after correctness work is complete. |
| Exposure aggregation saturates its public quantity view at signed-int64 maximum if an impossible aggregate overflows. | Failure semantics | 3 | 2 | It prevents unsigned wraparound, but saturation hides the underlying invariant failure rather than reporting it. | Refactor aggregate/view construction to return `Result` and fail closed on impossible aggregate state. |
| Oracle I/O remains one synchronous subprocess request per risk lifecycle action. | Scalability | 3 | 3 | Dense multi-market replay will spend more time in pipes than risk arithmetic. | Batch trace operations or adopt a native binding only after profiling proves the need. |

| The initial fixture set covers the representative reserve-to-expiry path, but not every listed lifecycle and restore edge yet. | Coverage debt | 4 | 4 | The schema and complete trace are now exercised, but the fixture matrix still needs expansion before it is broad conformance evidence. | Add one focused fixture per admission rejection, invalid transition, command rejection, kill-switch case, and restore failure. |

## Missing tests

| Test | Impact | Ease | Acceptance condition |
| --- | ---: | ---: | --- |
| Full fixture-driven Python/C++ state parity | 5 | 3 | Every shared trace step has identical result, watermark, position, exposure, order, and reservation state. |
| V2 partial/full fill and expiry trace | 4 | 4 | Trace preserves remaining quantity through partial fill, full fill, and logical expiry. |
| V2 command rejection, kill-switch, and checkpoint/restore | 4 | 3 | Each operation is represented through the oracle and leaves the expected state. |
| Portable launcher failure matrix | 3 | 4 | Missing cache, failed build, malformed path file, target outside build directory, and dead child all fail without a final result directory. |
| Product-term conversion tests | 5 | 2 | Fractional lots, off-grid prices, and missing term hashes are rejected before admission. |
| Trace replayer and manifest tamper test | 4 | 3 | Modified trace/artifact hashes fail verification and valid traces reconstruct the recorded state. |

## Post-increment critique

Impact is the consequence of leaving the issue open; Ease is how contained the next corrective
increment should be.  Priority is impact first, then ease.

| Priority | Finding | Category | Impact | Ease | Recommended next action |
| ---: | --- | --- | ---: | ---: | --- |
| P1 | Only one fixture exercises the happy reserve/bind/acknowledge/partial-fill/expiry path. It does not yet cover every admission rejection, command rejection, bad ordering, kill switch, checkpoint/restore, or malformed fixture. | Missing tests | 5 | 4 | Add one small reviewed fixture per matrix row and require both direct C++ and Python-oracle parity for each transition. |
| P1 | The Python reference implements only the first path and does not yet model configured limits, command rejection, checkpoint/restore, or invalid transition cases. | Coverage debt | 5 | 3 | Expand it only alongside fixture cases; reject any operation not deliberately admitted to the shared subset. |
| P1 | The V2 trace is complete, but the oracle request transport remains the unversioned whitespace protocol. `SNAPSHOT` and `KILL` add capability without a formal request/response schema. | Interface debt | 4 | 3 | Define a separate versioned local protocol before adding more lifecycle commands to research orchestration. Keep V1 frozen. |
| P2 | Snapshot JSON is manually streamed in C++. Its fields are numeric or fixed enums today, but hand-written serialization will become fragile if arbitrary strings are added. | Technical debt | 3 | 4 | Keep the payload closed; introduce a tested canonical JSON serializer before any free-form field is added. |
| P2 | The fixture manifest hashes members, but has no independently stored hash of its own payload and no trace-tamper verifier yet. | Auditability | 4 | 4 | Add a manifest-payload digest and a trace replay/verification command that fails on a changed byte. |
| P3 | The oracle is still synchronously queried for a snapshot after every lifecycle transition. This is correct for conformance but expensive for dense replay. | Scalability | 3 | 3 | Keep it in tests; batch operations or add a native binding only after profiling production-sized replay. |
| P3 | Full trace rows retain complete order and reservation records. This is intentionally auditable but grows with open state times transitions. | Scalability | 2 | 3 | Stream trace writes and consider periodic full checkpoints plus compact deltas only after retaining a full-fixture replay oracle. |

## Missing documentation

| Gap | Impact | Ease | Required addition |
| --- | ---: | ---: | --- |
| No formal V1 local-oracle command reference, including `SNAPSHOT` and `KILL`. | 4 | 4 | Document grammar, response forms, failure semantics, and its explicit non-production status. |
| No machine-readable complete trace schema reference. | 4 | 4 | Publish field types, sort order, and compatibility rules for `pmm.risk_conformance_trace.v2`. |
| No fixture authoring guide. | 3 | 5 | Explain fixture/expected-trace/manifest layout, reviewed-answer policy, and the shared-versus-C++-only boundary. |

## Possible optimizations

- Add a fixture loader that drives direct C++ tests from the same reviewed inputs rather than only
  Python-oracle integration.
- Stream and hash `risk-trace.jsonl` while writing it instead of retaining the whole trace in memory.
- Batch a fixture's oracle operations after the transport is versioned; do not weaken
  transition-by-transition assertions.
- Use compact deltas only after a replayer proves they reconstruct the same complete state.

## Missing documentation

- A formal oracle transport specification, including exact V1 limitations and the intended V2 replacement.
- A trace-state schema that declares which data is sufficient for independent replay.
- A migration matrix for each legacy V1 experiment and its eligibility for C++ risk.
- Product-term and unit-conversion policy documentation.
- A result-comparison policy for manifests with different risk contracts or execution models.

## Possible optimizations and scalability concerns

- Stream orders, fills, ledger, and trace records instead of retaining all records in Python lists.
- Replace the sorted scheduled-decision list with a stable heap after a benchmark demonstrates need.
- Batch oracle commands or use a native binding after trace correctness is demonstrated.
- Cache a verified built oracle by CMake target and source identity rather than invoking a build for every run.
- Incrementally hash artifacts while writing them to avoid a second full read on large outputs.

## Priority order

| Priority | Work | Impact | Ease | Reason |
| ---: | --- | ---: | ---: | --- |
| P0 | Preserve `ModelDerived` labels and the no-PnL/non-execution claims. | 5 | 5 | Prevents unsupported research conclusions immediately. |
| P1 | Add full fixture-driven parity and complete trace state. | 5 | 3 | Closes the remaining Python/C++ transition-drift gap. |
| P2 | Add product terms, lot/price validation, and compatibility hashes. | 5 | 2 | Required before widening the fixed integer baseline. |
| P3 | Version the oracle transport and cover remaining lifecycle operations. | 4 | 3 | Makes the local adapter an auditable interface rather than a convention. |
| P4 | Add trace replay/tamper validation and result comparison. | 4 | 3 | Turns artifacts into independently checkable evidence. |
| P5 | Batch/stream/cache only after benchmark evidence. | 3 | 3 | Important for scale, but not ahead of correctness. |

## Retained non-claims

This work still does not establish calibrated fills, queue priority, venue-equivalent execution,
PnL correctness, collateral, settlement, durable full-run recovery, paper trading, or live
readiness.

## Lifecycle-matrix follow-up

The reviewed V1 corpus now closes the lifecycle-matrix coverage gap for every transition the
frozen local adapter can faithfully express. The remaining P1 boundary is deliberately separate:
versioned checkpoint/restore fixtures, including a serialization contract and invalid-checkpoint
categories. This increment does not expand the V1 whitespace adapter.

## Post-matrix implementation critique

### Rating method

Impact is the consequence of leaving an issue unresolved: 1 is minor and 5 blocks trustworthy
conformance evidence. Ease is how contained the next corrective increment should be: 1 is broad
or externally blocked and 5 is small and local. Priority favors correctness and clear claims over
convenience.

| Priority | Finding | Category | Impact | Ease | Why it matters | Recommended handling |
| ---: | --- | --- | ---: | ---: | --- | --- |
| P1 | Direct C++ unit tests do not yet execute the same reviewed fixture documents as Python and the V1 oracle. | Missing test / future debt | 5 | 3 | The oracle proves the C++ projection through its adapter, but a direct API change can still leave the corpus and direct-unit surface out of sync. | Add a strict test-only C++ fixture reader/executor before calling direct-C++ fixture parity complete. |
| P1 | The frozen V1 adapter reports lifecycle failures as generic `ERROR`; the integration asserts rejection shape but not the numeric admission code. | Missing test precision | 4 | 4 | A wrong C++ admission category could still look like a generic rejection to this test. | Map the existing numeric `AdmissionRejectCode` values in the test adapter only; do not make error prose public API. |
| P2 | Fixture schema validation is deliberately small and currently lives in unittest helpers. | Future technical debt | 3 | 4 | It rejects unknown operations and malformed high-level shape, but it is not yet a reusable strict verifier for every field, unit, or path rule. | Extract a test-only verifier with field-level diagnostics and a documented command after the direct-C++ fixture executor exists. |
| P2 | Reviewed traces are one-line canonical JSON documents. | Unnecessary review friction | 3 | 4 | Byte stability is good, but human review of a large complete snapshot is awkward. | Keep canonical files authoritative; add a read-only pretty-print or trace-summary helper for reviewers. |
| P2 | The test-only Python reference now reproduces configured limit arithmetic. | Future technical debt | 3 | 3 | It is intentional independent evidence, but every added shared operation increases drift risk. | Extend it only with a reviewed fixture and explicit unsupported-operation failure; never import it into production or backtest code. |
| P3 | The oracle process is launched per fixture and receives a snapshot after every transition. | Possible optimization / scalability concern | 2 | 3 | Correctness fixtures are small today, but dense corpora pay process and JSON I/O overhead repeatedly. | Keep the exact transition assertions; batch only after a versioned transport or profiling evidence. |
| P3 | Full snapshots repeat open order and reservation records after every operation. | Future scalability concern | 2 | 3 | The records are the audit value of the corpus, but trace size grows with open state times transitions. | Retain complete fixtures; consider verified compact deltas only after a replayer proves equivalence. |

### Debt order in plain language

1. **Make direct C++ consume the reviewed fixtures.** This is the largest remaining gap because
   it removes a second scenario representation.
2. **Check V1 admission categories exactly.** This is contained work that strengthens the frozen
   adapter without extending it.
3. **Turn schema checks into a reusable test-only verifier.** That makes malformed-input failures
   easier to audit and diagnose.
4. **Improve reviewer ergonomics, not fixture semantics.** Pretty output can help humans while
   canonical one-line bytes remain the hashable source of truth.
5. **Optimize only after the correctness boundary is complete.** Process batching and compact
   traces should not weaken state-after-every-transition proof.

## Direct-C++ fixture closure critique

The final lifecycle-conformance increment removes the duplicate scenario representation: direct
C++ now consumes the same reviewed documents as the Python reference and every V1-compatible
oracle case. Its strict test-only verifier checks byte canonicality, schema shape, member and
payload hashes, path safety, complete state consistency, and executor eligibility before replay.

The V1 admission response now has exact numeric category coverage. Generic non-admission `ERROR`
responses intentionally remain shape-and-state assertions rather than text comparisons.

The remaining consequence is deliberately narrow: checkpoint/restore still lacks a versioned
fixture contract. It is not a hidden extension of this corpus and must be designed separately.

## Post-closure critique

### Rating method

Impact measures the consequence of leaving an issue open: 1 is minor and 5 blocks trustworthy
conformance evidence. Ease measures how contained the corrective increment is: 1 is broad or
externally blocked and 5 is small and local. Priority favors impact, then ease; it does not turn a
deliberately deferred boundary into implied current support.

| Priority | Finding | Category | Impact | Ease | Why it matters | Recommended handling |
| ---: | --- | --- | ---: | ---: | --- | --- |
| P1 | Checkpoint/restore has no reviewed, versioned fixture contract. | Future technical debt / missing test | 5 | 2 | Lifecycle conformance is now direct-C++ complete for V1, but serialized risk state still has no shared proof. | Design a separate test-only schema, restore-validity matrix, and C++-only executor boundary before implementing it. Do not add it to V1. |
| P2 | The C++ verifier has one tampered-byte regression test, not a full negative matrix for every declared failure category. | Missing tests | 4 | 4 | Path traversal, symlinks, bad payload hashes, unknown fields, invalid decimals, duplicate members, and inconsistent totals are checked in code but not each independently protected by a test. | Add focused temporary-corpus tests, one per verifier category, including the diagnostic path. |
| P3 | The test-only SHA-256 implementation has no known-answer-vector tests. | Future technical debt / missing test | 3 | 5 | Corpus hashes exercise it indirectly, but a shared wrong implementation and wrong expected value would be hard to diagnose. | Add empty-string, `abc`, and a multi-block known-answer test; keep the implementation test-only. |
| P4 | C++ and Python independently encode much of the fixture schema. | Future technical debt | 3 | 3 | Independence gives useful cross-checking, but a future schema addition can be accepted by one surface and rejected by the other. | Keep separate parsers, but add a concise versioned schema table and a shared malformed-corpus test matrix in documentation. |
| P5 | The test-only JSON dependency is fetched during a fresh CMake test configuration. | Unnecessary complexity / operational debt | 3 | 3 | It preserves production boundaries, but offline or restricted environments cannot bootstrap this new target without a populated dependency cache. | Document the dependency and cache requirement; consider a source archive with a verified digest only if offline test bootstrapping becomes a demonstrated need. |
| P6 | V1 exposes numeric categories only for admission failures; other domain failures remain generic `ERROR`. | Interface debt | 3 | 2 | State assertions prove rejection safety, but cannot distinguish non-admission failure classes through the adapter. | Keep V1 frozen. Address this only in a separately versioned local protocol, not through error-text assertions. |
| P7 | The verifier reads each document into memory and reparses member bytes after hashing; tests reload the corpus in multiple cases. | Possible optimization / future scalability concern | 2 | 4 | The checked-in corpus is tiny, but large future fixtures would repeat I/O and retain full JSON DOMs. | Cache a verified corpus per test process or stream hashes only after profiling; preserve byte and transition assertions. |
| P8 | Canonical one-line JSON remains difficult to inspect manually. | Missing documentation / review ergonomics | 2 | 4 | Hashable bytes are intentional, but reviewers must mentally parse long complete-state records. | Add a read-only pretty-printer or trace summary that never rewrites authoritative files. |
| P9 | The fixture guide does not yet specify the complete V1 oracle command grammar or the V2 trace schema. | Missing documentation | 3 | 4 | The guide explains fixture ownership, but an external reviewer still lacks a single command and trace reference. | Document V1 as a limited local adapter and publish a machine-readable trace-field reference without expanding either interface. |

### Debt order in plain language

1. **Design checkpoint/restore separately.** It is now the largest remaining correctness boundary,
   but must not be smuggled into V1.
2. **Test every strict-verifier rejection path.** The parser already rejects them; focused negative
   tests make that promise durable and are contained work.
3. **Prove the SHA helper with standard vectors.** This is cheap confidence for the evidence chain.
4. **Keep the two independent readers aligned through documentation.** Do not merge them into one
   production-like abstraction; maintain a small explicit schema matrix instead.
5. **Improve developer ergonomics only after correctness.** Offline bootstrap, pretty output,
   caching, and streaming are worthwhile only when their costs are observed.

## Checkpoint-conformance increment critique

Impact measures the consequence of leaving an issue open: 1 is minor and 5 blocks trustworthy
conformance evidence. Ease measures how contained the corrective increment is: 1 is broad or
externally blocked and 5 is small and local. Priority favors impact, then ease.

This increment closed the former P1: serialized risk state now has a versioned corpus, a
byte-exact capture contract, a dual-run restore proof, typed rejection categories, and a
per-rule negative matrix in both C++ and Python. The remaining debt is narrower.

| Priority | Finding | Category | Impact | Ease | Why it matters | Recommended handling |
| ---: | --- | --- | ---: | ---: | --- | --- |
| P1 | Checkpoint conformance proves in-memory round-trips only; risk state has no durable persistence boundary, unlike the exchange WAL. | Non-claim discipline / future work | 4 | 2 | A reader could over-generalize passing fixtures into recovery claims. | Keep the non-claims explicit; design risk-state durability as its own increment with its own failure matrix. |
| P2 | The limit arithmetic now exists three times: production C++, the direct C++ executor's expectations, and the Python reference. | Future technical debt | 4 | 3 | A future limit change can be applied to two surfaces and missed in the third. | Change limits only through a reviewed fixture that all executors must pass; never merge the readers into one abstraction. |
| P2 | Checkpoint documents duplicate identity and limits that roundtrip fixtures also imply. | Unnecessary complexity | 2 | 4 | The verifier enforces agreement, but authors write the same values twice. | Keep the redundancy: an explicit restore input is worth the authoring friction; revisit only if the corpus grows large. |
| P3 | The corpus is single account, single contract; portfolio-level checkpoint composition is undesigned. | Coverage debt | 3 | 2 | Multi-account recovery semantics cannot be inferred from this schema. | Treat portfolio checkpoints as new design work, not a schema extension. |
| P3 | The `checkpoint_*` first-failure order is now load-bearing for fixtures. | Interface debt | 3 | 4 | Reordering validation in C++ silently changes reviewed answers. | The order is documented in the header and guide and pinned by an ordering fixture plus unit test; change it only with a reviewed corpus update. |
| P4 | The negative matrix is enumerated, not generative; there is no fuzz or property testing of either reader. | Missing tests | 2 | 3 | A parser defect outside the enumerated categories could survive. | Consider a small structured fuzzer only after the enumerated matrix has proven insufficient. |

### Debt order in plain language

1. **Do not let round-trip evidence become a recovery claim.** Durable risk-state persistence is
   separate future work with its own design gate.
2. **Guard the triplicated limit arithmetic with fixtures.** Every limit-rule change must arrive
   with a reviewed fixture that all three surfaces replay.
3. **Leave the redundant identity/limits in documents.** Explicit restore inputs beat implicit
   context, and the verifier already enforces consistency.
4. **Treat validation order as part of the contract.** It is documented and pinned; reordering is
   a corpus change, not a refactor.
5. **Fuzz only if the enumerated matrix proves insufficient.** Correctness coverage is currently
   explicit and reviewable; keep it that way until evidence demands more.

## Checkpoint implementation post-review

This review examines the shipped implementation rather than the design. Impact rates the
consequence of leaving the issue open: 1 is minor and 5 blocks trustworthy conformance evidence.
Ease rates how contained the corrective increment is: 1 is broad or externally blocked and 5 is
small and local. Priority favors impact, then ease.

| Priority | Finding | Category | Impact | Ease | Why it matters | Recommended handling |
| ---: | --- | --- | ---: | ---: | --- | --- |
| P1 | `restore` never checks the per-order `maximum_order_quantity`; a checkpoint can restore a live order or reservation whose quantity admission would have rejected, as long as aggregate exposure fits. This preserves pre-existing behavior and both implementations agree, but restored state is not guaranteed to be admission-reachable. | Future technical debt | 4 | 4 | A checkpoint is trusted input; state that could never be created through admission weakens the claim that restore returns the system to a previously legal configuration. | Decide whether restore must enforce admission-time per-record limits. If yes, add a `checkpoint_order_quantity_limit` category, corpus rows, and a Python-reference update in one reviewed increment; do not change behavior silently. |
| P2 | The strict rules for reviewed captured checkpoints (strictly sorted records, positive quantities, post-only, nonzero ingress, identity/limits equal to the fixture) have no negative tests; only lax-input rules are covered by the mutation matrix. | Missing tests | 3 | 5 | A regression that stops enforcing strict-capture rules would go unnoticed until a bad reviewed document was checked in. | Add temporary-corpus tests that tamper a trace's captured checkpoint: wrong limits, wrong identity, unsorted records, zero quantity, `post_only` false. |
| P2 | The test-only SHA-256 still has no known-answer vectors, and two corpora now depend on it. | Missing tests | 3 | 5 | A shared wrong implementation and wrong recorded hash remain mutually consistent and undetectable. | Add empty-string, `abc`, and multi-block vector tests; this closes a critique item open since the direct-C++ closure. |
| P2 | The corpus generator was a throwaway script; adding or editing a fixture now requires hand-computing canonical bytes and three hashes with no documented workflow or checked-in helper. | Missing documentation / tooling | 3 | 4 | Authoring friction invites ad-hoc scripts that may not reproduce canonical bytes exactly, and the manifest must be regenerated correctly every time. | Check in a small authoring/rehash helper under `tools/` or document the exact canonicalization and hashing recipe in the fixture guide. |
| P3 | `pmm.risk_checkpoint.v1` now has three encoders: the C++ test serializer, the Python `capture`, and whatever authored the corpus. The two executor encoders are intentional independent evidence; the third is not. | Unnecessary complexity | 3 | 3 | A schema change must be applied identically in three places; the byte-equality assertions catch drift between the executors but not in offline authoring. | Fold authoring into the checked-in helper above so exactly two independent encoders remain, both exercised by tests. |
| P3 | The Python negative matrix covers nine reader rules; C++ covers seventeen, including symlinks, duplicate members, decreasing identifiers, wrong schema strings, and continuation-after-rejection. | Missing tests | 2 | 4 | The Python validator is secondary evidence, but its untested rules can silently rot. | Mirror the remaining categories with the existing `_mutated_corpus_fails` helper; each is a few lines. |
| P3 | The default limits quintuple (5,5,5,5,5,4) is independently hardcoded in the C++ `Limits` struct, `ReferenceRisk`, the Python fixture-defaults helper, and the corpus documents. | Unnecessary complexity | 2 | 4 | A default change is a four-file edit where missing one produces confusing distant failures. | Acceptable while frozen; if defaults ever change, drive all four from one reviewed fixture change and verify corpus failures point at the right file. |
| P3 | The README's ADR-009 paragraph does not mention checkpoint conformance, and the result-string vocabularies are duplicated as literal sets in C++ and Python. | Missing documentation | 2 | 5 | Discoverability and one more drift surface, both cheap to fix. | Add one README sentence; keep the vocabularies literal but note them in the fixture guide as the authoritative list. |
| P4 | Every test reloads and re-verifies the full corpus, and each negative test copies the whole corpus directory. | Possible optimization | 1 | 3 | Currently well under a second in total; caching would complicate isolation between mutation tests. | Leave as is until the corpus is large enough to measure. |
| P4 | The dual-run executor re-serializes both complete checkpoints after every post-restore transition, and the single sorted manifest is a merge hot-spot as the corpus grows. | Future scalability concern | 2 | 3 | Cost grows with open state times transitions, and parallel fixture authoring will conflict on `manifest.json`. | Keep the per-transition byte assertions; consider per-fixture manifest shards only if authoring contention actually occurs. |

### Debt order in plain language

1. **Decide whether restore must be admission-reachable.** This is the only finding that touches
   risk semantics: today a checkpoint may legally contain an order too large to ever admit.
2. **Test the strict-capture rules and the SHA helper.** Both are cheap, local tests that make
   existing promises durable instead of implicit.
3. **Check in the fixture-authoring workflow.** The corpus is only maintainable if canonical
   bytes and hashes can be regenerated the same way every time.
4. **Close the small drift surfaces.** Mirror the remaining Python negative tests and note the
   duplicated defaults and vocabularies where reviewers will look.
5. **Do not optimize yet.** Corpus loading and dual-run serialization are measured in
   milliseconds; correctness assertions must not be weakened for speed that nobody needs.

## Admission-reachable checkpoint restore critique

This review covers the completed per-record quantity increment. Impact rates the consequence of
leaving an issue open from 1 (minor) to 5 (blocks trustworthy evidence). Ease rates how contained
the correction is from 1 (broad or externally blocked) to 5 (small and local).

The former P1 semantic gap is closed: both live remainders and pending reservations must now be no
larger than `maximum_order_quantity`, the boundary is accepted, and direct C++ plus the independent
Python reference agree on the same reviewed result and first-failure order. The implementation adds
one enum value and two comparisons; no new abstraction or production dependency was needed.

During focused validation, the old buy, sell, and pending aggregate fixtures revealed that each
used one quantity-six record under a quantity-five per-order limit. Their expected aggregate result
had depended on the old missing check. They now use two individually legal quantity-three records,
so each aggregate fixture proves its named rule without relying on a semantic hole.

| Priority | Finding | Category | Impact | Ease | Why it matters | Recommended handling |
| ---: | --- | --- | ---: | ---: | --- | --- |
| P1 | Strict captured-checkpoint rules still lack focused negative tests. | Missing tests | 3 | 5 | Sorted records, matching identity/limits, positive quantities, post-only intent, and nonzero ingress are enforced by readers but not independently pinned. | Add temporary-corpus mutations for each strict-only rule in the next package. |
| P1 | The test-only SHA-256 implementation still lacks standard known-answer vectors. | Missing tests | 3 | 5 | Two corpora trust it indirectly; a shared incorrect digest and expected value would remain hard to diagnose. | Add empty-string, `abc`, and multi-block vectors alongside the strict-capture tests. |
| P2 | Adding five fixture pairs required manual canonical bytes and manifest rehashing. | Future technical debt / missing documentation and tooling | 3 | 4 | The process is deterministic but easy to repeat inconsistently as the corpus grows. | Keep a fixture-authoring/rehash helper as a separate increment after the two correctness tests. |
| P3 | The rejection vocabulary and limit arithmetic remain duplicated across C++ and Python. | Unnecessary complexity / future technical debt | 2 | 4 | Independent implementations are valuable evidence, but every semantic addition requires coordinated literal updates. | Continue requiring reviewed fixtures through both executors; do not merge the test-only model into production code. |
| P3 | Python still covers fewer reader-mutation categories than C++. | Missing tests | 2 | 4 | Semantic parity is complete for this increment, but secondary reader checks can still drift. | Mirror the remaining reader mutations separately; do not mix them into this semantic commit. |
| P4 | Every conformance test reloads the corpus, and mutation tests copy it repeatedly. | Possible optimization / future scalability concern | 1 | 3 | The 26-document corpus remains fast, so caching would currently add more state and complexity than value. | Leave unchanged until measured runtime makes caching worthwhile. |

### Debt order after this increment

1. Add strict captured-checkpoint negative tests.
2. Add SHA-256 known-answer vectors in the same cheap correctness package.
3. Make fixture authoring and rehashing reproducible with checked-in tooling or an exact recipe.
4. Close remaining Python reader-mutation parity.
5. Defer vocabulary cleanup and corpus-loading optimization until they create observed cost.

### Retained limitations

This increment proves a necessary admission-derived quantity invariant only. It does not prove a
complete historical lifecycle, durable persistence, process restart, portfolio recovery, or
multi-account recovery, and it changes no claim about fills, queue priority, execution realism,
PnL, collateral, settlement, paper trading, or live readiness.

## Strict capture and SHA implementation critique

This review covers the completed strict-capture mutation matrix and SHA-256 vectors. Impact rates
the consequence of leaving an issue open from 1 (minor) to 5 (blocks trustworthy evidence). Ease
rates how contained the correction is from 1 (broad or externally blocked) to 5 (small and local).

The two former P1 test gaps are closed. C++ and Python now independently reject 16 one-defect
captured checkpoints after their integrity metadata has been recomputed, and every row checks the
intended diagnostic path. Separate identity and limit rows protect every comparison rather than
using one representative value. The C++ hash helper independently matches three standard vectors,
including a multi-block input. No production code, schema, reviewed fixture, or dependency changed.

The table-driven form adds a small amount of test-local indirection, but keeps the full contract in
one place per language and avoids 32 repeated test bodies. The focused C++ selection remained
under one second during implementation, so corpus caching or a narrower parser-only hook would add
complexity without measured value.

### Assessment of the design itself

The implementation has two kinds of duplication, and they should not be treated the same way.
Repeating the strict matrix in C++ and Python is intentional independence: one reader cannot make
the other reader pass. Repeating temporary-directory setup, canonical writing, and rehashing inside
every individual test would have been accidental complexity, so those mechanics stay in one helper
per language. The chosen table is the middle ground: the rules remain visible while the machinery
is shared.

The main brittleness is not the table; it is how the donor checkpoint is addressed. Both tests use
transition index 5 because that is where `roundtrip_live_and_pending` currently captures state. A
future edit that inserts an operation before the checkpoint could make the mutation test fail for
an indexing reason rather than a strict-rule regression. This is contained test debt, not a flaw in
checkpoint semantics. A future cleanup should locate the unique `checkpoint` operation from the
fixture and use its matching transition, while still asserting that exactly one donor capture was
found.

Diagnostic matching also has a deliberate tradeoff. Field-path assertions prevent a generic hash
or schema failure from satisfying the test, but the C++ rows currently include short prose such as
`must equal the fixture limits`. Improving that prose would require a test update even when reader
behavior is unchanged. The tests should continue to require the stable field path; if diagnostic
wording begins changing frequently, separate the path from the explanatory message rather than
weakening the assertion to any exception.

| Priority | Finding | Category | Impact | Ease | Why it matters | Recommended handling |
| ---: | --- | --- | ---: | ---: | --- | --- |
| P1 | Fixture authoring and permanent rehashing still have no checked-in helper or exact command. | Future technical debt / missing tooling | 3 | 4 | The temporary test helper is deliberately private to tests and does not make reviewed corpus edits reproducible for an author. | Keep the fixture-authoring/rehash helper as the next separate correctness-support increment. |
| P2 | C++ and Python duplicate the 16-row strict mutation contract. | Unnecessary complexity / future drift risk | 2 | 3 | Independence is useful evidence, but a future strict field addition must update both tables. | Document every new strict field in this guide and require a named row in both readers; do not merge the implementations. |
| P2 | Both matrices hard-code donor transition index 5. | Future technical debt / maintainability | 3 | 4 | Inserting an operation before the capture could redirect or break every mutation without changing the strict contract. | Resolve the capture transition from the donor's `checkpoint` operation and assert that the donor has exactly one capture. |
| P2 | Python still lacks parity for several unrelated reader mutations already covered in C++. | Missing tests | 2 | 4 | Strict-capture parity is complete, but symlink, duplicate-member, wrong-schema, and continuation categories can still drift. | Close the remaining reader-mutation parity in its own package without changing checkpoint semantics. |
| P2 | SHA coverage does not enumerate adjacent padding and block boundaries such as 55, 63, 64, and 65 input bytes. | Missing tests | 2 | 5 | The required empty, short, and 56-byte multi-block vectors exercise the algorithm well, but an off-by-one defect outside those lengths could remain. | Add a small boundary-vector table only if the helper changes; property or fuzz testing remains a separate lower-priority package. |
| P2 | C++ diagnostics are asserted partly through human-readable prose. | Future technical debt / diagnostic coupling | 2 | 4 | A wording-only improvement can break the mutation test even though the rejection path remains correct. | Preserve field-path matching; split structured location from prose if diagnostic churn becomes real. |
| P2 | The fixture guide explains canonical bytes and hashes but still gives no exact authoring and verification command. | Missing documentation | 3 | 4 | A reviewer can understand the contract but cannot reproducibly regenerate a deliberately edited corpus using a checked-in workflow. | Document the command together with the future authoring/rehash helper, not as an ad hoc shell recipe. |
| P3 | Each strict row copies and verifies the complete 26-fixture corpus. | Possible optimization / future scalability concern | 1 | 3 | Isolation is valuable and current runtime is small; the cost will grow linearly if the corpus becomes much larger. | Retain full isolation until profiling shows material test cost, then consider a verified base copy or parameterized fixture cache. |
| P3 | Identity failures share one C++ diagnostic and limits share another. | Diagnostic precision | 1 | 4 | Named rows identify the failed comparison in tests, but the loader's prose does not name the exact identity or limit field. | Leave unchanged unless fixture-authoring failures become difficult to diagnose; changing test-only prose is not required for correctness. |
| P3 | One sorted manifest and canonical one-line traces remain review and merge hot spots. | Future scalability / review ergonomics | 2 | 3 | More fixtures increase line length, merge conflicts, and the cost of manually locating one changed transition even though runtime remains small. | Keep canonical files authoritative; add a read-only summary or pretty-printer before considering manifest sharding. |
| P4 | `std::function` mutations in C++ and dynamically traversed paths in Python are more abstract than explicit test bodies. | Unnecessary complexity | 1 | 4 | A new contributor must understand the table machinery before reading one case, but the alternative is 32 repetitive bodies. | Keep the tables small and local; do not extract a general mutation framework. |

### Debt order after this increment

1. Make permanent fixture authoring and rehashing reproducible, including an exact documented
   command.
2. Remove the hard-coded donor transition index without creating a general mutation framework.
3. Close remaining Python reader-mutation parity as a separate test package.
4. Preserve the duplicated strict matrix as independent evidence, updating both sides together.
5. Add SHA boundary vectors only when the helper changes or evidence reveals a need.
6. Defer corpus caching, manifest sharding, parser exposure, and serialization optimization until
   runtime or authoring contention is measured as a problem.

### Category summary

- **Unnecessary complexity — impact 2/5 overall.** The duplicated language-level matrix is mostly
  justified independent evidence. The table machinery itself is impact 1/5 and should remain
  local rather than becoming a framework.
- **Future technical debt — impact 3/5 overall.** The hard-coded capture index and absent permanent
  authoring workflow are the most concrete maintenance risks.
- **Missing tests — impact 2/5 overall.** Required strict rules and standard SHA vectors are
  covered. Remaining gaps concern secondary reader parity and additional hash boundary lengths.
- **Missing documentation — impact 3/5 overall.** The evidence contract is explained, but corpus
  authors still lack one reproducible checked-in regeneration command.
- **Possible optimizations — impact 1/5 overall.** Current focused runtime is below one second;
  caching would presently cost more clarity than it saves.
- **Future scalability concerns — impact 2/5 overall.** Full-corpus copies, one-line traces, and a
  single manifest grow linearly, but none is a measured bottleneck at 26 fixtures.

### Retained limitations

This increment proves that reviewed captures obey the existing strict reader contract and that the
test-only C++ digest helper matches standard SHA-256. It does not turn checkpoint JSON into a
production persistence format or establish durable storage, WAL integration, process restart,
portfolio or multi-account recovery, calibrated fills, queue priority, execution realism, PnL,
collateral, settlement, paper trading, or live readiness.

## Fixture integrity workflow implementation critique

This review covers the checked-in canonicalization and rehash command. Impact rates the consequence
of leaving a finding open from 1 (minor) to 5 (blocks trustworthy evidence). Ease rates how
contained its correction would be from 1 (broad or externally constrained) to 5 (small and local).

The former top tooling gap is closed. Both corpora now share one standard-library-only command,
verification is read-only by default, writing is explicit, unsafe corpus structure is refused, and
member plus payload digests are reproduced without invoking any risk implementation. Focused tests
prove checked-in no-op behaviour, stale-hash repair, repeated byte identity, semantic-answer
preservation, concurrent-edit refusal, and fail-closed recovery after an injected manifest-write
failure.

### Assessment of the design

The most important choice is that the helper validates only the shared integrity envelope. It can
therefore preserve and hash a semantically wrong expected answer. That is not missing validation;
it is what keeps human-reviewed evidence separate from an implementation blessing its own output.
The documented workflow must continue to pair `--write` with the existing C++ and Python semantic
tests.

The writer duplicates the small canonical JSON expression from `pmm_phase7.canonical_json` rather
than importing the large replay module. This avoids coupling a developer integrity tool to Phase-7
runtime code. A focused test requires byte equality with the existing function, and the independent
C++ readers verify the checked-in results. The duplication is six stable serialization options,
not a third checkpoint encoder.

Per-file atomic replacement plus manifest-last ordering is intentionally weaker than a corpus-wide
transaction. A crash between replacements may leave a member updated under an old manifest, but it
cannot create a half-file or a falsely valid corpus: the stale manifest is rejected. Directory
swaps, recovery markers, or rollback journals would add persistence machinery to a small checked-in
test workflow without improving the truth of its semantic evidence.

| Priority | Finding | Category | Impact | Ease | Why it matters | Recommended handling |
| ---: | --- | --- | ---: | ---: | --- | --- |
| P1 | Authors must still run semantic conformance tests after `--write`; the integrity command intentionally accepts reviewed values without deriving their truth. | Documentation / workflow risk | 3 | 5 | A hash-correct expected trace can still contain the wrong result or state. | Keep the warning beside every authoring command and retain the test that proves a wrong semantic answer is preserved. |
| P1 | The public CLI contract is exercised manually but not through a subprocess test that pins exit codes, standard output, standard error, and `--write` dispatch. | Missing tests | 2 | 5 | The core functions can pass while an argument-parser or return-code regression makes the documented command misleading in CI or review. | Add one temporary-root-capable CLI seam or a narrowly patched subprocess test; keep arbitrary corpus paths unavailable to normal users. |
| P1 | The parser advertises more refusal categories than its focused matrix pins: BOM, invalid UTF-8, out-of-range integers, root symlinks, absolute/backslash member names, unsorted entries, and schema mismatch lack one named tool-level test each. | Missing tests | 3 | 4 | The implementation is explicit, but an untested safety check can disappear while broad invalid-corpus tests still pass for a different reason. | Add a table-driven one-defect matrix with diagnostic fragments, analogous to the strict-capture tests, without creating a general mutation framework. |
| P2 | Mutation-and-repair tests use `checkpoint_v1`; `v1` is covered only by the checked-in no-op test. | Missing tests | 2 | 5 | The shared envelope makes behaviour likely identical, but the second allowlisted path and schema are not proven through an actual write-and-repair cycle. | Parameterize one repair test over both corpus names; do not duplicate the entire negative matrix. |
| P2 | Atomicity is per file, not across the complete corpus. | Future technical debt / failure handling | 2 | 2 | A crash between member and manifest replacement leaves a temporarily stale corpus. | Retain manifest-last fail-closed ordering and repairability; add transactional machinery only if this becomes an automated concurrent writer. |
| P2 | Canonical JSON options are repeated in the tool and `pmm_phase7.canonical_json`. | Unnecessary complexity / drift risk | 2 | 4 | A future change to one encoder could make the two Python surfaces disagree. | Keep the direct byte-equality test and C++ reader coverage; extract a shared module only if another production consumer appears. |
| P2 | The strict-capture mutation tests still locate their donor checkpoint with hard-coded transition index 5. | Existing future technical debt | 3 | 4 | Editing operations before the donor capture can break the negative matrix for an indexing reason unrelated to the integrity tool. | Make locating the unique checkpoint operation the next separate test-only increment. |
| P2 | `CorpusPlan` retains every original byte string and every candidate byte string until all selected corpora have been staged. | Unnecessary complexity / scalability | 2 | 3 | The duplication makes compare-before-write and whole-plan validation easy to audit, but memory grows at roughly twice the corpus byte size before JSON object overhead. | Keep it for the current small corpora; stream or spill plans only after measured corpus growth, while preserving preflight validation and concurrent-edit detection. |
| P2 | Two simultaneous writers can both pass the pre-write byte comparison and then interleave replacements. | Future technical debt / concurrency | 2 | 2 | Manifest-last ordering prevents a falsely valid half-write, but it is not a lock and cannot promise which author's bytes survive. | Document single-writer authoring; add an advisory corpus lock only if automation or shared workspaces introduce real concurrent writers. |
| P3 | The CLI has a fixed registry for `v1` and `checkpoint_v1`. | Scalability / maintenance | 1 | 5 | A future corpus requires one explicit path and schema entry. | Preserve the allowlist because it prevents arbitrary-path writes; extend it deliberately with a new schema. |
| P3 | Path checks and pre-write byte comparison reduce ordinary races but do not use hardened directory-relative `openat` operations. | Future technical debt | 1 | 2 | A hostile process with repository write access could race filesystem entries between checks. | Treat the repository as a trusted local authoring boundary; harden only if the tool is ever exposed to untrusted concurrent writers. |
| P3 | Verification reports changed paths but does not render a semantic or pretty JSON diff. | Review ergonomics | 1 | 4 | Authors still use `git diff` after writing canonical one-line documents. | Keep authoritative output compact; add a read-only pretty summary only if review friction becomes material. |
| P3 | The implementation assumes POSIX-like sibling temporary files, `fsync`, directory descriptors, permissions, and atomic rename behaviour, but the portability boundary is stated only indirectly. | Missing documentation / portability | 1 | 5 | A future Windows or unusual-filesystem user may mistake a platform error for corpus corruption. | State that the checked-in workflow is supported on the repository's current macOS/Linux environment; document any broader portability only after testing it. |
| P3 | Adding a third corpus requires editing the allowlist, but there is no short extension checklist covering schema selection, no-op proof, repair proof, and reader validation. | Missing documentation | 1 | 5 | The code change is small, but an incomplete addition could expose a path without matching tests or reader coverage. | Add a concise extension checklist when a third corpus is actually proposed; avoid speculative schema-generalization now. |
| P4 | Every verification reparses and rehashes every member, and every write stages every changed output before replacing any of them. | Possible optimization | 1 | 2 | Runtime and memory are linear in total corpus size, but the current command is effectively instantaneous and complete revalidation is valuable. | Do not cache, stream, or parallelize until profiling shows material authoring cost; never use timestamps as integrity evidence. |
| P4 | The single manifest and canonical one-line expected traces remain merge and review hot spots as fixture count grows. | Future scalability concern | 2 | 2 | Parallel fixture authors will increasingly conflict in one line even though runtime remains small. | Prefer a read-only review view first; consider manifest sharding only after actual merge contention, because sharding changes both readers and the integrity envelope. |

### Category summary

- **Unnecessary complexity — impact 2/5.** The 342-line tool is longer than its simple outcome
  suggests because it makes parsing, preflight comparison, staging, replacement order, and cleanup
  explicit. The two full byte maps and repeated canonical JSON expression are the main costs. They
  are acceptable at current scale, but should not grow into a generic fixture framework.
- **Future technical debt — impact 2/5.** Multi-file atomicity, concurrent writers, and hostile
  filesystem races remain consciously outside a trusted manual authoring tool. The hard-coded
  strict-capture donor index is the more immediate, easier maintenance debt in the surrounding
  suite.
- **Missing tests — impact 3/5.** The main correctness story is covered, including fail-closed
  repair and semantic non-generation. The strongest gap is that several individually claimed
  parser refusals and the CLI exit contract are not yet pinned by named focused tests. These gaps
  do not invalidate current corpora, but they make future refactoring less safe than the docs imply.
- **Missing documentation — impact 1/5.** Normal verify, write, review, and recovery behaviour is
  documented. POSIX portability and the checklist for deliberately adding another corpus remain
  absent and should be added only when those boundaries become active work.
- **Possible optimizations — impact 1/5.** Full parse/hash passes and in-memory plans are linear but
  currently negligible. Caching would weaken confidence in the exact bytes being checked; streaming
  would complicate the preflight guarantee. Neither is justified without measurements.
- **Future scalability — impact 2/5.** Memory grows with corpus bytes, and review/merge contention
  grows around one-line documents plus one manifest. Runtime is not the present concern; human
  review and parallel authoring will become the first scaling pressure.

### Fix now, fix next, and defer

| Time horizon | Action | Reason |
| --- | --- | --- |
| Keep now | Preserve verify-by-default, explicit `--write`, complete preflight, atomic per-file replacement, and manifest-last ordering. | These are the core safety properties and are already understandable and tested. |
| Next bounded increment | Remove the strict-capture donor index, then add the missing named parser/CLI tests if this tool is modified again. | The donor index has impact 3 and ease 4; parser/CLI tests are cheap protection against future refactoring. |
| Defer | Shared canonicalization module, advisory locking, pretty output, streaming, caching, parallel hashing, or manifest sharding. | None addresses a measured current failure, and several would blur or complicate the audit boundary. |

### Recommended next increment

Keep this tool unchanged and remove the hard-coded donor transition index from the mirrored strict-
capture mutation tests. Each test should find the fixture's unique `checkpoint` operation, use the
matching transition, and assert that exactly one donor capture exists. This is a contained test-only
maintainability correction; it should not be mixed with remaining Python reader-mutation parity,
SHA boundary vectors, caching, or schema changes.

### Retained limitations

This workflow establishes reproducible bytes and hashes only. It does not make expected traces
self-authenticating, change production risk semantics, create a production serialization format,
or establish durable storage, WAL integration, process restart, portfolio recovery, multi-account
recovery, calibrated fills, queue priority, execution realism, PnL, collateral, settlement, paper
trading, or live readiness.

## Dynamic strict-donor lookup implementation critique

This review covers the removal of the fixed strict-mutation donor index. Impact rates the
consequence of leaving a finding open from 1 (minor) to 5 (blocks trustworthy evidence). Ease rates
how contained its correction should be from 1 (broad or externally constrained) to 5 (small and
local).

The former donor-index debt is closed. C++ and Python now independently locate the unique fixture
`checkpoint` operation, require operation/transition alignment, require a checkpoint document in
the matching transition, and construct the strict diagnostic prefix from the discovered index.
Focused tests pin all four lookup failures, while shifted temporary corpora prove that canonical
rewriting, rehashing, execution, mutation targeting, and field-specific diagnostics remain aligned
after an earlier operation is inserted. The 16-row matrices remain visible and independent.

### Assessment of the design

Keeping the locator local avoids turning a donor-specific exactly-one rule into a new corpus-wide
schema rule. The cost is a small duplicated lookup in C++ and Python, but that duplication has the
same evidentiary value as the duplicated strict matrix: either reader can fail without sharing the
other's implementation. Direct failure tests add a little code beyond the shifted regression, but
they prevent a happy-path-only helper from silently weakening zero-capture, multiple-capture,
alignment, or missing-document diagnostics.

The shifted test deliberately validates and executes the temporary corpus before breaking a strict
field. That makes it more expensive than testing only the returned integer, but the complete C++
checkpoint suite remains below one second and the Python module remains well below one second.
There is no measured reason to cache the donor, expose a parser hook, or extract a shared framework.

| Priority | Finding | Category | Impact | Ease | Why it matters | Recommended handling |
| ---: | --- | --- | ---: | ---: | --- | --- |
| P1 | The integrity tool's named parser-refusal matrix still omits individually claimed cases such as BOM, invalid UTF-8, out-of-range integers, root symlinks, absolute/backslash paths, unsorted entries, and schema mismatch. | Missing tests | 3 | 4 | Broad invalid-input coverage can keep passing through the wrong earlier failure after a refactor. | Add one local table of single-defect temporary corpora with exact diagnostic fragments. |
| P2 | The public integrity CLI still lacks subprocess coverage for exit codes, output streams, and `--write` dispatch. | Missing tests | 2 | 5 | Core-function tests do not fully protect the documented command used by reviewers and CI. | Add a narrow CLI seam or patched subprocess test without exposing arbitrary corpus write roots. |
| P2 | Lifecycle V1 has checked-in no-op verification but no mutation-and-repair cycle matching checkpoint V1. | Missing tests | 2 | 5 | The shared envelope is strongly suggestive, but the second allowlisted corpus has not exercised an actual write repair. | Parameterize one repair case across both allowlisted corpora. |
| P2 | Python still lacks several unrelated checkpoint reader mutations covered in C++. | Missing tests / future drift | 2 | 4 | Strict-capture parity is complete, but secondary reader rejection categories can still drift. | Close this in its own reader-parity package without changing semantics. |
| P3 | Default limits and result vocabularies remain duplicated between the independent test implementations. | Future technical debt | 2 | 3 | Independence is useful evidence, but coordinated semantic additions require careful mirrored updates. | Continue using reviewed fixtures as the contract; do not merge the Python model into production. |
| P4 | Full-corpus copying, parsing, and hashing remain linear for every mutation row. | Possible optimization / scalability | 1 | 3 | Isolation currently costs milliseconds and prevents cross-test state. | Defer caching, streaming, sharding, or parallel hashing until profiling shows material cost. |

### Reranked next work

1. Add the named fixture-integrity parser-refusal matrix.
2. Pin the public CLI exit and output contract.
3. Exercise lifecycle V1 through one mutation-and-repair cycle.
4. Close remaining Python checkpoint-reader mutation parity separately.
5. Keep duplicated semantic vocabularies under review, but preserve implementation independence.
6. Defer corpus caching, locking, streaming, sharding, and serialization optimization.

### Retained limitations

This increment proves position-independent test targeting, not new checkpoint behavior. It changes
no checkpoint rejection category, enum ordinal, first-failure order, schema, reviewed fixture, or
production risk rule. It does not create production serialization, durable storage, WAL recovery,
process restart, portfolio or multi-account recovery, calibrated fills, queue priority, execution
realism, PnL, collateral, settlement, paper trading, or live readiness. The frozen lifecycle V1
oracle remains unchanged and ineligible for checkpoint fixtures.
