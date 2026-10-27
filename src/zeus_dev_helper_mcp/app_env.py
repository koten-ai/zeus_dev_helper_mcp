"""Write the app ``.env`` from its template and this process. Never echo secrets."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from zeus_dev_helper_mcp.config import HelperConfig, llm_key_in_process_env

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
    from zeus_dev_helper_mcp.env_questions import attach_login_ask, login_ask_text

    return attach_login_ask(
        {
            "ok": False,
            "written": False,
            "failure_class": "login_not_in_process",
            "missing_env": missing,
            "next_action": (
                login_ask_text(missing)
                + " A stored has_username or has_password flag is not a login. "
                "This app was not written."
            ),
        },
        missing,
    )


def _routing(cfg_value: str, env_name: str) -> str:
    direct = (cfg_value or "").strip()
    if direct:
        return direct
    return (os.environ.get(env_name) or "").strip()


_ASSIGN_RE = re.compile(
    r"^(?P<export>export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$"
)
_COMMENT_ASSIGN_RE = re.compile(
    r"^#\s*(?P<export>export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$"
)
_SAFE_VALUE_RE = re.compile(r"^[A-Za-z0-9_./:@%+\-]+$")
_LLM_GROUP = ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")


def _auth_mode(cfg: HelperConfig) -> str:
    return (cfg.zeus_auth_mode or "none").strip().lower() or "none"


def _unquote(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1]
    return text


def _format_value(value: str) -> str:
    if value == "" or _SAFE_VALUE_RE.fullmatch(value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _dotenv_map(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in text.splitlines():
        match = _ASSIGN_RE.match(line.strip())
        if match is None:
            continue
        found[match.group("key")] = _unquote(match.group("value"))
    return found


def _url_host(url: str) -> str:
    text = url.strip()
    if "://" in text:
        text = text.split("://", 1)[1]
    return text.split("/", 1)[0].split("@")[-1].split(":")[0].lower()


def _provider_match(base_url: str, model: str) -> str:
    """Return ``xai`` or ``openai`` when the base URL and model are one provider."""
    host = _url_host(base_url)
    model_name = model.strip().lower()
    if not host or not model_name:
        return ""
    if host == "api.x.ai" or host.endswith(".x.ai"):
        if model_name.startswith("grok"):
            return "xai"
        return ""
    if host == "api.openai.com" or host.endswith(".openai.com"):
        if model_name.startswith(("gpt-", "o1", "o3", "o4", "chatgpt")):
            return "openai"
        return ""
    return ""


def _confirmed_routing(cfg: HelperConfig) -> dict[str, str]:
    """Zeus routing and login from config or this process. No invented values."""
    found: dict[str, str] = {}
    for key, attr, env_name in (
        ("ZEUS_URL", "zeus_url", "ZEUS_URL"),
        ("ZEUS_BUCKET", "default_bucket", "ZEUS_BUCKET"),
        ("ZEUS_SCOPE", "default_scope", "ZEUS_SCOPE"),
        ("ZEUS_COLLECTION", "default_collection", "ZEUS_COLLECTION"),
    ):
        value = _routing(str(getattr(cfg, attr, "") or ""), env_name)
        if value:
            found[key] = value
    user = process_username()
    if user:
        found["ZEUS_USERNAME"] = user
    password = process_password()
    if password:
        found["ZEUS_PASSWORD"] = password
    if _auth_mode(cfg) == "bearer":
        token = (os.environ.get("ZEUS_BEARER_TOKEN") or os.environ.get("ZEUS_TOKEN") or "").strip()
        if token:
            found["ZEUS_BEARER_TOKEN"] = token
    return found


def _llm_fills(template: dict[str, str], existing: dict[str, str]) -> tuple[dict[str, str], str]:
    """Resolve the key, base URL, and model together.

    An ``OPENAI_API_KEY`` or ``XAI_API_KEY`` is copied into ``LLM_API_KEY`` only
    when the base URL and model match that provider. The returned alias name is
    the one that was left unused. Values are not logged by the caller.
    """
    fills: dict[str, str] = {}
    proc_key = (os.environ.get("LLM_API_KEY") or "").strip()
    proc_base = (os.environ.get("LLM_BASE_URL") or "").strip()
    proc_model = (os.environ.get("LLM_MODEL") or "").strip()
    xai = (os.environ.get("XAI_API_KEY") or "").strip()
    openai = (os.environ.get("OPENAI_API_KEY") or "").strip()

    def _kept(name: str) -> str:
        return (existing.get(name) or "").strip()

    if proc_key:
        fills["LLM_API_KEY"] = proc_key
        if proc_base and not _kept("LLM_BASE_URL"):
            fills["LLM_BASE_URL"] = proc_base
        if proc_model and not _kept("LLM_MODEL"):
            fills["LLM_MODEL"] = proc_model
        return fills, ""

    if proc_base and proc_model:
        pair_base, pair_model = proc_base, proc_model
        from_process = True
    elif not proc_base and not proc_model:
        pair_base = _kept("LLM_BASE_URL") or (template.get("LLM_BASE_URL") or "").strip()
        pair_model = _kept("LLM_MODEL") or (template.get("LLM_MODEL") or "").strip()
        from_process = False
    else:
        skipped = "OPENAI_API_KEY" if openai else ("XAI_API_KEY" if xai else "")
        return fills, skipped

    provider = _provider_match(pair_base, pair_model)
    alias = ""
    if provider == "xai" and xai:
        alias = xai
    elif provider == "openai" and openai:
        alias = openai
    if alias:
        fills["LLM_API_KEY"] = alias
        if from_process:
            if not _kept("LLM_BASE_URL"):
                fills["LLM_BASE_URL"] = pair_base
            if not _kept("LLM_MODEL"):
                fills["LLM_MODEL"] = pair_model
        return fills, ""
    if openai and provider != "openai":
        return fills, "OPENAI_API_KEY"
    if xai and provider != "xai":
        return fills, "XAI_API_KEY"
    return fills, ""


def _merge_env_text(
    example: str,
    existing: str,
    fills: dict[str, str],
    *,
    auth_mode: str,
) -> str:
    """Keep populated ``.env`` values, then fill empties, then the template."""
    existing_vals = _dotenv_map(existing)
    seen: set[str] = set()
    out_lines: list[str] = []

    def _choose(key: str, template_value: str) -> str:
        current = (existing_vals.get(key) or "").strip()
        if current:
            return current
        if key == "ZEUS_BEARER_TOKEN" and auth_mode == "basic":
            return template_value.strip()
        filled = (fills.get(key) or "").strip()
        if filled:
            return filled
        return template_value.strip()

    for raw in example.splitlines():
        stripped = raw.strip()
        match = _ASSIGN_RE.match(stripped)
        if match is not None:
            key = match.group("key")
            seen.add(key)
            value = _choose(key, _unquote(match.group("value")))
            prefix = "export " if match.group("export") else ""
            out_lines.append(f"{prefix}{key}={_format_value(value)}")
            continue
        comment = _COMMENT_ASSIGN_RE.match(stripped)
        if comment is not None:
            key = comment.group("key")
            filled = (fills.get(key) or "").strip()
            current = (existing_vals.get(key) or "").strip()
            if key == "ZEUS_BEARER_TOKEN" and auth_mode == "basic":
                out_lines.append(raw)
                seen.add(key)
                continue
            if current or filled:
                seen.add(key)
                out_lines.append(f"{key}={_format_value(current or filled)}")
                continue
        out_lines.append(raw)

    for key, value in existing_vals.items():
        if key in seen or not value.strip():
            continue
        seen.add(key)
        out_lines.append(f"{key}={_format_value(value.strip())}")
    for key, value in fills.items():
        if key in seen or not value.strip():
            continue
        if key == "ZEUS_BEARER_TOKEN" and auth_mode == "basic":
            continue
        out_lines.append(f"{key}={_format_value(value.strip())}")
    text = "\n".join(out_lines)
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def _required_names(cfg: HelperConfig, template: dict[str, str]) -> list[str]:
    names: list[str] = ["ZEUS_URL"]
    for name in _LLM_GROUP:
        if name in template:
            names.append(name)
    mode = _auth_mode(cfg)
    if mode == "basic":
        names.extend(["ZEUS_USERNAME", "ZEUS_PASSWORD"])
    elif mode == "bearer":
        names.append("ZEUS_BEARER_TOKEN")
    return names


def _process_has(cfg: HelperConfig, name: str, *, alias_accepted: bool) -> bool:
    if name == "ZEUS_URL":
        return bool(_routing(cfg.zeus_url, "ZEUS_URL"))
    if name == "ZEUS_USERNAME":
        return bool(process_username())
    if name == "ZEUS_PASSWORD":
        return bool(process_password())
    if name == "ZEUS_BEARER_TOKEN":
        token = (os.environ.get("ZEUS_BEARER_TOKEN") or os.environ.get("ZEUS_TOKEN") or "").strip()
        return bool(token)
    if name == "LLM_API_KEY":
        if (os.environ.get("LLM_API_KEY") or "").strip():
            return True
        return alias_accepted
    return bool((os.environ.get(name) or "").strip())


def _missing_settings(
    cfg: HelperConfig,
    template: dict[str, str],
    written: dict[str, str],
    *,
    alias_accepted: bool,
) -> tuple[list[str], list[str]]:
    app_missing: list[str] = []
    process_missing: list[str] = []
    for name in _required_names(cfg, template):
        if not (written.get(name) or "").strip():
            app_missing.append(name)
        if _process_has(cfg, name, alias_accepted=alias_accepted):
            continue
        if name in {"LLM_BASE_URL", "LLM_MODEL"} and (written.get(name) or "").strip():
            continue
        process_missing.append(name)
    return app_missing, process_missing


def _env_lines(cfg: HelperConfig) -> tuple[list[str], list[str]]:
    """Lines for a new ``.env`` when the app has no template."""
    fills = _confirmed_routing(cfg)
    llm, _skipped = _llm_fills({}, {})
    fills.update(llm)
    lines = [f"{key}={_format_value(value)}" for key, value in fills.items() if value.strip()]
    names = [key for key, _value in fills.items() if _value.strip()]
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
    """Create or merge a mode 600 ``.env`` from this app's ``.env.example``.

    Populated values already in ``.env`` stay. Missing template keys are added.
    Confirmed Zeus routing and this process fill empty keys. The result lists
    variable names only.
    """
    root = Path(target_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = root / ".env"
    example_path = root / ".env.example"
    created = False
    existing = ""
    if path.is_file() and not path.is_symlink():
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError:
            existing = ""
    example = ""
    if example_path.is_file() and not example_path.is_symlink():
        try:
            example = example_path.read_text(encoding="utf-8")
        except OSError:
            example = ""
    template = _dotenv_map(example)
    existing_vals = _dotenv_map(existing)
    fills = _confirmed_routing(cfg)
    llm_fills, skipped_alias = _llm_fills(template, existing_vals)
    fills.update(llm_fills)
    auth_mode = _auth_mode(cfg)
    if path.is_symlink():
        names = _env_key_names(existing)
        written = existing_vals
    elif example:
        merged = _merge_env_text(example, existing, fills, auth_mode=auth_mode)
        if not path.exists():
            created = True
        if merged != existing or created:
            _write_private(path, merged)
        else:
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        written = _dotenv_map(merged)
        names = _env_key_names(merged)
    elif existing.strip():
        names = _env_key_names(existing)
        written = existing_vals
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    else:
        lines, names = _env_lines(cfg)
        if lines:
            _write_private(path, "\n".join(lines) + "\n")
            created = True
        written = _dotenv_map("\n".join(lines))
    gitignore = _ensure_gitignore(root)
    present = path.is_file() and not path.is_symlink() and bool(names or created)
    if path.is_symlink():
        present = bool(names)
    app_missing, process_missing = _missing_settings(
        cfg,
        template,
        written,
        alias_accepted=bool(llm_fills.get("LLM_API_KEY")) and not (os.environ.get("LLM_API_KEY") or "").strip(),
    )
    report: dict[str, Any] = {
        "wrote_env": present,
        "created_env": created,
        "env_keys": names,
        "gitignore": gitignore,
        "env_template": ".env.example",
        "env_target": ".env",
        "configuration_policy": "preserve_existing_then_fill_missing",
        "missing_app_settings": app_missing,
        "missing_process_settings": process_missing,
    }
    if skipped_alias:
        report["skipped_llm_alias"] = skipped_alias
    return report


def strip_dotenv_copy(run: str) -> str:
    for snippet in _CP_SNIPPETS:
        run = run.replace(snippet, "")
    return run.strip()


def annotate_app_env(
    cfg: HelperConfig,
    root: str | Path,
    result: dict[str, Any],
    *,
    report: bool = False,
) -> dict[str, Any]:
    info = ensure_app_env(cfg, root)
    result["app_env"] = {
        "wrote_env": info["wrote_env"],
        "created_env": info["created_env"],
        "env_keys": list(info["env_keys"]),
        "gitignore": info["gitignore"],
    }
    if info["wrote_env"] and result.get("run"):
        result["run"] = strip_dotenv_copy(str(result["run"]))
    if info["wrote_env"] and result.get("next_action"):
        result["next_action"] = strip_dotenv_copy(str(result["next_action"]))
    if report:
        for key in (
            "env_template",
            "env_target",
            "configuration_policy",
            "missing_app_settings",
            "missing_process_settings",
            "skipped_llm_alias",
        ):
            if key in info:
                result[key] = info[key]
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
