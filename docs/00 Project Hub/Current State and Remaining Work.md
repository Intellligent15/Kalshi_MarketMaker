# Current State and Remaining Work

## Purpose and authority

This is the living execution roadmap for the repository. It tells maintainers and coding agents:

- what is implemented now;
- what the implementation actually proves;
- what remains unfinished;
- which work should happen next;
- which dependencies must be satisfied before later phases begin; and
- how to update the roadmap without turning aspiration into a current capability claim.

Use this document after `AGENTS.md`, `PROJECT_CHARTER.md`, and the accepted ADRs. The charter owns
the long-term vision. ADRs own architectural decisions. This document owns current status,
remaining-work order, and the handoff between bounded implementation packages.

When this document disagrees with a current accepted ADR, the ADR wins and this file must be
corrected. When an older engineering note calls something "next" but this document records it as
complete, this current-state document wins; the older note remains useful historical reasoning.

## Status snapshot

| Field | Current value |
| --- | --- |
| Last reviewed | 2026-07-16 |
| Baseline commit | `1fcc7ae` (`docs(risk): deepen fixture integrity CLI explanation`) |
| Branch state at review | `main` aligned with `origin/main` |
| C++/CTest validation | 78 tests passing |
| Python validation | 58 tests passing |
| Focused fixture-integrity validation | 17 tests passing |
| Lifecycle conformance corpus | 16 reviewed fixture pairs |
| Checkpoint conformance corpus | 26 reviewed fixture pairs |
| Current roadmap phase | Phase 7 foundation implemented; research-validity work remains |
| Next bounded package | Lifecycle-V1 temporary mutation-and-repair coverage |

These counts and commit references are evidence snapshots, not timeless guarantees. The next agent
must verify the current git state and test counts rather than copying them forward blindly.

## Status vocabulary

Use these terms consistently when updating the roadmap:

| Status | Meaning |
| --- | --- |
| Complete | Implemented, validated, documented, and within the stated boundary. |
| Current | Implemented and supported now, without implying broader roadmap completion. |
| Next | The single recommended bounded package after current work. |
| Planned | Ordered work with a known dependency and acceptance boundary. |
| Deferred | Deliberately outside the current package; not forgotten and not implied. |
| Blocked | Cannot be completed credibly without external evidence, data, authority, or infrastructure. |
| Aspirational | Part of the charter but not yet designed or implemented. |

Never use "complete" to mean that a demo exists. Never use "production" to describe a test-only
format, model-derived fill, local oracle adapter, research ledger, or exchange-only recovery path.

## Source map

Use these documents to verify or deepen a claim in this roadmap:

- [Project charter and long-term phases](../../PROJECT_CHARTER.md)
- [[00 Project Hub/Project Hub|Project navigation and working agreements]]
- [[01 Roadmap/Phase 7 Historical Replay and Backtesting|Phase 7 roadmap boundary]]
- [[02 Architecture/ADR-007 Deterministic Historical Replay and Backtesting|Historical replay architecture]]
- [[02 Architecture/ADR-008 Calibrated Execution Accounting and Research Evaluation|Execution, accounting, and evaluation boundary]]
- [[02 Architecture/ADR-009 Canonical Risk Conformance and Research Oracle Migration|Canonical C++ risk migration]]
- [[07 Engineering Notes/Phase 7 Critique|Original Phase 7 critique]]
- [[07 Engineering Notes/Research Execution Foundation Critique|Research execution critique]]
- [[07 Engineering Notes/Canonical Risk Conformance Critique|Current risk-conformance debt and reviews]]
- [[07 Engineering Notes/Canonical Risk Conformance Explained|Risk-conformance walkthroughs]]
- [[07 Engineering Notes/Risk Conformance Fixture Guide|Fixture and integrity authoring guide]]

Some critique documents are chronological and intentionally retain findings that later work closed.
In particular, older Phase 7 and research-execution notes describe Python-versus-C++ risk drift,
missing canonical risk traces, and missing runnable C++-oracle examples. ADR-009 and later
conformance work closed those gaps for new V2 research configurations. The Python implementation
remains only a V1 compatibility path and test-only reference; it is not the default for new V2
runs. Do not reopen a closed finding without checking the current implementation and later notes.

## Executive summary

The repository has a strong deterministic systems foundation:

- Phases 1 through 6 are complete within their documented boundaries.
- Phase 7 has a working V1 historical-research foundation.
- New V2 backtests use canonical C++ account risk and emit hashed risk traces.
- Lifecycle and checkpoint conformance evidence is broad and reviewed.

The repository is not yet a credible profitability, paper-trading, or live-trading system. Its
largest remaining gaps are no longer basic matching or simulation mechanics. They are:

1. authoritative venue product terms;
2. broader and recoverable observed-market data;
3. calibrated or sensitivity-tested execution assumptions;
4. real accounting, collateral, fees, and settlement;
5. compatible experiment comparison and reporting;
6. full-run recovery beyond the exchange boundary;
7. machine-learning datasets, baselines, training, and evaluation;
8. operational gateways, reconciliation, monitoring, and safety controls.

The immediate risk-conformance tail should be finished, but it must not consume the project
indefinitely. After the two highest-value remaining parity packages, work should return to Phase 7
research validity.

## What is complete now

### Phase 1: repository foundation — complete

Current evidence includes:

- CMake-based C++20 build;
- GoogleTest/CTest integration;
- formatting and test scripts;
- Python/uv workflow;
- documented repository layout and engineering standards; and
- an Obsidian-compatible documentation vault.

Boundary: this establishes reproducible local development, not deployment packaging or hosted CI
operations for every target platform.

### Phase 2: core domain types — complete

Current evidence includes:

- strongly typed identifiers;
- binary-market and contract rules;
- fixed integer price and quantity vocabulary;
- orders, trades, fills, inventory, and validation results; and
- separation between immutable domain facts and mutable matching state.

Boundary: fees, collateral, settlement, product-term ingestion, and accounting remain outside the
core types implemented in this phase.

### Phase 3: limit order book — complete

Current evidence includes:

- deterministic price-time priority;
- matching, cancellation, partial fills, and market-order expiry;
- self-trade prevention;
- dense bounded price ladders for binary prices;
- reservation of execution identifiers before mutation; and
- deterministic and randomized reference-model tests.

Boundary: the book owns live matching state only. It does not own strategy, inventory, risk,
historical-market truth, durable persistence, or venue connectivity.

### Phase 4: exchange simulator and exchange-only durability — complete

Current evidence includes:

- one book per registered contract;
- deterministic logical-time command ordering;
- global order, trade, and event identifiers;
- market lifecycle gates;
- sequenced event journals;
- checkpoints and deterministic replay;
- opt-in checksummed write-ahead command/event records;
- atomic exchange checkpoint replacement; and
- recovery through the normal matching path.

Boundary: durability protects the exchange boundary only. Coordinator, strategy, risk,
market-maker, accounting, gateway, portfolio, and complete process recovery remain separate.

### Phase 5: deterministic baseline agents — complete

Current evidence includes:

- seeded noise, momentum, mean-reversion, informed, and liquidity-taking agents;
- a deterministic coordinator and schedule;
- pull-based projections of the sequenced exchange journal; and
- checkpoint continuation for agent schedule and random state.

Boundary: agents produce intents and do not call the order book directly. They do not own risk,
inventory truth, accounting, or gateway state.

### Phase 6: baseline market making and account risk — complete

Current evidence includes:

- fixed-spread passive quoting;
- integer inventory skew;
- stale-quote cancellation and replacement;
- external account-risk admission;
- pending reservations and ingress binding;
- event-fed inventory and exposure;
- kill-switch behavior;
- checkpoint continuation; and
- ingress-correlated exchange rejection handling.

Boundary: this is a deterministic systems baseline. It does not establish optimal quoting,
calibrated fills, PnL, collateral, settlement, or venue-ready execution.

### Phase 7 foundation: historical replay and research orchestration — current

Implemented surfaces include:

- passive Kalshi raw capture;
- immutable normalization with hashes and provenance;
- fixed-point observed values and UTC logical ordering;
- duplicate and gap validation;
- Level-2 cursor projection and snapshots;
- causal spread, depth, imbalance, midpoint, and last-trade features;
- deterministic strategy scheduling;
- `no_fill_v1` and `trade_touch_v1` execution assumptions;
- explicit logical latency;
- append-only result artifacts and manifests;
- `Observed`, `Reconstructed`, `Synthetic`, and `ModelDerived` truth labels;
- canonical C++ risk for new `pmm.backtest.v2` configurations;
- hashed complete risk traces;
- an opt-in unresolved-settlement cash-flow ledger; and
- deterministic configuration and artifact hashing.

Boundary: Phase 7 is not complete as a credible research platform. The current data, execution,
accounting, compatibility, and recovery limitations below remain material.

### Canonical risk-conformance foundation — current

Implemented evidence includes:

- 16 reviewed lifecycle fixture pairs;
- direct C++, test-only Python, and frozen-V1 eligibility boundaries;
- 26 reviewed checkpoint fixture pairs;
- typed checkpoint rejection categories and fixed first-failure ordering;
- strict captured-checkpoint validation in independent C++ and Python readers;
- canonical JSON and manifest SHA-256 verification;
- a fixed-root fixture integrity authoring tool;
- named parser-refusal coverage; and
- real copied-script subprocess coverage for public CLI statuses, streams, selection, repair, and
  idempotence.

Boundary: checkpoint serialization and the Python checkpoint model remain test-only. The frozen V1
oracle remains a compatibility adapter and is ineligible for checkpoint fixtures.

## Remaining work by track

## Track A: close the current conformance tail

This track is small, local, and should end after the highest-value parity gaps are closed.

### A1. Lifecycle-V1 mutation-and-repair cycle — next

Goal: prove that the copied public integrity CLI performs the complete lifecycle-root write path,
not only lifecycle selection and stale reporting.

Required evidence:

- copy the real script and lifecycle corpus to a temporary repository;
- deliberately edit and noncanonically serialize one temporary lifecycle member;
- run `--corpus v1 --write`;
- require exact exit, stdout, and stderr behavior;
- prove only the intended member and manifest changed;
- prove canonical member bytes;
- prove the member and manifest-payload hashes;
- verify the repaired corpus successfully; and
- prove repeated `--write` is byte-identical.

Non-goal: do not change a reviewed lifecycle fixture, generate an expected trace, or duplicate the
checkpoint refusal matrix.

### A2. Remaining Python checkpoint-reader mutation parity — planned

Goal: close schema-specific rejection cases that the C++ checkpoint reader covers but the Python
reader does not yet mirror.

Required approach:

- inventory the exact asymmetric rows first;
- keep C++ and Python implementations independent;
- use canonical temporary documents with current hashes;
- require field-specific diagnostics; and
- preserve checkpoint rejection semantics and first-failure ordering.

Non-goal: do not expand production checkpoint semantics or convert the test-only JSON into a
durable production format.

### A3. Small conformance hardening — deferred

Lower-priority items:

- explicit 16-row cardinality assertions for both strict matrices;
- accepted signed and unsigned integer endpoints;
- compact current-state navigation for the long risk notes;
- a supported-platform note and Windows-specific path setup if Windows becomes supported;
- root README checkpoint discoverability;
- `--help` fragments;
- successful `all --write` coverage;
- injected subprocess translation of an atomic write failure;
- additional SHA padding-boundary vectors; and
- fuzz or property testing.

Exit rule for Track A: after A1 and A2, return to Phase 7 research validity unless new evidence
shows a higher-impact conformance defect.

## Track B: finish Phase 7 research validity

This is the highest-value project track after the conformance tail.

### B1. Authoritative product metadata — planned, high priority

The repository needs versioned venue product terms for every researched contract:

- tick and price grid;
- lot size and quantity unit;
- payout terms;
- market lifecycle and expiration;
- settlement source and rules;
- fee schedule and rounding;
- market/event/contract identity; and
- provenance and content hashes.

Acceptance gate:

- normalization and backtest manifests identify the exact product-term version;
- price and quantity conversion refuses unsupported values;
- results with incompatible product terms cannot be compared silently; and
- tests cover missing terms, incompatible terms, and boundary values.

Why it comes first: execution, accounting, and ML labels can all be internally consistent while
still being wrong for the actual venue contract if product terms are missing.

### B2. Broader observed-market coverage and recovery — planned

The current one-market foundation must expand to evidence that the pipeline generalizes:

- multiple contracts and markets;
- simultaneous source scopes;
- reconnect snapshots;
- sequence gaps and explicit recovery;
- conflicting duplicates;
- late and out-of-order records;
- longer captures;
- source-schema migration fixtures; and
- cross-market deterministic ordering.

Acceptance gate:

- every gap is either recovered with explicit evidence or propagated as incomplete data;
- a reconnect cannot silently erase provenance;
- multi-market ordering is deterministic; and
- a full-capture regression fixture pins known counts and hashes.

### B3. Experiment compatibility and reporting — planned

Build a research-control layer that can:

- run declared parameter grids;
- compare only compatible manifests;
- reject mismatched product, execution, risk, latency, or accounting contracts;
- preserve seeds and input hashes;
- produce compact experiment reports;
- retain baseline and no-fill controls; and
- report sensitivity instead of only a headline result.

Acceptance gate:

- two compatible runs can be compared reproducibly;
- incompatible runs fail with a specific reason;
- reports distinguish system metrics from economic claims; and
- identical inputs and implementation produce byte-identical artifacts.

### B4. Execution-model sensitivity and calibration — partly blocked

Before calibration, add declared sensitivity experiments across:

- acknowledgement latency;
- cancellation latency;
- fill probability;
- queue assumptions;
- partial-fill behavior;
- quote lifetime; and
- risk limits.

Credible calibration requires timestamped own-order evidence:

```text
submission -> acknowledgement -> market evolution -> fill/cancel outcome
```

Required external evidence:

- own submissions and client-order identifiers;
- venue acknowledgements and rejections;
- partial/full fills;
- cancellations and expiries;
- fees; and
- synchronized market data.

Until that evidence exists, parameters must remain `Assumed` or sensitivity-tested and fills must
remain `ModelDerived`.

Acceptance gate for calibration:

- chronological train/validation/test partitions;
- censoring-aware treatment of cancels and expiries;
- frozen parameters evaluated on later data;
- calibration and reliability metrics; and
- explicit comparison with `no_fill_v1` and `trade_touch_v1`.

### B5. Real accounting, collateral, fees, and settlement — planned, high priority

The current ledger records unresolved modeled cash flows. A credible accounting subsystem needs:

- double-entry cash and position ledgers;
- deterministic fee calculation and rounding;
- realized and unrealized PnL policy;
- marking policy;
- binary payout and settlement processing;
- collateral and buying power;
- venue sell/short semantics;
- reconciliation invariants; and
- compatibility with product-term hashes.

Acceptance gate:

- every fill and settlement balances under declared invariants;
- fee and rounding examples match sourced venue rules;
- incompatible accounting policies cannot be compared silently;
- restart/replay reproduces identical ledger state; and
- PnL is not exposed before these conditions hold.

### B6. Durable full-run continuation — planned

Exchange-only durability is insufficient for a long research run. A complete runner checkpoint
must cover:

- observed-market cursor and watermark;
- feature state;
- scheduled decisions;
- active modeled orders;
- market-maker state;
- canonical risk state;
- accounting state;
- input and configuration hashes; and
- output progress.

Acceptance gate:

- an interrupted run resumes without reinterpreting earlier data;
- later orders, fills, risk traces, ledger entries, and manifests are byte-identical to an
  uninterrupted run; and
- incompatible code, configuration, input, or product terms fail closed.

### B7. Formal schemas and protocol evolution — planned

The local whitespace oracle is intentionally narrow and frozen. Before broader process-boundary or
portfolio use, define:

- a versioned account-event request schema;
- versioned response and error categories;
- explicit escaping and framing;
- multi-account/product identity rules;
- compatibility fixtures; and
- migration behavior.

Non-goal: do not retrofit new semantics into the frozen V1 adapter.

### B8. Phase 7 performance and scale — deferred until measured

Candidate optimizations:

- streaming feature input;
- incremental order/fill/ledger/risk-trace output;
- stable priority queue for scheduled decisions;
- incremental artifact hashing;
- batched oracle requests or a native binding;
- corpus and manifest sharding; and
- multi-market worker isolation.

Gate: profile representative larger captures first. Preserve deterministic ordering and auditability
before reducing memory or process overhead.

## Track C: Phase 8 machine learning

Phase 8 is aspirational until Phase 7 data, execution, and comparison gates are credible.

### C1. Versioned ML datasets

Required work:

- dataset builders tied to normalized source and product-term hashes;
- feature-availability timestamps;
- chronological train/validation/test splits;
- leakage checks;
- missing-data and gap policies;
- label provenance; and
- dataset manifests.

### C2. Targets and non-ML baselines

Candidate targets:

- future midpoint or fair value;
- short-horizon markout;
- adverse selection;
- volatility;
- fill probability;
- order toxicity;
- spread width; and
- quote size.

Every target requires a meaningful simple baseline, such as current midpoint, rolling imbalance,
fixed volatility, historical frequency, logistic regression, or a rule-based quoting policy.

Gate: no model advances because it beats zero or a deliberately weak comparator.

### C3. Reproducible training and evaluation

Required work:

- explicit training configurations and seeds;
- chronological cross-validation;
- calibration metrics;
- cost-sensitive evaluation;
- regime and market breakdowns;
- hyperparameter records;
- model and feature compatibility hashes;
- deterministic inference fixtures; and
- drift and stability reports.

Gate: a model must improve a declared baseline on held-out data without leakage and with uncertainty
reported.

### C4. Model registry and lifecycle

Required work:

- immutable model artifacts;
- training-data and feature-schema lineage;
- approval state;
- rollback target;
- inference compatibility checks; and
- deprecation/migration rules.

## Track D: Phase 9 ML market maker

This phase integrates approved models without giving them ownership of exchange or risk state.

Planned capabilities:

- learned fair-value adjustment;
- dynamic spread width;
- inventory-aware learned skew;
- adaptive quote size;
- volatility-aware quoting;
- adverse-selection avoidance;
- confidence-aware fallback to the deterministic baseline;
- inference timeout and invalid-output handling; and
- shadow comparison against the baseline maker.

Architecture gate:

- models recommend quote parameters;
- the strategy remains deterministic for fixed inputs/model artifacts;
- external risk admission remains authoritative;
- the model cannot call the order book or gateway directly; and
- invalid or unavailable inference falls back safely.

Research gate: promotion requires held-out improvement under compatible execution and accounting
assumptions, not only better model loss.

## Track E: Phase 10 paper trading

Paper trading requires a real-time operational system, not merely a live-data backtest.

Required work:

- public live market-data gateway;
- authenticated private-account stream where available;
- venue product metadata refresh;
- real-time feature computation;
- wall-clock strategy scheduling;
- paper-order gateway;
- acknowledgement, rejection, cancellation, and fill reconciliation;
- connection-loss and reconnect handling;
- rate limits and backoff;
- clock synchronization;
- persistent audit records;
- full-process checkpoint/restart;
- monitoring and alerts;
- operator kill switch; and
- daily risk and accounting reports.

Gate: paper fills must remain explicitly labelled as paper-environment behavior. They are not live
execution evidence.

## Track F: Phase 11 demo exchange integration

Required work:

- credential and secret management;
- request signing;
- idempotent client-order identifiers;
- REST/WebSocket state reconciliation;
- retry classification;
- duplicate-request protection;
- unknown-order-state handling;
- cancel-all and emergency shutdown;
- venue rate-limit enforcement;
- startup account reconciliation;
- continuous local-versus-venue comparison; and
- retained demo execution evidence.

Gate: the system must fail closed on ambiguous remote order state and must never infer successful
cancellation or rejection without venue evidence.

## Track G: Phase 12 limited live deployment

This phase remains aspirational and requires explicit human authorization beyond repository
implementation.

Required work includes:

- small explicit capital and position limits;
- independent hard risk caps;
- verified collateral and settlement;
- cash and position reconciliation;
- operational dashboards and paging;
- incident response and runbooks;
- credential rotation;
- deployment rollback;
- process supervision;
- disaster recovery;
- audit retention;
- manual intervention controls;
- compliance and venue-rule review; and
- sustained paper/demo evidence.

Gate: live trading must not begin merely because the software builds or a demo environment works.

## Cross-cutting work

### Testing and compatibility

- Formal schema compatibility fixtures as formats mature.
- Multi-platform CI only for platforms the project intends to support.
- Deterministic replay and byte-identity tests at every persistence boundary.
- Property/fuzz testing for parsers after explicit matrices stabilize.
- Result-manifest compatibility validation.

### Security

- No credentials in configuration, fixtures, logs, or result artifacts.
- Scoped secret loading and rotation before authenticated gateways.
- Signed-request and replay protection.
- Audit-safe error reporting.
- Dependency and supply-chain review before deployment.

### Observability and operations

- Structured logs with stable event identity.
- Metrics for input gaps, decision latency, order state, reconciliation, and risk.
- Health checks and liveness/readiness policy.
- Alerts that distinguish data, strategy, risk, gateway, and accounting failures.
- Runbooks for kill switch, disconnect, inconsistent state, and recovery.

### Documentation and navigation

- Keep this file current after each bounded package.
- Add a compact risk current-state index when the long conformance notes next change materially.
- Keep root README navigation concise.
- Preserve historical critiques instead of rewriting them as if old gaps never existed.
- State observed, reconstructed, synthetic, and model-derived boundaries explicitly.

### Performance

- Benchmark before optimizing.
- Preserve deterministic order and correctness before concurrency.
- Do not introduce caches that weaken input/version identity.
- Treat throughput targets as workload-specific, not abstract claims.

## Dependency map

```text
Track A conformance tail
        |
        v
B1 product metadata -----> B5 accounting and settlement
        |                         |
        v                         v
B2 broader data -------> B3 comparison/reporting
        |                         |
        +-------> B4 execution sensitivity/calibration
                                  |
                                  v
                         credible Phase 7 research
                                  |
                                  v
                     C Phase 8 ML datasets/models
                                  |
                                  v
                     D Phase 9 ML market maker
                                  |
                                  v
                       E Phase 10 paper trading
                                  |
                                  v
                        F Phase 11 demo gateway
                                  |
                                  v
                     G Phase 12 limited live use
```

B6 full-run recovery, B7 protocol evolution, and measured B8 scaling can proceed alongside later
Phase 7 work when their dependencies become active, but paper/demo readiness requires them to be
closed at the appropriate operational boundary.

## Recommended execution order

| Order | Package | Why now |
| ---: | --- | --- |
| 1 | Lifecycle-V1 temporary mutation-and-repair cycle | Closes the current small CLI writer gap. |
| 2 | Remaining Python checkpoint-reader mutation parity | Closes the last meaningful mirrored-reader drift. |
| 3 | Product metadata ingest and compatibility hashes | Required for truthful units, accounting, and cross-market work. |
| 4 | Multi-market/reconnect/gap-recovery fixtures | Establishes broader observed-data validity. |
| 5 | Experiment compatibility and report tooling | Makes later sensitivity and model results comparable. |
| 6 | Execution sensitivity grid | Produces honest bounds before calibration data exists. |
| 7 | Own-execution capture and calibrated fill research | High value but externally evidence-dependent. |
| 8 | Accounting, fees, collateral, and settlement | Required before economic or PnL claims. |
| 9 | Durable full-run continuation | Required for long and operationally reliable experiments. |
| 10 | ML datasets and non-ML baselines | Begins Phase 8 on credible research inputs. |
| 11 | Predictive models and model registry | Follows held-out baseline evidence. |
| 12 | ML market-maker integration | Follows approved model evidence and safe fallback design. |
| 13 | Paper trading | Follows accounting, recovery, gateways, and monitoring. |
| 14 | Demo exchange integration | Follows stable paper operations and reconciliation. |
| 15 | Limited live deployment | Requires explicit human authorization and sustained evidence. |

This order is a default, not a prohibition on discovery work. A prototype may explore a later idea,
but it must remain labelled experimental and must not bypass its promotion gates.

## Current next package

The next agent should implement **Lifecycle-V1 temporary mutation-and-repair coverage**.

Recommended test boundary:

- reuse the copied-real-script subprocess harness in
  `python/tests/test_risk_fixture_integrity.py`;
- use a temporary copy of `v1/lifecycle.json` unless inspection identifies a better explicit donor;
- preserve authored values and avoid semantic expected-answer generation;
- assert exact exit status and both output streams;
- assert that only the temporary lifecycle member and manifest change;
- assert canonical bytes and both SHA-256 relationships;
- verify successfully afterward; and
- require repeated `--write` byte identity.

Expected commits:

1. `test(risk): exercise lifecycle fixture repair`
2. `docs(risk): document lifecycle fixture repair coverage`

After that package, update this file so A1 becomes complete, A2 becomes next, validation counts and
the baseline commit are current, and the recommended execution table still reflects reality.

## Non-claims that must remain explicit

Current implementation does not establish:

- calibrated fills;
- queue position or venue-equivalent execution;
- realistic cancellation priority or hidden liquidity;
- PnL correctness;
- fee, collateral, margin, or settlement correctness;
- durable full-run research recovery;
- portfolio or multi-account recovery;
- paper-trading readiness;
- authenticated gateway readiness;
- live-trading readiness; or
- profitability.

Do not remove these non-claims because a new test, fixture, model, or adapter lands. Remove or narrow
one only when its own acceptance gate has been implemented, validated, documented, and reviewed.

## Update protocol for future agents

Every bounded milestone that changes project status must update this file in its documentation
commit.

### Required update steps

1. Read `AGENTS.md`, the charter, applicable ADRs, this document, and the active implementation
   notes.
2. Verify current git status, branch relationship, tests, and relevant artifact counts.
3. Change the snapshot date and baseline commit only after the milestone commits exist.
4. Move the completed item from `Next` or `Planned` to `Complete`; do not delete its boundary.
5. Promote exactly one bounded item to `Next`.
6. Rerank work if new evidence changes impact or dependencies.
7. Preserve deferred items unless they are explicitly rejected with documented reasoning.
8. Update validation counts and corpus/artifact counts from actual commands.
9. Add links to new ADRs, guides, critiques, or explanations where they materially help navigation.
10. Recheck every readiness and economic claim before committing.

### Evidence rule

Every status promotion should name evidence such as:

- commit hashes;
- passing test commands and counts;
- reviewed fixture or data counts;
- manifest or artifact identities;
- accepted ADRs; and
- explicit limitations.

Do not use planned code, a design proposal, or a passing happy-path demo as completion evidence.

### Agent handoff checklist

A handoff prompt should include:

- repository path and `AGENTS.md` requirement;
- current clean/dirty state and recent commits;
- exact next bounded package;
- minimum files to read;
- design questions that require approval;
- acceptance conditions;
- validation commands;
- non-goals and deferred follow-ups;
- expected logical commits; and
- instruction to update this document after completion.

## How to place a new idea on the roadmap

For any new idea, answer these questions before implementation:

1. Which track and phase owns it?
2. Which current boundary does it improve?
3. What evidence or dependency must exist first?
4. Is it production behavior, test-only evidence, research infrastructure, or an experiment?
5. What claim becomes newly justified if it succeeds?
6. What claims remain unjustified?
7. Can it be completed as one bounded package with explicit acceptance tests?
8. Does it displace the current `Next` item, and if so, why is its impact higher?

Ideas may be explored out of order, but promotion into the supported system must follow the
dependency and evidence gates above.
