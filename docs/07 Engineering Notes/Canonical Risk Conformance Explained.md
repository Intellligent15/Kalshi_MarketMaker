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

## Named parser refusals in plain language

### What changed

The integrity tool already refused ambiguous bytes, unsafe paths, unsupported integer values, bad
manifest order, and mismatched schemas. Broad negative tests exercised some of that behaviour, but
they did not prove every advertised rule independently. A refactor could remove one check while a
test continued passing because the same temporary corpus happened to fail an earlier check.

The test suite now has one named row for each previously unpinned refusal. Signed underflow and
unsigned overflow are separate because the accepted interval has two independent boundaries:
signed 64-bit on the lower side and unsigned 64-bit on the upper side.

### How the proof works

```text
valid checkpoint corpus copy
            |
            v
one deliberate parser defect
            |
            v
snapshot every temporary file byte
            |
            v
build_plan must raise CorpusError
            |
            +--> diagnostic must name the intended refusal
            |
            v
every file byte must still match the snapshot
```

The mutations preserve the rest of the envelope. For example, the out-of-range integer occupies a
real integer field and its temporary hashes describe the invalid bytes. An absolute member name
still points to the same existing file, and a backslash-containing member is renamed so that the
manifest does not also describe a missing file. Manifest values are canonically rewritten and the
payload hash is updated when the intended defect allows parsing that far.

The root-symlink row moves the copied directory to a real sibling and places a symlink at the
original temporary root. Planning must reject the root before reading its manifest. Temporary-
directory cleanup removes both paths, and the target corpus's byte snapshot proves no file was
repaired through the link.

### Why the test calls `build_plan` directly

`build_plan` is the integrity tool's public, read-only planning boundary and is already used by the
tool tests. Calling it directly exposes the exact `CorpusError` and allows every row to use a
temporary corpus without adding an arbitrary public `--root` option. Argument parsing, exit-code
translation, stdout and stderr, and `--write` dispatch belong to the separate public CLI contract
and remain the recommended next increment.

The complete refusal matrix uses `checkpoint_v1` only because the lifecycle and checkpoint corpora
share this parser and integrity envelope. Duplicating the rows would repeat one implementation, not
provide independent semantic evidence. The checked-in corpora remain unchanged, and the integrity
tool still does not execute risk logic or derive expected transitions.

### What this does not prove

The matrix is enumerated safety coverage, not fuzzing, hostile-filesystem hardening, corpus-wide
transactions, or durable storage. It changes no risk result, rejection ordering, fixture schema,
reviewed expected answer, or V1 oracle capability. It does not establish process recovery,
portfolio recovery, realistic fills, queue priority, PnL, collateral, settlement, paper trading,
or live readiness.

## A deeper walkthrough of the parser-refusal matrix

### The problem we were actually solving

The integrity tool already contained the right safety checks. The problem was that several checks
were promises made by code and documentation but not independently protected by tests.

Suppose one broad test creates an unsafe manifest with three problems:

```text
wrong schema
    + stale payload hash
    + absolute member name
```

The test may expect the corpus to fail, and it will. But that test cannot tell us which guard caused
the failure. If a refactor accidentally removes the absolute-name check, the wrong-schema check
still fires and the broad test remains green. The suite says "bad input failed" while the specific
safety promise silently disappeared.

The new matrix changes the question from:

> Does some invalid corpus fail somehow?

to:

> When this is the only intended defect, does the planner raise `CorpusError` for this exact rule
> and leave every corpus file alone?

That is why the work is more than adding ten bad JSON examples. It constructs ten controlled
experiments.

### What we added

One test contains ten named rows:

| Layer | Refusal rows | What they protect |
| --- | --- | --- |
| Byte decoding | UTF-8 BOM, invalid UTF-8 | Readers agree on the byte encoding before JSON interpretation. |
| Numeric representation | signed underflow, unsigned overflow | Python cannot silently accept integers the C++ reader cannot represent. |
| Filesystem boundary | root symlink | The planner cannot be redirected through a linked corpus root. |
| Manifest membership | absolute name, backslash name | Members remain bare files inside the approved root. |
| Deterministic ordering | unsorted entries | Manifest traversal and generated bytes keep one stable order. |
| Version identity | wrong outer schema, wrong payload schema | The envelope cannot claim two versions or silently accept the wrong one. |

The two integer cases are separate because the supported range is asymmetric:

```text
minimum = -9,223,372,036,854,775,808      signed 64-bit minimum
maximum = 18,446,744,073,709,551,615      unsigned 64-bit maximum
```

Testing only one side would leave the other comparison unprotected.

### The anatomy of one row

Every row has three visible values:

```text
(human name, mutation, required diagnostic fragment)
```

The shared loop performs the proof:

1. Copy the 26-pair checkpoint corpus into a fresh temporary directory.
2. Apply the row's mutation.
3. Snapshot the bytes of every regular corpus file.
4. Call the public read-only planning boundary, `build_plan`.
5. Require `CorpusError`, not any exception.
6. Require the intended diagnostic fragment.
7. Snapshot the files again and require exact equality.
8. Delete the complete temporary directory.

The first snapshot is deliberately taken after mutation. The invalid corpus is the input to the
operation under test. We are not asking whether the mutation changed the copy; of course it did.
We are asking whether `build_plan` changed that input while deciding to reject it.

```text
pristine copy --test setup writes defect--> invalid input A
                                             |
                                             | build_plan
                                             v
                                        rejected input B

required: bytes(A) == bytes(B)
```

That equality is the read-only proof.

### Why some mutations repair hashes

A negative test can be misleading when its setup creates an earlier integrity failure. Consider
the signed-underflow row. Changing the fixture member also changes its SHA-256 digest. If the test
left the old digest in the manifest, a digest check could reject the file before integer parsing.

The setup therefore does the following:

```text
change maximum_active_orders to -2^63 - 1
        |
serialize the same object shape canonically
        |
hash those deliberately invalid member bytes
        |
put that digest in the temporary manifest payload
        |
rehash the canonical payload
        |
call build_plan
```

The hash does not make the integer valid. It only says, "the manifest accurately describes these
bytes." That clears unrelated integrity checks so the numeric-range refusal must do the rejecting.
The unsigned-overflow row uses the same path with `2^64`.

This distinction is central to the repository's evidence model:

```text
hash correctness     = metadata describes bytes
parser correctness   = bytes obey the accepted representation
semantic correctness = reviewed values describe intended risk behaviour
```

The integrity tool owns the first two boundaries only. It still does not decide whether an expected
risk transition is true.

### How the path rows avoid missing-file failures

An unsafe member-name test is easy to write badly. If the manifest is changed from `case.json` to
`bad\\case.json` while the file remains `case.json`, then both of these statements are true:

- the name contains a forbidden backslash; and
- the named file does not exist.

The test could pass for the second reason while claiming to prove the first.

The implemented row renames the temporary expected-trace file to the same backslash-containing
name placed in the manifest. On macOS and Linux, a backslash may be a literal filename character,
so the file exists. The planner must reject the name policy, not file absence.

The absolute row similarly replaces the manifest value with the resolved absolute path of the same
existing fixture. The target exists and has the recorded bytes; only the rule requiring a bare
local filename is violated. On POSIX the string also contains `/`, so the broad slash check is the
first internal predicate to fire. The test proves the public contract—absolute names are refused—
without claiming that it uniquely executes the later `Path.is_absolute()` expression.

### How the root-symlink row stays safe

The test begins with:

```text
temporary/checkpoint_v1/       real copied corpus
```

It renames that directory and creates a link at the original name:

```text
temporary/checkpoint_v1-real/  real copied corpus
temporary/checkpoint_v1  ----> checkpoint_v1-real
```

`build_plan` receives the linked path and must reject it before opening the manifest. The snapshot
walks through the link to record the real target files, so equality afterward proves that rejecting
the link did not repair anything behind it. Both paths remain inside the same temporary directory;
cleanup removes the link and its target without involving checked-in files.

### Why schemas need two rows

The manifest repeats its schema at two levels:

```json
{
  "schema": "pmm.risk_checkpoint_conformance_fixture_manifest.v1",
  "payload": {
    "schema": "pmm.risk_checkpoint_conformance_fixture_manifest.v1"
  }
}
```

The outer schema identifies the complete envelope. The payload schema identifies the bytes covered
by `payload_sha256`. If only one comparison were tested, a refactor could stop checking the other
and accept a manifest whose outside and hashed inside claim different versions. Separate rows keep
both comparisons load-bearing.

### Why one table is better than ten test bodies

The rows differ in defect construction and diagnostic. They do not differ in the proof obligations:

- fresh isolation;
- `CorpusError` specifically;
- intended diagnostic;
- no file writes; and
- cleanup.

Putting those obligations in one loop prevents a future row from accidentally omitting the
read-only assertion or weakening the exception type. Keeping the mutation functions local prevents
the table from turning into a general-purpose corpus mutation framework.

The tradeoff is density. The one test method is long because honest setup for paths and hashes is
long. Ten standalone methods would move the same code around rather than remove it, while a generic
framework would hide the details reviewers most need to audit.

### Why checkpoint V1 is the donor

The lifecycle and checkpoint corpora have different semantic documents, but `build_plan` treats
their outer envelope the same way:

```text
fixed root -> manifest shape -> member paths -> UTF-8/JSON -> canonical bytes -> hashes
```

Checkpoint V1 already supplies a real integer field and is the established mutation donor for this
tool's tests. Running the ten rows again against lifecycle V1 would execute the same Python parser,
not an independent implementation. The checked-in no-op test and explicit `--corpus v1` verifier
still prove that lifecycle V1 is registered and current. A real lifecycle mutation-and-repair cycle
remains useful, but it is a smaller separate registry/repair test rather than a second refusal
matrix.

### Why this is not a CLI test

The public command adds another layer:

```text
shell process
    -> argparse and corpus selection
        -> build_plan
            -> optional write_plans
        -> exit status and stdout/stderr
```

This package tests the middle boundary directly. That makes `CorpusError` observable and allows a
temporary root without adding a dangerous general `--root` option. It does not prove exit statuses,
stream routing, or `--write` dispatch. Those are now the recommended next bounded increment because
they can fail independently even when parsing remains correct.

### What the completed package proves

- Every listed parser refusal has a human-readable row.
- Signed underflow and unsigned overflow are independently protected.
- Each row requires `CorpusError` and the intended stable diagnostic fragment.
- Temporary metadata and files remain valid enough for the named refusal to win.
- Planning does not repair or write corpus files on refusal.
- The matrix exercises the shared envelope once through checkpoint V1.
- Both checked-in corpora remain canonical and byte-for-byte unchanged.
- No expected semantic answer is generated or blessed.

### What it deliberately does not prove

- It does not prove the CLI's exit codes or output streams.
- It does not prove accepted parsing at the exact numeric endpoints.
- It does not independently exercise every internal boolean predicate when multiple predicates
  enforce the same public rule.
- It is not fuzzing or property testing.
- It is not hostile-filesystem race hardening or a multi-file transaction protocol.
- It changes no checkpoint validation, risk result, fixture schema, or reviewed transition.
- It does not create durable risk storage, process restart, portfolio recovery, realistic fills,
  PnL, collateral, settlement, paper trading, or live readiness.

### The reason this work matters

The value of a refusal test is not that it makes malformed input fail today. The code already did
that. Its value is that it makes a specific safety promise difficult to remove accidentally
tomorrow.

The matrix turns documentation claims into independently named tripwires. If a future refactor
weakens UTF-8 handling, widens integers beyond the C++ boundary, follows a linked root, accepts an
unsafe member name, stops enforcing deterministic order, or ignores either schema comparison, the
corresponding row should fail for a clear reason. That is a modest change in code and a meaningful
improvement in how confidently the repository can evolve.

## The integrity command is now tested as authors actually run it

### What was still missing

The parser-refusal matrix called `build_plan` directly. That was the right boundary for proving a
specific `CorpusError`, but it stopped below the command-line layer:

```text
python process
    -> argparse
        -> fixed corpus selection
            -> build_plan
                -> optional write_plans
        -> exit status and stdout/stderr
```

A future edit could leave `build_plan` correct while breaking the documented command. Examples
include making `--corpus` optional accidentally, swapping a registry selection, returning the
wrong status, printing errors to stdout, or forgetting to dispatch `write_plans` when `--write` is
present. Direct function tests would remain green because none of those defects is inside
`build_plan`.

### How the subprocess proof works

Each case creates a repository-shaped temporary directory, copies the real integrity script into
`tools/`, and copies only the reviewed corpus roots needed by that case:

```text
temporary repository
├── tools/risk_fixture_integrity.py
└── python/tests/fixtures/risk_conformance/
    ├── checkpoint_v1/
    └── v1/
```

The test runs that copied file with the current Python interpreter. No module constant is patched.
No environment variable redirects a root. The script executes its normal top-level entry point and
derives `REPOSITORY_ROOT` from its own copied location exactly as the checked-in command does.

This preserves the public fixed-root rule while making writes harmless. The process can see only
the temporary fixture copies under the repository layout it expects.

### The byte snapshots

Before each command, the test records every regular corpus file by relative path and raw bytes.
The snapshot is taken after the test creates a stale or refused input:

```text
temporary valid copy
        |
        | deliberate test mutation
        v
input snapshot A
        |
        | real CLI subprocess
        v
output snapshot B
```

Verification success, stale verification, structural refusal, and argparse refusal must not alter
the corpus. For corpus-bearing cases the required result is `A == B`. This proves read-only
behavior at the public process boundary, not merely inside the planner.

### How the three non-parser statuses are separated

The command now has focused subprocess evidence for all three tool outcomes:

- status 0 means the selected corpus was current or an explicit write completed;
- status 1 means safe replacement candidates exist but verification did not write them; and
- status 2 means `CorpusError` refused the corpus.

Every case asserts both streams. Success uses stdout and leaves stderr empty. Stale verification
uses stderr and leaves stdout empty. Structural refusal also uses stderr, begins with `error:`, and
requires the intended parser diagnostic.

Argparse also exits 2, but it is a different failure contract. Missing and invalid `--corpus`
cases must begin with `usage:` and include argparse's `risk_fixture_integrity.py: error:` line.
The corpus-refusal case must begin directly with `error:` and must not include a usage block. The
test therefore cannot confuse malformed command syntax with a malformed corpus merely because the
numeric statuses match.

### How selection is proved without copying the whole matrix

Checkpoint V1 remains the main mutation donor. It supplies canonical success, safe stale input,
structural refusal, and the complete repair lifecycle. Repeating those cases against lifecycle V1
would test the same implementation twice.

Selection instead uses three small stale-input cases:

```text
--corpus checkpoint_v1  -> reports only the checkpoint member and manifest
--corpus v1             -> reports only the lifecycle member and manifest
--corpus all            -> reports both pairs in fixed registry order
```

The single-corpus temporary repositories contain only the selected root. The `all` repository
contains both. Exact repository-relative output paths show which allowlisted corpus was planned;
the `all` case cannot pass by silently visiting only one root because both temporary mutations must
be reported.

### What the write lifecycle proves

The temporary checkpoint donor receives a deliberately changed `fixture_id` and noncanonical
indentation while the copied manifest is left stale. This is safe integrity-tool input: the tool
preserves the authored JSON value rather than deciding whether it is a correct risk scenario.

The first `--write` must:

1. report the member and manifest in their stable replacement order;
2. change exactly those two files;
3. emit canonical member bytes;
4. update the member SHA-256 value;
5. update `payload_sha256`; and
6. leave stderr empty.

A normal verification then succeeds. A repeated `--write` reports that the metadata is already
current and produces an identical complete-corpus snapshot. Together these steps prove dispatch,
canonical repair, manifest integrity updates, post-repair validity, and idempotence through the
real command.

### Why there is still no root override

A public `--root` or output-directory flag would turn an allowlisted repository maintenance tool
into an arbitrary-path JSON rewriter. A test-only environment variable would add a hidden mode that
could be inherited accidentally. A `python -c` wrapper that patches `CORPORA` would skip the real
registry initialization. Direct `main(argv)` calls would skip process startup and argparse's exit
behavior.

Copying the real script avoids all four problems. Its cost is temporary filesystem copying and a
few short Python process launches. At 16 lifecycle and 26 checkpoint fixture pairs, that cost is
small and buys complete isolation.

### What this closes and what remains separate

The documented author command now has regression coverage for argument parsing, corpus selection,
statuses 0, 1, and tool-level 2, argparse-level 2, both output streams, read-only verification,
write repair, manifest updates, successful re-verification, and repeated-write byte identity.

This does not add lifecycle V1 mutation-and-repair parity beyond selection proof. It does not close
the remaining Python checkpoint-reader mutations, add the strict matrices' cardinality assertions,
or test accepted integer endpoints. It does not change fixture semantics, generate expected
answers, expand the frozen V1 oracle, or turn checkpoint serialization into production storage.

## A deeper walkthrough of the public CLI subprocess tests

### The short version

We tested the integrity command the same way a human or CI job uses it: start a new Python process,
pass command-line arguments, observe its exit status and two output streams, and inspect what
happened to the files.

We did not point that real command at the checked-in fixtures. Instead, we copied the command and
the required fixture corpora into a miniature temporary repository. Because the script discovers
the repository from its own file location, the copy behaves normally while every possible write is
confined to disposable files.

That design closes a specific gap:

```text
already tested                       newly tested
--------------                       ------------
JSON parsing                         script startup
canonical-byte planning              argparse behavior
manifest validation                  fixed corpus selection
atomic replacement helpers           process exit statuses
CorpusError details                  stdout versus stderr
                                      --write dispatch
```

### First, what the integrity tool is and is not

The tool manages an integrity envelope around reviewed test evidence. It answers questions such as:

- Is each JSON document encoded in the accepted canonical byte form?
- Does the manifest name the expected local files?
- Do its SHA-256 values describe those candidate bytes?
- Which safe byte replacements would be required?
- If explicitly authorized with `--write`, can those replacements be installed safely?

It does not answer:

- Is this risk transition semantically correct?
- Should an order have been admitted or rejected?
- Is this checkpoint a realistic result of exchange history?
- Does the expected trace match `AccountRiskProjection`?

Those semantic questions belong to independent C++ and test-only Python executors comparing
reviewed expected answers. The CLI tests deliberately mutate `fixture_id` because the integrity
tool must preserve an authored value, canonicalize its bytes, and rehash it without pretending to
know whether that identifier makes a good risk scenario.

This boundary is essential:

```text
author chooses JSON values
          |
          v
integrity tool canonicalizes and hashes those values
          |
          v
independent executors test whether reviewed answers match behavior
```

If the integrity tool generated expected transitions from one risk implementation, the hashes
would describe bytes but the corpus would no longer be independent reviewed evidence.

### Why direct tests were not enough

Before this increment, direct tests already called `build_plan` and `write_plans`. That was strong
coverage for the internal mechanics. It still left a thin but real untested layer.

Consider five possible regressions:

1. `--corpus` accidentally stops being required.
2. `--corpus v1` selects the checkpoint root.
3. stale verification returns 0 even though it prints paths.
4. an error is printed to stdout instead of stderr.
5. `--write` is parsed but never calls the writer.

Every direct `build_plan` test could remain green in those situations. The planner would still
parse, validate, and construct correct candidates. The documented command used by authors and CI
would nevertheless be wrong.

The subprocess tests cover the composition around those functions:

```text
operating system starts Python
             |
             v
copied script executes __main__
             |
             v
argparse creates or refuses arguments
             |
             v
fixed registry selects corpus roots
             |
             v
planner builds candidates
             |
             +---- verification reports without writing
             |
             +---- --write installs candidates
             |
             v
main returns and SystemExit sets process status
```

### Building the temporary repository

The helper creates a fresh `TemporaryDirectory`, then constructs only the layout the script needs:

```text
pmm-risk-integrity-cli-.../
└── repository/
    ├── tools/
    │   └── risk_fixture_integrity.py
    └── python/tests/fixtures/risk_conformance/
        ├── checkpoint_v1/
        └── v1/
```

Not every case receives both corpora. A checkpoint-only case copies only `checkpoint_v1`; a
lifecycle-only case copies only `v1`; the `all` case copies both. This is part of the selection
proof, not merely a speed optimization.

The script contains:

```python
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
```

For the copied file, that expression resolves to the temporary `repository/` directory. Its normal
`FIXTURE_ROOT` and `CORPORA` entries therefore point at the temporary copies automatically. The
checked-in script is not edited, and the checked-in fixture paths are never patched.

### Launching the real command

The helper calls the current interpreter explicitly:

```python
subprocess.run(
    [sys.executable, copied_script, *arguments],
    cwd=temporary_repository,
    capture_output=True,
    text=True,
    check=False,
)
```

Each choice is deliberate:

- `sys.executable` uses the interpreter running the test suite.
- The copied filename executes the real source as a script, including `__main__`.
- The temporary repository is the working directory authors would expect.
- `capture_output=True` keeps stdout and stderr independent.
- `text=True` makes the public lines easy to assert.
- `check=False` lets the test inspect expected statuses 1 and 2 instead of turning them into a
  generic `CalledProcessError`.

The result carries three independent observations: `returncode`, `stdout`, and `stderr`. Every CLI
case asserts all three.

### The snapshot model

The snapshot helper walks every regular file under the temporary risk-conformance root and records:

```text
relative path -> exact bytes
```

Relative paths distinguish the two corpora. Exact bytes distinguish a true no-op from a parse and
rewrite that happens to preserve the JSON value.

Timing matters. For a negative or stale case, the test first creates the intended input, then takes
the snapshot:

```text
canonical temporary copy
          |
          | test setup introduces one intended condition
          v
snapshot A = input to the command
          |
          | subprocess runs
          v
snapshot B = state after the command
```

Read-only behavior means `A == B`. Comparing B with the original canonical copy would be wrong:
the setup mutation is part of the intended input and is supposed to differ from the pristine
corpus.

### Case 1: canonical verification

The first case copies canonical checkpoint V1 and runs:

```text
--corpus checkpoint_v1
```

It requires:

- status 0;
- exactly `fixture integrity metadata is canonical and current` on stdout;
- empty stderr; and
- identical before/after corpus snapshots.

This proves more than "the planner found no changes." It proves the public command routes a clean
result to the intended stream, translates it to the documented status, and remains read-only.

### Case 2: safe stale verification and registry selection

A safe stale input is valid JSON that the tool can canonicalize without inventing values. The
helper loads a named member, appends `_cli_edited` to its authored `fixture_id`, and writes indented
JSON while leaving the manifest untouched.

The candidate plan then contains two changes:

```text
member
  - needs compact canonical bytes
  - has a new SHA-256 because the authored value changed

manifest
  - needs the new member digest
  - needs a new payload_sha256
```

Without `--write`, the command must return status 1, print nothing to stdout, print the two
`would update` paths plus the review-and-rerun instruction to stderr, and leave snapshot A intact.

The same proof shape covers selection proportionately:

| Selection | Temporary roots | Deliberate stale members | Required reported roots |
| --- | --- | --- | --- |
| `checkpoint_v1` | checkpoint only | checkpoint donor | checkpoint only |
| `v1` | lifecycle only | lifecycle donor | lifecycle only |
| `all` | both | one in each | lifecycle then checkpoint |

Why does this prove selection?

- If the checkpoint case selected V1, that root would not exist and the expected paths would not
  appear.
- If the V1 case selected checkpoint, the same failure would occur in reverse.
- If `all` silently visited only one root, only two of the four required changed paths would appear.

This is stronger than running `all` against two canonical roots. A broken implementation that
checked only one canonical root could still print the same success message.

### Case 3: structurally refused input

The refusal case adds a UTF-8 byte-order mark to the temporary checkpoint manifest. That is not a
safe stale representation to rewrite silently; it violates the documented parser boundary.

The command must:

- return status 2;
- leave stdout empty;
- begin stderr directly with `error:`;
- include the BOM-specific diagnostic;
- omit argparse's usage block; and
- preserve the refused bytes exactly.

This connects an actual `CorpusError` from the copied script to the public process contract. It does
not accept a generic exception or merely check that the status is nonzero.

### Case 4: argparse refusal

Two parser cases run before any corpus is needed:

```text
missing:  risk_fixture_integrity.py
invalid:  risk_fixture_integrity.py --corpus invalid
```

Argparse also returns status 2, so the number alone cannot distinguish command-syntax failure from
corpus refusal.

The shapes are intentionally different:

```text
argparse failure
    stderr begins: usage:
    later contains: risk_fixture_integrity.py: error:

CorpusError failure
    stderr begins: error:
    contains no usage block
```

The tests require these prefixes and the relevant missing/invalid-choice fragment. They do not
compare the complete argparse text because Python versions may wrap usage lines differently.

### Case 5: explicit repair and repeated no-op

The write case begins with the same safe stale checkpoint donor, then runs:

```text
--corpus checkpoint_v1 --write
```

The first process must return status 0, print the exact two updated paths to stdout, and leave
stderr empty. The test compares pre-write and post-write dictionaries and requires the changed set
to be exactly:

```text
checkpoint_v1/roundtrip_empty_state.json
checkpoint_v1/manifest.json
```

That prevents an implementation from rewriting every selected fixture while still producing a
valid corpus.

The content checks then reconstruct the integrity relationships:

```text
canonical member bytes
        |
        v
SHA-256 == manifest entry fixture_sha256

canonical manifest payload bytes
        |
        v
SHA-256 == manifest payload_sha256
```

The test also requires the repaired member bytes to equal the canonical serialization of the
deliberately authored document. The `_cli_edited` identifier survives. This proves the writer did
not derive or replace semantic content.

Two more independent commands finish the lifecycle:

1. Verification returns status 0 and leaves the repaired snapshot unchanged.
2. A repeated `--write` returns status 0 with the distinct "already canonical and current"
   message and leaves the same snapshot unchanged.

The second step is important. A writer can produce valid bytes once while still being
non-idempotent—for example, by changing formatting, order, or metadata on each invocation. Exact
snapshot equality rules that out for the complete selected temporary corpus.

### Why some output is exact and some is fragment-based

The tests divide output by ownership and stability.

Tool-owned, repository-relative output is exact:

- canonical/current success;
- already-current no-op write;
- `would update` paths;
- `updated` paths; and
- the instruction to review values and rerun with `--write`.

Exact equality is appropriate because these messages are the public author workflow. Stream
routing and path order are part of what the test protects.

Output influenced by the environment is shape-based:

- argparse usage wrapping can differ by Python version;
- `CorpusError` paths contain a random temporary directory.

Those assertions use stable prefixes and rule-specific fragments. This avoids brittle tests
without weakening the behavior being claimed.

### Why we did not add a root option

The simplest-looking test interface would be:

```text
risk_fixture_integrity.py --root /tmp/my-corpus --write
```

That would be a poor production interface. The current registry is an allowlist: the tool may
write only reviewed roots paired with known schemas. An arbitrary root option would turn a narrow
repository maintenance command into a general JSON rewriter and would require new safety and
support claims.

Other alternatives also weakened the evidence:

| Alternative | What it would miss or risk |
| --- | --- |
| Patch `CORPORA` with `python -c` | Skips real root and registry initialization. |
| Add a test-only environment variable | Creates a hidden mode that can be inherited accidentally. |
| Call `main(argv)` directly | Skips script startup, real argparse exit, and OS-level streams. |
| Mock `write_plans` | Proves a call shape, not actual canonical repair and file effects. |
| Run against checked-in corpora | Makes a negative or write test unsafe and difficult to isolate. |

Copying the script and repository shape is slightly more filesystem work, but it preserves the
actual interface and contains all effects.

### The accepted tradeoffs

#### More test code

The package added 219 lines for five CLI tests and their helpers. A shorter mock-based test could
assert that `main` returned certain numbers. It would not prove real process behavior or byte
effects.

The size is acceptable because the steps remain local and readable. The suite does not introduce a
general-purpose harness class, a production seam, or a mutation framework.

#### Repeated copies and processes

Each behavioral case receives fresh roots, and repair deliberately launches three processes. This
costs more than shared in-memory state but prevents mutation leakage and models actual command
usage. The focused module remains around six tenths of a second, so optimization is not justified.

#### Donor coupling

The tests name `roundtrip_empty_state.json` and `lifecycle.json`. That means a fixture rename
requires a test edit. The alternative—searching dynamically for any mutable-looking member—could
silently select the wrong evidence after corpus changes. Explicit donors are the safer coupling.

#### Stable prose becomes an interface

Exact messages make cosmetic changes more expensive. That is reasonable for a documented author
command: wording that tells a user what changed, where it changed, and whether to rerun with
`--write` is behavior worth reviewing.

### What a reviewer should check in future changes

When editing this CLI or its tests, ask:

1. Does the subprocess still execute the copied real script rather than an imported replacement?
2. Does every mutation remain under a fresh temporary repository?
3. Is the baseline snapshot taken after setup and before the command?
4. Does every case assert return code, stdout, stderr, and permitted byte effects?
5. Are tool-owned lines exact and environment-owned portions fragment-based?
6. Does `all` still require evidence from every allowlisted corpus?
7. Does repair change only the intended member and manifest?
8. Are both the member digest and manifest payload digest reconstructed independently?
9. Does verification succeed after repair?
10. Is repeated `--write` byte-identical?
11. Did any checked-in fixture, schema, production risk rule, or frozen-oracle capability change?

### What the completed work proves

- The actual script starts and parses its public arguments.
- Missing and invalid corpus arguments follow argparse's status-2 contract.
- `checkpoint_v1`, `v1`, and `all` reach the intended fixed registry roots.
- Canonical verification returns 0, uses stdout, and writes nothing.
- Safe stale verification returns 1, uses stderr, names planned paths, and writes nothing.
- Structural `CorpusError` returns 2, uses stderr, and writes nothing.
- Tool-level and argparse-level status 2 are distinguishable.
- `--write` performs real canonical repair in the temporary repository.
- Only the intended member and manifest change.
- Member and manifest payload hashes describe the repaired bytes.
- The authored JSON value is preserved rather than semantically regenerated.
- The repaired corpus verifies successfully.
- Repeated `--write` is a byte-for-byte no-op.
- The checked-in 16-pair lifecycle and 26-pair checkpoint corpora remain unchanged.

### What it does not prove

This is command-contract evidence, not semantic risk evidence. It does not prove that any reviewed
expected transition is correct, and it does not run `AccountRiskProjection`, the Python reference,
or the frozen V1 oracle to bless an answer.

It does not yet give lifecycle V1 its own complete write-repair cycle. It does not inject an atomic
replacement failure through the subprocess, pin `--help`, run a successful two-corpus
`all --write`, test accepted integer endpoints, or close remaining Python checkpoint-reader
parity. Those are separate and mostly low-impact boundaries.

It changes no production risk semantics, rejection category, enum ordinal, first-failure ordering,
fixture schema, reviewed fixture, matching behavior, core integer type, watermark, post-only rule,
external admission ownership, or kill-switch boundary.

It does not create production checkpoint serialization, durable storage, WAL integration, process
restart, portfolio recovery, multi-account recovery, calibrated fills, queue priority, execution
realism, PnL, collateral, settlement, paper trading, or live readiness.

### Why this was the right next increment

The parser rules were already tested directly. The documented command was the narrowest remaining
boundary where a regression could make correct internal functions unusable to authors and CI. The
copied-script approach closed that gap without widening production behavior.

The next increment should remain similarly narrow: give lifecycle V1 one complete temporary
mutation-and-repair cycle. That will close the one corpus-specific writer path not yet exercised
without repeating the full CLI matrix or changing semantic fixtures.

## Lifecycle V1 now completes the write-repair cycle

### What changed

The copied-script subprocess test now runs the same complete write cycle against both allowlisted
corpora. The established checkpoint case remains the first explicit row; lifecycle V1 adds
`v1/lifecycle.json` as the second. No checked-in fixture changes, and
`tools/risk_fixture_integrity.py` remains unchanged.

The lifecycle row proves the corpus-specific part that selection and stale reporting did not: the
real public command can canonicalize a lifecycle member, repair the lifecycle manifest, verify the
result, and recognize a repeated write as a byte-for-byte no-op.

### How it works

The test builds a miniature temporary repository containing a copy of the real script and only the
selected corpus. For lifecycle V1 it loads `lifecycle.json`, changes the authored identifier from
`lifecycle` to `lifecycle_cli_edited`, and writes indented JSON without repairing the manifest.

That creates two planned byte changes:

```text
v1/lifecycle.json
    authored identifier changed
    representation is noncanonical

v1/manifest.json
    fixture_sha256 describes the old member
    payload_sha256 describes the old manifest payload
```

The test snapshots every temporary corpus file and launches:

```text
risk_fixture_integrity.py --corpus v1 --write
```

It requires status 0, empty stderr, and these exact stdout lines in member-then-manifest order:

```text
updated python/tests/fixtures/risk_conformance/v1/lifecycle.json
updated python/tests/fixtures/risk_conformance/v1/manifest.json
```

The before/after snapshots must differ at exactly those two relative paths. The repaired lifecycle
bytes must equal `canonical_bytes` of the deliberately authored document, and parsing those bytes
must still return `fixture_id: lifecycle_cli_edited`.

The two hash relationships are then reconstructed separately:

```text
SHA-256(repaired lifecycle bytes)
    == manifest entry fixture_sha256

SHA-256(canonical manifest payload bytes)
    == manifest payload_sha256
```

The test does not accept the subprocess's success status as proof of either relationship; it reads
the resulting bytes and computes both digests independently.

Two fresh subprocesses finish the proof. Ordinary `--corpus v1` verification must return the exact
canonical/current message and preserve the repaired snapshot. A repeated `--corpus v1 --write`
must return the distinct already-current message and preserve the same complete snapshot.

### Why the existing test was parameterized

Checkpoint and lifecycle roots use the same public write protocol. A separate lifecycle test would
repeat the complete three-process sequence and its byte/hash assertions. A shared assertion helper
would keep separate test names but hide the important mutation, snapshot, write, verify, and repeat
ordering behind another interface.

One explicit two-row test table is the smaller auditable choice. The donor filenames and expected
authored identifiers remain visible, while every process and byte assertion stays in the test
body. A failure is still identified by its `corpus` subtest.

### Why this remains integrity-only

Changing `fixture_id` does not ask the tool to create a meaningful risk scenario. The temporary
expected trace remains untouched and is never executed. That temporary pair may therefore be
semantically inconsistent, which is acceptable for this test boundary.

The important separation is:

```text
integrity test
    preserve authored JSON -> canonicalize bytes -> repair hashes

semantic conformance test
    execute reviewed fixture -> compare reviewed transition answers
```

Running `AccountRiskProjection`, the test-only Python reference, or the frozen V1 oracle here would
blur those responsibilities and risk turning one implementation's output into an expected answer.

### What this closes and what remains

Both fixed corpus roots now have a complete temporary mutation, write, verification, and repeated
no-op cycle. Lifecycle selection, schema wiring, output paths, member canonicalization, manifest
repair, authored-value preservation, and idempotence are covered without repeating checkpoint
refusals or changing the public tool.

The next bounded conformance package is the remaining Python checkpoint-reader mutation parity.
Strict-matrix cardinality, integer endpoints, Windows setup, root README discoverability, `--help`,
successful `all --write`, subprocess write-failure injection, locking, transactions, additional SHA
vectors, and fuzz/property testing remain separate lower-priority work.

This increment changes no production risk behavior, checkpoint category or ordering, fixture
schema, reviewed answer, frozen-oracle capability, matching rule, integer type, watermark,
post-only rule, external admission ownership, or kill-switch boundary. It adds no durable storage,
restart recovery, portfolio recovery, calibrated execution, PnL, collateral, settlement, paper
trading, live readiness, or profitability evidence.
