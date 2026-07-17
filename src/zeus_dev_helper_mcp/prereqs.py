"""Persist prereqs (ZDH-4 set_prereq) without logging secret values."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from zeus_dev_helper_mcp.config import HelperConfig


def prereq_path(cfg: HelperConfig) -> Path:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    return cfg.state_dir / "prereqs.json"


def load_prereqs(cfg: HelperConfig) -> dict[str, Any]:
    path = prereq_path(cfg)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def save_prereqs(cfg: HelperConfig, data: dict[str, Any]) -> dict[str, Any]:
    """Merge and save prereqs. Never store raw secrets — only presence + non-secret fields.

    Allowed stored keys: zeus_url, auth_mode, bucket, scope, collection, mode, role,
    has_llm_key, has_bearer, has_password, has_username (booleans).
    """
    allowed = {
        "zeus_url",
        "auth_mode",
        "bucket",
        "scope",
        "collection",
        "mode",
        "role",
        "has_llm_key",
        "has_bearer",
        "has_password",
        "has_username",
    }
    current = load_prereqs(cfg)
    for k, v in data.items():
        if k not in allowed:
            continue
        if v is None or v == "":
            continue
        current[k] = v
    path = prereq_path(cfg)
    path.write_text(json.dumps(current, indent=2) + "\n")
    return current


def public_prereqs(cfg: HelperConfig) -> dict[str, Any]:
    p = load_prereqs(cfg)
    return {
        "stored": {k: p.get(k) for k in sorted(p.keys())},
        "path": str(prereq_path(cfg)),
        "note": "Secrets are never written here — only presence flags and non-secret fields.",
    }
