# Prediction Market ML Market Maker

A C++20 research platform for simulating prediction markets and developing progressively
more sophisticated market-making strategies. The project prioritizes correctness,
reproducibility, modularity, testability, and documented engineering decisions.

Phase 3 adds a deterministic limit order book for one contract: price-time priority, matching,
partial fills, cancellation, market-order expiry, and self-trade prevention. The book reuses the
validated Phase 2 domain model while keeping inventory, risk, market lifecycle, persistence, and
simulation outside the matching boundary.

## Quick start

Prerequisites: CMake 3.24+, a C++20 compiler, Git (to fetch GoogleTest for test builds),
and `clang-format` for formatting checks.

```sh
./scripts/build.sh
./scripts/test.sh
./build/cpp/pmm_demo
```

To validate formatting:

```sh
./scripts/check_format.sh
```

## Repository map

| Path | Purpose |
| --- | --- |
| `cpp/` | Production C++ sources and public headers (`pmm_core` and `pmm_book`). |
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
[Phase 3 plan](docs/01%20Roadmap/Phase%203%20Limit%20Order%20Book.md), and
[ADR-003](docs/02%20Architecture/ADR-003%20Limit%20Order%20Book.md) for the matching semantics
and implementation rationale.
