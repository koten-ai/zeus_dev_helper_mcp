# Changelog

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
