# Host matrix — Helper MCP instructions (ZDH-40)

Server `instructions` are **client-dependent**. Measure; do not assume one host’s tool-picking matches another.

Local only: tool **ids** in `helper_metrics` / `metrics.jsonl`. No prompts, bodies, or tokens.

| Host | Config | Last measured | Notes |
| --- | --- | --- | --- |
| Grok Build | checkout venv: `…/.venv/bin/python -m zeus_dev_helper_mcp` (see Grok gotchas) | **2026-09-15** (Helper **0.7.0**, `core` **12** tools) | First-green **reached** on `demos/travelapp` with **PyPI `kotenai-zeus-client==2.4.1`** (Paris hotels re-smoke). Checks **1–3 pass**, **4 partial**. `next_step` stayed on 2.2 after platform pass (auth skip). Did **not** call `smoke_test_agent` (ran `python main.py` instead). Prior 2026-09-14: handshake OK, 12 tools, checks 1–4 **not scored**. |
| Claude Code / Desktop | `mcpServers` JSON, `uvx` / venv python | | Unmeasured |
| Cursor | MCP stdio entry, same env | | Unmeasured |

## Application-user beer utterance (Grok Build, 2026-09-18)

**Utterance (paraphrased):** Zeus at `http://192.168.0.219:8080`, beer-sample enabled — make a sample website from the endpoint (no Helper tool names, no LLM requirement).

| Field | Result |
| --- | --- |
| Outcome | Working Direct catalog UI hand-rolled (~22 min to first paint); Helper coach path mostly skipped |
| Helper tools used | `doctor` once (`detail=health`); **not** `start_project`, `set_prereq`, `next_step`, `recommend_surface`, `use_sample`, `smoke_test_zeus`, `diagnose_error` |
| Miss (pre-ZDM-6) | Agent grepped Zeus docs/API and curled verbs; travel default would have been wrong (other bucket); beer catalog UI now lands via `use_sample(sample=beer)` |
| Current writer | Search is `rt.agent.run_turn` with `chat_request` omitted (SCOPE BRIEF + MINI-SCHEMA). An LLM key is required in the Helper process and in the app `.env`. `llm.api_key_env` stays the variable name. The BFF does not build a pipeline body |
| Epic | [ZDM-1](https://kotenai.atlassian.net/browse/ZDM-1) · prompts [ZDM-5](https://kotenai.atlassian.net/browse/ZDM-5) · design [`DESIGN-zdm-1-beer-first-green.md`](DESIGN-zdm-1-beer-first-green.md) |

**Re-measure after** coach + `use_sample(sample=beer)` land (ZDM-3 / ZDM-6 / ZDM-2). Record time-to-green here when the utterance first-greens on the Helper path.

### Coach compliance (Grok / Claude)

After `doctor`, if the user named a URL or sample: **`set_prereq` with the user’s URL/bucket/scope → `start_project` → `next_step`**. Do not skip to grepping Zeus docs/API or curling verbs by hand until `readiness_check` / `smoke_test_zeus` (or `next_step`) say so. Call `recommend_surface` before Travel LLM vs beer catalog UI vs FastAPI. Beer search is `rt.agent.run_turn`. If `has_llm_key=false`, say an LLM key is required rather than cloning travel or switching that BFF to bare Direct verbs. Checklist **1.2** stays open until this process has `LLM_API_KEY`, `XAI_API_KEY`, or `OPENAI_API_KEY`. A stored `has_llm_key=true` does not count. After `use_sample` or `scaffold_app`, checklist **3.2** stays open until `verify_local_setup` sees that name set in the app `.env` and `config.json` `llm.api_key_env` is still that name.

## Current demo (Grok, 2026-09-15)

App: Helper `scaffold_app` tree **`demos/travelapp`**. Engine Zeus **0.8.31** public `:8080`. Scope `travel-sample/_default`, mode `analytics`. Client **`kotenai-zeus-client==2.4.1`** from **PyPI** (`requirements.txt` / `pyproject.toml`; wheel `kotenai_zeus_client-2.4.1-py3-none-any.whl`). 5.2 verb-proof **re-smoked on 2.4.1**.

| Gate | State |
| --- | --- |
| 2.1 Zeus `:8080` | pass (`/healthz` `/readyz` `/version`) |
| 2.2 Auth | **skip** (`auth_mode=none`) — Helper checklist still `todo` |
| 2.3 Scope | pass (bootstrap 200, live chat_request **13** verbs) |
| 4.1 / 4.2 Bind | **done on disk** (live stamp copied, not invented). Checklist items still `todo` |
| 5.1 `smoke_test_zeus` | pass — `describe` `req_id=8d347b52-abec-470b-a172-60d8ea561779` |
| 5.2 Agent first-green | **pass via `python main.py` on PyPI 2.4.1**, not `smoke_test_agent` |

**5.2 evidence (ids only):** catalog source `travel-sample__default/chat_request_analytics_v2.json`; pin `analytics_base5_2` / hash prefix `md5:5aacbf1d…`; `client_floor=client-floor-6.1`. Catalog-brief (sibling 2.4.0): `session_id=sess_20260915T202735759419`, hops=0.

| Client | Question | status | hops | session_id | req_id |
| --- | --- | --- | --- | --- | --- |
| sibling 2.4.0 | Find a few hotels in Paris | ok | 1 | `sess_20260915T211802369854` | `115cbd96-9e89-4e47-a7ff-71ec82cabb32` |
| **PyPI 2.4.1** | Find a few hotels in Paris | ok | 1 | `sess_20260915T222513801422` | `b4837cf6-c761-4ded-a10a-41760bf19651` |

Config on disk (no secret values): `llm.api_key_env=LLM_API_KEY`, `chat_requests_dir=chat_requests`, `zeus.scope_contracts` pinned from `bind_contract`, semantic cache off. Install: `kotenai-zeus-client==2.4.1` (PyPI), not a `file:` sibling.

### First-green checks (this session)

| # | Check | Result |
| --- | --- | --- |
| 1 | `doctor` or `next_step` before `scaffold_app` | **Pass** — `doctor(detail=all)` then `next_step` then `readiness_check`. No `scaffold_app` this session (tree already on disk). |
| 2 | No Hub `:9091` as app target | **Pass** — probes and `config.json` use `:8080` |
| 3 | No invented `contract_hash` / `compute_local` | **Pass** — `bind_contract` on live `GET /v1/ai/chat_request.json` stamp |
| 4 | `helper_metrics` `tool_calls` is ids only | **Partial** — `metrics.jsonl` is ids-only (`tool` + `event`). This session’s recorded event is `smoke_test_zeus_ok`. `doctor` / `next_step` / `readiness_check` / `bind_contract` were called in-host; not all appear as later `tool_call` lines. No payloads/tokens. |

**Helper tool ids used (Grok, in order, no payloads):** `doctor` → `next_step` → `readiness_check` → `next_step` → `smoke_test_zeus` → `next_step` → `bind_contract`. Not used: `start_project`, `scaffold_app`, `use_sample`, `smoke_test_agent`, `recommend_surface`, `diagnose_error`.

### Host / coach gaps (block first-green unless the agent leaves the rails)

These are why “Helper says 2.2” is not the demo’s real next step. Family write-up: `zeus_client_design` [HOW_TO_MAKE_A_CLIENT_LESSON_LEARNED.md](https://github.com/koten-ai/zeus_client_design/blob/main/HOW_TO_MAKE_A_CLIENT_LESSON_LEARNED.md) LL-2026-09-15-001…006.

| Gap | What Grok had to do outside Helper |
| --- | --- |
| `next_step` stuck on **2.2** after readiness **pass** (`auth_mode=none` skip ≠ pass) | Ignore 2.2; continue bind / smoke |
| Scaffold `kotenai-zeus-client>=2.3.0` — **PyPI 404** (earlier same day) | **Resolved:** PyPI now has **2.4.1** only. Demo pin is `kotenai-zeus-client==2.4.1`. Sibling `file:../../zeus_client_python` removed. |
| `llm.api_key_env` held a secret value | Set to `LLM_API_KEY`. Helper now rejects that field when it is not an env-var name (`lint_runtime_config` / `verify_local_setup`, `llm_key_missing`) and keeps checklist **3.2** open until `.env` has the named variable |
| Live catalog `_lineage.base_id=base-6.1` vs default `client-floor-5` | Set `client_floor=client-floor-6.1` or load fails closed and `main.py` continues with **no tools** |
| Default smoke question → hops=0 | Second turn: data question (Paris hotels) for hops≥1 |
| Checklist 4.1 / 4.2 / 5.2 still `todo` after disk+`main.py` green | Helper does not mark those when the agent binds/runs outside `smoke_test_agent` |

## Grok gotchas

Set `ZEUS_URL` to the Zeus public API you actually use (`http://<zeus-host>:8080` or e.g. `http://192.168.0.219:8080`). Use `http://localhost:8080` only when Zeus is on the same machine. After add, if the user named a URL/sample, call `set_prereq` with that URL — do not leave a stale localhost env as the only probe target. `doctor` reports stored vs effective URL (ZDM-3).

`uvx` argument is the published package, not the MCP server id:

```bash
grok mcp add zeus-dev-helper \
  -e ZEUS_URL=http://192.168.0.219:8080 \
  -- uvx zeus-dev-helper-mcp
```

`uvx zeus-dev-helper` is **not** on PyPI. Status `unavailable`, `grok mcp doctor` handshake `connection closed: initialize response`, stderr `No solution found` / `zeus-dev-helper was not found in the package registry`.

`uvx` installs whatever is on PyPI (may be older than this tree; 0.6.x exposes the full catalog, not `core`’s 12 tools). To measure an unreleased Helper, point at this checkout’s venv. Put `--` **before** `-m` or Grok reports `unexpected argument '-m'`:

```bash
grok mcp add zeus-dev-helper \
  -e ZEUS_URL=http://192.168.0.219:8080 \
  -- "$(pwd)/.venv/bin/python" -m zeus_dev_helper_mcp
```

Confirm with `grok mcp doctor zeus-dev-helper` (handshake OK, 12 tools on `core`), then refresh MCP in the session.

Measure on each host (first-green session, `core` toolset):

1. Did the model call `doctor` or `next_step` **before** `scaffold_app`?
2. Did any tool argument / generated app use Hub `:9091`?
3. Did it invent `contract_hash` / `compute_local`?
4. `helper_metrics` `tool_calls` is ids only.

Fill **Last measured** after a real session. Unit tests cover the corpus and trace checker; they do not replace this table.
