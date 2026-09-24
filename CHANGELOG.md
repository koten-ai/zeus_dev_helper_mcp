# Changelog

## Unreleased

### Added
- **[ZDM-11](https://kotenai.atlassian.net/browse/ZDM-11)** Helper MCP tool failures write one stderr line, `zeus_dev_helper.tool.failed`, in the Zeus Client family text shape. `source.file` is package-relative (`zeus_dev_helper_mcp/<module>.py`) and the line omits `error.code`. stdout stays the MCP JSON-RPC stream. Domain `ok: false` results (lint, diagnose, blocked handoff) are not logged as errors.

### Changed
- Beer catalog search follows `demo_travel_sample`: `use_sample(sample=beer)` writes a BFF that calls `rt.agent.run_turn` and omits `chat_request`, so `catalog.load_for_turn` merges the live SCOPE BRIEF and MINI-SCHEMA into the model request. An LLM key is required. The BFF does not build a pipeline body. Cards are taken from the turn's tool results.

## 0.7.4

### Changed
- **[ZDM-8](https://kotenai.atlassian.net/browse/ZDM-8)** Host install docs no longer pin `localhost:8080` as the only `ZEUS_URL` example. README / `docs/HOST-MATRIX.md` lead with remote-host examples (`http://<zeus-host>:8080` / `http://192.168.0.219:8080`), note localhost only for same-machine Zeus, add Cursor `.cursor/mcp.json`, keep Grok `--` / `uvx zeus-dev-helper-mcp` gotchas, and document day-one `set_prereq` with the user’s URL plus Travel+LLM vs Direct+beer paths. `server.json` placeholder is `http://<zeus-host>:8080`. `doctor` stored-vs-effective URL note points at ZDM-3.
- **[ZDM-10](https://kotenai.atlassian.net/browse/ZDM-10)** Treat [docs.koten.ai/zeus-client](https://docs.koten.ai/zeus-client) as the live human docs hub. Removed “placeholder while wiring” from `AGENTS.md` / `docs_links.py` / DESIGN blurbs. Day-one load order prefers Helper tools + published hub + live `:8080`; `agent-index.yaml` remains a machine map only (do not clone `koten_docs` for first green). `first_green` prompt + server `INSTRUCTIONS` name the hub. `doctor` docs include `zeus_client_hub` / `dev_helper_mcp`. Optional `scripts/docs_link_smoke.py` GETs key pages (not wired into CI).
- **[ZDM-9](https://kotenai.atlassian.net/browse/ZDM-9)** Coach wording: TravelPlan / `demo_travel_sample` is the **agent-plane** (LLM + `run_turn`) example; `demo_beer_sample` is the **data-plane Direct** example. Direct websites may copy TravelPlan BFF/same-origin/config only — **do not copy `run_turn`** unless this is an agent app. Beer / website / no LLM never clones `demo_travel_sample`. Glossary topics `demo_travel_sample` / `demo_beer_sample`; `first_green`, server instructions, LIST, AGENTS, README, TOOLS.
- **[ZDM-2](https://kotenai.atlassian.net/browse/ZDM-2)** `recommend_surface(needs_llm=false)` steers to Direct / beer. `start_project` reroutes the default travel track when prereqs are beer-sample with `has_llm_key=false`. `next_step` does not push `smoke_test_agent` on that path.
- **[ZDM-5](https://kotenai.atlassian.net/browse/ZDM-5)** Application-user beer prompts: zero-vocabulary samples with expected Helper sequences. `first_green` teaches the beer website utterance.
- **[ZDM-3](https://kotenai.atlassian.net/browse/ZDM-3)** When the user named a URL or sample, coach order is `doctor` → `set_prereq` → `start_project` → `next_step`.

### Fixed
- **[ZDM-3](https://kotenai.atlassian.net/browse/ZDM-3)** Persisted `set_prereq(zeus_url/bucket/scope/…)` now **overrides** MCP host `ZEUS_*` env defaults. Stale `ZEUS_URL=http://localhost:8080` no longer shadows a lab URL for `doctor` / `readiness_check`. `set_prereq` also mirrors those fields into process env. `doctor` reports `url_routing` (`stored` / `env` / `effective`) and flags when host env differs from `set_prereq`.
- Beer Direct search no longer sends `What beers are made from fruits?` as a name lookup. That sentence is `find` `where.style="Fruit Beer"` (`return: "rows"`, page of 50). Bare `fruit`, `IPA`, and `Duvel` stay name lookups. `fruits` falls through to the style filter only after the name search misses. `Belgian and French Ale` uses `where.category`. FTS uses content tokens only (`strategy: "fts"`, `timeout_ms: 8000`). `get` uses the find row's `n_*` id.

### Added
- **[ZDM-7](https://kotenai.atlassian.net/browse/ZDM-7)** Beer Direct NL planner — `plan_beer_query` (tokenize / stopwords / `where.style` incl. Fruit Beer + Pumpkin Beer / FTS `query_text`=tokens) mirrored in the `demo_beer_sample` BFF. Golden “What beers are made from fruit?” maps to `where.style=Fruit Beer`, never `find.query=` the full sentence. Prefer `result.node_ids` / `file::` over item-local `n_*` for `get`. README + `diagnose_error(empty_find_get)` treat “0 rows on a sentence” as a bad plan, not empty Zeus.
- **[ZDM-6](https://kotenai.atlassian.net/browse/ZDM-6)** Beer Direct UI — `start_project(sample=beer)` sets track `ui-direct`; `use_sample(sample=beer)` writes `demo_beer_sample` (FastAPI same-origin BFF + static catalog page). BFF uses sequential `find` → `get` with FTS fallback, `abort_if_empty` (never `get` on empty `node_ids`), and `doc_key` cards when FTS returns no graph ids. **No `pipeline`**, **no LLM key**. Walkthrough recommends `use_sample` on 0.2/3.1 and does not push `smoke_test_agent` as primary on this track.
- **[ZDM-4](https://kotenai.atlassian.net/browse/ZDM-4)** `diagnose_error` maps beer Direct lab failures to `session_force_closed`, `empty_find_get`, and `fts_doc_key_only` (docs anchors and coach `next_action`) ahead of generic `dispatch_failed`.
- **[ZDM-1](https://kotenai.atlassian.net/browse/ZDM-1)** Design note for beer-sample first green: locked Direct path is sequential `find` → `get` (never `pipeline`).

## 0.7.3

### Changed
- **License** — project is now **BSD-3-Clause** (was proprietary). Aligns with `kotenai-zeus-client` / `demo_travel_sample`. See `LICENSE`, `pyproject.toml`, and README.

## 0.7.2

### Added
- **UI Docker standalone prep** — `use_sample` / `ensure_travel_sample` / `travel_golden_path` detect when `demo_travel_sample` Docker packaging assumes the monorepo (`context: ..`, `demo_travel_sample/Dockerfile`, sibling `zeus_client_python`) and the clone is outside that layout. Helper rewrites `Dockerfile`, `docker-compose.yml`, `pyproject.toml` (PyPI `kotenai-zeus-client>=2.3.0`), and `.dockerignore` so `docker compose up --build` works. Skips when monorepo siblings are present or packaging is already standalone. Still does **not** execute Docker.

### Notes
- Fixes the bootstrap failure `lstat .../demo_travel_sample: no such file or directory` when cloning the UI sample into a project directory (e.g. `demos/my-first-zeus-app`).

## 0.7.1

### Added
- **`use_sample` auto-clone** ([ZDH-41](https://kotenai.atlassian.net/browse/ZDH-41)–[ZDH-45](https://kotenai.atlassian.net/browse/ZDH-45)) — public `demo_travel_sample` is shallow-cloned when no local path is found; optional `project_name` sets the clone directory (default `demo_travel_sample`); sets process env + persisted `DEMO_TRAVEL_SAMPLE_DIR`.
- **`list_catalog_modes` / `fetch_chat_request` auto-clone** ([ZDH-47](https://kotenai.atlassian.net/browse/ZDH-47)) — when `ZEUS_CHAT_REQUEST_DIR` is unset, Helper locates a sibling `zeus_chat_request` checkout or shallow-clones the public repo, then sets process env + persisted `ZEUS_CHAT_REQUEST_DIR` (GitHub raw / `GITHUB_TOKEN` remain fallback).
- **API-only bootstrap** ([ZDH-46](https://kotenai.atlassian.net/browse/ZDH-46)) — `start_project(sample=api)` + `scaffold_app(app_kind=api, coding_language=python)` emits a FastAPI REST middle-man (`GET /healthz`, `POST /turn` → `ZeusRuntime.run_turn`) on `kotenai-zeus-client`. Default bootstrap remains **UI** (`sample=travel` / `use_sample` / `demo_travel_sample`). Non-python `coding_language` → `unsupported_coding_language` (golang/node not scaffolded yet).
- **[ZDH-40](https://kotenai.atlassian.net/browse/ZDH-40)** First-green eval suite (`eval_suite`): ~20 prompts from `guides/LIST_OF_PROMPT_SAMPLES.md`; trace check that `doctor` / `next_step` precede `scaffold_app`.
- **[ZDH-40](https://kotenai.atlassian.net/browse/ZDH-40)** `helper_metrics` records tool **ids** only (`tool_call` events; no payloads/tokens/prompts).
- **[ZDH-40](https://kotenai.atlassian.net/browse/ZDH-40)** `docs/HOST-MATRIX.md` — Grok / Claude / Cursor measurement notes (do not assume one host’s tool picking).
- **smoke_test_agent / travel** — When `kotenai-zeus-client` is not installed and `demo_travel_sample` has Docker install docs (`docker-compose` / `Dockerfile` / README signals), return guide-only `install_path=docker` (`docker compose up --build`) instead of only the pip/`[agent]` message. Persist `travel_sample_dir` after `use_sample` / `travel_golden_path`. No Docker execution from the Helper.

### Changed
- Travel golden-path phase 5 prefers Docker compose when Docker packaging/docs are detected; soft markers include `docker-compose.yml` / `Dockerfile`.
- `first_green` prompt + server instructions: UI default vs API track; credentials via env / presence flags only.

### Notes
- Existing-project integration into arbitrary repos is **not supported**. Helper coaches first green via **`demo_travel_sample` (UI default)** or **API/CLI scaffolds** (`scaffold_app`).

## 0.7.0

### Added
- **ZDH-29 / 0.7 MCP quality** — default `core` toolset (≤15 tools), static opt-in `catalog` / `lint` / `travel` / `support` / `handoff` via `ZEUS_DEV_HELPER_TOOLSETS` (no dynamic `enable_toolset`).
- MCP resources: `zeus-helper://checklist`, `glossary/{topic}`, `verbs/{name}`, `policy/hash-boundary`, `policy/req-id`, `catalog/modes`.
- MCP prompts: `first_green`, `smoke_question`, `support_pack`.
- Tool annotations (`readOnlyHint` / `destructiveHint` / `idempotentHint` / `openWorldHint`) on every exposed tool.
- Shared result envelope (`ok`, `failure_class`, `next_action`, `recommended_tools`, `docs`).
- Execution failures raise MCP `ToolError` (`isError: true` on mcp 2.x) for `readiness_check` / `bind_contract` / catalog fetch / scaffold / smoke.
- `docs/DESIGN-0.7.md` increment. Frozen `docs/DESIGN.md` is unchanged.
- **ZDH-35** `doctor(detail=health|env|compat|cache|all)`; `lint_app` folds config+code linters; `use_sample` includes travel golden path; Detective URLs live on `diagnose_error` / `support_pack_from_turn`. Old names stay on opt-in toolsets.
- **ZDH-39** MCP Inspector CLI smoke in CI (`scripts/inspector_smoke.py`).

### Changed
- Server `instructions` cover order + hard constraints, not a tool-name dump.
- `next_step` returns `resource_links` for checklist / glossary / policies.
- Deleted leftover `_stub()` (ZDH-36).
- `validate_env` moved off `core` (use `doctor(detail=env)` or the lint toolset).

### Notes
- Full catalog remains available with `ZEUS_DEV_HELPER_TOOLSETS=all`.

## 0.6.2

### Changed
- **ZDH-32** `scaffold_app` emits `ZeusRuntime.from_config()` + `HttpxZeusPort` + `OpenAICompatibleLlmClient` (`config.json` + `main.py`). Floor `kotenai-zeus-client>=2.3.0`.
- **ZDH-32** `smoke_test_agent` uses `rt.agent.run_turn` → `TurnResult` (ids/hops only in `last_smoke_agent.json`).
- Checklist 5.2 / tool docs no longer coach V1 `ZeusClient` / `run_agent` as the generated path. `lint_app_code` still flags leftover V1 in caller code.

## 0.6.1

### Changed
- Public README: install, host config, tools, and env only (no Jira / sibling-repo links)

## 0.6.0

### Fixed
- Server import on **mcp 2.x** (`FastMCP` renamed to `MCPServer`). Supports 1.x and 2.x; pin is now `mcp>=1.8.0,<3`.
- Grok host install: `grok mcp add` must pass `--` before `python -m` (otherwise Grok errors `unexpected argument '-m'`), and `command` must be the repo venv interpreter so the TUI can spawn the server without an activated venv.

### Added
- **ZDH-18** Surface router + V2 verb coach: `recommend_surface`, `explain_verb`, `lint_verb_args`, `suggest_verb_call`
- **ZDH-19** `diagnose_error` ErrorCode / Zeus `error_class` plus 0.7 failure classes (`invalid_req_id`, `composite_req_id`, `pipeline_not_on_direct`, …); Detective URL templates only
- `explain` topics: `zeus_runtime`, `turn_result`, `cheap_path`, `semantic_cache`, `req_id_policy`, `trace_class`, `direct`, `typeahead`, `pipeline`
- `docs/DESIGN-0.6.md` increment (frozen `docs/DESIGN.md` pointer only)
- Optional extra `[agent]` floor `kotenai-zeus-client>=2.3.0`
- **ZDH-21** `compat_check` — `/version` + `/healthz` on `:8080`; static 0.7 feature gates (not a COMPAT matrix row)
- **ZDH-22** `lint_chat_request`, `bind_contract`, `explain_hash_boundary`, `catalog_diff` — stamp extract only; never compute production hashes
- **ZDH-24** `lint_runtime_config` + `lint_app_code` — env names not values; secrets redacted; V1 / hash-literal / Dockerfile smells
- **ZDH-23** `explain_req_id_policy`, `detective_links`, `support_pack_from_turn` — URL templates + redacted ids/hops only
- **ZDH-25** `describe_scope` — entity types + field names; no document samples
- **ZDH-26** `recommend_motion` — 13 Zeus motions; does not generate a chat_request
- **ZDH-27** `suggest_hooks` — tenant pin / deny pipeline / output_schema / OCR snippets (not executed)
- **ZDH-28** `semantic_cache_status` — default off; optional `/v2/agent_memory/status` probe
- Helper tool catalog: [`docs/TOOLS.md`](docs/TOOLS.md) (when / args / side effects / do-not; not a Zeus OpenAPI dump)
- PyPI + official MCP Registry distribution: `server.json` (`io.github.koten-ai/zeus-dev-helper`), README `mcp-name` marker, tag-driven [`.github/workflows/release.yml`](.github/workflows/release.yml)

### Notes
- V1 `scaffold_app` / `smoke_test_agent` are **not** rewritten in this release ([ZDH-17](https://kotenai.atlassian.net/browse/ZDH-17) Cancelled)
- Bootstrap/auth/catalog probes stay on existing `/v1` ([ZDH-20](https://kotenai.atlassian.net/browse/ZDH-20) Cancelled)
- Verb tools never POST; they explain, lint, and draft

## 0.5.0

### Added
- **ZDH-2** Product design freeze: `docs/DESIGN.md` (tool catalog, checklist, boundaries, metrics)
- **ZDH-10** `travel_golden_path` + richer `use_sample` layout validation / README snippet for demo_travel_sample
- **ZDH-11** `handoff_to_multi` + gated `start_project(goal=multi|sample=yelp)` until single-agent smokes green
- **ZDH-12** `recommend_data_plane_mcp` + `emit_mcp_config` (scope-bound, read-only placeholder fragment)
- **ZDH-13** Expanded `explain` glossary topics (≥30) with docs deep-links + aliases
- Local privacy-safe metrics: `helper_metrics` + auto events on start/smoke green
- Post-green hints on `next_step` after 5.1 + 5.2 done

### Notes
- Data Plane MCP package is **placeholder** until published — do not invent install packages
- Multi-agent jobs remain **ZJA**; Helper only coaches graduation
- demo_travel_sample may stay private; set `DEMO_TRAVEL_SAMPLE_DIR` when cloned

## 0.4.0

### Added
- **P4** `scaffold_app`, `use_sample`, `write_env`, `verify_local_setup`
- **P3** full `bootstrap_scope` (live GET bootstrap + chat_request summary)
- **P6** `gap_report` + richer `next_step` (recommended_tools coach)
- Minimal project template: `main.py`, `requirements.txt`, `.env.example`

### Notes
- Secrets never written by scaffold/write_env
- `smoke_test_agent` still needs optional `[agent]` extra

## 0.3.0

- P5 `smoke_test_zeus`, `smoke_test_agent`, `diagnose_error`, `suggest_demo_prompts`

## 0.2.0

- P2 `set_prereq`, `readiness_check`

## 0.1.0

- P1 skeleton + P3b catalogs (`list_catalog_modes`, `fetch_chat_request`)
