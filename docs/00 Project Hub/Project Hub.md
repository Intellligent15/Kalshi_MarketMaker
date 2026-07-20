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

Phase 7 now also has an additive multi-market backtest implementation: one global causal schedule,
independent per-product baseline state, and one canonical C++ risk projection per contract. Its
focused and full offline closure gates pass. B2c now has offline evidence-index, measurement, and
instrumentation tooling, but no retained capture. Its deeper review found operator-interrupt and
independent-verification blockers. The B2c-H hardening design is documented and approved for bounded
implementation. The first additive V2 supervisor/verifier/schema slice and focused offline coverage
are now implemented, but the complete design acceptance matrix is still open. B2c-H remains current;
the separately approved B2c-P product-evidence and capture gate remains blocked.

A local Graphify navigation index is available for repository discovery. Its first snapshot has
6,062 nodes and 9,165 built edges, but also reports dangling, collapsed, and AST-empty coverage
warnings. It is an advisory map only; source, tests, accepted ADRs, and the living roadmap remain
authoritative.

## Navigation

- [[00 Project Hub/Current State and Remaining Work|Authoritative current state and remaining work]]
- [[00 Project Hub/Graphify Workflow|Local Graphify navigation and update workflow]]
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
- [[02 Architecture/ADR-011 Bracketed Product Evidence and Review Responsibility|Bracketed product evidence and review responsibility]]
- [[02 Architecture/ADR-012 Deterministic Document Evidence and Completeness Profiles|Deterministic document evidence and completeness-profile decision]]
- [[02 Architecture/ADR-013 Multi-Scope Capture and Reconnect-Aware Normalization|Multi-scope capture and reconnect-normalization decision]]
- [[07 Engineering Notes/Phase 7 Historical Replay and Backtesting|Phase 7 implementation record]]
- [[07 Engineering Notes/Phase 7 Explained|Phase 7 plain-language walkthrough]]
- [[07 Engineering Notes/Phase 7 Critique|Phase 7 critique and prioritized debt]]
- [[07 Engineering Notes/Phase 7 Multi-Scope Capture and Recovery|B2a implementation and operator guide]]
- [[07 Engineering Notes/Phase 7 Multi-Scope Capture Explained|B2a plain-language walkthrough]]
- [[07 Engineering Notes/Phase 7 Multi-Scope Capture Critique|B2a severity-ranked critique]]
- [[07 Engineering Notes/Phase 7 Retained Capture Evidence|B2c evidence operator guide]]
- [[07 Engineering Notes/Phase 7 Retained Capture Evidence Explained|B2c plain-language explanation]]
- [[07 Engineering Notes/Phase 7 Retained Capture Evidence Critique|B2c tooling critique]]
- [[07 Engineering Notes/Phase 7 B2c-H Hardening Design|B2c-H reviewed implementation design]]
- [[07 Engineering Notes/Phase 7 B2c-H Hardening Explained|B2c-H plain-language explanation]]
- [[07 Engineering Notes/Phase 7 B2c-H Hardening Critique|B2c-H design critique and debt register]]
- [[07 Engineering Notes/Phase 7 Segment-Aware Features|B2b-1 implementation and operator guide]]
- [[07 Engineering Notes/Phase 7 Segment-Aware Features Explained|B2b-1 plain-language walkthrough]]
- [[07 Engineering Notes/Phase 7 Segment-Aware Features Critique|B2b-1 severity-ranked critique]]
- [[07 Engineering Notes/Product Terms Source and Review Guide|Product-term evidence and review workflow]]
- [[07 Engineering Notes/Authoritative Product Terms Explained|Authoritative product-term plain-language walkthrough]]
- [[07 Engineering Notes/Authoritative Product Terms Critique|Authoritative product-term critique and ranked debt]]
- [[07 Engineering Notes/Product Terms Refusal Codes|Product-term refusal-code compatibility reference]]
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
