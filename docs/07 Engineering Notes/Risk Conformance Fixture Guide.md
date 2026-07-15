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
this schema and requires a separate versioned test-only harness.
