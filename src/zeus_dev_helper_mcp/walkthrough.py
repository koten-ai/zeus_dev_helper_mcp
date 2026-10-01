"""Walkthrough helpers: richer next_step + gap_report (ZDH-8)."""

from __future__ import annotations

import json
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
    "3.2": ["write_env", "verify_local_setup", "lint_runtime_config"],
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


def _enabled_tool_names() -> set[str]:
    from zeus_dev_helper_mcp.toolsets import enabled_tools

    return {meta.name for meta in enabled_tools()}


def _keep_enabled(tools: list[str]) -> list[str]:
    """Drop tools the host did not load. Core does not include explain."""
    allowed = _enabled_tool_names()
    kept: list[str] = []
    seen: set[str] = set()
    for name in tools:
        if name in allowed and name not in seen:
            kept.append(name)
            seen.add(name)
    return kept


def _yelp_app_current(cfg: HelperConfig) -> bool:
    """True when the recorded directory is the yelp-demo app whose search is a turn."""
    from zeus_dev_helper_mcp.yelp import recorded_yelp_sample_dir
    from zeus_dev_helper_mcp.yelp_app import yelp_bff_is_current

    root = recorded_yelp_sample_dir(cfg)
    if root is None:
        return False
    main = root / "main.py"
    if not main.is_file():
        return False
    try:
        text = main.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return yelp_bff_is_current(text)


def _yelp_use_sample_hint() -> dict[str, str]:
    return {
        "sample": "demo_yelp",
        "project_name": "demo_yelp",
        "note": (
            "Write the yelp-demo app and set DEMO_YELP_SAMPLE_DIR. "
            "POST /api/search calls rt.agent.run_turn and omits chat_request so "
            "catalog.load_for_turn reads "
            "data/chat_requests/yelp-demo__default/chat_request_analytics_v2.json. "
            "Suggest, the header count, and the business page page find on User "
            "and keep biz: rows. Do not scan those rows for search. "
            "Do not copy demo_beer_sample. Bucket yelp-demo, scope _default. "
            "Do not clone demo_travel_sample. Do not pass sample=yelp."
        ),
    }


def _stored_zeus_url(cfg: HelperConfig) -> str:
    try:
        from zeus_dev_helper_mcp.prereqs import load_prereqs

        prefs = load_prereqs(cfg)
    except Exception:  # noqa: BLE001
        prefs = {}
    return str((prefs or {}).get("zeus_url") or "").strip()


def _checklist_sample(cfg: HelperConfig) -> str:
    data = load_checklist(cfg)
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    sample = str((meta or {}).get("sample") or "travel").lower().strip()
    if sample in ("rest", "api_only", "api-only"):
        return "api"
    if sample in ("ui", "demo_travel", "demo_travel_sample", "travel_sample"):
        return "travel"
    from zeus_dev_helper_mcp.beer import is_beer_sample
    from zeus_dev_helper_mcp.yelp import is_yelp_demo_sample

    if is_beer_sample(sample):
        return "beer"
    if is_yelp_demo_sample(sample):
        return "demo_yelp"
    return sample


# Live V2 shapes the generated catalog page follows (ZDM-17).
RESULT_SHAPES: dict[str, str] = {
    "contract": "live V2",
    "find": (
        "find forwards limit and order_by. offset is not forwarded. "
        "Hide Next unless a probe shows page 2 ids differ from page 1."
    ),
    "total": "total_count may be null. The label is 1–N shown.",
    "search": (
        "search items are {node: {doc_key}, score} and node_ids may be empty. "
        "A doc_key-only hit is an empty state. A hop name is not a card title."
    ),
}


def _website_green_failed(cfg: HelperConfig) -> bool:
    path = cfg.state_dir / "website_green.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and data.get("ok") is False


def enriched_next_step(cfg: HelperConfig) -> dict[str, Any]:
    from zeus_dev_helper_mcp.beer import missing_recorded_beer_dir

    base = base_next_step(cfg)
    missing = missing_recorded_beer_dir(cfg)
    if missing is not None:
        base["failure_class"] = "sample_dir_missing"
        base["sample_dir"] = missing
        base["recommended_tools"] = _keep_enabled(["use_sample"])
        base["note"] = (
            "Recorded beer sample directory is not on disk. "
            "use_sample(sample=beer) writes the catalog UI."
        )
        base["result_shapes"] = dict(RESULT_SHAPES)
        return base
    item = base.get("item") or {}
    item_id = item.get("id") if isinstance(item, dict) else None
    tools = list(TOOL_HINTS.get(item_id or "", ["next_step", "doctor"]))
    sample = _checklist_sample(cfg)
    if (
        sample == "demo_yelp"
        and item_id not in ("0.1", "0.2")
        and not _yelp_app_current(cfg)
    ):
        base["app_track"] = "ui"
        base["use_sample_args_hint"] = _yelp_use_sample_hint()
        base["note"] = (
            "The yelp-demo app is not on disk yet. use_sample(sample=demo_yelp) "
            "writes it. POST /api/search calls rt.agent.run_turn and omits "
            "chat_request so catalog.load_for_turn reads "
            "data/chat_requests/yelp-demo__default/chat_request_analytics_v2.json."
        )
        base["recommended_tools"] = _keep_enabled(["use_sample"])
        return base
    if sample == "demo_yelp" and item_id not in ("0.1", "0.2") and _yelp_app_current(cfg):
        from zeus_dev_helper_mcp.yelp import recorded_yelp_sample_dir

        recorded = recorded_yelp_sample_dir(cfg)
        base["app_track"] = "ui"
        base["local_dir"] = str(recorded) if recorded is not None else ""
        base["note"] = (
            f"The yelp-demo app is at {recorded}. "
            "POST /api/search calls rt.agent.run_turn and omits chat_request. "
            "Suggest, the header count, and the business page page find on User "
            "and keep biz: rows. "
            "Do not scaffold_app and do not copy demo_beer_sample."
        )
        base["recommended_tools"] = []
        return base
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
            "note": "Beer catalog UI. Search is rt.agent.run_turn with chat_request omitted (MINI-SCHEMA merge). Do not clone travel.",
        }
    elif sample == "beer" and item_id in ("5.1", "5.2", "6.1"):
        if _website_green_failed(cfg):
            tools = ["diagnose_error"]
            base["note"] = (
                "website_green failed on the running app. diagnose_error maps the symptom. "
                "Do not scaffold another app."
            )
        else:
            tools = ["website_green"]
            base["note"] = (
                "The catalog sample is written. website_green installs, starts, and "
                "checks the list page. smoke_test_agent is not this check. "
                "A describe 200 is not this check."
            )
    elif sample == "demo_yelp" and item_id in ("0.2", "3.1"):
        tools = ["use_sample"]
        base["use_sample_args_hint"] = _yelp_use_sample_hint()
    if sample == "api":
        base["app_track"] = "api"
    elif sample == "beer":
        base["app_track"] = "ui-direct"
    elif sample == "demo_yelp":
        base["app_track"] = "ui"
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
                sample = "beer"
                tools = ["use_sample", "recommend_surface", "smoke_test_zeus"]
                base["use_sample_args_hint"] = {
                    "sample": "beer",
                    "note": "has_llm_key=false + beer bucket → beer catalog UI, not a travel clone",
                }
                base["app_track"] = "ui-direct"
                base["note"] = (
                    "Prereqs name beer-sample and have no LLM key. "
                    "use_sample(sample=beer); search still needs an LLM key. Do not clone travel."
                )
            else:
                base["note"] = (
                    "has_llm_key=false: smoke_test_agent is not required; "
                    "prefer recommend_surface(needs_llm=false) / Direct path."
                )
    if item_id == "1.2":
        from zeus_dev_helper_mcp.config import llm_key_in_process_env
        from zeus_dev_helper_mcp.llm_key import path_needs_llm_key

        if path_needs_llm_key(cfg) and not llm_key_in_process_env():
            extra = (
                "1.2 stays open until LLM_API_KEY, XAI_API_KEY, or OPENAI_API_KEY "
                "is set in this process. set_prereq(has_llm_key=true) does not count. "
                "Put the secret in the environment or the app .env, never in "
                "config.json api_key_env and never in a tool argument. Then validate_env."
            )
            prior = (base.get("note") or "").strip()
            base["note"] = f"{prior} {extra}".strip()
    elif item_id == "3.2":
        base["note"] = (
            "Copy .env.example to .env and set LLM_API_KEY there. "
            "config.json llm.api_key_env stays the name LLM_API_KEY. "
            "verify_local_setup checks presence only and then marks 3.2 done. "
            "Do not run the app or smoke_test_agent before that."
        )
    # ZDM-15: after the app is chosen, one next action. Host ZEUS_URL does not count.
    if item_id == "0.2" and sample in ("beer", "travel", "api", "demo_yelp"):
        if not _stored_zeus_url(cfg):
            tools = ["set_prereq"]
            base["note"] = (
                "Zeus URL is not stored. set_prereq with the public :8080 URL "
                "the user named. Do not copy the host ZEUS_URL."
            )
        elif sample == "api":
            tools = ["readiness_check", "scaffold_app"]
            base["note"] = (
                "URL is stored. readiness_check, then "
                "scaffold_app(app_kind=api, coding_language=python)."
            )
        elif sample == "demo_yelp":
            tools = ["readiness_check", "use_sample"]
            base["use_sample_args_hint"] = _yelp_use_sample_hint()
            base["note"] = (
                "URL is stored. readiness_check, then use_sample(sample=demo_yelp)."
            )
        else:
            tools = ["readiness_check", "use_sample"]
            base["use_sample_args_hint"] = {
                "sample": sample,
                "note": (
                    "readiness_check first. Then use_sample for this sample. "
                    "Beer search is run_turn with chat_request omitted and needs an LLM key. "
                    "Do not clone travel on the beer path."
                    if sample == "beer"
                    else "readiness_check first, then use_sample."
                ),
            }
            base["note"] = (
                "URL is stored. readiness_check, then use_sample. "
                "List and detail are Direct find + get."
            )
    tools = _keep_enabled(tools)
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
            base["recommended_tools"] = _keep_enabled(list(base["recommended_tools"]))
    base["result_shapes"] = dict(RESULT_SHAPES)
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
                        "recommended_tools": _keep_enabled(
                            list(TOOL_HINTS.get(item.get("id") or "", []))
                        ),
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
