"""Write named business rules into the Zeus app the user is working on.

The client splices ``ClientSettings.rules`` into the model prompt. This module
only updates the app ``config.json`` and, for known call sites that drop those
settings, the constructor that builds them.
"""

from __future__ import annotations

import json
import os
import re
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
_SCAFFOLD_NEEDLE = "settings=ClientSettings(ai_process_result=False)"
_SKIP_DIRS = frozenset(
    {".venv", "venv", "node_modules", "__pycache__", ".git", "data", "frontend"}
)
_API_NAMES = frozenset({"api", "rest", "api_only", "fastapi"})
_TRAVEL_RULES = (
    'dict(settings_raw["rules"]) if isinstance(settings_raw.get("rules"), dict) else None'
)
_YELP_RULES = (
    'dict(cfg["settings"]["rules"]) if isinstance(cfg.get("settings"), dict) '
    'and isinstance(cfg["settings"].get("rules"), dict) else None'
)
_WIRE_NEXT = (
    "Pass rules from config.json settings.rules into the ClientSettings "
    "constructor. Restart the app after that edit."
)
_RESTART_NEXT = "Restart the app so the new rules load."


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
    if "ok" in chosen:
        return chosen
    root: Path = chosen["root"]
    kind: str = chosen["sample"]

    reading = not incoming and not removed and not replace
    if reading:
        current = _stored_rules(_read_config(root / "config.json"))
        wired = _is_wired(root)
        return {
            "ok": True,
            "app_dir": str(root),
            "sample": kind,
            "rules": current,
            "changes": [],
            "written": False,
            "injected": wired,
            "wire_required": not wired,
            "next_action": "These are the business rules on this app.",
        }

    loaded = _read_config(root / "config.json")
    if loaded is None:
        return _not_zeus(root)
    settings = loaded.get("settings")
    if settings is None:
        settings = {}
        loaded["settings"] = settings
    if not isinstance(settings, dict):
        return _invalid("settings", "config.json settings is not an object")
    previous = _stored_rules(loaded)
    working = {} if replace else dict(previous)
    changes: list[dict[str, str]] = []
    for rule_id, text in incoming.items():
        if rule_id in working and working[rule_id] == text:
            action = "unchanged"
        elif rule_id in working:
            action = "replaced"
        else:
            action = "added"
        working[rule_id] = text
        changes.append({"id": rule_id, "action": action})
    if replace:
        for rule_id in previous:
            if rule_id not in incoming and rule_id not in removed:
                changes.append({"id": rule_id, "action": "removed"})
    for rule_id in removed:
        if rule_id in working:
            working.pop(rule_id)
            changes.append({"id": rule_id, "action": "removed"})
    wrote = working != previous
    if wrote:
        settings["rules"] = working
        _write_config(root / "config.json", loaded)
    patched = _patch_known_calls(root)
    wired = _is_wired(root)
    if wired:
        next_action = _RESTART_NEXT if wrote or patched else "These rules are already on this app."
    else:
        next_action = _WIRE_NEXT
    return {
        "ok": True,
        "app_dir": str(root),
        "sample": kind,
        "rules": working,
        "changes": changes,
        "written": wrote,
        "patched": patched,
        "injected": wired,
        "wire_required": not wired,
        "next_action": next_action,
    }


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
) -> dict[str, Any]:
    explicit = app_dir.strip()
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            path = cwd / path
        path = path.resolve()
        if not _is_zeus_app(path):
            return _not_zeus(path)
        return {"root": path, "sample": _sample_for_path(cfg, path)}

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
        return {"root": root.resolve(), "sample": kind}

    if _is_zeus_app(cwd):
        return {"root": cwd, "sample": _sample_for_path(cfg, cwd)}

    current = _checklist_app(cfg)
    if current is not None:
        return {"root": current[0], "sample": current[1]}
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


def _checklist_app(cfg: HelperConfig) -> tuple[Path, str] | None:
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
    return root.resolve(), kind


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
        dirnames[:] = [name for name in dirnames if name not in _SKIP_DIRS and not name.startswith(".")]
        for name in filenames:
            if name.endswith(".py"):
                found.append(Path(dirpath) / name)
    return found


def _patch_known_calls(root: Path) -> list[str]:
    patched: list[str] = []
    main = root / "main.py"
    if main.is_file():
        original = main.read_text(encoding="utf-8")
        updated = _patch_scaffold(original)
        if updated != original:
            main.write_text(updated, encoding="utf-8")
            patched.append(str(main))
    targets = (
        (root / "src" / "travel_planner" / "runtime_factory.py", _TRAVEL_RULES),
        (root / "src" / "local_guide" / "live_search.py", _YELP_RULES),
    )
    for path, expr in targets:
        if not path.is_file():
            continue
        original = path.read_text(encoding="utf-8")
        updated = _insert_rules_kw(original, expr)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            patched.append(str(path))
    return patched


def _patch_scaffold(text: str) -> str:
    if _SCAFFOLD_NEEDLE not in text:
        return text
    parts: list[str] = []
    rest = text
    while _SCAFFOLD_NEEDLE in rest:
        index = rest.index(_SCAFFOLD_NEEDLE)
        window = rest[max(0, index - 500) : index]
        runtime = window.rfind("_runtime.agent.run_turn")
        plain = window.rfind("rt.agent.run_turn")
        replacement = (
            "settings=_runtime.config.settings"
            if runtime > plain
            else "settings=rt.config.settings"
        )
        parts.append(rest[:index])
        parts.append(replacement)
        rest = rest[index + len(_SCAFFOLD_NEEDLE) :]
    parts.append(rest)
    return "".join(parts)


def _insert_rules_kw(text: str, expr: str) -> str:
    key = "ClientSettings("
    search = 0
    while True:
        found = text.find(key, search)
        if found < 0:
            return text
        open_paren = found + len(key) - 1
        close = _match_paren(text, open_paren)
        if close is None:
            return text
        body = text[open_paren + 1 : close]
        if re.search(r"\brules\s*=", body):
            search = close + 1
            continue
        indent = "            "
        for line in body.splitlines():
            if line.strip():
                indent = line[: len(line) - len(line.lstrip())]
                break
        tail_match = re.search(r"\s*$", body)
        tail = tail_match.group(0) if tail_match else ""
        core = body[: len(body) - len(tail)] if tail else body
        if core and not core.rstrip().endswith(","):
            core = core.rstrip() + ","
        spacer = tail if tail else "\n"
        new_body = f"{core}\n{indent}rules={expr},{spacer}"
        return text[: open_paren + 1] + new_body + text[close:]


def _match_paren(text: str, open_index: int) -> int | None:
    depth = 0
    for index in range(open_index, len(text)):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def _calls_have_rules(calls: list[str]) -> bool:
    return bool(calls) and all(re.search(r"\brules\s*=", call) for call in calls)


def _client_settings_calls(text: str) -> list[str]:
    calls: list[str] = []
    key = "ClientSettings("
    search = 0
    while True:
        found = text.find(key, search)
        if found < 0:
            return calls
        open_paren = found + len(key) - 1
        close = _match_paren(text, open_paren)
        if close is None:
            return calls
        calls.append(text[open_paren + 1 : close])
        search = close + 1


def _is_wired(root: Path) -> bool:
    files = _py_files(root)
    if not files:
        return False
    blobs = [(path, path.read_text(encoding="utf-8")) for path in files]
    for path, text in blobs:
        calls = _client_settings_calls(text)
        if path.name == "runtime_factory.py" and calls and not _calls_have_rules(calls):
            return False
        if path.name == "live_search.py" and "run_agent(" in text and not calls:
            return False
        if path.name == "live_search.py" and calls and not _calls_have_rules(calls):
            return False
    for _path, text in blobs:
        if _SCAFFOLD_NEEDLE in text:
            return False
        calls = _client_settings_calls(text)
        if calls and not _calls_have_rules(calls):
            return False
    joined = "\n".join(text for _path, text in blobs)
    if "settings=cfg.settings" in joined or "settings=rt.config.settings" in joined:
        return True
    if "settings=_runtime.config.settings" in joined:
        return True
    if any(_calls_have_rules(_client_settings_calls(text)) for _path, text in blobs):
        return True
    return "ZeusRuntime.from_config" in joined and "ClientSettings(" not in joined
