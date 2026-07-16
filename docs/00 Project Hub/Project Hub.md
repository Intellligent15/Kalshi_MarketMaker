# Project Hub

## Purpose

Build a production-quality, modular prediction-market simulation and market-making research
platform. Correctness, simple baselines, reproducibility, and documentation take precedence
over sophistication.

Canonical GitHub repository: [Intellligent15/Kalshi_MarketMaker](https://github.com/Intellligent15/Kalshi_MarketMaker)

## Current status

Phases 1–6 are complete and Phase 7 is in progress. `pmm_core` provides validated market and execution vocabulary,
`pmm_book` provides deterministic single-writer matching, and `pmm_sim` provides a deterministic
exchange event loop, lifecycle gating, global IDs and event sequencing, in-memory journals,
checkpoints, and replay. `pmm_agents` adds deterministic synthetic agents and pull-based market
data projections. `pmm_risk` adds external event-fed inventory/exposure and command admission;
`pmm_market_maker` adds deterministic passive fixed-spread and inventory-aware quoting. PnL,
fees, collateral, settlement, durable persistence, and gateways remain intentionally separate.

## Navigation

- [[00 Project Hub/Current State and Remaining Work|Authoritative current state and remaining work]]
- [[01 Roadmap/Phase 1 Plan|Roadmap and Phase 1 plan]]
- [[01 Roadmap/Phase 2 Core Domain Types|Phase 2 plan and scope]]
- [[01 Roadmap/Phase 3 Limit Order Book|Phase 3 plan and scope]]
- [[01 Roadmap/Phase 4 Exchange Simulator|Phase 4 plan and scope]]
- [[01 Roadmap/Phase 5 Baseline Trading Agents|Phase 5 plan and scope]]
- [[01 Roadmap/Phase 6 Baseline Market Making|Phase 6 plan and scope]]
- [[01 Roadmap/Phase 7 Historical Replay and Backtesting|Phase 7 plan and scope]]
- [[02 Architecture/ADR-001 Repository Foundation|Repository foundation decision]]
- [[02 Architecture/ADR-002 Core Domain Model|Core domain model decision]]
- [[02 Architecture/ADR-003 Limit Order Book|Limit order book decision]]
- [[02 Architecture/ADR-004 Exchange Simulator and Replay|Exchange simulator and replay decision]]
- [[02 Architecture/ADR-005 Deterministic Baseline Agents|Baseline-agent decision]]
- [[02 Architecture/ADR-006 Baseline Market Making and Risk Admission|Market-making and risk decision]]
- [[02 Architecture/ADR-007 Deterministic Historical Replay and Backtesting|Historical replay and backtesting decision]]
- [[02 Architecture/ADR-008 Calibrated Execution Accounting and Research Evaluation|Research execution and accounting decision]]
- [[02 Architecture/ADR-009 Canonical Risk Conformance and Research Oracle Migration|Canonical risk conformance decision]]
- [[02 Architecture/ADR-010 Authoritative Product Terms and Artifact Lineage|Authoritative product terms and lineage decision]]
- [[07 Engineering Notes/Phase 7 Historical Replay and Backtesting|Phase 7 implementation record]]
- [[07 Engineering Notes/Phase 7 Explained|Phase 7 plain-language walkthrough]]
- [[07 Engineering Notes/Phase 7 Critique|Phase 7 critique and prioritized debt]]
- [[07 Engineering Notes/Product Terms Source and Review Guide|Product-term evidence and review workflow]]
- [[07 Engineering Notes/Authoritative Product Terms Explained|Authoritative product-term plain-language walkthrough]]
- [[07 Engineering Notes/Authoritative Product Terms Critique|Authoritative product-term critique and ranked debt]]
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
- [[07 Engineering Notes/Phase 6 Baseline Market Making|Phase 6 implementation record]]
- [[07 Engineering Notes/Phase 6 Explained|Phase 6 plain-language walkthrough]]
- [[07 Engineering Notes/Phase 6 Critique|Phase 6 critique and follow-up register]]
- [[Templates/Feature Note Template|Feature note template]]
- [[Templates/Experiment Template|Experiment template]]

## Working agreements

1. Design an interface and record the tradeoffs before implementing a substantial feature.
2. Keep exchange, risk, strategy, ML, market state, and simulation concerns separate.
3. Add tests with behavior, and document purpose, design, tradeoffs, tests, and limitations.
4. Keep experiments explicit about data, seeds, validation, baselines, and metrics.
5. Keep market lifecycle, risk, inventory, and persistence outside the order-book matching path.
6. Treat exchange event sequence order as authoritative for consumers and replay.
