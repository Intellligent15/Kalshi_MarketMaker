# Phase 7 B2c-P Approval Controls

## Status and boundary

B2c-P is the current package after B2c-H offline hardening. This note documents control documents
that can be authored and verified offline. It is not approval to query a venue, acquire product
evidence, read credentials, start a capture, or retain external bytes.

The two runtime authorities are:

- `pmm.phase7.b2c_candidate_snapshot.v1`, verified by
  `pmm_b2c_operator.verify_candidate_snapshot`; and
- `pmm.phase7.b2c_run_approval.v1`, verified by
  `pmm_b2c_operator.verify_run_approval`.

Their schemas are additive historical control-plane schemas. They do not change Capture V2,
normalization V3, feature V3, Backtest/Result V4, risk, checkpoint, or frozen B2c V1 behavior.

## Gate A: permission to acquire selection and opening evidence

Before any venue access, present one proposal containing:

- candidate-query timestamp and the fixed `volume_24h_fp` activity field;
- proposed exact twelve-hour capture window and 1,800-second close margin;
- opening and closing acquisition-source specifications;
- reviewer and capture operator;
- exact absolute primary and backup storage paths;
- owner, readers, project-lifetime retention, owner-only construction writes, post-verification
  immutability, and hash-restore check; and
- confirmation that only the already documented environment credential names will be used.

Gate A requires explicit user approval. Without it, stop. Do not create a candidate snapshot by
querying the venue.

## Candidate snapshot reconstruction

After Gate A, retain every market-listing response page. The verifier rejects unsafe or duplicate
page paths, symlinks, hash drift, malformed rows, a non-null first cursor, a broken cursor chain, a
non-null final cursor, duplicate market tickers, and any candidate projection that differs from the
retained page bytes.

Eligibility is reconstructed from retained rows, not trusted from the document:

1. environment is production;
2. query is exactly the unfiltered `{"status":"open"}` base request to
   `/trade-api/v2/markets`; cursor and narrowing parameters are forbidden;
3. contracts are open binary markets;
4. close time is at least 1,800 seconds after the proposed capture end;
5. `volume_24h_fp` is parsed exactly as a nonnegative decimal;
6. ordering is volume descending, ticker ascending; and
7. greedy selection returns exactly three distinct series.

Retrieval must complete before the capture window begins. The snapshot payload hash, page hashes,
and exact selected order must all verify.

## Gate B: permission for the one capture attempt

The run approval binds the verified snapshot bytes, frozen B2c policy hash, exact selected order,
exact capture window, opening/closing acquisition-spec bytes for every ticker, operator, reviewer,
and durable storage policy. Approval must occur after snapshot retrieval and before capture start.

Opening reviewed product evidence must be complete before Gate B. Present the verified run-approval
document and product review result to the user. Gate B requires a second explicit approval. Without
it, do not invoke `measure-v2`, `kalshi_capture.py`, or any venue connector.

## After Gate B

Run at most the one fixed attempt. Never substitute a market or repeat a run for preference. Retain
the outcome once the recorder owns the first raw record. Begin closing evidence acquisition
immediately after the attempt. Strict normalization and downstream stages are permitted only if
each reviewed product interval brackets the exact observed capture; otherwise retain the raw result
and stop at the independently derived eligible stage.

The mounted Evidence V2 verifier requires candidate and approval roles for Observed evidence,
re-verifies their referenced page/spec bytes, binds the approved selection/window to the capture,
and includes those controls in the credential-scanned exact package membership.

## Current missing values

No candidate-query time, candidate pages, selected production tickers, product acquisitions,
primary/backup storage paths, capture window, or approval document has been supplied or approved.
Therefore Gate A is not satisfied and all venue-facing work remains unauthorized.
