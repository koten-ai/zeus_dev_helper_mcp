# Zeus Dev Helper MCP

<!-- mcp-name: io.github.koten-ai/zeus-dev-helper -->

Stdio MCP server that coaches a coding agent and a human to a first successful Zeus Client app turn.

This is not a data-plane MCP. It does not run Explore/Verify verbs on your behalf, invent contract hashes, or perform Hub admin mutations. After the first-green smokes pass, data-plane and multi-agent work are **handoffs only**.

| | |
| --- | --- |
| **Package** | `zeus-dev-helper-mcp` |
| **Registry name** | `io.github.koten-ai/zeus-dev-helper` |
| **Transport** | stdio |
| **Python** | 3.11+ |
| **MCP SDK** | `mcp` (`FastMCP` on 1.x / `MCPServer` on 2.x) |

## What it does

The server walks a first-app checklist: prereqs, live readiness on the public Zeus API, catalog templates, contract bind (copy a stamped hash only), surface/verb coaching, config lint, and smoke tests. Prefer a live Zeus stamp for catalogs. `fetch_chat_request` is always **template only**.

Hard constraints the tools enforce:

- Public Zeus API on port **8080** only (never Hub **9091** from the app path)
- Never invent `contract_hash`
- No secrets in tool results, checklist evidence, or support packs
- Semantic cache stays off

## Install

```bash
pip install zeus-dev-helper-mcp
# or
uvx zeus-dev-helper-mcp
```

Optional extra for `smoke_test_agent` (pulls the Zeus Client package):

```bash
pip install "zeus-dev-helper-mcp[agent]"
```

## Run

```bash
zeus-dev-helper-mcp
# or
python -m zeus_dev_helper_mcp
```

Prefer the published console script (`uvx` / `pip install`) so hosts do not need a source checkout.

## Host install

### Grok Build

`grok mcp add` treats flags like `-m` as its own unless they come **after `--`**.

```bash
grok mcp add zeus-dev-helper \
  -e ZEUS_URL=http://localhost:8080 \
  -- uvx zeus-dev-helper-mcp
```

From a local checkout after `pip install -e ".[dev]"`, point `command` at this tree’s venv so the host can start the server even when it was launched without the venv activated:

```bash
grok mcp add zeus-dev-helper \
  -e ZEUS_URL=http://localhost:8080 \
  -- "$(pwd)/.venv/bin/python" -m zeus_dev_helper_mcp
```

Equivalent config:

```toml
[mcp_servers.zeus-dev-helper]
command = "uvx"
args = ["zeus-dev-helper-mcp"]
env = { ZEUS_URL = "http://localhost:8080" }
enabled = true
```

Then refresh MCP servers, or `grok mcp doctor zeus-dev-helper`.

Common failures:

- `unexpected argument '-m'` — missing `--` before the python command
- `No module named 'zeus_dev_helper_mcp'` / `python: No such file or directory` — the host did not inherit the venv; use the `.venv/bin/python` path above
- `No module named 'mcp.server.fastmcp'` — mcp 2.x renamed FastMCP; use Helper **0.6.0+** (`mcp>=1.8.0,<3`)

### Claude Code / Claude Desktop

```json
{
  "mcpServers": {
    "zeus-dev-helper": {
      "command": "uvx",
      "args": ["zeus-dev-helper-mcp"],
      "env": {
        "ZEUS_URL": "http://localhost:8080"
      }
    }
  }
}
```

### Other stdio hosts

Point the host’s MCP stdio entry at `uvx zeus-dev-helper-mcp` (or `python -m zeus_dev_helper_mcp` from a venv) with the same env vars.

## Day-one coach path

```text
doctor → start_project → set_prereq → validate_env → readiness_check
  → list_catalog_modes → fetch_chat_request → explain → recommend_surface
  → use_sample | travel_golden_path | scaffold_app
  → bootstrap_scope / bind_contract / catalog_diff / explain_hash_boundary
  → recommend_surface / explain_verb / lint_verb_args / compat_check
  → lint_runtime_config / lint_app_code
  → smoke_test_zeus → smoke_test_agent → gap_report
  → (optional) recommend_data_plane_mcp | emit_mcp_config | handoff_to_multi
```

Prefer `next_step` over dumping the full checklist.

## Tools

Live `tools/list` is the call contract. Names below are the coach surface.

### Start and health

| Tool | Job |
| --- | --- |
| `doctor` | Version, public config (no secrets), catalog reachability |
| `start_project` | Init or reset the first-app checklist |
| `helper_metrics` | Local time-to-green (never leaves the machine) |

### Checklist

| Tool | Job |
| --- | --- |
| `get_checklist` | Full checklist JSON |
| `next_step` | Current item plus recommended tools |
| `gap_report` | Open items and progress |
| `mark_done` | Mark an item done (evidence must not include secrets) |
| `mark_blocked` | Mark an item blocked |

### Env and platform

| Tool | Job |
| --- | --- |
| `set_prereq` | Store non-secret prereqs (presence flags only for secrets) |
| `validate_env` | Shape check: URL port, key presence, bucket/scope, templates |
| `readiness_check` | Live gates: healthz / readyz / version, auth, bootstrap |
| `compat_check` | Version and feature gates on `:8080` |
| `bootstrap_scope` | Live bootstrap plus chat_request summary |

### Catalogs and contracts

| Tool | Job |
| --- | --- |
| `list_catalog_modes` | List min catalog modes from local templates |
| `fetch_chat_request` | Fetch a min template by mode (**TEMPLATE ONLY**) |
| `lint_chat_request` | Read-only lint of a chat_request |
| `bind_contract` | Copy a stamped `contract.hash` only; refuses empty / local compute |
| `explain_hash_boundary` | What is excluded from the hash |
| `catalog_diff` | Live bootstrap summary vs on-disk vs bound hash prefix |

### Project on disk

| Tool | Job |
| --- | --- |
| `use_sample` | Point at a local travel sample (or gate other samples) |
| `travel_golden_path` | Travel sample phases plus optional layout check |
| `scaffold_app` | Minimal app files (`main.py`, requirements, `.env.example`) |
| `write_env` | Write `.env.example` from prereqs (never secret values) |
| `verify_local_setup` | Import check plus optional scaffold files |
| `lint_runtime_config` | Lint runtime config: `:8080`, auth mode, env names, cache off |
| `lint_app_code` | Anti-example scan (stale V1, hash literals, Hub port) |

### Surface and verbs (coach only; does not POST find/search/get/pipeline)

| Tool | Job |
| --- | --- |
| `recommend_surface` | Intent → Client surface + do-not list |
| `explain_verb` | Static V2 verb encyclopedia |
| `lint_verb_args` | Lint a would-be JSON body (`posted=false`) |
| `suggest_verb_call` | Draft a legal JSON body from a goal (does not POST) |

### Smoke and diagnose

| Tool | Job |
| --- | --- |
| `smoke_test_zeus` | No LLM: readiness plus a read-only describe |
| `smoke_test_agent` | One Client agent turn (needs `[agent]` extra and an LLM key) |
| `suggest_demo_prompts` | Advice-shaped starter questions |
| `describe_scope` | Live schema-only describe (entity types and field names; no document samples) |
| `diagnose_error` | Map HTTP / body / error codes to a failure class |

### Correlation and support

| Tool | Job |
| --- | --- |
| `explain_req_id_policy` | One UUID per hop; never composite hop ids |
| `detective_links` | Hub Detective URL templates only (does not fetch) |
| `support_pack_from_turn` | Redacted markdown from debug JSON or last smoke artifact |

### Motion, hooks, cache, glossary

| Tool | Job |
| --- | --- |
| `recommend_motion` | User job → one of 13 motions; does not generate a catalog |
| `suggest_hooks` | Middleware snippets (`executed=false`; Helper is not a policy engine) |
| `semantic_cache_status` | Leave enabled=false; optional status probe |
| `explain` | Short glossary answer |

### Post-green handoffs

Gated on smoke **5.1 + 5.2** unless forced.

| Tool | Job |
| --- | --- |
| `recommend_data_plane_mcp` | Hand off to a future scope-bound data-plane MCP |
| `emit_mcp_config` | Safe-by-default MCP config fragment (placeholder command/args) |
| `handoff_to_multi` | Multi-agent graduation guidance (does not run jobs) |

## Environment

Secrets stay in the process environment. `set_prereq` stores presence flags only. Tool results redact secret values.

| Variable | Purpose |
| --- | --- |
| `ZEUS_URL` | Public Zeus API base URL (port 8080) |
| `ZEUS_BUCKET` / `ZEUS_SCOPE` / `ZEUS_COLLECTION` | Scope for bootstrap and auth probes |
| `ZEUS_MODE` | Default catalog mode (`analytics`) |
| `ZEUS_AUTH_MODE` | Auth mode (`none`, basic, bearer) |
| `ZEUS_USERNAME` / `ZEUS_PASSWORD` | Basic auth (never logged) |
| `ZEUS_BEARER_TOKEN` | Bearer auth (never logged) |
| `LLM_API_KEY` / `OPENAI_API_KEY` | Presence checked by `validate_env`; required for `smoke_test_agent` |
| `ZEUS_CHAT_REQUEST_DIR` | Local directory of min catalog templates (offline `list_catalog_modes` / `fetch_chat_request`) |
| `DEMO_TRAVEL_SAMPLE_DIR` | Local sample directory for `use_sample` / `travel_golden_path` |
| `ZEUS_DEV_HELPER_STATE_DIR` | Checklist, prereqs, and local metrics (default `~/.config/zeus_dev_helper`) |

## Boundaries

| This MCP | Not this MCP |
| --- | --- |
| Onboarding coach to first green | Data-plane Explore/Verify tools |
| Catalog **templates** plus readiness and smoke | Inventing or locally computing `contract_hash` |
| Verb explain / lint / draft (`posted=false`) | POSTing `find` / `search` / `get` / `pipeline` |
| Detective **URL templates** | Hub scrape or Hub admin mutations |
| Multi / data-plane **handoffs** | Multi-agent job runtime |
| Local checklist and metrics | Shipping secrets in evidence or support packs |

## Dev install

From a local checkout:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# optional agent smoke:
pip install -e ".[agent]"
export ZEUS_URL=http://localhost:8080
```

```bash
pytest -q
```

## MCP Registry

Official registry name: `io.github.koten-ai/zeus-dev-helper`. The registry hosts metadata only; the install artifact is the PyPI package `zeus-dev-helper-mcp`.
