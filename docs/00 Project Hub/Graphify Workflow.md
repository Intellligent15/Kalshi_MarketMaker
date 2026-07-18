# Graphify Workflow

## Purpose

Graphify is an optional local navigation layer for this repository. It builds a persistent graph of
code symbols, documentation concepts, files, and relationships so maintainers can find relevant
source before reading deeply.

The graph is a map, not a source of truth. Accepted ADRs own architecture, source and tests own
implemented behavior, and [[00 Project Hub/Current State and Remaining Work]] owns current status and
execution order. Graphify edges labelled `INFERRED` or `AMBIGUOUS` are leads to verify, not facts to
repeat without inspection.

## Local-state boundary

Graphify writes generated files under `graphify-out/`. The directory is ignored by Git and must not
be committed, cited as retained product evidence, or used as a test/roadmap closure artifact. Do not
edit generated graph files manually.

The repository uses the version-controlled `tools/git-hooks` path. Do not run
`graphify hook install` without separate approval: it changes repository hook behavior, refreshes
only code changes, and does not replace the manual update required after material ADR or roadmap
edits.

## Current local snapshot

The first local graph completed on 2026-07-18 with 6,062 nodes, 9,165 built edges, and 462
communities. Its report recorded a roughly 101.4x token reduction for an average query relative to
the detected 303,100-word corpus.

This snapshot is usable but explicitly incomplete:

- 421 dangling-endpoint edges;
- 166 undirected endpoint-collapsed edges;
- 111 code/configuration files with no AST nodes; and
- zero recorded semantic token usage because the delegated-agent interface did not expose reusable
  usage counts.

These are health warnings, not repository defects. Keep them visible when using the graph, and
verify every material result directly. The graph was generated while the repository-local Graphify
guidance was being added, so run `$graphify . --update` after those documentation changes are
committed before treating the snapshot as current.

## Build and inspect

In a new Codex chat opened at the repository root, build the complete code-and-document graph with:

```text
$graphify .
```

Wait for the run to report completion before querying or updating it. Expected local outputs are:

- `graphify-out/graph.json` — machine-readable graph;
- `graphify-out/graph.html` — interactive visualization; and
- `graphify-out/GRAPH_REPORT.md` — generated overview and audit report.

For a terminal-only structural graph that deliberately skips semantic documentation extraction:

```sh
graphify extract . --code-only
```

Do not run the terminal command over an active `$graphify .` build; both own the same output
directory.

## Query before broad exploration

When the graph exists, start architecture, ownership, dependency, and data-flow investigations with
one focused query:

```text
$graphify query "Trace Capture V2 through normalization V3 and Backtest V4"
$graphify query "Which contracts enforce complete observed intervals?"
$graphify explain "CxxRiskOracle"
$graphify path "Capture V2" "Result V4"
```

Terminal equivalents are useful outside Codex:

```sh
graphify query "capture normalization features backtest" --graph graphify-out/graph.json
graphify explain "CxxRiskOracle" --graph graphify-out/graph.json
graphify path "Capture V2" "Result V4" --graph graphify-out/graph.json
```

Use graph results to select files. Before changing code or reporting behavior:

1. inspect the named source and tests;
2. check the relevant accepted ADR;
3. check the living roadmap for current status;
4. distinguish `EXTRACTED`, `INFERRED`, and `AMBIGUOUS` edges; and
5. report when the graph is missing or conflicts with direct evidence.

## Refresh policy

After meaningful code or documentation changes, refresh incrementally in a Graphify-enabled Codex
chat:

```text
$graphify . --update
```

Use a full rebuild only when the initial run failed, the graph is known to be corrupt, or a Graphify
upgrade requires it. Re-clustering without re-extraction is available when only community grouping
or labels need refreshing:

```sh
graphify cluster-only .
```

To check whether the current corpus differs from Graphify's saved manifest:

```sh
graphify check-update .
```

Incremental freshness is a convenience, not a release gate. Formatting and repository test commands
remain the validation authority.

## Useful maintenance commands

```sh
# Confirm the graph exists.
test -f graphify-out/graph.json

# Diagnose same-endpoint edge-collapse risk.
graphify diagnose multigraph \
  --graph graphify-out/graph.json \
  --extract-path .

# Measure graph token reduction against a naive full-corpus approach.
graphify benchmark graphify-out/graph.json

# Regenerate the hierarchy-oriented HTML view.
graphify tree \
  --graph graphify-out/graph.json \
  --output graphify-out/GRAPH_TREE.html \
  --root . \
  --label PM_MarketMaker

# Inspect optional hook state without changing it.
graphify hook status
```

Run diagnostics only after the active build completes. A diagnostic warning should remain visible
in any graph-based explanation; do not silently treat an incomplete graph as complete.

## Prompt pattern for future agents

Repository handoffs may include this bounded instruction:

> If `graphify-out/graph.json` exists, use a focused Graphify query for initial navigation, then
> verify every material claim against source, tests, accepted ADRs, and the living roadmap. Treat
> inferred or ambiguous edges as leads only. After meaningful code or documentation changes, run
> `$graphify . --update` when Graphify is available. Never commit `graphify-out/` or use it as
> completion evidence.

This pattern improves discovery without allowing a generated secondary index to override reviewed
repository authority.
