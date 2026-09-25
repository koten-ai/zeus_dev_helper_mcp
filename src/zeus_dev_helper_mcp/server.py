"""Developer Helper MCP server — first-app coach (ZDH)."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from functools import wraps
from typing import Annotated, Any

from zeus_dev_helper_mcp import __version__
from zeus_dev_helper_mcp.bootstrap import bootstrap_scope as bootstrap_scope_impl
from zeus_dev_helper_mcp.cache import (
    semantic_cache_status as semantic_cache_status_impl,
)
from zeus_dev_helper_mcp.catalog import (
    CatalogError,
    list_modes,
    resolve_local_repo_hint,
)
from zeus_dev_helper_mcp.catalog import (
    fetch_chat_request as fetch_catalog_template,
)
from zeus_dev_helper_mcp.checklist import (
    load_checklist,
    set_item_status,
)
from zeus_dev_helper_mcp.clarify import (
    HAS_ELICIT as _HAS_ELICIT,
)
from zeus_dev_helper_mcp.clarify import (
    UNASKED,
    interpret_gate,
    persist_gate,
)
from zeus_dev_helper_mcp.compat import compat_check as compat_check_impl
from zeus_dev_helper_mcp.config import HelperConfig, reload_config
from zeus_dev_helper_mcp.config_lint import (
    lint_app as lint_app_impl,
)
from zeus_dev_helper_mcp.config_lint import (
    lint_app_code as lint_app_code_impl,
)
from zeus_dev_helper_mcp.config_lint import (
    lint_runtime_config as lint_runtime_config_impl,
)
from zeus_dev_helper_mcp.contract import (
    bind_contract as bind_contract_impl,
)
from zeus_dev_helper_mcp.contract import (
    catalog_diff as catalog_diff_impl,
)
from zeus_dev_helper_mcp.contract import (
    explain_hash_boundary as explain_hash_boundary_impl,
)
from zeus_dev_helper_mcp.contract import (
    lint_chat_request as lint_chat_request_impl,
)
from zeus_dev_helper_mcp.diagnose import diagnose_error as diagnose_error_impl
from zeus_dev_helper_mcp.docs_links import docs_url
from zeus_dev_helper_mcp.envelope import (
    as_envelope,
    is_execution_failure,
    raise_tool_error,
)
from zeus_dev_helper_mcp.error_log import log_tool_exception, log_tool_failure
from zeus_dev_helper_mcp.explain import explain_topic
from zeus_dev_helper_mcp.handoff import (
    emit_mcp_config as emit_mcp_config_impl,
)
from zeus_dev_helper_mcp.handoff import (
    handoff_to_multi as handoff_to_multi_impl,
)
from zeus_dev_helper_mcp.handoff import (
    metrics_summary as metrics_summary_impl,
)
from zeus_dev_helper_mcp.handoff import (
    recommend_data_plane_mcp as recommend_data_plane_impl,
)
from zeus_dev_helper_mcp.handoff import (
    record_metric,
)
from zeus_dev_helper_mcp.hooks import suggest_hooks as suggest_hooks_impl
from zeus_dev_helper_mcp.mcp_compat import (
    make_fastmcp,
    make_tool_annotations,
    register_tool,
)
from zeus_dev_helper_mcp.motion import recommend_motion as recommend_motion_impl
from zeus_dev_helper_mcp.prereqs import load_prereqs, public_prereqs, save_prereqs
from zeus_dev_helper_mcp.prompts import register_prompts
from zeus_dev_helper_mcp.readiness import run_readiness_check
from zeus_dev_helper_mcp.resources import register_resources
from zeus_dev_helper_mcp.scaffold import (
    scaffold_app as scaffold_app_impl,
)
from zeus_dev_helper_mcp.scaffold import (
    use_sample as use_sample_impl,
)
from zeus_dev_helper_mcp.scaffold import (
    verify_local_setup as verify_local_setup_impl,
)
from zeus_dev_helper_mcp.scaffold import (
    write_env_example,
)
from zeus_dev_helper_mcp.smoke import smoke_test_agent as smoke_agent_impl
from zeus_dev_helper_mcp.smoke import smoke_test_zeus as smoke_zeus_impl
from zeus_dev_helper_mcp.support import (
    detective_links as detective_links_impl,
)
from zeus_dev_helper_mcp.support import (
    explain_req_id_policy as explain_req_id_policy_impl,
)
from zeus_dev_helper_mcp.support import (
    support_pack_from_turn as support_pack_from_turn_impl,
)
from zeus_dev_helper_mcp.surface import recommend_surface as recommend_surface_impl
from zeus_dev_helper_mcp.toolsets import TOOL_REGISTRY, parse_toolsets
from zeus_dev_helper_mcp.travel import travel_golden_path as travel_golden_path_impl
from zeus_dev_helper_mcp.verbs import (
    describe_scope as describe_scope_impl,
)
from zeus_dev_helper_mcp.verbs import (
    explain_verb as explain_verb_impl,
)
from zeus_dev_helper_mcp.verbs import (
    lint_verb_args as lint_verb_args_impl,
)
from zeus_dev_helper_mcp.verbs import (
    suggest_verb_call as suggest_verb_call_impl,
)
from zeus_dev_helper_mcp.walkthrough import build_gap_report, enriched_next_step

INSTRUCTIONS = (
    "Developer Helper MCP coaches a first Zeus Client app to green "
    "(session_id / req_id on public :8080). "
    "Human docs for first green: https://docs.koten.ai/zeus-client "
    "(live published Zeus Client hub — For AI agents, Start, Using Zeus Client, Errors, "
    "Dev Helper MCP). Prefer that hub + Helper tools + live :8080; do not clone koten_docs "
    "or grep the Zeus engine for first green. "
    "Order: doctor → (if user gave URL/sample) set_prereq with those values → "
    "start_project → next_step, then only the recommended tool. "
    "If the user named a Zeus URL or sample (e.g. beer-sample), call set_prereq with that "
    "zeus_url/bucket/scope — do not keep localhost defaults and do not grep the Zeus source tree "
    "or hand-roll curl for first green; use readiness_check / smoke_test_zeus / zeus-helper://. "
    "If the user did not name a Zeus URL, leave zeus_url empty and wait for the form. "
    "Do not copy the host ZEUS_URL into set_prereq. "
    "Call recommend_surface before choosing Travel LLM vs Direct UI vs FastAPI. "
    "If has_llm_key=false, do not offer smoke_test_agent / travel as the only path. "
    "Hard constraints: public API is :8080 not Hub :9091; never invent contract_hash; "
    "fetch_chat_request / catalog resources are TEMPLATE ONLY (prefer a live Zeus stamp); "
    "no secrets in results or checklist evidence; semantic cache stays off. "
    "scaffold_app / smoke_test_agent emit ZeusRuntime + run_turn, not V1 ZeusClient / run_agent. "
    "TravelPlan / demo_travel_sample is the agent-plane (LLM chat UI) example; "
    "demo_beer_sample is the beer-sample catalog UI. Its search follows travel: "
    "rt.agent.run_turn with chat_request omitted so catalog.load_for_turn merges "
    "SCOPE BRIEF + MINI-SCHEMA. An LLM key is required. The BFF does not build a pipeline body — "
    "https://docs.koten.ai/zeus-client/using-zeus-client. "
    "Bootstrap default is UI: use_sample clones public demo_travel_sample when missing "
    "and sets DEMO_TRAVEL_SAMPLE_DIR (optional project_name for the clone directory). "
    "Beer / website: start_project(sample=beer) → use_sample(sample=beer) writes "
    "demo_beer_sample (same run_turn search as travel; do not clone demo_travel_sample). "
    "Yelp demo: utterances yelp-demo / demo_yelp use start_project(sample=demo_yelp) → "
    "use_sample(sample=demo_yelp), which clones https://github.com/koten-ai/demo_yelp when "
    "missing and sets DEMO_YELP_SAMPLE_DIR. set_prereq bucket yelp-demo scope _default. "
    "Do not clone demo_travel_sample on that path. Bare sample=yelp stays the multi-agent handoff. "
    "API-only: start_project(sample=api) → scaffold_app(app_kind=api, coding_language=python) "
    "(FastAPI POST /turn). Other coding languages are not scaffolded yet. "
    "Never pass username/password/token into MCP tools — env + set_prereq presence flags only. "
    "Knowledge is resources under zeus-helper:// (checklist, glossary, verbs, policies, catalog modes). "
    "Walkthroughs are prompts: first_green, smoke_question, support_pack. "
    "After 5.1+5.2 green: data-plane and multi-agent are handoffs only."
)


def _cfg() -> HelperConfig:
    return reload_config()


def _apply_gate(outcome: Any, *, kind: str) -> tuple[Any, dict[str, Any] | None]:
    """Persist a confirmed URL or auth mode. Return an envelope when the tool must stop."""
    gate = interpret_gate(outcome)
    if gate.direct:
        return gate, None
    if (
        gate.save_url
        or gate.save_auth
        or gate.has_username is not None
        or gate.has_password is not None
        or gate.has_bearer is not None
    ):
        persist_gate(gate)
    if gate.proceed:
        return gate, None
    out: dict[str, Any] = {
        "ok": False,
        "failure_class": None,
        "next_action": gate.next_action,
    }
    if kind == "start":
        out["started"] = False
    elif kind == "prereq":
        out["saved"] = False
    else:
        out["written"] = False
    return gate, out


DOCTOR_DETAILS = ("health", "env", "compat", "cache", "all")


def _url_routing_view(cfg: HelperConfig) -> dict[str, Any]:
    """Compare MCP host ZEUS_URL, set_prereq stored URL, and effective config (ZDM-3)."""
    stored = (load_prereqs(cfg).get("zeus_url") or "").strip() or None
    env_url = (os.environ.get("ZEUS_URL") or "").strip() or None
    effective = (cfg.zeus_url or "").strip() or None

    def _norm(u: str | None) -> str | None:
        return u.rstrip("/") if u else None

    issues: list[dict[str, str]] = []
    if stored and env_url and _norm(stored) != _norm(env_url):
        issues.append(
            {
                "code": "env_url_differs_from_prereq",
                "message": (
                    f"MCP host ZEUS_URL={env_url} differs from set_prereq "
                    f"zeus_url={stored}; effective uses set_prereq (persisted wins)."
                ),
                "severity": "set_prereq",
                "env": "ZEUS_URL",
            }
        )
    return {
        "stored_zeus_url": stored,
        "env_zeus_url": env_url,
        "effective_zeus_url": effective,
        "zeus_url_confirmed": bool(stored),
        "issues": issues,
    }


def _doctor_health() -> dict[str, Any]:
    cfg = _cfg()
    catalog_ok = False
    catalog_error = None
    modes_count = None
    try:
        modes = list_modes(cfg)
        catalog_ok = True
        modes_count = len(modes.get("modes") or [])
    except Exception as e:  # noqa: BLE001 — surface as doctor field
        catalog_error = str(e)

    sibling = resolve_local_repo_hint()
    routing = _url_routing_view(cfg)
    next_action = (
        "set_prereq with the user’s Zeus URL/sample (if named), then start_project → next_step"
    )
    return {
        "ok": True,
        "version": __version__,
        "config": cfg.public_view(),
        "url_routing": routing,
        "catalog": {
            "reachable": catalog_ok,
            "modes_count": modes_count,
            "error": catalog_error,
            "hint_local_dir": sibling or None,
            "env": (
                "ZEUS_CHAT_REQUEST_DIR auto-set from local/clone of public "
                "zeus_chat_request; GITHUB_TOKEN for private fetch fallback"
            ),
            "local_dir": str(cfg.chat_request_dir) if cfg.chat_request_dir else None,
        },
        "docs": {
            "zeus_client_hub": docs_url("zeus-client"),
            "for_ai_agents": (
                docs_url("zeus-client/for-ai-agents.md")
            ),
            "using_zeus_client": (
                docs_url("zeus-client/using-zeus-client.md")
            ),
            "dev_helper_mcp": docs_url("zeus-client/dev-helper-mcp.md"),
            "zeus_chat_request": f"https://github.com/{cfg.chat_request_repo}",
        },
        "next_action": next_action,
    }


def doctor(detail: str = "health") -> dict[str, Any]:
    """Health / doctor. detail: health | env | compat | cache | all.

    env/compat/cache fold validate_env, compat_check, and semantic_cache_status
    (those names stay on the lint toolset).

    If the user already gave a Zeus URL or sample name, next call set_prereq with
    those values (not Helper localhost defaults), then start_project / next_step.
    Do not grep the Zeus engine tree for first green.
    """
    key = (detail or "health").strip().lower()
    if key not in DOCTOR_DETAILS:
        return {
            "ok": False,
            "detail": detail,
            "known_details": list(DOCTOR_DETAILS),
            "next_action": "Pass detail=health|env|compat|cache|all",
        }
    health = _doctor_health()
    if key == "health":
        health["detail"] = "health"
        return health
    if key == "env":
        out = validate_env()
        out["detail"] = "env"
        return out
    if key == "compat":
        out = compat_check()
        out["detail"] = "compat"
        return out
    if key == "cache":
        out = semantic_cache_status()
        out["detail"] = "cache"
        return out
    env = validate_env()
    compat = compat_check()
    cache = semantic_cache_status()
    return {
        "ok": bool(health.get("ok")) and bool(env.get("ok")),
        "detail": "all",
        "health": health,
        "env": env,
        "compat": compat,
        "cache": cache,
        "next_action": env.get("next_action") or "next_step",
    }


def start_project(
    goal: str = "single-agent",
    sample: str = "travel",
    force_multi: bool = False,
) -> dict[str, Any]:
    """Start or reset first-app coaching checklist (single-agent default).

    sample:
      - travel (default) — UI path via demo_travel_sample / use_sample
      - beer — beer-sample catalog UI; search is run_turn + MINI-SCHEMA (use_sample sample=beer)
      - demo_yelp — yelp-demo UI; use_sample clones demo_yelp (aliases yelp-demo, demo-yelp)
      - api — API-only FastAPI scaffold (scaffold_app app_kind=api)
      - yelp / multi — gated until single-agent smokes green unless force_multi.
        Not the yelp demo. Utterances yelp-demo / demo_yelp use sample=demo_yelp.

    Multi-agent goals (goal=multi or sample=yelp) are gated until single-agent
    smokes are green, unless force_multi=true (ZDH-11).

    When no Zeus URL is stored, the MCP call asks for the public :8080 URL
    before the checklist starts. Leave zeus_url empty when the user did not
    name one. Do not copy the host ZEUS_URL. Do not pass a password.
    """
    return _start_project_body(goal=goal, sample=sample, force_multi=force_multi)


def _start_project_body(
    goal: str = "single-agent",
    sample: str = "travel",
    force_multi: bool = False,
    gate_outcome: Any = UNASKED,
) -> dict[str, Any]:
    _gate, blocked = _apply_gate(gate_outcome, kind="start")
    if blocked is not None:
        return blocked
    cfg = _cfg()
    goal_l = (goal or "single-agent").lower().strip()
    sample_raw = (sample or "travel").lower().strip()
    sample_l = sample_raw
    if sample_l in ("ui", "demo_travel", "demo_travel_sample", "travel_sample"):
        sample_l = "travel"
        sample = "travel"
    from zeus_dev_helper_mcp.beer import is_beer_sample, prereqs_prefer_beer_direct
    from zeus_dev_helper_mcp.prereqs import load_prereqs
    from zeus_dev_helper_mcp.yelp import is_yelp_demo_sample

    if is_beer_sample(sample_l):
        sample_l = "beer"
        sample = "beer"
    if is_yelp_demo_sample(sample_l):
        sample_l = "demo_yelp"
        sample = "demo_yelp"
    if sample_l in ("rest", "api_only", "api-only"):
        sample_l = "api"
        sample = "api"
    # Named beer bucket + has_llm_key=false wins over default travel (ZDM-2).
    rerouted_from_travel = False
    if sample_l == "travel":
        prefs = load_prereqs(cfg)
        if prereqs_prefer_beer_direct(prefs) and prefs.get("has_llm_key") is False:
            sample_l = "beer"
            sample = "beer"
            rerouted_from_travel = True
    wants_multi = goal_l in ("multi", "multi-agent", "multi_agent") or sample_l in (
        "yelp",
        "multi",
    )
    if wants_multi:
        handoff = handoff_to_multi_impl(cfg, force=force_multi)
        if handoff.get("blocked"):
            return {
                "started": False,
                "blocked": True,
                "goal": goal,
                "sample": sample,
                "handoff_to_multi": handoff,
                "next_action": handoff.get("next_action"),
                "read_first": [
                    docs_url("zeus-client/for-ai-agents.md"),
                    docs_url("zeus-client/using-zeus-client.md"),
                ],
            }

    data = load_checklist(cfg)
    data["project"] = f"{goal}:{sample}"
    data["meta"] = {"goal": goal, "sample": sample, "force_multi": force_multi}
    from zeus_dev_helper_mcp.checklist import save_checklist

    save_checklist(cfg, data)
    try:
        record_metric(cfg, "start_project")
    except Exception:  # noqa: BLE001, S110
        pass
    nxt = enriched_next_step(cfg)
    out: dict[str, Any] = {
        "started": True,
        "goal": goal,
        "sample": sample,
        "checklist_path": str(cfg.state_dir / "checklist.json"),
        "next_step": nxt,
        "read_first": [
            docs_url("zeus-client/for-ai-agents.md"),
            docs_url("zeus-client/using-zeus-client.md"),
        ],
        "semantic_cache": {
            "enabled": False,
            "note": (
                "Leave session.semantic_cache.enabled=false. start_project never turns it on. "
                "Direct/typeahead must not call agent_memory."
            ),
        },
        "secrets_note": (
            "If the user gave Zeus username/password in chat, put them in env "
            "(ZEUS_USERNAME / ZEUS_PASSWORD) or gitignored .env; call set_prereq with "
            "zeus_url + has_username/has_password flags only — never secret values."
        ),
    }
    if sample_l == "api":
        out["track"] = "api"
        out["app_kind"] = "api"
        out["coding_language"] = "python"
        out["note"] = (
            "API-only track: after prereqs/readiness, scaffold_app(app_kind=api, "
            "coding_language=python). Default UI track is sample=travel / use_sample."
        )
        out["recommended_tools"] = [
            "set_prereq",
            "readiness_check",
            "scaffold_app",
            "bind_contract",
            "smoke_test_zeus",
            "smoke_test_agent",
        ]
    elif sample_l == "beer":
        out["track"] = "ui-direct"
        out["app_kind"] = "ui"
        out["llm_required"] = False
        out["note"] = (
            "Beer catalog UI: after prereqs/readiness, use_sample(sample=beer) writes "
            "demo_beer_sample. Search is rt.agent.run_turn with chat_request omitted so "
            "catalog.load_for_turn merges SCOPE BRIEF + MINI-SCHEMA (same as travel). "
            "Put LLM_API_KEY in .env. The BFF does not build a pipeline body."
        )
        if rerouted_from_travel:
            out["note"] = (
                "Rerouted from default travel: prereqs have beer-sample + has_llm_key=false. "
                + out["note"]
            )
            out["rerouted_from"] = "travel"
        out["recommended_tools"] = [
            "set_prereq",
            "readiness_check",
            "use_sample",
            "smoke_test_zeus",
            "recommend_surface",
        ]
    elif sample_l == "demo_yelp":
        out["track"] = "ui"
        out["app_kind"] = "ui"
        out["note"] = (
            "Yelp demo UI: after prereqs/readiness, use_sample(sample=demo_yelp) "
            "locates or clones demo_yelp and sets DEMO_YELP_SAMPLE_DIR. "
            "set_prereq bucket yelp-demo scope _default. "
            "Do not clone demo_travel_sample. Do not pass sample=yelp "
            "(that name is the multi-agent handoff)."
        )
        out["recommended_tools"] = [
            "set_prereq",
            "readiness_check",
            "use_sample",
            "smoke_test_zeus",
            "smoke_test_agent",
        ]
    elif wants_multi:
        out["track"] = "multi-agent"
        out["handoff_to_multi"] = handoff_to_multi_impl(cfg, force=True)
        out["note"] = "Multi track is graduation guidance only — jobs live in ZJA."
    else:
        out["track"] = "ui"
        out["app_kind"] = "ui"
        out["note"] = (
            "UI track (default): use_sample / demo_travel_sample for the full app look."
        )
        prefs = load_prereqs(cfg)
        if prefs.get("has_llm_key") is False:
            out["note"] += (
                " has_llm_key=false: prefer recommend_surface(needs_llm=false) / Direct; "
                "do not treat smoke_test_agent as required. If bucket is beer-sample, "
                "use start_project(sample=beer) / use_sample(sample=beer)."
            )
            out["llm_required"] = False
    return out


def get_checklist() -> dict[str, Any]:
    """Return the current first-app checklist state."""
    return load_checklist(_cfg())


def next_step() -> dict[str, Any]:
    """Return the single current checklist blocker + recommended Helper tools (coach).

    Call only the recommended tool next. If the user named a URL/bucket and prereqs
    are unset, recommend set_prereq first. Prefer zeus-helper:// + readiness_check /
    smoke_test_zeus over hand-rolled curl.
    """
    return enriched_next_step(_cfg())


def gap_report() -> dict[str, Any]:
    """What's left for single-agent / production-ish path (phases 4–7 focus)."""
    return build_gap_report(_cfg())


def mark_done(item_id: str, evidence: str = "") -> dict[str, Any]:
    """Mark a checklist item done (optional evidence string, no secrets)."""
    data = set_item_status(_cfg(), item_id, "done", evidence=evidence or None)
    return {"updated": item_id, "status": "done", "next_step": enriched_next_step(_cfg()), "checklist": data}


def mark_blocked(item_id: str, reason: str = "") -> dict[str, Any]:
    """Mark a checklist item blocked with a reason."""
    data = set_item_status(_cfg(), item_id, "blocked", evidence=reason or None)
    return {"updated": item_id, "status": "blocked", "next_step": enriched_next_step(_cfg()), "checklist": data}


def validate_env() -> dict[str, Any]:
    """Validate Helper env + stored prereqs shape (presence only — no secret values)."""
    cfg = _cfg()
    issues: list[dict[str, str]] = []
    if not cfg.zeus_url:
        issues.append(
            {
                "field": "ZEUS_URL",
                "level": "warn",
                "message": "Not set — required for readiness_check / smoke.",
            }
        )
    elif ":9091" in cfg.zeus_url or cfg.zeus_url.rstrip("/").endswith(":9091"):
        issues.append(
            {
                "field": "ZEUS_URL",
                "level": "error",
                "failure_class": "wrong_port_hub_vs_public",
                "message": "Looks like Hub :9091 — app path must use public :8080.",
            }
        )
    if not cfg.has_llm_key:
        issues.append(
            {
                "field": "LLM_API_KEY",
                "level": "warn",
                "failure_class": "llm_key_missing",
                "message": "No LLM key env detected — needed for smoke_test_agent.",
            }
        )
    if not cfg.default_bucket or not cfg.default_scope:
        issues.append(
            {
                "field": "ZEUS_BUCKET/ZEUS_SCOPE",
                "level": "warn",
                "message": "Bucket/scope not set — bootstrap/auth scope probes will skip.",
            }
        )
    catalog_note = None
    try:
        m = list_modes(cfg)
        catalog_note = f"OK — {len(m.get('modes') or [])} modes from zeus_chat_request"
    except CatalogError as e:
        catalog_note = f"catalog templates unavailable: {e.message}"
        issues.append(
            {
                "field": "zeus_chat_request",
                "level": "warn",
                "failure_class": e.failure_class,
                "message": e.message,
            }
        )
    except Exception as e:  # noqa: BLE001
        catalog_note = str(e)
        issues.append({"field": "zeus_chat_request", "level": "warn", "message": str(e)})

    ok = not any(i.get("level") == "error" for i in issues)
    return {
        "ok": ok,
        "config": cfg.public_view(),
        "prereqs": public_prereqs(cfg),
        "catalog_templates": catalog_note,
        "issues": issues,
        "docs": (
            docs_url("zeus-client/config-reference.md")
        ),
        "next_action": "Run readiness_check after ZEUS_URL is set",
    }


def set_prereq(
    zeus_url: str = "",
    auth_mode: str = "",
    bucket: str = "",
    scope: str = "",
    collection: str = "",
    mode: str = "",
    role: str = "",
    has_llm_key: bool | None = None,
    has_bearer: bool | None = None,
    has_username: bool | None = None,
    has_password: bool | None = None,
) -> dict[str, Any]:
    """Store non-secret prereqs for readiness (does not store password/token values).

    Put real secrets in environment variables (ZEUS_PASSWORD, ZEUS_BEARER_TOKEN, LLM_API_KEY).
    When the user named a Zeus URL or sample in chat, pass that zeus_url / bucket / scope here
    (not Helper localhost defaults). If the user did not name a URL, leave zeus_url empty
    and wait for the form. Do not copy the host ZEUS_URL. Persisted values override MCP
    host ZEUS_* env defaults so readiness/doctor hit the user's cluster (ZDM-3).
    Presence flags only for credentials and LLM key.
    """
    return _set_prereq_body(
        zeus_url=zeus_url,
        auth_mode=auth_mode,
        bucket=bucket,
        scope=scope,
        collection=collection,
        mode=mode,
        role=role,
        has_llm_key=has_llm_key,
        has_bearer=has_bearer,
        has_username=has_username,
        has_password=has_password,
    )


def _set_prereq_body(
    zeus_url: str = "",
    auth_mode: str = "",
    bucket: str = "",
    scope: str = "",
    collection: str = "",
    mode: str = "",
    role: str = "",
    has_llm_key: bool | None = None,
    has_bearer: bool | None = None,
    has_username: bool | None = None,
    has_password: bool | None = None,
    gate_outcome: Any = UNASKED,
) -> dict[str, Any]:
    gate, blocked = _apply_gate(gate_outcome, kind="prereq")
    if blocked is not None:
        return blocked
    if not gate.direct and gate.zeus_url and not (zeus_url or "").strip():
        zeus_url = gate.zeus_url
    cfg = _cfg()
    payload: dict[str, Any] = {}
    if zeus_url:
        payload["zeus_url"] = zeus_url.strip()
    if auth_mode:
        payload["auth_mode"] = auth_mode.strip()
    if bucket:
        payload["bucket"] = bucket.strip()
    if scope:
        payload["scope"] = scope.strip()
    if collection:
        payload["collection"] = collection.strip()
    if mode:
        payload["mode"] = mode.strip()
    if role:
        payload["role"] = role.strip()
    if has_llm_key is not None:
        payload["has_llm_key"] = has_llm_key
    if has_bearer is not None:
        payload["has_bearer"] = has_bearer
    if has_username is not None:
        payload["has_username"] = has_username
    if has_password is not None:
        payload["has_password"] = has_password

    stored = save_prereqs(cfg, payload)
    # Mirror non-secret routing into process env so tools that read ZEUS_* directly
    # and reload_config() agree. Persisted prereqs still win if the MCP host re-injects
    # a stale localhost ZEUS_URL (ZDM-3).
    env_map = {
        "zeus_url": "ZEUS_URL",
        "auth_mode": "ZEUS_AUTH_MODE",
        "bucket": "ZEUS_BUCKET",
        "scope": "ZEUS_SCOPE",
        "collection": "ZEUS_COLLECTION",
        "mode": "ZEUS_MODE",
        "role": "ZEUS_HELPER_ROLE",
    }
    for key, env_name in env_map.items():
        val = stored.get(key)
        if val is not None and str(val).strip() != "":
            os.environ[env_name] = str(val).strip()

    cfg = reload_config()
    return {
        "saved": True,
        "stored_public": stored,
        "effective_config": cfg.public_view(),
        "note": (
            "Secrets must remain in env vars — only presence flags are stored. "
            "Persisted zeus_url/bucket/scope override MCP host ZEUS_* defaults."
        ),
        "next_action": "validate_env → readiness_check",
    }


def readiness_check(update_checklist: bool = True) -> dict[str, Any]:
    """Live Zeus platform gates: healthz/readyz/version, auth, bootstrap, chat_request.

    Never returns secret values. Emits failure_class + next_action on red paths.
    """
    cfg = _cfg()
    return run_readiness_check(cfg, update_checklist=update_checklist)


def list_catalog_modes() -> dict[str, Any]:
    """List V2 min chat_request modes from zeus_chat_request (ZDH-14).

    When ZEUS_CHAT_REQUEST_DIR is unset, clones public zeus_chat_request and sets the env.
    """
    cfg = _cfg()
    try:
        return list_modes(cfg)
    except CatalogError as e:
        return {
            "error": e.message,
            "failure_class": e.failure_class,
            "next_action": (
                "Helper clones public https://github.com/koten-ai/zeus_chat_request "
                "when ZEUS_CHAT_REQUEST_DIR is unset; fix git/network or set "
                "ZEUS_CHAT_REQUEST_DIR / GITHUB_TOKEN and retry."
            ),
            "hint_local": resolve_local_repo_hint() or None,
        }


def fetch_chat_request(mode: str = "analytics", detail: str = "summary") -> dict[str, Any]:
    """Fetch a V2 min chat_request template by mode from zeus_chat_request.

    Prefer live Zeus stamp for production. detail: summary | full.
    When ZEUS_CHAT_REQUEST_DIR is unset, clones public zeus_chat_request and sets the env.
    """
    cfg = _cfg()
    try:
        return fetch_catalog_template(cfg, mode, detail=detail)
    except CatalogError as e:
        return {
            "error": e.message,
            "failure_class": e.failure_class,
            "mode": mode,
            "next_action": (
                "Helper clones public zeus_chat_request when ZEUS_CHAT_REQUEST_DIR "
                "is unset; fix git/network or set ZEUS_CHAT_REQUEST_DIR / GITHUB_TOKEN, "
                "then retry. Still stamp on Zeus for production."
            ),
            "docs": (
                docs_url("zeus-client/contracts-and-catalog.md")
            ),
        }


def explain(topic: str) -> dict[str, Any]:
    """Explain a Zeus/Client concept (glossary) with docs deep-link."""
    return explain_topic(_cfg(), topic)


def bootstrap_scope(
    bucket: str = "",
    scope: str = "",
    mode: str = "",
    detail: str = "summary",
    update_checklist: bool = True,
) -> dict[str, Any]:
    """Live GET /v1/ai/bootstrap/scope/{bucket}/{scope} + chat_request summary (P3)."""
    return bootstrap_scope_impl(
        _cfg(),
        bucket=bucket,
        scope=scope,
        mode=mode,
        detail=detail,
        update_checklist=update_checklist,
    )


def scaffold_app(
    target_dir: str,
    project_name: str = "zeus_first_app",
    force: bool = False,
    app_kind: str = "cli",
    coding_language: str = "python",
) -> dict[str, Any]:
    """Write a ZeusRuntime middle-man.

    app_kind=cli (default) or api (FastAPI POST /turn). coding_language=python only today.
    UI demos use use_sample / demo_travel_sample, not this tool.
    When no Zeus URL is stored, the MCP call asks before writing files.
    Do not pass a password.
    """
    return _scaffold_app_body(
        target_dir,
        project_name=project_name,
        force=force,
        app_kind=app_kind,
        coding_language=coding_language,
    )


def _scaffold_app_body(
    target_dir: str,
    project_name: str = "zeus_first_app",
    force: bool = False,
    app_kind: str = "cli",
    coding_language: str = "python",
    gate_outcome: Any = UNASKED,
) -> dict[str, Any]:
    _gate, blocked = _apply_gate(gate_outcome, kind="scaffold")
    if blocked is not None:
        return blocked
    return scaffold_app_impl(
        _cfg(),
        target_dir,
        project_name=project_name,
        force=force,
        app_kind=app_kind,
        coding_language=coding_language,
    )


def use_sample(
    sample: str = "travel",
    sample_dir: str = "",
    project_name: str = "",
    parent_dir: str = "",
    clone_if_missing: bool = True,
) -> dict[str, Any]:
    """UI sample: travel clone, beer catalog, or yelp demo clone.

    sample=travel — locate/clone demo_travel_sample; set DEMO_TRAVEL_SAMPLE_DIR.
    sample=beer — write demo_beer_sample catalog UI. Search is rt.agent.run_turn with chat_request omitted (catalog.load_for_turn merges MINI-SCHEMA). LLM key required. No pipeline body.
    sample=demo_yelp — locate/clone demo_yelp (aliases yelp-demo, demo-yelp); set DEMO_YELP_SAMPLE_DIR. Bare sample=yelp stays the multi-agent handoff.
    project_name = directory name (defaults: demo_travel_sample / demo_beer_sample / demo_yelp).
    Extra travel-only phases stay on travel_golden_path (travel toolset).
    When no Zeus URL is stored, the MCP call asks before writing or cloning.
    Do not pass a password.
    """
    return _use_sample_body(
        sample=sample,
        sample_dir=sample_dir,
        project_name=project_name,
        parent_dir=parent_dir,
        clone_if_missing=clone_if_missing,
    )


def _use_sample_body(
    sample: str = "travel",
    sample_dir: str = "",
    project_name: str = "",
    parent_dir: str = "",
    clone_if_missing: bool = True,
    gate_outcome: Any = UNASKED,
) -> dict[str, Any]:
    _gate, blocked = _apply_gate(gate_outcome, kind="sample")
    if blocked is not None:
        return blocked
    return use_sample_impl(
        _cfg(),
        sample=sample,
        sample_dir=sample_dir,
        project_name=project_name,
        parent_dir=parent_dir,
        clone_if_missing=clone_if_missing,
    )


def travel_golden_path(
    sample_dir: str = "",
    project_name: str = "",
    parent_dir: str = "",
    clone_if_missing: bool = True,
) -> dict[str, Any]:
    """ZDH-10: locate/clone public demo_travel_sample + golden path validation."""
    return travel_golden_path_impl(
        _cfg(),
        sample_dir=sample_dir,
        project_name=project_name,
        parent_dir=parent_dir,
        clone_if_missing=clone_if_missing,
    )


def write_env(target_dir: str) -> dict[str, Any]:
    """Write .env.example from prereqs (no secrets)."""
    return write_env_example(_cfg(), target_dir)


def verify_local_setup(target_dir: str = "") -> dict[str, Any]:
    """Check zeus_client import and optional scaffold files."""
    return verify_local_setup_impl(_cfg(), target_dir=target_dir)


def smoke_test_zeus(update_checklist: bool = True) -> dict[str, Any]:
    """Smoke Zeus without LLM: readiness + POST /v2/{bucket}/{scope}/describe."""
    return smoke_zeus_impl(_cfg(), update_checklist=update_checklist)


def smoke_test_agent(
    question: str = "In one short sentence, what data is available in this scope?",
    update_checklist: bool = True,
) -> dict[str, Any]:
    """One ZeusRuntime run_turn (requires kotenai-zeus-client>=2.3.0 + LLM key).

    If the client is missing and demo_travel_sample documents Docker install,
    returns guide-only docker compose next_action instead of only pip install.
    """
    return smoke_agent_impl(_cfg(), question=question, update_checklist=update_checklist)


def diagnose_error(
    status: str = "",
    body: str = "",
    message: str = "",
    req_id: str = "",
    session_id: str = "",
    zeus_url: str = "",
    error_code: str = "",
    error_class: str = "",
    chat_id: str = "",
    turn_id: str = "",
) -> dict[str, Any]:
    """Map error signals to failure_class + errors.md anchor (ZDH-7 / ZDH-19).

    Includes Detective URL templates when req_id/chat_id are present (folded
    detective_links). Does not scrape Hub.
    """
    return diagnose_error_impl(
        _cfg(),
        status=status,
        body=body,
        message=message,
        req_id=req_id,
        session_id=session_id,
        zeus_url=zeus_url,
        error_code=error_code,
        error_class=error_class,
        chat_id=chat_id,
        turn_id=turn_id,
    )


def recommend_surface(
    intent: str,
    qps: float = 0,
    needs_llm: bool | None = None,
) -> dict[str, Any]:
    """Pick Direct vs agent surface + Trace-Class (ZDH-18). Does not call Zeus."""
    return recommend_surface_impl(
        _cfg(),
        intent=intent,
        qps=qps if qps else None,
        needs_llm=needs_llm,
    )


def explain_verb(name: str) -> dict[str, Any]:
    """V2 verb encyclopedia: path class, demux, Direct vs pipeline (ZDH-18)."""
    return explain_verb_impl(_cfg(), name=name)


def lint_verb_args(
    verb: str,
    body: str = "{}",
    mini_schema: str = "",
) -> dict[str, Any]:
    """Lint a would-be V2 verb JSON body (MINI-SCHEMA / equality / pipeline). Does not POST."""
    return lint_verb_args_impl(
        _cfg(),
        verb=verb,
        body=body,
        mini_schema=mini_schema or None,
    )


def suggest_verb_call(goal: str, mini_schema: str = "") -> dict[str, Any]:
    """Draft a legal V2 verb JSON body from a goal. Guidance only — does not POST."""
    return suggest_verb_call_impl(
        _cfg(),
        goal=goal,
        mini_schema=mini_schema or None,
    )


def compat_check(zeus_url: str = "") -> dict[str, Any]:
    """Probe GET /version + /healthz on :8080 and evaluate static 0.7 feature gates (ZDH-21)."""
    return compat_check_impl(_cfg(), zeus_url=zeus_url)


def lint_chat_request(path: str = "", json_text: str = "") -> dict[str, Any]:
    """Lint a chat_request JSON (path or pasted). Read-only; never stamps (ZDH-22)."""
    return lint_chat_request_impl(_cfg(), path=path, json_text=json_text)


def bind_contract(
    path: str = "",
    json_text: str = "",
    bucket: str = "",
    scope: str = "",
    mode: str = "",
) -> dict[str, Any]:
    """Extract stamped contract.hash only. Refuse placeholders / compute_local (ZDH-22)."""
    return bind_contract_impl(
        _cfg(),
        path=path,
        json_text=json_text,
        bucket=bucket,
        scope=scope,
        mode=mode,
    )


def explain_hash_boundary() -> dict[str, Any]:
    """MINI-SCHEMA / brief are excluded from contract_hash (ZDH-22)."""
    return explain_hash_boundary_impl(_cfg())


def catalog_diff(path: str = "", json_text: str = "", bound_hash: str = "") -> dict[str, Any]:
    """Compare live bootstrap summary vs on-disk catalog vs bound hash prefix (ZDH-22)."""
    return catalog_diff_impl(_cfg(), path=path, json_text=json_text, bound_hash=bound_hash)


def lint_runtime_config(path: str) -> dict[str, Any]:
    """Lint client config.json (:8080, auth_mode, env names, cheap path). Secrets redacted (ZDH-24)."""
    return lint_runtime_config_impl(_cfg(), path=path)


def lint_app_code(path: str) -> dict[str, Any]:
    """Anti-example scan of main.py / Dockerfiles (stale V1, hash literals, :9091) (ZDH-24)."""
    return lint_app_code_impl(_cfg(), path=path)


def lint_app(path: str) -> dict[str, Any]:
    """Lint config.json and app code under one path (ZDH-35)."""
    return lint_app_impl(_cfg(), path=path)


def explain_req_id_policy() -> dict[str, Any]:
    """One UUID per hop; never base:1; never Rewind /v2/session/{id}/turn (ZDH-23)."""
    return explain_req_id_policy_impl(_cfg())


def detective_links(req_id: str = "", chat_id: str = "", zeus_url: str = "") -> dict[str, Any]:
    """Hub Detective URL templates only — no scrape (ZDH-23)."""
    return detective_links_impl(_cfg(), req_id=req_id, chat_id=chat_id, zeus_url=zeus_url)


def support_pack_from_turn(
    debug_json: str = "",
    path: str = "",
    zeus_url: str = "",
) -> dict[str, Any]:
    """Redacted support-pack markdown from debug JSON or last smoke artifact (ZDH-23)."""
    return support_pack_from_turn_impl(
        _cfg(), debug_json=debug_json, path=path, zeus_url=zeus_url
    )


def describe_scope(bucket: str = "", scope: str = "") -> dict[str, Any]:
    """Live MINI-SCHEMA: entity types + field names only, no document samples (ZDH-25)."""
    return describe_scope_impl(_cfg(), bucket=bucket, scope=scope)


def recommend_motion(user_job: str) -> dict[str, Any]:
    """Map a user job to a Zeus motion + typical verbs/modes. Does not generate a chat_request (ZDH-26)."""
    return recommend_motion_impl(_cfg(), user_job=user_job)


def suggest_hooks(recipe: str = "") -> dict[str, Any]:
    """Middleware snippets (tenant pin, deny pipeline, output_schema, OCR). Not executed (ZDH-27)."""
    return suggest_hooks_impl(_cfg(), recipe=recipe)


def semantic_cache_status(zeus_url: str = "") -> dict[str, Any]:
    """Semantic cache coach: leave enabled=false; optional GET /v2/agent_memory/status (ZDH-28)."""
    return semantic_cache_status_impl(_cfg(), zeus_url=zeus_url)


def handoff_to_multi(force: bool = False) -> dict[str, Any]:
    """ZDH-11: graduate to multi-agent guidance after single-agent green (or force)."""
    return handoff_to_multi_impl(_cfg(), force=force)


def recommend_data_plane_mcp() -> dict[str, Any]:
    """ZDH-12: hand off to a future scope-bound Data Plane MCP (Helper stays coach)."""
    return recommend_data_plane_impl(_cfg())


def emit_mcp_config(
    server_name: str = "zeus-data-plane",
    read_only: bool = True,
    host: str = "claude",
) -> dict[str, Any]:
    """Emit safe-by-default MCP config fragment for a future data-plane server."""
    return emit_mcp_config_impl(
        _cfg(),
        server_name=server_name,
        read_only=read_only,
        host=host,
    )


def helper_metrics() -> dict[str, Any]:
    """Local privacy-safe success metrics (time-to-green heuristic; never leaves machine)."""
    return metrics_summary_impl(_cfg())


def suggest_demo_prompts() -> dict[str, Any]:
    """Starter advice-shaped prompts for smoke / demos."""
    return {
        "prompts": [
            "What kinds of entities exist in this dataset?",
            "Give me a short overview of available data for analysis.",
            "A fun beach destination in Mexico, in April, under $300.",
            "List a few example records and what fields they have.",
        ],
        "note": "Prefer advice-shaped questions, not raw SQL.",
        "docs": (
            docs_url("zeus-client/using-zeus-client.md")
        ),
    }


def _wrap_tool(fn: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(fn)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            record_metric(_cfg(), "tool_call", tool=fn.__name__)
        except Exception:  # noqa: BLE001, S110 — metrics must not break tools
            pass
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            # stdout is the MCP JSON-RPC stream; the family line goes to stderr.
            log_tool_exception(fn, exc)
            raise
        if not isinstance(result, dict):
            return result
        payload = as_envelope(result)
        if is_execution_failure(fn.__name__, payload):
            log_tool_failure(fn, payload)
            raise_tool_error(payload)
        return payload

    return wrapped


_MCP_OVERRIDES: dict[str, Any] = {}

if _HAS_ELICIT:
    from mcp.server.elicitation import ElicitationResult
    from mcp.server.mcpserver.resolve import Resolve

    from zeus_dev_helper_mcp.clarify import (
        Clarification,
        clarify_project,
        clarify_scaffold,
        clarify_url_argument,
    )

    def set_prereq_mcp(
        zeus_url: str = "",
        auth_mode: str = "",
        bucket: str = "",
        scope: str = "",
        collection: str = "",
        mode: str = "",
        role: str = "",
        has_llm_key: bool | None = None,
        has_bearer: bool | None = None,
        has_username: bool | None = None,
        has_password: bool | None = None,
        clarification: Annotated[
            ElicitationResult[Clarification], Resolve(clarify_url_argument)
        ] = UNASKED,
    ) -> dict[str, Any]:
        return _set_prereq_body(
            zeus_url=zeus_url,
            auth_mode=auth_mode,
            bucket=bucket,
            scope=scope,
            collection=collection,
            mode=mode,
            role=role,
            has_llm_key=has_llm_key,
            has_bearer=has_bearer,
            has_username=has_username,
            has_password=has_password,
            gate_outcome=clarification,
        )

    def start_project_mcp(
        goal: str = "single-agent",
        sample: str = "travel",
        force_multi: bool = False,
        clarification: Annotated[ElicitationResult[Clarification], Resolve(clarify_project)] = UNASKED,
    ) -> dict[str, Any]:
        return _start_project_body(
            goal=goal,
            sample=sample,
            force_multi=force_multi,
            gate_outcome=clarification,
        )

    def use_sample_mcp(
        sample: str = "travel",
        sample_dir: str = "",
        project_name: str = "",
        parent_dir: str = "",
        clone_if_missing: bool = True,
        clarification: Annotated[ElicitationResult[Clarification], Resolve(clarify_project)] = UNASKED,
    ) -> dict[str, Any]:
        return _use_sample_body(
            sample=sample,
            sample_dir=sample_dir,
            project_name=project_name,
            parent_dir=parent_dir,
            clone_if_missing=clone_if_missing,
            gate_outcome=clarification,
        )

    def scaffold_app_mcp(
        target_dir: str,
        project_name: str = "zeus_first_app",
        force: bool = False,
        app_kind: str = "cli",
        coding_language: str = "python",
        clarification: Annotated[ElicitationResult[Clarification], Resolve(clarify_scaffold)] = UNASKED,
    ) -> dict[str, Any]:
        return _scaffold_app_body(
            target_dir,
            project_name=project_name,
            force=force,
            app_kind=app_kind,
            coding_language=coding_language,
            gate_outcome=clarification,
        )

    for _mcp_fn, _public_name, _public in (
        (set_prereq_mcp, "set_prereq", set_prereq),
        (start_project_mcp, "start_project", start_project),
        (use_sample_mcp, "use_sample", use_sample),
        (scaffold_app_mcp, "scaffold_app", scaffold_app),
    ):
        _mcp_fn.__name__ = _public_name
        _mcp_fn.__doc__ = _public.__doc__
        _MCP_OVERRIDES[_public_name] = _mcp_fn


def create_mcp_server(toolsets: Iterable[str] | None = None) -> Any:
    """Build an MCP server with static toolsets, resources, and prompts."""
    raw = None if toolsets is None else ",".join(toolsets)
    enabled = parse_toolsets(raw)
    mcp_server = make_fastmcp(
        name="zeus-dev-helper",
        instructions=INSTRUCTIONS,
        version=__version__,
    )
    g = globals()
    for meta in TOOL_REGISTRY:
        if not meta.enabled_for(enabled):
            continue
        fn = _MCP_OVERRIDES.get(meta.name) or g.get(meta.name)
        if fn is None or not callable(fn):
            continue
        annotations = make_tool_annotations(
            read_only=meta.read_only,
            destructive=meta.destructive,
            idempotent=meta.idempotent,
            open_world=meta.open_world,
            title=meta.name,
        )
        register_tool(mcp_server, _wrap_tool(fn), annotations=annotations)
    register_resources(mcp_server)
    register_prompts(mcp_server)
    return mcp_server


mcp = create_mcp_server()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
