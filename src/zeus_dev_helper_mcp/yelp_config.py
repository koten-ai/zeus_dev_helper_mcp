"""Write the yelp demo's gitignored config.json from this process.

The password is copied into the file the way the beer sample writes ``.env``.
The LLM value is the env name ``LLM_API_KEY``. The key itself is not copied.
The tool result lists names only.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

from zeus_dev_helper_mcp.config import HelperConfig

_CLIENT_GIT = "git+ssh://git@github.com/koten-ai/zeus_client_python.git@0.3.1-alpha"
_CLIENT_PIN = f"kotenai-zeus-client @ {_CLIENT_GIT}"
_FILE_DEP = "file:../zeus_client_python"


def _write_private(path: Path, text: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, text.encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(path, 0o600)


def _ensure_gitignore(root: Path) -> None:
    path = root / ".gitignore"
    existing = ""
    if path.is_file():
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError:
            existing = ""
    if "config.json" in {line.strip() for line in existing.splitlines()}:
        return
    if not existing:
        path.write_text("config.json\n", encoding="utf-8")
        return
    suffix = "" if existing.endswith("\n") else "\n"
    path.write_text(existing + suffix + "config.json\n", encoding="utf-8")


def _process(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _login_missing(cfg: HelperConfig) -> bool:
    mode = (cfg.zeus_auth_mode or "none").strip().lower()
    if mode != "basic":
        return False
    user = _process("ZEUS_USERNAME") or _process("ZEUS_USER")
    return not user or not _process("ZEUS_PASSWORD")


def _base_document(root: Path) -> dict[str, Any]:
    example = root / "config.example.json"
    if not example.is_file():
        return {}
    try:
        data = json.loads(example.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _llm_section(doc: dict[str, Any]) -> dict[str, Any]:
    raw = doc.get("llm_provider")
    provider = dict(raw) if isinstance(raw, dict) else {}
    provider["api_key"] = ""
    provider["api_key_env"] = "LLM_API_KEY"
    if not provider.get("base_url"):
        provider["base_url"] = "https://api.x.ai/v1"
    models = provider.get("models")
    if not isinstance(models, list) or not models:
        provider["models"] = ["grok-4.5-latest"]
    return provider


def write_yelp_config(cfg: HelperConfig, root: Path) -> dict[str, Any]:
    """Create mode-600 ``config.json`` when the checkout does not have one.

    An existing non-empty file is left in place. ``scope_contracts`` hashes
    are copied from ``config.example.json`` when that file has them. This
    function does not invent a hash.
    """
    root = root.expanduser().resolve()
    path = root / "config.json"
    _ensure_gitignore(root)
    if path.is_file():
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError:
            existing = ""
        if existing.strip():
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            return {
                "created": False,
                "existed": True,
                "mode": stat.S_IMODE(path.stat().st_mode) if path.is_file() else None,
                "fields": ["config.json"],
            }
    if _login_missing(cfg):
        return {
            "created": False,
            "existed": False,
            "failure_class": "login_not_in_process",
            "next_action": (
                "ZEUS_USERNAME and ZEUS_PASSWORD are not in this process. "
                "Write them to a mode-600 env file and call load_process_login. "
                "set_prereq stores presence flags only. Then use_sample again "
                "so config.json can be written. Do not pass the password as a tool argument."
            ),
        }

    doc = _base_document(root)
    zeus = doc.get("zeus")
    zeus_doc = dict(zeus) if isinstance(zeus, dict) else {}
    url = (cfg.zeus_url or _process("ZEUS_URL") or "").strip()
    if url:
        zeus_doc["url"] = url
    mode = (cfg.zeus_auth_mode or "none").strip().lower() or "none"
    zeus_doc["auth_mode"] = mode
    user = _process("ZEUS_USERNAME") or _process("ZEUS_USER")
    password = _process("ZEUS_PASSWORD")
    if user:
        zeus_doc["username"] = user
    if password:
        zeus_doc["password"] = password
    bucket = (cfg.default_bucket or "yelp-demo").strip() or "yelp-demo"
    scope = (cfg.default_scope or "_default").strip() or "_default"
    if user or password:
        creds = zeus_doc.get("scope_credentials")
        scope_creds = dict(creds) if isinstance(creds, dict) else {}
        scope_creds[f"{bucket}/{scope}"] = {"username": user, "password": password}
        zeus_doc["scope_credentials"] = scope_creds
    zeus_doc["enable_durable_sessions"] = False
    doc["zeus"] = zeus_doc
    doc["llm_provider"] = _llm_section(doc)
    doc["default_mode"] = doc.get("default_mode") or "analytics"
    doc["default_sample"] = "yelp-demo"
    samples = doc.get("samples")
    sample_doc = dict(samples) if isinstance(samples, dict) else {}
    yelp = sample_doc.get("yelp-demo")
    yelp_doc = dict(yelp) if isinstance(yelp, dict) else {}
    yelp_doc["bucket"] = bucket
    yelp_doc["scope"] = scope
    yelp_doc["collection"] = yelp_doc.get("collection") or "_default"
    sample_doc["yelp-demo"] = yelp_doc
    doc["samples"] = sample_doc

    _write_private(path, json.dumps(doc, indent=2) + "\n")
    fields = ["zeus.url", "zeus.auth_mode", "zeus.username", "llm_provider.api_key_env"]
    if password:
        fields.append("zeus.password")
    return {
        "created": True,
        "existed": False,
        "mode": 0o600,
        "fields": fields,
        "llm_api_key_env": "LLM_API_KEY",
    }


def pin_yelp_client(root: Path) -> dict[str, Any]:
    """Replace the sibling ``file:`` client dep with the 0.3.1 tag the template imports.

    ``kotenai-zeus-client`` 2.4 does not export ``run_agent`` or
    ``zeus_client.zeus.catalog.load_live_chat_request``. A ``parent_dir`` clone
    cannot resolve ``file:../zeus_client_python``.
    """
    path = root / "pyproject.toml"
    if not path.is_file():
        return {"patched": False, "reason": "no pyproject"}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"patched": False, "reason": type(exc).__name__}
    if _FILE_DEP not in text:
        return {"patched": False, "reason": "file dependency absent", "requirement": _CLIENT_PIN}
    path.write_text(text.replace(_FILE_DEP, _CLIENT_GIT), encoding="utf-8")
    return {"patched": True, "requirement": _CLIENT_PIN}
