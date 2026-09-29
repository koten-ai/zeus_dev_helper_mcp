"""Write the app ``.env`` from this process. Never echo secret values."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from zeus_dev_helper_mcp.config import (
    LLM_KEY_ENV_NAMES,
    HelperConfig,
    llm_key_in_process_env,
)

_POUR_OFF = (
    "Pour is disabled. Search calls rt.agent.run_turn and this process has no "
    "LLM_API_KEY, XAI_API_KEY, or OPENAI_API_KEY. The list page still loads. "
    "Do not call smoke_test_agent."
)

_CP_SNIPPETS = (
    " && cp -n .env.example .env",
    " && cp .env.example .env",
    "cp -n .env.example .env && ",
    "cp .env.example .env && ",
    "cp -n .env.example .env",
    "cp .env.example .env",
)


def process_username() -> str:
    return (os.environ.get("ZEUS_USERNAME") or os.environ.get("ZEUS_USER") or "").strip()


def process_password() -> str:
    return (os.environ.get("ZEUS_PASSWORD") or "").strip()


def credential_presence(cfg: HelperConfig) -> dict[str, bool]:
    """Stored set_prereq flags versus this process. No secret values."""
    from zeus_dev_helper_mcp.prereqs import load_prereqs

    stored = load_prereqs(cfg)
    return {
        "stored_has_username": bool(stored.get("has_username")),
        "stored_has_password": bool(stored.get("has_password")),
        "process_has_username": bool(process_username()),
        "process_has_password": bool(process_password()),
    }


def basic_login_blocked(cfg: HelperConfig) -> dict[str, Any] | None:
    """Refuse to write an app that claims basic auth when this process cannot log in."""
    mode = (cfg.zeus_auth_mode or "none").strip().lower()
    if mode != "basic":
        return None
    missing: list[str] = []
    if not process_username():
        missing.append("ZEUS_USERNAME")
    if not process_password():
        missing.append("ZEUS_PASSWORD")
    if not missing:
        return None
    return {
        "ok": False,
        "written": False,
        "failure_class": "login_not_in_process",
        "missing_env": missing,
        "next_action": (
            "Set "
            + " and ".join(missing)
            + " in this process before writing the app. "
            "A stored has_username or has_password flag is not a login. "
            "This app was not written."
        ),
    }


def _routing(cfg_value: str, env_name: str) -> str:
    direct = (cfg_value or "").strip()
    if direct:
        return direct
    return (os.environ.get(env_name) or "").strip()


def _llm_assignments() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for name in LLM_KEY_ENV_NAMES:
        value = (os.environ.get(name) or "").strip()
        if value:
            found.append((name, value))
    if found and all(name != "LLM_API_KEY" for name, _value in found):
        found.insert(0, ("LLM_API_KEY", found[0][1]))
    return found


def _env_lines(cfg: HelperConfig) -> tuple[list[str], list[str]]:
    """Lines for a new ``.env``. Values come from routing config or this process."""
    pairs: list[tuple[str, str]] = []
    url = _routing(cfg.zeus_url, "ZEUS_URL")
    if url:
        pairs.append(("ZEUS_URL", url))
    bucket = _routing(cfg.default_bucket, "ZEUS_BUCKET")
    if bucket:
        pairs.append(("ZEUS_BUCKET", bucket))
    scope = _routing(cfg.default_scope, "ZEUS_SCOPE")
    if scope:
        pairs.append(("ZEUS_SCOPE", scope))
    user = process_username()
    if user:
        pairs.append(("ZEUS_USERNAME", user))
    password = process_password()
    if password:
        pairs.append(("ZEUS_PASSWORD", password))
    pairs.extend(_llm_assignments())
    lines = [f"{key}={value}" for key, value in pairs]
    names = [key for key, _value in pairs]
    return lines, names


def _env_key_names(text: str) -> list[str]:
    names: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key.lower().startswith("export "):
            key = key[7:].strip()
        if key and key not in names:
            names.append(key)
    return names


def _write_private(path: Path, text: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, text.encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(path, 0o600)


def _ensure_gitignore(root: Path) -> bool:
    path = root / ".gitignore"
    existing = ""
    if path.is_file():
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError:
            existing = ""
    if ".env" in {line.strip() for line in existing.splitlines()}:
        return True
    if not existing:
        path.write_text(".env\n.venv/\n__pycache__/\n", encoding="utf-8")
    else:
        suffix = "" if existing.endswith("\n") else "\n"
        path.write_text(existing + suffix + ".env\n", encoding="utf-8")
    return True


def ensure_app_env(cfg: HelperConfig, target_dir: str | Path) -> dict[str, Any]:
    """Create a mode 600 ``.env`` when the app does not have one yet.

    An existing non-empty ``.env`` is left as the user wrote it. The result
    lists variable names only.
    """
    root = Path(target_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = root / ".env"
    created = False
    names: list[str] = []
    existing = ""
    if path.is_file():
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError:
            existing = ""
    if existing.strip():
        names = _env_key_names(existing)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    else:
        lines, names = _env_lines(cfg)
        if lines:
            _write_private(path, "\n".join(lines) + "\n")
            created = True
    gitignore = _ensure_gitignore(root)
    present = path.is_file() and bool(names or created)
    return {
        "wrote_env": present,
        "created_env": created,
        "env_keys": names,
        "gitignore": gitignore,
    }


def strip_dotenv_copy(run: str) -> str:
    for snippet in _CP_SNIPPETS:
        run = run.replace(snippet, "")
    return run.strip()


def annotate_app_env(cfg: HelperConfig, root: str | Path, result: dict[str, Any]) -> dict[str, Any]:
    info = ensure_app_env(cfg, root)
    result["app_env"] = {
        "wrote_env": info["wrote_env"],
        "created_env": info["created_env"],
        "env_keys": list(info["env_keys"]),
        "gitignore": info["gitignore"],
    }
    if info["wrote_env"] and result.get("run"):
        result["run"] = strip_dotenv_copy(str(result["run"]))
    return result


def annotate_pour(result: dict[str, Any], *, catalog_ui: bool = False) -> dict[str, Any]:
    """Record whether a run_turn search can run. Never include the key."""
    if llm_key_in_process_env():
        result["pour_enabled"] = True
        tools = result.get("recommended_tools")
        if isinstance(tools, list):
            result["recommended_tools"] = [name for name in tools if name != "smoke_test_agent"]
        return result
    reason = _POUR_OFF if catalog_ui else (
        "This process has no LLM_API_KEY, XAI_API_KEY, or OPENAI_API_KEY. "
        "Do not call smoke_test_agent."
    )
    result["pour_enabled"] = False
    result["pour_reason"] = reason
    tools = result.get("recommended_tools")
    if isinstance(tools, list):
        result["recommended_tools"] = [name for name in tools if name != "smoke_test_agent"]
    else:
        result["recommended_tools"] = []
    action = str(result.get("next_action") or "")
    action = action.replace("before uvicorn or smoke_test_agent", "before uvicorn")
    action = action.replace("before main.py or smoke_test_agent", "before main.py")
    action = action.replace(" or smoke_test_agent", "")
    if "smoke_test_agent" in action:
        action = action.replace("smoke_test_agent", "")
    action = " ".join(action.split())
    if reason not in action:
        action = f"{action} {reason}".strip()
    result["next_action"] = action
    return result
