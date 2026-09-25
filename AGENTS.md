# AGENTS — Developer Helper MCP

**Mission:** Get a coding agent + human to a **first green** Zeus Client app turn.

## Load order

1. This file  
2. [docs/TOOLS.md](docs/TOOLS.md) — Helper tool catalog (when / args / side effects / do-not)  
3. [Zeus Client docs](https://docs.koten.ai/zeus-client) — **live** published human docs hub  
4. [For AI agents](https://docs.koten.ai/zeus-client/for-ai-agents) · [Using Zeus Client](https://docs.koten.ai/zeus-client/using-zeus-client) · [Start](https://docs.koten.ai/zeus-client/start) · [Errors](https://docs.koten.ai/zeus-client/errors) · [Dev Helper MCP](https://docs.koten.ai/zeus-client/dev-helper-mcp)  
5. Live Zeus public API **:8080** (readiness / stamp / smoke — never Hub **:9091** from the app path)  
6. [agent-index.yaml](https://github.com/koten-ai/koten_docs/blob/zeus-v1.0.0/agent-index.yaml) — machine map only (do **not** clone `koten_docs` or grep the Zeus engine for first green)  
7. [zeus_chat_request](https://github.com/koten-ai/zeus_chat_request) for templates  

## Hard constraints

- Public API **:8080** only (never Hub **:9091** from app path)  
- Never invent `contract_hash`  
- Catalogs: live stamp preferred; `fetch_chat_request` is **template only**  
- No secrets in tool results or checklist evidence  

## Tools to use first

Default surface (`core`): `doctor` → (if user named URL/sample) `set_prereq` → `start_project` → `next_step` → `readiness_check` → `use_sample` | `scaffold_app` → `bind_contract` → `recommend_surface` → `smoke_test_zeus` / `smoke_test_agent` → `diagnose_error`. **Default app kind is UI** (`start_project(sample=travel)` → `use_sample` clones public `demo_travel_sample` when missing, optional `project_name` for the clone dir, sets `DEMO_TRAVEL_SAMPLE_DIR`). **Beer / website:** `start_project(sample=beer)` → `use_sample(sample=beer)` writes `demo_beer_sample` catalog UI (FastAPI BFF). Search follows travel: `rt.agent.run_turn` with `chat_request` omitted so `catalog.load_for_turn` merges SCOPE BRIEF + MINI-SCHEMA into the model request. An LLM key is required for that search. The BFF does not build a pipeline body. Do not clone `demo_travel_sample` on the beer path. `rt.data.verb('pipeline')` stays rejected (060010). **Yelp demo:** `start_project(sample=demo_yelp)` → `use_sample(sample=demo_yelp)` clones [demo_yelp](https://github.com/koten-ai/demo_yelp) when missing (aliases `yelp-demo` / `demo_yelp`) and sets `DEMO_YELP_SAMPLE_DIR`. Do not clone `demo_travel_sample` on that path. Bare `sample=yelp` stays the multi-agent handoff. **API-only** when the user asks for API/REST: `start_project(sample=api)` → `scaffold_app(app_kind=api, coding_language=python)` (FastAPI). Credentials → env + `set_prereq` presence flags only. `doctor(detail=env|compat|cache)` covers checks that also live on the lint toolset. Wiring Zeus into an arbitrary existing repo is **out of scope**.

Knowledge is resources: `zeus-helper://checklist`, `zeus-helper://glossary/{topic}`, `zeus-helper://verbs/{name}`, `zeus-helper://policy/hash-boundary`, `zeus-helper://policy/req-id`, `zeus-helper://catalog/modes`. Prompts: `first_green`, `smoke_question`, `support_pack`.

`scaffold_app` / `smoke_test_agent` emit **ZeusRuntime** + `rt.agent.run_turn` (not V1 `ZeusClient` / `run_agent`). Semantic cache stays **off**.

Opt-in toolsets (`ZEUS_DEV_HELPER_TOOLSETS=core,lint,catalog` or `all`): catalog / lint / travel / support / handoff. Travel sample: `use_sample` (core) / `travel_golden_path` (travel toolset; set `DEMO_TRAVEL_SAMPLE_DIR` if cloned).

After 5.1+5.2 green: `recommend_data_plane_mcp`, `emit_mcp_config`, `handoff_to_multi` — **handoffs only** (handoff toolset).

Design freeze: `docs/DESIGN.md`. 0.7 increment: `docs/DESIGN-0.7.md`. Tool catalog: `docs/TOOLS.md`.

## Not this MCP

Data-plane tools, Hub admin mutations, multi-agent jobs (ZJA). Integrating Zeus into an arbitrary existing application (use `demo_travel_sample` / `use_sample(sample=beer)` / `use_sample(sample=demo_yelp)` / `use_sample` instead).
