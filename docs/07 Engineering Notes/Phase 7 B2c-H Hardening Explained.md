# Phase 7 B2c-H Hardening Explained

## The short version

B2c-H is the safety inspection and evidence audit that must happen before anyone uses the B2c
tooling for the one real twelve-hour capture.

## What is implemented so far

The first V2 slice now exists: a new measurement supervisor owns a child process group, records
sampling validity rather than inventing zero RSS, drains each stream under a 64 MiB limit, and
publishes a V2 report. A separate V2 verifier path has initial inventory and credential-scanner
building blocks. This is useful hardening, but it is not the whole inspection: the exhaustive
mounted role, lineage, repetition, and scanner tests are still required before any capture work.

The earlier B2c package built useful offline tools, but a deeper review found two dangerous gaps:

1. stopping the wrapper did not guarantee that the measured child and its descendants stopped; and
2. some evidence claims were declarations that the verifier trusted instead of facts it rebuilt.

The approved B2c-H design would fix those gaps without changing how market data, features,
backtests, or risk work. It would strengthen the control plane around the pipeline. The design is
documented, critiqued, and approved for bounded implementation. The initial V2 slice is now
implemented; the complete acceptance matrix remains open.

## What we did in the design review

We first verified the repository state and authority order. The living roadmap identified B2c-H as
the next bounded package. Accepted ADRs defined which artifact meanings must remain frozen. Source
and tests showed what the current tooling actually does.

We then reviewed the problem through three connected lenses:

- process lifecycle and resource measurement;
- evidence membership, repetition, lineage, and schemas; and
- compatibility, security, tests, CLI behavior, and documentation.

Graphify helped locate the main ownership center and related schemas/tests, but every useful lead was
checked against source. The local graph was known to be stale and incomplete, so it was never treated
as proof.

Finally, we reconciled the review into one design. We chose additive formats and a small supervisor
boundary instead of redesigning the accepted pipeline.

## Why the process problem matters

Imagine starting a twelve-hour capture through a wrapper and pressing Ctrl-C because something looks
wrong. The wrapper exiting is not enough. If the capture or one of its descendants keeps running, it
can continue writing data after the operator believes the attempt stopped.

The current wrapper starts a new process group, which is a good foundation. The missing piece is an
owner that remains responsible until the group is gone.

B2c-H would therefore give the wrapper an explicit shutdown lifecycle:

```text
ask politely with SIGINT
    -> wait a bounded time
    -> request termination with SIGTERM
    -> wait again
    -> force termination with SIGKILL
    -> reap the direct child
    -> confirm no live non-zombie process remains in the group
    -> publish the measurement report
```

The order matters. SIGINT gives Capture V2 a chance to finalize honest interrupted raw evidence.
SIGTERM and SIGKILL prevent a broken or signal-resistant command from running forever. Publishing
the report last ensures that the report describes the final shutdown rather than an intermediate
guess.

The portable limit is also explicit: a parent can directly reap only its own child. It can still use
a successful process-table sample to confirm that no live non-zombie process remains in the process
group. A zombie can no longer execute or write, but is recorded because this supervisor may not own
its reap. The wrapper cannot contain a grandchild that deliberately escapes into a new session, so
retained-evidence commands are not allowed to daemonize.

## Why child outcome and wrapper outcome are separate

There are several different reasons a measured command can stop:

- the child completed successfully;
- the child refused an invalid request;
- the child failed;
- the operator interrupted it;
- the raw, aggregate, or stream budget was exceeded;
- the sampler failed; or
- the wrapper itself failed.

Those are not interchangeable. The measurement report records both the child's exact exit and the
wrapper's stop reason. The CLI uses the repository's established convention: successful JSON goes to
stdout only on exit zero; nonzero paths keep stdout empty and put a coded diagnostic on stderr.

The wrapper does not take ownership of stage outputs. Capture V2 still decides whether interrupted
raw evidence can be finalized. Normalization, features, and backtesting still own their temporary
output cleanup. If escalation was forced, the report says finalization is unknown instead of calling
the output clean.

## Why zero RSS must not mean “the sampler broke”

Today, failure to run `ps` returns zero processes and zero RSS. That looks like a valid, wonderfully
cheap run even though no measurement occurred.

B2c-H would replace that ambiguity with explicit validity:

- successful and failed sample counts;
- sampler identity;
- stable error category;
- nullable peaks; and
- a measurement-valid flag.

Zero becomes valid only when a successful sample actually observes zero. If the sampler fails, the
measurement becomes invalid and the supervisor shuts the group down safely. This is intentionally
strict because a twelve-hour evidence run with missing resource measurement cannot support the
claim it was intended to make.

## How storage accounting becomes honest

The fixed policy already says:

- raw evidence may use at most 1 GiB;
- the complete retained package may use at most 5 GiB; and
- at least 10 GiB must be free before starting.

The old wrapper measured only caller-listed output paths. The new design names three different facts:

1. raw bytes under the raw root;
2. aggregate retained-package bytes, including upstream files that already exist; and
3. stdout/stderr bytes produced while the command runs.

The raw and aggregate limits are absolute: equality is allowed and one byte over stops the group.
Pre-existing bytes count toward the ceiling and are also reported separately from new growth.

Temporary log files are removed entirely. The wrapper drains stdout and stderr through bounded
streaming hash collectors. This prevents a noisy child from filling the temporary filesystem while
preserving the existing rule that command output bytes are not retained.

## Why a hash is not enough evidence

A payload hash proves that a declaration has not changed. It does not prove that the declaration was
true when written.

The old repetition record could say “run A inventory hash equals run B inventory hash,” and the
verifier checked that the Boolean agreed with those two strings. It did not rebuild either inventory.

B2c-H would make the verifier do the work:

1. enumerate both mounted output trees;
2. sort the same relative paths deterministically;
3. record length and SHA-256 for every file;
4. reproduce both retained inventory documents;
5. compare path, length, and hash; and
6. finally compare exact bytes.

The final byte comparison makes the intended claim easy to state: the two eligible offline runs
produced the same named files with the same bytes.

## How lineage is reconstructed

Think of lineage as a chain of receipts:

```text
raw frames + raw metadata
    -> normalization records/scopes/product map/manifest
    -> feature rows + feature manifest
    -> Backtest V4 configuration
    -> Result V4 streams + per-contract risk traces
```

Each arrow must be proven from the mounted artifacts. The evidence manifest may describe the arrows,
but the verifier derives the required graph independently and requires an exact match.

Product terms receive the same treatment. A list of product hashes is not enough. Reviewed source,
terms, review, conversion policy, and version-required evidence members must be mounted and passed
through the existing offline product verifier. Their derived identities must then agree everywhere
they appear downstream.

Measurements and telemetry are also part of the graph. A normalization measurement must name the
exact raw inputs and normalization outputs it measured. Risk telemetry must agree with the mounted
Backtest V4 config, products, contracts, and traces.

## Why stage membership is exact

A package should contain exactly what its claimed furthest stage requires—no less and no unexplained
later-stage files.

- Raw packages contain the policy, raw bytes/metadata, capture measurement, and scanner report.
- Record-only normalization adds the discontinuity-aware normalization set and its repeatability
  evidence, but forbids features and backtests.
- Strict normalization additionally requires a complete observed interval and reviewed product
  coverage.
- Feature evidence adds feature rows, manifest, measurement, and repetition inventories.
- Backtest evidence adds the config, Result V4 manifest, nine typed streams, risk telemetry, and one
  trace per contract.

Interrupted, failed, and operational-refusal captures may remain valuable at raw or record-only
boundaries. They are not upgraded into strict evidence just because downstream-looking filenames
exist.

## How credential scanning changes

The old verifier looked for two private-key markers and trusted a passed assertion in the manifest.
That was useful defense-in-depth, not an independently verified scan.

The new deterministic scanner would check mounted filenames and bytes for:

- common private-key PEM variants;
- authorization and bearer headers;
- API-key, token, password, and secret assignments; and
- suspicious secret/private-key filenames.

It deliberately avoids broad entropy guessing because hashes and public identifiers are expected in
this package. The retained clean report contains scanner and payload-inventory identities, never
secret bytes or filenames. The verifier reruns the deterministic scan. A separate authoring-time
check searches for the then-configured credential values in memory, but later verification does not
need or retain those historical secrets. The manifest and scanner report are outside the scanner's
self-referential inventory and are scanned directly after assembly. Tests use synthetic canaries
only.

## Why additive successors are worth the extra files

The new facts cannot be added honestly to an old schema without changing what old bytes mean. This
repository has repeatedly chosen additive successors for exactly that reason.

The cost is more schema names and compatibility branches. The benefit is auditability: a V1 report
continues to mean what it meant when created, while a V2 report makes stronger, explicit claims.
The same rule applies to the command line: the existing `measure` and `verify` commands remain
available with their old behavior, while operator-ready packages use new `measure-v2` and
`verify-v2` commands with stronger semantics. Existing automation is therefore not silently
reinterpreted.

## What remains intentionally unfinished

B2c-H does not create the evidence it is designed to verify. Product coverage, durable storage,
operator/window approval, and the one real capture remain B2c-P.

It also does not optimize the duplicate table, stream Result V4, reuse risk-oracle processes, make
telemetry publication crash-atomic, or create path-independent normalization identities. Those items
remain measured or deferred because changing them before obtaining measurements would mix evidence
collection with architectural redesign.

## Why B2c-P remains blocked

Before B2c-H, an operator could stop the wrapper while the process group continued, and a retained
package could contain internally consistent declarations that were not independently reconstructed.
That is too weak a foundation for a one-attempt live evidence package.

B2c-P becomes next only after the supervisor, verifier, schemas, role matrix, scanner, named tests,
compatibility gates, and documentation all close. B3 remains later because research reporting should
not be built on evidence whose operational and verification boundaries are still open.
