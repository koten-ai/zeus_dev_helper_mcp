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
doctor → start_project → next_step
  → set_prereq → validate_env → readiness_check
  → use_sample | scaffold_app → bind_contract → recommend_surface
  → smoke_test_zeus → smoke_test_agent → diagnose_error
```

Prefer `next_step` over dumping the full checklist.

- **Default (UI):** `start_project(sample=travel)` → **`use_sample`**, which **clones** public [`demo_travel_sample`](https://github.com/koten-ai/demo_travel_sample) when missing (optional `project_name` for the directory) and sets `DEMO_TRAVEL_SAMPLE_DIR`.
- **API-only:** user asks for an API/REST app → `start_project(sample=api)` → `scaffold_app(app_kind=api, coding_language=python)` (FastAPI `POST /turn` on `kotenai-zeus-client`). Other languages not scaffolded yet.
- Credentials from chat → process env / gitignored `.env`; `set_prereq` presence flags only.
- Integrating into an arbitrary existing repo is **out of scope**.

Read `zeus-helper://` resources for glossary, verbs, policies, and catalog modes. Hosts can pick prompts `first_green`, `smoke_question`, and `support_pack`.

## Default tools (`core`)

Live `tools/list` is the call contract. Default surface is **12 tools** (`ZEUS_DEV_HELPER_TOOLSETS=core`).

| Tool | Job |
| --- | --- |
| `doctor` | Health. `detail=health\|env\|compat\|cache\|all` (env/compat/cache fold lint-toolset checks) |
| `start_project` | Init checklist; `sample=travel` (UI default) or `sample=api` |
| `next_step` | Current item plus recommended tools and resource links |
| `set_prereq` | Store non-secret prereqs (presence flags only for secrets) |
| `readiness_check` | Live gates: healthz / readyz / version, auth, bootstrap |
| `scaffold_app` | CLI or FastAPI (`app_kind=cli\|api`) ZeusRuntime app; python only |
| `use_sample` | Travel UI sample plus golden-path check (or gate other samples) |
| `bind_contract` | Copy a stamped `contract.hash` only; refuses empty / local compute |
| `recommend_surface` | Intent → Client surface + do-not list |
| `smoke_test_zeus` | No LLM: readiness plus a read-only describe |
| `smoke_test_agent` | One Client `run_turn` (needs `[agent]` extra and an LLM key) |
| `diagnose_error` | Map HTTP / body / error codes to a failure class |

Opt-in toolsets (static, comma-separated): `catalog`, `lint`, `travel`, `support`, `handoff`. `all` enables every set. Full when/args/side-effects map: [`docs/TOOLS.md`](docs/TOOLS.md).

Resources (always on): `zeus-helper://checklist`, `zeus-helper://glossary/{topic}`, `zeus-helper://verbs/{name}`, `zeus-helper://policy/hash-boundary`, `zeus-helper://policy/req-id`, `zeus-helper://catalog/modes`.

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
| `ZEUS_CHAT_REQUEST_DIR` | Local directory of min catalog templates; auto-set when `list_catalog_modes` / `fetch_chat_request` locate or clone public `zeus_chat_request` |
| `DEMO_TRAVEL_SAMPLE_DIR` | Local sample directory for `use_sample` / `travel_golden_path` |
| `ZEUS_DEV_HELPER_STATE_DIR` | Checklist, prereqs, and local metrics (default `~/.config/zeus_dev_helper`) |
| `ZEUS_DEV_HELPER_TOOLSETS` | Static toolsets: `core` (default), plus `catalog,lint,travel,support,handoff` or `all` |

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

## License

BSD-3-Clause — see [LICENSE](LICENSE).
