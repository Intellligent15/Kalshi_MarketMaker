# Phase 1 plan and completion record

## Initial repository state

The workspace contained only `PROJECT_BOOTSTRAP_PROMPT.md` and `PROJECT_CHARTER.md` and was
not its own Git repository. There was no build configuration, source tree, test framework,
formatting policy, documentation hierarchy, CI workflow, or executable.

## Scope

Create the smallest maintainable repository foundation without implementing any market-domain
behavior. The Phase 1 deliverables are a repository scaffold, CMake, GoogleTest,
clang-format policy, documentation vault, GitHub Actions, ignore rules, README, scripts, a
minimal executable, a trivial test, and local build verification.

## Implementation plan

1. Establish independent version-control metadata and the charter-aligned directory map.
2. Configure C++20 targets through CMake and apply shared compiler warnings.
3. Add a pinned GoogleTest dependency and CTest discovery with one smoke test.
4. Add a checked-in formatting policy and scripts for configure, build, test, and formatting.
5. Create the Obsidian structure, ADR, templates, and Phase 1 engineering record.
6. Add Linux/macOS build-and-test CI plus an Ubuntu formatting check.
7. Build, test, run the executable, and record any environment limitation.

## Deferred decisions required before Phase 2

- **Price representation and tick rules:** integer ticks, fixed-point decimal, and their
  conversion/overflow behavior must be chosen before `Price` exists.
- **Contract identity and binary settlement semantics:** the model needs an explicit identity,
  outcome set, and lifecycle boundary.
- **Time and ordering:** choose timestamp source, sequence-number ownership, and deterministic
  tie-breaking before orders or matching are modeled.
- **Error model:** define whether invalid domain inputs use expected-like results, exceptions,
  or invariant checks, consistently across core types.
- **Configuration format:** decide TOML, YAML, JSON, or a narrow custom format when runtime
  configuration first has real consumers.
- **Dependency policy:** decide whether a locked package manager or a vendored source mirror is
  needed for offline/release-grade reproducibility beyond the pinned test dependency.

These are intentionally unresolved because selecting them now would either pre-empt the
domain design or add unused infrastructure.
