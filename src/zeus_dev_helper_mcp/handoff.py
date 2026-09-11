"""Post-green handoffs: multi-agent graduation + data-plane MCP (ZDH-11, ZDH-12)."""

from __future__ import annotations

import json
from typing import Any

from zeus_dev_helper_mcp.checklist import load_checklist
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.docs_links import docs_url
from zeus_dev_helper_mcp.walkthrough import build_gap_report


def _single_agent_green(cfg: HelperConfig) -> tuple[bool, dict[str, Any]]:
    """Heuristic: checklist items 5.1 and 5.2 done, or gap_report empty on phase 5."""
    data = load_checklist(cfg)
    flags = {"5.1": False, "5.2": False}
    for phase in data.get("phases") or []:
        for item in phase.get("items") or []:
            iid = item.get("id")
            if iid in flags and item.get("status") == "done":
                flags[iid] = True
    green = flags["5.1"] and flags["5.2"]
    return green, flags


def handoff_to_multi(cfg: HelperConfig, *, force: bool = False) -> dict[str, Any]:
    """ZDH-11: graduate to multi-agent only after single-agent green (or force)."""
    green, flags = _single_agent_green(cfg)
    if not green and not force:
        return {
            "ok": False,
            "blocked": True,
            "reason": "Single-agent path not green (need smoke_test_zeus + smoke_test_agent done).",
            "checklist_flags": flags,
            "next_action": "Run smoke_test_zeus and smoke_test_agent, or pass force=true to override.",
            "docs": {
                "using_client": docs_url("zeus-client/using-zeus-client.md"),
                "crawl_turbo": docs_url("zeus-client/crawl-walk-run-turbo.md"),
            },
        }

    return {
        "ok": True,
        "blocked": False,
        "forced": force and not green,
        "checklist_flags": flags,
        "track": "multi-agent",
        "concept": {
            "three_tier": [
                "Orchestrator — decomposes multi-part help, fans out work",
                "Workers — scoped agents / tool loops (often per scope or specialty)",
                "Advisor — optional critique / policy / merge guidance",
            ],
            "note": "Helper does not run Job storage — that is Zeus_Job_Agents (ZJA).",
        },
        "samples": {
            "yelp": {
                "status": "planned_or_private",
                "note": "Yelp multi-agent demo when published; do not invent clone URLs.",
            },
            "zja": {
                "repo": "https://github.com/koten-ai/Zeus_Job_Agents",
                "note": "Multi-agent job platform — integrate when product-ready",
            },
        },
        "checklist_multi_preview": [
            {"id": "m.1", "title": "Single-agent green confirmed", "status": "done" if green else "forced"},
            {"id": "m.2", "title": "Read multi-agent / Turbo ladder docs", "status": "todo"},
            {"id": "m.3", "title": "Clone multi sample when available (Yelp)", "status": "todo"},
            {"id": "m.4", "title": "Map to ZJA jobs / orchestrator patterns", "status": "todo"},
        ],
        "next_action": (
            "Stay on single-agent until product samples land; explore Zeus_Job_Agents docs; "
            "do not reimplement job coordination inside Helper."
        ),
        "docs": {
            "turbo": docs_url("zeus-client/crawl-walk-run-turbo.md"),
            "platform": docs_url(""),
        },
        "jira": "https://kotenai.atlassian.net/browse/ZDH-11",
    }


def recommend_data_plane_mcp(cfg: HelperConfig) -> dict[str, Any]:
    """ZDH-12: after first app green, hand off to a future data-plane MCP."""
    green, flags = _single_agent_green(cfg)
    gaps = build_gap_report(cfg)
    return {
        "ok": True,
        "helper_role": "onboarding coach only — not the data plane",
        "data_plane_role": "scope-bound governed data tools (Explore/Verify) after first app is green",
        "single_agent_green": green,
        "checklist_flags": flags,
        "recommend_now": green or gaps.get("progress", {}).get("pct", 0) >= 50,
        "boundary": {
            "use_helper_for": [
                "first green path",
                "scaffold",
                "catalog templates",
                "readiness / smoke",
            ],
            "use_data_plane_for": [
                "ongoing explore/verify on live scopes",
                "governed tool loops without re-onboarding",
            ],
            "do_not": [
                "mix full data-plane tool dump into Helper",
                "free multi-bucket discovery without allowlist",
            ],
        },
        "next_action": (
            "When a Data Plane MCP package is published, install it with emit_mcp_config "
            "defaults (scope-bound, read-only). Until then continue with Zeus Client apps."
        ),
        "status": "interface_ready_package_pending",
        "docs": {
            "helper": docs_url("zeus-client/dev-helper-mcp.md"),
            "using_client": docs_url("zeus-client/using-zeus-client.md"),
        },
        "jira": "https://kotenai.atlassian.net/browse/ZDH-12",
    }


def emit_mcp_config(
    cfg: HelperConfig,
    *,
    server_name: str = "zeus-data-plane",
    read_only: bool = True,
    host: str = "claude",
) -> dict[str, Any]:
    """Emit a safe-by-default MCP config fragment for a future data-plane server."""
    bucket = cfg.default_bucket or "YOUR_BUCKET"
    scope = cfg.default_scope or "YOUR_SCOPE"
    zeus_url = cfg.zeus_url or "http://localhost:8080"

    env = {
        "ZEUS_URL": zeus_url,
        "ZEUS_BUCKET": bucket,
        "ZEUS_SCOPE": scope,
        "ZEUS_MODE": cfg.default_mode or "analytics",
        "DATA_PLANE_READ_ONLY": "true" if read_only else "false",
        "DATA_PLANE_SCOPE_ALLOWLIST": f"{bucket}/{scope}",
    }

    # Placeholder command until real package exists
    command = "python"
    args = ["-m", "zeus_data_plane_mcp"]  # future package name

    claude = {
        "mcpServers": {
            server_name: {
                "command": command,
                "args": args,
                "env": env,
            }
        }
    }

    note = (
        "PLACEHOLDER — no public Data Plane MCP package is assumed yet. "
        "Replace command/args when ZE/ZC publish the server. "
        "Defaults are scope-bound and read-only."
    )

    return {
        "ok": True,
        "host": host,
        "note": note,
        "scope_allowlist": f"{bucket}/{scope}",
        "read_only": read_only,
        "claude_desktop_fragment": claude,
        "json": json.dumps(claude, indent=2),
        "next_action": (
            "Do not install a non-existent package; keep fragment for when Data Plane MCP ships. "
            "Helper remains the onboarding coach."
        ),
        "docs": docs_url("zeus-client/dev-helper-mcp.md"),
    }


def record_metric(cfg: HelperConfig, event: str, *, tool: str = "") -> None:
    """Append a privacy-safe local metric event (ids only — no payloads)."""
    path = cfg.state_dir / "metrics.jsonl"
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    import time

    row: dict[str, Any] = {"ts": time.time(), "event": event}
    if event == "tool_call":
        name = (tool or "").strip()[:80]
        if not name:
            return
        row["tool"] = name
    line = json.dumps(row) + "\n"
    with path.open("a") as f:
        f.write(line)


def metrics_summary(cfg: HelperConfig) -> dict[str, Any]:
    path = cfg.state_dir / "metrics.jsonl"
    if not path.is_file():
        return {"events": 0, "time_to_green_seconds": None, "tool_calls": []}
    starts = []
    zeus_ok = []
    agent_ok = []
    tool_calls: list[str] = []
    for line in path.read_text().splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        e = ev.get("event")
        ts = ev.get("ts")
        if e == "start_project" and ts:
            starts.append(ts)
        if e == "smoke_test_zeus_ok" and ts:
            zeus_ok.append(ts)
        if e == "smoke_test_agent_ok" and ts:
            agent_ok.append(ts)
        if e == "tool_call":
            name = str(ev.get("tool") or "").strip()
            if name:
                tool_calls.append(name)
    t0 = min(starts) if starts else None
    t1 = min(agent_ok) if agent_ok else None
    ttg = (t1 - t0) if t0 and t1 and t1 >= t0 else None
    from zeus_dev_helper_mcp.eval_suite import check_trace

    sequence = check_trace(tool_calls)
    return {
        "events": sum(1 for _ in path.read_text().splitlines() if _.strip()),
        "start_project_count": len(starts),
        "smoke_zeus_ok_count": len(zeus_ok),
        "smoke_agent_ok_count": len(agent_ok),
        "time_to_green_seconds": round(ttg, 1) if ttg is not None else None,
        "tool_calls": tool_calls[-80:],
        "tool_call_count": len(tool_calls),
        "sequence": sequence,
        "path": str(path),
        "note": "Local only — tool ids, no payloads/tokens/prompts",
    }
