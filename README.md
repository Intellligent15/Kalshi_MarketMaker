# Prediction Market ML Market Maker

A C++20 research platform for simulating prediction markets and developing progressively
more sophisticated market-making strategies. The project prioritizes correctness,
reproducibility, modularity, testability, and documented engineering decisions.

Canonical repository: [Intellligent15/Kalshi_MarketMaker](https://github.com/Intellligent15/Kalshi_MarketMaker)

Phase 4 adds `pmm_sim`: a deterministic exchange event loop around one book per registered
contract. It owns logical-time command ordering, global order/trade/event IDs, lifecycle gating,
in-memory event journals, checkpoints, replay, and aggregate depth-change events. The book still
owns only live matching state; inventory, risk, durable persistence, and strategy consumers remain
outside the matching boundary.

Phase 5 adds `pmm_agents`: a deterministic coordinator for seeded noise, momentum,
mean-reversion, informed, and liquidity-taking baselines. Agents consume pull-based projections
of the sequenced exchange journal and return intents; they never call an order book or mutate the
exchange directly. Risk, inventory, PnL, durable persistence, and gateway layers remain deferred.

Phase 6 adds `pmm_risk` and `pmm_market_maker`. A market maker produces identity-free,
post-only limit intents; an external account-risk projection binds the authorized `TraderId`,
reserves worst-case inventory exposure, and consumes the globally sequenced exchange journal.
The baseline maker supports fixed-spread quotes, integer inventory skew, stale-quote cancellation,
kill switches, checkpoint continuation, and ingress-correlated exchange rejections. Fees, PnL,
collateral, settlement, durable recovery, and paper-trading claims remain deliberately deferred.

The Phase 7 foundation adds opt-in local exchange durability: a versioned, checksummed
write-ahead command/event journal and atomic exchange checkpoints. `create_durable`,
`persist_checkpoint`, and `recover_durable` protect only the exchange boundary; coordinator,
risk, market-maker, accounting, and paper-trading recovery remain separate work. Historical
market-data normalization, causal features, and backtesting are now in progress under ADR-007.

ADR-008 adds a research-only account-risk bridge: canonical account events let explicitly labelled
model-derived lifecycle events use the same C++ `AccountRiskProjection` semantics as the
simulator. `pmm_risk_oracle` is a deterministic local adapter for Python research orchestration,
not a live gateway. Phase-7 backtests may also emit an opt-in unresolved-settlement cash-flow
ledger; it is not PnL, collateral, settlement, paper trading, or execution-realism evidence.

ADR-009 makes C++ risk mandatory for new `pmm.backtest.v2` research configurations. Those runs
launch the local oracle through a repository-relative CMake target and emit a hashed canonical
risk trace. Existing V1 configurations retain their Python compatibility path for reproducibility.

ADR-010 adds reviewed authoritative product terms without coupling replay to a live venue API.
Exact first-party source bytes, canonical terms, effective-time review, and the local conversion
policy are hashed through normalization V2, feature V2, backtest V3, and result manifests. Valid
venue values that cannot be represented as integer cents or whole contracts refuse without
rounding. Fees and settlement are identified but not applied.

B1b-1 hardens that boundary before a second product is admitted. Terms, review, and catalog use
one exact interval; acquisition validates every first-party redirect, streams bounded sources with
incremental hashes and observed HTTP metadata, and cleans partial output; formal schemas share a
runtime parity matrix; and public product/lineage refusals use stable documented codes. The first
reviewed package and existing V1/V2/V3 artifacts keep their original bytes and meaning.

B1b-2 adds a contemporaneous climate product without changing the integer core or downstream
artifact formats. Two complete HMONTH acquisitions bracket one exact effective interval, an
immutable policy hash fixes the acquisition rules, field-level anchors bind JSON/Markdown/PDF
evidence, and review V2 records repository-declared human responsibility without claiming a
signature. Product-terms V2 preserves the official empty secondary rule; V1 remains unchanged.

## Quick start

Prerequisites: CMake 3.24+, a C++20 compiler, Git (to fetch GoogleTest for test builds),
and `clang-format` for formatting checks.

```sh
./scripts/build.sh
./scripts/test.sh
./build/cpp/pmm_demo --steps 5
```

To validate formatting:

```sh
./scripts/check_format.sh
```

`pmm_demo` is a small deterministic Phase 6 walkthrough. It prints market-maker quotes, fills,
inventory, risk admissions, cancellations, and displayed depth. Run `pmm_demo --help` for options.

## Passive historical-data capture

The Phase 7 recorder is a separate passive client: it only subscribes to public Kalshi
order-book/trade feeds and never submits orders. Its required runtime arguments, credential-safe
environment check, smoke-test command, three-hour capture command, and observed-L2 inspection are
documented in [python/README.md](python/README.md).

## Repository map

| Path | Purpose |
| --- | --- |
| `cpp/` | Production C++ sources and public headers (`pmm_core`, `pmm_book`, `pmm_sim`, `pmm_risk`, and `pmm_market_maker`). |
| `tests/` | Independent C++ unit tests for foundation and core-domain behavior. |
| `docs/` | Obsidian vault: roadmap, architecture, research, and engineering records. |
| `configs/` | Explicit runtime and experiment configuration (introduced with functionality). |
| `data/` | Local raw, external, and processed data; generated data is ignored. |
| `experiments/` | Reproducible research definitions and notebooks/scripts. |
| `results/` | Generated experiment outputs, ignored by Git. |
| `scripts/` | Portable developer workflows. |
| `benchmarks/` | Performance benchmarks once behavior is established. |
| `third_party/` | Documentation or deliberately vendored dependencies; currently empty. |
| `tools/` | Project tooling that does not belong to application code. |
| `python/` | Analysis, data preparation, and future ML support code. |

See the [Project Hub](docs/00%20Project%20Hub/Project%20Hub.md), the
[current state and remaining-work roadmap](docs/00%20Project%20Hub/Current%20State%20and%20Remaining%20Work.md),
the
[Phase 3 plan](docs/01%20Roadmap/Phase%203%20Limit%20Order%20Book.md), the
[Phase 4 plan](docs/01%20Roadmap/Phase%204%20Exchange%20Simulator.md), and
[ADR-004](docs/02%20Architecture/ADR-004%20Exchange%20Simulator%20and%20Replay.md) for matching
semantics and exchange/replay rationale.
