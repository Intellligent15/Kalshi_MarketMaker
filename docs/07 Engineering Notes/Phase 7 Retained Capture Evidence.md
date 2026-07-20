# Phase 7 Retained Capture Evidence

## Status and authority

This is the B2c operator guide for the additive evidence tooling. It does not authorize product
acquisition or a venue capture. A post-implementation review found process-lifecycle and
independent-verification gaps that must first close in B2c-H. The later B2c-P package must name the
selection snapshot, activity field, three markets, reviewed acquisition responsibility, durable
storage owner, and storage destination before an operator uses the live-capture steps below.

The fixed policy is `configs/phase7/b2c_evidence_policy_v1.json`. The run is one 43,200-second,
three-market attempt on the existing `single_connection_v1` Capture V2 path. It has a 1 GiB raw
ceiling, a 5 GiB total evidence ceiling, and a 10 GiB free-space preflight. Once the first raw record
exists, the attempt is retained regardless of outcome and is never replaced by a cleaner sample.

## Approval gates

Before capture, record and review all of the following:

1. One fixed candidate-selection timestamp and the retained candidate snapshot.
2. One exact venue activity field, descending ordering, and ticker-ascending tie break.
3. Exactly three eligible production binary markets from distinct series, with no later substitution.
4. Complete opening acquisitions under the accepted evidence profile.
5. The repository human responsible for closing acquisition and review.
6. A durable storage destination, owner, read policy, and backup promise.
7. At least 10 GiB free and readable environment-only credentials.

Closing acquisitions start immediately after the capture. Their reviewed effective intervals must
cover the exact capture start and end before strict normalization may use the packages. Failure to
obtain compatible closing evidence does not erase the raw run; it limits the evidence index to the
raw or record-only boundary.

## Credential boundary

Only `KALSHI_API_KEY_ID` and `KALSHI_PRIVATE_KEY_PATH` are read. Do not put credential values,
private-key bytes, signed headers, or environment dumps in a capture specification, command line,
measurement report, or evidence index. The measurement tool hashes credential-scrubbed stdout and
stderr and does not retain their bytes. The mounted-package verifier rejects PEM private-key markers.

## Measured commands

> [!CAUTION]
> Do not use the measurement wrapper for a live capture yet. The additive `measure-v2` command now
> owns a fresh process group, bounded per-stream collection, sampler-validity reporting, preflight,
> and report publication, but B2c-H is not closed: its complete mounted role/lineage/repetition/scanner
> matrix still needs implementation and review.

The measurement wrapper starts an unchanged command in a fresh process group, samples process-tree
RSS and process count, measures declared input/output bytes, hashes scrubbed streams, and interrupts
the group if the declared output budget is exceeded. Reports are create-new sidecars and are not part
of deterministic derived outputs.

After B2c-H closure and B2c-P approval, the capture command has this shape (use `measure-v2`, never
the frozen V1 `measure` command):

```sh
UV_CACHE_DIR=/tmp/pmm-uv-cache uv run python python/pmm_phase7_evidence.py measure-v2 \
  --stage capture-v2 \
  --report data/raw/<capture-id>-measurements/capture.json \
  --package-root data/raw/<capture-id>-package \
  --raw-root data/raw/<capture-id> \
  --output-root data/raw/<capture-id> \
  --identity-file configs/phase7/b2c_evidence_policy_v1.json \
  -- uv run --env-file .env python python/kalshi_capture.py capture-v2 \
    --ticker <MARKET-A> --ticker <MARKET-B> --ticker <MARKET-C> \
    --duration 43200 --output data/raw/<capture-id>
```

This command is documentation, not present authorization to run it.

For eligible raw evidence, normalize twice from the same immutable raw path. The optional telemetry
sidecar records processed raw records and logarithmic samples of the current/peak/final duplicate
identity table without altering any normalization artifact byte:

```sh
uv run python python/pmm_phase7.py normalize-v3 \
  --input data/raw/<capture-id> \
  --output data/processed/<capture-id>-normalized-a \
  --catalog configs/product_catalog \
  --conversion-policy configs/product_catalog/conversion_policies/integer_cents_whole_contracts_v1.json \
  --instrumentation-output data/processed/<capture-id>-measurements/normalization-a-telemetry.json
```

Run features twice from the byte-identical normalization results. Run Backtest V4 twice from one
fixed config. `backtest-v4 --instrumentation-output ...` writes per-contract executable-resolution,
spawn-to-READY, lifetime, command/response, blocking-read, and trace-row measurements without
changing Result V4 bytes.

The repetition inventory must compare explicit relative member names, byte lengths, SHA-256 values,
and bytes for:

- normalization `records.jsonl`, `source_scopes.json`, `product.json`, and `manifest.json`;
- feature `features.jsonl` and `manifest.json`; and
- Result V4 `manifest.json`, all nine typed artifact streams, and every contract risk trace.

Use the same raw path because normalization V3 still includes its repository-relative input locator.
Path-independent reproduction remains B2A-17 debt.

## Evidence index

`pmm.phase7.b2c_evidence_manifest.v1` is a compact checked-in control-plane document. Its canonical
payload hash binds the fixed policy, exact 12-hour timestamps, outcome, selected markets, retention
ownership, reviewed or unavailable product-lineage state, every member hash/count/size, lineage
edges, repetition inventories, and credential-scan result.

Index-only verification remains bounded and offline:

```sh
uv run python python/pmm_phase7_evidence.py verify \
  --manifest path/to/evidence-manifest.json
```

When the immutable large package is mounted, require every byte:

```sh
uv run python python/pmm_phase7_evidence.py verify \
  --manifest path/to/evidence-manifest.json \
  --artifact-root path/to/mounted-package \
  --require-artifacts
```

Full verification rejects missing, extra, symlinked, escaping, truncated, hash-stale, count-stale,
schema-stale, lineage-stale, interval-ineligible, credential-bearing, or Result V4-inconsistent
members. It is read-only.

## Outcome table

| Outcome | Required behavior |
| --- | --- |
| Strict eligible, no disconnect | Normalize, feature, and backtest twice; verify the full package. |
| Natural reconnect or discontinuity | Retain raw; publish only record-mode normalization; features and V4 refuse. |
| Incomplete prefix | Retain raw; record-mode normalization only where identity is mechanically valid. |
| Operational refusal | Exit 2 with finalized raw evidence; do not recapture for preference. |
| Operator interruption or budget stop | Exit 130 with finalized raw evidence; record the stopping cause. |
| Failure after recorder creation | Exit 1 and retain finalized failed raw evidence. |
| Failure before recorder creation | Remove only the newly owned empty output directory. |

Natural reconnects remain Observed. Forced recovery fixtures remain Synthetic. A later snapshot
starts a new observed segment and never repairs missing history.

## Git retention

Keep large raw and derived trees outside Git under the approved immutable storage policy. Check in
the compact policy, evidence index, measurement summaries, review record, and documentation. A
complete reviewed V4 bundle may be a deliberate exception only when it is at most 10 MiB. A
manifest-only pointer does not close B2B2-06.
