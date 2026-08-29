# Developer Helper MCP 0.6 — ZeusRuntime coach

**Status:** Waves 0–2 implemented (0.6.0). Wave 3 remains queued.  
**Product:** `zeus_dev_helper_mcp`  
**Parent epic:** [ZDH-15](https://kotenai.atlassian.net/browse/ZDH-15) (relates [ZDH-1](https://kotenai.atlassian.net/browse/ZDH-1))  
**Plan:** [`PLAN-runtime-coach-0.6.md`](PLAN-runtime-coach-0.6.md)  
**Frozen MVP:** [`DESIGN.md`](DESIGN.md) (ZDH-2) — not rewritten here.

Target stack: Zeus engine **0.7.x** + `kotenai-zeus-client` **≥ 2.3.0** (`ZeusRuntime`).

---

## 1. Promise (unchanged)

First green middle-man turn — `session_id` / `req_id` — on public **`:8080`**.

This increment coaches the **current** client surface (`ZeusRuntime`, `TurnResult`, Direct vs agent) without rewriting V1 `scaffold_app` / `smoke_test_agent` ([ZDH-17](https://kotenai.atlassian.net/browse/ZDH-17) Cancelled) and without switching bootstrap probes to `/v2` ([ZDH-20](https://kotenai.atlassian.net/browse/ZDH-20) Cancelled).

---

## 2. New tools (Wave 0)

| Tool | Role | Side effects |
| --- | --- | --- |
| `recommend_surface` | intent → surface + Trace-Class + do-not list | none |
| `explain_verb` | static V2 verb encyclopedia (path class, demux, Direct) | none |
| `lint_verb_args` | lint would-be JSON (`where` equality, MINI-SCHEMA keys, FTS ids, pipeline) | optional read-only `describe` |
| `suggest_verb_call` | draft **legal** JSON body | does **not** POST |
| `diagnose_error` | existing + ErrorCode / 0.7 classes | none (Detective **URLs only**) |

`explain` topics added: `zeus_runtime`, `turn_result`, `cheap_path`, `semantic_cache`, `req_id_policy`, `trace_class`, `direct`, `typeahead`, `pipeline`, `hash_boundary`.

### Wave 1 tools

| Tool | Role | Side effects |
| --- | --- | --- |
| `compat_check` | `GET /version` + `/healthz` on `:8080`; static 0.7 feature gates | none (read probes) |
| `lint_chat_request` | path or pasted JSON; `_format` / `verbs` / `TO_BE_FILLED` | none |
| `bind_contract` | extract stamped `contract.hash` only; refuse placeholders / `compute_local` | none |
| `explain_hash_boundary` | MINI-SCHEMA / brief excluded from hash; inject at call time | none |
| `catalog_diff` | live bootstrap summary vs on-disk vs bound hash **prefix** | optional live GET |
| `lint_runtime_config` | `config.json`: port, auth_mode, env names, cheap path, cache off | none (redacts secrets) |
| `lint_app_code` | `main.py` / Dockerfiles anti-examples | none |

Checklist 4.2 `recommended_tools`: `bind_contract` / `catalog_diff` / `explain_hash_boundary`.

### Wave 2 tools

| Tool | Role | Side effects |
| --- | --- | --- |
| `explain_req_id_policy` | one UUID per hop; never `base:1`; never Rewind `/v2/session/{id}/turn` | none |
| `detective_links` | `/hub/debug/req/<id>` and `/hub/debug?chat_id=` templates | none |
| `support_pack_from_turn` | redacted markdown from debug JSON or `last_smoke_agent.json` | none (reads state dir) |
| `describe_scope` | live `POST /v2/{bucket}/{scope}/describe` — types + field names only | read-only POST |
| `recommend_motion` | user job → 13 Zeus motions + typical verbs/modes | none — **no** chat_request |

`explain("motion")` lists the 13 motions vs `mode`. `smoke_test_agent` writes ids/hops (no bodies) to `last_smoke_agent.json`.

---

## 3. Surfaces

| Intent | Surface | Trace-Class |
| --- | --- | --- |
| `nl_question` | `rt.agent.run_turn` | `agent` |
| `typeahead` | `rt.data.search` | `direct.interactive` |
| `single_verb` | `rt.data.verb` | `direct.read` |
| `multi_step` | `agent-for-pipeline` | `agent` |

**Do not:** pipeline on Direct; agent_memory on Direct/typeahead; Hub `:9091` from the app path; invented `contract_hash`; composite hop ids (`base:1`).

Client wiring (guidance only): `ZeusRuntime.from_config()` loads config and may set `catalog_remote`; apps still assign `rt.services.zeus = HttpxZeusPort(...)` and `rt.services.llm = OpenAICompatibleLlmClient(...)`.

---

## 4. Verb routing (static)

From Zeus `docs/API/API.md` + `docs/API/V2/find.md`. Helper does not scrape Hub and does not expose `find`/`search`/`get` as MCP tools.

| Path class | HTTP | Verbs |
| --- | --- | --- |
| Bare | `POST /v2/{verb}` | `explain`, `return` |
| Scope | `POST /v2/{bucket}/{scope}/{verb}` | `describe`, `analyze` |
| Collection | `POST /v2/{bucket}/{scope}/{collection}/{verb}` | `get`, `find`, `search`, `traverse`, `set`, `order`, `enrich`, `project` (+ `pipeline` **rejected on Direct**) |
| Named query | `POST /v2/{bucket}/{scope}/named_queries/{name}/execute` | execute |

`find` pitfalls: `return` is the router; `where` equality-only; MINI-SCHEMA authoritative. Optional live `describe` fills **entity types + field names only** (no document samples). If Zeus is down, lint with caller schema or skip schema rules.

---

## 5. Failure classes (extend DESIGN §6)

MVP: `wrong_port_hub_vs_public`, `auth_failed`, `scope_not_enabled`, `collection_not_registered`, `empty_tool_catalog`, `contract_required`, `hash_drift`, `llm_key_missing`, `network_timeout`, `dispatch_failed`.

**0.6 additions:** `invalid_req_id`, `v1_session_removed`, `pipeline_not_on_direct`, `where_not_in_mini_schema`, `fts_key_used_as_node_id`, `composite_req_id`, `contract_hash_invent_forbidden`.

Mapped well-known client ErrorCode strings (table in `diagnose.py`, **no** `zeus_client` import on the default extra): `030005`, `060010`, `060004`, `050010`, …

Match order: explicit `error_code` / `error_class` → HTTP status → needles. Detective links only when `req_id` / `chat_id` present (`/hub/debug/req/<id>`, `/hub/debug?chat_id=`) — URL templates, no Hub scrape.

---

## 6. Boundaries (carry forward)

- Public API **`:8080`** only from the app path.
- Never invent production `contract_hash`; templates always **TEMPLATE ONLY**.
- No secrets in tool results or checklist evidence.
- Prefer live Zeus stamp; `zeus_chat_request` is min templates only.
- Handoffs after 5.1+5.2 remain handoffs.
- Semantic cache stays **off** in guidance.
- Not this MCP: data-plane verbs as tools, Hub mutations, ZJA jobs.

---

## 7. Out of this increment

- Rewriting V1 `scaffold_app` / `smoke_test_agent` to `ZeusRuntime`.
- Switching bootstrap/auth/catalog probes to `/v2`.
- Wave 3 tools (hooks recipes, semantic-cache probe).

---

## 8. Verification

Unit tests (`pytest -q`) must not require a cluster. Diagnose: 409, 401, `:9091`, 400 `invalid_req_id` / `base:1`, `060010`. Surface: typeahead → `rt.data.search` + `direct.interactive`; multi_step does not recommend Direct `pipeline`. Verb lint: `where.abv.$gt` fails; unknown field fails when schema provided; `suggest_verb_call` does not POST. Compat: `:9091` rejected; 0.7.5 lacks semantic cache; never a fake COMPAT row. Bind: placeholder hash refused; stamped hash copied only. Config lint: Hub port error; secret values redacted from output. Support pack: no prompt/body in markdown; Detective URLs only. `describe_scope`: names only. `recommend_motion("book a hotel")` → Funnel and `chat_request` is null.
