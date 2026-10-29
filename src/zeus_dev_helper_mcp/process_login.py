"""Put Zeus login into this already-running process.

``set_prereq`` keeps presence flags only. This tool reads a mode-600 env file
and sets ``ZEUS_USERNAME`` / ``ZEUS_PASSWORD`` (and the LLM key names) on
``os.environ``. The password is never a tool argument and never a result field.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

_AUTH_MODES = {"none", "basic", "bearer"}
_LOGIN_KEYS = (
    "ZEUS_AUTH_MODE",
    "ZEUS_USERNAME",
    "ZEUS_USER",
    "ZEUS_PASSWORD",
    "ZEUS_BEARER_TOKEN",
    "ZEUS_TOKEN",
    "LLM_API_KEY",
    "XAI_API_KEY",
    "OPENAI_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
)
_LOGIN_FILE_KEYS = {
    "ZEUS_USERNAME",
    "ZEUS_USER",
    "ZEUS_PASSWORD",
    "ZEUS_BEARER_TOKEN",
    "ZEUS_TOKEN",
}


def _parse_env(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, raw = stripped.partition("=")
        key = key.strip()
        if key.lower().startswith("export "):
            key = key[7:].strip()
        if key not in _LOGIN_KEYS:
            continue
        value = raw.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key == "ZEUS_AUTH_MODE":
            value = value.strip().lower()
            if value not in _AUTH_MODES:
                continue
        if value:
            found[key] = value
    return found


def _private_file(path: Path) -> bool:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return False
    return mode & 0o077 == 0


def load_process_login(env_file: str) -> dict[str, Any]:
    """Load login from ``env_file`` into this process.

    The file must be mode 600. Allowed keys are ``ZEUS_AUTH_MODE``,
    ``ZEUS_USERNAME``, ``ZEUS_PASSWORD``, ``ZEUS_BEARER_TOKEN``, the LLM
    key names, ``LLM_BASE_URL``, and ``LLM_MODEL``. ``ZEUS_AUTH_MODE`` is
    ``none``, ``basic``, or ``bearer``. The result lists names only.
    """
    raw = (env_file or "").strip()
    if not raw:
        from zeus_dev_helper_mcp.env_questions import attach_login_ask, login_ask_text

        return attach_login_ask(
            {
                "ok": False,
                "loaded": [],
                "failure_class": "login_not_in_process",
                "next_action": login_ask_text(
                    ["ZEUS_USERNAME", "ZEUS_PASSWORD"]
                ),
            },
            ["ZEUS_USERNAME", "ZEUS_PASSWORD"],
        )
    path = Path(raw).expanduser()
    if not path.is_file():
        from zeus_dev_helper_mcp.env_questions import attach_login_ask

        return attach_login_ask(
            {
                "ok": False,
                "loaded": [],
                "failure_class": "login_not_in_process",
                "next_action": (
                    "That env file is not on disk. Ask the user for ZEUS_USERNAME "
                    "and ZEUS_PASSWORD. Write them in a mode-600 file and call "
                    "load_process_login again. Do not pass the password as a tool argument."
                ),
            },
            ["ZEUS_USERNAME", "ZEUS_PASSWORD"],
        )
    if not _private_file(path):
        return {
            "ok": False,
            "loaded": [],
            "failure_class": "login_not_in_process",
            "next_action": (
                "The env file must be mode 600 before it is loaded. "
                "chmod 600 that file and call load_process_login again. "
                "Do not pass the password as a tool argument."
            ),
        }
    try:
        parsed = _parse_env(path.read_text(encoding="utf-8"))
    except OSError:
        return {
            "ok": False,
            "loaded": [],
            "failure_class": "login_not_in_process",
            "next_action": "The env file could not be read. Check the path and mode 600.",
        }

    loaded: list[str] = []
    for key, value in parsed.items():
        os.environ[key] = value
        loaded.append(key)
    if "ZEUS_USERNAME" not in loaded and parsed.get("ZEUS_USER"):
        os.environ["ZEUS_USERNAME"] = parsed["ZEUS_USER"]
        loaded.append("ZEUS_USERNAME")
    if "ZEUS_BEARER_TOKEN" not in loaded and parsed.get("ZEUS_TOKEN"):
        os.environ["ZEUS_BEARER_TOKEN"] = parsed["ZEUS_TOKEN"]
        loaded.append("ZEUS_BEARER_TOKEN")

    has_login = bool((os.environ.get("ZEUS_USERNAME") or os.environ.get("ZEUS_USER") or "").strip())
    has_password = bool((os.environ.get("ZEUS_PASSWORD") or "").strip())
    has_bearer = bool(
        (os.environ.get("ZEUS_BEARER_TOKEN") or os.environ.get("ZEUS_TOKEN") or "").strip()
    )
    if (has_login and has_password) or has_bearer:
        return {
            "ok": True,
            "loaded": loaded,
            "failure_class": None,
            "next_action": "readiness_check. The password stays in this process.",
        }
    from zeus_dev_helper_mcp.config import llm_key_in_process_env
    from zeus_dev_helper_mcp.env_questions import (
        attach_llm_ask,
        attach_login_ask,
        llm_ask_text,
        login_ask_text,
    )

    file_had_login = any(key in parsed for key in _LOGIN_FILE_KEYS)
    llm_ready = (
        llm_key_in_process_env()
        and bool((os.environ.get("LLM_BASE_URL") or "").strip())
        and bool((os.environ.get("LLM_MODEL") or "").strip())
    )
    loaded_llm = [name for name in loaded if name.startswith("LLM_")]
    if loaded_llm and not file_had_login and _auth_mode() != "basic":
        if llm_ready:
            return {
                "ok": True,
                "loaded": loaded,
                "failure_class": None,
                "next_action": (
                    "LLM_BASE_URL, LLM_MODEL, and LLM_API_KEY are in this process. "
                    "The API key stays out of tool arguments. Then readiness_check."
                ),
            }
        return attach_llm_ask(
            {
                "ok": True,
                "loaded": loaded,
                "failure_class": None,
                "next_action": llm_ask_text(),
            }
        )
    missing: list[str] = []
    if not has_login:
        missing.append("ZEUS_USERNAME")
    if not has_password:
        missing.append("ZEUS_PASSWORD")
    return attach_login_ask(
        {
            "ok": False,
            "loaded": loaded,
            "failure_class": "login_not_in_process",
            "next_action": login_ask_text(missing),
        },
        missing,
    )


def _auth_mode() -> str:
    try:
        from zeus_dev_helper_mcp.config import reload_config

        return (reload_config().zeus_auth_mode or "none").strip().lower() or "none"
    except Exception:  # noqa: BLE001
        return (os.environ.get("ZEUS_AUTH_MODE") or "none").strip().lower() or "none"
