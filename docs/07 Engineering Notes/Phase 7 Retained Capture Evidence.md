# Phase 7 Retained Capture Evidence

## Status and authority

This is the B2c operator guide for the additive evidence tooling. It does not authorize product
acquisition or a venue capture. B2c-H offline hardening is closed. B2c-P is current, but it has two
explicit human gates before any capture: Gate A before venue access and candidate/product evidence
acquisition, and Gate B after the retained candidate snapshot and opening evidence are verified.

The fixed policy is `configs/phase7/b2c_evidence_policy_v1.json`. The run is one 43,200-second,
three-market attempt on the existing `single_connection_v1` Capture V2 path. It has a 1 GiB raw
ceiling, a 5 GiB total evidence ceiling, and a 10 GiB free-space preflight. Once the first raw record
exists, the attempt is retained regardless of outcome and is never replaced by a cleaner sample.

## Approval gates

Before Gate A, propose and obtain explicit user approval for:

1. The candidate-query time and fixed `volume_24h_fp` activity field.
2. The exact proposed twelve-hour capture window.
3. The complete opening/closing acquisition-source plan and responsible reviewer/operator.
4. Exact absolute primary and backup storage paths, owner, readers, and retention policy.

Do not access the venue or acquire candidate/product bytes before Gate A.

After Gate A, retain the complete paginated market-listing responses and verify the candidate
snapshot with `pmm_b2c_operator.verify_candidate_snapshot`. The verifier requires the open-market
endpoint/status query, first-to-final cursor chain, page hashes, exact candidate projection, close
margin, descending fixed-point volume with ticker tie-break, and exactly three distinct series.

Before Gate B, record and verify all of the following:

1. One fixed candidate-selection timestamp and the retained candidate snapshot.
2. One exact venue activity field, descending ordering, and ticker-ascending tie break.
3. Exactly three eligible production binary markets from distinct series, with no later substitution.
4. Complete opening acquisitions under the accepted evidence profile.
5. The repository human responsible for closing acquisition and review.
6. A durable storage destination, owner, read policy, and backup promise.
7. At least 10 GiB free and readable environment-only credentials.

The `pmm.phase7.b2c_run_approval.v1` document binds the candidate snapshot, fixed policy, exact
selection/window, opening/closing acquisition-spec paths and hashes, people, and durable storage.
Verify it with `pmm_b2c_operator.verify_run_approval`, then present it for explicit human Gate B
approval. Do not start the capture before Gate B.

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
> Do not use the measurement wrapper for a live capture until B2c-P Gate B is explicitly approved.
> B2c-H closes offline tooling risk only; it is not venue, product-evidence, storage, credential, or
> capture authorization.

The measurement wrapper starts an unchanged command in a fresh process group, samples process-group
RSS/count, accounts for raw roots and the complete package, drains stdout and stderr concurrently
under independent 64 MiB limits, and owns bounded SIGINT -> SIGTERM -> SIGKILL escalation, direct-
child reap, live-group quiescence, and create-new report publication. Reports are control-plane
sidecars and are not part of deterministic derived outputs.

After B2c-H closure and explicit B2c-P Gate B approval, the capture command has this shape (use
`measure-v2`, never the frozen V1 `measure` command):

```sh
UV_CACHE_DIR=/tmp/pmm-uv-cache uv run python python/pmm_phase7_evidence.py measure-v2 \
  --stage capture-v2 \
  --report data/raw/<capture-id>-package/measurements/capture.json \
  --package-root data/raw/<capture-id>-package \
  --raw-root data/raw/<capture-id>-package/raw \
  --output-root data/raw/<capture-id>-package/raw \
  --identity-file data/raw/<capture-id>-package/control/evidence-policy-v2.json \
  -- uv run --env-file .env python python/kalshi_capture.py capture-v2 \
    --ticker <MARKET-A> --ticker <MARKET-B> --ticker <MARKET-C> \
    --duration 43200 --output data/raw/<capture-id>-package/raw
```

This command is documentation, not present authorization to run it.

All accounting roots, identity files, and the report must resolve below one package root. Exact
`raw-root == output-root` is allowed only for `capture-v2`, whose raw root must be absent or empty at
preflight. Derived stages may reference pre-existing immutable raw roots, but duplicate roots,
cross-class equality, ancestor/descendant overlap, symlinks, and escapes refuse before spawn.

On operator interruption, send no extra signals outside the wrapper: the first interrupt requests
cooperative SIGINT finalization and the second accelerates escalation. Resume only with a new package
root after reviewing the coded stderr diagnostic and any published report. Never overwrite a final
or `.partial` report. A published report owns measurement facts only; the child stage still owns its
canonical output and cleanup semantics.

For eligible raw evidence, normalize twice from the same immutable raw path. The optional telemetry
sidecar records processed raw records and logarithmic samples of the current/peak/final duplicate
identity table without altering any normalization artifact byte:

```sh
uv run python python/pmm_phase7.py normalize-v3 \
  --input data/raw/<capture-id>-package/raw \
  --output data/processed/<capture-id>-normalized-a \
  --catalog configs/product_catalog \
  --conversion-policy configs/product_catalog/conversion_policies/integer_cents_whole_contracts_v1.json \
  --instrumentation-output data/processed/<capture-id>-measurements/normalization-a-telemetry.json
```

The production run must wrap each normalization, feature, and Backtest V4 invocation in its own
`measure-v2` call, with a stage-specific report below the same retained package root and identity
files naming that stage's exact mounted inputs and outputs. The bare pipeline command above shows
the child arguments only; it is not the complete measured-run command. Each repeated output also
needs its own nonoverlapping output root and measurement report.

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

New packages use the additive mounted verifier:

```sh
uv run python python/pmm_phase7_evidence.py verify-v2 \
  --manifest path/to/mounted-package/control/evidence-manifest-v2.json \
  --artifact-root path/to/mounted-package \
  --require-artifacts
```

Review the retained `pmm.phase7.b2c_credential_scan.v1` document only after `verify-v2` returns exit
zero. The verifier recomputes the scanner over mounted payload bytes and separately scans the
manifest/report control bytes; a self-asserted `clean` status is insufficient. Never test with real
credential values. Use synthetic canaries only, and treat any `EvidenceCredentialLeak` or
`EvidenceV2CredentialScanMismatch` as a stop requiring a new reviewed package.

Measurement comparisons are valid only when sampler identity, platform/architecture, Python and
toolchain, policy controls, stage identities, and sample interval match. RSS is host-`ps` KiB under
`ps-pid-pgid-rss-state-v1`; it is not a portable benchmark or a cross-machine performance claim.
See [[07 Engineering Notes/Phase 7 B2c-H Refusal Codes]] for V2 status and stream behavior.

## Outcome table

| Outcome | Required behavior |
| --- | --- |
| Strict eligible, no disconnect | Normalize, feature, and backtest twice; verify the full package. |
| Natural reconnect or discontinuity | Retain raw; publish only record-mode normalization; features and V4 refuse. |
| Incomplete prefix | Retain raw; record-mode normalization only where identity is mechanically valid. |
| Post-recorder Capture V2 operational refusal | Exit 2 with finalized raw evidence; do not recapture for preference. Preflight wrapper refusals spawn no recorder and create no report or raw evidence. |
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
