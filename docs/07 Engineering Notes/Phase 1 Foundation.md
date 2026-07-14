# Phase 1: Repository foundation

## Purpose

Provide a repeatable, cross-platform starting point for the charter's incremental development
workflow without beginning market-domain implementation.

## Design

CMake configures C++20 with extensions disabled and emits `compile_commands.json`. The project
builds a minimal `pmm_demo` executable. CTest discovers a GoogleTest smoke test from a pinned
upstream revision. Shared warnings are centralized in `cmake/Warnings.cmake`; CI enables
warnings-as-errors. Developer scripts provide the normal configure/build/test/format path.

The documentation tree is an Obsidian vault with a Project Hub, roadmap, architecture records,
topic folders, daily logs, interview notes, references, and reusable templates.

## Tradeoffs

This foundation favors a small number of targets over a speculative component hierarchy. It
uses a fetched dependency rather than committing GoogleTest, trading a clean source tree for a
network requirement during fresh test configuration. The full rationale is in
[[02 Architecture/ADR-001 Repository Foundation]].

## Tests and validation

- `tests/smoke_test.cpp` verifies that GoogleTest is linked and CTest can discover a test.
- CI builds and tests on current Ubuntu and macOS runners.
- CI checks C++ formatting on Ubuntu.
- Local verification should run `./scripts/test.sh`, `./build/cpp/pmm_demo`, and
  `./scripts/check_format.sh` when clang-format is installed.

## Known limitations

- The only test is intentionally trivial; behavior tests begin with Phase 2 types.
- No package lock or offline dependency mirror exists.
- Phase 1 intentionally contained no domain behavior; the later Phase 2 core types are recorded
  separately in [[07 Engineering Notes/Phase 2 Core Domain Types]].

## Repository policy update

The local bootstrap prompt and charter are ignored because they are workspace setup material,
not project source. `AGENTS.md` prohibits AI-assistant commit attribution, and the committed
`tools/git-hooks/commit-msg` hook rejects `Co-authored-by` trailers naming Codex, OpenAI, or
ChatGPT. The repository config points Git at the committed hooks directory so the rule is active
for this checkout.
