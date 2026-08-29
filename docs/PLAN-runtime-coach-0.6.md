# Plan: Helper MCP 0.6 — Runtime coach (Zeus 0.7.x + Client 2.3)

**Product:** `zeus_dev_helper_mcp` (current **0.5.0**, DESIGN.md frozen as ZDH-2 MVP)  
**Target stack:** Zeus engine **0.7.29** (`main.go` `Version`) + `kotenai-zeus-client` **≥ 2.3.0** (`ZeusRuntime`)  
**Promise (unchanged):** first green middle-man turn — `session_id` / `req_id` — on public **`:8080`**.  
**Not this MCP:** data-plane verbs as tools, Hub mutations, ZJA jobs, invented `contract_hash`.

**Status:** Wave 0 + Wave 1 (PR 2, 3, 5, 6, 8 + glue) implemented as **0.6.0**. Waves 2–3 not started. Cancelled: PR 1 / [ZDH-17](https://kotenai.atlassian.net/browse/ZDH-17) (V1 scaffold/smoke rewrite); PR 4 / [ZDH-20](https://kotenai.atlassian.net/browse/ZDH-20) (v2 bootstrap probe).  
**Date:** 2026-08-26  
**Board:** [ZDH](https://kotenai.atlassian.net/jira/software/projects/ZDH/boards/45)  
**Parent epic:** [ZDH-1](https://kotenai.atlassian.net/browse/ZDH-1)  
**MVP design (frozen):** [`DESIGN.md`](DESIGN.md) (ZDH-2)

This file is the product plan for the 0.6 runtime-coach train (high-value additions + suggested next slice). Jira ticket map is at the bottom.

---

## Context

The MVP helper still coaches a **V1 client API** that 2.3.0 no longer exports on `import zeus_client`:

| Helper today | Current client / engine |
| --- | --- |
| `from zeus_client import ZeusClient, run_agent, sync_chat_requests` | Default is `ZeusRuntime`; V1 lives only as `zeus_client.compat.v1` |
| Scaffold `main.py` + `smoke_test_agent` use the V1 tuple | `await rt.agent.run_turn(...)` → `TurnResult` (`answer`, `debug`, `session`) |
| `GET /v1/ai/bootstrap/scope/...` | Public API doc prefers **`/v2/ai/bootstrap/...`** (v1 dual still exists) |
| `diagnose_error` keyword matcher | Client `ErrorCode` enum + Zeus `400 invalid_req_id` (composite hop ids) |
| `kotenai-zeus-client>=1.0.0` extra | Need **≥ 2.3.0**; `from_config` does **not** auto-wire Zeus HTTP / LLM ports |

Coding agents implementing Zeus will keep copying last month’s `run_agent` snippets unless the helper’s **glossary, diagnose, and surface router** move. **Out of this train:** rewriting V1 scaffold/smoke ([ZDH-17](https://kotenai.atlassian.net/browse/ZDH-17) Cancelled); switching bootstrap probes to `/v2` ([ZDH-20](https://kotenai.atlassian.net/browse/ZDH-20) Cancelled).

`docs/DESIGN.md` stays the frozen MVP record. This train is a **new increment** (`docs/DESIGN-0.6.md` + CHANGELOG 0.6.0), not an in-place rewrite of ZDH-2.

---

## Recommended approach

Keep FastMCP stdio, checklist phases 0–7, and the coach loop. Add **small modules** next to existing ones (`surface.py`, `verbs.py`, `compat.py`, `contract.py`, `config_lint.py`). Do not expose Zeus `find`/`search`/`get` as MCP tools.

**Hard rules (carry forward):**

- Public API **`:8080`** only from the app path.
- Never invent production `contract_hash`; templates always **TEMPLATE ONLY**.
- No secrets in tool results or checklist evidence.
- Prefer live Zeus stamp; `zeus_chat_request` is min templates only.
- Handoffs after 5.1+5.2 remain handoffs.

**Client wiring truth (guidance only — not a scaffold rewrite in this train):** `ZeusRuntime.from_config()` loads config and may set `catalog_remote`; apps still must assign `rt.services.zeus = HttpxZeusPort(...)` and `rt.services.llm = OpenAICompatibleLlmClient(...)` (see `zeus_client_python/examples/minimal_agent.py`).

---

## Suggested next slice (implement first)

Ship **0.6.0** coach tools that match Zeus 0.7 + client 2.3 **without** rewriting V1 `scaffold_app` / `smoke_test_agent` ([ZDH-17](https://kotenai.atlassian.net/browse/ZDH-17) Cancelled) and **without** switching bootstrap to `/v2` ([ZDH-20](https://kotenai.atlassian.net/browse/ZDH-20) Cancelled). Wave 0 is PR 2 ∥ PR 3.

### PR 2 — Surface router + verb / MINI-SCHEMA lint

**Why:** Agents call `run_agent` per keystroke, put `pipeline` on Direct, and pass `$gt` / unknown `where` keys to `find`.

**New tools (pure + optional live schema):**

| Tool | Inputs | Output |
| --- | --- | --- |
| `recommend_surface` | `intent` (nl_question / typeahead / single_verb / multi_step), optional `qps`, `needs_llm` | surface (`rt.agent.run_turn` / `rt.data.search` / `rt.data.verb` / agent-for-pipeline), Trace-Class, **do-not** list |
| `explain_verb` | `name` | path class (bare / scope / collection), HTTP path, demux (`find.return`), siblings, “not on Direct” for `pipeline` |
| `lint_verb_args` | `verb`, `body` JSON, optional `mini_schema` fields | issues (`where` not equality, key not in schema, FTS `biz:` key used as node id, pipeline on Direct) |
| `suggest_verb_call` | `goal`, optional live `mini_schema` | draft **legal** JSON body (guidance; does not POST) |

**Static table** (from Zeus `docs/API/API.md` + `docs/API/V2/find.md`) in `verbs.py` — do not scrape Hub.

Optional: if `ZEUS_URL` + bucket/scope set, `lint_verb_args` / `suggest_verb_call` may call existing describe probe to fill MINI-SCHEMA field names (read-only, no doc bodies). If Zeus is down, lint with caller-supplied schema or skip schema rules.

**Files:** new `surface.py`, `verbs.py`; register in `server.py`; `tests/test_surface.py`, `tests/test_verbs.py`; `explain.py` topics: `direct`, `typeahead`, `pipeline`, `trace_class`.

**Reuse:** `smoke.py` describe URL builder, `docs_url`.

### PR 3 — Diagnose ErrorCode + 0.7 failure classes

**Why:** Keyword matching misses `invalid_req_id`, V1 session 404, pipeline-not-on-direct, invent-hash.

**Changes to `diagnose_error`:**

- New optional args: `error_code` (client six-digit or name), `error_class` (Zeus JSON), `chat_id`, `turn_id`.
- First match: explicit `error_code` / `error_class` map, then HTTP status, then needles.
- New failure classes (extend DESIGN §6; document in 0.6 design):  
  `invalid_req_id`, `v1_session_removed`, `pipeline_not_on_direct`, `where_not_in_mini_schema`, `fts_key_used_as_node_id`, `composite_req_id`, `contract_hash_invent_forbidden`.
- `next_action` + docs anchors; include Detective **URL only** when `req_id`/`chat_id` present (no Hub scrape).
- Map well-known `ErrorCode` strings (`030005`, `060010`, `060004`, `050010`…). Keep table in `diagnose.py`; do not import the client package in the default (non-`[agent]`) extra.

**Files:** `diagnose.py`, `server.py` signature, `tests/test_diagnose.py`.

**Reuse:** existing `_RULES` / `_NEXT` pattern.

### Slice-wide glue (land with PR 2 or a tiny docs PR)

- `explain` topics: `zeus_runtime`, `turn_result`, `cheap_path` (`ai_process_result=false`), `semantic_cache` (flag, default off, Zeus ≥ 0.7.6), `req_id_policy`, `trace_class`.
- README / AGENTS.md tool list: `recommend_surface` (do not claim a Runtime scaffold rewrite).
- Version **0.6.0** in `pyproject.toml` + `__init__.py`.
- `docs/DESIGN-0.6.md`: increment (promise, new tools, new failure classes, boundaries). Do not rewrite frozen `docs/DESIGN.md`; add a pointer at the top: “Post-MVP: DESIGN-0.6.md”.

**Slice verification:** `pytest -q`; diagnose tests for 409, 401, 400 `invalid_req_id`, `060010`; surface/verb unit tests; `ruff check` on touched files. Unit tests must not require a cluster. Live Zeus/LLM `smoke_test_agent` and a v2 bootstrap switch are **not** in this slice.

---

## High-value additions (full catalog)

Everything below stays in the 0.6+ train except **cancelled** items (V1-scaffold rewrite, v2 bootstrap probe). **Wave 0 = next slice.**

### 1. Version / compatibility pin — `compat_check`

**Wave 1 (PR 5)**

- Inputs: optional override URL.
- Probe `GET /version` (and `/healthz`) on `:8080`; reject `:9091`.
- If `[agent]` installed, report `zeus_client.__version__` and `client_floor` if importable without side effects.
- Static gate table (data, not invented COMPAT triple):
  - semantic cache / agent_memory: Zeus **≥ 0.7.6**
  - `invalid_req_id` reject + Trace-Class: **0.7.x**
  - V1 `/v1/session` and `/v1/tools/*`: **gone**
- Output: `{zeus_version, client_version, gates[], docs: COMPAT_0.7}` — **never** emit a fake COMPAT row.
- Reuse: `readiness.py` version probe.

### 2. Surface router — `recommend_surface` (+ Trace-Class)

**Wave 0 / PR 2** (see next slice). Later: walkthrough `TOOL_HINTS` for 3.x/6.x point here.

### 4. Catalog / contract coach

**Wave 1 (PR 6)** — still never stamps.

| Tool | Role |
| --- | --- |
| `lint_chat_request` | Path or pasted JSON. If `[agent]` present, wrap client linter; else local subset: `_format`, placeholder hashes, missing `verbs`, `TO_BE_FILLED`. Read-only. |
| `bind_contract` | Extract `contract.hash` / `_hash` via same rules as `extract_stamped_hash` **copied as a small helper** (do not compute production hashes). Refuse empty / `TO_BE_FILLED` / “compute_local for prod”. Return bind snippet for `scope_contracts` / RuntimeConfig. |
| `explain_hash_boundary` | Brief + MINI-SCHEMA **excluded from hash**; inject at call time. |
| `catalog_diff` | Live bootstrap summary vs on-disk file vs bound hash prefix (not full bodies). |

Update checklist 4.2 `recommended_tools` to `bind_contract` / `catalog_diff`.

**Do not** write stamped files with secrets; do not call Hub `POST /admin/api/contracts`.

### 5. Verb encyclopedia + pitfalls

**Wave 0 / PR 2** for `explain_verb` / `lint_verb_args` / `suggest_verb_call`.  
Wave 2: richer demux table if needed (`search` strategies, `get` vs FTS keys).

Static routing to encode:

- Bare: `explain`, `return` → `POST /v2/{verb}`
- Scope: `describe`, `analyze` → `POST /v2/{bucket}/{scope}/{verb}`
- Collection: `get`, `find`, `search`, `traverse`, `set`, `order`, `enrich`, `project` (+ `pipeline` **rejected on Direct**)
- Named query: `POST /v2/{bucket}/{scope}/named_queries/{name}/execute`

`find` pitfalls from engine docs: `return` is the router; `where` equality-only; MINI-SCHEMA authoritative.

### 6. Error taxonomy

**Wave 0 / PR 3.** Wave 1: `compat_check` can attach “this Zeus version lacks X” as a gate, not a diagnose class.

### 7. Correlation / debug gather

**Wave 2 (PR 7):**

- `explain_req_id_policy` — one UUID per hop; never `base:1`; group with chat/turn; never Rewind `/v2/session/{id}/turn`.
- `support_pack_from_turn` — accept a **redacted** debug JSON (or last smoke artifact under state dir). Return markdown support pack + Detective links. No Hub fetch, no journal dump of bodies.
- `detective_links(req_id|chat_id)` — URL templates only (`/hub/debug/req/<id>`, `/hub/debug?chat_id=`).

State-dir artifact from `smoke_test_agent` (ids only + hop names + statuses) is OK; **no** tool bodies, tokens, or prompts.

### 8. Config linter + anti-examples

**Wave 1 (PR 8)**

- `lint_runtime_config` — path to `config.json`: `:8080` vs `:9091`; `auth_mode`; env **names** not values; `target` triple; `ai_process_result` default false; semantic_cache default false; no secret-looking strings in output (redact).
- `lint_app_code` or `anti_example` — path to `main.py`: import-before-env, `asyncio.run` per request smell (heuristic), `run_agent` / `ZeusClient` (stale), `contract_hash` literals, `localhost:8080` inside Dockerfiles.

Reuse: `validate_env` issues[] shape.

### 9. Live MINI-SCHEMA / `describe_scope`

**Wave 2 (PR 9)**

- Tool `describe_scope` (or extend `smoke_test_zeus` with `detail=schema`).
- `POST /v2/{bucket}/{scope}/describe` — return **entity types + field names only**, cap size, no document samples.
- Feeds `lint_verb_args` / `suggest_verb_call`.
- Reuse smoke describe probe.

### 10. Motions → mode → verbs

**Wave 2 (PR 10)** — guidance only.

- `recommend_motion(user_job)` from Zeus motions table (Funnel / Explore / Verify / …).
- Returns motion, typical verbs, modes that usually support it, link to `docs/public/motions/`.
- Does **not** generate a custom `chat_request`.
- `explain("motion")` already exists; expand to the 13 motions + vs `mode`.

### 11. Policy / hooks recipes

**Wave 3 (PR 11)**

- `explain` + `suggest_hooks` returning **snippets** (tenant pin, deny pipeline on Direct, `output_schema` allowlist, never promote OCR to system).
- Not a policy engine; not `before_zeus_dispatch` execution.
- Checklist 6.1 / 7.1 `recommended_tools`.

### 12. Semantic cache coach

**Wave 3 (PR 12)**

- Expand `explain("semantic_cache")`.
- Optional probe `GET /v2/agent_memory/status` when URL set; if 404, “engine too old or flag off”.
- Scaffolds **leave `enabled=false`**. Never enable in `start_project`.
- Direct/typeahead must not call agent_memory (already in `recommend_surface` do-not).

---

## PR Plan (DAG)

| PR | Title | Depends on | Wave |
| --- | --- | --- | --- |
| ~~PR 1~~ | ~~ZeusRuntime scaffold + `smoke_test_agent`~~ — **Cancelled** ([ZDH-17](https://kotenai.atlassian.net/browse/ZDH-17)) | — | — |
| **PR 2** | `recommend_surface` + verb lint/explain | None | 0 |
| **PR 3** | `diagnose_error` ErrorCode + 0.7 classes | None | 0 |
| ~~PR 4~~ | ~~Bootstrap/auth/chat_request prefer `/v2` with v1 fallback~~ — **Cancelled** ([ZDH-20](https://kotenai.atlassian.net/browse/ZDH-20)) | — | — |
| **PR 5** | `compat_check` | None (uses existing `/version` probe) | 1 |
| **PR 6** | `lint_chat_request` / `bind_contract` / `catalog_diff` / hash-boundary | None | 1 |
| **PR 7** | Req-id policy + support pack + Detective links | PR 3 | 2 |
| **PR 8** | `lint_runtime_config` + anti-example scan | None | 1 |
| **PR 9** | `describe_scope` schema-only | None | 2 |
| **PR 10** | `recommend_motion` | PR 2 | 2 |
| **PR 11** | Hooks/policy recipes | None | 3 |
| **PR 12** | Semantic cache explain + status probe | PR 5 | 3 |

**Max parallelism in slice 0:** PR 2 ∥ PR 3.

---

## Critical files

| Path | Role |
| --- | --- |
| `src/zeus_dev_helper_mcp/server.py` | Register tools; FastMCP instructions |
| `src/zeus_dev_helper_mcp/readiness.py` | healthz/readyz/version (existing v1 auth mint stays) |
| `src/zeus_dev_helper_mcp/diagnose.py` | Keyword failure classes |
| `src/zeus_dev_helper_mcp/explain.py` | Glossary `TOPICS` |
| `src/zeus_dev_helper_mcp/checklist.py` | Phase items + `_hint_for` |
| `src/zeus_dev_helper_mcp/walkthrough.py` | `TOOL_HINTS` |
| `src/zeus_dev_helper_mcp/config.py` | Env + public_view |
| `pyproject.toml` | 0.5.0 → 0.6.0 |
| `docs/DESIGN.md` | Frozen MVP — pointer only |
| `docs/DESIGN-0.6.md` | **New** increment (create) |
| `README.md`, `AGENTS.md`, `CHANGELOG.md` | Tool list / day-one path |
| `tests/test_diagnose.py` | 409 / 401 / port |

**New modules (wave 0–1):** `surface.py`, `verbs.py`; later `compat.py`, `contract.py`, `config_lint.py`, `motion.py`.

---

## Reuse (do not reinvent)

- `HelperConfig` / `reload_config` / `public_view` — never log secrets.
- `run_readiness_check` gates + `failure_class`.
- `CatalogError` + `STAMP_WARNING` in `catalog.py`.
- `docs_url()` for all deep-links.
- `set_item_status` + `record_metric` on smoke green.
- `httpx.Client` timeouts already used in bootstrap/smoke/readiness.
- Client **example** wiring (`HttpxZeusPort`, `OpenAICompatibleLlmClient`, `FsCatalogStore`) — cite in `explain` / recipes; do **not** rewrite generated `main.py` in this train.
- Hash extract: copy the “stamped field only” rule; optional thin wrapper if `[agent]` is installed (`extract_stamped_hash`) — never `compute_contract_hash` for production bind.

---

## Key decisions

1. **Do not rewrite V1 `scaffold_app` / `smoke_test_agent` in this train** ([ZDH-17](https://kotenai.atlassian.net/browse/ZDH-17) Cancelled). Coach tools still describe `ZeusRuntime`.
2. **Do not switch bootstrap/auth/catalog probes to `/v2`** ([ZDH-20](https://kotenai.atlassian.net/browse/ZDH-20) Cancelled). Existing `/v1` probes stay.
3. **Verb tools are coaches** (explain/lint/draft). Executing `find`/`search` is data-plane — out of scope.
4. **Diagnose does not depend on `[agent]`** — tables of codes, not an SDK import on the default extra.
5. **DESIGN.md remains frozen**; 0.6 lives in `docs/DESIGN-0.6.md`.
6. **Semantic cache stays off** in guidance and later scaffolds; coach-only in wave 3.
7. **Support packs are ids + hop metadata**, never tool bodies or prompts.

---

## Out of scope (all waves)

- Data-plane MCP tools (`rt.data.find` as an MCP tool).
- Hub enable-wizard, entity-map writes, `POST /admin/api/contracts`.
- Computing or minting production `contract_hash`.
- ZJA / `RunJob` runtime; `handoff_to_multi` stays a gate.
- Engine-contributor MCP (admin JS syntax, metrics lint, `5TH` train).
- Teaching `import zeus_client_v2` as the default.
- Scraping Detective / Rewind payloads.
- Rewriting V1 `scaffold_app` / `smoke_test_agent` to `ZeusRuntime` ([ZDH-17](https://kotenai.atlassian.net/browse/ZDH-17) Cancelled).
- Switching bootstrap/auth/catalog probes to `/v2` with v1 fallback ([ZDH-20](https://kotenai.atlassian.net/browse/ZDH-20) Cancelled).

---

## Verification

**Unit (every PR):** `pytest -q` from repo root; no live Zeus required.

| Area | Assert |
| --- | --- |
| Diagnose | 409 → `hash_drift`; `invalid_req_id` / `base:1` → new class; `060010` → `pipeline_not_on_direct` |
| Surface | typeahead → `rt.data.search` + `direct.interactive`; multi_step → not Direct pipeline |
| Verb lint | `find` + `where.abv.$gt` fails; unknown field fails when schema provided |
| Secrets | no password/token in JSON fixtures or tool return fixtures |

**Manual (slice exit):** against a lab Zeus 0.7.x: `doctor` → `readiness_check` → `recommend_surface` / `explain_verb`. Confirm probes never hit `:9091`. Do **not** require a rewritten `smoke_test_agent` or a `/v2` bootstrap switch for Wave 0.

**Lint:** `ruff check` on `src/` `tests/` touched files.

---

## Jira tickets (ZDH)

Created 2026-08-26 on project **ZDH**. Board: [ZDH](https://kotenai.atlassian.net/jira/software/projects/ZDH/boards/45).  
New epic **[ZDH-15](https://kotenai.atlassian.net/browse/ZDH-15)** (Relates to [ZDH-1](https://kotenai.atlassian.net/browse/ZDH-1); next-gen does not nest epic-under-epic).  
Labels: `helper-mcp`, `v0-6`, `runtime-coach`.  
ZDH’s team-managed workflow has no **Cancelled** column (only To Do / In Progress / In Review / Done). Cancelled stories are labelled `cancelled` and moved to **Done** as the terminal status ([ZDH-17](https://kotenai.atlassian.net/browse/ZDH-17), [ZDH-20](https://kotenai.atlassian.net/browse/ZDH-20)).

| # | Key | Type | Summary | Wave | PR | Parent |
| --- | --- | --- | --- | --- | --- | --- |
| A | [ZDH-15](https://kotenai.atlassian.net/browse/ZDH-15) | Epic | Helper MCP 0.6 — ZeusRuntime coach (Zeus 0.7 + client 2.3) | — | this plan | Relates ZDH-1 |
| B | [ZDH-16](https://kotenai.atlassian.net/browse/ZDH-16) | Story | 0.6 plan on disk (`docs/PLAN-runtime-coach-0.6.md`; later `DESIGN-0.6.md` with Wave 0) | 0 | docs only | ZDH-15 |
| C | [ZDH-17](https://kotenai.atlassian.net/browse/ZDH-17) | Story | ZeusRuntime scaffold + `smoke_test_agent` (no V1 fallback) | — | ~~1~~ | **Cancelled** |
| D | [ZDH-18](https://kotenai.atlassian.net/browse/ZDH-18) | Story | `recommend_surface` + V2 verb lint/explain | 0 | 2 | ZDH-15 |
| E | [ZDH-19](https://kotenai.atlassian.net/browse/ZDH-19) | Story | `diagnose_error` ErrorCode + 0.7 failure classes | 0 | 3 | ZDH-15 |
| F | [ZDH-20](https://kotenai.atlassian.net/browse/ZDH-20) | Story | Bootstrap/auth/catalog probes prefer `/v2` | — | ~~4~~ | **Cancelled** |
| G | [ZDH-21](https://kotenai.atlassian.net/browse/ZDH-21) | Story | `compat_check` version/feature gates | 1 | 5 | ZDH-15 |
| H | [ZDH-22](https://kotenai.atlassian.net/browse/ZDH-22) | Story | Catalog lint / bind / diff / hash-boundary | 1 | 6 | ZDH-15 |
| I | [ZDH-23](https://kotenai.atlassian.net/browse/ZDH-23) | Story | Req-id policy + support pack + Detective links | 2 | 7 | ZDH-15 |
| J | [ZDH-24](https://kotenai.atlassian.net/browse/ZDH-24) | Story | `lint_runtime_config` + anti-example scan | 1 | 8 | ZDH-15 |
| K | [ZDH-25](https://kotenai.atlassian.net/browse/ZDH-25) | Story | `describe_scope` schema-only | 2 | 9 | ZDH-15 |
| L | [ZDH-26](https://kotenai.atlassian.net/browse/ZDH-26) | Story | `recommend_motion` | 2 | 10 | ZDH-15 |
| M | [ZDH-27](https://kotenai.atlassian.net/browse/ZDH-27) | Story | Hooks/policy recipe snippets | 3 | 11 | ZDH-15 |
| N | [ZDH-28](https://kotenai.atlassian.net/browse/ZDH-28) | Story | Semantic cache coach (default off) | 3 | 12 | ZDH-15 |

**Blocks links (after ZDH-17 and ZDH-20 Cancelled):** ZDH-19 blocks ZDH-23. ZDH-18 blocks ZDH-26. ZDH-21 blocks ZDH-28. Former ZDH-17 and ZDH-20 “blocks” links are removed so cancelled work does not stall the train.

**Epic description:** Coach first-green on Zeus 0.7.x + kotenai-zeus-client ≥ 2.3.0 (`ZeusRuntime`). Plan: `docs/PLAN-runtime-coach-0.6.md`. Not: data-plane verbs, Hub mutations, ZJA, invented `contract_hash`.

**B AC:** `docs/PLAN-runtime-coach-0.6.md` committed; frozen `DESIGN.md` not rewritten in this docs-only step.

**C:** **Cancelled** — V1 scaffold/smoke rewrite removed from the 0.6 plan.

**D AC:** typeahead → `rt.data.search` + `direct.interactive`; multi_step does not recommend Direct `pipeline`; `explain_verb(find)` documents `return` demux; lint rejects `$gt`; `suggest_verb_call` does not POST.

**E AC:** existing 409/401/:9091; `invalid_req_id` / `base:1`; `060010` → `pipeline_not_on_direct`; default extra does not import `zeus_client`; Detective URLs only.

**F:** **Cancelled** — v2 bootstrap/auth/catalog probe switch removed from the 0.6 plan.

G–N AC = verification in the corresponding PR section above.

---

## Open questions (defaults if unapproved)

1. **Jira issue type** — Story if the ZDH project has it, else Task. Epic A is always Epic.
2. **`compat_check` live client_floor** — version string only if import is cheap; skip floor if it pulls adapters.
3. **Travel sample** — leave `travel_golden_path` on sample layout; do **not** rewrite demo_travel_sample.

**Defaults for this docs-only landing:** persist this file; ZDH tickets exist; do not start remaining PRs until asked. Cancelled: PR 1 / ZDH-17, PR 4 / ZDH-20.
