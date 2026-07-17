# Changelog

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
