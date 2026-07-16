# Canonical Risk Conformance Explained

## What we changed

Before this milestone, a historical backtest could either use a small Python admission gate or ask
the real C++ risk projection. The Python gate was useful for the first Phase-7 pipeline, but it
did not understand reservations, ingress binding, side exposure, event watermarks, or the kill
switch.

We introduced `pmm.backtest.v2`. New V2 experiments must use the C++ oracle. The old V1
configurations keep their original Python path so prior experiments remain reproducible instead of
changing behavior under the same name.

## How it works

```text
observed Level-2 -> causal feature -> quote intent
                                      |
                                      v
                         C++ AccountRiskProjection
                                      |
                 ModelDerived lifecycle transition
                                      |
                  risk trace + orders/fills/ledger
```

Python still owns observed-data replay, causal feature scheduling, and the deliberately synthetic
fill model. It does not send observed L2 into the exchange or order book. When a strategy produces
a quote, Python asks C++ risk to admit it. C++ reserves the worst-case exposure; Python binds the
synthetic ingress ID and sends a model-derived acknowledgement. Later model fills, cancellations,
and expiries are sent through the same projection.

V2 writes `risk-trace.jsonl`. Each row records the operation, its input, C++ result, and the C++
risk view after it ran. The result manifest hashes that trace alongside orders, fills, and ledger.
Running the same inputs, configuration, implementation, and build target twice produces the same
artifact bytes.

The configuration names the CMake target `pmm_risk_oracle`, not an absolute executable path. The
runner builds that target in a repository-relative build directory, reads CMake's generated target
path, and verifies that it did not escape the build directory.

## Why it matters

The important improvement is not a claim that the fill model became realistic. It did not.
`trade_touch_v1`, when used, remains `ModelDerived`; the first V2 example intentionally uses
`no_fill_v1`.

Instead, the improvement is that newly created research runs can no longer silently use weaker
risk semantics than the C++ simulator-side projection. A rejected C++ event now also leaves the
projection unchanged: acknowledgement, fill, and order-outcome validation occurs before state
mutation.

## What remains deliberately limited

- The oracle's transport is still a small local line protocol; the versioned trace is an artifact,
  not yet a complete versioned IPC specification.
- The trace records aggregate risk state, not enough order/reservation detail for independent
  replay.
- V2 supports a fixed whole-contract, cent-priced, post-only research baseline only.
- There is no calibrated fill model, queue position, fee/PnL correctness, collateral, settlement,
  paper trading, durable full-run recovery, or live-trading claim.

The next correctness milestone is fixture-driven transition parity plus explicit product terms.

## Fixture conformance increment

The first fixture is deliberately small: reserve a buy, bind its ingress, acknowledge it, partially
fill it, then logically expire its remainder.  It has a reviewed state after each transition and is
run against both C++ and a test-only Python reference.  The resulting V2 trace now includes the
live order or pending reservation itself, not only the totals.  This proves state-machine agreement
for the shared lifecycle subset; it does not make the local whitespace oracle a production protocol.

## What, how, and why

### What changed

The risk trace now records the individual things that make up its totals: each live order and each
pending reservation.  The repository also has a small reviewed lifecycle fixture, its expected
state after every step, a manifest that hashes both, and a Python reference that exists only in the
test tree.

### How it works

1. A fixture admits a two-contract buy, binds its ingress ID, acknowledges order 11, fills one
   contract, then expires the remaining contract.
2. The Python test-only reference applies the same operations and compares every result and state
   to the reviewed expected trace.
3. The same fixture drives the real C++ oracle.  After each operation, `SNAPSHOT` returns the
   complete C++ state, which must equal the Python state.
4. Backtest V2 uses that same snapshot to write `pmm.risk_conformance_trace.v2`; its manifest
   hashes the trace as before.

### Why this shape

Comparing only final position can miss a reservation leak or a wrongly correlated order that later
balances out.  Comparing the complete state after every transition makes those defects visible at
the first bad operation.  Keeping Python under `python/tests/` gives an independent check without
allowing a second production risk engine to enter research runs.

### Debt in plain language

This is a foundation, not full conformance yet.  We proved one representative lifecycle path and
made all future traces inspectable.  The next work is repetitive but important: add the remaining
small fixtures, especially rejection, restore, and malformed-input paths, before treating the
suite as complete lifecycle coverage.

## Latest ingress-safety and fixture-integrity increment

### What we did

We closed three small state-machine holes and added one negative fixture:

- A pending reservation can now bind an ingress sequence only if no other reservation owns it.
- A zero-quantity fill is rejected before it can advance the risk watermark.
- Restoring a risk checkpoint now rejects invalid pending reservations and state that exceeds the
  configured order, exposure, or position limits.
- The fixture manifest now hashes its own canonical payload as well as every fixture and expected
  trace. A second fixture proves that duplicate ingress binding fails without changing state.

The standard `scripts/test.sh` command now runs the C++ CTest suite and the Python unittest suite.

### How we did it

```text
admit two reservations
        |
bind client 1 to ingress 7
        |
attempt to bind client 2 to ingress 7
        |
reject, retain both reservations exactly as they were
```

The C++ projection enforces the rule. The Python test-only reference implements the same narrow
rule. The reviewed fixture is replayed through both and `SNAPSHOT` compares watermark, position,
exposures, live orders, pending reservations, and kill-switch state after each step.

### Why we did it

Ingress is the link between a risk reservation and a later exchange response. If two reservations
could share it, an acknowledgement or rejection could release or activate the wrong reservation.
That is a risk-state correctness problem even if the final inventory later happens to balance.

The manifest-payload hash prevents a reviewer from trusting a manifest whose member list was
changed but whose individual files were not. Replaying the fixture twice and comparing raw bytes
checks that the test reference does not introduce hidden nondeterminism.

### What this still does not mean

This does not create a versioned production oracle protocol, durable full-run recovery, realistic
fills, queue priority, PnL correctness, paper trading, or live readiness. The whitespace oracle
remains the limited V1 local adapter. Full checkpoint/restore parity still belongs in a separate,
versioned test-only fixture harness.

## Completed lifecycle matrix

The shared corpus now checks every admission rejection, bad reservation binding, bad
acknowledgement or fill, command rejection, cancellation, logical expiry, bad event sequence, and
kill-switch transition. Each row compares watermark, position, all exposure totals, sorted live
orders, sorted pending reservations, and kill-switch state.

The V1 oracle did not grow: it is used only where its existing commands faithfully express the
fixture operation. Different-contract and foreign-identity boundaries stay direct-C++ only, and
checkpoint/restore remains the next separate versioned test-only harness.

## What we did, how we did it, and why

### What we did

We expanded two small fixtures into a reviewed lifecycle matrix. It covers the ways an order can
be refused before reservation, the ways a reservation can fail to bind to ingress, bad exchange
responses, ordinary lifecycle release, event ordering, and the kill switch. The matrix also checks
that the manifest and expected traces have not been silently changed.

### How we did it

Each fixture gives the test-only Python reference a binding, optional risk limits, and a short list
of operations. Its matching expected trace records the result and full account-risk state after
each operation. The same V1-compatible operation list is sent to the existing local C++ oracle;
after each response, `SNAPSHOT` must match the reviewed state exactly. Cases the V1 adapter cannot
say faithfully, such as a different contract on admission, stay in direct C++ tests.

### Why we did it

Final position alone can be correct after an earlier bug leaked a reservation or advanced a failed
event watermark. Comparing state at every step finds the first wrong transition. Keeping the
Python model under tests creates an independent check without making it a second research engine,
while freezing the whitespace adapter avoids accidentally presenting it as a production protocol.

### What remains next

The next correctness increment is not more V1 commands. It is a separate, versioned test-only
checkpoint/restore harness. Direct C++ fixture execution now makes all three lifecycle test
surfaces consume the reviewed documents.

## Direct-C++ fixture closure

The reviewed V1 documents now drive three separate test surfaces:

```text
fixture + expected trace + manifest
       |              |             |
Python reference   direct C++    eligible V1 oracle
```

The direct path calls `AccountRiskProjection` directly. It does not launch the oracle, so a
whitespace-protocol or snapshot-serialization change cannot hide a direct API regression. Before
replay, its test-only reader verifies the document bytes, SHA-256 hashes, schemas, safe file names,
and complete expected state. After every operation it compares watermark, position, all exposure
totals, sorted live orders, sorted pending reservations, and kill-switch state.

The oracle remains frozen. Its existing admission rejection number is now asserted exactly; other
domain failures remain generic `ERROR` responses whose prose is not a public interface. This work
does not include checkpoint/restore, durable recovery, realistic fills, PnL, or live readiness.

## What, how, and why of the closure

### What we did

We removed the last lifecycle-conformance representation gap. The reviewed V1 fixtures and expected
traces now drive a direct C++ test as well as the Python reference and eligible oracle integration.
The direct test compares the C++ projection's full state after every operation, including failed
operations. The oracle integration now checks the existing numeric admission rejection code rather
than only the broad rejection shape.

### How we did it

The C++ test-only reader loads `manifest.json`, checks its payload hash and every member hash, and
rejects noncanonical JSON, unsafe paths, malformed fields, invalid values, bad executor eligibility,
and internally inconsistent expected state. It maps each fixture operation to the existing public
`AccountRiskProjection` calls. It uses the same fixed 50-cent fill price already used by V1 because
V1 fixtures intentionally have no fill-price field and account-risk state does not depend on it.

The Python test independently validates the reviewed corpus, runs only eligible executors, and
parses `ADMISSION rejected <client> <code>` exactly for admission failures. For every other V1
domain failure, it accepts generic `ERROR` and compares the reviewed post-state instead of treating
the human-readable diagnostic as an interface.

### Why we did it

Before this increment, direct C++ tests and the reviewed fixtures could drift apart even while the
oracle path passed. Using one reviewed scenario representation removes that blind spot. Comparing
complete post-state after every transition finds reservation leaks, unintended watermark movement,
or incorrect ingress release at the first incorrect operation rather than after later events happen
to balance it out.

The reader is test-only so fixture review does not create a production JSON format or alter Phase 3
matching, core integer types, deterministic ordering, risk admission, or kill-switch ownership.

## Checkpoint/restore conformance

### What we did

We gave serialized risk state its own reviewed, versioned, test-only corpus. A checkpoint document
now writes down everything a restore needs — identity, limits, watermark, position, kill switch,
live orders, and pending reservations with their ingress bindings — and the corpus proves both
directions: a captured checkpoint has exactly the reviewed bytes, and an invalid checkpoint is
refused for exactly the reviewed reason. `restore` itself did not change behavior; it now
delegates to a pure `validate_checkpoint` that names which rule a bad checkpoint broke.

### How it works

```text
build state through lifecycle operations
        |
   capture checkpoint  ->  bytes must equal the reviewed document
        |
      restore
        |
  original and restored projections
        |
   every later operation runs on both
        |
identical results, identical state, identical re-serialized bytes
```

Roundtrip fixtures prove nothing is lost across capture and restore, including the kill switch,
a nonzero watermark, and partial-fill remainders. Document-restore fixtures prove the other
boundary: authored documents with duplicate order identifiers, zero quantities, duplicate client
intents, duplicate or zero ingress bindings, wrong contracts, non-post-only intents, or state
beyond the configured limits are each rejected with one exact `checkpoint_<category>` result.
The reader deliberately checks only syntax and canonical bytes on input documents so those
semantic defects reach the C++ projection instead of being masked by the test harness. Malformed
bytes, wrong hashes, unsafe paths, and unknown fields are separate reader rejections, each with
its own negative test in both C++ and Python.

### Why we did it

Restore is where serialized state and a second implementation matter most: a checkpoint that
silently drops a reservation or accepts an over-limit position can look fine until much later.
Comparing the original and restored projections after every subsequent transition finds the first
divergence, and asserting rejection categories — not prose — keeps diagnostics free to improve.
The frozen V1 whitespace oracle gained nothing, and the Python checkpoint module lives only under
`python/tests/` behind explicit entry points, so no second risk engine can leak into research
runs.

### What this still does not mean

Checkpoint conformance is in-memory round-trip evidence. It is not durable full-run recovery, not
a production serialization format, and it does not change any fill-model, PnL, settlement,
collateral, paper-trading, or live-readiness claim.

## The checkpoint increment in plain terms

### What we did

Risk state could already be checkpointed and restored in memory, but the only proof lived in a
handful of hand-written C++ tests. We wrote the state down: a checkpoint is now a small JSON
document listing who the account is, what its limits are, and exactly which orders and
reservations it holds. Twenty-one reviewed fixtures prove two things about it. Round-trip
fixtures prove nothing is lost: capture must produce exactly the reviewed bytes, and after
restoring, the original and the copy must agree on every later event, forever. Document-restore
fixtures prove bad state is refused: a checkpoint with a duplicated order, a zero quantity, a
shared ingress binding, the wrong contract, or state beyond the configured limits is rejected
with one exact named reason.

### How we did it

The production change is one pure function: `validate_checkpoint` names which rule a checkpoint
broke, in a documented first-failure order, and `restore` now calls it without changing its own
behavior. Everything else is test-only. A strict reader verifies the corpus bytes, hashes, and
schemas before anything runs — but it deliberately checks only *syntax* on input checkpoints, so
semantic defects still reach the real C++ projection instead of being filtered out by the test
harness. The same reviewed documents then drive two independent implementations: direct C++ and
a small Python model that lives only under `python/tests/`. Both must produce identical results,
identical complete state, and byte-identical re-serialized checkpoints after every step, and a
mutation matrix proves the reader rejects every tampering category it claims to.

### Why we did it

Restore is where hidden state corruption does the most damage: a dropped reservation or an
over-limit position can stay invisible until events later happen to balance it. Comparing the
original and the restored projection after every subsequent transition finds the first
divergence, not the eventual symptom. Writing rejection *categories* into fixtures — never error
prose — means diagnostics can improve without breaking reviewed evidence. And keeping the second
implementation in the test tree keeps the useful property of a cross-check without ever creating
a second production risk engine.

### Where the debt was before the quantity increment

The implementation review that preceded the next section found that restore still accepted an
individual order quantity that admission would have rejected. It ranked that semantic question
ahead of the strict-capture negative tests, SHA-256 vectors, and missing fixture-authoring helper.
The admission-reachable quantity increment below closes that first item; the remaining items stay
open and are reprioritized at the end of the section.

## Admission-reachable record quantities

### What changed

Restore no longer accepts an individual live order or pending reservation larger than the
configured maximum order size. Both cases produce the same typed result,
`checkpoint_order_quantity_limit`, while a quantity exactly at the limit remains valid.

### Why both record classes use the same rule

A pending reservation is created only after admission approves its quantity. When the exchange
acknowledges it, the live order must match that reservation exactly. Later fills and order outcomes
can shrink the remaining quantity but cannot increase it. In plain terms, a quantity-six live
order cannot appear naturally if the account has always had a per-order limit of five, just as a
quantity-six pending reservation cannot.

This makes restored records consistent with the normal admission path. It does not prove that
every field in an authored checkpoint came from a real sequence of historical events; watermark,
position, and record combinations are still validated through their stated structural and limit
rules rather than by reconstructing a hidden history.

### How we implemented it

The production surface changed in one place. `AccountRiskProjection::validate_checkpoint` now
compares every live `remaining_quantity` and pending intent `quantity` with
`maximum_order_quantity`. A violation returns the appended enum value
`CheckpointRejectCode::OrderQuantityLimit`; appending it preserves the ordinals of all existing
categories. `restore` still delegates to the pure validator and returns its existing
`DomainErrorCode::InvalidOrder`, so no partially restored projection can escape.

The test-only wire result is `checkpoint_order_quantity_limit`. Separate live and pending fixtures
raise aggregate limits so they isolate the new rule. A boundary fixture restores one live record
and one pending reservation exactly at the limit. Two multi-defect fixtures pin the preserved
structural precedence. Focused testing also exposed that three older aggregate-limit fixtures used
one oversized record; those now use two individually legal records whose sum exceeds the aggregate
limit, making their stated purpose truthful.

Both the direct C++ executor and the independent Python checkpoint validator consume the same 26
reviewed documents and must return the same typed result. The checkpoint JSON schema did not
change: this deliberately narrows which test-only V1 documents restore accepts without creating a
production serialization or migration promise. The frozen lifecycle V1 adapter remains ineligible
to execute checkpoint fixtures.

### How ordering stays predictable

Existing record-structure failures still win first. A duplicate live order remains a duplicate
failure even if the repeated record is also oversized. A wrong-contract, non-post-only, invalid-
ingress, or duplicate pending record likewise keeps its existing result. The quantity-limit check
then runs before active-order, aggregate-exposure, and position checks.

The corpus now separates these ideas cleanly. Oversized-record cases use larger aggregate limits,
while aggregate-limit cases use two individually valid records whose combined quantity is too
large. A separate accepted case places both a live order and a pending reservation exactly at the
boundary. Direct C++ and the independent test-only Python model execute all 26 reviewed documents.

### What remains next

The previous highest-priority semantic gap is closed. The next package remains intentionally
smaller: add negative tests for strict captured-checkpoint validation and standard SHA-256
known-answer vectors. Durable risk persistence, production serialization, process recovery, and
portfolio recovery remain separate design work.

## Strict capture and hash evidence hardening

### What changed

The strict promises made about a reviewed captured checkpoint now each have a focused negative
test in C++ and Python. The tests cover every identity field, every configured limit, strict live
and pending record order, positive quantities, post-only reservations, and positive bound ingress
sequences. The test-only C++ SHA-256 helper now also has three standard known-answer vectors.

No reviewed fixture or production risk rule changed. The new tests create invalid documents only
inside temporary copies of the corpus.

### The problem in plain language

A reviewed checkpoint is evidence about what the risk engine captured. Before this increment, the
reader contained rules saying that evidence must have the right owner, the right limits, sorted
records, positive quantities, post-only reservations, and valid ingress identifiers. The ordinary
corpus proved that valid captures were accepted, but it did not prove that removing any one of
those rules would be detected.

That is the difference between exercising code and pinning a contract. A valid example travels
through all checks at once. A focused negative example removes exactly one guarantee and proves
that this guarantee, specifically, is load-bearing.

The hash helper had a similar gap. Real fixture hashes exercised it repeatedly, but those expected
hashes had been created for the same corpus. A standard known-answer vector gives an answer defined
outside this repository, so agreement cannot come merely from the repository being internally
consistent with itself.

### How it works

`roundtrip_live_and_pending` is the donor because its captured checkpoint contains one live order,
one bound pending reservation, all four identity fields, and all six limits. A named table changes
one fact at a time. After the expected trace is rewritten canonically, the test recomputes its
member hash and the manifest payload hash before asking the reader to load it.

That rehash step matters. Without it, every case would stop at the stale digest and say nothing
about the intended strict rule. Each case also checks the expected field path or identity/limits
diagnostic. If the targeted rule disappears, the otherwise valid temporary corpus loads and the
test fails instead of accepting some unrelated later error.

The sorting cases use a duplicate identifier rather than decreasing order. Authored restore inputs
already reject decreasing identifiers, but deliberately allow equal identifiers so the production
restore validator can diagnose duplicates. Reviewed captures require the stronger, strictly
increasing rule, so equality isolates exactly that extra promise.

The SHA test bypasses the corpus and calls `Sha256Hex` with the empty string, `abc`, and a
multi-block NIST input. This separates algorithm correctness from the end-to-end manifest checks:
the corpus still proves that real bytes are hashed, while the vectors prove that the digest itself
is standard SHA-256.

### One mutation from beginning to end

Consider the `post_only` rule:

```text
copy the valid 26-fixture corpus
        |
find roundtrip_live_and_pending's unique checkpoint operation
        |
select the expected transition at that same discovered index
        |
change only pending_orders[0].post_only from true to false
        |
write canonical expected-trace bytes
        |
recompute the expected-trace hash and manifest payload hash
        |
load the corpus and require the post_only diagnostic path
```

If the test did not rehash, it would stop at “file hash is wrong” and never reach `post_only`. If it
accepted any exception, a schema error or stale path could make it pass accidentally. If it mutated
a `document_restore` input, it would test a different boundary where semantic defects are supposed
to reach the production validator. Keeping all three details together makes the negative test say
exactly what its name claims.

### Why there are 16 rows for eight high-level rules

“Identity matches” sounds like one rule, but the implementation compares account, strategy,
trader, and contract separately. “Limits match” similarly contains six independent values. One
representative identity mutation would not catch a future edit that accidentally stopped checking
the trader, and one representative limit would not catch omission of pending exposure. Separate
rows cost little because they share the same temporary-corpus machinery, so the suite pins all ten
individual comparisons plus the six record rules.

The C++ and Python tables intentionally repeat those rows. The duplication is useful: it is
possible for either reader to be wrong without automatically teaching the other reader the same
mistake. They share the reviewed donor and expected contract, not implementation code.

### What the two layers of hash testing prove

```text
known-answer vectors
        |
        +-- prove Sha256Hex implements standard SHA-256

real corpus member and payload hashes
        |
        +-- prove the correct algorithm is applied to the exact reviewed bytes
```

Neither layer replaces the other. Vectors alone do not prove that the manifest hashes the right
file. Corpus checks alone do not independently pin the algorithm. Together they make the evidence
chain easier to diagnose: an algorithm failure points at the vector test, while changed fixture
bytes point at member or payload integrity.

### Why we did not simplify the reader boundaries

The strict expected-capture reader and lax document-restore reader serve different purposes. A
reviewed capture claims to be output produced by a valid projection, so it must already obey every
capture invariant. An authored restore input may be deliberately invalid because the test wants to
observe the production `validate_checkpoint` category. Making both readers strict would look
simpler, but it would prevent semantic defects from reaching the component whose behavior the
restore fixtures are meant to prove.

Likewise, moving the Python checkpoint model into production would remove some test duplication
but create a second risk implementation. Keeping it under `python/tests/` preserves its value as an
independent cross-check without allowing research runs to choose weaker or divergent semantics.

### Why this boundary stays small

These are tests of existing evidence rules, not a new persistence design. `document_restore`
remains lax, the frozen V1 oracle remains ineligible, and Python checkpoint code remains under the
test tree. There is still no durable risk storage, process restart, portfolio recovery, or claim
about realistic fills, queue position, PnL, settlement, paper trading, or live readiness.

## Reproducible fixture integrity workflow

### What changed

The repository now has one checked-in command for turning deliberately edited fixture JSON into
the exact compact bytes both readers expect and for updating the manifest hashes over those bytes.
The same command handles the lifecycle and checkpoint corpora because their semantic documents are
different but their outer integrity envelope is identical.

The safe default only checks. An author must pass `--write` before any file can change:

```sh
uv run python tools/risk_fixture_integrity.py --corpus checkpoint_v1
uv run python tools/risk_fixture_integrity.py --corpus checkpoint_v1 --write
```

### How it works

```text
human reviews and edits JSON values
               |
               v
canonical UTF-8 JSON with exactly one final LF
               |
               v
SHA-256 over each fixture and expected-trace member
               |
               v
SHA-256 over the canonical manifest payload
               |
               v
atomic member replacement, then manifest replacement last
```

The tool validates the manifest membership and filesystem boundary before staging output. It
refuses unsafe paths, symlinks, duplicate or missing members, unreferenced JSON, ambiguous JSON
numbers, duplicate keys, and malformed manifest structure. It also remembers the bytes seen during
validation and refuses to overwrite a file changed by another process before the write begins.

Every output is staged beside its destination and flushed before atomic replacement. Installing
the manifest last is the important failure rule: if a process stops after installing a member, the
old manifest no longer matches and both conformance readers reject the corpus. The next explicit
write can repair that detectable state. This is fail-closed checked-in tooling, not durable storage
or a multi-file transaction protocol.

### Why integrity and semantics stay separate

The helper deliberately knows nothing about admission, restore, checkpoint rejection categories,
or expected risk state. If a human authors the wrong expected result, the helper preserves that
wrong value and faithfully hashes it. The C++ and Python conformance executors must then reject the
semantic mismatch.

That division prevents the implementation under test from blessing its own answer:

```text
rehash command       -> these hashes describe these bytes
fixture readers      -> these bytes satisfy the document contract
conformance executors -> actual behaviour matches the reviewed answer
human review         -> the reviewed answer is the intended rule
```

The workflow adds no production JSON or cryptography dependency, changes no risk rule or fixture
schema, and does not expand the frozen V1 adapter. Rehashing is maintenance support for reviewed
test evidence; it is not semantic verification, checkpoint durability, process recovery, or proof
of realistic fills, PnL, settlement, paper trading, or live readiness.

### An edit from beginning to end

Assume a reviewer deliberately changes one checkpoint fixture and its expected trace. Before this
workflow existed, the reviewer needed an ad hoc script or three manual digest calculations. A
small difference in JSON spacing or whether the final newline was included could produce a digest
that disagreed with both readers.

The new workflow proceeds in two distinct phases.

**Phase one plans without writing:**

1. Resolve `checkpoint_v1` through the fixed repository allowlist. The command cannot redirect a
   write to an arbitrary directory.
2. Read `manifest.json` and require its exact outer keys, matching top-level and payload schemas,
   a nonempty entry list, and strictly fixture-name-sorted entries.
3. Require every fixture and expected-trace name to be a unique bare filename. Reject a missing
   file, symlink, nested path, duplicate reference, or unreferenced JSON document.
4. Decode every member as UTF-8, reject ambiguous inputs such as duplicate object keys, floats,
   nonstandard constants, or values outside the C++ JSON reader's integer range, and require a JSON
   object at the top level.
5. Serialize the parsed value with sorted keys, no extra spaces, UTF-8 characters preserved, and
   one final LF. The tool retains both the original and candidate bytes.
6. Hash each candidate member. Insert those digests into the in-memory payload, hash the canonical
   payload including its final LF, and construct the candidate manifest.
7. Compare originals with candidates. Without `--write`, report the paths that differ and exit;
   nothing has been opened for output.

**Phase two writes only after explicit authorization:**

1. Re-read every destination that would change and compare it with the original bytes captured in
   phase one. If an editor or another process changed a file in between, refuse to overwrite it.
2. Create a temporary sibling for every changed destination, copy the candidate bytes, flush them,
   preserve the destination mode, and synchronize the staged file.
3. Atomically replace changed fixture and expected-trace members in filename order.
4. Replace `manifest.json` last and synchronize the containing directory.
5. Remove any unused temporary siblings if staging or replacement fails.

The split matters because validation failure cannot produce half an authored update, while the
manifest-last rule ensures an interrupted replacement sequence is detectable. It is possible to
end with new member bytes and an old manifest after a crash, but that state is invalid rather than
falsely trusted. Running the explicit write command again reconstructs the hashes and completes the
repair.

### What canonicalization changes and what it preserves

Canonicalization changes representation only:

```text
authored representation                 canonical representation
{
  "schema": "example",
  "result": "approved"
}                                        {"result":"approved","schema":"example"}\n
same keys, strings, arrays, numbers, booleans, and nulls
different ordering, spacing, and newline representation
```

The helper does not insert a missing state, reorder a semantic array, change a rejection category,
sort live orders, or calculate aggregate quantities. Array order is data and is preserved. Object
key order is representation and is canonicalized. That distinction is why the tool may repair
spacing but must not repair a supposedly incorrect expected transition.

Floats are refused even though Python can parse them because the current fixture schemas use JSON
integers only where a number is required and decimal strings everywhere else. Refusing floats
avoids depending on language-specific numeric rendering. Duplicate keys are refused because
silently choosing the first or last value would change what a human believed they authored.

### Why the hashes are layered

Each member digest answers a local question: did this exact fixture or expected-trace byte string
change? The payload digest answers a corpus question: did the reviewed member list, filenames,
ordering, or member digests change?

```text
fixture bytes --------> fixture_sha256 -----+
                                              |
expected-trace bytes -> expected_trace_sha256 +--> canonical payload --> payload_sha256
```

The complete manifest is not hashed inside itself because that would be recursively impossible.
Instead, the payload contains the stable membership facts and digests, and the top-level manifest
stores the digest of that canonical payload. The top-level and payload schema strings must also
match, so a manifest cannot quietly claim one envelope outside and another inside.

### What each test layer proves

The integrity-tool tests prove that valid checked-in corpora are no-ops, deliberately stale bytes
can be repaired deterministically, repeated writes are identical, unsafe structure is refused,
newer concurrent edits are not overwritten, and an injected failure before the manifest leaves a
repairable fail-closed state. One test deliberately writes the wrong expected rejection category
and proves the helper preserves it. That apparently strange test is the clearest evidence that the
helper is not a semantic answer generator.

The lifecycle and checkpoint conformance tests then provide the missing semantic layer. They load
the canonical bytes, validate the schema-specific document rules, and execute eligible C++ and
Python implementations against the reviewed transitions. Passing the integrity command alone is
therefore never a completion condition for an authored fixture change.

### Why the design is intentionally not more general

An arbitrary `--root` option would make temporary tests convenient but would widen the public
write boundary. Automatic discovery could silently bless a scratch JSON file. Generating expected
traces from C++ would make the implementation approve itself. A shared production JSON module
would pull test-evidence concerns into runtime code. Corpus-wide transactions, file locking,
streaming, caching, and parallel hashing would solve scale or concurrency problems the current
small, manually reviewed corpora do not have.

The chosen design is deliberately boring: two known roots, one manifest envelope, one canonical
encoding, standard SHA-256, explicit writing, and existing semantic executors. That makes every
boundary visible during code and fixture review.

## Position-independent strict checkpoint mutations

### What changed

The C++ and Python strict-capture matrices no longer assume where the donor checkpoint appears.
Each test finds the unique `checkpoint` operation in `roundtrip_live_and_pending`, uses the expected
transition at the same index, and builds its required diagnostic path from that discovered index.
All 16 named mutation rows remain separate in both languages.

### How it works

```text
fixture operations -- find exactly one checkpoint --> capture index
        |                                           |
        | require equal lengths                     v
        +--------------------------------> expected transition[index]
                                                    |
                                      require checkpoint document
                                                    |
                              mutate + canonical rewrite + rehash
                                                    |
                                 require dynamic field diagnostic
```

The lookup fails explicitly if the donor has no checkpoint operation, more than one checkpoint
operation, a different number of operations and transitions, or no checkpoint document in the
aligned transition. These are donor-test requirements, so the helpers stay local to the two test
files rather than becoming new checkpoint-schema rules in the shared fixture readers.

A second test inserts `kill_switch: false` and a matching unchanged-state transition immediately
before the temporary donor's capture. The rewritten and rehashed corpus must still load, and both
the direct C++ projection and test-only Python reference must execute the shifted donor before a
representative strict mutation is applied at the rediscovered index. This proves that selection,
mutation targeting, integrity metadata, and diagnostic construction all move together.

### Why the fixture operation leads

The fixture operation list is the program being executed; the expected trace is the reviewed
answer. Searching the trace for a `checkpoint` field would reverse that relationship and let a
misaligned answer identify itself as valid evidence. Operation-first lookup instead says: this is
where capture was requested, so the transition at this same position must carry the capture.

The change is test maintainability only. It changes no reviewed fixture bytes, checkpoint schema,
restore rule, rejection ordering, production risk behavior, or V1 oracle capability. Checkpoint
serialization and the Python checkpoint model remain test-only, and rehashing still proves byte
integrity rather than semantic truth.

## A deeper walkthrough of the donor-index correction

### The problem in one sentence

The strict tests knew *where the checkpoint happened today* instead of knowing *how to find where
the fixture says checkpointing happens*.

That difference sounds small because the reviewed donor currently has one obvious capture. It
matters because the fixture and expected trace are parallel arrays. If a valid operation were
inserted before capture, every later position would move:

```text
before
operations:  [admit, bind, acknowledge, admit, bind, checkpoint, restore, ...]
transitions: [  0,     1,          2,     3,    4,       5,       6, ...]

after inserting one valid earlier operation
operations:  [admit, bind, acknowledge, admit, bind, kill(false), checkpoint, restore, ...]
transitions: [  0,     1,          2,     3,    4,           5,       6,       7, ...]
```

The checkpoint semantics did not change, but a literal reference to transition 5 now points at
the inserted kill-switch transition. A test could fail with "checkpoint missing," mutate the wrong
value, or expect a diagnostic path that no longer describes its target. Those would be test-
maintenance failures, not risk-engine regressions.

### The mental model: program first, reviewed answer second

Treat the fixture operations as a tiny program and the expected transitions as its reviewed
step-by-step answer:

```text
fixture operation i  ------------------>  expected transition i
       instruction                              reviewed outcome
```

The operation `checkpoint` says that capture must occur at index `i`. The expected transition at
`i` must then contain the reviewed checkpoint document. The trace is not searched for something
that merely looks like a checkpoint because that would allow the answer to choose which
instruction it claims to answer.

This produces four explicit donor requirements:

| Requirement | Failure meaning |
| --- | --- |
| Exactly one checkpoint operation | Zero means there is no mutation target; more than one makes the donor ambiguous. |
| Equal operation and transition counts | Positional alignment cannot be defined if one array has extra or missing steps. |
| Same-index selection | The capture is chosen from the program, not inferred from answer shape. |
| Object-valued checkpoint at that transition | The reviewed answer must actually carry the document the strict matrix will mutate. |

### The three layers of proof

The implementation separates three questions that are easy to blur together.

#### Layer 1: can the donor be located unambiguously?

The local C++ and Python helpers scan only `operations[*].operation`, require exactly one
`checkpoint`, require equal array lengths, and inspect the transition at that returned index. Four
focused cases remove the capture, duplicate it, misalign the arrays, or remove the matching
checkpoint document. Each case requires its intended diagnostic rather than any failure.

#### Layer 2: do all strict rules use that location?

The existing 16-row table remains unchanged in meaning. Every row receives the checkpoint selected
through the helper, and every expected diagnostic is the discovered transition prefix plus a row-
specific suffix. The table still independently covers:

- four identity fields;
- six configured limits;
- live- and pending-record order;
- live and pending positive quantities;
- post-only pending intent; and
- positive bound ingress.

This is why the implementation did not replace the matrix with one generic mutation. Position
selection is shared mechanics, but each strict comparison remains separate evidence.

#### Layer 3: does the complete workflow survive a real position change?

A helper-only test could pass even if the matrix continued to use a literal index elsewhere. The
shifted regression therefore changes a temporary corpus exactly as a future fixture edit might:

1. Copy all 26 checkpoint fixture pairs to a temporary directory.
2. Locate the donor's capture from its operation list.
3. Insert `kill_switch: false` immediately before it.
4. Insert an `applied` transition carrying the unchanged preceding state.
5. Canonically rewrite the temporary fixture and trace.
6. Recompute both member hashes and the canonical manifest-payload hash.
7. Load the complete corpus and execute the shifted donor successfully.
8. Locate the capture again and require that it moved by one position.
9. Change the captured pending order's `post_only` value to false.
10. Canonically rewrite and rehash again.
11. Require the strict `post_only` field path at the newly discovered index.

Step 7 is especially important. Without it, the test might pass because the inserted operation or
transition was itself invalid. Executing the donor first proves that the position shift is a valid
scenario; the later failure can then be attributed to the intentional strict mutation.

### One mutation from input to diagnostic

The `post_only` shifted case now follows this evidence chain:

```text
operation list says capture is at i
              |
              v
expected transition i contains reviewed checkpoint
              |
              v
temporary earlier operation moves capture to i + 1
              |
              v
loader and executor accept the shifted corpus
              |
              v
post_only becomes false at transition i + 1
              |
              v
canonical bytes and hashes are repaired
              |
              v
reader reaches transition[i + 1].checkpoint.pending_orders[0].post_only
              |
              v
the exact strict diagnostic is required
```

If canonical rewriting were skipped, byte-shape validation could fail first. If rehashing were
skipped, member integrity would fail first. If the expected diagnostic were generic, either early
failure could accidentally satisfy the test. Keeping all three requirements ensures the row proves
the strict rule it names.

### Why the helpers are local and duplicated

There were two tempting abstractions that we deliberately rejected.

Moving the lookup into `risk_checkpoint_fixture.*` would make it reusable, but would also blur two
different rules. The shared reader currently permits the versioned roundtrip shape it documents;
the strict mutation test specifically needs one unambiguous donor. A donor-selection condition is
not automatically a schema condition for every fixture.

Sharing the locator or matrix between C++ and Python would reduce repeated code, but would also let
one implementation encode the other's answer. The current design shares the reviewed documents
and required behavior while keeping the code that enforces them independent. That duplication is
an evidence boundary, much like two independent calculations agreeing on the same reviewed result.

### Tradeoffs we accepted

| Choice | Benefit | Cost |
| --- | --- | --- |
| Local helper in each test file | Keeps donor policy out of shared schema code. | Two similar implementations must be maintained. |
| Four direct failure cases plus shifted regression | Pins both clear failures and real position independence. | More test code than a simple search expression. |
| Dynamic prefix plus row-specific suffix | Removes fixed-index coupling without weakening diagnostics. | Lookup returns a small amount of presentation data as well as the index. |
| Full temporary-corpus copy and rehash | Proves the same integrity boundary used by real fixtures and isolates every row. | Work grows with corpus size and number of mutations. |
| One shifted representative strict mutation | Proves shared targeting machinery with little repetition. | Does not rerun all 16 strict defects on the shifted donor. |
| Independent C++ and Python tables | Either reader can expose drift in the other. | New strict fields require coordinated updates in two places. |

At the current corpus size these costs are appropriate. The focused C++ checkpoint suite and
Python module both remain below one second, so caching, parser exposure, or shared mutation
frameworks would trade away clarity and isolation without solving a measured problem.

### What the completed tests prove

- The strict donor is identified from exactly one fixture checkpoint operation.
- Operation and transition alignment is required before mutation.
- The aligned expected transition must contain a checkpoint document.
- Capture selection, mutation targeting, and diagnostic paths do not depend on a fixed position.
- All 16 existing strict mutations still reach their intended rule after canonical rewriting and
  integrity rehashing.
- C++ and Python provide independent implementations of the same reviewed contract.
- The checked-in 26-pair checkpoint corpus remains unchanged.

### What they do not prove

The correction does not add a new checkpoint semantic, reconstruct event history, or make the JSON
a production persistence format. It does not test durable storage, WAL recovery, process restart,
portfolio recovery, or multi-account recovery. It does not improve fill calibration, queue
priority, execution realism, PnL, collateral, settlement, paper trading, or live readiness.

It also does not make integrity hashes semantic truth. Rehashing proves that metadata describes
the temporary bytes; the strict readers and executors prove behavior against reviewed expectations.
The frozen lifecycle V1 oracle remains unchanged and cannot execute checkpoint fixtures.

### How to review a future change safely

When the donor or strict contract changes, a reviewer should ask:

1. Does the fixture operation list still contain exactly one donor checkpoint?
2. Does the expected transition at that same index contain the reviewed capture?
3. Are new strict fields represented by named rows in both independent matrices?
4. Are mutation documents canonical and rehashed before loading?
5. Does each case still require its field-specific diagnostic?
6. Does the shifted donor still load and execute before the representative defect is introduced?
7. Did any checked-in fixture byte, schema, production risk rule, or V1 capability change
   unintentionally?

This checklist preserves the central idea: the fixture program chooses the capture, the reviewed
trace must align with it, and integrity metadata must be valid before a strict rule can count as
tested.
