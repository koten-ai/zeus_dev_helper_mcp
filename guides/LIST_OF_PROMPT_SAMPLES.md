# List of prompt samples — Developer Helper MCP

Natural-language prompts for a coding agent that has **zeus-dev-helper** connected. Each section is one MCP tool. Say the prompt as a user; the agent should call the named tool.

Tool contract (when / args / side effects / do-not): [`docs/TOOLS.md`](../docs/TOOLS.md).

Hard constraints the prompts assume:

- Public Zeus API is **`:8080`**, never Hub **`:9091`** on the app path.
- Never invent `contract_hash`. `fetch_chat_request` is **template only**.
- No secrets in checklist evidence or support packs.
- Coach only: this MCP does not run data-plane verbs, Hub admin mutations, or ZJA jobs.

Day-one order (for chaining, not required per prompt). Default MCP surface is `core`; encyclopedia tools need `ZEUS_DEV_HELPER_TOOLSETS` or `zeus-helper://` resources:

```text
doctor → (if user named URL/sample) set_prereq → start_project → next_step
  → readiness_check → use_sample | scaffold_app → bind_contract → recommend_surface
  → smoke_test_zeus → smoke_test_agent → diagnose_error
```

MCP prompts: `first_green`, `smoke_question`, `support_pack`. Resources: `zeus-helper://checklist`, `glossary/{topic}`, `verbs/{name}`, `policy/hash-boundary`, `policy/req-id`, `catalog/modes`.

---

## Application user (zero Zeus vocabulary)

Copy-paste prompts for someone who only has a public Zeus URL and a sample name. They will not say Helper tool names. The agent should stay on the coach path (see [`docs/DESIGN-zdm-1-beer-first-green.md`](../docs/DESIGN-zdm-1-beer-first-green.md)).

**Plane reminder (ZDM-9):** TravelPlan / `demo_travel_sample` = **agent-plane** (LLM + `run_turn`). `demo_beer_sample` = **data-plane Direct** (find→get, no LLM). Docs: [Using Zeus Client](https://docs.koten.ai/zeus-client/using-zeus-client). A Direct website may copy TravelPlan’s BFF/same-origin/config shape only — **do not copy `run_turn`** unless this is an agent app. Beer / website / no LLM **never clones** `demo_travel_sample`.

### Make a website from beer-sample

1. I have Zeus running at `http://192.168.0.219:8080` and beer-sample enabled. Make a sample website from that endpoint.

**Expected tool sequence:** `doctor` → `set_prereq(zeus_url=http://192.168.0.219:8080, bucket=beer-sample, scope=_default, has_llm_key=false)` (user URL, not localhost) → `start_project(sample=beer)` (named beer + no LLM also reroutes default travel → beer) → `next_step` → only the recommended tool (`readiness_check` / `use_sample(sample=beer)` / `smoke_test_zeus` / `recommend_surface(needs_llm=false)`). Do not grep the Zeus engine repo or hand-roll curl until readiness/smoke say so. Do not ask for an LLM key for first paint. **Never** `use_sample(sample=travel)` / clone `demo_travel_sample` on this path.

2. Don’t use an LLM. Browse beer-sample with find/search and show cards.

**Expected tool sequence:** Same coach order as (1). `recommend_surface(intent=typeahead|single_verb, needs_llm=false)` → Direct catalog UI via `use_sample(sample=beer)`. Never `smoke_test_agent` / travel clone as the primary path.

3. What beers are made from fruit?

**Expected tool sequence:** Only after a Direct catalog site exists. Answer via the site / Direct find+search (style map or FTS fallback) — not `smoke_test_agent` unless the user asked for chat. On failure, `diagnose_error` (empty find→get, FTS `doc_key`-only).

---

## Start and health

### `doctor`

Health / doctor: version, public config (no secrets), catalog source readiness.

1. Run doctor on the Zeus Dev Helper MCP. Tell me the version, whether catalogs are reachable, and whether `ZEUS_URL` looks like public `:8080`.
2. Is this Helper MCP healthy? Check config (redact secrets) and catalog templates before we start a first app.
3. Diagnose the helper itself: is `ZEUS_CHAT_REQUEST_DIR` or GitHub fetch set up, and what docs should I read first?

### `start_project`

Start or reset the first-app coaching checklist (single-agent default). Multi-agent is gated until smokes are green unless `force_multi=true`.

1. Start a new Zeus first-app project for a single-agent travel sample. Initialize the checklist and tell me the next step.
2. Reset my Helper coaching checklist. Goal is `single-agent`, sample is `travel`. Do not enable semantic cache.
3. I want a multi-agent Yelp track. Start that project and show me whether Helper blocks it until single-agent is green.

### `helper_metrics`

Local privacy-safe success metrics (time-to-green heuristic; never leaves the machine).

1. Show Helper time-to-green metrics from this machine only. Do not send anything off-box.
2. Have we recorded a `start_project` and first Zeus/agent smokes yet? Summarize local helper metrics.
3. What is our local time-to-first-green if 5.1 and 5.2 are done?

---

## Checklist walkthrough

### `get_checklist`

Return the current first-app checklist state.

1. Show the full Zeus first-app checklist, including item statuses and evidence.
2. Dump my current Helper checklist JSON so I can see which phases are still `todo`.
3. What is stored in the coaching checklist right now, and which project/sample is it bound to?

### `next_step`

Return the single current checklist blocker plus recommended Helper tools.

1. What is the single next step on my Zeus first-app checklist? Which Helper tool should I run?
2. Don't give me the whole gap list — just the current blocker and the recommended tools for it.
3. Coach me: I am stuck. Call `next_step` and tell me exactly what to do next.

### `gap_report`

What's left for the single-agent / production-ish path (phases 4–7 focus).

1. Give me a gap report for getting this Zeus Client app to first green.
2. What is still open in bind, smoke, customize, and production-ish phases?
3. Summarize remaining checklist work after platform readiness. Focus on phases 4–7.

### `mark_done`

Mark a checklist item done (optional evidence string, no secrets).

1. Mark checklist item `2.1` done. Evidence: Zeus `:8080` healthz returned 200. No tokens.
2. I finished scaffolding. Mark `3.1` done with evidence `wrote zeus_first_app/main.py` and show the next step.
3. Smoke Zeus succeeded with a `req_id`. Mark `5.1` done using only the id, never the auth header.

### `mark_blocked`

Mark a checklist item blocked with a reason.

1. Mark `2.3` blocked: scope is not enabled on this cluster. Suggest the next Helper tool.
2. I cannot run `smoke_test_agent` because there is no LLM key. Mark `5.2` blocked with that reason.
3. Block item `4.2` — we only have a `TO_BE_FILLED` template hash, not a live stamp. Do not invent a hash.

---

## Prerequisites and platform

### `set_prereq`

Store non-secret prereqs for readiness. Does not store password or token values.

1. Record prereqs: Zeus URL `http://localhost:8080`, bucket `travel-sample`, scope `inventory`, mode `analytics`, role `dev`. Do not store secrets.
2. Save that we have username+password auth present in env (flags only), public API `:8080`, collection `_default`.
3. Set prereqs for `beer-sample` / `_default` on `:8080` with `auth_mode=basic` and `has_llm_key=true`. Then tell me to run `validate_env`.

### `validate_env`

Validate Helper env + stored prereqs shape (presence only — no secret values).

1. Validate my Helper environment. Flag Hub `:9091`, missing `ZEUS_URL`, missing LLM key, and catalog template problems.
2. Is env ready for `readiness_check`? Check presence of Zeus URL, bucket/scope, and catalog templates without printing secrets.
3. Run `validate_env` and explain every issue with its `failure_class`.

### `readiness_check`

Live Zeus platform gates: healthz / readyz / version, auth, bootstrap, chat_request. Never returns secrets.

1. Run a live readiness check against Zeus `:8080` and update the checklist.
2. Probe platform gates without updating the checklist (`update_checklist=false`). Tell me which gate is red.
3. Is this scope enabled and authenticated on the public API? Run readiness and give `failure_class` + next action if not.

### `compat_check`

Probe `GET /version` + `/healthz` on `:8080` and evaluate static 0.7 feature gates.

1. Check Zeus compatibility for Client 2.3 / engine 0.7. Use public `:8080` only.
2. Does this cluster have the version for semantic cache (needs ≥ 0.7.6)? Run `compat_check` and keep cache off anyway.
3. Compat-check `http://localhost:8080`. If someone passed `:9091`, refuse it as `wrong_port_hub_vs_public`.

### `bootstrap_scope`

Live `GET /v1/ai/bootstrap/scope/{bucket}/{scope}` plus chat_request summary.

1. Bootstrap scope `travel-sample` / `inventory` and summarize the live chat_request. Prefer the stamp; do not invent a hash.
2. Call bootstrap for my default bucket/scope with `detail=summary` and update the checklist.
3. Show a full bootstrap summary (`detail=full`) for `beer-sample` / `_default` so I can see collections and modes.

---

## Catalogs and glossary

### `list_catalog_modes`

List V2 min chat_request modes from `zeus_chat_request`.

1. List the V2 min catalog modes available from `zeus_chat_request`.
2. What chat_request modes can I fetch templates for before we stamp on Hub?
3. If catalog fetch fails after auto-clone, tell me to fix git/network or set `ZEUS_CHAT_REQUEST_DIR` / `GITHUB_TOKEN` — then list modes.

### `fetch_chat_request`

Fetch a V2 min chat_request template by mode. Always **TEMPLATE ONLY**. Prefer live Zeus stamp for production.

1. Fetch the `analytics` min chat_request template (`detail=summary`). Warn that it is template only.
2. Get the full `tenant` chat_request template. Do not treat its hash as production; we still stamp on Zeus.
3. Pull the `regulated` min catalog so I can see allowed verbs, then remind me to bind a live stamp later.

### `explain`

Explain a Zeus/Client concept (glossary) with a docs deep-link.

1. Explain `contract_hash`. Stress that we never invent production hashes.
2. Explain `zeus_runtime` vs the retired V1 `run_agent` path, and link the Client docs.
3. Explain `motion` versus Zeus `mode`. List the 13 motions and tell me to use `recommend_motion` instead of generating a catalog.

### `explain_hash_boundary`

MINI-SCHEMA / brief are excluded from `contract_hash`.

1. What is excluded from `contract_hash`? Explain the hash boundary (MINI-SCHEMA, brief, guidance).
2. Can I inject MINI-SCHEMA at call time without changing the bound hash? Explain the hash boundary.
3. Why must we not `compute_local` a production hash? Use `explain_hash_boundary`.

### `explain_req_id_policy`

One UUID per hop; never `base:1`; never Rewind `POST /v2/session/{id}/turn`.

1. Explain Zeus `req_id` policy: one opaque UUID per HTTP hop, no `base:1` composites.
2. How should I group hops with `X-Zeus-Chat-Id` / `X-Zeus-Turn-Id`? Explain req_id policy.
3. Is it legal to Rewind by posting `/v2/session/{id}/turn`? Explain the policy and say no.

### `suggest_demo_prompts`

Starter advice-shaped prompts for smoke / demos (not raw SQL).

1. Give me starter demo questions for `smoke_test_agent` — advice-shaped, not SQL.
2. What should I ask the travel-sample agent on the first green turn?
3. Suggest demo prompts I can paste into a Zeus Client smoke without leaking secrets.

---

## Project on disk

### `scaffold_app`

Write a ZeusRuntime middle-man (`cli` or FastAPI `api`). UI demos use `use_sample` instead.

1. Scaffold a first Zeus app into `./zeus_first_app` named `zeus_first_app`. Don't overwrite unless needed.
2. Create a middle-man project at `/tmp/zeus_first_app` with `force=true` so we can start from a clean tree.
3. Bootstrap my first **API** Zeus app into `./zeus_first_api` with `app_kind=api` and `coding_language=python` (FastAPI `POST /turn`).
4. I asked for a golang API — call `scaffold_app` with `coding_language=golang` and show the unsupported response (do not invent an SDK).

### `start_project` (API vs UI)

1. Start a first-app checklist with the default travel **UI** sample.
2. Bootstrap an API-only track: `start_project(sample=api)` then show the next step.
3. I will give ZEUS_URL and say I have credentials in env — `start_project(sample=api)` then `set_prereq` with URL + `has_username`/`has_password` flags only (no password values).

### `use_sample`

Locate or clone public `demo_travel_sample` (UI default). Sets `DEMO_TRAVEL_SAMPLE_DIR`.

1. Bootstrap the travel UI sample — clone it if needed and show where it landed.
2. Clone the travel sample as directory `my_first_zeus_ui` under my workspace (`project_name=my_first_zeus_ui`).
3. I already have the sample at `/path/to/demo_travel_sample`. Run `use_sample` with that `sample_dir` (no re-clone).
4. Can I switch the sample to Yelp/multi now? Use `use_sample` and show the single-agent gate if it blocks.

### `travel_golden_path`

Travel sample golden path phases + optional layout validation.

1. Walk the travel-sample golden path and validate the layout if `DEMO_TRAVEL_SAMPLE_DIR` is set.
2. What are the travel golden-path phases? Run `travel_golden_path` for my local clone.
3. Check `/path/to/demo_travel_sample` against the travel golden path before we smoke.

### `write_env`

Write `.env.example` from prereqs (no secrets).

1. Write `.env.example` into `./zeus_first_app` from stored prereqs. Do not put passwords in the file.
2. Generate an env template for the scaffolded app at `/tmp/zeus_first_app`.
3. Refresh `.env.example` in the current project dir from Helper prereqs (presence flags only).

### `verify_local_setup`

Check `zeus_client` import and optional scaffold files.

1. Verify local setup for `./zeus_first_app`: can we import the client and are scaffold files present?
2. Check whether `kotenai-zeus-client` is installed and whether the target dir looks like a Helper scaffold.
3. Run `verify_local_setup` with no target dir — just tell me if the Zeus Client import works.

---

## First green (smoke)

### `smoke_test_zeus`

Smoke Zeus without LLM: readiness + `POST /v2/{bucket}/{scope}/describe`.

1. Smoke Zeus on `:8080` without an LLM. Update checklist 5.1 if describe works.
2. Run `smoke_test_zeus` with `update_checklist=false` so I can see describe output first.
3. Prove the public API can describe this scope. If it fails, return `failure_class` and next action.

### `smoke_test_agent`

One Zeus Client `rt.agent.run_turn` (needs `kotenai-zeus-client>=2.3.0` + LLM key).

1. Run one agent smoke turn: "In one short sentence, what data is available in this scope?"
2. Smoke the agent with "A fun beach destination in Mexico, in April, under $300." Capture `session_id` / `req_id` only — no secrets.
3. Do a first-green agent turn and update checklist 5.2 if Zeus tools were used.

### `diagnose_error`

Map error signals to `failure_class` + `errors.md` anchor (ErrorCode + 0.7 classes).

1. Diagnose this Zeus error: HTTP 401, message `unauthorized`. What `failure_class` is it?
2. I got ErrorCode `060010` trying to run `pipeline` on Direct. Diagnose it and tell me the correct surface.
3. Diagnose status 400, body contains `base:1`, `req_id` `11111111-1111-1111-1111-111111111111`. Map to `invalid_req_id` / composite policy and give Detective URL templates only.

---

## Runtime coach (Direct vs agent)

### `recommend_surface`

Pick Direct vs agent surface + Trace-Class. Does not call Zeus.

1. I need as-you-type hotel name suggestions. Recommend the surface (`typeahead` vs `run_turn`).
2. Recommend a surface for a natural-language question that needs an LLM. Include the do-not list (no `:9091`, no invented hash, no pipeline on Direct).
3. We will run a multi-step DAG of verbs. Recommend `multi_step` / agent-for-pipeline — not `rt.data.verb`.

### `explain_verb`

V2 verb encyclopedia: path class, demux, Direct vs pipeline.

1. Explain the `find` verb: path class, `return` router, equality-only `where`, MINI-SCHEMA.
2. Explain `pipeline`. Confirm it is rejected on Direct and which surface to use instead.
3. Explain `get` vs `search`. Stress that `get` wants graph `n_*` ids, not FTS `biz:` keys.

### `lint_verb_args`

Lint a would-be V2 verb JSON body. Does not POST.

1. Lint this `find` body before I POST it:

   ```json
   {"entity_type": "Hotel", "where": {"city": "Paris"}, "return": "rows", "limit": 5}
   ```

2. Lint `get` with `{"ids": ["biz:hotel:1"]}`. I think FTS keys are illegal as node ids.
3. Lint a `pipeline` body I was about to send on Direct (`rt.data.verb`). Tell me if that is forbidden.

### `suggest_verb_call`

Draft a legal V2 verb JSON body from a goal. Guidance only — does not POST.

1. Suggest a legal V2 call to list hotels in Paris with equality-only `where`. Do not POST it.
2. Draft a `describe` body to get entity types for this scope. Guidance only.
3. I want a typeahead-style recall of "beach resort". Suggest a `search` body with a required `strategy`, still do not call Zeus.

### `describe_scope`

Live MINI-SCHEMA: entity types + field names only, no document samples.

1. Describe scope `travel-sample` / `inventory` — entity types and field names only, no sample documents.
2. Pull live MINI-SCHEMA for my default bucket/scope so I can lint `where` keys.
3. What fields exist on this scope? Use `describe_scope` on `:8080`; refuse Hub `:9091`.

---

## Contract and catalog bind

### `lint_chat_request`

Lint a chat_request JSON (path or pasted). Read-only; never stamps.

1. Lint `./chat_request.json` for `_format`, verbs, and `TO_BE_FILLED` placeholders. Do not stamp.
2. Lint this pasted catalog JSON and tell me if it is still a min template rather than a live stamp.
3. Check `/tmp/analytics.chat_request.json` for missing verbs and placeholder hashes.

### `bind_contract`

Extract stamped `contract.hash` only. Refuse placeholders / `compute_local`.

1. Bind the contract from `./stamped_chat_request.json`. Extract the stamped hash only — refuse `TO_BE_FILLED`.
2. I have a live stamp for `travel-sample` / `inventory` / `analytics`. Bind it; do not compute a local hash.
3. Try to bind this template JSON. If the hash is a placeholder, refuse and tell me to stamp on Hub.

### `catalog_diff`

Compare live bootstrap summary vs on-disk catalog vs bound hash prefix.

1. Diff my on-disk `./chat_request.json` against live bootstrap and bound hash prefix.
2. Catalog-diff the travel analytics template vs what Zeus bootstrap reports for this scope.
3. Compare bound hash `abc123` (prefix only from a real stamp) to the file on disk. Do not invent a full hash.

---

## Config and code lint

### `lint_runtime_config`

Lint client `config.json` (`:8080`, auth_mode, env names, cheap path). Secrets redacted.

1. Lint `./config.json` for Hub `:9091`, secret literals, cheap-path defaults, and semantic cache left off.
2. Check `/tmp/zeus_first_app/config.json`. Redact any secrets in the report.
3. Lint runtime config and tell me if `auth_mode` and env names match Helper prereqs.

### `lint_app_code`

Anti-example scan of `main.py` / Dockerfiles (stale V1, hash literals, `:9091`).

1. Lint `./zeus_first_app/main.py` for Hub port, invented `contract_hash`, and stale V1 `run_agent` as the default path.
2. Scan `/tmp/zeus_first_app` (including Dockerfile) for anti-examples before we smoke.
3. Anti-example scan this app: no `:9091`, no hash literals, no secrets in prompts.

---

## Correlation and support

### `detective_links`

Hub Detective URL templates only — no scrape.

1. Give Detective URL templates for `req_id` `11111111-1111-1111-1111-111111111111`. Do not scrape Hub.
2. I have `chat_id` `chat-demo-1`. Emit Detective links only (`/hub/debug/req/<id>` and `/hub/debug?chat_id=`).
3. Build Detective templates using my public Zeus URL as a host hint. Still no scrape, no bodies.

### `support_pack_from_turn`

Redacted support-pack markdown from debug JSON or last smoke artifact.

1. Build a redacted support pack from the last `smoke_test_agent` artifact. Strip secrets and response bodies.
2. Make a support pack from `./debug_turn.json` with ids/hops only.
3. I need something I can paste to support: redacted markdown from the last agent smoke, plus Detective templates if ids exist.

---

## Motions, hooks, semantic cache

### `recommend_motion`

Map a user job to a Zeus motion + typical verbs/modes. Does **not** generate a chat_request.

1. Recommend a Zeus motion for: "Help me book a hotel in Paris under $200."
2. User job: "Is this claim allowed under the policy?" Map to a motion and typical verbs. Do not generate a catalog.
3. "What happens if we drop the refund window to 24 hours?" Recommend simulate vs other motions.

### `suggest_hooks`

Middleware snippets (tenant pin, deny pipeline, `output_schema`, OCR). Not executed.

1. Suggest the `tenant_pin` hook snippet so the model cannot pick another bucket/scope.
2. Give me `deny_pipeline_direct` and `output_schema_allowlist` recipes. Do not install or run them.
3. How do I keep OCR text off the system prompt? Use `suggest_hooks` with `never_promote_ocr`.

### `semantic_cache_status`

Leave `enabled=false`; optional `GET /v2/agent_memory/status`. Direct/typeahead must not call `agent_memory`.

1. Confirm semantic cache should stay off. Optionally probe `/v2/agent_memory/status` on `:8080`.
2. Check cache status. Treat 404 as engine too old or flag off. Do not enable it.
3. Is it safe for typeahead to call `agent_memory`? Use `semantic_cache_status` and say no.

---

## Graduation handoffs

### `handoff_to_multi`

Graduate to multi-agent guidance after single-agent green (or `force`).

1. Hand off to multi-agent. If 5.1/5.2 are not green, block and tell me to smoke first.
2. Force the multi-agent handoff even if smokes are incomplete (`force=true`). Remind me jobs live in ZJA, not this MCP.
3. After first green, graduate me: orchestrator / workers / advisor — but do not start a ZJA job.

### `recommend_data_plane_mcp`

Hand off to a future scope-bound Data Plane MCP. Helper stays coach.

1. We are green on 5.1 and 5.2. Recommend the data-plane MCP handoff. Do not add Explore/Verify tools here.
2. What MCP should I use next for governed find/search after first green?
3. Explain why Helper will not expose `find`/`get` as tools and where that work goes.

### `emit_mcp_config`

Emit a safe-by-default MCP config fragment for a future data-plane server.

1. Emit a read-only Claude MCP config fragment for a future `zeus-data-plane` server.
2. Give me a Grok-host MCP config snippet for data-plane, still `read_only=true`.
3. Emit MCP config for host `claude`, server name `zeus-data-plane`, read-only. No secrets in the fragment.

---

## Quick index (all tools)

| Tool | Typical first prompt |
| --- | --- |
| `doctor` | Run doctor on the Helper MCP. |
| `start_project` | Start a single-agent travel first-app checklist. |
| `get_checklist` | Show the full first-app checklist. |
| `next_step` | What is the single current blocker? |
| `gap_report` | What is left before first green? |
| `mark_done` | Mark `5.1` done with a `req_id` only. |
| `mark_blocked` | Mark `2.3` blocked: scope not enabled. |
| `set_prereq` | Save `:8080` + bucket/scope flags, no secrets. |
| `validate_env` | Validate env without printing secrets. |
| `readiness_check` | Live platform gates on `:8080`. |
| `compat_check` | Probe version/healthz for 0.7 gates. |
| `bootstrap_scope` | Bootstrap `travel-sample` / `inventory`. |
| `list_catalog_modes` | List min chat_request modes. |
| `fetch_chat_request` | Fetch `analytics` template (template only). |
| `explain` | Explain `contract_hash`. |
| `explain_hash_boundary` | What is excluded from the hash? |
| `explain_req_id_policy` | One UUID per hop, never `base:1`. |
| `suggest_demo_prompts` | Advice-shaped smoke questions. |
| `scaffold_app` | Scaffold `./zeus_first_app`. |
| `use_sample` | Point at the travel sample. |
| `travel_golden_path` | Walk travel golden-path phases. |
| `write_env` | Write `.env.example` with no secrets. |
| `verify_local_setup` | Can we import Zeus Client? |
| `smoke_test_zeus` | Describe-scope smoke, no LLM. |
| `smoke_test_agent` | One `run_turn` to first green. |
| `diagnose_error` | Map 401 / `060010` / `base:1` to classes. |
| `recommend_surface` | Typeahead vs NL question vs pipeline. |
| `explain_verb` | Explain `find` / `pipeline` / `get`. |
| `lint_verb_args` | Lint a `find` JSON body; do not POST. |
| `suggest_verb_call` | Draft a legal `find` body. |
| `describe_scope` | Live types + field names only. |
| `lint_chat_request` | Lint on-disk catalog; never stamp. |
| `bind_contract` | Extract stamped hash only. |
| `catalog_diff` | Disk vs live bootstrap vs bound prefix. |
| `lint_runtime_config` | Lint `config.json` (`:8080`, cache off). |
| `lint_app_code` | Anti-example scan `main.py`. |
| `detective_links` | Detective URL templates only. |
| `support_pack_from_turn` | Redacted pack from last smoke. |
| `recommend_motion` | Map "book a hotel" to a motion. |
| `suggest_hooks` | Tenant-pin / deny-pipeline snippets. |
| `semantic_cache_status` | Leave cache off; optional status GET. |
| `handoff_to_multi` | Multi-agent graduation after green. |
| `recommend_data_plane_mcp` | Data-plane MCP handoff only. |
| `emit_mcp_config` | Read-only data-plane MCP fragment. |
| `helper_metrics` | Local time-to-green metrics. |
