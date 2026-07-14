# ADR-001: Repository foundation

- Status: Accepted
- Date: 2026-07-13
- Scope: Phase 1

## Context

The charter requires a C++20, CMake, GoogleTest, clang-format project that can grow into a
layered exchange, risk, strategy, ML, market-state, and simulation system. Phase 1 must remain
free of premature domain implementation.

## Decision

Use the following repository boundary:

```text
cpp/include/pmm/  public project-owned C++ interfaces
cpp/src/          production implementation and executables
tests/            independent behavior tests
cmake/            reusable CMake policy modules
docs/             Obsidian vault and engineering record
configs/          future versioned configuration
data/             local raw/external/processed data, ignored by default
experiments/      reproducible research definitions
results/          generated experiment output, ignored by default
scripts/          portable developer commands
benchmarks/       measured performance work after correctness
third_party/      intentionally vendored dependencies only
tools/            non-runtime project tooling
python/           future analysis and ML support
```

Use a root CMake project with subdirectories for production code and tests. Build a small
`pmm_demo` executable now, while reserving public headers for Phase 2 interfaces. Use CTest and
GoogleTest; CMake fetches GoogleTest at immutable commit
`f8d7d77c06936315286eb55f8de22cd23c188571` only when testing is enabled. Apply one
clang-format configuration and share compiler-warning policy through `cmake/Warnings.cmake`.

## Rationale

The `include`/`src` split makes the public/private boundary visible before multiple components
arrive. A separate test tree ensures test code does not leak into runtime targets. Keeping
Python, data, experiments, and results distinct prevents research artifacts from becoming
accidental trading dependencies. Fetching a pinned test dependency avoids committing a large
third-party tree while making the resolved source revision explicit.

## Tradeoffs

- FetchContent requires network access for a clean test build. An offline application-only
  build is possible with `-DBUILD_TESTING=OFF`; an offline test strategy is deferred.
- `cpp/` is a single module today. Splitting it into libraries such as `core`, `book`,
  `simulation`, and `strategy` now would express unvalidated boundaries too early. Create those
  targets only when Phase 2/3 interfaces require them.
- Numbered, space-containing docs directories optimize Obsidian navigation and match the
  charter, but shell paths need quoting. Markdown links and scripts already account for this.
- Ignoring generated data and results protects repository size and provenance, but shared,
  reviewed fixtures must be added explicitly when tests need them.

## Consequences

Phase 2 should add only deliberately designed core-type targets and tests, then reconsider
whether a `pmm_core` library is warranted. This decision does not prescribe a package manager,
runtime configuration format, or any trading behavior.
