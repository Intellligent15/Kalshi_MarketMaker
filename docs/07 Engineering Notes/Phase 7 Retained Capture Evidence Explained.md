# Phase 7 Retained Capture Evidence Explained

## The short version

B2c did not build a new market-data collector or a new backtester. Those already existed. It built
the audit layer needed to make one longer multi-market run reviewable.

That audit layer answers five questions:

1. What experiment did we commit to before seeing the outcome?
2. Which exact raw and derived bytes belong to the run?
3. Can every derived file be traced to the raw capture and reviewed product terms?
4. Did running the offline pipeline twice produce byte-for-byte identical outputs?
5. What time, memory, disk, and per-contract risk-process cost did each stage consume?

The work is intentionally split into tooling and evidence. The tooling now exists and passes offline
tests. The evidence does not: no product acquisition or live capture occurred. A deeper review also
found hardening work that must precede live operation.

## The problem we were solving

The existing Phase 7 chain was already deterministic on small fixtures:

```text
Capture V2
    -> normalization V3
    -> feature rows V2 + feature manifest V3
    -> Backtest V4
    -> Result V4 + one risk trace per contract
```

That is enough to show the software can process known inputs. It is not enough to claim that it can
process a longer real multi-market interval reliably. A credible retained run also needs immutable
raw identity, exact record counts, product-term coverage for the whole interval, complete lineage,
resource measurements, and a repeatability proof.

Without a prospective policy, an operator could keep capturing until a clean interval appears,
change markets after seeing failures, or quietly discard a reconnect. Without an evidence index,
large external files can drift away from the small checked-in description. Without sidecar
measurements, optimizing memory or oracle cost would be guesswork.

## What we added

### 1. A prospective policy

`configs/phase7/b2c_evidence_policy_v1.json` fixes the experimental choices that must not change
after observing the run:

- twelve hours, or 43,200 seconds;
- exactly three binary markets from distinct series;
- the existing one-connection Capture V2 implementation;
- one retained attempt after the first raw record;
- no fallback market substitution;
- no manufactured reconnect and no recapture for a preferred outcome;
- a 1 GiB raw ceiling, 5 GiB total evidence ceiling, and 10 GiB free-space preflight; and
- large bytes outside Git, except for a deliberately reviewed V4 bundle no larger than 10 MiB.

Why twelve hours and three markets? Twelve hours is long enough to expose duration-dependent memory
growth, disk growth, operational interruption, and ordinary venue behavior while remaining a
bounded single attempt. Three distinct series establish that the multi-market path is genuinely
used and avoid treating three contracts in one family as broad product evidence. This is regression
evidence, not a claim of venue-wide scale.

### 2. A compact evidence manifest

The evidence manifest is the package's table of contents. Each member has a role, relative path,
retention class, byte length, SHA-256 identity, optional schema, and optional JSONL record count.
The payload also records:

- the exact capture interval and selected tickers;
- the observed outcome and furthest eligible processing stage;
- reviewed product identities and effective intervals, or an honest unavailable reason;
- raw-to-derived lineage edges;
- repeated-run inventory identities;
- retention ownership and durable location; and
- the credential-scan assertion.

The payload has its own canonical hash. This makes silent edits detectable and allows a small Git
artifact to name much larger external bytes. It does not make the external store durable by itself;
the store still needs an owner and backup policy.

### 3. Two verification modes

Index-only verification checks the compact document's schema, payload hash, membership rules,
interval logic, outcome logic, and internal references. It is useful in CI when the large package is
not mounted. It deliberately reports `artifacts_verified: false`.

Mounted verification reads the external package. It checks exact membership, safe paths, no final
member symlinks, byte lengths, SHA-256 values, JSONL counts, raw ingress ordinals and count summaries,
normalization counts, feature counts, selected Result V4 descriptors, and risk trace cardinality.
Missing, extra, truncated, stale, or unsafe members fail closed.

The later B2c-H closure addresses the deeper critique: V2 mounted verification reconstructs exact
schema, identity, truth/catalog, canonical-repetition, lineage, approval, and scanner facts. The
mounted positive remains Synthetic verifier-conformance data, not observed evidence.

### 4. A generic process measurement wrapper

`python/pmm_phase7_evidence.py measure` launches an unchanged command in a fresh process group. It
records:

- wall-clock start, finish, and elapsed time;
- process-tree count and summed RSS samples;
- declared input bytes and initial, peak, and final output bytes;
- exit code and termination reason;
- hashes of credential-scrubbed stdout and stderr;
- hashes of explicitly named identity files; and
- OS, architecture, Python version, CPU count, Git revision, and dirty state.

Why measure the process tree rather than Python alone? Backtest V4 launches C++ risk-oracle children.
Measuring only the parent would systematically omit part of the cost.

The report is a create-new sidecar. Measurement timestamps and RSS values are nondeterministic, so
they must never enter canonical normalization, feature, result, or risk-trace bytes.

The current sampler uses host `ps` and recursively scans declared output paths. Its RSS is a useful
descriptive number, not a portable benchmark. B2c-H closes the audited teardown, invalid-sample, and
budget-accounting defects in additive Measurement V2. The documented live command still requires
B2c-P Gate B approval.

### 5. Normalization duplicate-state telemetry

Normalization owns a dictionary called `sequence_payloads`. Its key is a scoped sequence identity;
its value is the payload hash already seen for that identity. This is how identical duplicates can
be skipped and conflicting duplicates can be refused.

The dictionary currently grows with unique sequenced input. Generic RSS cannot tell how much of a
process belongs to that table, so optional telemetry records:

- processed raw records;
- final and peak unique sequence identities;
- identical duplicates skipped; and
- logarithmic samples when the table reaches powers of two.

Logarithmic sampling avoids creating a second event-sized telemetry file. It measures B2A-10 but
does not solve the linear-memory behavior.

### 6. Per-contract risk telemetry

Backtest V4 owns one canonical C++ risk process per contract. Optional risk telemetry records, for
each product:

- executable-resolution time;
- spawn-to-READY time;
- process lifetime;
- commands sent and responses received;
- time blocked waiting for responses; and
- canonical trace rows.

This isolates B2B2-05. If startup or synchronous IPC is expensive, later work can compare batching,
process reuse, or native integration. B2c does not make that architectural change before evidence.

## How a run is supposed to proceed

The intended lifecycle is deliberately gated:

```text
B2c-H hardening
    -> B2c-P approval packet
    -> opening reviewed product evidence
    -> one fixed Capture V2 attempt
    -> immediate closing product evidence and review
    -> classify the observed completeness
    -> process only as far as eligible
    -> repeat eligible offline stages
    -> build and independently verify the retained package
    -> review measurements and close only supported findings
```

B2c-P must pin the selection timestamp, exact activity metric, ticker-ascending tie break, three
selected markets, acquisition sources, reviewer, durable owner/location/backup policy, operator,
and capture window. The selection snapshot is retained so the operator cannot substitute easier
markets later.

Opening and closing product packages bracket the exact capture interval. Strict processing is
allowed only when reviewed effective intervals cover the whole run for all three markets. Product
evidence is not inferred from market messages.

## Why partial evidence remains valuable

Real captures do not owe us a clean outcome. The package distinguishes:

| Observed outcome | What is retained | Furthest honest claim |
| --- | --- | --- |
| Complete continuous interval | Raw plus the full eligible repeated chain | Backtest V4 if product coverage is complete |
| Natural reconnect or sequence gap | Raw and discontinuity-aware normalization where supported | Record-only; no strict features/backtest |
| Incomplete prefix | Raw and mechanically valid prefix description | Raw or record-only |
| Completed but unusable/refused | Finalized raw metadata and frames | Raw evidence of the refusal |
| Operator interruption | Finalized interrupted raw package | Raw incomplete evidence |
| Failure after recorder creation | Finalized failed raw package | Raw failure evidence |
| Failure before recorder ownership | No invented evidence; remove only newly owned empty output | Failure record outside a capture package |

A later snapshot can start a new observed segment. It cannot reconstruct missing history. Natural
reconnects stay `Observed`; forced recovery fixtures stay `Synthetic`. This is why a discontinuous
run is retained but refused by strict feature and backtest consumers.

## How determinism is tested

For an eligible capture, normalization runs twice from the same immutable raw locator. Features run
twice from equivalent normalized outputs. Backtest V4 runs twice from one fixed configuration.

The intended repetition proof compares explicit relative names, byte lengths, SHA-256 values, and
bytes for:

- normalization records, source scopes, product map, and manifest;
- feature rows and manifest; and
- Result V4 manifest, nine typed artifact streams, and every contract risk trace.

Instrumentation-on/off unit tests already prove that telemetry does not alter canonical artifact
bytes. B2c-H must still add the canonical inventory builder and mounted recomputation needed to make
the retained repetition claim independently auditable.

## What the tests currently prove

The focused B2c suite uses only temporary offline fixtures. Together with the existing Phase 7 and
capture suites, it proves:

- the fixed policy validates against its schema;
- index and mounted verification do not mutate a package;
- stale payloads, ticker order, product membership, duplicate roles, bad edges, false repetition
  verdicts, and inconsistent outcomes are refused;
- missing, truncated, count-stale, raw-count-stale, final-member-symlinked, Result V4-stale, and
  extra members are refused;
- measurement reports are create-new and output budget overrun signals the process group;
- Capture V2 output-exists, interruption, failure, and cleanup behaviors are characterized; and
- optional normalization and risk telemetry leave canonical outputs byte-identical.

The critique records the gaps precisely: operator-interrupt teardown, stage/outcome matrices,
independent inventory/lineage reconstruction, member runtime/schema parity, aggregate storage,
sampler failure, credential scanning, telemetry publication failure, and positive partial packages.

## Why this design instead of a redesign

Changing capture or streaming while collecting evidence would mix two questions: “does the current
system work for a longer run?” and “does a new architecture work?” The chosen design keeps the first
question answerable.

Sidecars isolate nondeterministic measurements from deterministic research artifacts. A compact
manifest keeps Git reviewable while binding external bytes. One prospective policy prevents
selection bias. Strict completeness refusal preserves the meaning of existing downstream formats.
Separate normalization and risk telemetry name the actual state owners rather than guessing from
whole-process RSS.

This is the smallest credible architecture for B2c. Its first implementation still needs the
hardening in the critique before it is safe to operate.

## What this work does not prove

Even after a successful retained run, B2c will not prove:

- venue-global sequence scope or recovery of missing history;
- hidden orders, queue position, or calibrated fills;
- fees, PnL, collateral, margin, or settlement correctness;
- portfolio risk or cross-market alpha;
- crash-atomic full-run publication or recovery;
- scaling beyond the measured three-market/twelve-hour point;
- paper-trading or live-order readiness; or
- profitability.

Those boundaries are intentional. A trustworthy research system is built by making one narrow claim
at a time and retaining enough evidence for another person to challenge it.

## Current status

The work completed the first offline implementation, tests, schemas, operator guide, and
documentation. The deeper review now sets the order:

1. B2c-H closes process-lifecycle and evidence-verification blockers.
2. B2c-P separately approves and acquires contemporaneous product evidence and the one capture.
3. The retained package closes only the measurements and evidence claims it actually supports.
4. B3 follows only after the applicable B2c gates close.
