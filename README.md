# zeus_dev_helper_mcp

**Developer Helper MCP** — first Zeus-powered app onboarding coach.

| | |
| --- | --- |
| **Board** | [ZDH](https://kotenai.atlassian.net/jira/software/projects/ZDH/boards/45) |
| **Epic** | [ZDH-1](https://kotenai.atlassian.net/browse/ZDH-1) |
| **Skeleton** | [ZDH-3](https://kotenai.atlassian.net/browse/ZDH-3) |
| **Catalogs** | [ZDH-14](https://kotenai.atlassian.net/browse/ZDH-14) → [zeus_chat_request](https://github.com/koten-ai/zeus_chat_request) |
| **Docs** | [docs.koten.ai](https://docs.koten.ai/) · [Dev Helper MCP](https://docs.koten.ai/zeus-client/dev-helper-mcp) |

> Not a data-plane MCP. Coaches: checklist → templates → (later) live readiness & smoke.

## Stack

- **Python 3.11+**
- Official **`mcp`** SDK (`FastMCP`, stdio)

## Install (dev)

```bash
git clone https://github.com/koten-ai/zeus_dev_helper_mcp.git
cd zeus_dev_helper_mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# Agent smoke (optional):
pip install -e ".[agent]"   # pulls kotenai-zeus-client

# Recommended: local catalog repo (private GH needs this or GITHUB_TOKEN)
export ZEUS_CHAT_REQUEST_DIR=../zeus_chat_request   # sibling clone
# or: export GITHUB_TOKEN=...   # Contents API for private zeus_chat_request
export ZEUS_URL=http://localhost:8080
export ZEUS_BUCKET=beer-sample ZEUS_SCOPE=_default
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

## Implemented tools (0.4.0)

| Tool | Status |
| --- | --- |
| `doctor` | Config + catalog reachability |
| `start_project` / `get_checklist` / `next_step` / `gap_report` | **ZDH-8** coach walkthrough |
| `mark_done` / `mark_blocked` | Checklist updates |
| `set_prereq` / `validate_env` / `readiness_check` | **ZDH-4** |
| `bootstrap_scope` | **ZDH-5** live bootstrap + chat_request summary |
| `scaffold_app` / `use_sample` / `write_env` / `verify_local_setup` | **ZDH-6** |
| `smoke_test_zeus` / `smoke_test_agent` / `diagnose_error` | **ZDH-7** |
| `list_catalog_modes` / `fetch_chat_request` | **ZDH-14** |
| `explain` / `suggest_demo_prompts` | Glossary + prompts |

### Day-one coach path

```text
start_project → set_prereq → validate_env → readiness_check
  → use_sample | scaffold_app → bootstrap_scope / fetch_chat_request
  → smoke_test_zeus → smoke_test_agent → gap_report
```

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
| `KOTEN_DOCS_BASE_URL` | default `https://docs.koten.ai` (published site) |
| `KOTEN_DOCS_BRANCH` | default `zeus-v1.0.0` (source branch for machine files) |
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
| [docs.koten.ai](https://docs.koten.ai/) | Published platform docs |
| [koten_docs](https://github.com/koten-ai/koten_docs) | Docs source + agent-index.yaml |
| [Zeus](https://github.com/koten-ai/Zeus) | Engine |
