# Repository instructions for coding agents

## Commit attribution

Never add Codex, OpenAI, ChatGPT, or any AI assistant as a commit author or co-author.
Do not add `Co-authored-by` trailers for an AI assistant. Commits must attribute only the
responsible human contributor(s).

The version-controlled `tools/git-hooks/commit-msg` hook rejects commit messages containing
AI-assistant co-author trailers when the repository's configured hooks path is active.
