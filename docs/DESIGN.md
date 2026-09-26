# Developer Helper MCP — product design (ZDH-2)

**Post-MVP:** [`DESIGN-0.6.md`](DESIGN-0.6.md) (runtime coach) · [`DESIGN-0.7.md`](DESIGN-0.7.md) (MCP quality). This file remains the frozen MVP record (ZDH-2).  
**Live tool catalog:** [`TOOLS.md`](TOOLS.md) — when / args / side effects / do-not. Default surface is `core` (0.7). §4 below is the frozen MVP table.

**Status:** Implemented (MVP 0.4.x+) — design frozen post-implementation for the board.  
**Epic:** [ZDH-1](https://kotenai.atlassian.net/browse/ZDH-1)  
**Repo:** https://github.com/koten-ai/zeus_dev_helper_mcp  
**Published docs:** https://docs.koten.ai/zeus-client (live Zeus Client hub; site is public)

---

## 1. Product promise

Help a developer **and** their coding agent get a **first Zeus-powered application green**:

```text
scaffold/configure → platform ready → bind catalog/contract
  → one real agent turn with Zeus tool use → session_id / req_id
```

**Not:** data-plane MCP, Hub enable-wizard, multi-agent job runtime (ZJA).

---

## 2. Architecture

```text
Coding agent / IDE host (Claude, Grok, Hermes, OpenClaw, …)
        │  MCP stdio
        ▼
┌─────────────────────────────┐
│  zeus_dev_helper_mcp        │  coach: checklist + probes + scaffold + smoke
└───┬──────────┬──────────┬───┘
    │          │          │
    ▼          ▼          ▼
 docs.koten.ai/zeus-client  zeus_chat_request  live Zeus :8080
 (live hub)                 (min templates)    (stamp / bootstrap / describe)
```

**Stack decision:** Python 3.11+ · official `mcp` FastMCP · stdio transport.

---

## 3. Checklist model

Persisted under `~/.config/zeus_dev_helper/checklist.json` (override: `ZEUS_DEV_HELPER_STATE_DIR`).

```json
{
  "project": "single-agent:travel",
  "phases": [
    {
      "id": "0_intent",
      "title": "Intent & sample path",
      "items": [
        {"id": "0.1", "title": "…", "status": "todo|done|blocked|skipped", "evidence": "optional string"}
      ]
    }
  ]
}
```

| Field | Rules |
| --- | --- |
| `status` | `todo` \| `done` \| `blocked` \| `skipped` |
| `evidence` | No secrets / PII / full tokens |
| Phases | 0 intent → 1 prereqs → 2 platform → 3 project on disk → 4 bind → 5 green → 6 customize → 7 production-ish |

---

## 4. Tool catalog (MVP)

| Tool | Inputs (main) | Outputs | Side effects |
| --- | --- | --- | --- |
| `doctor` | — | version, config (no secrets), catalog reachability | none |
| `start_project` | goal, sample | checklist init + next_step | writes checklist |
| `get_checklist` | — | full checklist | none |
| `next_step` | — | single item + recommended_tools | none |
| `gap_report` | — | progress + open items | none |
| `mark_done` / `mark_blocked` | item_id, evidence/reason | updated checklist | writes checklist |
| `set_prereq` | url, bucket, scope, … flags | stored prereqs | writes prereqs.json (no secret values) |
| `validate_env` | — | issues[] | none |
| `readiness_check` | update_checklist | gates[] + failure_class | may update checklist 2.x and 1.2 (1.2 needs the process LLM key on `run_turn` paths) |
| `bootstrap_scope` | bucket, scope, mode, detail | bootstrap summary | may update checklist |
| `list_catalog_modes` | — | modes from zeus_chat_request | none / network |
| `fetch_chat_request` | mode, detail | template + **TEMPLATE ONLY** warning | none / network |
| `scaffold_app` | target_dir, project_name, force | files written | filesystem write |
| `use_sample` | sample | clone URL / layout check | may update checklist |
| `write_env` | target_dir | .env.example | filesystem write |
| `verify_local_setup` | target_dir | checks[] | may update checklist 3.2 when the app `.env` key check applies |
| `smoke_test_zeus` | update_checklist | describe + req_id | may update 5.1 |
| `smoke_test_agent` | question | answer preview, session_id, tool_calls | may update 5.2; needs the process LLM key (`llm_key_missing` if absent) |
| `diagnose_error` | status, body, message, … | failure_class + docs anchor | none |
| `explain` | topic | glossary short answer + docs link | none |
| `suggest_demo_prompts` | — | prompt list | none |
| `handoff_to_multi` | force | multi-agent graduation gate | none |
| `recommend_data_plane_mcp` | — | handoff guidance | none |
| `emit_mcp_config` | scope, host | MCP config fragment | none |

---

## 5. Auth & config model

| Variable | Role |
| --- | --- |
| `ZEUS_URL` | Public API (`:8080`) |
| `ZEUS_BUCKET` / `ZEUS_SCOPE` / `ZEUS_COLLECTION` | Scope binding |
| `ZEUS_USERNAME` / `ZEUS_PASSWORD` / `ZEUS_BEARER_TOKEN` | Secrets — env only |
| `LLM_API_KEY` / `XAI_API_KEY` / `OPENAI_API_KEY` | Process key for checklist 1.2 and `smoke_test_agent`. App `.env` holds the same name. `llm.api_key_env` stays the name. Stored `has_llm_key` does not count |
| `ZEUS_CHAT_REQUEST_DIR` / `GITHUB_TOKEN` | Catalog templates |
| `KOTEN_DOCS_BASE_URL` | default `https://docs.koten.ai` |
| `ZEUS_DEV_HELPER_STATE_DIR` | checklist + prereqs |

**role:** `dev` (default) vs `admin` (documented; admin mutations out of scope for v1).

---

## 6. Failure classes

Aligned with koten_docs `errors.md` / `agent-index.yaml`:

`wrong_port_hub_vs_public`, `auth_failed`, `scope_not_enabled`, `collection_not_registered`, `empty_tool_catalog`, `contract_required`, `hash_drift`, `llm_key_missing`, `network_timeout`, `dispatch_failed`.

---

## 7. Success metrics (local, privacy-safe)

Optional local metrics file under state dir (no network):

- `start_project` timestamp  
- first `smoke_test_zeus` ok  
- first `smoke_test_agent` ok  
- derived **time-to-first-green** seconds  

---

## 8. Boundaries

| Product | Role |
| --- | --- |
| **Helper MCP** | Onboarding coach |
| **Zeus Client** | Middleman library |
| **Zeus Hub** | Ops enable + Workbench stamp |
| **zeus_chat_request** | Baseline min catalogs |
| **Data Plane MCP** | Post-green governed data tools (handoff only) |
| **ZJA** | Multi-agent jobs (graduation handoff only) |

---

## 9. Day-one path

```text
start_project → set_prereq → validate_env → readiness_check
  → use_sample | scaffold_app → bootstrap_scope / fetch_chat_request
  → smoke_test_zeus → smoke_test_agent → gap_report
  → (optional) recommend_data_plane_mcp | handoff_to_multi
```

---

## 10. Design approval

Implementation matches this document. Comment on [ZDH-2](https://kotenai.atlassian.net/browse/ZDH-2): **design approved** (retroactive freeze for MVP).
