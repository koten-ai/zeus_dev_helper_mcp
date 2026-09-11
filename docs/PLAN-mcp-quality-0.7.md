# Plan: Helper MCP 0.7 — MCP server quality (then Runtime first-green)

**Product:** `zeus_dev_helper_mcp` (current **0.7.0**)  
**Promise (unchanged):** first green middle-man turn — `session_id` / `req_id` — on public **`:8080`**.  
**Not this MCP:** data-plane verbs as tools, Hub mutations, ZJA jobs, invented `contract_hash`.

**Status:** 0.7 MCP quality implemented (ZDH-29). Name-folding (ZDH-35) and Inspector-in-CI remain follow-up. Epic: [ZDH-29](https://kotenai.atlassian.net/browse/ZDH-29).  
**Date:** 2026-09-04  
**Board:** [ZDH](https://kotenai.atlassian.net/jira/software/projects/ZDH/boards/45)  
**Parent:** [ZDH-15](https://kotenai.atlassian.net/browse/ZDH-15) (0.6, still In Progress at time of writing) relates [ZDH-1](https://kotenai.atlassian.net/browse/ZDH-1)  
**Frozen MVP:** [`DESIGN.md`](DESIGN.md) (ZDH-2) — not rewritten here.  
**0.6 increment:** [`DESIGN-0.6.md`](DESIGN-0.6.md) · [`PLAN-runtime-coach-0.6.md`](PLAN-runtime-coach-0.6.md)

This file is the recommended path **after** the 0.6 coach catalog. It follows MCP server best practices rather than adding more Zeus-domain tools.

---

## Thesis

The best next move is **not more Zeus-domain tools**. 0.6 already covers the coach job. The gap is that this server is still a **45-tool encyclopedia**, not an MCP interface an agent can use well.

Ship **0.6 as frozen**, then treat **0.7 as MCP-server quality**, then **reopen the Runtime scaffold** that 0.6 deferred ([ZDH-17](https://kotenai.atlassian.net/browse/ZDH-17) Cancelled). Adding another wave of `explain_*` / lint / probe tools would make first-green worse, not better.

---

## Current state (2026-09-04)

### Code

Version **0.6.0**. Waves 0–3 from [`PLAN-runtime-coach-0.6.md`](PLAN-runtime-coach-0.6.md) are implemented on `feat/runtime-coach-0.6`. Stack: Python 3.11+ · official `mcp` FastMCP / MCPServer · stdio.

### Jira

| Range | Status |
| --- | --- |
| ZDH-1 … ZDH-14 | Done (MVP) |
| [ZDH-15](https://kotenai.atlassian.net/browse/ZDH-15) | **In Progress** (0.6 epic) |
| [ZDH-17](https://kotenai.atlassian.net/browse/ZDH-17) / [ZDH-20](https://kotenai.atlassian.net/browse/ZDH-20) | Cancelled (Runtime scaffold; `/v2` bootstrap) |
| ZDH-18 … ZDH-28 | **In Review** (code in repo; tickets not closed) |

Until Jira matches the repo, a 0.7 epic will fork on unfinished review.

### What is already good (keep)

- One bounded context: coach, not data-plane, not Hub, not ZJA.
- Outcome loop: `next_step` + checklist + `failure_class` / `next_action`.
- Server `instructions` exist on the FastMCP constructor.
- Secrets never in tool results or checklist evidence.
- Live stamp preferred; `fetch_chat_request` is **TEMPLATE ONLY**.
- Unit tests that do not need a cluster.

### Gaps vs MCP server best practice

| Gap | Evidence |
| --- | --- |
| Too many tools | **45** `@mcp.tool()` handlers in `server.py`. Industry sweet spot is ~8–15; large lists degrade tool choice and burn context. |
| Wrong primitive | Glossary (`explain`, `explain_verb`, `explain_hash_boundary`, `explain_req_id_policy`), checklist dump, catalog modes, and demo prompts are **tools**. Those belong as **resources** and **prompts**. |
| No annotations | No `readOnlyHint` / `destructiveHint` / `idempotentHint` / `openWorldHint`. Hosts cannot tell `doctor` from `scaffold_app(force=true)`. |
| No output schemas | Tools return free-form dicts. Spec wants `outputSchema` + `structuredContent`. |
| Soft errors | Failures are `{"error": ...}` JSON. Spec wants `isError: true` so the model can self-correct. |
| Tools fight each other | **Resolved (0.6.2):** `scaffold_app` / `smoke_test_agent` emit `ZeusRuntime` + `run_turn`; `lint_app_code` still flags leftover V1 in *user* code. |
| No protocol tests | `tests/test_server_import.py` only checks the module imports. No Inspector / `tools/list` / annotation / resource tests. |
| Dead code | `_stub()` in `server.py` is leftover from the MVP skeleton. |

The remaining product hole after the Runtime scaffold patch is MCP interface quality (tool count, annotations, resources), not first-green generation.

---

## What “best practice MCP” means here

MCP is a UI for agents, not a REST dump. Practices that apply to this server:

1. **Outcomes, not operations.** One call should move the checklist. `next_step` is already the right shape; `get_checklist` + `gap_report` + three `explain_*` tools are the wrong shape.
2. **Curate the default surface.** 5–15 tools on the hot path. Extra capability behind **static toolsets** or resources, not in every `tools/list`.
3. **Use all three primitives.** Tools = side effects. Resources = read-only knowledge. Prompts = the day-one walkthrough already written in `guides/LIST_OF_PROMPT_SAMPLES.md`.
4. **Descriptions are the contract.** When to use, when not to, what comes back. Server `instructions` cover **workflows across tools**, not a second catalog.
5. **Annotations + typed I/O.** Hosts need read-only vs write vs open-world (live Zeus `:8080`).
6. **Errors the model can act on.** `isError` + `failure_class` + `next_action` + recommended tool. Helper already has the last three; wire the first.
7. **Stay one job.** Data-plane verbs stay a *different* server. That boundary in DESIGN.md is already correct.

**Do not copy discarded patterns.** GitHub MCP shipped dynamic `enable_toolset` meta-tools, then removed them. Use **static toolsets** (env / flag), not a discovery triad that mutates `tools/list` at runtime.

References (external):

- [MCP tools spec](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) — annotations, `outputSchema`, `isError`
- [Server instructions](https://blog.modelcontextprotocol.io/posts/2025-11-03-using-server-instructions/) — workflows across tools, not a second catalog
- [Phil Schmid — MCP is not the problem](https://www.philschmid.de/mcp-best-practices) — outcomes, flatten args, 5–15 tools
- GitHub MCP toolsets — default surface vs full catalog; later removal of dynamic toolsets

---

## Recommended sequence

```text
Close 0.6  →  Runtime scaffold (0.6.2 / ZDH-32, done)  →  0.7 MCP quality  →  evals / hosts
                                    (this plan)
```

Do not grow the 0.6 catalog in parallel with 0.7.

---

## Phase 0 — Close 0.6

Days, not a feature train.

- Merge `feat/runtime-coach-0.6`, close ZDH-18–28, close ZDH-15.
- Patch-only after that: mcp 2.x import, host install, secret leaks. **No new tools.**
- Delete `_stub` in `server.py`.
- Freeze: **0.6.x does not grow the catalog.**

---

## Phase 1 — Helper 0.7: MCP interface

Highest-leverage work. This is the increment that follows MCP practice.

`docs/DESIGN.md` stays frozen. 0.7 lives in a new `docs/DESIGN-0.7.md` (create with the first 0.7 PR), same pattern as 0.6.

### 1.A Default toolset ≈ the day-one path (~12 tools)

Always on (`ZEUS_DEV_HELPER_TOOLSETS=core`, default):

| Tool | Why it stays a tool |
| --- | --- |
| `doctor` | Health |
| `start_project` | Writes checklist |
| `next_step` | The coach |
| `set_prereq` | Writes state |
| `validate_env` | Gate before live probes |
| `readiness_check` | Live `:8080` |
| `scaffold_app` / `use_sample` | Disk |
| `bind_contract` | Stamp extract (never invent) |
| `recommend_surface` | Direct vs agent |
| `smoke_test_zeus` / `smoke_test_agent` | First green |
| `diagnose_error` | Recovery |

Opt-in toolsets (env, GitHub-style): `catalog`, `lint`, `travel`, `support`, `handoff`. Power users set `ZEUS_DEV_HELPER_TOOLSETS=core,lint,catalog`.

### 1.B Demote knowledge to resources

| Resource URI (sketch) | Replaces as a default tool |
| --- | --- |
| `zeus-helper://checklist` | `get_checklist` |
| `zeus-helper://glossary/{topic}` | `explain` |
| `zeus-helper://verbs/{name}` | `explain_verb` |
| `zeus-helper://policy/hash-boundary` | `explain_hash_boundary` |
| `zeus-helper://policy/req-id` | `explain_req_id_policy` |
| `zeus-helper://catalog/modes` | `list_catalog_modes` |

`next_step` may return **resource links** (`type: resource_link`) instead of inlining the glossary.

Keep existing Python modules (`explain.py`, `verbs.py`, `walkthrough.py`). Change only how they are **exposed**.

### 1.C Promote walkthroughs to prompts

`suggest_demo_prompts` and the day-one chain in `guides/LIST_OF_PROMPT_SAMPLES.md` become MCP `prompts`: `first_green`, `smoke_question`, `support_pack`. Users/hosts pick them; the model should not spend a tool call to fetch canned strings.

### 1.D Annotations, output schema, `isError`

- **Read-only:** `doctor`, `next_step`, linters, `recommend_*`, `compat_check`
- **Destructive:** `start_project` (reset), `scaffold_app(force=true)`
- **Open-world:** anything that hits Zeus `:8080`
- **Shared output envelope:** `ok`, `failure_class`, `next_action`, `recommended_tools[]`, `docs`
- **Execution failures:** `isError: true`, not a 200-looking dict with an `error` key

### 1.E Tighten `instructions`

Keep only what tool descriptions cannot say:

- Order: `doctor` → `next_step` → …
- Hard constraints: public `:8080`, never invent `contract_hash`, templates are TEMPLATE ONLY
- `scaffold_app` / `smoke_test_agent` already emit ZeusRuntime (0.6.2 / ZDH-32 pulled forward)

Cut the tool-name dump. It duplicates `tools/list` and burns context.

### 1.F Protocol tests

- `tools/list` count for the default toolset (assert ≤ ~15)
- Every exposed tool has annotations
- `resources/list` + `resources/read` for glossary / checklist
- MCP Inspector smoke in CI
- Golden agent prompts from `guides/LIST_OF_PROMPT_SAMPLES.md` (did the model call `next_step` first, or dump 45 tools?)

Unit tests still must not require a cluster.

### 1.G Consolidation (same behavior, fewer names)

| Fold into | Retire as a default tool |
| --- | --- |
| `doctor` with a `detail` enum | `validate_env`, `compat_check`, `semantic_cache_status` (keep as detail or lint toolset) |
| Resource + `next_step` | `get_checklist`, `gap_report` |
| One sample tool | `use_sample` + `travel_golden_path` |
| `lint_app` | `lint_runtime_config` + `lint_app_code` |
| `diagnose_error` / `support_pack_from_turn` | `detective_links` |

**Keep as tools** (actions on caller JSON, not encyclopedia pages): `lint_verb_args`, `suggest_verb_call`, `bind_contract`, `lint_chat_request`. They may live on the `lint` / `catalog` toolset rather than `core`.

---

## Phase 2 — Helper 0.8: Runtime first-green (reopen ZDH-17)

**Pulled forward into 0.6.2** (ZDH-32 AC) so Helper no longer generates the V1 anti-example it lints. Remaining 0.8 work is MCP quality (Phase 1), not the Runtime rewrite.

- `scaffold_app` emits `ZeusRuntime.from_config()` + `HttpxZeusPort` + `OpenAICompatibleLlmClient` (cite `zeus_client_python/examples/minimal_agent.py`).
- `smoke_test_agent` uses `rt.agent.run_turn` → `TurnResult`.
- Floor stays `kotenai-zeus-client>=2.3.0` on the `[agent]` extra.
- `lint_app_code` and scaffold **agree**.
- Checklist 5.2 text stops saying `run_agent`.

`/v2` bootstrap (old ZDH-20) is lower priority: dual `/v1` probes still work. Do it when the engine drops v1, not as a catalog-expanding story.

---

## Phase 3 — Measure the promise

Local time-to-green already exists (`helper_metrics`). Extend it:

- Which tools get called on a real first-green session (ids only; no payloads, tokens, or prompts).
- Eval suite: ~20 prompts from `guides/LIST_OF_PROMPT_SAMPLES.md`; assert sequence (`doctor` / `next_step` before `scaffold_app`; never `:9091`; never invented hash).
- Host matrix: Grok, Claude Code, Cursor. Server `instructions` are client-dependent; measure, don’t assume.

Without this, 0.7 is a refactor that cannot be proven.

---

## Phase 4 — Stay local stdio; split later, don’t grow

- Stdio is the right transport for a laptop coach. Streamable HTTP + OAuth only if there is a shared team server.
- After first-green is reliable, **do not add Explore/Verify here**. `recommend_data_plane_mcp` / `emit_mcp_config` stay handoffs. A second MCP is the correct bounded context.
- Optional later: a tiny **skill** (AGENTS.md-style) that teaches the day-one path, plus a **small** MCP for live probes. Skills for workflow text, MCP for typed actions. Complementary, not a replacement.

---

## What not to do

- Another 0.6-style wave of Zeus encyclopedia tools.
- Exposing `find` / `search` / `get` as Helper tools.
- Hub admin mutations or ZJA jobs.
- Turning semantic cache on in `start_project`.
- Dynamic `enable_toolset` meta-tools (`list_available_toolsets` / `get_toolset_tools` / `enable_toolset`).
- 1:1 REST wrapping of Zeus.
- Rewriting frozen `docs/DESIGN.md` in place — same pattern as 0.6: new `DESIGN-0.7.md` increment.

---

## Epic sketch

| Epic | Outcome | Why this order |
| --- | --- | --- |
| **Close 0.6** | ZDH-15 Done, catalog frozen | Stop forking on In Review |
| **0.7 — MCP quality** | Default ≤12 tools; resources + prompts; annotations; `isError`; Inspector CI | Agents can actually choose tools |
| **0.8 — Runtime first-green** | Scaffold + smoke match Client 2.3 | Mission is green on the current SDK |
| **Evals / hosts** | Golden prompts + host matrix | Proves 0.7 / 0.8 |
| **Data-plane MCP (other repo)** | After 5.1+5.2 is real Runtime green | Already the boundary |

If only one thing happens after merging 0.6: **cut the default tool list and move glossary to resources.** That is the MCP-best-practice path. The Runtime scaffold is the Zeus-best-practice path, and it should come immediately after, not before.

---

## Suggested 0.7 PR DAG

| PR | Title | Depends on |
| --- | --- | --- |
| 0 | Close 0.6 Jira; delete `_stub`; freeze “no new tools in 0.6.x” | — |
| 1 | Tool annotations + shared result envelope + `isError` | 0 |
| 2 | Resources for glossary / checklist / verb encyclopedia / policies | 0 |
| 3 | MCP prompts: `first_green`, `smoke_question`, `support_pack` | 2 |
| 4 | Static toolsets (`core` default; `lint` / `catalog` / `travel` / `support` / `handoff`) | 1 |
| 5 | Consolidate overlapping tools (doctor detail, lint_app, sample, detective_links) | 4 |
| 6 | Tighten server `instructions`; protocol tests + Inspector CI | 4, 2 |
| 7 | `docs/DESIGN-0.7.md` + README / AGENTS.md tool list for the default surface | 4–6 |

**Max parallelism:** PR 1 ∥ PR 2 after PR 0.

0.8 (Runtime scaffold + `smoke_test_agent`) is a **separate epic**, blocked on 0.7 PR 4 at minimum so the new generator is not registered on a 45-tool default list.

---

## Key decisions

1. **Do not add Zeus-domain tools in 0.7.** Curate, re-expose, consolidate.
2. **Static toolsets, not dynamic discovery.** Env / flag; default `core`.
3. **Knowledge is resources; walkthroughs are prompts; only side effects stay tools.**
4. **Reopen ZDH-17 as 0.8**, after the default surface is small.
5. **Leave ZDH-20 (`/v2` probes) until engine v1 is gone.**
6. **DESIGN.md remains frozen**; 0.7 design is a new increment file.
7. **Semantic cache stays off.** Data-plane and ZJA stay handoffs.

---

## Out of scope (0.7 and 0.8)

- Data-plane MCP tools (`rt.data.find` as an MCP tool).
- Hub enable-wizard, entity-map writes, `POST /admin/api/contracts`.
- Computing or minting production `contract_hash`.
- ZJA / `RunJob` runtime.
- Engine-contributor MCP.
- Remote Streamable HTTP + OAuth (unless a team-shared server is explicitly requested).
- Teaching `import zeus_client_v2` as the default.
- Scraping Detective / Rewind payloads.

---

## Verification

**Unit (every 0.7 PR):** `pytest -q` from repo root; no live Zeus required.

| Area | Assert |
| --- | --- |
| Default `tools/list` | Count within the core cap (~12, hard ceiling 15) |
| Annotations | Every default tool has `readOnlyHint` (and destructive/openWorld where true) |
| Resources | Glossary topic and checklist readable without a tool call |
| Errors | A failed `readiness_check` / `bind_contract` path sets `isError` (or documented SDK equivalent) |
| Secrets | No password/token in fixtures or tool-return fixtures |
| Scaffold | Generated `main.py` uses `ZeusRuntime`; `lint_app_code` is clean on it (landed 0.6.2) |

**Manual (0.7 exit):** against a lab Zeus 0.7.x with only `core` enabled: `doctor` → `next_step` → `readiness_check`. Confirm `tools/list` does not include `explain_hash_boundary` / `detective_links` / `semantic_cache_status`. Confirm probes never hit `:9091`.

**Lint:** `ruff check` on `src/` `tests/` touched files.

---

## Open questions (defaults if unapproved)

1. **Jira** — New epic for 0.7 (MCP quality) and 0.8 (Runtime scaffold), both relating to ZDH-1 / ZDH-15. Do not nest epic-under-epic (same as 0.6).
2. **Default tool cap** — Target 12, hard ceiling 15 on `core`. Extra tools go to named toolsets, not the default.
3. **Backward compatibility** — 0.7 may hide tools from `tools/list` by default but should still **implement** them when the matching toolset is on, so existing prompt samples keep working for power users.
4. **Travel sample** — Leave `travel_golden_path` behavior; fold it under the sample tool / `travel` toolset. Do not rewrite `demo_travel_sample`.

**Defaults for this docs-only landing:** persist this file; do not create Jira or start PRs until asked.
