# ZDM-1 — Beer-sample first-green (endpoint + dataset → website)

**Status:** In progress.  
**Epic:** [ZDM-1](https://kotenai.atlassian.net/browse/ZDM-1)  
**Product:** `zeus_dev_helper_mcp` (≥ 0.7.3 baseline)  
**Parent context:** Helper 0.7 quality ([`DESIGN-0.7.md`](DESIGN-0.7.md)); tool catalog [`TOOLS.md`](TOOLS.md).

## Goal utterance

> Zeus is at `$HOST:8080`, `beer-sample` is enabled. Make a sample website from that endpoint. Don’t require an LLM.

Target: first paint via Helper coach tools in minutes, without grepping the Zeus engine repo, cloning travel, or asking for an LLM key.

## Locked decisions

1. **BFF → Zeus uses sequential `find` then `get` (+ FTS fallback).** Never POST `pipeline` from the Direct/zero-LLM catalog UI. Aligns with frozen `pipeline_not_on_direct` / ErrorCode `060010`.
2. **“Direct” here means zero-LLM catalog UI** (same-origin BFF + page), coached as `rt.data.verb` / typeahead — not `pipeline` on Direct.
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
| Website + beer / named sample / no LLM | `sample=beer` | `use_sample` → Direct catalog UI |
| API / REST | `sample=api` | `scaffold_app(app_kind=api)` |

## Child tickets

| Ticket | Branch | Role |
| --- | --- | --- |
| [ZDM-5](https://kotenai.atlassian.net/browse/ZDM-5) | `zdm-5/application-user-prompts` | Application-user prompt samples + `first_green` + host-matrix note |
| [ZDM-4](https://kotenai.atlassian.net/browse/ZDM-4) | `zdm-4/diagnose-lab-errors` | `session_force_closed`, empty find→get, FTS `doc_key`-only |
| [ZDM-3](https://kotenai.atlassian.net/browse/ZDM-3) | `zdm-3/coach-utterance` | doctor → set_prereq (user URL) → start_project → next_step |
| [ZDM-6](https://kotenai.atlassian.net/browse/ZDM-6) | `zdm-6/beer-direct-ui` | Beer Direct UI template (find→get, no pipeline) |
| [ZDM-2](https://kotenai.atlassian.net/browse/ZDM-2) | `zdm-2/recommend-surface-direct` | website + sample + no LLM → Direct, not travel agent |

## Non-goals

- TravelPlan LLM loop changes  
- Multi-language scaffolds  
- Integrating Zeus into arbitrary existing apps  
- Data-plane MCP / Hub admin / ZJA  
- Inventing `contract_hash`  
- Requiring Hub `:9091` from the app path  

## Success bar

Agent stays on Helper tools. Browser search `ipa` / style chip returns rows with `req_id`. NL-ish “fruit” maps or FTS-falls-back without raw `STEP_FAILED`. No Zeus repo grep, no travel clone, no LLM key required.
