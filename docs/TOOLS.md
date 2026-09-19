# Helper tool reference (0.7)

Coach map for the Developer Helper MCP: **when** to call each tool, **args that matter**, **side effects**, and **do-not**.

Default `tools/list` is the **`core`** toolset (≤15). Extra tools are static opt-in via `ZEUS_DEV_HELPER_TOOLSETS` (`catalog`, `lint`, `travel`, `support`, `handoff`, or `all`). This file still documents the full catalog.

Knowledge (glossary, verbs, checklist, policies, catalog modes) is MCP **resources** under `zeus-helper://`. Walkthroughs are MCP **prompts** (`first_green`, `smoke_question`, `support_pack`).

This is not Zeus public API documentation (`find` / `search` / `describe` live in Zeus `docs/API`). Helper does not expose those verbs as MCP tools.

| Layer | Role |
| --- | --- |
| Live MCP `tools/list` | Call contract (names, JSON schema, annotations). Trust the running server if this file disagrees. |
| This file | Coach map for agents and humans (full catalog). |
| [`AGENTS.md`](../AGENTS.md) | Load order + hard constraints. |
| [`README.md`](../README.md) | Install + host config. |
| [`DESIGN.md`](DESIGN.md) / [`DESIGN-0.6.md`](DESIGN-0.6.md) / [`DESIGN-0.7.md`](DESIGN-0.7.md) | Frozen product design + increments. |
| [`guides/LIST_OF_PROMPT_SAMPLES.md`](../guides/LIST_OF_PROMPT_SAMPLES.md) | How a human should *ask*. |

---

## Hard constraints (every tool)

- Public API **`:8080`** only. Never Hub **`:9091`** from the app path.
- Never invent `contract_hash`. Never `compute_local` for production bind.
- `fetch_chat_request` is **TEMPLATE ONLY**. Prefer a live Zeus stamp.
- No secrets in tool results, checklist evidence, or support packs.
- Semantic cache stays **off**. Direct / typeahead must not call `agent_memory`.
- Verb tools explain, lint, and draft. They do **not** POST `find` / `search` / `get` / `pipeline`.
- `suggest_hooks` returns snippets with `executed=false`. Helper is not a policy engine.
- After checklist **5.1 + 5.2** green: data-plane MCP and multi-agent are **handoffs only** (not ZJA, not Hub admin).

Prefer `next_step` over dumping the full checklist.

---

## Day-one path

```text
doctor → set_prereq (when user already named URL/sample) → start_project → next_step
  → readiness_check → recommend_surface
  → use_sample | scaffold_app → bind_contract (agent path)
  → smoke_test_zeus → smoke_test_agent (only if LLM) → diagnose_error
```

If the user already gave a Zeus URL or sample name, call `set_prereq` with **those** values before relying on Helper localhost defaults. Do not grep the Zeus engine tree or hand-roll OpenAPI curl for first green — use `readiness_check` / `smoke_test_zeus` / `zeus-helper://`. Call `recommend_surface` before choosing Travel LLM vs Direct UI vs FastAPI. If `has_llm_key=false`, do not treat travel + `smoke_test_agent` as the only path.

**Bootstrap app kind**

| User intent | `start_project` | Project on disk |
| --- | --- | --- |
| Unspecified / UI / “show me the app” (**default**, **agent-plane**) | `sample=travel` | `use_sample` → **`demo_travel_sample`** / TravelPlan (LLM + `run_turn`) |
| Website + beer-sample / no LLM (**data-plane Direct**) | `sample=beer` | `use_sample(sample=beer)` → **`demo_beer_sample`** (find→get, no pipeline; never clone travel) |
| “API” / REST / FastAPI | `sample=api` | `scaffold_app(app_kind=api, coding_language=python)` |
| Minimal CLI fallback | (travel unavailable) | `scaffold_app(app_kind=cli)` |

Direct websites may copy TravelPlan’s BFF/same-origin/config shape only — **do not copy `run_turn`** unless this is an agent app. Agent vs Direct: [Using Zeus Client](https://docs.koten.ai/zeus-client/using-zeus-client).

Credentials in the user message → env / gitignored `.env` + `set_prereq` **presence flags** only (never password values in MCP args). Existing-repo integration is **out of scope**.

Resources (not default tools): `zeus-helper://checklist` / `glossary/{topic}` / `verbs/{name}` / `policy/*` / `catalog/modes`. Extra tools: `ZEUS_DEV_HELPER_TOOLSETS=core,lint,catalog` (or `all`).

---

## Side-effect tags

| Tag | Meaning |
| --- | --- |
| `none` | No writes; no Zeus HTTP |
| `state` | Checklist, prereqs, and/or metrics under `ZEUS_DEV_HELPER_STATE_DIR` (default `~/.config/zeus_dev_helper`) |
| `disk` | Writes under `target_dir` (never secret values) |
| `live GET` | Public `:8080` GET (`/healthz`, `/readyz`, `/version`, `/v1/ai/bootstrap/…`) |
| `live POST` | Public `:8080` read-only POST (`/v2/{bucket}/{scope}/describe` or one agent turn) |
| `catalog` | Local `ZEUS_CHAT_REQUEST_DIR` (auto-clone public repo when unset) or GitHub Contents |
| `LLM` | Needs LLM key + optional extra `kotenai-zeus-client` |

---

## 1. Start and health

| Tool | Job | Args | Effects | When / next |
| --- | --- | --- | --- | --- |
| `doctor` | Version, public config (no secrets), catalog reachability | — | `catalog` | First call. Then `start_project`. |
| `start_project` | Init or reset the first-app checklist | `goal=single-agent`, `sample=travel\|beer\|api`, `force_multi=false` | `state` | After doctor. Default **`travel`** (UI). `sample=beer` → Direct/`ui-direct` (no LLM). `sample=api` → API track. Then `set_prereq`. Never turns semantic cache on. Multi / `sample=yelp` gated until 5.1+5.2 unless `force_multi`. |
| `helper_metrics` | Local time-to-green (never leaves the machine) | — | none (reads `state`) | Anytime. Events are recorded on start / smoke green. |

**Do not:** treat `doctor` as a Zeus cluster health check (`readiness_check` does that). Do not pass passwords into `start_project`.

---

## 2. Checklist

Phases: **0** intent → **1** prereqs → **2** platform → **3** project on disk → **4** bind → **5** green → **6** customize → **7** production-ish.

| Tool | Job | Args | Effects | When / next |
| --- | --- | --- | --- | --- |
| `get_checklist` | Full checklist JSON | — | none | Only when the user asks for the whole list. Prefer `next_step`. |
| `next_step` | Single current item + `recommended_tools` | — | none | Default coach turn. After smokes green, also suggests handoff tools. |
| `gap_report` | Open items (phases 4–7 emphasis) + progress | — | none | After smokes, or when asked “what’s left”. |
| `mark_done` | Mark an item done | `item_id`, `evidence` (optional) | `state` | After a probe actually succeeded. Evidence: no secrets / tokens / bodies. |
| `mark_blocked` | Mark an item blocked | `item_id`, `reason` | `state` | When a gate fails and the human must act. |

**Do not:** dump the entire checklist every turn. Do not put passwords, bearer tokens, or full Zeus bodies in `evidence`.

---

## 3. Env and platform

| Tool | Job | Args | Effects | When / next |
| --- | --- | --- | --- | --- |
| `set_prereq` | Store non-secret prereqs | `zeus_url`, `auth_mode`, `bucket`, `scope`, `collection`, `mode`, `role`, presence flags (`has_llm_key`, `has_bearer`, `has_username`, `has_password`) | `state` | After `start_project` (or right after `doctor` when the user already named a URL/sample). Persisted `zeus_url` / `bucket` / `scope` **override** MCP host `ZEUS_*` env defaults (common `localhost:8080` must not win). Secrets stay in env (`ZEUS_PASSWORD`, `ZEUS_BEARER_TOKEN`, `LLM_API_KEY`). Then `validate_env`. |
| `validate_env` | Shape check: URL port, LLM key presence, bucket/scope, catalog templates | — | `catalog` | After `set_prereq`. Then `readiness_check`. Flags `:9091` as `wrong_port_hub_vs_public`. |
| `readiness_check` | Live gates: healthz / readyz / version, auth, bootstrap, chat_request | `update_checklist=true` | `live GET`, optional `state` | After env looks sane. Then catalogs or `bootstrap_scope`. |
| `compat_check` | `GET /version` + `/healthz` plus static 0.7 feature gates | `zeus_url` (optional override) | `live GET` | Before relying on 0.7 behaviour (req-id policy, V1 session gone, semantic cache floor). **Not** a COMPAT matrix row. |
| `bootstrap_scope` | Live `GET /v1/ai/bootstrap/scope/{bucket}/{scope}` + chat_request summary | `bucket`, `scope`, `mode`, `detail=summary\|full`, `update_checklist=true` | `live GET`, optional `state` | After readiness. Prefer `summary`. Then stamp on Hub; Helper does not stamp. |

**Do not:** store secret *values* via `set_prereq` (presence flags only). Do not point `zeus_url` at Hub `:9091`. Do not treat `compat_check` as permission to invent a COMPAT row.

---

## 4. Catalogs and contracts

Prefer a **live Zeus stamp**. `zeus_chat_request` is min templates only.

| Tool | Job | Args | Effects | When / next |
| --- | --- | --- | --- | --- |
| `list_catalog_modes` | V2 min modes from `zeus_chat_request` | — | `catalog` (+ optional `git clone`) | Before fetching a template. When `ZEUS_CHAT_REQUEST_DIR` is unset, locates or shallow-clones public `zeus_chat_request` and sets the env (`GITHUB_TOKEN` remains fallback). |
| `fetch_chat_request` | Fetch a min template by mode | `mode=analytics`, `detail=summary\|full` | `catalog` (+ optional `git clone`) | After modes. Always returns **TEMPLATE ONLY**. Auto-clones public repo when env unset. Then Hub stamp → `bind_contract`. |
| `lint_chat_request` | Read-only lint (`_format`, verbs, `TO_BE_FILLED`) | `path` **or** `json_text` | none | Before bind. Never stamps. |
| `bind_contract` | Copy stamped `contract.hash` only | `path` or `json_text`; optional `bucket`, `scope`, `mode` | none | After a real Hub stamp. Refuses empty / `TO_BE_FILLED` / `compute_local` (`contract_hash_invent_forbidden`). Returns a `scope_contracts` snippet to paste. |
| `explain_hash_boundary` | What is **excluded** from the hash (MINI-SCHEMA, SCOPE BRIEF, `guidance` / `contract` / `metadata` / `_*`) | — | none | Checklist 4.2. Inject schema/brief at call time; do not bake them into the stamp expecting the hash to change. |
| `catalog_diff` | Live bootstrap summary vs on-disk vs bound hash **prefix** | `path` or `json_text`, optional `bound_hash` | optional `live GET` | After bind, if stamp and disk might have drifted. Not full catalog bodies. |

**Do not:** invent or locally compute a production hash. Do not treat a min template as stamped for this cluster.

---

## 5. Project on disk

| Tool | Job | Args | Effects | When / next |
| --- | --- | --- | --- | --- |
| `use_sample` | Travel: locate or **clone** public `demo_travel_sample`; set `DEMO_TRAVEL_SAMPLE_DIR`; prepare standalone Docker when needed. Beer: **write** `demo_beer_sample` Direct UI (FastAPI BFF find→get + static; no pipeline; no LLM) | `sample=travel\|beer`, optional `sample_dir`, `project_name` (dir name), `parent_dir`, `clone_if_missing=true` (travel) | `state` + process env + disk (beer write / travel Docker rewrite) | Default UI path is travel. `sample=beer` defaults `project_name=demo_beer_sample`. Existing non-empty dir must look like the beer sample or fails. Yelp/multi → `handoff_to_multi` gate. |
| `travel_golden_path` | Same ensure/clone + golden-path phases | same as `use_sample` travel args | `state` + env if layout ok (marks 0.2 / 3.1) | Same track as `use_sample` for travel. Then readiness + smokes with the sample’s bucket/scope. |
| `scaffold_app` | ZeusRuntime middle-man on disk | `target_dir`, `project_name`, `force=false`, `app_kind=cli\|api`, `coding_language=python` | `disk`, `state` | **`api`**: FastAPI `GET /healthz` + `POST /turn`. **`cli`**: one-shot `main.py`. Only **python** / `kotenai-zeus-client` today; other languages → `unsupported_coding_language`. UI demos use `use_sample`, not this tool. |
| `write_env` | Write `.env.example` from prereqs | `target_dir` | `disk` | After scaffold/sample. Never writes secret values. |
| `verify_local_setup` | `zeus_client` import + optional scaffold files | `target_dir` | none | After files exist, before smokes. |
| `lint_runtime_config` | Lint `config.json`: `:8080`, `auth_mode`, env **names**, cheap path, cache off | `path` | none (redacts secrets) | Before agent smoke. Hub port is an error. |
| `lint_app_code` | Anti-example scan of `main.py` / Dockerfiles (stale V1, hash literals, `:9091`) | `path` (file or dir) | none | Before calling the path “production-ish”. |

**Do not:** commit `.env`. Do not emit V1 `ZeusClient` / `run_agent` from `scaffold_app`. Do not treat Helper as an existing-app integrator — point users at `demo_travel_sample`.

---

## 6. Surface and V2 verbs (coach only)

These tools do **not** run Zeus data-plane verbs (except `lint_verb_args` may optionally `describe` for field names).

| Tool | Job | Args | Effects | When / next |
| --- | --- | --- | --- | --- |
| `recommend_surface` | Intent → Client surface + Trace-Class + do-not list | `intent` (`nl_question` \| `typeahead` \| `single_verb` \| `multi_step`), optional `qps`, `needs_llm` | none | Before writing app code. High `qps` stays off `run_turn`. **Website + named sample (beer-sample) + `needs_llm=false` → Direct**, not travel agent — then `use_sample(sample=beer)`. |
| `explain_verb` | Static V2 encyclopedia: path class, demux, Direct vs pipeline | `name` (`find`, `search`, `get`, `describe`, `pipeline`, …) | none | When drafting a verb. `find`: `return` is the router; `where` is equality-only. |
| `lint_verb_args` | Lint a would-be JSON body | `verb`, `body` (JSON string), optional `mini_schema` | optional `live POST` describe (schema only) | After `explain_verb`. Rejects `$gt` / non-equality `where`, FTS `biz:` keys as node ids, pipeline on Direct. `posted=false`. |
| `suggest_verb_call` | Draft a **legal** JSON body from a goal | `goal`, optional `mini_schema` | none | Guidance only — **does not POST**. Then the **app** calls `rt.data.verb` / agent. |

**Intents → surface**

| Intent | Surface | Trace-Class |
| --- | --- | --- |
| `nl_question` | `rt.agent.run_turn` (or Direct when `needs_llm=false`) | `agent` / `direct.read` |
| `typeahead` | `rt.data.search` | `direct.interactive` |
| `single_verb` | `rt.data.verb` | `direct.read` |
| `multi_step` | `agent-for-pipeline` | `agent` |

**ZDM-2 case:** website + sample + no LLM → `needs_llm=false` → Direct Trace-Class; `start_project` / `next_step` must not recommend `use_sample(travel)` or `smoke_test_agent` as the primary path. Named `beer-sample` bucket + `has_llm_key=false` reroutes default travel to `sample=beer`.

**Do not:** pipeline on Direct; `agent_memory` on Direct/typeahead; composite hop ids (`base:1`); invent `contract_hash`.

Verbs Helper can explain (not call): `explain`, `return`, `describe`, `analyze`, `get`, `find`, `search`, `traverse`, `set`, `order`, `enrich`, `project`, `pipeline` (Direct-rejected), `named_query`.

---

## 7. Smoke and diagnose

| Tool | Job | Args | Effects | When / next |
| --- | --- | --- | --- | --- |
| `smoke_test_zeus` | No LLM: readiness + `POST /v2/{bucket}/{scope}/describe` | `update_checklist=true` | `live GET` + `live POST`, optional `state` | Checklist **5.1**. Returns `req_id`. Then `smoke_test_agent`. |
| `smoke_test_agent` | One Client `rt.agent.run_turn` | `question` (advice-shaped), `update_checklist=true` | `LLM` + Zeus HTTP, `state` (`last_smoke_agent.json` ids/hops only) | Checklist **5.2**. Needs `[agent]` extra (`kotenai-zeus-client>=2.3.0`) + LLM key. Returns `TurnResult` (`session_id` / `req_id`). If the client package is missing **and** `demo_travel_sample` documents Docker install (`DEMO_TRAVEL_SAMPLE_DIR` / persisted path), returns guide-only `install_path=docker` (`docker compose up --build`) instead of only pip; otherwise `install_path=pip`. |
| `suggest_demo_prompts` | Advice-shaped starter questions | — | none | Before 5.2. Prefer NL over raw SQL. |
| `describe_scope` | Live MINI-SCHEMA: entity types + field names | `bucket`, `scope` (else env) | `live POST` | Schema for lint / UI. **No document samples.** Cap applied. |
| `diagnose_error` | Map HTTP / body / ErrorCode / `error_class` → `failure_class` + docs anchor | `status`, `body`, `message`, `error_code`, `error_class`, `req_id`, `session_id`, `chat_id`, `turn_id`, `zeus_url` | none (Detective **URLs only**) | On any red path. Does not import `zeus_client` on the default extra. |

**Do not:** paste secrets into `diagnose_error` bodies if you can redact first. Do not scrape Hub Detective. `describe_scope` must not be used to dump rows.

---

## 8. Correlation and support

| Tool | Job | Args | Effects | When / next |
| --- | --- | --- | --- | --- |
| `explain_req_id_policy` | One UUID per hop; never `base:1`; never Rewind `/v2/session/{id}/turn` | — | none | On `invalid_req_id` / composite hops. Then `detective_links`. |
| `detective_links` | Hub Detective URL **templates** | `req_id`, `chat_id`, optional `zeus_url` | none | After a failed hop with ids. Helper does not fetch them. |
| `support_pack_from_turn` | Redacted markdown from debug JSON or last smoke artifact | `debug_json` or `path` (else `last_smoke_agent.json`) | none (reads `state` / file) | For ops handoff. Drops prompt / body / token keys. |

**Do not:** send `X-Zeus-Req-Id: base:1`. Do not Rewind `POST /v2/session/{id}/turn`. Do not include prompt or result bodies in the pack.

---

## 9. Motion, hooks, cache

| Tool | Job | Args | Effects | When / next |
| --- | --- | --- | --- | --- |
| `recommend_motion` | User job → one of 13 Zeus motions + typical verbs/modes | `user_job` | none | Intent / customize. **`chat_request` is always null** — does not generate a catalog. Motions ≠ Zeus modes. |
| `suggest_hooks` | Middleware snippets | `recipe` empty (all) or `tenant_pin` \| `deny_pipeline_direct` \| `output_schema_allowlist` \| `never_promote_ocr` | none | Checklist 6.1 / 7.1. `executed=false`. Wire in the app; Helper does not install hooks. |
| `semantic_cache_status` | Coach: leave `enabled=false`; optional `GET /v2/agent_memory/status` | optional `zeus_url` | optional `live GET` | Never enable from Helper. 404 → engine too old or flag off. Direct must not call `agent_memory`. |

**13 motions:** Funnel, Explore, Verify, Compare, Monitor, Explain, Compose, Simulate, Triage, Route, Refine, Remember, Custom. `explain("motion")` lists them vs `mode`.

---

## 10. Glossary

| Tool | Job | Args | Effects | When / next |
| --- | --- | --- | --- | --- |
| `explain` | Short glossary answer + docs deep-link | `topic` | none | Anytime a term is unclear. Not a substitute for this catalog (`explain("helper_mcp")` is the product blurb). |

Useful topics: `public_api`, `hub`, `contract_hash`, `chat_request`, `zeus_runtime`, `turn_result`, `cheap_path`, `direct`, `typeahead`, `pipeline`, `trace_class`, `req_id_policy`, `hash_boundary`, `semantic_cache`, `motion`, `helper_mcp`, `data_plane_mcp`. Motion names (e.g. `funnel`) are topics too. Unknown topic → list of known keys.

---

## 11. Post-green handoffs

Gated on checklist **5.1 + 5.2** done (except `force` on multi).

| Tool | Job | Args | Effects | When / next |
| --- | --- | --- | --- | --- |
| `recommend_data_plane_mcp` | Hand off to a future scope-bound Data Plane MCP | — | none | After green (or ~50% progress). Helper stays the coach. Package may still be unpublished. |
| `emit_mcp_config` | Safe-by-default MCP fragment (scope allowlist, read-only) | `server_name=zeus-data-plane`, `read_only=true`, `host=claude` | none | After the recommend. **Placeholder** command/args — do not install a non-existent package. |
| `handoff_to_multi` | Multi-agent graduation guidance (ZJA) | `force=false` | none | After green, or `force=true` to preview. Helper does **not** run jobs. |

**Do not:** mix data-plane Explore/Verify tools into this server. Do not invent Data Plane install packages or Yelp clone URLs.

---

## Checklist item → tools

What `next_step` / `gap_report` recommend (`walkthrough.TOOL_HINTS`):

| Item | Title | Tools |
| --- | --- | --- |
| 0.1 | Choose single-agent first app | `start_project`, `explain`, `recommend_motion` |
| 0.2 | Pick sample or custom domain | `use_sample`, `travel_golden_path`, `scaffold_app` |
| 1.1 | Python 3.11+ / pip | `doctor`, `verify_local_setup` |
| 1.2 | `ZEUS_URL` and LLM key | `set_prereq`, `validate_env` |
| 2.1 | Zeus `:8080` reachable | `readiness_check`, `smoke_test_zeus` |
| 2.2 | Auth works | `readiness_check`, `set_prereq` |
| 2.3 | Scope enabled | `bootstrap_scope`, `readiness_check` |
| 3.1 | Scaffold or clone sample | `scaffold_app`, `use_sample`, `travel_golden_path` |
| 3.2 | Config / env template | `write_env`, `scaffold_app` |
| 4.1 | Fetch or sync chat_request | `fetch_chat_request`, `list_catalog_modes`, `bootstrap_scope` |
| 4.2 | Pin `scope_contracts` after stamp | `bind_contract`, `catalog_diff`, `explain_hash_boundary` |
| 5.1 | `smoke_test_zeus` | `smoke_test_zeus`, `describe_scope` |
| 5.2 | `smoke_test_agent` | `smoke_test_agent`, `suggest_demo_prompts` |
| 6.1 | Multi-turn and/or hooks | `suggest_hooks`, `explain`, `suggest_demo_prompts` |
| 7.1 | No anti-patterns; secrets out | `diagnose_error`, `suggest_hooks`, `support_pack_from_turn`, `detective_links`, `gap_report` |

Ops note on **4.2:** stamp is usually Administrator / Hub Workbench. Dev binds `contract_id` + `contract_hash` after the stamp.

---

## Failure classes

Returned on red paths (`failure_class` + `next_action`). Do not invent new ones in app code.

**MVP:** `wrong_port_hub_vs_public`, `auth_failed`, `scope_not_enabled`, `collection_not_registered`, `empty_tool_catalog`, `contract_required`, `hash_drift`, `llm_key_missing`, `network_timeout`, `dispatch_failed`.

**0.6:** `invalid_req_id`, `v1_session_removed`, `pipeline_not_on_direct`, `where_not_in_mini_schema`, `fts_key_used_as_node_id`, `composite_req_id`, `contract_hash_invent_forbidden`.

**ZDM-4 (beer Direct lab):** `session_force_closed`, `empty_find_get`, `fts_doc_key_only`.

`diagnose_error` also maps well-known client ErrorCode strings (`030005`, `060010`, `060004`, `050010`, …) without importing the SDK on the default extra.

---

## Not this MCP

| Use Helper | Do not use Helper for |
| --- | --- |
| First green path (`demo_travel_sample` preferred), templates, readiness, smoke, lint, handoffs | Data-plane Explore/Verify tools |
| Copy a **stamped** hash | Inventing or computing `contract_hash` |
| Detective **URL templates** | Hub scrape, Hub admin mutations, enable-wizard |
| Multi / data-plane **guidance** | ZJA job runtime |
| — | Integrating Zeus into an arbitrary existing app (out of scope) |
| — | Scaffolding non-python client SDKs (golang/node) until Helper supports them |

---

## Related

| Doc | Use |
| --- | --- |
| [For AI agents](https://docs.koten.ai/zeus-client/for-ai-agents) | Agent load order (published) |
| [Using Zeus Client](https://docs.koten.ai/zeus-client/using-zeus-client) | Client / Runtime wiring |
| [Dev Helper MCP](https://docs.koten.ai/zeus-client/dev-helper-mcp) | Published Helper page |
| [zeus_chat_request](https://github.com/koten-ai/zeus_chat_request) | Min catalog templates |
