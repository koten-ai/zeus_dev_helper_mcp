"""Walkthrough helpers: richer next_step + gap_report (ZDH-8)."""

from __future__ import annotations

from typing import Any

from zeus_dev_helper_mcp.checklist import load_checklist
from zeus_dev_helper_mcp.checklist import next_step as base_next_step
from zeus_dev_helper_mcp.config import HelperConfig

# Recommended Helper tool(s) per checklist item
TOOL_HINTS: dict[str, list[str]] = {
    "0.1": ["start_project", "explain", "recommend_motion"],
    "0.2": ["use_sample", "travel_golden_path", "scaffold_app"],
    "1.1": ["doctor", "verify_local_setup"],
    "1.2": ["set_prereq", "doctor", "validate_env"],
    "2.1": ["readiness_check", "smoke_test_zeus"],
    "2.2": ["readiness_check", "set_prereq"],
    "2.3": ["bootstrap_scope", "readiness_check"],
    "3.1": ["scaffold_app", "use_sample", "travel_golden_path"],
    "3.2": ["write_env", "scaffold_app"],
    "4.1": ["fetch_chat_request", "list_catalog_modes", "bootstrap_scope"],
    "4.2": ["bind_contract", "catalog_diff", "explain_hash_boundary"],
    "5.1": ["smoke_test_zeus", "describe_scope"],
    "5.2": ["smoke_test_agent", "suggest_demo_prompts"],
    "6.1": ["suggest_hooks", "explain", "suggest_demo_prompts"],
    "7.1": [
        "diagnose_error",
        "suggest_hooks",
        "support_pack_from_turn",
        "detective_links",
        "gap_report",
    ],
}

# Knowledge that should be read as resources instead of encyclopedia tools (ZDH-33).
RESOURCE_HINTS: dict[str, list[str]] = {
    "0.1": [
        "zeus-helper://glossary/single_agent",
        "zeus-helper://glossary/motion",
    ],
    "1.2": ["zeus-helper://checklist"],
    "4.1": ["zeus-helper://catalog/modes"],
    "4.2": ["zeus-helper://policy/hash-boundary"],
    "5.2": ["zeus-helper://glossary/turn_result"],
    "7.1": ["zeus-helper://policy/req-id", "zeus-helper://checklist"],
}


def _smokes_green(cfg: HelperConfig) -> bool:
    data = load_checklist(cfg)
    flags = {"5.1": False, "5.2": False}
    for phase in data.get("phases") or []:
        for item in phase.get("items") or []:
            iid = item.get("id")
            if iid in flags and item.get("status") == "done":
                flags[iid] = True
    return flags["5.1"] and flags["5.2"]


def _checklist_sample(cfg: HelperConfig) -> str:
    data = load_checklist(cfg)
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    sample = str((meta or {}).get("sample") or "travel").lower().strip()
    if sample in ("rest", "api_only", "api-only"):
        return "api"
    if sample in ("ui", "demo_travel", "demo_travel_sample", "travel_sample"):
        return "travel"
    from zeus_dev_helper_mcp.beer import is_beer_sample

    if is_beer_sample(sample):
        return "beer"
    return sample


def enriched_next_step(cfg: HelperConfig) -> dict[str, Any]:
    base = base_next_step(cfg)
    item = base.get("item") or {}
    item_id = item.get("id") if isinstance(item, dict) else None
    tools = list(TOOL_HINTS.get(item_id or "", ["next_step", "doctor"]))
    sample = _checklist_sample(cfg)
    if sample == "api" and item_id in ("0.2", "3.1"):
        # API track: scaffold FastAPI, not travel UI sample
        tools = ["scaffold_app", "verify_local_setup", "write_env"]
        base["scaffold_args_hint"] = {
            "app_kind": "api",
            "coding_language": "python",
            "note": "UI demos use use_sample; API-only uses scaffold_app(app_kind=api)",
        }
    elif sample == "beer" and item_id in ("0.2", "3.1"):
        tools = ["use_sample", "write_env", "verify_local_setup"]
        base["use_sample_args_hint"] = {
            "sample": "beer",
            "project_name": "demo_beer_sample",
            "note": "Zero-LLM Direct catalog UI (find→get); not travel / not smoke_test_agent",
        }
    elif sample == "beer" and item_id in ("5.2", "6.1"):
        # Direct track: agent smoke is not the primary next step
        tools = ["smoke_test_zeus", "recommend_surface", "diagnose_error"]
        base["note"] = (
            "Beer Direct track does not require smoke_test_agent; "
            "prefer smoke_test_zeus + browser search on the BFF."
        )
    if sample == "api":
        base["app_track"] = "api"
    elif sample == "beer":
        base["app_track"] = "ui-direct"
    else:
        base["app_track"] = "ui"
    # ZDM-2: no LLM → do not push travel agent smoke as primary
    try:
        from zeus_dev_helper_mcp.prereqs import load_prereqs

        prefs = load_prereqs(cfg)
    except Exception:  # noqa: BLE001
        prefs = {}
    if prefs.get("has_llm_key") is False:
        tools = [t for t in tools if t != "smoke_test_agent"]
        if sample == "travel" and item_id in ("0.2", "3.1", "5.2"):
            from zeus_dev_helper_mcp.beer import prereqs_prefer_beer_direct

            if prereqs_prefer_beer_direct(prefs):
                tools = ["use_sample", "recommend_surface", "smoke_test_zeus"]
                base["use_sample_args_hint"] = {
                    "sample": "beer",
                    "note": "has_llm_key=false + beer bucket → Direct, not travel agent",
                }
                base["app_track"] = "ui-direct"
                base["note"] = (
                    "Prereqs prefer beer Direct (no LLM). "
                    "use_sample(sample=beer); do not clone travel or run smoke_test_agent."
                )
            else:
                base["note"] = (
                    "has_llm_key=false: smoke_test_agent is not required; "
                    "prefer recommend_surface(needs_llm=false) / Direct path."
                )
    base["recommended_tools"] = tools
    uris = ["zeus-helper://checklist", *RESOURCE_HINTS.get(item_id or "", [])]
    seen: set[str] = set()
    links: list[dict[str, str]] = []
    for uri in uris:
        if uri in seen:
            continue
        seen.add(uri)
        links.append({"type": "resource_link", "uri": uri, "name": uri.rsplit("/", 1)[-1]})
    base["resource_links"] = links
    base["coach"] = {
        "do_not": "Do not dump entire checklist unless asked; do not invent contract hashes",
        "ports": "Public Zeus :8080 only for app path",
        "catalogs": "Live stamp preferred; zeus_chat_request for templates",
        "resources": "Read zeus-helper:// checklist / glossary / verbs / policies instead of encyclopedia tools",
    }
    if item_id == "4.2":
        base["ops_note"] = (
            "Contract stamp is usually Administrator/Hub. Dev binds id+hash after stamp."
        )
    # Post-green handoffs (ZDH-11 / ZDH-12)
    if _smokes_green(cfg):
        base["post_green"] = {
            "single_agent_smokes": "green",
            "suggested_tools": [
                "recommend_data_plane_mcp",
                "emit_mcp_config",
                "handoff_to_multi",
                "gap_report",
            ],
            "note": (
                "First-app smokes are green. Helper stays the onboarding coach; "
                "data-plane MCP and multi-agent (ZJA) are handoffs only."
            ),
        }
        if not item_id or item_id in ("6.1", "7.1") or base.get("complete"):
            for t in ("recommend_data_plane_mcp", "handoff_to_multi"):
                if t not in base["recommended_tools"]:
                    base["recommended_tools"].append(t)
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
