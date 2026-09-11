# AGENTS — Developer Helper MCP

**Mission:** Get a coding agent + human to a **first green** Zeus Client app turn.

## Load order

1. This file  
2. [docs/TOOLS.md](docs/TOOLS.md) — Helper tool catalog (when / args / side effects / do-not)  
3. [docs.koten.ai](https://docs.koten.ai/) (published docs; site may be placeholder while wiring)  
4. [agent-index.yaml](https://github.com/koten-ai/koten_docs/blob/zeus-v1.0.0/agent-index.yaml) (machine index in source repo)  
5. [For AI agents](https://docs.koten.ai/zeus-client/for-ai-agents)  
6. [Using Zeus Client](https://docs.koten.ai/zeus-client/using-zeus-client)  
7. [zeus_chat_request](https://github.com/koten-ai/zeus_chat_request) for templates  

## Hard constraints

- Public API **:8080** only (never Hub **:9091** from app path)  
- Never invent `contract_hash`  
- Catalogs: live stamp preferred; `fetch_chat_request` is **template only**  
- No secrets in tool results or checklist evidence  

## Tools to use first

Default surface (`core`): `doctor` → `start_project` → `next_step` → `set_prereq` / `readiness_check` → `use_sample` | `scaffold_app` → `bind_contract` → `recommend_surface` → `smoke_test_zeus` / `smoke_test_agent` → `diagnose_error`. `doctor(detail=env|compat|cache)` covers checks that also live on the lint toolset.

Knowledge is resources: `zeus-helper://checklist`, `zeus-helper://glossary/{topic}`, `zeus-helper://verbs/{name}`, `zeus-helper://policy/hash-boundary`, `zeus-helper://policy/req-id`, `zeus-helper://catalog/modes`. Prompts: `first_green`, `smoke_question`, `support_pack`.

`scaffold_app` / `smoke_test_agent` emit **ZeusRuntime** + `rt.agent.run_turn` (not V1 `ZeusClient` / `run_agent`). Semantic cache stays **off**.

Opt-in toolsets (`ZEUS_DEV_HELPER_TOOLSETS=core,lint,catalog` or `all`): catalog / lint / travel / support / handoff. Travel sample: `use_sample` (core) / `travel_golden_path` (travel toolset; set `DEMO_TRAVEL_SAMPLE_DIR` if cloned).

After 5.1+5.2 green: `recommend_data_plane_mcp`, `emit_mcp_config`, `handoff_to_multi` — **handoffs only** (handoff toolset).

Design freeze: `docs/DESIGN.md`. 0.7 increment: `docs/DESIGN-0.7.md`. Tool catalog: `docs/TOOLS.md`.

## Not this MCP

Data-plane tools, Hub admin mutations, multi-agent jobs (ZJA).
