"""Scaffold minimal Zeus Client middle-man app (ZDH-6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from zeus_dev_helper_mcp.checklist import set_item_status
from zeus_dev_helper_mcp.config import HelperConfig

SAMPLE_TRAVEL = {
    "name": "demo_travel_sample",
    "repo": "https://github.com/koten-ai/demo_travel_sample",
    "note": "Primary single-agent demo (may be private → public). Clone when you have access.",
    "clone": "git clone https://github.com/koten-ai/demo_travel_sample.git",
    "related": [
        "https://github.com/koten-ai/zeus_client_python/tree/main/docs/demo-builder",
        "https://github.com/koten-ai/koten_docs/blob/zeus-v1.0.0/zeus-client/using-zeus-client.md",
    ],
}


def use_sample(cfg: HelperConfig, sample: str = "travel") -> dict[str, Any]:
    sample = (sample or "travel").lower().strip()
    if sample in ("travel", "demo_travel", "travel_sample", "demo_travel_sample"):
        info = dict(SAMPLE_TRAVEL)
        info["sample"] = "travel"
        try:
            set_item_status(cfg, "0.2", "done", evidence="sample=travel")
        except Exception:  # noqa: BLE001
            pass
        return {
            "ok": True,
            "sample": info,
            "next_action": (
                "Clone the sample if you have access, or call scaffold_app "
                "for a minimal middle-man without the full demo UI."
            ),
            "checklist_hint": "Mark 3.1 done after clone/scaffold succeeds",
        }
    if sample in ("yelp", "multi"):
        return {
            "ok": False,
            "sample": sample,
            "next_action": "Multi-agent / Yelp path is stretch (ZDH-11). Finish single-agent green first.",
            "blocked": True,
        }
    return {
        "ok": False,
        "sample": sample,
        "next_action": "Use sample=travel or scaffold_app for custom domain",
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
# OpenAI-compatible LLM
LLM_BASE_URL=https://api.x.ai/v1
LLM_API_KEY=
LLM_MODEL=grok-4-1-fast-non-reasoning
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
    """Write a minimal runnable Zeus Client script + env example."""
    root = Path(target_dir).expanduser().resolve()
    if root.exists() and any(root.iterdir()) and not force:
        # allow if only empty or our marker
        existing = list(root.iterdir())
        if existing and not (root / "main.py").exists() and not force:
            return {
                "ok": False,
                "error": f"target_dir not empty: {root}",
                "next_action": "Pick an empty directory or pass force=true",
            }
    root.mkdir(parents=True, exist_ok=True)

    bucket = cfg.default_bucket or "beer-sample"
    scope = cfg.default_scope or "_default"
    collection = cfg.default_collection or "_default"
    mode = cfg.default_mode or "analytics"
    zeus_url = cfg.zeus_url or "http://localhost:8080"

    files: dict[str, str] = {}

    files["README.md"] = f"""# {project_name}

Minimal Zeus Client middle-man scaffolded by **zeus_dev_helper_mcp**.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill LLM_API_KEY and Zeus auth if needed
```

## Run

```bash
python main.py
```

## Docs

- https://github.com/koten-ai/koten_docs/blob/zeus-v1.0.0/zeus-client/using-zeus-client.md
- https://github.com/koten-ai/zeus_chat_request (min catalog templates)
"""

    files["requirements.txt"] = "kotenai-zeus-client>=1.0.0\nhttpx>=0.27.0\npython-dotenv>=1.0.0\n"

    files["main.py"] = f'''#!/usr/bin/env python3
"""Minimal Zeus Client agent turn — scaffolded by zeus_dev_helper_mcp."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from zeus_client import (
    ZeusClient,
    load_config,
    resolve_llm_provider_config,
    resolve_zeus_config,
    run_agent,
    sync_chat_requests,
)


async def main() -> None:
    # Optional: pin config dir next to this project
    # os.environ.setdefault("ZEUS_CLIENT_CONFIG_DIR", str(Path(__file__).parent / ".zeus_client"))

    async with ZeusClient():
        cfg = await load_config()
        # Prefer env overrides from Helper / .env
        zeus_url = os.environ.get("ZEUS_URL", "{zeus_url}").rstrip("/")
        if isinstance(cfg.get("zeus"), dict):
            cfg["zeus"]["url"] = zeus_url

        zcfg = resolve_zeus_config(cfg)
        provider = resolve_llm_provider_config(cfg)

        try:
            result = await sync_chat_requests(cfg)
            print(f"Synced {{len(result.synced)}} catalog(s)")
        except Exception as e:
            print(f"Catalog sync warning: {{e}} (continuing with local/bundled catalogs)")

        bucket = os.environ.get("ZEUS_BUCKET", "{bucket}")
        scope = os.environ.get("ZEUS_SCOPE", "{scope}")
        collection = os.environ.get("ZEUS_COLLECTION", "{collection}")
        mode = os.environ.get("ZEUS_MODE", "{mode}")
        api_version = cfg.get("default_api_version", "v2")

        # Prefer client samples if bucket not overridden and samples exist
        samples = cfg.get("samples") or {{}}
        default_sample = cfg.get("default_sample")
        if default_sample and default_sample in samples and not os.environ.get("ZEUS_BUCKET"):
            sample = samples[default_sample]
            bucket = sample.get("bucket", bucket)
            scope = sample.get("scope", scope)
            collection = sample.get("collection", collection)

        question = os.environ.get(
            "ZEUS_QUESTION",
            "In one short sentence, what data is available in this scope?",
        )

        answer, trace, turns, session_meta = await run_agent(
            zcfg["url"],
            zcfg,
            provider["base_url"],
            provider["api_key"],
            provider["models"][0],
            api_version,
            mode,
            bucket,
            scope,
            collection,
            question,
            prior_turns=[],
        )

        print("Answer:", answer)
        print("session_id:", session_meta.get("session_id"))
        print("round:", session_meta.get("round"))
        tool_calls = (trace or {{}}).get("tool_calls") or []
        print("tool_calls:", len(tool_calls) if isinstance(tool_calls, list) else tool_calls)
        # Log req_ids when present for Detective
        if isinstance(tool_calls, list):
            for tc in tool_calls[:5]:
                if isinstance(tc, dict) and tc.get("req_id"):
                    print("req_id:", tc.get("req_id"))


if __name__ == "__main__":
    asyncio.run(main())
'''

    files["pyproject.toml"] = f"""[project]
name = "{project_name.replace(" ", "-").lower()}"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "kotenai-zeus-client>=1.0.0",
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
        "next_action": "Fill .env secrets, install deps, run main.py; then smoke_test_agent via Helper or locally",
        "docs": {
            "using": f"https://github.com/koten-ai/koten_docs/blob/{cfg.docs_branch}/zeus-client/using-zeus-client.md",
            "recipe_01": f"https://github.com/koten-ai/koten_docs/blob/{cfg.docs_branch}/zeus-client/recipes/01-minimal-qa.md",
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
        for name in ("main.py", "requirements.txt", ".env.example"):
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
