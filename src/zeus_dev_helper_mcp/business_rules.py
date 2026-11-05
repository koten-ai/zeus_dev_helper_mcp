"""Write named business rules into the Zeus app the user is working on.

The client splices ``ClientSettings.rules`` into the model prompt when
``run_turn`` receives the settings loaded from ``config.json``. This module
updates ``settings.rules`` and does not edit application Python. When the app
builds ``ClientSettings`` itself, the result sets ``wire_required``.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zeus_dev_helper_mcp.checklist import _is_template_repo, bound_app_root
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.env_questions import HOST_FORM
from zeus_dev_helper_mcp.sample_log import bound_sample_dirs, sample_kind

# Same ids as zeus_client.domain.policy.JAILBREAK_RULE_IDS. The SDK owns them.
JAILBREAK_RULE_IDS = frozenset(
    {
        "ignore_system",
        "no_prompt_dump",
        "no_unrestricted_agent",
        "no_invent_data",
        "no_secrets",
        "stay_in_company_context",
    }
)

NOT_ZEUS_MESSAGE = "app is not a Zeus enabled app"
_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SECRET_RE = re.compile(
    r"(?i)(?:\bsk-[a-z0-9_-]{8,}\b|\bxai-[a-z0-9_-]{8,}\b|\bbearer\s+\S+"
    r"|api[_-]?key\s*[:=]|password\s*[:=])"
)
_SKIP_DIRS = frozenset(
    {".venv", "venv", "node_modules", "__pycache__", ".git", "data", "frontend"}
)
_API_NAMES = frozenset({"api", "rest", "api_only", "fastapi"})
_LOADED_SETTINGS = (
    "settings=cfg.settings",
    "settings=rt.config.settings",
    "settings=_runtime.config.settings",
)
_WIRE_NEXT = (
    "Pass rules from config.json settings.rules into the ClientSettings "
    "constructor. The tool does not edit Python. Restart the app after that edit."
)
_RESTART_NEXT = "Restart the app so the new rules load."
_READ_NEXT = "These are the business rules on this app."
_UNCHANGED_NEXT = "These rules are already on this app."


@dataclass(frozen=True)
class _ChosenApp:
    root: Path
    sample: str


def inject_business_rules(
    cfg: HelperConfig,
    *,
    app_dir: str = "",
    sample: str = "",
    rules: dict[str, Any] | None = None,
    remove: list[Any] | None = None,
    replace: bool = False,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Merge ``settings.rules`` into one Zeus app. Does not call the model."""
    work = cwd.expanduser().resolve() if cwd is not None else Path.cwd().resolve()
    incoming, removed, problem = _validate(rules, remove)
    if problem is not None:
        return problem

    chosen = _resolve(cfg, app_dir=app_dir, sample=sample, cwd=work)
    if isinstance(chosen, dict):
        return chosen
    root = chosen.root
    kind = chosen.sample

    reading = not incoming and not removed and not replace
    loaded = _read_config(root / "config.json")
    if loaded is None:
        return _not_zeus(root)
    wired = _is_wired(root)
    if reading:
        return _success(
            root=root,
            sample=kind,
            rules=_stored_rules(loaded),
            changes=[],
            written=False,
            wired=wired,
            next_action=_READ_NEXT if wired else _WIRE_NEXT,
        )

    settings = loaded.get("settings")
    if settings is None:
        settings = {}
        loaded["settings"] = settings
    if not isinstance(settings, dict):
        return _invalid("settings", "config.json settings is not an object")
    previous = _stored_rules(loaded)
    working, changes = _merge(previous, incoming, removed, replace)
    wrote = working != previous
    if wrote:
        settings["rules"] = working
        _write_config(root / "config.json", loaded)
    if wired:
        next_action = _RESTART_NEXT if wrote else _UNCHANGED_NEXT
    else:
        next_action = _WIRE_NEXT
    return _success(
        root=root,
        sample=kind,
        rules=working,
        changes=changes,
        written=wrote,
        wired=wired,
        next_action=next_action,
    )


def _success(
    *,
    root: Path,
    sample: str,
    rules: dict[str, str],
    changes: list[dict[str, str]],
    written: bool,
    wired: bool,
    next_action: str,
) -> dict[str, Any]:
    return {
        "ok": True,
        "app_dir": str(root),
        "sample": sample,
        "rules": rules,
        "changes": changes,
        "written": written,
        "injected": wired,
        "wire_required": not wired,
        "next_action": next_action,
    }


def _merge(
    previous: dict[str, str],
    incoming: dict[str, str],
    removed: list[str],
    replace: bool,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    working: dict[str, str] = {} if replace else dict(previous)
    changes: list[dict[str, str]] = []
    for rule_id, text in incoming.items():
        if previous.get(rule_id) == text:
            action = "unchanged"
        elif rule_id in previous:
            action = "replaced"
        else:
            action = "added"
        working[rule_id] = text
        changes.append({"id": rule_id, "action": action})
    seen: set[str] = set()
    for rule_id in removed:
        if rule_id in seen:
            continue
        if rule_id in working or rule_id in previous:
            working.pop(rule_id, None)
            changes.append({"id": rule_id, "action": "removed"})
            seen.add(rule_id)
    if replace:
        for rule_id in previous:
            if rule_id not in working and rule_id not in seen:
                changes.append({"id": rule_id, "action": "removed"})
                seen.add(rule_id)
    return working, changes


def _validate(
    rules: dict[str, Any] | None,
    remove: list[Any] | None,
) -> tuple[dict[str, str], list[str], dict[str, Any] | None]:
    if rules is None:
        incoming: dict[str, Any] = {}
    elif isinstance(rules, dict):
        incoming = dict(rules)
    else:
        return {}, [], _invalid("", "rules must be an object of id to sentence")
    removed = [str(item) for item in remove] if remove else []
    jailbreaks = [str(key) for key in incoming if str(key) in JAILBREAK_RULE_IDS]
    if jailbreaks:
        return {}, [], {
            "ok": False,
            "failure_class": "jailbreak_rule_protected",
            "ids": jailbreaks,
            "next_action": (
                "Leave the SDK jailbreak pack alone. Use a different rule id. "
                "The app file was not changed."
            ),
        }
    cleaned: dict[str, str] = {}
    for key, value in incoming.items():
        rule_id = str(key)
        if _ID_RE.fullmatch(rule_id) is None:
            return {}, [], _invalid(rule_id, "id must be snake_case")
        if not isinstance(value, str):
            return {}, [], _invalid(rule_id, "text must be one sentence")
        text = value.strip()
        if not _one_sentence(text):
            return {}, [], _invalid(rule_id, "text must be one sentence of at most 400 characters")
        if _SECRET_RE.search(text):
            return {}, [], _invalid(rule_id, "text looks like a secret")
        cleaned[rule_id] = text
    for rule_id in removed:
        if _ID_RE.fullmatch(rule_id) is None:
            return {}, [], _invalid(rule_id, "id must be snake_case")
    return cleaned, removed, None


def _one_sentence(text: str) -> bool:
    if not text or len(text) > 400 or "\n" in text or "\r" in text:
        return False
    marks = [match.start() for match in re.finditer(r"[.!?]", text)]
    if len(marks) > 1:
        return False
    return not marks or marks[0] == len(text) - 1


def _invalid(rule_id: str, reason: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "failure_class": "rule_invalid",
        "next_action": f"{reason}. The app file was not changed.",
    }
    if rule_id:
        payload["id"] = rule_id
    return payload


def _not_zeus(path: Path) -> dict[str, Any]:
    return {
        "ok": False,
        "failure_class": "not_a_zeus_app",
        "message": NOT_ZEUS_MESSAGE,
        "app_dir": str(path),
        "next_action": NOT_ZEUS_MESSAGE,
    }


def _resolve(
    cfg: HelperConfig,
    *,
    app_dir: str,
    sample: str,
    cwd: Path,
) -> _ChosenApp | dict[str, Any]:
    explicit = app_dir.strip()
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            path = cwd / path
        path = path.resolve()
        if not _is_zeus_app(path):
            return _not_zeus(path)
        return _ChosenApp(path, _sample_for_path(cfg, path))

    named = sample.strip()
    if named:
        kind = _normalize_sample(named)
        if kind is None:
            return _ask(cfg, sample=named)
        root = _dir_for_sample(cfg, kind)
        if root is None:
            return _ask(cfg, sample=kind, missing=True)
        if not _is_zeus_app(root):
            return _not_zeus(root)
        return _ChosenApp(root.resolve(), kind)

    if _is_zeus_app(cwd):
        return _ChosenApp(cwd, _sample_for_path(cfg, cwd))

    current = _checklist_app(cfg)
    if current is not None:
        return current
    return _ask(cfg)


def _ask(
    cfg: HelperConfig,
    *,
    sample: str = "",
    missing: bool = False,
) -> dict[str, Any]:
    options = [
        {"label": kind, "description": str(path)}
        for kind, path in _candidates(cfg)
    ]
    if options and not missing:
        question: dict[str, Any] = {
            "question": "Which app should receive the business rule?",
            "options": options,
        }
        detail = "The selected label is sample on the next inject_business_rules call."
    else:
        question = {
            "question": "Which directory should receive the business rule?",
            "prompt": "Path to the Zeus app",
        }
        detail = "Pass that path as app_dir on the next inject_business_rules call."
    if missing and sample:
        detail = f"No directory is recorded for {sample}. {detail}"
    return {
        "ok": False,
        "failure_class": "app_required",
        "sample": sample,
        "ask_user": [question],
        "next_action": (
            f"Ask where the business rule should go. {HOST_FORM} {detail} "
            "A path that is not a Zeus app is not used."
        ),
    }


def _checklist_app(cfg: HelperConfig) -> _ChosenApp | None:
    path = cfg.state_dir / "checklist.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    meta = data.get("meta") if isinstance(data, dict) else None
    if not isinstance(meta, dict):
        return None
    kind = _normalize_sample(str(meta.get("sample") or ""))
    if kind is None:
        return None
    if kind == "api":
        root = _scaffold_dir(cfg)
    else:
        root = bound_app_root(cfg)
    if root is None or not _is_zeus_app(root):
        return None
    return _ChosenApp(root.resolve(), kind)


def _dir_for_sample(cfg: HelperConfig, kind: str) -> Path | None:
    if kind == "api":
        return _scaffold_dir(cfg)
    raw = bound_sample_dirs(cfg).get(kind, "")
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_dir() else None


def _scaffold_dir(cfg: HelperConfig) -> Path | None:
    path = cfg.state_dir / "checklist.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    phases = data.get("phases") if isinstance(data, dict) else None
    if not isinstance(phases, list):
        return None
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        for item in phase.get("items") or []:
            if not isinstance(item, dict) or item.get("id") != "3.1":
                continue
            evidence = str(item.get("evidence") or "")
            match = re.match(r"scaffold=(?:api|cli):(.+)", evidence)
            if match is None:
                return None
            root = Path(match.group(1).strip()).expanduser()
            return root if root.is_dir() else None
    return None


def _candidates(cfg: HelperConfig) -> list[tuple[str, Path]]:
    rows: list[tuple[str, Path]] = []
    for kind, raw in bound_sample_dirs(cfg).items():
        path = Path(raw).expanduser()
        if _is_zeus_app(path):
            rows.append((kind, path.resolve()))
    api = _scaffold_dir(cfg)
    if api is not None and _is_zeus_app(api):
        rows.append(("api", api.resolve()))
    return rows


def _sample_for_path(cfg: HelperConfig, root: Path) -> str:
    try:
        resolved = root.expanduser().resolve()
    except OSError:
        return ""
    for kind, path in _candidates(cfg):
        if path == resolved:
            return kind
    return ""


def _normalize_sample(name: str) -> str | None:
    text = (name or "").strip().lower()
    if not text:
        return None
    if text in _API_NAMES:
        return "api"
    return sample_kind(text)


def _helper_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _is_zeus_app(root: Path) -> bool:
    try:
        resolved = root.expanduser().resolve()
    except OSError:
        return False
    if not resolved.is_dir() or resolved == _helper_root():
        return False
    if _is_template_repo(resolved):
        return False
    config = _read_config(resolved / "config.json")
    zeus = config.get("zeus") if isinstance(config, dict) else None
    return isinstance(zeus, dict)


def _read_config(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _stored_rules(config: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(config, dict):
        return {}
    settings = config.get("settings")
    if not isinstance(settings, dict):
        return {}
    raw = settings.get("rules")
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items() if value is not None}


def _write_config(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _py_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name for name in dirnames if name not in _SKIP_DIRS and not name.startswith(".")
        ]
        for name in filenames:
            if name.endswith(".py"):
                found.append(Path(dirpath) / name)
    return found


def _is_wired(root: Path) -> bool:
    """True when run_turn receives settings loaded from config.json.

    A hand-built ``ClientSettings`` drops ``settings.rules``, so any such call
    in the tree means the rules are not injected yet.
    """
    files = _py_files(root)
    if not files:
        return False
    chunks: list[str] = []
    for path in files:
        try:
            chunks.append(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            return False
    text = "\n".join(chunks)
    if "ClientSettings(" in text:
        return False
    return any(marker in text for marker in _LOADED_SETTINGS)
