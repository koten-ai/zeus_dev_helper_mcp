# zeus_dev_helper_mcp

**Developer Helper MCP** — first Zeus-powered app onboarding coach.

| | |
| --- | --- |
| **Board** | [ZDH](https://kotenai.atlassian.net/jira/software/projects/ZDH/boards/45) |
| **Epic** | [ZDH-1](https://kotenai.atlassian.net/browse/ZDH-1) |
| **Skeleton** | [ZDH-3](https://kotenai.atlassian.net/browse/ZDH-3) |
| **Catalogs** | [ZDH-14](https://kotenai.atlassian.net/browse/ZDH-14) → [zeus_chat_request](https://github.com/koten-ai/zeus_chat_request) |
| **Docs** | [docs.koten.ai](https://docs.koten.ai/) · [Dev Helper MCP](https://docs.koten.ai/zeus-client/dev-helper-mcp) |

> Not a data-plane MCP. Coaches: checklist → templates → live readiness & smoke → handoffs.

**Design:** [`docs/DESIGN.md`](docs/DESIGN.md) (ZDH-2, frozen MVP) · [`docs/DESIGN-0.6.md`](docs/DESIGN-0.6.md) (runtime coach)

## Stack

- **Python 3.11+**
- Official **`mcp`** SDK (`FastMCP` on 1.x / `MCPServer` on 2.x, stdio)

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
# Optional travel golden path (private sample):
# export DEMO_TRAVEL_SAMPLE_DIR=/path/to/demo_travel_sample
```

## Run

```bash
zeus-dev-helper-mcp
# or
python -m zeus_dev_helper_mcp
```

## Host install

### Grok Build

`grok mcp add` treats flags like `-m` as its own unless they come **after `--`**. Point `command` at this repo’s venv so Grok can start the server even when the TUI was launched without the venv activated:

```bash
# from this repo, after `pip install -e ".[dev]"`
grok mcp add zeus-dev-helper \
  -e ZEUS_CHAT_REQUEST_DIR=/absolute/path/to/zeus_chat_request \
  -e ZEUS_URL=http://localhost:8080 \
  -- "$(pwd)/.venv/bin/python" -m zeus_dev_helper_mcp
```

Equivalent `~/.grok/config.toml` (or `.grok/config.toml` with `--scope project`):

```toml
[mcp_servers.zeus-dev-helper]
command = "/absolute/path/to/zeus_dev_helper_mcp/.venv/bin/python"
args = ["-m", "zeus_dev_helper_mcp"]
cwd = "/absolute/path/to/zeus_dev_helper_mcp"
env = { ZEUS_CHAT_REQUEST_DIR = "/absolute/path/to/zeus_chat_request", ZEUS_URL = "http://localhost:8080" }
enabled = true
```

Then `/mcps` → `r` to refresh, or `grok mcp doctor zeus-dev-helper`.

Common failures:

- `unexpected argument '-m'` — missing `--` before the python command
- `No module named 'zeus_dev_helper_mcp'` / `python: No such file or directory` — Grok did not inherit the venv; use the `.venv/bin/python` path above
- `No module named 'mcp.server.fastmcp'` — mcp 2.x renamed FastMCP; use Helper **0.6.0+** (`mcp>=1.8.0,<3`)

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

## Implemented tools (0.6.0)

| Tool | Status |
| --- | --- |
| `doctor` | Config + catalog reachability |
| `start_project` / `get_checklist` / `next_step` / `gap_report` | **ZDH-8** coach walkthrough |
| `mark_done` / `mark_blocked` | Checklist updates |
| `set_prereq` / `validate_env` / `readiness_check` | **ZDH-4** |
| `bootstrap_scope` | **ZDH-5** live bootstrap + chat_request summary |
| `scaffold_app` / `use_sample` / `write_env` / `verify_local_setup` | **ZDH-6** |
| `travel_golden_path` | **ZDH-10** travel sample golden path |
| `smoke_test_zeus` / `smoke_test_agent` / `diagnose_error` | **ZDH-7** / **ZDH-19** ErrorCode + 0.7 classes |
| `recommend_surface` / `explain_verb` / `lint_verb_args` / `suggest_verb_call` | **ZDH-18** Direct vs agent + V2 verb lint (does not POST; no Runtime scaffold rewrite) |
| `compat_check` | **ZDH-21** version/feature gates on `:8080` (not a COMPAT row) |
| `lint_chat_request` / `bind_contract` / `explain_hash_boundary` / `catalog_diff` | **ZDH-22** catalog coach — extract stamp only |
| `lint_runtime_config` / `lint_app_code` | **ZDH-24** config + anti-example scan (secrets redacted) |
| `explain_req_id_policy` / `detective_links` / `support_pack_from_turn` | **ZDH-23** correlation + redacted support pack |
| `describe_scope` | **ZDH-25** schema-only live describe |
| `recommend_motion` | **ZDH-26** 13 motions; no custom chat_request |
| `suggest_hooks` | **ZDH-27** policy snippets (not a policy engine) |
| `semantic_cache_status` | **ZDH-28** leave enabled=false; optional status probe |
| `list_catalog_modes` / `fetch_chat_request` | **ZDH-14** |
| `explain` / `suggest_demo_prompts` | **ZDH-13** glossary + prompts |
| `handoff_to_multi` | **ZDH-11** multi-agent graduation (gated) |
| `recommend_data_plane_mcp` / `emit_mcp_config` | **ZDH-12** data-plane handoff |
| `helper_metrics` | Local time-to-green (privacy-safe) |

### Day-one coach path

```text
start_project → set_prereq → validate_env → readiness_check
  → use_sample | travel_golden_path | scaffold_app
  → bootstrap_scope / fetch_chat_request / bind_contract / catalog_diff
  → recommend_surface / explain_verb / lint_verb_args / compat_check
  → lint_runtime_config / lint_app_code
  → smoke_test_zeus → smoke_test_agent → gap_report
  → (optional) recommend_data_plane_mcp | handoff_to_multi
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
| `DEMO_TRAVEL_SAMPLE_DIR` | Local clone of demo_travel_sample (ZDH-10) |
| `KOTEN_DOCS_BASE_URL` | default `https://docs.koten.ai` |
| `ZEUS_DEV_HELPER_STATE_DIR` | checklist / prereqs / local metrics |

## Boundaries

| This Helper | Not this Helper |
| --- | --- |
| Onboarding coach to first green | Data-plane Explore/Verify tools |
| Catalog **templates** + readiness/smoke | Inventing `contract_hash` |
| Multi / data-plane **handoffs** | ZJA job runtime / Hub admin mutations |
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
