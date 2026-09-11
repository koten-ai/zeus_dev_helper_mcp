# Developer Helper MCP 0.7 — MCP server quality

**Status:** Implemented (0.7.0).  
**Product:** `zeus_dev_helper_mcp`  
**Parent epic:** [ZDH-29](https://kotenai.atlassian.net/browse/ZDH-29) (relates [ZDH-1](https://kotenai.atlassian.net/browse/ZDH-1), [ZDH-15](https://kotenai.atlassian.net/browse/ZDH-15))  
**Plan:** [`PLAN-mcp-quality-0.7.md`](PLAN-mcp-quality-0.7.md)  
**Frozen MVP:** [`DESIGN.md`](DESIGN.md) (ZDH-2) — not rewritten here.  
**Prior increment:** [`DESIGN-0.6.md`](DESIGN-0.6.md)  
**Tool catalog:** [`TOOLS.md`](TOOLS.md) — when / args / side effects / do-not (full catalog, including opt-in toolsets).

This increment curates the MCP interface. It does **not** add Zeus-domain tools.

---

## 1. Promise (unchanged)

First green middle-man turn — `session_id` / `req_id` — on public **`:8080`**.

`scaffold_app` / `smoke_test_agent` already emit **ZeusRuntime** + `rt.agent.run_turn` (0.6.2 / ZDH-32).

---

## 2. Default toolset (`core`, ≤15)

Always on. `ZEUS_DEV_HELPER_TOOLSETS` defaults to `core`. Extra named sets are unioned; `core` cannot be switched off. `all` enables every named set.

| Tool | Why it stays a tool |
| --- | --- |
| `doctor` | Health (`detail=health\|env\|compat\|cache\|all`) |
| `start_project` | Writes checklist |
| `next_step` | The coach |
| `set_prereq` | Writes state |
| `readiness_check` | Live `:8080` |
| `scaffold_app` / `use_sample` | Disk / sample (travel includes golden path) |
| `bind_contract` | Stamp extract (never invent) |
| `recommend_surface` | Direct vs agent |
| `smoke_test_zeus` / `smoke_test_agent` | First green |
| `diagnose_error` | Recovery |

Opt-in (static, env only — **no** dynamic `enable_toolset`): `catalog`, `lint`, `travel`, `support`, `handoff`.

Hidden tools stay implemented when their toolset is on so existing prompt samples keep working for power users.

---

## 3. Resources

Knowledge is `resources/list` + `resources/read`, not default tools.

| URI | Replaces as a default tool |
| --- | --- |
| `zeus-helper://checklist` | `get_checklist` |
| `zeus-helper://glossary/{topic}` | `explain` |
| `zeus-helper://verbs/{name}` | `explain_verb` |
| `zeus-helper://policy/hash-boundary` | `explain_hash_boundary` |
| `zeus-helper://policy/req-id` | `explain_req_id_policy` |
| `zeus-helper://catalog/modes` | `list_catalog_modes` |

Indexes: `zeus-helper://glossary`, `zeus-helper://verbs`.  
`next_step` returns `resource_links` (`type: resource_link`) plus recommended tools.

---

## 4. Prompts

| Prompt | Role |
| --- | --- |
| `first_green` | Day-one order + hard constraints |
| `smoke_question` | Advice-shaped `smoke_test_agent` question |
| `support_pack` | Redacted support pack (ids/hops only) |

`suggest_demo_prompts` is not on the default tool list (support toolset).

---

## 5. Annotations, envelope, `isError`

Every exposed tool sets `readOnlyHint`, `destructiveHint`, `idempotentHint`, and `openWorldHint` (explicit; do not rely on spec defaults).

- **Read-only:** `doctor`, `next_step`, linters, `recommend_*`, `compat_check`, glossary/verb/bind reads
- **Destructive:** `start_project` (reset), `scaffold_app` (may overwrite with `force=true`)
- **Open-world:** anything that hits Zeus `:8080`

Shared JSON envelope on tool results: `ok`, `failure_class`, `next_action`, `recommended_tools[]`, `docs`.

Execution failures (`readiness_check` overall fail, `bind_contract` refuse, catalog fetch miss, scaffold/smoke fail) raise MCP `ToolError`. On mcp 2.x the protocol handler maps that to `CallToolResult(isError=true)`. Domain reports (lint findings, gated `start_project`) stay `ok=false` without `isError`.

---

## 6. Instructions

Server `instructions` cover workflows across tools, not a second catalog: order (`doctor` → `next_step`), hard constraints (`:8080`, never invent `contract_hash`, TEMPLATE ONLY), resources vs tools, prompts, handoffs after 5.1+5.2.

---

## 7. Boundaries (unchanged)

Not this MCP: data-plane verbs as tools, Hub mutations, ZJA jobs, invented `contract_hash`, dynamic toolset meta-tools.

Name-folding ([ZDH-35](https://kotenai.atlassian.net/browse/ZDH-35)): `doctor(detail=…)` covers env/compat/cache; `lint_app` covers config+code; `use_sample` includes travel golden path; `diagnose_error` / `support_pack_from_turn` include Detective URL templates. Old names stay on opt-in toolsets.

---

## 8. Verification

Unit tests (`pytest -q`) do not require a cluster. Protocol tests assert default `tools/list` ≤ 15, annotations on every default tool, `resources/list`+`read`, `prompts/list`+`get`, and `ToolError` on failed `bind_contract` / `readiness_check`.
