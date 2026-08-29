"""Developer Helper MCP server — first-app coach (ZDH MVP tools)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from zeus_dev_helper_mcp import __version__
from zeus_dev_helper_mcp.catalog import (
    CatalogError,
    fetch_chat_request as fetch_catalog_template,
    list_modes,
    resolve_local_repo_hint,
)
from zeus_dev_helper_mcp.bootstrap import bootstrap_scope as bootstrap_scope_impl
from zeus_dev_helper_mcp.checklist import (
    load_checklist,
    set_item_status,
)
from zeus_dev_helper_mcp.config import HelperConfig, reload_config
from zeus_dev_helper_mcp.diagnose import diagnose_error as diagnose_error_impl
from zeus_dev_helper_mcp.explain import explain_topic
from zeus_dev_helper_mcp.surface import recommend_surface as recommend_surface_impl
from zeus_dev_helper_mcp.verbs import (
    explain_verb as explain_verb_impl,
    lint_verb_args as lint_verb_args_impl,
    suggest_verb_call as suggest_verb_call_impl,
)
from zeus_dev_helper_mcp.prereqs import public_prereqs, save_prereqs
from zeus_dev_helper_mcp.readiness import run_readiness_check
from zeus_dev_helper_mcp.scaffold import (
    scaffold_app as scaffold_app_impl,
    use_sample as use_sample_impl,
    verify_local_setup as verify_local_setup_impl,
    write_env_example,
)
from zeus_dev_helper_mcp.smoke import smoke_test_agent as smoke_agent_impl
from zeus_dev_helper_mcp.smoke import smoke_test_zeus as smoke_zeus_impl
from zeus_dev_helper_mcp.walkthrough import build_gap_report, enriched_next_step
from zeus_dev_helper_mcp.docs_links import docs_url
from zeus_dev_helper_mcp.travel import travel_golden_path as travel_golden_path_impl
from zeus_dev_helper_mcp.handoff import (
    emit_mcp_config as emit_mcp_config_impl,
    handoff_to_multi as handoff_to_multi_impl,
    metrics_summary as metrics_summary_impl,
    recommend_data_plane_mcp as recommend_data_plane_impl,
    record_metric,
)

mcp = FastMCP(
    "zeus-dev-helper",
    instructions=(
        "Developer Helper MCP: coach first Zeus Client app to green. "
        "Prefer live Zeus for stamps; use zeus_chat_request for min templates. "
        "Never invent contract hashes. Public API is :8080 not Hub :9091. "
        "Use readiness_check for platform gates; fetch_chat_request for templates. "
        "Use recommend_surface / explain_verb / lint_verb_args for Zeus 0.7 + Client 2.3 "
        "(ZeusRuntime / Direct vs agent). Do not treat this as a Runtime scaffold rewrite. "
        "After smoke green: recommend_data_plane_mcp / handoff_to_multi (handoffs only). "
        "Docs: koten_docs agent-index.yaml + using-zeus-client.md."
    ),
)


def _cfg() -> HelperConfig:
    return reload_config()


def _stub(tool: str, phase: str) -> dict[str, Any]:
    return {
        "implemented": False,
        "tool": tool,
        "phase": phase,
        "message": f"{tool} is not implemented yet (scheduled {phase}).",
        "next_action": "Continue with implemented tools: doctor, readiness_check, set_prereq, "
        "get_checklist, next_step, list_catalog_modes, fetch_chat_request, explain.",
        "docs": {
            "dev_helper_mcp": (
                docs_url("zeus-client/dev-helper-mcp.md")
            ),
            "zdh_board": "https://kotenai.atlassian.net/jira/software/projects/ZDH/boards/45",
        },
    }


@mcp.tool()
def doctor() -> dict[str, Any]:
    """Health / doctor: version, config (no secrets), catalog source readiness."""
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
    return {
        "ok": True,
        "version": __version__,
        "config": cfg.public_view(),
        "catalog": {
            "reachable": catalog_ok,
            "modes_count": modes_count,
            "error": catalog_error,
            "hint_local_dir": sibling or None,
            "env": "ZEUS_CHAT_REQUEST_DIR or GITHUB_TOKEN for private repo",
        },
        "docs": {
            "for_ai_agents": (
                docs_url("zeus-client/for-ai-agents.md")
            ),
            "using_zeus_client": (
                docs_url("zeus-client/using-zeus-client.md")
            ),
            "zeus_chat_request": f"https://github.com/{cfg.chat_request_repo}",
        },
    }


@mcp.tool()
def start_project(
    goal: str = "single-agent",
    sample: str = "travel",
    force_multi: bool = False,
) -> dict[str, Any]:
    """Start or reset first-app coaching checklist (single-agent default).

    Multi-agent goals (goal=multi or sample=yelp) are gated until single-agent
    smokes are green, unless force_multi=true (ZDH-11).
    """
    cfg = _cfg()
    goal_l = (goal or "single-agent").lower().strip()
    sample_l = (sample or "travel").lower().strip()
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
    except Exception:  # noqa: BLE001
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
    }
    if wants_multi:
        out["track"] = "multi-agent"
        out["handoff_to_multi"] = handoff_to_multi_impl(cfg, force=True)
        out["note"] = "Multi track is graduation guidance only — jobs live in ZJA."
    return out


@mcp.tool()
def get_checklist() -> dict[str, Any]:
    """Return the current first-app checklist state."""
    return load_checklist(_cfg())


@mcp.tool()
def next_step() -> dict[str, Any]:
    """Return the single current checklist blocker + recommended Helper tools (coach)."""
    return enriched_next_step(_cfg())


@mcp.tool()
def gap_report() -> dict[str, Any]:
    """What's left for single-agent / production-ish path (phases 4–7 focus)."""
    return build_gap_report(_cfg())


@mcp.tool()
def mark_done(item_id: str, evidence: str = "") -> dict[str, Any]:
    """Mark a checklist item done (optional evidence string, no secrets)."""
    data = set_item_status(_cfg(), item_id, "done", evidence=evidence or None)
    return {"updated": item_id, "status": "done", "next_step": enriched_next_step(_cfg()), "checklist": data}


@mcp.tool()
def mark_blocked(item_id: str, reason: str = "") -> dict[str, Any]:
    """Mark a checklist item blocked with a reason."""
    data = set_item_status(_cfg(), item_id, "blocked", evidence=reason or None)
    return {"updated": item_id, "status": "blocked", "next_step": enriched_next_step(_cfg()), "checklist": data}


@mcp.tool()
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


@mcp.tool()
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
    """
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
    cfg = reload_config()
    return {
        "saved": True,
        "stored_public": stored,
        "effective_config": cfg.public_view(),
        "note": "Secrets must remain in env vars — only presence flags are stored.",
        "next_action": "validate_env → readiness_check",
    }


@mcp.tool()
def readiness_check(update_checklist: bool = True) -> dict[str, Any]:
    """Live Zeus platform gates: healthz/readyz/version, auth, bootstrap, chat_request.

    Never returns secret values. Emits failure_class + next_action on red paths.
    """
    cfg = _cfg()
    return run_readiness_check(cfg, update_checklist=update_checklist)


@mcp.tool()
def list_catalog_modes() -> dict[str, Any]:
    """List V2 min chat_request modes from zeus_chat_request (ZDH-14)."""
    cfg = _cfg()
    try:
        return list_modes(cfg)
    except CatalogError as e:
        return {
            "error": e.message,
            "failure_class": e.failure_class,
            "next_action": (
                "Clone https://github.com/koten-ai/zeus_chat_request and set "
                "ZEUS_CHAT_REQUEST_DIR, or set GITHUB_TOKEN for private fetch."
            ),
            "hint_local": resolve_local_repo_hint() or None,
        }


@mcp.tool()
def fetch_chat_request(mode: str = "analytics", detail: str = "summary") -> dict[str, Any]:
    """Fetch a V2 min chat_request template by mode from zeus_chat_request.

    Prefer live Zeus stamp for production. detail: summary | full.
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
                "Set ZEUS_CHAT_REQUEST_DIR to a local clone of zeus_chat_request "
                "or GITHUB_TOKEN; then retry. Still stamp on Zeus for production."
            ),
            "docs": (
                docs_url("zeus-client/contracts-and-catalog.md")
            ),
        }


@mcp.tool()
def explain(topic: str) -> dict[str, Any]:
    """Explain a Zeus/Client concept (glossary) with docs deep-link."""
    return explain_topic(_cfg(), topic)


@mcp.tool()
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


@mcp.tool()
def scaffold_app(
    target_dir: str,
    project_name: str = "zeus_first_app",
    force: bool = False,
) -> dict[str, Any]:
    """Write a minimal Zeus Client middle-man project (main.py, requirements, .env.example)."""
    return scaffold_app_impl(_cfg(), target_dir, project_name=project_name, force=force)


@mcp.tool()
def use_sample(sample: str = "travel", sample_dir: str = "") -> dict[str, Any]:
    """Point at demo_travel_sample (or block multi until single-agent green)."""
    return use_sample_impl(_cfg(), sample=sample, sample_dir=sample_dir)


@mcp.tool()
def travel_golden_path(sample_dir: str = "") -> dict[str, Any]:
    """ZDH-10: demo_travel_sample golden path phases + optional layout validation."""
    return travel_golden_path_impl(_cfg(), sample_dir=sample_dir)


@mcp.tool()
def write_env(target_dir: str) -> dict[str, Any]:
    """Write .env.example from prereqs (no secrets)."""
    return write_env_example(_cfg(), target_dir)


@mcp.tool()
def verify_local_setup(target_dir: str = "") -> dict[str, Any]:
    """Check zeus_client import and optional scaffold files."""
    return verify_local_setup_impl(_cfg(), target_dir=target_dir)


@mcp.tool()
def smoke_test_zeus(update_checklist: bool = True) -> dict[str, Any]:
    """Smoke Zeus without LLM: readiness + POST /v2/{bucket}/{scope}/describe."""
    return smoke_zeus_impl(_cfg(), update_checklist=update_checklist)


@mcp.tool()
def smoke_test_agent(
    question: str = "In one short sentence, what data is available in this scope?",
    update_checklist: bool = True,
) -> dict[str, Any]:
    """One Zeus Client run_agent turn (requires kotenai-zeus-client + LLM key)."""
    return smoke_agent_impl(_cfg(), question=question, update_checklist=update_checklist)


@mcp.tool()
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
    """Map error signals to failure_class + errors.md anchor (ZDH-7 / ZDH-19)."""
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


@mcp.tool()
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


@mcp.tool()
def explain_verb(name: str) -> dict[str, Any]:
    """V2 verb encyclopedia: path class, demux, Direct vs pipeline (ZDH-18)."""
    return explain_verb_impl(_cfg(), name=name)


@mcp.tool()
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


@mcp.tool()
def suggest_verb_call(goal: str, mini_schema: str = "") -> dict[str, Any]:
    """Draft a legal V2 verb JSON body from a goal. Guidance only — does not POST."""
    return suggest_verb_call_impl(
        _cfg(),
        goal=goal,
        mini_schema=mini_schema or None,
    )


@mcp.tool()
def handoff_to_multi(force: bool = False) -> dict[str, Any]:
    """ZDH-11: graduate to multi-agent guidance after single-agent green (or force)."""
    return handoff_to_multi_impl(_cfg(), force=force)


@mcp.tool()
def recommend_data_plane_mcp() -> dict[str, Any]:
    """ZDH-12: hand off to a future scope-bound Data Plane MCP (Helper stays coach)."""
    return recommend_data_plane_impl(_cfg())


@mcp.tool()
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


@mcp.tool()
def helper_metrics() -> dict[str, Any]:
    """Local privacy-safe success metrics (time-to-green heuristic; never leaves machine)."""
    return metrics_summary_impl(_cfg())


@mcp.tool()
def suggest_demo_prompts() -> dict[str, Any]:
    """Starter advice-shaped prompts for smoke / demos."""
    cfg = _cfg()
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


def main() -> None:
    # stdio transport for Claude / Grok / etc.
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
