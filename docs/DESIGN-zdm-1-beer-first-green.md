# ZDM-1 — Beer-sample first-green (endpoint + dataset → website)

**Status:** In progress.  
**Epic:** [ZDM-1](https://kotenai.atlassian.net/browse/ZDM-1)  
**Product:** `zeus_dev_helper_mcp` (≥ 0.7.3 baseline)  
**Parent context:** Helper 0.7 quality ([`DESIGN-0.7.md`](DESIGN-0.7.md)); tool catalog [`TOOLS.md`](TOOLS.md).

## Goal utterance

> Zeus is at `$HOST:8080`, `beer-sample` is enabled. Make a sample website from that endpoint. Don’t require an LLM.

Target: first paint via Helper coach tools in minutes, without grepping the Zeus engine repo or cloning travel. Search in the written app is a client turn, so an LLM key is required.

## Locked decisions

1. **BFF search follows `demo_travel_sample`.** `use_sample(sample=beer)` writes a FastAPI BFF that calls `rt.agent.run_turn` and omits `chat_request`, so `catalog.load_for_turn` merges the live SCOPE BRIEF and MINI-SCHEMA. The raw question is the turn message. The BFF does not build a pipeline body and does not call `rt.data.verb`. `rt.data.verb("pipeline")` stays rejected (ErrorCode `060010`). Cards come from the turn's tool results. `client_floor` is `client-floor-6.1` on `kotenai-zeus-client>=2.4.0,<2.5`. An older pipeline BFF is rewritten on the next `use_sample(sample=beer)`. `plan_beer_query` stays for tests and diagnosis and is not inlined.
2. **Catalog UI, LLM required for search.** Same-origin BFF + static page. Do not clone `demo_travel_sample`. The key is required even when the user said not to use an LLM. Checklist **1.2** stays open until the Helper process has `LLM_API_KEY`, `XAI_API_KEY`, or `OPENAI_API_KEY` (`validate_env` errors; `has_llm_key=true` does not count). Checklist **3.2** stays open until `verify_local_setup` sees that variable set in the app `.env` and `config.json` `llm.api_key_env` is still the name. Do not paste the secret into `api_key_env`. Do not switch the BFF to bare Direct verbs.
3. **Beer sample delivery (v1):** template written by `use_sample(sample=beer)` inside Helper (scaffold-style). Optional later: public `demo_beer_sample` clone (travel pattern).
4. **Stacked branches** (one per ticket):

```text
main
  └─ zdm-1/beer-first-green          (this note)
       └─ zdm-5/application-user-prompts
            └─ zdm-4/diagnose-lab-errors
                 └─ zdm-3/coach-utterance
                      └─ zdm-6/beer-direct-ui
                           └─ zdm-2/recommend-surface-direct
```

## Bootstrap tracks (after epic)

| Intent | `start_project` | On disk |
| --- | --- | --- |
| UI travel (default when unspecified) | `sample=travel` | `use_sample` → `demo_travel_sample` (LLM) |
| Website + beer-sample | `sample=beer` | `use_sample` → `demo_beer_sample` (`run_turn`, `chat_request` omitted, LLM key) |
| API / REST | `sample=api` | `scaffold_app(app_kind=api)` |

## Child tickets

| Ticket | Branch | Role |
| --- | --- | --- |
| [ZDM-5](https://kotenai.atlassian.net/browse/ZDM-5) | `zdm-5/application-user-prompts` | Application-user prompt samples + `first_green` + host-matrix note |
| [ZDM-4](https://kotenai.atlassian.net/browse/ZDM-4) | `zdm-4/diagnose-lab-errors` | `session_force_closed`, empty find→get, FTS `doc_key`-only |
| [ZDM-3](https://kotenai.atlassian.net/browse/ZDM-3) | `zdm-3/coach-utterance` | doctor → set_prereq (user URL) → start_project → next_step |
| [ZDM-6](https://kotenai.atlassian.net/browse/ZDM-6) | `zdm-6/beer-direct-ui` | Beer catalog UI template (now `run_turn`; the ticket first shipped Direct find/search then get) |
| [ZDM-2](https://kotenai.atlassian.net/browse/ZDM-2) | `zdm-2/recommend-surface-direct` | website + beer-sample → beer catalog UI, not a travel clone |

## Non-goals

- TravelPlan LLM loop changes  
- Multi-language scaffolds  
- Integrating Zeus into arbitrary existing apps  
- Data-plane MCP / Hub admin / ZJA  
- Inventing `contract_hash`  
- Requiring Hub `:9091` from the app path  

## Success bar

Agent stays on Helper tools. Browser search sends the question through `run_turn` and shows beer cards from the turn. No Zeus repo grep, no travel clone. An LLM key is in the Helper process and in the app `.env`, and `llm.api_key_env` is the variable name. The BFF does not build a pipeline body.
