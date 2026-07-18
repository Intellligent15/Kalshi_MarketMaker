# Repository instructions for coding agents

## Commit attribution

Never add Codex, OpenAI, ChatGPT, or any AI assistant as a commit author or co-author.
Do not add `Co-authored-by` trailers for an AI assistant. Commits must attribute only the
responsible human contributor(s).

The version-controlled `tools/git-hooks/commit-msg` hook rejects commit messages containing
AI-assistant co-author trailers when the repository's configured hooks path is active.

## Graphify navigation

When `graphify-out/graph.json` exists and Graphify is available, use it as a read-only navigation
index before broad repository searches for architecture, ownership, dependency, or data-flow
questions. Prefer a focused Graphify query, path, or explanation, then inspect the named source files
before making a claim or edit.

Graphify is not architectural authority. Accepted ADRs, source code, tests, and
`docs/00 Project Hub/Current State and Remaining Work.md` take precedence over stale, inferred, or
ambiguous graph edges. Preserve Graphify's `EXTRACTED`, `INFERRED`, and `AMBIGUOUS` distinctions.

`graphify-out/` is generated local state and must not be committed. Do not edit its files manually.
After meaningful code or documentation changes, refresh it with the installed Graphify skill's
incremental workflow (`$graphify . --update`) when available. Do not install Graphify Git hooks or
make graph freshness a validation/closure claim without explicit approval.
