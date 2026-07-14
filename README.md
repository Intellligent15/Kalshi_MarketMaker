# Prediction Market ML Market Maker

A C++20 research platform for simulating prediction markets and developing progressively
more sophisticated market-making strategies. The project prioritizes correctness,
reproducibility, modularity, testability, and documented engineering decisions.

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
[Phase 3 plan](docs/01%20Roadmap/Phase%203%20Limit%20Order%20Book.md), the
[Phase 4 plan](docs/01%20Roadmap/Phase%204%20Exchange%20Simulator.md), and
[ADR-004](docs/02%20Architecture/ADR-004%20Exchange%20Simulator%20and%20Replay.md) for matching
semantics and exchange/replay rationale.
