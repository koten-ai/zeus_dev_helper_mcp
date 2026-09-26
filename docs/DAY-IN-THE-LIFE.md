# Day in the life — developer using Helper MCP

Narrative of how a developer and their coding agent actually use **zeus-dev-helper**. Specs stay in [`DESIGN.md`](DESIGN.md) (MVP), [`DESIGN-0.6.md`](DESIGN-0.6.md) (runtime coach), and [`DESIGN-0.7.md`](DESIGN-0.7.md) (MCP quality / default surface). Prompt phrasing: [`guides/LIST_OF_PROMPT_SAMPLES.md`](../guides/LIST_OF_PROMPT_SAMPLES.md).

---

A developer using this MCP does not open a Zeus dashboard and click tools. They sit in a coding agent (Grok, Claude, Hermes, OpenClaw, …) with **zeus-dev-helper** connected, and talk in English. The agent is the one that calls Helper.

The product promise is one thing: **first green Zeus Client turn** (`session_id` / `req_id` on public `:8080`), then stay on the rails while they build.

Helper is a **coach**, not the app. It does not run data-plane verbs, mutate Hub, or start multi-agent jobs (ZJA).

---

## The setup they already did (once)

MCP is wired in the host (`grok mcp add`, Claude config, etc.) with:

- `ZEUS_URL=http://localhost:8080` (never Hub `:9091`)
- `ZEUS_BUCKET` / `ZEUS_SCOPE` (e.g. `travel-sample` / `inventory`)
- Auth in env only (`ZEUS_USERNAME` / `ZEUS_PASSWORD` or bearer) — Helper never stores secret values
- `ZEUS_CHAT_REQUEST_DIR` (or `GITHUB_TOKEN`) so catalog templates resolve
- `LLM_API_KEY`, `XAI_API_KEY`, or `OPENAI_API_KEY` in this process when the path calls `run_turn` (travel, beer, API, yelp demo). A stored `has_llm_key` flag is not the key
- Optional: `DEMO_TRAVEL_SAMPLE_DIR`, `ZEUS_DEV_HELPER_TOOLSETS` (default `core`)

State lives locally: `~/.config/zeus_dev_helper/checklist.json` (override: `ZEUS_DEV_HELPER_STATE_DIR`). The day is a walk down that checklist, one blocker at a time.

---

## Day one — get to green

This is the day the product is designed for. Typical talk with the agent:

> Start a Zeus first-app. Travel sample, single-agent. Coach me — don’t dump the whole checklist.

### Morning: is anything even up?

| They say | Agent calls | What they learn |
| --- | --- | --- |
| “Is Helper healthy?” | `doctor` | Version, `:8080` vs Hub, catalog templates reachable |
| “Start the project” | `start_project` | Checklist reset: `single-agent:travel` |
| “What’s the one next step?” | `next_step` | Current blocker + 1–3 recommended tools |

They record non-secret prereqs (`set_prereq`), then `validate_env` (presence only). On a `run_turn` path a missing process key is an error (`llm_key_missing`), including beer when `has_llm_key=false`. `set_prereq(has_llm_key=true)` does not clear it. Then a live `readiness_check`: healthz / readyz / version, auth, bootstrap, chat_request. That check marks checklist **1.2** done only when `ZEUS_URL` is set and, for those paths, the process key is present. A non-beer Direct opt-out can close 1.2 from the URL alone. If something is red, they get a `failure_class` (`wrong_port_hub_vs_public`, `auth_failed`, `scope_not_enabled`, `llm_key_missing`, …) and a next action — not a stack dump.

If they do not know a term: `explain("contract_hash")`, `explain("zeus_runtime")`. Glossary + docs link, not a guess.

### Late morning: something on disk

Two paths:

- **Sample:** `use_sample` / `travel_golden_path` if `demo_travel_sample` is cloned
- **From scratch:** `scaffold_app` → `write_env` → `verify_local_setup`

They still copy real secrets into `.env` themselves. Helper only writes `.env.example`, with `LLM_API_KEY=` empty, and writes `config.json` `llm.api_key_env` as the name `LLM_API_KEY`. Checklist **3.2** stays open until `verify_local_setup` on that directory sees a non-empty value for the named variable. The check reports presence only. A secret pasted into `api_key_env` fails as `llm_key_missing`. Do not start uvicorn or Pour before that.

### Afternoon: bind without inventing a hash

This is where people usually go wrong. The coach’s job is to stop that.

1. `list_catalog_modes` / `fetch_chat_request` — **TEMPLATE ONLY**. The hash in the file is not production.
2. Ops stamps the catalog on Hub. The **dev does not invent** `contract_hash`.
3. `bind_contract` copies the stamped hash only; placeholders / `compute_local` are refused.
4. `catalog_diff` / `explain_hash_boundary` — live bootstrap vs on-disk vs bound prefix; MINI-SCHEMA / brief stay out of the hash.

Meanwhile they pick a **surface**, not “just call the LLM”:

| Intent | Surface | Trace-Class |
| --- | --- | --- |
| Natural-language question | `rt.agent.run_turn` | `agent` |
| Typeahead | `rt.data.search` | `direct.interactive` |
| One verb | `rt.data.verb` | `direct.read` |
| Multi-step DAG | agent-for-pipeline | `agent` — **not** pipeline on Direct |

`recommend_surface` / `explain_verb` / `lint_verb_args` / `suggest_verb_call` draft and lint JSON. They **do not POST**. Live field names come from `describe_scope` (types + names only, no sample docs).

`compat_check` confirms engine 0.7 / Client 2.3 on `:8080`. Semantic cache stays **off**.

### Late afternoon: first green

1. `smoke_test_zeus` — no LLM; describe on `:8080` → checklist **5.1**
2. `suggest_demo_prompts` — advice-shaped questions, not SQL
3. `smoke_test_agent` — one `rt.agent.run_turn` → `session_id` / `req_id`, Zeus tools used → **5.2**. When the client package imports, this refuses with `llm_key_missing` unless the process has `LLM_API_KEY`, `XAI_API_KEY`, or `OPENAI_API_KEY`.

If it blows up: paste status / body / `ErrorCode` into `diagnose_error`. They get a class, a docs anchor, and Detective **URL templates** (`/hub/debug/req/<id>`) — Helper does not scrape Hub.

`gap_report` is the stand-up view: progress %, open items, phases 4–7 still red.

When 5.1 + 5.2 are green, `next_step` offers **handoffs only**: `recommend_data_plane_mcp`, `emit_mcp_config`, `handoff_to_multi`. Helper does not become those products.

Time-to-green is local (`helper_metrics`). Nothing leaves the machine.

---

## A later day — they already have a green app

The checklist is mostly done. The 0.6 runtime coach is now the daily loop.

**Morning — “What should this feature even be?”**

> Help me book a hotel in Paris under $200.

`recommend_motion` maps that to a Zeus motion (funnel / explore / verify / …) plus typical verbs and modes. It does **not** generate a new `chat_request`.

Then `recommend_surface` so they do not put typeahead on the agent path or pipeline on Direct.

**Write code, let Helper lint before they hit Zeus**

- `lint_runtime_config` on `config.json` — Hub port, secret literals (redacted in output), `llm.api_key_env` as a variable name (`llm_key_missing` if it holds the secret), cheap path, cache left off
- `lint_app_code` on `main.py` / Dockerfile — `:9091`, hash literals, stale V1 `run_agent` as the default
- `lint_verb_args` on a would-be `find` body — equality-only `where`, MINI-SCHEMA keys, no FTS ids on `get`
- `suggest_hooks` — tenant pin, deny pipeline on Direct, `output_schema` allowlist. Snippets, **not executed**

**A 409 / 401 / `060010` in the terminal**

They do not grep docs first. They paste into `diagnose_error`, then `detective_links` / `explain_req_id_policy` (one UUID per hop, never `base:1`, never Rewind `/v2/session/{id}/turn`). If they need to ping someone: `support_pack_from_turn` — redacted markdown from the last smoke or a debug JSON. Ids and hops only; no prompt bodies, no tokens.

**End of day — “Are we production-ish yet?”**

`gap_report` again. Phase 6 is multi-turn / hooks; phase 7 is anti-patterns and secrets out of prompts. If they ask for Yelp / multi or a data-plane MCP too early, Helper **gates** until single-agent smokes are green.

---

## What a day is *not*

| They might want | Helper’s answer |
| --- | --- |
| `find` / `search` / `get` as MCP tools | No — those stay in the app via Zeus Client |
| Stamp a catalog / enable a scope on Hub | Ops / Workbench. Dev only binds the stamp |
| Invent a hash so CI goes green | Refused (`contract_hash_invent_forbidden`) |
| Hit Hub `:9091` from the app | `wrong_port_hub_vs_public` |
| Turn on semantic cache | Guidance: leave `enabled=false` |
| Start a ZJA multi-agent job | `handoff_to_multi` only |

---

## The shape of the conversation

The human almost never names tools. They say things like:

- “What’s the single next step?”
- “Don’t invent a hash.”
- “Lint this `find` before I POST it.”
- “Hotel typeahead — agent or Direct?”
- “401 from Zeus — what class is that?”
- “Give me a redacted pack for support.”

The agent is supposed to call **one current blocker’s tools**, not dump the 40-tool catalog. That is why `next_step` exists.

A successful day ends with either a **green turn** (day one) or a **legal change that did not leave the rails** (every day after): right port, live stamp, right surface, linted verbs, secrets never in evidence.

---

## Coach path (for chaining)

Day-one order (not required per prompt):

```text
doctor → start_project → set_prereq → validate_env → readiness_check
  → list_catalog_modes → fetch_chat_request → explain → recommend_surface
  → use_sample | travel_golden_path | scaffold_app
  → bootstrap_scope / bind_contract / catalog_diff
  → smoke_test_zeus → smoke_test_agent → gap_report
  → (optional) recommend_data_plane_mcp | handoff_to_multi
```

Hard constraints throughout:

- Public Zeus API is **`:8080`**, never Hub **`:9091`** on the app path.
- Never invent `contract_hash`. `fetch_chat_request` is **template only**.
- No secrets in checklist evidence or support packs.
- Coach only: this MCP does not run data-plane verbs, Hub admin mutations, or ZJA jobs.
