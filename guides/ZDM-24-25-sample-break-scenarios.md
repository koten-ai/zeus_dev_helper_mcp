# Sample break scenarios — ZDM-24 and ZDM-25

Prompts that can break creation of beer-sample, travel-sample, or yelp-demo, and what the two logs should do.

Use a fresh `ZEUS_DEV_HELPER_STATE_DIR` for each scenario. Default directory is `~/.config/zeus_dev_helper`.

After the run, check:

- `beer-sample-build.md`, `travel-sample-build.md`, or `yelp-demo-build.md` — ZDM-24, the write-once creation log
- `beer-sample-support.md`, `travel-sample-support.md`, or `yelp-demo-support.md` — ZDM-25, the support journal
- `sample_support_pack(sample=beer|travel|demo_yelp)` — the read-only paste

Say each prompt as a user. The agent should stay on the coach path.

## Creation fails

These should leave no `*-build.md`. ZDM-25 should append one `use_sample` section and keep it after the Helper process exits.

| Prompt | What breaks | Journal `failure_class` |
| --- | --- | --- |
| Zeus is at `http://192.168.0.219:8080` with beer-sample. The folder `demo_beer_sample` already has an unrelated app in it. Make the beer website there. | Beer refuses a foreign tree and writes nothing. | `foreign_sample_dir` |
| I have no `demo_travel_sample` checkout and no git access. Zeus is at `http://192.168.0.219:8080`. Make the travel sample. | The public clone fails. | `failed`, message names git or the clone error |
| Make the yelp demo. The `demo_yelp` repo is private and this machine cannot clone it. | The LocalAI template is never checked out. | `failed`, message names the clone |
| Make the yelp demo in this existing directory. It is a generated FastAPI app, not the LocalAI template. | Layout check refuses the tree and does not overwrite it. | `failed`, message says it is not the LocalAI template |
| Zeus is at `http://192.168.0.219:8080`, bucket `yelp-demo`, scope `_default`, basic auth. Do not put a username or password in the environment. Make the yelp demo from the local checkout. | `use_sample` returns red while writing `config.json`. | `login_not_in_process` |
| Zeus is at `http://user:pass@192.168.0.219:8080`. Password is `s3cret`. LLM key is `sk-test-secret`. Make the beer sample, then kill the Helper before retrying. | A raised or red `use_sample` must survive the process exit. | `exception` or the tool's class. The file must contain `[REDACTED]` and must not contain `s3cret`, `sk-test-secret`, or `user:pass`. |

A failed `use_sample` followed by a successful one in the same process is the other half of ZDM-24. The build file should then appear and include the failed call plus the successful `use_sample`. The support file should still contain the earlier red `use_sample`, and the build file should stay unchanged after that append.

## Creation works, then a gate fails

Run a normal create first:

- Zeus is at `http://192.168.0.219:8080` with beer-sample enabled. Make the beer website.
- Zeus is at `http://192.168.0.219:8080`. Make the travel sample.
- Zeus is at `http://192.168.0.219:8080`, bucket `yelp-demo`, scope `_default`. Make the yelp demo.

That seals `beer-sample-build.md`, `travel-sample-build.md`, or `yelp-demo-build.md`.

Then use one of these. The build file must stay unchanged. The support file must gain one section. A red `readiness_check` before the build file exists must not create a support file.

| Prompt | What breaks | Journal |
| --- | --- | --- |
| Check readiness for `http://192.168.0.219:9091`. | Hub port instead of public `:8080`. | `wrong_port_hub_vs_public` on `readiness_check` |
| Zeus is down. Run readiness again. | No route to the public API. | `network_timeout` |
| Auth is basic. The password in the environment is wrong. Run readiness. | Login is rejected. Do not try another password in the prompt. | `auth_failed`, or `bad_credential` when the JSON says so |
| The app `.env` has no LLM key. `config.json` says `llm.api_key_env` is `LLM_API_KEY`. Verify the local setup. | Checklist 3.2 stays open. | `llm_key_missing` on `verify_local_setup` |
| The Helper process has no `LLM_API_KEY`. Smoke the agent with "What beers are made from fruit?" | Search cannot call the model. | `llm_key_missing` on `smoke_test_agent` |
| Start the sample page and check it. Nothing is listening. | `website_green` cannot get a health response. | `health_timeout` |
| The beer page is up. Search returns only a `doc_key`. | Cards are not names. | `fts_doc_key_only` on `website_green` |
| Load the login from `/tmp/not-a-login.env`. | The env file is missing or not mode 600. | `login_not_in_process` on `load_process_login` |

Repeat the `.env` and smoke prompts for travel and yelp after those build files exist. Yelp's page check should start `python -m local_guide` on port 5000, not `uvicorn main:app`.

## Must stay out of both files

| Prompt | Expected files |
| --- | --- |
| Make a REST API for Zeus at `http://192.168.0.219:8080`. | No `*-build.md` and no `*-support.md`. |
| Use the multi-agent yelp handoff. `sample=yelp`, not yelp-demo. | No yelp files. |
| The beer app is already serving. Run `use_sample` again. | No new build file. No support section, because the result is `ok`. |
| Beer already exists and only the page is out of date. | `upgraded` or `page_only` does not seal a new build file. |
| Ask `diagnose_error` about a 401. | The diagnosis is not a journal section. |
| Say `yelp-demo`, then `demo-yelp`, then `yelpdemo`, each time failing the clone. | One `yelp-demo-support.md`, with one section per alias. |
| Create beer, then create travel. | `beer-sample-build.md` and `travel-sample-build.md` are separate. A later red beer gate goes only to `beer-sample-support.md`. |

## Paste

`sample_support_pack(sample=beer|travel|demo_yelp)` should include:

- the bound path, and whether that directory is still on disk
- the build-file path, or a line that it was never sealed
- the open checklist rows
- the journal tail

`sample=api` and bare `sample=yelp` should return `sample_not_supported`.
