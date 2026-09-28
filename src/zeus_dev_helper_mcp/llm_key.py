"""LLM key gates. Presence only — never return or store the secret."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from zeus_dev_helper_mcp.config import (
    LLM_KEY_ENV_NAMES,
    HelperConfig,
    llm_key_in_process_env,
)
from zeus_dev_helper_mcp.config_lint import _ENV_NAME

__all__ = [
    "inspect_app_llm_key",
    "llm_key_in_process_env",
    "path_needs_llm_key",
    "sync_checklist_llm_prereq",
]


def path_needs_llm_key(cfg: HelperConfig) -> bool:
    """True when this checklist path calls the model before first green.

    Beer search calls ``run_turn`` even when the stored flag is false.
    ``has_llm_key=false`` on a non-beer travel path is the Direct opt-out.
    """
    from zeus_dev_helper_mcp.beer import prereqs_prefer_beer_direct
    from zeus_dev_helper_mcp.prereqs import load_prereqs
    from zeus_dev_helper_mcp.walkthrough import _checklist_sample

    sample = _checklist_sample(cfg)
    prefs = load_prereqs(cfg)
    if sample == "beer" or prereqs_prefer_beer_direct(prefs):
        return True
    if sample == "travel" and prefs.get("has_llm_key") is False:
        return False
    if sample in {"travel", "api", "demo_yelp"}:
        return True
    return prefs.get("has_llm_key") is not False


def sync_checklist_llm_prereq(cfg: HelperConfig) -> None:
    """Mark checklist 1.2 done only when the URL and the key rule both hold."""
    from zeus_dev_helper_mcp.checklist import load_checklist, set_item_status

    if not (cfg.zeus_url or "").strip():
        return
    needs = path_needs_llm_key(cfg)
    has_key = llm_key_in_process_env()
    if has_key or not needs:
        evidence = (
            "ZEUS_URL set; LLM key present"
            if has_key
            else "ZEUS_URL set; LLM key not required for this path"
        )
        set_item_status(cfg, "1.2", "done", evidence=evidence)
        return
    data = load_checklist(cfg)
    for phase in data.get("phases") or []:
        for item in phase.get("items") or []:
            if item.get("id") != "1.2" or item.get("status") != "done":
                continue
            if str(item.get("evidence") or "") == "ZEUS_URL set":
                set_item_status(cfg, "1.2", "todo")
            return


def _dotenv_values(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    found: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key.lower().startswith("export "):
            key = key[7:].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        found[key] = value
    return found


def _example_key_names(path: Path) -> list[str]:
    names = []
    for name in _dotenv_values(path):
        if name in LLM_KEY_ENV_NAMES and name not in names:
            names.append(name)
    return names


def _declared_api_key_envs(doc: dict[str, Any]) -> list[tuple[str, str]] | None:
    found: list[tuple[str, str]] = []

    def _take(prefix: str, node: dict[str, Any]) -> None:
        if "api_key_env" in node:
            raw = node.get("api_key_env")
            found.append((f"{prefix}.api_key_env", raw.strip() if isinstance(raw, str) else ""))
        roles = node.get("roles")
        if isinstance(roles, dict):
            for role_name, role in roles.items():
                if isinstance(role, dict) and "api_key_env" in role:
                    raw = role.get("api_key_env")
                    found.append(
                        (
                            f"{prefix}.roles.{role_name}.api_key_env",
                            raw.strip() if isinstance(raw, str) else "",
                        )
                    )

    for key in ("llm", "llm_provider"):
        node = doc.get(key)
        if isinstance(node, dict):
            _take(key, node)
    return found or None


def inspect_app_llm_key(root: Path) -> dict[str, Any]:
    """Check the app directory. Report names and presence, never the secret."""
    root = Path(root)
    config_path = root / "config.json"
    example = root / ".env.example"
    dotenv = root / ".env"
    example_names = _example_key_names(example) if example.is_file() else []
    names: list[str] = []

    if config_path.is_file():
        try:
            doc = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {
                "applies": True,
                "ok": False,
                "message": "config.json is not valid JSON.",
            }
        if not isinstance(doc, dict):
            return {
                "applies": True,
                "ok": False,
                "message": "config.json must be a JSON object.",
            }
        declared = _declared_api_key_envs(doc)
        if declared is None and not example_names:
            return {"applies": False, "ok": True, "message": ""}
        if declared is None:
            names = example_names
        else:
            for field, value in declared:
                if not _ENV_NAME.match(value):
                    return {
                        "applies": True,
                        "ok": False,
                        "message": (
                            f"{field} must be an environment variable name such as "
                            "LLM_API_KEY. Put the secret only in .env."
                        ),
                    }
            names = []
            for _field, value in declared:
                if value not in names:
                    names.append(value)
    elif example_names:
        names = example_names
    else:
        return {"applies": False, "ok": True, "message": ""}

    values = _dotenv_values(dotenv)
    missing = [name for name in names if not (values.get(name) or "").strip()]
    shown = ", ".join(names)
    if missing:
        missing_shown = ", ".join(missing)
        return {
            "applies": True,
            "ok": False,
            "api_key_env": names[0] if len(names) == 1 else names,
            "message": (
                f"Set {missing_shown} in .env. "
                "Leave config.json llm.api_key_env as that name. "
                "Do not paste the secret into api_key_env. "
                "Then verify_local_setup."
            ),
        }
    return {
        "applies": True,
        "ok": True,
        "api_key_env": names[0] if len(names) == 1 else names,
        "message": f"{shown} is set in .env. api_key_env is that variable name.",
        "evidence": f"api_key_env={shown} present in .env",
    }
