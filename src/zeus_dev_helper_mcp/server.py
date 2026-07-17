"""Developer Helper MCP server (ZDH-3 skeleton + ZDH-14 catalogs)."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from zeus_dev_helper_mcp import __version__
from zeus_dev_helper_mcp.catalog import (
    CatalogError,
    fetch_chat_request as fetch_catalog_template,
    list_modes,
    resolve_local_repo_hint,
)
from zeus_dev_helper_mcp.checklist import (
    load_checklist,
    next_step as checklist_next_step,
    set_item_status,
)
from zeus_dev_helper_mcp.config import CFG, HelperConfig, load_config, reload_config
from zeus_dev_helper_mcp.explain import explain_topic

mcp = FastMCP(
    "zeus-dev-helper",
    instructions=(
        "Developer Helper MCP: coach first Zeus Client app to green. "
        "Prefer live Zeus for stamps; use zeus_chat_request for min templates. "
        "Never invent contract hashes. Public API is :8080 not Hub :9091. "
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
        "next_action": "Continue with implemented tools: doctor, get_checklist, next_step, "
        "list_catalog_modes, fetch_chat_request, explain, mark_done/mark_blocked.",
        "docs": {
            "dev_helper_mcp": (
                f"https://github.com/koten-ai/koten_docs/blob/{_cfg().docs_branch}/"
                "zeus-client/dev-helper-mcp.md"
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
                f"https://github.com/koten-ai/koten_docs/blob/{cfg.docs_branch}/"
                "zeus-client/for-ai-agents.md"
            ),
            "using_zeus_client": (
                f"https://github.com/koten-ai/koten_docs/blob/{cfg.docs_branch}/"
                "zeus-client/using-zeus-client.md"
            ),
            "zeus_chat_request": f"https://github.com/{cfg.chat_request_repo}",
        },
    }


@mcp.tool()
def start_project(goal: str = "single-agent", sample: str = "travel") -> dict[str, Any]:
    """Start or reset first-app coaching checklist (single-agent default)."""
    cfg = _cfg()
    data = load_checklist(cfg)
    data["project"] = f"{goal}:{sample}"
    data["meta"] = {"goal": goal, "sample": sample}
    from zeus_dev_helper_mcp.checklist import save_checklist

    save_checklist(cfg, data)
    nxt = checklist_next_step(cfg)
    return {
        "started": True,
        "goal": goal,
        "sample": sample,
        "checklist_path": str(cfg.state_dir / "checklist.json"),
        "next_step": nxt,
        "read_first": [
            f"https://github.com/koten-ai/koten_docs/blob/{cfg.docs_branch}/zeus-client/for-ai-agents.md",
            f"https://github.com/koten-ai/koten_docs/blob/{cfg.docs_branch}/zeus-client/using-zeus-client.md",
        ],
    }


@mcp.tool()
def get_checklist() -> dict[str, Any]:
    """Return the current first-app checklist state."""
    return load_checklist(_cfg())


@mcp.tool()
def next_step() -> dict[str, Any]:
    """Return the next incomplete checklist item with a short hint."""
    return checklist_next_step(_cfg())


@mcp.tool()
def mark_done(item_id: str, evidence: str = "") -> dict[str, Any]:
    """Mark a checklist item done (optional evidence string, no secrets)."""
    data = set_item_status(_cfg(), item_id, "done", evidence=evidence or None)
    return {"updated": item_id, "status": "done", "next_step": checklist_next_step(_cfg()), "checklist": data}


@mcp.tool()
def mark_blocked(item_id: str, reason: str = "") -> dict[str, Any]:
    """Mark a checklist item blocked with a reason."""
    data = set_item_status(_cfg(), item_id, "blocked", evidence=reason or None)
    return {"updated": item_id, "status": "blocked", "next_step": checklist_next_step(_cfg()), "checklist": data}


@mcp.tool()
def validate_env() -> dict[str, Any]:
    """Validate Helper env shape (presence only — no secret values)."""
    cfg = _cfg()
    issues: list[dict[str, str]] = []
    if not cfg.zeus_url:
        issues.append(
            {
                "field": "ZEUS_URL",
                "level": "warn",
                "message": "Not set — required for live readiness/smoke (P2/P5).",
            }
        )
    elif ":9091" in cfg.zeus_url:
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
        "catalog_templates": catalog_note,
        "issues": issues,
        "docs": (
            f"https://github.com/koten-ai/koten_docs/blob/{cfg.docs_branch}/"
            "zeus-client/config-reference.md"
        ),
    }


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
                f"https://github.com/koten-ai/koten_docs/blob/{cfg.docs_branch}/"
                "zeus-client/contracts-and-catalog.md"
            ),
        }


@mcp.tool()
def explain(topic: str) -> dict[str, Any]:
    """Explain a Zeus/Client concept (glossary) with docs deep-link."""
    return explain_topic(_cfg(), topic)


# --- Stubs for later phases (registered so hosts see full catalog) ---


@mcp.tool()
def set_prereq() -> dict[str, Any]:
    """Store prereqs (P2) — not fully implemented; use env vars for now."""
    return _stub("set_prereq", "P2")


@mcp.tool()
def readiness_check() -> dict[str, Any]:
    """Live Zeus readiness probes (P2) — stub."""
    return _stub("readiness_check", "P2")


@mcp.tool()
def bootstrap_scope() -> dict[str, Any]:
    """Call Zeus bootstrap API (P3) — stub; use fetch_chat_request for templates now."""
    out = _stub("bootstrap_scope", "P3")
    out["workaround"] = "fetch_chat_request(mode=...) for offline templates (ZDH-14)"
    return out


@mcp.tool()
def scaffold_app() -> dict[str, Any]:
    """Scaffold middle-man app (P4) — stub."""
    return _stub("scaffold_app", "P4")


@mcp.tool()
def use_sample() -> dict[str, Any]:
    """Point at demo_travel_sample (P4/P8) — stub."""
    return _stub("use_sample", "P4")


@mcp.tool()
def smoke_test_zeus() -> dict[str, Any]:
    """Smoke Zeus without LLM (P5) — stub."""
    return _stub("smoke_test_zeus", "P5")


@mcp.tool()
def smoke_test_agent() -> dict[str, Any]:
    """Full agent turn smoke (P5) — stub."""
    return _stub("smoke_test_agent", "P5")


@mcp.tool()
def diagnose_error(status: str = "", body: str = "", message: str = "") -> dict[str, Any]:
    """Map error signals to failure_class (P5) — minimal heuristic + docs links."""
    cfg = _cfg()
    blob = f"{status} {body} {message}".lower()
    failure = "dispatch_failed"
    if "9091" in blob or "hub" in blob:
        failure = "wrong_port_hub_vs_public"
    elif "401" in blob or "unauthor" in blob:
        failure = "auth_failed"
    elif "409" in blob or "drift" in blob:
        failure = "hash_drift"
    elif "timeout" in blob:
        failure = "network_timeout"
    elif "llm" in blob or "api_key" in blob:
        failure = "llm_key_missing"
    elif "catalog" in blob or "chat_request" in blob:
        failure = "empty_tool_catalog"
    return {
        "implemented": "partial",
        "failure_class": failure,
        "docs": (
            f"https://github.com/koten-ai/koten_docs/blob/{cfg.docs_branch}/"
            f"zeus-client/errors.md"
        ),
        "agent_index": (
            f"https://github.com/koten-ai/koten_docs/blob/{cfg.docs_branch}/agent-index.yaml"
        ),
        "note": "Full diagnose matrix lands in ZDH-7; this is a first-pass heuristic.",
    }


def main() -> None:
    # stdio transport for Claude / Grok / etc.
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
