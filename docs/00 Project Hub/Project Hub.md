# Project Hub

## Purpose

Build a production-quality, modular prediction-market simulation and market-making research
platform. Correctness, simple baselines, reproducibility, and documentation take precedence
over sophistication.

## Current status

Phases 1–5 are complete. `pmm_core` provides validated market and execution vocabulary,
`pmm_book` provides deterministic single-writer matching, and `pmm_sim` provides a deterministic
exchange event loop, lifecycle gating, global IDs and event sequencing, in-memory journals,
checkpoints, and replay. `pmm_agents` adds deterministic synthetic agents and pull-based market
data projections. PnL, risk, durable persistence, and gateway layers remain intentionally separate.

## Navigation

- [[01 Roadmap/Phase 1 Plan|Roadmap and Phase 1 plan]]
- [[01 Roadmap/Phase 2 Core Domain Types|Phase 2 plan and scope]]
- [[01 Roadmap/Phase 3 Limit Order Book|Phase 3 plan and scope]]
- [[01 Roadmap/Phase 4 Exchange Simulator|Phase 4 plan and scope]]
- [[01 Roadmap/Phase 5 Baseline Trading Agents|Phase 5 plan and scope]]
- [[02 Architecture/ADR-001 Repository Foundation|Repository foundation decision]]
- [[02 Architecture/ADR-002 Core Domain Model|Core domain model decision]]
- [[02 Architecture/ADR-003 Limit Order Book|Limit order book decision]]
- [[02 Architecture/ADR-004 Exchange Simulator and Replay|Exchange simulator and replay decision]]
- [[02 Architecture/ADR-005 Deterministic Baseline Agents|Baseline-agent decision]]
- [[07 Engineering Notes/Phase 1 Foundation|Phase 1 implementation record]]
- [[07 Engineering Notes/Phase 2 Core Domain Types|Phase 2 implementation record]]
- [[07 Engineering Notes/Phase 2 Explained|Phase 2 plain-language walkthrough]]
- [[07 Engineering Notes/Phase 2 Critique|Phase 2 critique and follow-up register]]
- [[07 Engineering Notes/Phase 3 Limit Order Book|Phase 3 implementation record]]
- [[07 Engineering Notes/Phase 3 Critique|Phase 3 critique and follow-up register]]
- [[07 Engineering Notes/Phase 3 Explained|Phase 3 plain-language walkthrough]]
- [[07 Engineering Notes/Phase 4 Exchange Simulator|Phase 4 implementation record]]
- [[07 Engineering Notes/Phase 4 Explained|Phase 4 plain-language walkthrough]]
- [[07 Engineering Notes/Phase 4 Critique|Phase 4 critique and follow-up register]]
- [[07 Engineering Notes/Phase 5 Baseline Trading Agents|Phase 5 implementation record]]
- [[07 Engineering Notes/Phase 5 Explained|Phase 5 plain-language walkthrough]]
- [[07 Engineering Notes/Phase 5 Critique|Phase 5 critique and follow-up register]]
- [[Templates/Feature Note Template|Feature note template]]
- [[Templates/Experiment Template|Experiment template]]

## Working agreements

1. Design an interface and record the tradeoffs before implementing a substantial feature.
2. Keep exchange, risk, strategy, ML, market state, and simulation concerns separate.
3. Add tests with behavior, and document purpose, design, tradeoffs, tests, and limitations.
4. Keep experiments explicit about data, seeds, validation, baselines, and metrics.
5. Keep market lifecycle, risk, inventory, and persistence outside the order-book matching path.
6. Treat exchange event sequence order as authoritative for consumers and replay.
