# zeus_dev_helper_mcp

**Developer Helper MCP** — first Zeus-powered app onboarding coach.

| | |
| --- | --- |
| **Board** | [ZDH](https://kotenai.atlassian.net/jira/software/projects/ZDH/boards/45) |
| **Epic** | [ZDH-1](https://kotenai.atlassian.net/browse/ZDH-1) |
| **Skeleton** | [ZDH-3](https://kotenai.atlassian.net/browse/ZDH-3) |
| **Catalogs** | [ZDH-14](https://kotenai.atlassian.net/browse/ZDH-14) → [zeus_chat_request](https://github.com/koten-ai/zeus_chat_request) |
| **Docs** | [koten_docs · dev-helper-mcp](https://github.com/koten-ai/koten_docs/blob/zeus-v1.0.0/zeus-client/dev-helper-mcp.md) |

> Not a data-plane MCP. Coaches: checklist → templates → (later) live readiness & smoke.

## Stack

- **Python 3.11+**
- Official **`mcp`** SDK (`FastMCP`, stdio)

## Install (dev)

```bash
git clone https://github.com/koten-ai/zeus_dev_helper_mcp.git
cd zeus_dev_helper_mcp
pip install -e ".[dev]"

# Recommended: local catalog repo (private GH needs this or GITHUB_TOKEN)
export ZEUS_CHAT_REQUEST_DIR=../zeus_chat_request   # sibling clone
# or: export GITHUB_TOKEN=...   # Contents API for private zeus_chat_request
```

## Run

```bash
zeus-dev-helper-mcp
# or
python -m zeus_dev_helper_mcp
```

## Host install

### Grok Build

```bash
grok mcp add zeus-dev-helper -- \
  env ZEUS_CHAT_REQUEST_DIR=/absolute/path/to/zeus_chat_request \
  python -m zeus_dev_helper_mcp
```

(Adjust to your host’s MCP config format if `grok mcp add` differs.)

### Claude Code / Claude Desktop

Add to MCP servers config (example):

```json
{
  "mcpServers": {
    "zeus-dev-helper": {
      "command": "python",
      "args": ["-m", "zeus_dev_helper_mcp"],
      "env": {
        "ZEUS_CHAT_REQUEST_DIR": "/absolute/path/to/zeus_chat_request",
        "ZEUS_URL": "http://localhost:8080"
      }
    }
  }
}
```

### Hermes / OpenClaw

Point the host’s MCP stdio entry at `python -m zeus_dev_helper_mcp` with the same env vars.

## Implemented tools (0.3.0)

| Tool | Status |
| --- | --- |
| `doctor` | Config + catalog reachability |
| `start_project` | Init checklist |
| `get_checklist` / `next_step` | Checklist walkthrough |
| `mark_done` / `mark_blocked` | Checklist updates |
| `set_prereq` | **ZDH-4** — store non-secret prereqs |
| `validate_env` | Env + prereqs + :9091 guard |
| `readiness_check` | **ZDH-4** — live probes |
| `smoke_test_zeus` | **ZDH-7** — readiness + `POST …/describe` (no LLM) |
| `smoke_test_agent` | **ZDH-7** — one `run_agent` turn (needs `pip install -e ".[agent]"`) |
| `diagnose_error` | **ZDH-7** — failure_class + errors.md anchors |
| `suggest_demo_prompts` | Starter advice-shaped prompts |
| `list_catalog_modes` / `fetch_chat_request` | **ZDH-14** |
| `explain` | Glossary topics |
| `bootstrap_scope` | Partial via readiness |
| scaffold / use_sample | **Stubs** (P4) |

## Catalog rules (never invent hashes)

1. Live Zeus stamp + `sync_chat_requests` for production.  
2. [zeus_chat_request](https://github.com/koten-ai/zeus_chat_request) `v2/min/*` for offline templates.  
3. `fetch_chat_request` always returns **TEMPLATE ONLY** warning.

## Env

| Variable | Purpose |
| --- | --- |
| `ZEUS_URL` | Public Zeus API (`:8080`) |
| `ZEUS_BUCKET` / `ZEUS_SCOPE` / `ZEUS_COLLECTION` | Scope for bootstrap/auth probes |
| `ZEUS_MODE` | default `analytics` |
| `ZEUS_USERNAME` / `ZEUS_PASSWORD` | basic auth (not stored by set_prereq) |
| `ZEUS_BEARER_TOKEN` | bearer auth |
| `ZEUS_CHAT_REQUEST_DIR` | Local clone of zeus_chat_request |
| `GITHUB_TOKEN` / `GH_TOKEN` | Private GitHub fetch |
| `ZEUS_CHAT_REQUEST_REPO` | default `koten-ai/zeus_chat_request` |
| `ZEUS_CHAT_REQUEST_BRANCH` | default `main` |
| `KOTEN_DOCS_BRANCH` | default `zeus-v1.0.0` |
| `ZEUS_DEV_HELPER_STATE_DIR` | checklist + prereqs state (default `~/.config/zeus_dev_helper`) |
| `LLM_API_KEY` / `OPENAI_API_KEY` | presence checked by `validate_env` |

## Tests

```bash
pip install -e ".[dev]"
pytest -q
```

Requires sibling `../zeus_chat_request` with `manifest.json` for catalog tests.

## Related

| Repo | Role |
| --- | --- |
| [zeus_client_python](https://github.com/koten-ai/zeus_client_python) | SDK |
| [zeus_chat_request](https://github.com/koten-ai/zeus_chat_request) | Min catalogs |
| [koten_docs](https://github.com/koten-ai/koten_docs) | Docs + agent-index |
| [Zeus](https://github.com/koten-ai/Zeus) | Engine |
