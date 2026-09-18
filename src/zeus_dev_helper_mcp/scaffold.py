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

_API_MAIN_PY = '''#!/usr/bin/env python3
"""Minimal FastAPI ZeusRuntime REST middle-man — scaffolded by zeus_dev_helper_mcp."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")

from zeus_client import ClientSettings, ZeusRuntime  # noqa: E402
from zeus_client.adapters.catalog_fs.store import FsCatalogStore  # noqa: E402
from zeus_client.adapters.llm_openai_compatible import OpenAICompatibleLlmClient  # noqa: E402
from zeus_client.adapters.zeus_http import HttpxZeusPort  # noqa: E402
from zeus_client.adapters.zeus_http.catalog_remote import HttpxCatalogRemote  # noqa: E402

_runtime: ZeusRuntime | None = None


class TurnRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Advice-shaped natural language question")


class TurnResponse(BaseModel):
    answer: str | None = None
    status: str | None = None
    session_id: str | None = None
    req_ids: list[str] = Field(default_factory=list)
    hops: int = 0


async def _wire_runtime(rt: ZeusRuntime) -> None:
    secrets = rt.services.secrets
    if rt.config.chat_requests_dir:
        rt.services.catalog = FsCatalogStore(root=rt.config.chat_requests_dir)
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _runtime
    rt = ZeusRuntime.from_config(_ROOT / "config.json", profile="development")
    await rt.__aenter__()
    await _wire_runtime(rt)
    _runtime = rt
    try:
        yield
    finally:
        _runtime = None
        await rt.__aexit__(None, None, None)


app = FastAPI(title="Zeus first API app", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/turn", response_model=TurnResponse)
async def turn(body: TurnRequest) -> TurnResponse:
    if _runtime is None:
        raise HTTPException(status_code=503, detail="runtime not ready")
    chat_request = None
    try:
        loaded = await _runtime.catalog.load(mode=_runtime.config.settings.mode)
        chat_request = dict(loaded.body)
    except Exception:
        chat_request = None
    result = await _runtime.agent.run_turn(
        body.question,
        settings=ClientSettings(ai_process_result=False),
        chat_request=chat_request,
    )
    session = result.session
    debug = result.debug
    hops = list(getattr(debug, "hops", ()) or ())
    req_ids = list(getattr(debug, "req_ids", ()) or ())
    if not req_ids:
        for hop in hops:
            if isinstance(hop, dict) and hop.get("req_id"):
                req_ids.append(str(hop["req_id"]))
    return TurnResponse(
        answer=getattr(result, "answer", None),
        status=str(getattr(result.status, "value", result.status)),
        session_id=getattr(session, "session_id", None) or getattr(debug, "session_id", None),
        req_ids=[str(r) for r in req_ids[:8]],
        hops=len(hops),
    )


def main() -> None:
    import uvicorn

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
'''

SUPPORTED_CODING_LANGUAGES = frozenset({"python"})
APP_KINDS = frozenset({"cli", "api"})
FAILURE_UNSUPPORTED_LANG = "unsupported_coding_language"

SAMPLE_TRAVEL = {
    "name": "demo_travel_sample",
    "repo": "https://github.com/koten-ai/demo_travel_sample",
    "note": "Primary single-agent UI demo (public). use_sample clones when no local path is set.",
    "clone": "git clone --depth 1 https://github.com/koten-ai/demo_travel_sample.git",
    "related": [
        "https://github.com/koten-ai/zeus_client_python/tree/main/docs/demo-builder",
        "https://docs.koten.ai/zeus-client/using-zeus-client",
    ],
}


def use_sample(
    cfg: HelperConfig,
    sample: str = "travel",
    sample_dir: str = "",
    project_name: str = "",
    parent_dir: str = "",
    clone_if_missing: bool = True,
) -> dict[str, Any]:
    """UI sample path: travel clone or beer Direct template.

    travel: locate/clone public demo_travel_sample; set DEMO_TRAVEL_SAMPLE_DIR.
    beer: write zero-LLM Direct catalog UI (default dir demo_beer_sample).
    For API-only apps use scaffold_app(app_kind=api).
    """
    sample = (sample or "travel").lower().strip()
    if sample in ("travel", "demo_travel", "travel_sample", "demo_travel_sample", "ui"):
        from zeus_dev_helper_mcp.travel import travel_golden_path

        golden = travel_golden_path(
            cfg,
            sample_dir=sample_dir,
            project_name=project_name,
            parent_dir=parent_dir,
            clone_if_missing=clone_if_missing,
        )
        info = dict(SAMPLE_TRAVEL)
        info["sample"] = "travel"
        info["app_kind"] = "ui"
        info["private"] = False
        return {
            "ok": bool(golden.get("ok")),
            "sample": info,
            "app_kind": "ui",
            "golden_path": golden,
            "local_dir": golden.get("local_dir"),
            "cloned": golden.get("cloned"),
            "project_name": golden.get("project_name"),
            "layout": golden.get("layout"),
            "docker": golden.get("docker"),
            "docker_setup": golden.get("docker_setup"),
            "env": golden.get("env"),
            "next_action": golden.get("next_action")
            or (
                "Set DEMO_TRAVEL_SAMPLE_DIR after clone, or scaffold_app "
                "for a minimal middle-man without the full demo UI."
            ),
            "checklist_hint": "Mark 3.1 done after clone/scaffold succeeds",
            "sample_readme_snippet": golden.get("sample_readme_snippet"),
        }
    from zeus_dev_helper_mcp.beer import SAMPLE_BEER, ensure_beer_sample, is_beer_sample

    if is_beer_sample(sample):
        ensured = ensure_beer_sample(
            cfg,
            sample_dir=sample_dir,
            project_name=project_name,
            parent_dir=parent_dir,
        )
        info = dict(SAMPLE_BEER)
        info["sample"] = "beer"
        info["app_kind"] = "ui"
        info["track"] = "ui-direct"
        info["llm_required"] = False
        return {
            "ok": bool(ensured.get("ok")),
            "sample": info,
            "app_kind": "ui",
            "track": "ui-direct",
            "llm_required": False,
            "local_dir": ensured.get("local_dir") or ensured.get("target_dir"),
            "written": ensured.get("written"),
            "project_name": ensured.get("project_name"),
            "layout": ensured.get("layout"),
            "env": ensured.get("env"),
            "run": ensured.get("run"),
            "files": ensured.get("files"),
            "env_example": ensured.get("env_example"),
            "error": ensured.get("error"),
            "next_action": ensured.get("next_action")
            or (
                "Set ZEUS_URL in .env (no LLM key), run uvicorn, then smoke_test_zeus. "
                "smoke_test_agent is not required on this Direct track."
            ),
            "checklist_hint": "Mark 3.1 done after the beer Direct UI is on disk",
            "docs": ensured.get("docs"),
        }
    if sample in ("api", "rest", "api_only", "api-only"):
        return {
            "ok": False,
            "sample": sample,
            "app_kind": "api",
            "next_action": (
                "API-only apps use scaffold_app(app_kind=api, coding_language=python). "
                "start_project(sample=api) then scaffold — not use_sample."
            ),
            "recommended_tools": ["scaffold_app", "start_project"],
            "docs": {"using": docs_url("zeus-client/using-zeus-client.md")},
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
        "next_action": (
            "Use sample=travel (LLM UI), sample=beer (Direct catalog UI), "
            "or scaffold_app for custom domain"
        ),
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
    app_kind: str = "cli",
    coding_language: str = "python",
) -> dict[str, Any]:
    """Write a ZeusRuntime middle-man.

    app_kind:
      - cli — one-shot main.py (default for this tool)
      - api — FastAPI REST (POST /turn) using kotenai-zeus-client (python only today)

    Prefer use_sample / demo_travel_sample when the user wants a UI app (default bootstrap).
    """
    lang = (coding_language or "python").strip().lower().replace("-", "_")
    if lang in {"py", "python3"}:
        lang = "python"
    kind = (app_kind or "cli").strip().lower().replace("-", "_")
    if kind in {"rest", "api_only", "fastapi"}:
        kind = "api"
    if kind in {"script", "main", "middle_man", "middleman"}:
        kind = "cli"

    docs = {
        "using": docs_url("zeus-client/using-zeus-client.md"),
        "recipe_01": docs_url("zeus-client/recipes/01-minimal-qa.md"),
    }

    if lang not in SUPPORTED_CODING_LANGUAGES:
        return {
            "ok": False,
            "failure_class": FAILURE_UNSUPPORTED_LANG,
            "coding_language": lang,
            "supported_coding_languages": sorted(SUPPORTED_CODING_LANGUAGES),
            "client_packages": {
                "python": "kotenai-zeus-client (zeus_client_python)",
                "golang": "not scaffolded by Helper yet",
                "node": "not scaffolded by Helper yet",
            },
            "app_kind": kind,
            "next_action": (
                "Pass coding_language=python for API/CLI scaffolds. "
                "For a UI demo use use_sample (demo_travel_sample). "
                "Do not invent zeus_client_golang / zeus_client_node scaffolds here yet."
            ),
            "recommended_tools": ["scaffold_app", "use_sample"],
            "docs": docs,
        }

    if kind not in APP_KINDS:
        return {
            "ok": False,
            "failure_class": "invalid_app_kind",
            "app_kind": app_kind,
            "known_app_kinds": sorted(APP_KINDS),
            "next_action": "Pass app_kind=cli|api (UI apps use use_sample / demo_travel_sample)",
            "recommended_tools": ["scaffold_app", "use_sample"],
            "docs": docs,
        }

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
    if kind == "api":
        default_name = project_name if project_name != "zeus_first_app" else "zeus_first_api"
        slug = default_name.replace(" ", "-").lower()
        files["README.md"] = f"""# {default_name}

FastAPI REST middle-man for Zeus, scaffolded by **zeus_dev_helper_mcp**.

Uses `kotenai-zeus-client>={CLIENT_FLOOR}` (`zeus_client_python`): `ZeusRuntime` +
`HttpxZeusPort` + `OpenAICompatibleLlmClient`. Do not import `zeus_client.compat.v1`.

This is an **API-only** app (no demo UI). For the travel planner UI use
`demo_travel_sample` via Helper `use_sample`.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # ZEUS_URL, ZEUS_USERNAME/ZEUS_PASSWORD or bearer, LLM_API_KEY
```

Never invent `contract.hash`. Public API is `:8080`, not Hub `:9091`.
Secrets stay in `.env` — never commit them.

## Run

```bash
uvicorn main:app --host 127.0.0.1 --port 8000
# or: python main.py
```

## Endpoints

- `GET /healthz` → `{{"status":"ok"}}`
- `POST /turn` body `{{"question":"…"}}` → answer + `session_id` / `req_ids` / hops

```bash
curl -s http://127.0.0.1:8000/healthz
curl -s -X POST http://127.0.0.1:8000/turn \\
  -H 'content-type: application/json' \\
  -d '{{"question":"In one short sentence, what data is available in this scope?"}}'
```

## Docs

- https://docs.koten.ai/zeus-client/using-zeus-client
- https://github.com/koten-ai/zeus_chat_request (min catalog templates)
"""
        files["requirements.txt"] = (
            f"kotenai-zeus-client>={CLIENT_FLOOR}\n"
            "httpx>=0.27.0\n"
            "python-dotenv>=1.0.0\n"
            "fastapi>=0.115.0\n"
            "uvicorn[standard]>=0.30.0\n"
        )
        files["main.py"] = _API_MAIN_PY
        files["pyproject.toml"] = f"""[project]
name = "{slug}"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "kotenai-zeus-client>={CLIENT_FLOOR}",
  "httpx>=0.27.0",
  "python-dotenv>=1.0.0",
  "fastapi>=0.115.0",
  "uvicorn[standard]>=0.30.0",
]
"""
        run_cmd = (
            f"cd {root} && python3 -m venv .venv && source .venv/bin/activate && "
            "pip install -r requirements.txt && cp .env.example .env && "
            "uvicorn main:app --host 127.0.0.1 --port 8000"
        )
        next_action = (
            "Put ZEUS_URL / credentials / LLM_API_KEY in .env (never in MCP tool args), "
            "install deps, run uvicorn; then Helper smoke_test_zeus / smoke_test_agent "
            "or curl POST /turn"
        )
        project_name = default_name
    else:
        files["README.md"] = f"""# {project_name}

Minimal ZeusRuntime middle-man scaffolded by **zeus_dev_helper_mcp**.

Requires `kotenai-zeus-client>={CLIENT_FLOOR}`. Default path is `ZeusRuntime.from_config()`
plus `HttpxZeusPort` / `OpenAICompatibleLlmClient`. Do not import `zeus_client.compat.v1`.

For a **UI** demo prefer `use_sample` / `demo_travel_sample`. For a **REST API** use
`scaffold_app(app_kind=api)`.

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
        run_cmd = (
            f"cd {root} && python3 -m venv .venv && source .venv/bin/activate && "
            "pip install -r requirements.txt && cp .env.example .env && python main.py"
        )
        next_action = (
            "Fill .env secrets, install deps, run main.py "
            "(ZeusRuntime + run_turn); then smoke_test_agent via Helper or locally"
        )

    files["config.json"] = json.dumps(runtime_cfg, indent=2) + "\n"

    written: list[str] = []
    for name, body in files.items():
        path = root / name
        if path.exists() and not force:
            continue
        path.write_text(body)
        written.append(str(path))

    env_info = write_env_example(cfg, root)

    hint = {
        "zeus_url": zeus_url,
        "bucket": bucket,
        "scope": scope,
        "collection": collection,
        "mode": mode,
        "app_kind": kind,
        "coding_language": lang,
        "client_package": "kotenai-zeus-client",
        "from": "zeus_dev_helper_mcp.scaffold_app",
    }
    hint_path = root / "scaffold_meta.json"
    hint_path.write_text(json.dumps(hint, indent=2) + "\n")
    written.append(str(hint_path))

    try:
        set_item_status(cfg, "3.1", "done", evidence=f"scaffold={kind}:{root}")
        set_item_status(cfg, "3.2", "done", evidence=str(env_info.get("path")))
    except Exception:  # noqa: BLE001, S110
        pass

    return {
        "ok": True,
        "target_dir": str(root),
        "app_kind": kind,
        "coding_language": lang,
        "client_package": "kotenai-zeus-client",
        "written": written,
        "env_example": env_info,
        "secrets_note": (
            "Put username/password/token/LLM keys in .env or the process environment. "
            "Never pass secret values into MCP tools — set_prereq uses presence flags only."
        ),
        "run": run_cmd,
        "next_action": next_action,
        "docs": docs,
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
