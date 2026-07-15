# Risk Conformance Fixture Guide

The V1 corpus under `python/tests/fixtures/risk_conformance/v1/` is reviewed test evidence for
the account-risk lifecycle. It is not a production input format and does not version or expand the
V1 whitespace oracle.

## Documents and integrity

`manifest.json` names every fixture and expected trace. Its payload has a SHA-256 digest, and each
member has its own SHA-256 digest. Every JSON document must be canonical UTF-8 JSON with sorted
keys and exactly one final newline. Fixture member names are bare local filenames and must match
`<fixture_id>.json`; traces must match `<fixture_id>.expected.json`.

The test-only C++ verifier rejects malformed schemas, missing or unknown fields, invalid decimal
strings, unsafe paths, symlinks, duplicate members, bad hashes, noncanonical bytes, unsorted
records, and aggregate state that disagrees with its records.

## Fixture contract

A fixture has schema `pmm.risk_conformance_fixture.v1`, an identifier, operations, optional risk
limits, and optional executor eligibility. Omitted eligibility preserves the legacy shared default:
`direct_cpp`, `python_reference`, and `v1_oracle`. Explicit eligibility must be a unique subset of
those names.

The supported operations are `admit`, `bind_ingress`, `acknowledge`, `fill`, `cancel`,
`logical_expiry`, `command_rejected`, and `kill_switch`. `fill` intentionally has no price field:
the frozen V1 adapter and direct C++ fixture executor both use its existing fixed 50-cent test
value, which does not affect account-risk state.

Each expected transition gives a result and full post-state. A state includes aggregate exposure,
watermark, position, kill switch, identifier-sorted live orders, and identifier-sorted pending
reservations. This makes failed transitions auditable: their expected state is normally unchanged.

## Executor boundary

The direct C++ executor invokes `AccountRiskProjection` directly. The Python reference remains
under `python/tests/` and explicitly rejects C++-only operations. The V1 oracle runs only fixtures
it can faithfully express; for example contract mismatch remains direct-C++/Python-only.

V1 admission rejections assert their numeric `AdmissionRejectCode`. Non-admission V1 failures are
generic `ERROR` results and must not be compared by diagnostic text. Checkpoint/restore is outside
this schema; it lives in the separate checkpoint corpus described below.

## Checkpoint corpus

The corpus under `python/tests/fixtures/risk_conformance/checkpoint_v1/` is reviewed evidence for
serialized risk state. Its manifest (`pmm.risk_checkpoint_conformance_fixture_manifest.v1`)
follows the same canonical-bytes, payload-hash, member-hash, and path-safety rules as V1.

A fixture (`pmm.risk_checkpoint_conformance_fixture.v1`) declares `kind: "roundtrip"` or
`kind: "document_restore"`. Roundtrip fixtures use the V1 operation vocabulary plus two marker
operations: `checkpoint` captures the projection state and `restore` must immediately follow a
`checkpoint`. Document-restore fixtures embed a `pmm.risk_checkpoint.v1` document as input and
take identity and limits from it. Executor eligibility defaults to `direct_cpp` and
`python_reference`; the frozen `v1_oracle` is not a legal executor name here.

A checkpoint document carries account/strategy/trader/contract identity, all six limits, the
watermark, net position, kill-switch state, and identifier-sorted live and pending records.
Input documents are checked for syntax and canonicality only — non-decreasing identifier order,
canonical decimals, exact keys — so semantic defects such as duplicate identifiers, zero
quantities, non-post-only intents, or limit violations reach `restore` and must be rejected
there. Captured documents inside expected traces are strict: strictly sorted, positive
quantities, post-only, nonzero ingress, and identity/limits equal to the fixture's.

Expected traces (`pmm.risk_checkpoint_conformance_expected_trace.v1`) reuse the V1 complete-state
shape. Capture transitions carry result `captured` plus the reviewed checkpoint document, whose
canonical bytes must equal the serialized capture exactly. Restore transitions carry `restored`
with the post-restore state, after which executors dual-run every later operation against both
projections. A rejected document restore records exactly one `checkpoint_<category>` result with
no state and no continuation; the category is asserted against the typed
`CheckpointRejectCode` from `validate_checkpoint`, whose documented first-failure order is: live
orders in document order (zero quantity, duplicate identifier, per-order quantity limit), pending
orders (contract, zero quantity, post-only, zero ingress, duplicate ingress, duplicate intent,
per-order quantity limit), active-order count, buy/sell/pending exposure, position. The shared
per-record result is `checkpoint_order_quantity_limit`; equality with
`maximum_order_quantity_contracts` is accepted.

Per-order and aggregate-limit fixtures must isolate their intended rule. Oversized-record fixtures
raise the aggregate limits so only `maximum_order_quantity_contracts` fails. Aggregate exposure
fixtures use multiple individually legal records whose sum exceeds the relevant aggregate limit.
This prevents a fixture name from depending accidentally on a different rule's precedence.

## Strict captured-checkpoint mutation coverage

The strict rules for reviewed captures are pinned independently in both readers. The tests copy
the corpus to a temporary directory and mutate only the checkpoint embedded in the expected trace
for `roundtrip_live_and_pending`. They do not mutate a `document_restore` input: those documents
remain intentionally lax so semantic defects reach `AccountRiskProjection::restore`.

The mirrored C++ and Python matrix has one named row for each account, strategy, trader, and
contract identity field; one row for each of the six limits; separate live- and pending-record
ordering rows; separate live and pending positive-quantity rows; a post-only row; and a nonzero
bound-ingress row. The ordering mutations duplicate the donor's existing record. Equality is the
strict-only distinction because input documents already reject decreasing identifiers while
allowing duplicates through to restore.

Every mutation is written as canonical JSON, then the expected-trace member hash and canonical
manifest-payload hash are recomputed. The test requires the rule-specific field path or captured
identity/limits diagnostic. A stale digest, generic corpus rejection, or later restore failure
therefore cannot satisfy the assertion. The mutations are temporary test inputs; the 26 reviewed
fixture pairs and checkpoint schema remain unchanged.

The shared test-only C++ `Sha256Hex` helper is also checked directly against the standard empty,
`abc`, and multi-block NIST known-answer vectors. Corpus hashes remain the integration evidence;
the direct vectors establish that the helper producing and checking those hashes implements the
expected algorithm.

## Reproducible authoring and rehashing

`tools/risk_fixture_integrity.py` is the checked-in byte-integrity workflow for both reviewed
corpora. It canonicalizes JSON values that a human deliberately authored and updates the manifest
hashes that describe those bytes. It never executes `AccountRiskProjection`, the test-only Python
references, or the frozen V1 oracle, and it never creates or repairs semantic expected results or
states.

Verification is the default and never writes:

```sh
uv run python tools/risk_fixture_integrity.py --corpus checkpoint_v1
uv run python tools/risk_fixture_integrity.py --corpus v1
uv run python tools/risk_fixture_integrity.py --corpus all
```

Exit status `0` means the selected corpus is already current. In verification mode, status `1`
means safe candidate bytes differ and `--write` is required. Status `2` means the corpus was
refused as unsafe or structurally malformed, or an atomic replacement failed. A status-2 failure
must be diagnosed rather than treated as an ordinary stale-hash repair.

After deliberately editing a fixture or reviewed expected trace, explicitly request canonical
replacement and rehashing:

```sh
uv run python tools/risk_fixture_integrity.py --corpus checkpoint_v1 --write
```

The exact author workflow is:

1. Edit the fixture and its reviewed expected trace by hand. Do not copy an answer out of the C++
   projection, Python reference, or V1 oracle and call that review.
2. Run the verification command. It exits nonzero and names every document whose canonical bytes
   or integrity metadata would change.
3. Run the same command with `--write`. The tool preserves the parsed JSON values, emits compact
   UTF-8 sorted-key JSON with exactly one final LF, recomputes both member hashes, and then computes
   `payload_sha256` over the canonical manifest payload plus its final LF.
4. Review `git diff` as evidence of the authored semantic change. A successful rehash proves only
   that the manifest describes the new bytes.
5. Run the C++ and Python conformance tests. Those executors, not the rehash command, compare the
   reviewed answers with actual risk behaviour.

For a normal checked-in corpus, `--write` is a byte-for-byte no-op. The command accepts only the
fixed repository corpus names `v1`, `checkpoint_v1`, and `all`; it does not accept an arbitrary
output directory. It refuses unsafe or nested member names, symlinks, duplicate manifest members,
missing members, unreferenced JSON documents, unsorted entries, malformed manifest structure,
duplicate JSON keys, invalid UTF-8, floating-point values, nonstandard numeric constants, and JSON
integers outside the C++ reader's 64-bit range.

All candidate bytes are prepared before replacement. Changed files are staged as temporary
siblings, flushed, and atomically installed, with `manifest.json` installed last. An interruption
cannot leave a half-written JSON file. An interruption after a member replacement but before the
manifest replacement leaves stale hashes, so the normal readers fail closed and a later `--write`
can finish the repair. This is intentionally not a transactional durable-storage protocol.
