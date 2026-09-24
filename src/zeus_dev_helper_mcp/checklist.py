"""In-memory first-app checklist (ZDH master phases 0–7)."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.docs_links import docs_url

PHASES: list[dict[str, Any]] = [
    {
        "id": "0_intent",
        "title": "Intent & sample path",
        "items": [
            {"id": "0.1", "title": "Choose single-agent first app", "status": "todo"},
            {"id": "0.2", "title": "Pick sample or custom domain", "status": "todo"},
        ],
    },
    {
        "id": "1_prereqs",
        "title": "Prerequisites",
        "items": [
            {"id": "1.1", "title": "Python 3.11+ / pip", "status": "todo"},
            {"id": "1.2", "title": "ZEUS_URL and LLM key available", "status": "todo"},
        ],
    },
    {
        "id": "2_platform",
        "title": "Platform readiness",
        "items": [
            {"id": "2.1", "title": "Zeus :8080 reachable", "status": "todo"},
            {"id": "2.2", "title": "Auth works for principal", "status": "todo"},
            {"id": "2.3", "title": "Scope enabled", "status": "todo"},
        ],
    },
    {
        "id": "3_project",
        "title": "Project on disk",
        "items": [
            {"id": "3.1", "title": "Scaffold or clone sample", "status": "todo"},
            {"id": "3.2", "title": "Config / env template present", "status": "todo"},
        ],
    },
    {
        "id": "4_bind",
        "title": "Bind Zeus (catalog + contract)",
        "items": [
            {
                "id": "4.1",
                "title": "Fetch or sync chat_request (zeus_chat_request / live stamp)",
                "status": "todo",
            },
            {"id": "4.2", "title": "Pin scope_contracts after stamp", "status": "todo"},
        ],
    },
    {
        "id": "5_green",
        "title": "First green path",
        "items": [
            {"id": "5.1", "title": "smoke_test_zeus", "status": "todo"},
            {"id": "5.2", "title": "smoke_test_agent (tool call + session_id)", "status": "todo"},
        ],
    },
    {
        "id": "6_customize",
        "title": "Customize",
        "items": [
            {"id": "6.1", "title": "Multi-turn and/or hooks", "status": "todo"},
        ],
    },
    {
        "id": "7_prodish",
        "title": "Production-ish single-agent",
        "items": [
            {"id": "7.1", "title": "No anti-patterns; secrets out of prompts", "status": "todo"},
        ],
    },
]


def _state_path(cfg: HelperConfig) -> Path:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    return cfg.state_dir / "checklist.json"


def load_checklist(cfg: HelperConfig) -> dict[str, Any]:
    path = _state_path(cfg)
    if path.is_file():
        return json.loads(path.read_text())
    data = {
        "project": "default",
        "phases": deepcopy(PHASES),
        "docs": {
            "for_ai_agents": (
                docs_url("zeus-client/for-ai-agents.md")
            ),
            "using_zeus_client": (
                docs_url("zeus-client/using-zeus-client.md")
            ),
            "dev_helper_mcp": (
                docs_url("zeus-client/dev-helper-mcp.md")
            ),
            "agent_index": (
                docs_url("agent-index.yaml")
            ),
        },
    }
    save_checklist(cfg, data)
    return data


def save_checklist(cfg: HelperConfig, data: dict[str, Any]) -> None:
    path = _state_path(cfg)
    path.write_text(json.dumps(data, indent=2) + "\n")


def set_item_status(
    cfg: HelperConfig,
    item_id: str,
    status: str,
    *,
    evidence: str | None = None,
) -> dict[str, Any]:
    if status not in ("todo", "done", "blocked", "skipped"):
        raise ValueError("status must be todo|done|blocked|skipped")
    data = load_checklist(cfg)
    found = False
    for phase in data["phases"]:
        for item in phase["items"]:
            if item["id"] == item_id:
                item["status"] = status
                if evidence is not None:
                    item["evidence"] = evidence
                found = True
    if not found:
        raise KeyError(f"unknown item_id: {item_id}")
    save_checklist(cfg, data)
    return data


def next_step(cfg: HelperConfig) -> dict[str, Any]:
    data = load_checklist(cfg)
    for phase in data["phases"]:
        for item in phase["items"]:
            if item["status"] in ("todo", "blocked"):
                return {
                    "phase_id": phase["id"],
                    "phase_title": phase["title"],
                    "item": item,
                    "hint": _hint_for(item["id"], cfg),
                    "docs": data.get("docs"),
                }
    return {
        "phase_id": None,
        "item": None,
        "message": "All checklist items done or skipped.",
        "docs": data.get("docs"),
    }


def _hint_for(item_id: str, cfg: HelperConfig) -> str:
    hints = {
        "0.1": "Read using-zeus-client.md; stay single-agent until green.",
        "1.2": (
            "If no Zeus URL is stored, the tool form asks for the public :8080 URL. "
            "Credentials stay in ZEUS_USERNAME / ZEUS_PASSWORD or ZEUS_BEARER_TOKEN; "
            "the form does not collect the password. Then validate_env."
        ),
        "2.1": "curl $ZEUS_URL/healthz — not Hub :9091.",
        "4.1": "list_catalog_modes / fetch_chat_request from zeus_chat_request; then stamp on Zeus.",
        "5.2": "rt.agent.run_turn one turn; log session_id; see recipe 01.",
    }
    return hints.get(item_id, "See for-ai-agents.md and next_step docs links.")
