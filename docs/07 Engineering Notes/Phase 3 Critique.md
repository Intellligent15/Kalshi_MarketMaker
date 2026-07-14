# Phase 3 critique and follow-up register

## Rating scale

- **1 — Low:** cosmetic or inexpensive to correct later.
- **2 — Limited:** worth improving, but does not constrain the next milestone.
- **3 — Moderate:** should be resolved during the next one or two milestones.
- **4 — High:** likely to cause rework or incorrect behavior if ignored.
- **5 — Critical:** blocks a safe, credible implementation of the roadmap.

This critique evaluates the Phase 3 limit-order-book implementation after its initial formatting,
build, and behavior-test validation. It distinguishes deliberate Phase 3 boundaries from issues
that need resolution before broader simulation or exchange work.

## Unnecessary complexity

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| `ExecutionIdSource::reserve` is a virtual interface that allocates an identifier vector per matching command. | 2 | It makes command atomicity explicit, but Phase 3 has only one in-memory source and no simulator-owned global sequence yet. | Retain through Phase 4, where a shared simulator source is a real consumer; benchmark allocation cost before replacing the vector with a caller-owned buffer or range object. |
| Bitmap-based best-price discovery plus intrusive lists adds more code than a simple dense-level scan would for a 99-tick contract. | 2 | The complexity is justified only if cancellation/matching workloads make it worthwhile. | Keep it as a documented performance-oriented design, but add benchmarks before further low-level specialization. |
| `OrderUpdate` reports final state while executions are separate vectors instead of one ordered event variant. | 2 | This keeps the API small now, but callers must infer ordering from documentation and container order. | Define a unified event envelope when Phase 4 introduces the durable event stream; do not add one solely for Phase 3. |

## Future technical debt

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| Trade IDs and execution sequences are only globally safe when every book shares a correctly configured `ExecutionIdSource`. | 4 | Per-book `MonotonicExecutionIdSource` is suitable for tests but can collide across contracts. | Phase 4 must make the simulator/exchange the sole owner of globally unique IDs and event sequencing. |
| Terminal order state is returned in reports but not retained or queryable. | 3 | Replay, user order status, and audit workflows cannot recover a filled/cancelled order from the book alone. | Keep the live book compact; persist terminal transitions in the Phase 4 event log rather than adding unbounded book history. |
| The raw-pointer intrusive queue depends on strict unlink-before-erase discipline. | 3 | A future amend/replace feature can introduce dangling links or aggregate errors if it bypasses the current helper path. | Add debug-only invariant validation and preserve private ownership/mutation helpers. |
| The 4096-level dense-ladder default is a reasonable guard but not a benchmark-derived product limit. | 2 | It may reject a legitimate fine-grained contract or allocate more empty levels than necessary. | Move the limit into explicit simulator configuration and benchmark a sparse ladder before changing the representation. |
| `snapshot(depth)` linearly examines every configured tick and has no incremental market-data output. | 3 | Snapshot cost will grow with grid size and does not support efficient downstream consumers. | Add sequenced depth deltas and benchmark snapshot needs in Phase 4. |
| Book commands do not check mutable market status, risk limits, or outstanding exposure. | 4 | A caller can submit to a halted market or create risk exposure if it bypasses the future exchange/risk boundary. | Enforce these controls in the Phase 4 exchange command path; do not couple them to book storage. |

## Missing tests

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| No property-based or randomized invariant tests. | 4 | Example scenarios do not prove queue links, aggregates, bitmaps, and locator membership stay consistent under long command sequences. | Add deterministic seeded command-sequence tests with a simple reference model before Phase 4 replay work. |
| No tests cancel the head, middle, and tail of a multi-order price-level queue. | 4 | Intrusive-list unlink correctness is central to FIFO and cancellation safety. | Add focused tests that then match the remaining queue to prove preserved order. |
| No test reaches a self order after first matching third-party liquidity. | 4 | The selected policy must cancel the remaining aggressor and must not bypass its own resting order. | Add a multi-level scenario with earlier fills followed by self-trade prevention. |
| Duplicate submission, wrong-contract submission, non-crossing limit orders, and no-liquidity market orders are not directly tested. | 3 | These are public API rejection/terminal behaviors. | Add table-driven input-validation and terminal-state tests. |
| No tests assert buyer/seller fill ownership, trade IDs, identifier-source wrong-count rejection, or output-vector ordering. | 3 | Consumers need a reliable execution-report contract. | Test reports as a public API, including injected-source failure variants. |
| No overflow, maximum-level boundary, snapshot-depth, or lot-size greater than one scenarios. | 2 | These boundaries are lower-probability but important for robust contracts. | Add targeted tests after the core invariant suite. |

## Missing documentation

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| No public C++ usage example constructs a book, submits orders, and consumes a report. | 3 | New contributors must derive source ownership and report interpretation from tests. | Add a short README/API example with Phase 4 documentation. |
| Execution-report ordering is not a formal contract. | 3 | It is unclear whether vectors are chronological, whether passive updates precede the final aggressor update, and how future event envelopes map to them. | Specify exact report ordering before a simulator or strategy consumes it. |
| The distinction between `Order::submitted_at` and `submit(..., received_at)` is not documented. | 2 | Replay and latency modeling need to know which timestamp becomes the trade execution timestamp. | Document that `received_at` is matching time and defer latency policy to the simulator. |
| Complexity and memory bounds are described informally but not as an API contract. | 2 | Users cannot assess the dense-ladder guard or snapshot cost from the public header. | Add a concise complexity table to the public documentation after benchmarking. |
| The single-writer requirement has no explicit thread-safety annotation. | 3 | Concurrent use could corrupt intrusive links and aggregates. | State that concurrent mutation or mutation/read sharing requires external serialization. |

## Possible optimizations

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| Active order nodes use `std::unordered_map` node allocations. | 2 | High cancel/add rates can create allocator and cache pressure. | Benchmark first; consider a monotonic/slab allocator or pooled nodes only with evidence. |
| Match planning, ID reservation, and report construction allocate vectors on crossing commands. | 2 | Atomicity is correct, but allocation can dominate tiny fills. | Consider `std::pmr`, a small-vector implementation, or reserved reusable command buffers after profiling. |
| Snapshots scan all configured levels instead of using the occupancy bitmap. | 2 | This is cheap for 99 ticks but not for the maximum configured range. | Iterate set bitmap bits when snapshot profiling proves material. |
| Quantity conversion and full `Trade`/`Fill` value construction occur for each match. | 1 | Correctness and auditability matter more than micro-optimizations at this stage. | Retain until a benchmark identifies execution-record construction as material. |

## Future scalability concerns

| Finding | Impact | Why it matters | Recommended handling |
| --- | ---: | --- | --- |
| No durable, globally sequenced event log, snapshots, or recovery boundary. | 5 | Replay, audit, historical research, recovery, and gateway integration require ordered durable events. | Make this the central Phase 4 deliverable. |
| No exchange-level instrument sharding or command serialization architecture. | 4 | The book is deliberately single-writer; multi-market throughput needs deterministic partitioning rather than internal locks. | Design a per-contract event loop/shard model in Phase 4. |
| No market-data fanout or incremental depth updates. | 4 | Strategies and later gateways cannot consume book changes efficiently. | Emit sequenced trade/order/depth events from the simulator boundary. |
| Market lifecycle, risk, inventory, fees, and PnL are still absent from the command path. | 4 | A matching book alone is not a safe trading system. | Introduce explicit exchange and risk boundaries before any agent or paper-trading milestone. |
| One binary contract per market remains the core product restriction. | 4 | Multi-outcome or linked contracts will require a broader market aggregate. | Preserve the one-contract scope through simulation; design the extension before product expansion. |
| No throughput, latency, allocation, or memory benchmark exists. | 3 | The selected dense structure is plausible but not yet evidence-backed. | Add reproducible Phase 4 benchmarks with realistic add/cancel/match mixes and grids. |
