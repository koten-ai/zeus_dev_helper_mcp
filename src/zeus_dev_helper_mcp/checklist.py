"""In-memory first-app checklist (ZDH master phases 0–7)."""

from __future__ import annotations

import json
import re
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
            {
                "id": "3.2",
                "title": "App .env has the LLM key; api_key_env is the name",
                "status": "todo",
            },
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
        "1.1": (
            "kotenai-zeus-client needs Python 3.11 or newer. "
            "doctor and verify_local_setup check python3 on PATH, "
            "or the app .venv interpreter when that file exists. "
            "website_green does not run pip on an older interpreter. "
            "Recreate the virtualenv with Python 3.11 or newer, then install again."
        ),
        "1.2": (
            "Set ZEUS_URL with set_prereq. The form does not collect a password or an "
            "API key. LLM_API_KEY, XAI_API_KEY, or OPENAI_API_KEY must be set in this "
            "process when the path calls the model. has_llm_key=true does not count. "
            "Then validate_env. Beer lists do not keep 1.2 open. Pour stays off until "
            "the key is in the app .env. smoke_test_agent and verify_local_setup "
            "still require it for that question box. Travel and API turns keep 1.2 "
            "open until that variable is set."
        ),
        "3.2": (
            "Copy .env.example to .env and set LLM_API_KEY there. Leave config.json "
            "llm.api_key_env as that name. verify_local_setup checks presence only, "
            "then marks 3.2 done. That call also imports zeus_client in this Helper "
            "process. The app .venv does not satisfy the import. Do not paste the "
            "secret into api_key_env or into a tool argument."
        ),
        "2.1": "curl $ZEUS_URL/healthz — not Hub :9091.",
        "4.1": "list_catalog_modes / fetch_chat_request from zeus_chat_request; then stamp on Zeus.",
        "5.2": "rt.agent.run_turn one turn; log session_id; see recipe 01.",
    }
    return hints.get(item_id, "See for-ai-agents.md and next_step docs links.")


_ENV_LITERAL = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)+$")
_PLACEHOLDER_HASH = "TO_BE_FILLED"
_LOCAL_HASHES = frozenset({"compute_local", "compute-local", "local"})
_CATALOG_EVIDENCE = "scope catalog on disk"
_PIN_EVIDENCE = "scope_contracts pinned"


def _concrete(value: str, fallback: str) -> str:
    text = (value or "").strip()
    if text and _ENV_LITERAL.fullmatch(text) is None:
        return text
    return (fallback or "").strip()


def _read_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _is_template_repo(root: Path) -> bool:
    """A zeus_chat_request checkout is the template index, not the app store."""
    if not root.is_dir():
        return False
    if (root / "v2").is_dir() and (root / "catalog-index.json").is_file():
        return True
    manifest = _read_object(root / "manifest.json")
    catalogs = manifest.get("catalogs")
    if isinstance(catalogs, list) and catalogs:
        return True
    if manifest.get("schema_version"):
        return True
    return str(manifest.get("repo") or "").strip() == "koten-ai/zeus_chat_request"


def bound_app_root(cfg: HelperConfig) -> Path | None:
    """Directory recorded for the checklist sample. Does not create state."""
    data = _read_object(cfg.state_dir / "checklist.json")
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    from zeus_dev_helper_mcp.sample_log import bound_sample_dirs, sample_kind

    kind = sample_kind(str((meta or {}).get("sample") or ""))
    if not kind:
        return None
    raw = str(bound_sample_dirs(cfg).get(kind) or "").strip()
    if not raw:
        return None
    root = Path(raw).expanduser()
    return root if root.is_dir() else None


def _identity(cfg: HelperConfig, config: dict[str, Any]) -> tuple[str, str, str]:
    target = config.get("target") if isinstance(config.get("target"), dict) else {}
    settings = config.get("settings") if isinstance(config.get("settings"), dict) else {}
    bucket = _concrete(str(target.get("bucket") or ""), cfg.default_bucket or "")
    scope = _concrete(str(target.get("scope") or ""), cfg.default_scope or "")
    mode = _concrete(str(settings.get("mode") or ""), cfg.default_mode or "analytics")
    return bucket, scope, mode


def _chat_dir_for_app(root: Path, config: dict[str, Any]) -> Path | None:
    raw = config.get("chat_requests_dir")
    named: Path | None = None
    if isinstance(raw, str) and raw.strip():
        named = Path(raw.strip()).expanduser()
        if not named.is_absolute():
            named = root / named
    if named is not None and named.is_dir() and not _is_template_repo(named):
        return named
    fallback = root / "data" / "chat_requests"
    has_app = (root / "main.py").is_file() or (root / "pyproject.toml").is_file()
    if fallback.is_dir() and has_app and not _is_template_repo(fallback):
        return fallback
    return None


def _catalog_names(mode: str) -> list[str]:
    name = (mode or "").strip() or "analytics"
    if name == "default":
        return ["chat_request_v2.json", "chat_request.json"]
    return [
        f"chat_request_{name}_v2.json",
        f"chat_request_{name}.json",
        f"{name}.json",
    ]


def _scope_catalog_exists(chat_dir: Path, bucket: str, scope: str, mode: str) -> bool:
    if not bucket or not scope or not mode or not chat_dir.is_dir():
        return False
    tail = scope.removeprefix("_")
    scope_dir = chat_dir / f"{bucket}__{tail}"
    names = _catalog_names(mode)
    for folder in (scope_dir, scope_dir / "min", chat_dir, chat_dir / "min"):
        for filename in names:
            if (folder / filename).is_file():
                return True
    return False


def _real_hash(value: object) -> bool:
    text = str(value or "").strip()
    if not text or _PLACEHOLDER_HASH in text:
        return False
    return text.lower() not in _LOCAL_HASHES


def _has_real_pin(config: dict[str, Any], bucket: str, scope: str, mode: str) -> bool:
    if not bucket or not scope or not mode:
        return False
    zeus = config.get("zeus") if isinstance(config.get("zeus"), dict) else {}
    contracts = zeus.get("scope_contracts") if isinstance(zeus, dict) else None
    if not isinstance(contracts, dict):
        return False
    row = contracts.get(f"{bucket}/{scope}")
    if not isinstance(row, dict):
        return False
    pin = row.get(mode)
    if not isinstance(pin, dict):
        return False
    return _real_hash(pin.get("contract_hash"))


def bound_catalog_done(cfg: HelperConfig, root: Path | None = None) -> dict[str, str]:
    """4.1 / 4.2 evidence when the bound app already has the catalog and pin.

    Read-only. A fetched template and a ``bind_contract`` snippet do not count.
    """
    app = root if root is not None else bound_app_root(cfg)
    if app is None:
        return {}
    app = Path(app)
    if not app.is_dir():
        return {}
    config = _read_object(app / "config.json")
    bucket, scope, mode = _identity(cfg, config)
    found: dict[str, str] = {}
    chat_dir = _chat_dir_for_app(app, config)
    if chat_dir is not None and _scope_catalog_exists(chat_dir, bucket, scope, mode):
        found["4.1"] = _CATALOG_EVIDENCE
    if _has_real_pin(config, bucket, scope, mode):
        found["4.2"] = _PIN_EVIDENCE
    return found


def sync_bound_catalog_checklist(
    cfg: HelperConfig,
    root: Path | None = None,
) -> dict[str, str]:
    """Upgrade todo or blocked 4.1 / 4.2. Leave an existing done row unchanged."""
    found = bound_catalog_done(cfg, root)
    if not found:
        return {}
    data = load_checklist(cfg)
    changed = False
    applied: dict[str, str] = {}
    for phase in data.get("phases") or []:
        if not isinstance(phase, dict):
            continue
        items = phase.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "")
            evidence = found.get(item_id)
            if not evidence or item.get("status") not in ("todo", "blocked"):
                continue
            item["status"] = "done"
            item["evidence"] = evidence
            changed = True
            applied[item_id] = evidence
    if changed:
        save_checklist(cfg, data)
    return applied
