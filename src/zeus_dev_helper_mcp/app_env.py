"""Write the app ``.env`` from its template and this process. Never echo secrets."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from zeus_dev_helper_mcp.config import HelperConfig, llm_key_in_process_env
from zeus_dev_helper_mcp.error_log import scrub_text

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


def dotenv_map(text: str) -> dict[str, str]:
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
    existing_vals = dotenv_map(existing)
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


def _auth_mode_fill(cfg: HelperConfig, existing: Mapping[str, str]) -> dict[str, str]:
    """Fill an empty ``ZEUS_AUTH_MODE``. A populated value stays put.

    The default ``none`` is not invented. An explicit process value, including
    ``none``, and a stored ``basic`` or ``bearer`` mode are written.
    """
    if (existing.get("ZEUS_AUTH_MODE") or "").strip():
        return {}
    explicit = (os.environ.get("ZEUS_AUTH_MODE") or "").strip().lower()
    if explicit not in {"none", "basic", "bearer"}:
        stored = (cfg.zeus_auth_mode or "").strip().lower()
        explicit = stored if stored in {"basic", "bearer"} else ""
    if not explicit:
        return {}
    return {"ZEUS_AUTH_MODE": explicit}


def _env_lines(cfg: HelperConfig) -> tuple[list[str], list[str]]:
    """Lines for a new ``.env`` when the app has no template."""
    fills = _confirmed_routing(cfg)
    llm, _skipped = _llm_fills({}, {})
    fills.update(llm)
    fills.update(_auth_mode_fill(cfg, {}))
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


_OVERLAY_KEYS = (
    "ZEUS_AUTH_MODE",
    "ZEUS_URL",
    "ZEUS_USERNAME",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "COUCHBASE_QUERY_URL",
    "COUCHBASE_USERNAME",
)
_TRACKED_SETTINGS = (
    "ZEUS_AUTH_MODE",
    "ZEUS_USERNAME",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "COUCHBASE_QUERY_URL",
    "COUCHBASE_USERNAME",
)
_SECRET_PRESENCE = (
    "ZEUS_PASSWORD",
    "ZEUS_BEARER_TOKEN",
    "LLM_API_KEY",
    "COUCHBASE_PASSWORD",
)
ENV_REPORT_KEYS = (
    "settings_written",
    "settings_kept",
    "secret_presence",
    "env_change",
)
_ENV_NOTE_MARK = "Env report:"


def overlay_nonsecret_env(
    root: str | Path,
    updates: Mapping[str, str],
    *,
    ensure_empty: tuple[str, ...] = (),
) -> None:
    """Replace accepted non-secret keys. Leave every other line unchanged.

    ``ZEUS_PASSWORD``, ``ZEUS_BEARER_TOKEN``, ``LLM_API_KEY``, and
    ``COUCHBASE_PASSWORD`` stay as they are, including an empty or quoted
    value. A missing ``.env`` is created with only the accepted keys.
    ``ensure_empty`` adds ``KEY=`` when that key is not already in the file.
    """
    chosen = {
        key: updates[key]
        for key in _OVERLAY_KEYS
        if key in updates
    }
    if not chosen and not ensure_empty:
        return
    path = Path(root).expanduser().resolve() / ".env"
    if path.is_symlink():
        return
    existing = ""
    if path.is_file():
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError:
            existing = ""
    seen: set[str] = set()
    out_lines: list[str] = []
    for raw in existing.splitlines():
        match = _ASSIGN_RE.match(raw.strip())
        if match is not None:
            key = match.group("key")
            seen.add(key)
            if key in chosen:
                prefix = "export " if match.group("export") else ""
                out_lines.append(f"{prefix}{key}={_format_value(chosen[key])}")
                continue
        out_lines.append(raw)
    for key in _OVERLAY_KEYS:
        if key in chosen and key not in seen:
            out_lines.append(f"{key}={_format_value(chosen[key])}")
            seen.add(key)
    for key in ensure_empty:
        if key not in seen:
            out_lines.append(f"{key}=")
    text = "\n".join(out_lines)
    if text and not text.endswith("\n"):
        text += "\n"
    if not path.parent.is_dir():
        return
    _write_private(path, text)


def ensure_app_env(
    cfg: HelperConfig,
    target_dir: str | Path,
    *,
    example_text: str = "",
    template_name: str = "",
) -> dict[str, Any]:
    """Create or merge a mode 600 ``.env`` from this app's ``.env.example``.

    Populated values already in ``.env`` stay. Missing template keys are added.
    Confirmed Zeus routing and this process fill empty keys. The result names
    which of ``ZEUS_AUTH_MODE``, ``ZEUS_USERNAME``, ``LLM_BASE_URL``, and
    ``LLM_MODEL`` were written, and the populated values that were kept.
    ``ZEUS_PASSWORD``, ``ZEUS_BEARER_TOKEN``, ``LLM_API_KEY``, and
    ``COUCHBASE_PASSWORD`` stay presence-only. A caller with no
    ``.env.example`` passes ``example_text``.
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
    chosen_template = ".env.example"
    if example_path.is_file() and not example_path.is_symlink():
        try:
            example = example_path.read_text(encoding="utf-8")
        except OSError:
            example = ""
    elif example_text:
        example = example_text
        chosen_template = template_name or "inline"
    template = dotenv_map(example)
    existing_vals = dotenv_map(existing)
    fills = _confirmed_routing(cfg)
    llm_fills, skipped_alias = _llm_fills(template, existing_vals)
    fills.update(llm_fills)
    fills.update(_auth_mode_fill(cfg, existing_vals))
    auth_mode = _auth_mode(cfg)
    file_changed = False
    if path.is_symlink():
        names = _env_key_names(existing)
        written = existing_vals
    elif example:
        merged = _merge_env_text(example, existing, fills, auth_mode=auth_mode)
        file_changed = bool(existing.strip()) and merged != existing
        if not path.exists():
            created = True
        if merged != existing or created:
            _write_private(path, merged)
        else:
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        written = dotenv_map(merged)
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
        written = dotenv_map("\n".join(lines))
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
        "env_template": chosen_template,
        "env_target": ".env",
        "configuration_policy": "preserve_existing_then_fill_missing",
        "missing_app_settings": app_missing,
        "missing_process_settings": process_missing,
    }
    report.update(
        settings_report(existing_vals, written, file_changed=file_changed)
    )
    if skipped_alias:
        report["skipped_llm_alias"] = skipped_alias
    return report


def _secret_presence(values: Mapping[str, str]) -> dict[str, bool]:
    bearer = (values.get("ZEUS_BEARER_TOKEN") or values.get("ZEUS_TOKEN") or "").strip()
    found = {
        "ZEUS_PASSWORD": bool((values.get("ZEUS_PASSWORD") or "").strip()),
        "ZEUS_BEARER_TOKEN": bool(bearer),
        "LLM_API_KEY": bool((values.get("LLM_API_KEY") or "").strip()),
        "COUCHBASE_PASSWORD": bool((values.get("COUCHBASE_PASSWORD") or "").strip()),
    }
    return {name: found[name] for name in _SECRET_PRESENCE}


def settings_report(
    before: Mapping[str, str],
    after: Mapping[str, str],
    *,
    file_changed: bool,
) -> dict[str, Any]:
    """Names written, populated values kept, and whether an existing file changed.

    Secret values are not copied. ``secret_presence`` is booleans only.
    """
    written: list[str] = []
    kept: dict[str, str] = {}
    for name in _TRACKED_SETTINGS:
        previous = (before.get(name) or "").strip()
        current = (after.get(name) or "").strip()
        if current != previous:
            written.append(name)
        elif current:
            shown = scrub_text(current).strip()
            if shown:
                kept[name] = shown
    return {
        "settings_written": written,
        "settings_kept": kept,
        "secret_presence": _secret_presence(after),
        "env_change": file_changed,
    }


def _env_report_from(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """The ensure report on a result, or on its ``app_env`` block.

    A payload that never ran ``ensure_app_env`` has neither and returns
    ``None``. Callers must not invent a report for that result.
    """
    source: Mapping[str, Any] | None = None
    if "settings_written" in payload or "env_change" in payload:
        source = payload
    else:
        nested = payload.get("app_env")
        if isinstance(nested, dict) and (
            "settings_written" in nested or "env_change" in nested
        ):
            source = nested
    if source is None:
        return None
    written_in = source.get("settings_written")
    written = (
        [str(name) for name in written_in if isinstance(name, str)]
        if isinstance(written_in, list)
        else []
    )
    kept_in = source.get("settings_kept")
    kept: dict[str, str] = {}
    if isinstance(kept_in, dict):
        for name in _TRACKED_SETTINGS:
            raw = kept_in.get(name)
            if not isinstance(raw, str) or not raw.strip():
                continue
            shown = scrub_text(raw).strip()
            if shown:
                kept[name] = shown
    created = bool(payload.get("created_env"))
    for block in (payload.get("app_env"), source):
        if isinstance(block, dict):
            created = created or bool(block.get("created_env"))
    report: dict[str, Any] = {
        "settings_written": [name for name in _TRACKED_SETTINGS if name in set(written)],
        "settings_kept": {name: kept[name] for name in _TRACKED_SETTINGS if name in kept},
        "env_change": bool(source.get("env_change")),
        "created_env": created,
    }
    presence = source.get("secret_presence")
    if isinstance(presence, dict):
        report["secret_presence"] = dict(presence)
    return report


def _read_env_text(path: Path) -> str:
    if path.is_file() and not path.is_symlink():
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""
    return ""


def refresh_env_report(
    payload: Mapping[str, Any],
    before_text: str,
    after_text: str,
) -> dict[str, Any] | None:
    """Merge an overlay diff into an ensure report.

    ``settings_report`` is the only value diff. Names the ensure pass already
    wrote stay written. A first create stays ``env_change`` false. A payload
    with no ensure report returns ``None``.
    """
    prior = _env_report_from(payload)
    if prior is None:
        return None
    overlay = settings_report(
        dotenv_map(before_text),
        dotenv_map(after_text),
        file_changed=bool(before_text.strip()) and before_text != after_text,
    )
    written_set = set(prior["settings_written"]) | set(overlay["settings_written"])
    kept = {
        name: overlay["settings_kept"][name]
        for name in _TRACKED_SETTINGS
        if name not in written_set and name in overlay["settings_kept"]
    }
    env_change = False if prior["created_env"] else (
        bool(prior["env_change"]) or bool(overlay["env_change"])
    )
    return {
        "settings_written": [name for name in _TRACKED_SETTINGS if name in written_set],
        "settings_kept": kept,
        "secret_presence": overlay["secret_presence"],
        "env_change": env_change,
    }


def apply_env_overlay(
    payload: dict[str, Any],
    updates: Mapping[str, str],
    *,
    ensure_empty: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Write accepted non-secrets and refresh the ensure report.

    A payload that never ran ``ensure_app_env`` is returned unchanged. No
    ``.env`` is created for that result, and no env report is attached.
    """
    if _env_report_from(payload) is None:
        return payload
    root = payload.get("local_dir") or payload.get("target_dir")
    if not isinstance(root, str) or not root.strip() or not Path(root).is_dir():
        return payload
    env_path = Path(root) / ".env"
    before = _read_env_text(env_path)
    overlay_nonsecret_env(root, updates, ensure_empty=ensure_empty)
    refreshed = refresh_env_report(payload, before, _read_env_text(env_path))
    if refreshed is None:
        return payload
    assign_env_report(payload, refreshed)
    return attach_env_change_note(payload)


def assign_env_report(payload: dict[str, Any], report: Mapping[str, Any]) -> None:
    """Copy the env report onto the tool result and its ``app_env`` block."""
    app_env = payload.get("app_env")
    for key in ENV_REPORT_KEYS:
        if key not in report:
            continue
        payload[key] = report[key]
        if isinstance(app_env, dict):
            app_env[key] = report[key]


def describe_env_change(report: Mapping[str, Any]) -> str:
    """One suffix the agent can act on before ``run_turn``. No secret values."""
    view = _env_report_from(report)
    if view is None:
        return ""
    written = [
        name
        for name in _TRACKED_SETTINGS
        if name in set(view["settings_written"])
    ]
    kept_in = view["settings_kept"]
    kept_bits = [
        f"{name}={kept_in[name]}"
        for name in _TRACKED_SETTINGS
        if name in kept_in
    ]
    wrote = ", ".join(written) if written else "none"
    if view["env_change"]:
        kept_note = f" Kept {', '.join(kept_bits)}." if kept_bits else ""
        changed = ", ".join(written) if written else "other keys"
        return (
            f"{_ENV_NOTE_MARK} env change. Wrote {changed}.{kept_note} "
            "Restart the app before run_turn."
        )
    if view["created_env"]:
        return f"{_ENV_NOTE_MARK} created .env. Wrote {wrote}."
    if kept_bits or written:
        kept_note = ", ".join(kept_bits) if kept_bits else "none"
        return f"{_ENV_NOTE_MARK} no env change. Wrote {wrote}. Kept {kept_note}."
    return ""


def attach_env_change_note(result: dict[str, Any]) -> dict[str, Any]:
    """Replace any earlier env-report suffix. Other coaching stays in front.

    The report is copied to the top level when it so far lives only on
    ``app_env``. A result with no ensure report is unchanged.
    """
    view = _env_report_from(result)
    if view is not None:
        assign_env_report(result, view)
    note = describe_env_change(result)
    action = str(result.get("next_action") or "")
    mark = action.find(_ENV_NOTE_MARK)
    if mark >= 0:
        action = action[:mark].rstrip()
    if note:
        action = f"{action} {note}".strip()
    if action:
        result["next_action"] = action
    return result


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
    example_text: str = "",
    template_name: str = "",
) -> dict[str, Any]:
    info = ensure_app_env(
        cfg,
        root,
        example_text=example_text,
        template_name=template_name,
    )
    result["app_env"] = {
        "wrote_env": info["wrote_env"],
        "created_env": info["created_env"],
        "env_keys": list(info["env_keys"]),
        "gitignore": info["gitignore"],
    }
    for key in ENV_REPORT_KEYS:
        result["app_env"][key] = info[key]
        result[key] = info[key]
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
