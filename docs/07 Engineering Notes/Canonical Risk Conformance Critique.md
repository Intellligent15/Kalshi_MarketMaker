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
