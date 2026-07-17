# Phase 7 Historical Replay and Backtesting

## Delivered V1

Phase 7 treats the Kalshi WebSocket capture as an immutable Level-2 observed-market source. `python/pmm_phase7.py` normalizes raw frames, materializes causal observed-book features, and runs a configured synthetic-fill or no-fill backtest.

The observed stream never calls `ExchangeSimulator` or `LimitOrderBook`. The C++ exchange retains its ownership of simulator matching, IDs, lifecycle, checkpointing, and command replay.

## First captured source

`data/raw/wsh-tor-wsh2-3h/` is an ignored local source capture for `KXWNBASPREAD-26JUL14WSHTOR-WSH2`. It completed normally after 10,800.087 seconds with one snapshot, 19,832 deltas, 125 trades, no disconnects, no malformed JSONL records, and no sequence gaps.

The raw `frames.jsonl` SHA-256 is `6983165c9926693dc53a0f8ec09981dc86b9740608b2bf406da829126459c4c6`. The normalizer records raw-file/output hashes, source fidelity, ordering policy, and limitations. Trade messages omit the market UUID, so they are bound to the already established capture identity and labelled `capture_bound`.

## Causality and replay rules

- Canonical events preserve local receive time, source sequence, source timestamp when present, and raw ingress order.
- Sequence gaps, corrupt data, conflicting duplicates, ticker changes, and negative displayed quantities fail normalization by default. Identical duplicate source events are idempotently skipped and recorded.
- Logical time is monotonic source `ts_ms` where available, otherwise local receive time; ingress order is the deterministic tie-breaker.
- Features only use state applied through their own watermark. Future returns and post-watermark book state are not inputs.
- The projection is Level-2 reconstruction, not queue, individual-order, cancellation, or hidden-liquidity truth.

## V1 execution boundary

`trade_touch_v1` fills a simulated buy when an observed trade's YES price is at or below its quote, and a sell when it is at or above its quote. It allocates public-trade quantity to eligible simulated orders by stable order ID. This is `ModelDerived`, not an observed fill or execution-realism claim.

`no_fill_v1` is the execution-free control. Neither model includes queue priority, venue acknowledgements, hidden liquidity, fees, PnL, collateral, settlement, paper trading, or live execution. Checked-in configs use 100 ms logical market-data, decision, and order latency; one-contract quotes; 30-second quote expiry; and a 10-contract absolute-position limit.

## Initial generated outputs

The ignored normalized dataset has 19,958 events and the feature dataset has 19,958 causal rows. The normalized event SHA-256 is `8e869653a341790b15311bb8a483b3bf71bb73e64b84c53e33289aa12e82d9cd`.

The first `trade_touch_v1` run produced 1,213 decisions, 2,074 accepted synthetic orders, 76 model-derived fills, 352 position-limit rejections, and final synthetic inventory of -10 contracts. The no-fill control produced 1,213 decisions, 2,426 accepted synthetic orders, zero fills, and zero final inventory. These are model outputs, not PnL or evidence of executable performance.

## Authoritative product-term path

Track B1a adds an offline-reviewed catalog under `configs/product_catalog/`. The first package
retains exact official market, series, event-metadata, fixed-point, settlement, and fee-rounding
source bytes. Its market-specific terms are a reviewed projection, not a copy of WebSocket
metadata. Runtime verification checks canonical JSON, every retained source hash, exact package
membership, safe paths, source-to-terms field agreement, review hashes, effective-time coverage,
catalog overlap, and conversion compatibility.

`normalize-v2` writes the same canonical observed events as V1 for the known capture while adding
`pmm.historical.product_map.v2`, the reviewed package, the conversion policy, and a V2 manifest.
`features` detects that lineage and emits a V2 feature manifest. `pmm.backtest.v3` requires those
manifests and exact product hashes before running the canonical C++ risk oracle. `verify-lineage`
can audit the full configuration and optional result directory without network access.

The validated known-capture V3 no-fill run retained 19,958 normalized events, 19,958 feature rows,
1,213 decisions, 2,426 accepted orders, 2,424 cancellations, and zero fills. Event, feature, and
order hashes stayed byte-identical to the corresponding earlier generated data. The added metadata
does not reinterpret or mutate V1/V2 artifacts.

## Deferred work

- The observed projection has an in-memory checkpoint/restore boundary verified by continuation tests. Persisted projection/backtest checkpoints remain deferred; current restart is deterministic full replay from immutable normalized input and makes no durable live-run claim.
- Contemporaneous pre-capture product snapshots, retained linked contract/certification PDF bytes,
  additional reviewed markets, source-schema migration, multi-product ordering, snapshot recovery
  after gaps, and long-term retention/compaction.
- Calibrated latency, queue-aware or externally observed fills, fees, PnL, collateral, settlement, portfolio risk, ML models, paper trading, and live gateways.

The first post-V1 risk and unresolved-cash-flow foundation is recorded in
[[02 Architecture/ADR-008 Calibrated Execution Accounting and Research Evaluation]]. See
[[07 Engineering Notes/Research Execution Foundation Explained]] for the plain-language walkthrough
and [[07 Engineering Notes/Research Execution Foundation Critique]] for the ranked follow-up register.
Product-term ownership and lineage are specified by
[[02 Architecture/ADR-010 Authoritative Product Terms and Artifact Lineage]].
See [[07 Engineering Notes/Authoritative Product Terms Explained]] for the deeper what/how/why
walkthrough and [[07 Engineering Notes/Authoritative Product Terms Critique]] for the current
severity-ranked limitations and follow-up order.

## B1b-1 integrity hardening

Commits `dbd6fd8` and `6d489e3` close the pre-second-product integrity package. Product terms,
review, and catalog intervals must now match exactly. Catalog lookup uses its own verified interval
rather than silently selecting by the review interval. The checked-in retrospective package
already met this contract, so its source, terms, review, and catalog hashes did not change.

New acquisition specifications emit source-manifest V2 with observed timestamps, redirect history,
final URL, response status and selected headers, media type, byte count, incremental SHA-256, and
tool version. Every redirect remains within an approved first-party HTTPS allowlist. JSON, text,
PDF, per-source, package, redirect, and timeout policies are bounded, and failures remove temporary
files and directories before any final package is published. Tests use fake sessions and never
contact a live venue.

The formal schemas now define the complete nested structures that runtime can validate locally.
A reviewed parity matrix checks positive artifacts and one-defect negatives through both schema
and runtime validation. Cross-file hashes, source projection, interval equality, arithmetic, and
filesystem membership remain named runtime-only rules. Public product and lineage CLIs have tested
success/refusal exit codes and stdout/stderr separation.

Focused product-term validation now passes 18 tests, the complete Python suite passes 77 tests,
and all 78 CTest tests remain passing. The next package is B1b-2: acquire a contemporaneous source
bundle including required linked documents, approve a second product family, and prove additive
catalog refresh entirely offline after acquisition.

## B1b-2 contemporaneous evidence

The reviewed `KXHMONTH-26JUL` climate package retains byte-identical opening and closing
observations of eight required sources, including contract and certification PDFs. Its exact
half-open interval is bounded by opening completion and closing start. Source-manifest V3 binds an
immutable acquisition policy, evidence-map V1 resolves structured and document anchors, review V2
records repository-declared responsibility, and product-terms V2 honestly permits the official
empty secondary-rules value.

The catalog now selects between two reviewed markets while the B1a package and existing normalized,
feature, configuration, result, lifecycle, checkpoint, and risk artifacts remain unchanged. The
new focused tests remain entirely offline. B1c document-anchor truth and generic source completeness
is the next hardening gate; B2 broader observed-market coverage and recovery follows it. This
metadata package does not implement multi-market replay or reconnect handling.

## B2a multi-scope capture and reconnect normalization

Commits `520d0a0`, `399e500`, `48f2a25`, and `a04b0c1` add the versioned capture, normalization,
offline fixture, and product-lineage compatibility boundaries. Raw capture V2 records explicit
ingress, connection, request, acknowledgement, channel, SID, membership, and sequence-domain
facts. Normalization V3 keeps discontinuities in the ordered record stream and invalidates books
across connection gaps. The post-implementation review found that sequence gaps in a shared or
unknown scope currently under-invalidate possible market members; B2a-1 must close that defect.

One later snapshot can start a new valid observed segment; it never proves the missing interval.
Default normalization refuses discontinuous/incomplete input, record mode preserves it honestly,
and feature generation refuses V3 until B2b. Existing V1/V2 normalized and feature artifacts and
V1/V2/V3 configuration/result artifacts are unchanged.

Focused validation passes 11 capture tests, 26 Phase 7 tests, and 42 product-term tests. The full
Python suite passes 118 tests; all tests remain offline. B2a-1 truth-boundary hardening is next,
then B2b multi-market segment-aware projection, features, and replay. B2c owns the retained
full-capture regression.
