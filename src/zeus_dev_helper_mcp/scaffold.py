"""Scaffold minimal Zeus Client middle-man app (ZDH-6 / ZDH-32)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from zeus_dev_helper_mcp.checklist import set_item_status
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.docs_links import docs_url

CLIENT_FLOOR = "2.3.0"

_MAIN_PY = '''#!/usr/bin/env python3
"""Minimal ZeusRuntime agent turn — scaffolded by zeus_dev_helper_mcp."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")

from zeus_client import ClientSettings, ZeusRuntime  # noqa: E402
from zeus_client.adapters.catalog_fs.store import FsCatalogStore  # noqa: E402
from zeus_client.adapters.llm_openai_compatible import OpenAICompatibleLlmClient  # noqa: E402
from zeus_client.adapters.zeus_http import HttpxZeusPort  # noqa: E402
from zeus_client.adapters.zeus_http.catalog_remote import HttpxCatalogRemote  # noqa: E402


async def main() -> None:
    rt = ZeusRuntime.from_config(_ROOT / "config.json", profile="development")
    secrets = rt.services.secrets
    if rt.config.chat_requests_dir:
        rt.services.catalog = FsCatalogStore(root=rt.config.chat_requests_dir)
    async with rt:
        rt.services.zeus = HttpxZeusPort(
            endpoint=rt.config.zeus, secrets=secrets, journal=rt.journal
        )
        rt.services.llm = OpenAICompatibleLlmClient(
            config=rt.config.llm, secrets=secrets, journal=rt.journal
        )
        if rt.services.catalog_remote is None:
            rt.services.catalog_remote = HttpxCatalogRemote(
                endpoint=rt.config.zeus, secrets=secrets
            )

        question = os.environ.get(
            "ZEUS_QUESTION",
            "In one short sentence, what data is available in this scope?",
        )
        chat_request = None
        try:
            loaded = await rt.catalog.load(mode=rt.config.settings.mode)
            chat_request = dict(loaded.body)
            print(f"Loaded catalog from {loaded.source}")
        except Exception as e:
            print(f"Catalog load warning: {e} (continuing without a local catalog)")

        result = await rt.agent.run_turn(
            question,
            settings=ClientSettings(ai_process_result=False),
            chat_request=chat_request,
        )
        print("Answer:", result.answer)
        print("Status:", getattr(result.status, "value", result.status))
        session = result.session
        debug = result.debug
        print(
            "session_id:",
            getattr(session, "session_id", None) or getattr(debug, "session_id", None),
        )
        print("round:", getattr(session, "round", None) or getattr(debug, "rounds", None))
        hops = list(getattr(debug, "hops", ()) or ())
        print("hops:", len(hops))
        req_ids = list(getattr(debug, "req_ids", ()) or ())
        if not req_ids:
            for hop in hops:
                if isinstance(hop, dict) and hop.get("req_id"):
                    req_ids.append(hop["req_id"])
        for rid in req_ids[:5]:
            print("req_id:", rid)


if __name__ == "__main__":
    asyncio.run(main())
'''

SAMPLE_TRAVEL = {
    "name": "demo_travel_sample",
    "repo": "https://github.com/koten-ai/demo_travel_sample",
    "note": "Primary single-agent demo (may be private → public). Clone when you have access.",
    "clone": "git clone https://github.com/koten-ai/demo_travel_sample.git",
    "related": [
        "https://github.com/koten-ai/zeus_client_python/tree/main/docs/demo-builder",
        "https://docs.koten.ai/zeus-client/using-zeus-client",
    ],
}


def use_sample(cfg: HelperConfig, sample: str = "travel", sample_dir: str = "") -> dict[str, Any]:
    """Point at a sample path. Travel uses ZDH-10 golden-path validation."""
    sample = (sample or "travel").lower().strip()
    if sample in ("travel", "demo_travel", "travel_sample", "demo_travel_sample"):
        from zeus_dev_helper_mcp.travel import travel_golden_path

        golden = travel_golden_path(cfg, sample_dir=sample_dir)
        info = dict(SAMPLE_TRAVEL)
        info["sample"] = "travel"
        return {
            "ok": True,
            "sample": info,
            "golden_path": golden,
            "local_dir": golden.get("local_dir"),
            "layout": golden.get("layout"),
            "next_action": golden.get("next_action")
            or (
                "Clone the sample if you have access, or call scaffold_app "
                "for a minimal middle-man without the full demo UI."
            ),
            "checklist_hint": "Mark 3.1 done after clone/scaffold succeeds",
            "sample_readme_snippet": golden.get("sample_readme_snippet"),
        }
    if sample in ("yelp", "multi"):
        from zeus_dev_helper_mcp.handoff import handoff_to_multi

        handoff = handoff_to_multi(cfg, force=False)
        return {
            "ok": False,
            "sample": sample,
            "blocked": True,
            "handoff_to_multi": handoff,
            "next_action": (
                "Multi-agent / Yelp path is stretch (ZDH-11). "
                "Call handoff_to_multi after single-agent green, or force=true."
            ),
        }
    return {
        "ok": False,
        "sample": sample,
        "next_action": "Use sample=travel or scaffold_app for custom domain",
    }


def _llm_api_key_env() -> str:
    for name in ("LLM_API_KEY", "XAI_API_KEY", "OPENAI_API_KEY"):
        if os.environ.get(name):
            return name
    return "LLM_API_KEY"


def runtime_config_dict(cfg: HelperConfig) -> dict[str, Any]:
    """RuntimeConfig JSON shape (env *names* only — never secret values)."""
    auth_mode = (cfg.zeus_auth_mode or "none").strip().lower()
    if auth_mode not in {"none", "basic", "bearer", "session", "certificate"}:
        auth_mode = "none"
    zeus: dict[str, Any] = {
        "url": (cfg.zeus_url or "http://localhost:8080").rstrip("/"),
        "auth_mode": auth_mode,
        "timeout_s": 30,
    }
    user = (os.environ.get("ZEUS_USERNAME") or os.environ.get("ZEUS_USER") or "").strip()
    if user:
        zeus["username"] = user
    if auth_mode == "basic":
        zeus["password_env"] = "ZEUS_PASSWORD"
    elif auth_mode in {"bearer", "session"}:
        zeus["token_env"] = "ZEUS_BEARER_TOKEN" if auth_mode == "bearer" else "ZEUS_SESSION_ID"
    return {
        "profile": "development",
        "zeus": zeus,
        "target": {
            "bucket": cfg.default_bucket or "beer-sample",
            "scope": cfg.default_scope or "_default",
            "collection": cfg.default_collection or "_default",
        },
        "llm": {
            "provider": "xai",
            "base_url": (os.environ.get("LLM_BASE_URL") or "https://api.x.ai/v1").rstrip("/"),
            "model": os.environ.get("LLM_MODEL") or "grok-4-1-fast-non-reasoning",
            "api_key_env": _llm_api_key_env(),
            "timeout_s": 120,
        },
        "settings": {
            "ai_process_result": False,
            "max_rounds": 8,
            "force_trace": False,
            "mode": cfg.default_mode or "analytics",
            "durable_sessions": True,
        },
        "session": {"semantic_cache": {"enabled": False}},
        "chat_requests_dir": str(cfg.chat_request_dir) if cfg.chat_request_dir else None,
    }


def write_env_example(cfg: HelperConfig, target_dir: str | Path) -> dict[str, Any]:
    root = Path(target_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = root / ".env.example"
    content = f"""# Copy to .env and fill secrets (never commit .env)
ZEUS_URL={cfg.zeus_url or "http://localhost:8080"}
ZEUS_AUTH_MODE={cfg.zeus_auth_mode or "none"}
# ZEUS_USERNAME=
# ZEUS_PASSWORD=
# ZEUS_BEARER_TOKEN=
ZEUS_BUCKET={cfg.default_bucket or "beer-sample"}
ZEUS_SCOPE={cfg.default_scope or "_default"}
ZEUS_COLLECTION={cfg.default_collection or "_default"}
ZEUS_MODE={cfg.default_mode or "analytics"}
# OpenAI-compatible LLM (config.json llm.api_key_env points at this name)
LLM_BASE_URL=https://api.x.ai/v1
LLM_API_KEY=
LLM_MODEL=grok-4-1-fast-non-reasoning
# session.semantic_cache.enabled stays false unless you opt in (Zeus >= 0.7.6)
"""
    path.write_text(content)
    return {"ok": True, "path": str(path), "note": "No secrets written — placeholders only"}


def scaffold_app(
    cfg: HelperConfig,
    target_dir: str,
    *,
    project_name: str = "zeus_first_app",
    force: bool = False,
) -> dict[str, Any]:
    """Write a minimal ZeusRuntime middle-man (config.json + main.py + env example)."""
    root = Path(target_dir).expanduser().resolve()
    if root.exists() and any(root.iterdir()) and not force:
        existing = list(root.iterdir())
        if existing and not (root / "main.py").exists() and not force:
            return {
                "ok": False,
                "error": f"target_dir not empty: {root}",
                "next_action": "Pick an empty directory or pass force=true",
            }
    root.mkdir(parents=True, exist_ok=True)

    runtime_cfg = runtime_config_dict(cfg)
    bucket = runtime_cfg["target"]["bucket"]
    scope = runtime_cfg["target"]["scope"]
    collection = runtime_cfg["target"]["collection"]
    mode = runtime_cfg["settings"]["mode"]
    zeus_url = runtime_cfg["zeus"]["url"]
    slug = project_name.replace(" ", "-").lower()

    files: dict[str, str] = {}

    files["README.md"] = f"""# {project_name}

Minimal ZeusRuntime middle-man scaffolded by **zeus_dev_helper_mcp**.

Requires `kotenai-zeus-client>={CLIENT_FLOOR}`. Default path is `ZeusRuntime.from_config()`
plus `HttpxZeusPort` / `OpenAICompatibleLlmClient`. Do not import `zeus_client.compat.v1`.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill LLM_API_KEY and Zeus auth if needed
```

Edit `config.json` target (bucket / scope / collection) if Helper prereqs were empty.
Never invent `contract.hash`. Public API is `:8080`, not Hub `:9091`.

## Run

```bash
python main.py
```

## Docs

- https://docs.koten.ai/zeus-client/using-zeus-client
- https://github.com/koten-ai/zeus_chat_request (min catalog templates)
"""

    files["requirements.txt"] = (
        f"kotenai-zeus-client>={CLIENT_FLOOR}\nhttpx>=0.27.0\npython-dotenv>=1.0.0\n"
    )
    files["main.py"] = _MAIN_PY
    files["config.json"] = json.dumps(runtime_cfg, indent=2) + "\n"
    files["pyproject.toml"] = f"""[project]
name = "{slug}"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "kotenai-zeus-client>={CLIENT_FLOOR}",
  "httpx>=0.27.0",
  "python-dotenv>=1.0.0",
]
"""

    written: list[str] = []
    for name, body in files.items():
        path = root / name
        if path.exists() and not force:
            continue
        path.write_text(body)
        written.append(str(path))

    env_info = write_env_example(cfg, root)

    # Also write a tiny config hint JSON (no secrets)
    hint = {
        "zeus_url": zeus_url,
        "bucket": bucket,
        "scope": scope,
        "collection": collection,
        "mode": mode,
        "from": "zeus_dev_helper_mcp.scaffold_app",
    }
    hint_path = root / "scaffold_meta.json"
    hint_path.write_text(json.dumps(hint, indent=2) + "\n")
    written.append(str(hint_path))

    try:
        set_item_status(cfg, "3.1", "done", evidence=f"scaffold={root}")
        set_item_status(cfg, "3.2", "done", evidence=str(env_info.get("path")))
    except Exception:  # noqa: BLE001
        pass

    return {
        "ok": True,
        "target_dir": str(root),
        "written": written,
        "env_example": env_info,
        "run": f"cd {root} && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && cp .env.example .env && python main.py",
        "next_action": (
            "Fill .env secrets, install deps, run main.py "
            "(ZeusRuntime + run_turn); then smoke_test_agent via Helper or locally"
        ),
        "docs": {
            "using": docs_url("zeus-client/using-zeus-client.md"),
            "recipe_01": docs_url("zeus-client/recipes/01-minimal-qa.md"),
        },
    }


def verify_local_setup(cfg: HelperConfig, target_dir: str = "") -> dict[str, Any]:
    """Check imports and basic project layout."""
    checks: list[dict[str, Any]] = []
    # zeus_client import
    try:
        import zeus_client  # type: ignore

        checks.append({"name": "import_zeus_client", "ok": True, "version": getattr(zeus_client, "__version__", "?")})
    except ImportError as e:
        checks.append(
            {
                "name": "import_zeus_client",
                "ok": False,
                "error": str(e),
                "next_action": "pip install kotenai-zeus-client",
            }
        )

    root = Path(target_dir).expanduser() if target_dir else None
    if root and root.is_dir():
        for name in ("main.py", "config.json", "requirements.txt", ".env.example"):
            p = root / name
            checks.append({"name": f"file:{name}", "ok": p.is_file(), "path": str(p)})
        env_path = root / ".env"
        checks.append(
            {
                "name": "file:.env",
                "ok": env_path.is_file(),
                "note": "optional until you copy from .env.example",
            }
        )

    ok = all(c.get("ok") for c in checks if c["name"] == "import_zeus_client")
    return {
        "ok": ok,
        "checks": checks,
        "config": cfg.public_view(),
        "next_action": "Install missing deps or scaffold_app if files missing",
    }
