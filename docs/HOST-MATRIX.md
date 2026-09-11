# Host matrix — Helper MCP instructions (ZDH-40)

Server `instructions` are **client-dependent**. Measure; do not assume one host’s tool-picking matches another.

Local only: tool **ids** in `helper_metrics` / `metrics.jsonl`. No prompts, bodies, or tokens.

| Host | Config | Last measured | Notes |
| --- | --- | --- | --- |
| Grok Build | `grok mcp add … -- uvx zeus-dev-helper-mcp` (`--` before `python -m`) | | `unexpected argument '-m'` if `--` missing |
| Claude Code / Desktop | `mcpServers` JSON, `uvx` / venv python | | |
| Cursor | MCP stdio entry, same env | | |

Measure on each host (first-green session, `core` toolset):

1. Did the model call `doctor` or `next_step` **before** `scaffold_app`?
2. Did any tool argument / generated app use Hub `:9091`?
3. Did it invent `contract_hash` / `compute_local`?
4. `helper_metrics` `tool_calls` is ids only.

Fill **Last measured** after a real session. Unit tests cover the corpus and trace checker; they do not replace this table.
