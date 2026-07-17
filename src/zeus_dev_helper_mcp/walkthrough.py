"""Walkthrough helpers: richer next_step + gap_report (ZDH-8)."""

from __future__ import annotations

from typing import Any

from zeus_dev_helper_mcp.checklist import load_checklist, next_step as base_next_step
from zeus_dev_helper_mcp.config import HelperConfig

# Recommended Helper tool(s) per checklist item
TOOL_HINTS: dict[str, list[str]] = {
    "0.1": ["start_project", "explain"],
    "0.2": ["use_sample", "scaffold_app"],
    "1.1": ["doctor", "verify_local_setup"],
    "1.2": ["set_prereq", "validate_env"],
    "2.1": ["readiness_check", "smoke_test_zeus"],
    "2.2": ["readiness_check", "set_prereq"],
    "2.3": ["bootstrap_scope", "readiness_check"],
    "3.1": ["scaffold_app", "use_sample"],
    "3.2": ["write_env", "scaffold_app"],
    "4.1": ["fetch_chat_request", "list_catalog_modes", "bootstrap_scope"],
    "4.2": ["explain", "bootstrap_scope"],  # stamp is ops/Hub
    "5.1": ["smoke_test_zeus"],
    "5.2": ["smoke_test_agent", "suggest_demo_prompts"],
    "6.1": ["explain", "suggest_demo_prompts"],
    "7.1": ["diagnose_error", "gap_report"],
}


def enriched_next_step(cfg: HelperConfig) -> dict[str, Any]:
    base = base_next_step(cfg)
    item = base.get("item") or {}
    item_id = item.get("id") if isinstance(item, dict) else None
    tools = TOOL_HINTS.get(item_id or "", ["get_checklist", "doctor"])
    base["recommended_tools"] = tools
    base["coach"] = {
        "do_not": "Do not dump entire checklist unless asked; do not invent contract hashes",
        "ports": "Public Zeus :8080 only for app path",
        "catalogs": "Live stamp preferred; zeus_chat_request for templates",
    }
    if item_id == "4.2":
        base["ops_note"] = (
            "Contract stamp is usually Administrator/Hub. Dev binds id+hash after stamp."
        )
    return base


def build_gap_report(cfg: HelperConfig) -> dict[str, Any]:
    data = load_checklist(cfg)
    open_items: list[dict[str, Any]] = []
    done = 0
    total = 0
    for phase in data.get("phases") or []:
        for item in phase.get("items") or []:
            total += 1
            st = item.get("status")
            if st == "done":
                done += 1
            elif st in ("todo", "blocked"):
                open_items.append(
                    {
                        "phase": phase.get("id"),
                        "phase_title": phase.get("title"),
                        "item_id": item.get("id"),
                        "title": item.get("title"),
                        "status": st,
                        "recommended_tools": TOOL_HINTS.get(item.get("id") or "", []),
                        "evidence": item.get("evidence"),
                    }
                )
    productionish = [
        i
        for i in open_items
        if str(i.get("phase") or "").startswith(("5_", "6_", "7_", "4_"))
    ]
    return {
        "progress": {"done": done, "total": total, "pct": round(100 * done / total, 1) if total else 0},
        "open_count": len(open_items),
        "open_items": open_items,
        "productionish_gaps": productionish,
        "next_step": enriched_next_step(cfg),
        "single_agent_done": len(open_items) == 0,
        "docs": data.get("docs"),
        "note": "04a/05a production-ish gaps mapped onto phases 4–7 of first-app checklist",
    }
