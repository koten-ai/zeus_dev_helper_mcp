"""Yelp-demo app written by use_sample(sample=demo_yelp).

Search is one agent turn. The handler calls ``rt.agent.run_turn`` and leaves
``chat_request`` unset so ``catalog.load_for_turn`` reads

``data/chat_requests/yelp-demo__default/chat_request_analytics_v2.json``.

Suggest, the header count, and the business page page ``find`` on ``User``
and keep ``biz:`` rows. Those routes are not the search turn.
"""

from __future__ import annotations

import inspect
import json
import os
import textwrap
from pathlib import Path
from typing import Any

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.docs_links import docs_url
from zeus_dev_helper_mcp.yelp import (
    DEFAULT_YELP_DIR_NAME,
    ENV_YELP_DIR,
    YELP_BUCKET,
    YELP_SCOPE,
    _resolve_clone_dest,
    sanitize_yelp_dir_name,
    save_yelp_sample_dir,
    set_demo_yelp_sample_dir_env,
)

YELP_PORT = 8110
_CATALOG_NAME = "chat_request_analytics_v2.json"
_SCOPE_DIR = "yelp-demo__default"

_VERB_NAMES = frozenset(
    {
        "pipeline",
        "find",
        "search",
        "describe",
        "get",
        "count",
        "traverse",
        "project",
        "order",
        "return",
    }
)
_SIGNAL_KEYS = (
    "city",
    "category",
    "categories",
    "rating",
    "stars",
    "average_stars",
    "review_count",
    "address",
)


def _parse_blob(payload: Any) -> Any:
    if isinstance(payload, str):
        text = payload.strip()
        if not text or text[0] not in "{[":
            return None
        try:
            return json.loads(text)
        except (TypeError, ValueError):
            return None
    return payload


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _meta(row: dict[str, Any]) -> dict[str, Any]:
    meta = row.get("metadata")
    return meta if isinstance(meta, dict) else {}


def _biz_id(row: dict[str, Any]) -> str:
    for source in (row, _meta(row)):
        for key in ("doc_key", "business_id", "id", "source"):
            text = _text(source.get(key))
            if text.startswith("biz:"):
                return text
    return ""


def _has_business_signal(row: dict[str, Any]) -> bool:
    """True for a biz: id, city, category, rating, review count, or address."""
    if _biz_id(row):
        return True
    for source in (row, _meta(row)):
        for key in _SIGNAL_KEYS:
            if source.get(key) not in (None, "", [], {}):
                return True
    return False


def _display_name(row: dict[str, Any]) -> str:
    """Business name. A hop's verb name is not a business."""
    for source in (row, _meta(row)):
        for key in ("name", "title"):
            text = _text(source.get(key))
            if text and text.casefold() not in _VERB_NAMES:
                return text
    return ""


def _pick(row: dict[str, Any], *keys: str) -> Any:
    for source in (row, _meta(row)):
        for key in keys:
            val = source.get(key)
            if val not in (None, ""):
                return val
    return None


def card_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """One business card. A bare verb name is not a card."""
    if not isinstance(row, dict) or not _has_business_signal(row):
        return None
    name = _display_name(row)
    if not name:
        return None
    category = _pick(row, "category", "categories")
    return {
        "id": _biz_id(row) or _text(_pick(row, "id", "node_id")),
        "name": name,
        "city": _text(_pick(row, "city")),
        "category": category if category is not None else "",
        "rating": _pick(row, "rating", "stars", "average_stars"),
        "review_count": _pick(row, "review_count"),
        "address": _text(_pick(row, "address")),
    }


def is_biz_user(row: dict[str, Any]) -> bool:
    """Direct-read row: graph type User (when set) and a biz: doc key."""
    if not isinstance(row, dict) or not _biz_id(row):
        return False
    kind = _text(row.get("type") or row.get("entity_type"))
    return not kind or kind == "User"


def collect_yelp_cards(blobs: list[Any], *, limit: int = 24) -> list[dict[str, Any]]:
    """Cards from a turn. Hop records use name for the verb, so name alone is not enough."""
    found: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(card: dict[str, Any]) -> None:
        key = (card.get("id") or card["name"]).casefold()
        if key in seen:
            return
        seen.add(key)
        found.append(card)

    def walk(payload: Any, depth: int = 0) -> None:
        if depth > 8 or len(found) >= limit:
            return
        payload = _parse_blob(payload)
        if payload is None:
            return
        if isinstance(payload, list):
            for item in payload:
                walk(item, depth + 1)
            return
        if not isinstance(payload, dict):
            return
        card = card_from_row(payload)
        if card is not None:
            add(card)
        for key, val in payload.items():
            if key in {"args", "where", "input", "parameters"}:
                continue
            if isinstance(val, (dict, list)) or (
                isinstance(val, str) and val.lstrip()[:1] in "{["
            ):
                walk(val, depth + 1)

    for blob in blobs:
        walk(blob)
        if len(found) >= limit:
            break
    return found[: max(0, limit)]


def scope_catalog_dirname(bucket: str, scope: str) -> str:
    """yelp-demo / _default → yelp-demo__default. No base_id in the name."""
    tail = scope[1:] if scope.startswith("_") else scope
    return f"{bucket}__{tail}"


def yelp_target(cfg: HelperConfig) -> tuple[str, str]:
    """Bucket and scope for the written app. Beer and travel buckets stay off this path."""
    bucket = (cfg.default_bucket or "").strip()
    if bucket in {"", "beer-sample", "travel-sample", "yelp-data"}:
        bucket = YELP_BUCKET
    scope = (cfg.default_scope or "").strip() or YELP_SCOPE
    return bucket, scope


def _catalog_sources(cfg: HelperConfig | None) -> list[Path]:
    """On-disk analytics catalog for this scope, then the brief-free template."""
    roots: list[Path] = []
    if cfg is not None and cfg.chat_request_dir is not None:
        roots.append(Path(cfg.chat_request_dir))
    env = os.environ.get("ZEUS_CHAT_REQUEST_DIR", "").strip()
    if env:
        roots.append(Path(env).expanduser())
    here = Path(__file__).resolve()
    roots.append(here.parents[3] / "demo_yelp" / "data" / "chat_requests")
    roots.append(here.parents[3] / "zeus_chat_request")
    found: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        path = root / _SCOPE_DIR / _CATALOG_NAME
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if path.is_file():
            found.append(path)
    from zeus_dev_helper_mcp.beer import analytics_catalog_source

    packaged = analytics_catalog_source(cfg)
    if packaged is not None and packaged not in found:
        found.append(packaged)
    return found


def install_yelp_catalog(cfg: HelperConfig, root: Path) -> dict[str, Any]:
    """Copy the catalog into the scope directory load_for_turn checks first.

    The file is copied unchanged. A definition that mentions SCOPE BRIEF is not
    a ``## SCOPE BRIEF`` heading, and this copy does not add one.
    """
    bucket, scope = yelp_target(cfg)
    dirname = scope_catalog_dirname(bucket, scope)
    dest_dir = root / "data" / "chat_requests" / dirname
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / _CATALOG_NAME
    sources = _catalog_sources(cfg)
    if not sources:
        return {"ok": False, "copied": False, "path": str(dest)}
    src = sources[0]
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return {
        "ok": True,
        "copied": True,
        "path": str(dest),
        "source": str(src),
        "scope_dir": dirname,
    }


def _search_source(text: str) -> str:
    start = text.find("async def _run_search")
    if start < 0:
        return ""
    end = text.find("\nasync def ", start + 1)
    if end < 0:
        end = len(text)
    return text[start:end]


def yelp_bff_is_current(text: str) -> bool:
    """True when search is a catalog turn and does not scan biz: rows itself."""
    search = _search_source(text)
    return (
        "agent.run_turn" in search
        and "catalog.load_for_turn" in search
        and "collect_yelp_cards" in search
        and f"{_SCOPE_DIR}/{_CATALOG_NAME}" in text
        and "chat_request=" not in text
        and "pipeline_body" not in text
        and 'fetch("pipeline"' not in text
        and "fetch('pipeline'" not in text
        and ".find(" not in search
        and "biz:" not in search
        and 'entity_type": "User"' in text
        and "is_biz_user" in text
    )


def looks_like_yelp_app(root: Path) -> bool:
    return (
        (root / "main.py").is_file()
        and (root / "README.md").is_file()
        and (root / "requirements.txt").is_file()
        and (root / "static" / "index.html").is_file()
    )


def _nonempty(path: Path) -> bool:
    try:
        return path.exists() and any(path.iterdir())
    except OSError:
        return False


def _foreign_yelp_dir(path: Path) -> bool:
    return _nonempty(path) and not looks_like_yelp_app(path)


def _next_open_yelp_dir(parent: Path) -> Path | None:
    for n in range(2, 100):
        candidate = parent / f"{DEFAULT_YELP_DIR_NAME}-{n}"
        if not _foreign_yelp_dir(candidate):
            return candidate
    return None


def _embedded_source() -> str:
    chunks = [
        f"_VERB_NAMES = frozenset({set(_VERB_NAMES)!r})",
        f"_SIGNAL_KEYS = {_SIGNAL_KEYS!r}",
    ]
    for fn in (
        _parse_blob,
        _text,
        _meta,
        _biz_id,
        _has_business_signal,
        _display_name,
        _pick,
        card_from_row,
        is_biz_user,
        collect_yelp_cards,
    ):
        chunks.append(textwrap.dedent(inspect.getsource(fn)).rstrip())
    return "\n\n".join(chunks) + "\n"


_MAIN_PREFIX = '''\
"""Yelp-demo app. Search loads the analytics catalog through the client turn."""

from __future__ import annotations

import json
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from zeus_client import TurnStatus, ZeusRuntime, user_facing_answer
from zeus_client.adapters.catalog_fs.store import FsCatalogStore
from zeus_client.adapters.llm_openai_compatible import OpenAICompatibleLlmClient
from zeus_client.adapters.zeus_http import HttpxZeusPort
from zeus_client.adapters.zeus_http.catalog_remote import HttpxCatalogRemote
from zeus_client.domain.errors import ZeusClientError

_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")

PAGE_CAP = 24
PORT = int(os.environ.get("PORT") or "8110")
_runtime_obj: ZeusRuntime | None = None


def _overlay_client_env() -> None:
    pairs = (
        ("ZEUS_URL", "ZEUS_CLIENT_URL"),
        ("ZEUS_AUTH_MODE", "ZEUS_CLIENT_AUTH_MODE"),
        ("ZEUS_USERNAME", "ZEUS_CLIENT_USERNAME"),
        ("ZEUS_USER", "ZEUS_CLIENT_USERNAME"),
        ("ZEUS_BUCKET", "ZEUS_CLIENT_BUCKET"),
        ("ZEUS_SCOPE", "ZEUS_CLIENT_SCOPE"),
        ("ZEUS_COLLECTION", "ZEUS_CLIENT_COLLECTION"),
        ("ZEUS_MODE", "ZEUS_CLIENT_MODE"),
        ("LLM_BASE_URL", "ZEUS_CLIENT_LLM_BASE_URL"),
        ("LLM_MODEL", "ZEUS_CLIENT_LLM_MODEL"),
    )
    for src, dst in pairs:
        val = (os.environ.get(src) or "").strip()
        if val and not (os.environ.get(dst) or "").strip():
            os.environ[dst] = val
    chat = ""
    for key in (
        "ZEUS_CHAT_REQUESTS_DIR",
        "ZEUS_CLIENT_CHAT_REQUESTS_DIR",
        "ZEUS_CHAT_REQUEST_DIR",
    ):
        chat = (os.environ.get(key) or "").strip()
        if chat:
            break
    if not chat:
        chat = str(_ROOT / "data" / "chat_requests")
    os.environ["ZEUS_CLIENT_CHAT_REQUESTS_DIR"] = chat


def _build_runtime() -> ZeusRuntime:
    _overlay_client_env()
    rt = ZeusRuntime.from_config(_ROOT / "config.json", profile="development")
    secrets = rt.services.secrets
    rt.services.zeus = HttpxZeusPort(
        endpoint=rt.config.zeus, secrets=secrets, journal=rt.journal
    )
    rt.services.llm = OpenAICompatibleLlmClient(
        config=rt.config.llm, secrets=secrets, journal=rt.journal
    )
    chat_dir = rt.config.chat_requests_dir or str(_ROOT / "data" / "chat_requests")
    rt.services.catalog = FsCatalogStore(root=chat_dir)
    rt.services.catalog_remote = HttpxCatalogRemote(
        endpoint=rt.config.zeus, secrets=secrets
    )
    return rt


def _runtime() -> ZeusRuntime:
    global _runtime_obj
    if _runtime_obj is None:
        _runtime_obj = _build_runtime()
    return _runtime_obj


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    try:
        yield
    finally:
        global _runtime_obj
        rt = _runtime_obj
        _runtime_obj = None
        if rt is not None:
            await rt.aclose()


app = FastAPI(title="Yelp demo", version="0.1.0", lifespan=_lifespan)
_static = _ROOT / "static"
if _static.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static)), name="static")


def _pour_enabled() -> bool:
    for name in ("LLM_API_KEY", "XAI_API_KEY", "OPENAI_API_KEY"):
        if (os.environ.get(name) or "").strip():
            return True
    return False
'''

_MAIN_SUFFIX = r'''
def _turn_blobs(result: Any) -> list[Any]:
    debug = getattr(result, "debug", None)
    blobs: list[Any] = []
    hops = getattr(debug, "hops", None) or ()
    if isinstance(hops, (list, tuple)):
        blobs.extend(hops)
    trace = getattr(debug, "public_trace", None)
    if trace:
        blobs.append(trace)
    return blobs


def _req_ids(result: Any) -> list[str]:
    debug = getattr(result, "debug", None)
    raw = getattr(debug, "req_ids", None) or ()
    ids = [str(item) for item in raw if item]
    if ids:
        return ids
    for hop in getattr(debug, "hops", None) or ():
        if isinstance(hop, dict) and hop.get("req_id"):
            ids.append(str(hop["req_id"]))
    return ids


def _verb_result(result: Any) -> dict[str, Any]:
    body = result.body if isinstance(getattr(result, "body", None), dict) else {}
    inner = body.get("result") if isinstance(body.get("result"), dict) else {}
    return inner


def _verb_req_ids(result: Any) -> list[str]:
    found: list[str] = []
    for item in getattr(result, "req_ids", ()) or ():
        text = str(item or "").strip()
        if text and text not in found:
            found.append(text)
    one = str(getattr(result, "req_id", "") or "").strip()
    if one and one not in found:
        found.append(one)
    return found


_FIND_PAGES = 64


async def _find_users(offset: int) -> tuple[list[Any], list[str]]:
    """One find page of User rows. Callers keep the biz: rows."""
    rt = _runtime()
    try:
        found = await rt.data.find({
            "entity_type": "User",
            "limit": PAGE_CAP,
            "offset": max(0, int(offset)),
        })
    except ZeusClientError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": exc.public_message or str(exc)},
        ) from exc
    if not getattr(found, "ok", False):
        raise HTTPException(
            status_code=502,
            detail={
                "error": getattr(found, "error", None) or "find failed",
                "req_ids": _verb_req_ids(found),
            },
        )
    body = _verb_result(found)
    raw_items = body.get("items") if isinstance(body.get("items"), list) else []
    return raw_items, _verb_req_ids(found)


async def _page_businesses(query: str, *, limit: int, offset: int) -> dict[str, Any]:
    """Page find on User until this view has enough biz: cards. Not the search turn."""
    cap = max(1, min(int(limit or PAGE_CAP), PAGE_CAP))
    skip = max(0, int(offset or 0))
    start = skip
    needle = (query or "").strip().casefold()
    items: list[dict[str, Any]] = []
    req_ids: list[str] = []
    examined = 0
    exhausted = False
    for _ in range(_FIND_PAGES):
        if len(items) >= cap:
            break
        raw_items, page_ids = await _find_users(skip)
        for req_id in page_ids:
            if req_id not in req_ids:
                req_ids.append(req_id)
        short = len(raw_items) < PAGE_CAP
        filled = False
        consumed_all = True
        for row in raw_items:
            examined += 1
            skip += 1
            if not isinstance(row, dict) or not is_biz_user(row):
                continue
            card = card_from_row(row)
            if card is None:
                continue
            if needle and needle not in card["name"].casefold():
                continue
            items.append(card)
            if len(items) >= cap:
                filled = True
                consumed_all = False
                break
        if short and consumed_all:
            exhausted = True
        if filled or exhausted:
            break
    return {
        "ok": True,
        "items": items[:cap],
        "count": len(items[:cap]),
        "fetched": examined,
        "limit": cap,
        "offset": start,
        "next_offset": skip,
        "exhausted": exhausted,
        "path": ["find"],
        "req_ids": req_ids,
    }


async def _load_business(business_id: str) -> dict[str, Any]:
    """Business page: page find on User and keep the matching biz: row."""
    ident = (business_id or "").strip()
    if ident and not ident.startswith("biz:"):
        ident = "biz:" + ident
    req_ids: list[str] = []
    offset = 0
    for _ in range(_FIND_PAGES):
        page = await _page_businesses("", limit=PAGE_CAP, offset=offset)
        for req_id in page["req_ids"]:
            if req_id not in req_ids:
                req_ids.append(req_id)
        for card in page["items"]:
            if card.get("id") == ident:
                return {"ok": True, "business": card, "path": ["find"], "req_ids": req_ids}
        nxt = int(page.get("next_offset") or 0)
        if page.get("exhausted") or nxt <= offset:
            break
        offset = nxt
    raise HTTPException(status_code=404, detail={"error": "not found", "id": ident})


async def _run_search(query: str, *, limit: int) -> dict[str, Any]:
    """One search via rt.agent.run_turn.

    chat_request is omitted. AgentAPI.run_turn calls catalog.load_for_turn,
    which reads data/chat_requests/yelp-demo__default/chat_request_analytics_v2.json
    (the scope directory before the chat_requests root; no base_id, so the v2 name).
    The handler does not build a pipeline and does not paste a catalog into the call.
    An empty card list stays empty: the catalog entity can miss while User rows exist.
    """
    message = (query or "").strip()
    if not _pour_enabled():
        reason = "Search is off until LLM_API_KEY, XAI_API_KEY, or OPENAI_API_KEY is set in .env."
        return {
            "ok": False,
            "items": [],
            "count": 0,
            "pour_enabled": False,
            "answer": reason,
            "path": [],
            "req_ids": [],
        }
    if not message:
        return {
            "ok": True,
            "items": [],
            "count": 0,
            "answer": "",
            "path": ["run_turn", "catalog.load_for_turn"],
            "req_ids": [],
        }
    cap = max(1, min(int(limit or PAGE_CAP), PAGE_CAP))
    rt = _runtime()
    cfg = rt.config
    chat_id = "yelp_" + uuid.uuid4().hex[:12]
    try:
        result = await rt.agent.run_turn(
            message,
            target=cfg.target,
            settings=cfg.settings,
            chat_id=chat_id,
            model=cfg.llm.model,
            enable_sessions=bool(cfg.settings.durable_sessions),
        )
    except ZeusClientError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": exc.public_message or str(exc)},
        ) from exc
    answer = user_facing_answer(result.answer or "")
    err = result.error
    err_text = (getattr(err, "message", None) or "") if err is not None else ""
    if result.status == TurnStatus.ERROR:
        raise HTTPException(
            status_code=502,
            detail={"error": err_text or "agent turn failed", "req_ids": _req_ids(result)},
        )
    items = collect_yelp_cards(_turn_blobs(result), limit=cap)
    return {
        "ok": True,
        "items": items,
        "count": len(items),
        "pour_enabled": True,
        "answer": answer,
        "path": ["run_turn", "catalog.load_for_turn"],
        "req_ids": _req_ids(result),
        "status": result.status.value if hasattr(result.status, "value") else str(result.status),
    }


class SearchBody(BaseModel):
    query: str = ""
    limit: int = PAGE_CAP


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "sample": "demo_yelp"}


@app.get("/api/config")
async def api_config() -> dict[str, Any]:
    cfg = _runtime().config
    return {
        "zeus_url": cfg.zeus.url or "",
        "bucket": cfg.target.bucket,
        "scope": cfg.target.scope,
        "collection": cfg.target.collection,
        "mode": cfg.settings.mode,
        "llm_required": True,
        "pour_enabled": _pour_enabled(),
        "catalog": "data/chat_requests/yelp-demo__default/chat_request_analytics_v2.json",
    }


@app.post("/api/search")
async def api_search(body: SearchBody) -> dict[str, Any]:
    return await _run_search(body.query, limit=body.limit)


@app.get("/api/suggest")
async def api_suggest(
    q: str = Query("", max_length=200),
    limit: int = Query(8, ge=1, le=PAGE_CAP),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return await _page_businesses(q, limit=limit, offset=offset)


@app.get("/api/businesses")
async def api_businesses(
    limit: int = Query(PAGE_CAP, ge=1, le=PAGE_CAP),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return await _page_businesses("", limit=limit, offset=offset)


@app.get("/api/business/{business_id}")
async def api_business(business_id: str) -> dict[str, Any]:
    return await _load_business(business_id)


@app.get("/")
@app.get("/business/{business_id}")
async def index(business_id: str = "") -> FileResponse:
    index_path = _static / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=500, detail="static/index.html missing")
    return FileResponse(index_path)


def main() -> None:
    import uvicorn

    host = os.environ.get("HOST", "127.0.0.1")
    uvicorn.run("main:app", host=host, port=PORT, reload=False)


if __name__ == "__main__":
    main()
'''

_MAIN_PY = _MAIN_PREFIX + "\n" + _embedded_source() + "\n" + _MAIN_SUFFIX

_REQUIREMENTS = """\
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
kotenai-zeus-client>=2.4.0,<2.5
python-dotenv>=1.0.0
"""

_README = """\
# {project_name}

Yelp-demo app written by Developer Helper MCP `use_sample(sample=demo_yelp)`.

Bucket `yelp-demo`, scope `_default`. Zeus stays on public `:8080`.

## Search loads the chat request

`POST /api/search` calls `rt.agent.run_turn` and leaves `chat_request` unset.
`catalog.load_for_turn` then reads

`data/chat_requests/yelp-demo__default/chat_request_analytics_v2.json`

(the scope directory before the `chat_requests` root; no `base_id`, so the
filename is `chat_request_analytics_v2.json`). The handler does not build a
pipeline body and does not paste a catalog into the call.

The pack may mention Beer, and it may contain the words SCOPE BRIEF as a
definition. That is still this scope's analytics chat request. `extract_scope_brief`
only treats a `## SCOPE BRIEF` heading as a brief. This app does not skip the
turn because of either string.

An empty search stays empty. The catalog's entity can return no rows while
`User` nodes with a `biz:` doc key still exist. Search does not scan those rows.

Cards from the turn need a business signal: a `biz:` id, a city, a category, a
rating, a review count, or an address. A hop named `pipeline`, `find`, `search`,
or `describe` is not a business.

## Direct reads

Suggest (`GET /api/suggest`), the header count (`GET /api/businesses`), and the
business page (`GET /api/business/{{id}}`) page `find` on `User` and keep `biz:`
rows. Typeahead does not call the agent.

## Run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` when `.env` is missing. Set `LLM_API_KEY` there.
`config.json` `llm.api_key_env` stays the name `LLM_API_KEY`. Then:

```bash
uvicorn main:app --host 127.0.0.1 --port 8110
```

Search needs the key. The list, suggest, and business routes do not.
"""

_INDEX_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Yelp demo</title>
  <style>
    :root { color-scheme: light; }
    body { margin: 0; font: 16px/1.4 system-ui, sans-serif; background: #f6f4f1; color: #1c1917; }
    header, main { max-width: 880px; margin: 0 auto; padding: 1.25rem; }
    header { display: flex; justify-content: space-between; gap: 1rem; align-items: baseline; }
    h1 { font-size: 1.4rem; margin: 0; }
    #count { color: #57534e; }
    form { display: flex; gap: 0.5rem; margin: 0 0 0.75rem; }
    input[type="search"] { flex: 1; padding: 0.6rem 0.75rem; border: 1px solid #d6d3d1; border-radius: 8px; }
    button { padding: 0.6rem 0.9rem; border: 0; border-radius: 8px; background: #9f1239; color: white; }
    #suggest { display: flex; flex-wrap: wrap; gap: 0.4rem; min-height: 1.5rem; margin-bottom: 0.75rem; }
    #suggest button { background: white; color: #1c1917; border: 1px solid #d6d3d1; }
    #answer { color: #44403c; margin: 0 0 0.75rem; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 0.75rem; }
    article { background: white; border-radius: 10px; padding: 0.9rem; }
    article h2 { font-size: 1rem; margin: 0 0 0.25rem; }
    article p { margin: 0.15rem 0; color: #57534e; }
    article a { color: inherit; text-decoration: none; }
    #detail { margin-top: 1rem; }
    @media (max-width: 640px) {
      header { flex-direction: column; }
      form { flex-direction: column; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Neighborhood</h1>
    <p id="count">Loading businesses…</p>
  </header>
  <main>
    <form id="search-form">
      <input id="q" type="search" name="q" placeholder="Search businesses" autocomplete="off" />
      <button type="submit">Search</button>
    </form>
    <div id="suggest"></div>
    <p id="answer"></p>
    <div id="grid" class="grid"></div>
    <section id="detail"></section>
  </main>
  <script>
    const grid = document.getElementById("grid");
    const countEl = document.getElementById("count");
    const answerEl = document.getElementById("answer");
    const suggestEl = document.getElementById("suggest");
    const detailEl = document.getElementById("detail");
    const input = document.getElementById("q");

    function cardHtml(card) {
      const bits = [card.city, card.category, card.rating, card.review_count, card.address]
        .filter((part) => part !== undefined && part !== null && part !== "")
        .map((part) => String(part));
      const id = encodeURIComponent(card.id || "");
      return '<article><h2><a href="/business/' + id + '">' + card.name + '</a></h2><p>'
        + bits.join(" · ") + "</p></article>";
    }

    function render(items) {
      grid.innerHTML = (items || []).map(cardHtml).join("");
    }

    async function loadBusinesses() {
      const res = await fetch("/api/businesses?limit=24&offset=0");
      const data = await res.json();
      const n = Number(data.count || 0);
      countEl.textContent = n + " shown";
      render(data.items || []);
    }

    async function loadSuggest(q) {
      if (!q) { suggestEl.innerHTML = ""; return; }
      const res = await fetch("/api/suggest?q=" + encodeURIComponent(q) + "&limit=8");
      const data = await res.json();
      suggestEl.innerHTML = (data.items || []).map((card) =>
        '<button type="button" data-q="' + card.name + '">' + card.name + "</button>"
      ).join("");
    }

    async function runSearch(q) {
      answerEl.textContent = "Searching…";
      suggestEl.innerHTML = "";
      const res = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q })
      });
      const data = await res.json();
      answerEl.textContent = data.answer || data.error || "";
      render(data.items || []);
      countEl.textContent = (data.items || []).length + " from search";
    }

    async function loadBusiness(id) {
      const res = await fetch("/api/business/" + encodeURIComponent(id));
      if (!res.ok) { detailEl.textContent = "Business not found."; return; }
      const data = await res.json();
      const card = data.business || {};
      detailEl.innerHTML = "<h2>" + (card.name || "") + "</h2><p>"
        + [card.address, card.city, card.review_count].filter(Boolean).join(" · ") + "</p>";
    }

    document.getElementById("search-form").addEventListener("submit", (event) => {
      event.preventDefault();
      runSearch(input.value.trim());
    });
    let suggestTimer = 0;
    input.addEventListener("input", () => {
      window.clearTimeout(suggestTimer);
      const q = input.value.trim();
      suggestTimer = window.setTimeout(() => { loadSuggest(q); }, 250);
    });
    suggestEl.addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (!button) return;
      input.value = button.dataset.q || "";
      runSearch(input.value);
    });

    const businessPath = location.pathname.startsWith("/business/")
      ? decodeURIComponent(location.pathname.slice("/business/".length))
      : "";
    if (businessPath) loadBusiness(businessPath);
    loadBusinesses();
  </script>
</body>
</html>
"""


def write_yelp_env_example(cfg: HelperConfig, root: Path) -> Path:
    bucket, scope = yelp_target(cfg)
    path = root / ".env.example"
    path.write_text(
        "\n".join(
            [
                "# Copy to .env (never commit .env). Search needs an LLM key.",
                f"ZEUS_URL={cfg.zeus_url or 'http://localhost:8080'}",
                f"ZEUS_BUCKET={bucket}",
                f"ZEUS_SCOPE={scope}",
                "ZEUS_COLLECTION=_default",
                "ZEUS_MODE=analytics",
                f"PORT={YELP_PORT}",
                "LLM_BASE_URL=https://api.x.ai/v1",
                "LLM_API_KEY=",
                "LLM_MODEL=grok-4-1-fast-non-reasoning",
                "# ZEUS_USERNAME=",
                "# ZEUS_PASSWORD=",
                "# ZEUS_BEARER_TOKEN=",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def write_yelp_config(cfg: HelperConfig, root: Path) -> Path:
    """Runtime pin. No base_id, so the catalog filename stays chat_request_analytics_v2.json."""
    root.mkdir(parents=True, exist_ok=True)
    bucket, scope = yelp_target(cfg)
    auth = (cfg.zeus_auth_mode or "none").strip().lower() or "none"
    if auth not in {"none", "basic", "bearer", "session", "certificate"}:
        auth = "none"
    zeus: dict[str, Any] = {
        "url": (cfg.zeus_url or "http://localhost:8080").rstrip("/"),
        "auth_mode": auth,
        "timeout_s": 30,
    }
    user = (os.environ.get("ZEUS_USERNAME") or os.environ.get("ZEUS_USER") or "").strip()
    if user:
        zeus["username"] = user
    if auth == "basic":
        zeus["password_env"] = "ZEUS_PASSWORD"
    elif auth == "bearer":
        zeus["token_env"] = "ZEUS_BEARER_TOKEN"
    elif auth == "session":
        zeus["token_env"] = "ZEUS_SESSION_ID"
    chat_dir = root / "data" / "chat_requests"
    payload = {
        "profile": "development",
        "client_floor": "client-floor-6.1",
        "chat_requests_dir": str(chat_dir),
        "zeus": zeus,
        "target": {
            "bucket": bucket,
            "scope": scope,
            "collection": cfg.default_collection or "_default",
        },
        "llm": {
            "provider": "xai",
            "base_url": (os.environ.get("LLM_BASE_URL") or "https://api.x.ai/v1").rstrip("/"),
            "model": os.environ.get("LLM_MODEL") or "grok-4-1-fast-non-reasoning",
            "api_key_env": "LLM_API_KEY",
            "timeout_s": 120,
        },
        "settings": {
            "mode": "analytics",
            "durable_sessions": False,
            "ai_process_result": False,
            "max_rounds": 8,
            "ignore_user_tool_path_hints": True,
        },
        "session": {"semantic_cache": {"enabled": False}},
    }
    path = root / "config.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _write_tree(cfg: HelperConfig, root: Path, name: str) -> list[str]:
    files = {
        "main.py": _MAIN_PY,
        "requirements.txt": _REQUIREMENTS,
        "README.md": _README.format(project_name=name),
    }
    written: list[str] = []
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        written.append(str(path))
    static = root / "static"
    static.mkdir(parents=True, exist_ok=True)
    page = static / "index.html"
    page.write_text(_INDEX_HTML, encoding="utf-8")
    written.append(str(page))
    written.append(str(write_yelp_env_example(cfg, root)))
    catalog = install_yelp_catalog(cfg, root)
    written.append(str(catalog.get("path")))
    written.append(str(write_yelp_config(cfg, root)))
    return written


def _attach(cfg: HelperConfig, root: Path, result: dict[str, Any]) -> dict[str, Any]:
    from zeus_dev_helper_mcp.app_env import annotate_app_env, annotate_pour
    from zeus_dev_helper_mcp.llm_key import inspect_app_llm_key

    result = annotate_app_env(cfg, root, result)
    report = inspect_app_llm_key(root)
    result["llm_key"] = report
    result["llm_required"] = True
    if report.get("applies") and not report.get("ok") and report.get("message"):
        rest = str(result.get("next_action") or "").strip()
        message = str(report["message"])
        result["next_action"] = f"{message} {rest}".strip() if rest else message
    return annotate_pour(result, catalog_ui=True)


def _layout(root: Path) -> dict[str, Any]:
    main = root / "main.py"
    current = False
    if main.is_file():
        try:
            current = yelp_bff_is_current(main.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            current = False
    return {
        "ok": current and (root / "README.md").is_file(),
        "current": current,
        "readme": (root / "README.md").is_file(),
        "frontend_package": False,
        "pyproject": (root / "pyproject.toml").is_file(),
    }


_DO_NOT = [
    "Do not scaffold_app",
    "Do not copy demo_beer_sample",
    "Do not clone demo_travel_sample",
    "Do not scan User biz: rows in POST /api/search",
    "Do not build a pipeline body or pass chat_request into run_turn",
    "Do not skip the turn because the pack mentions Beer or the words SCOPE BRIEF",
]


def _next_action(root: Path) -> str:
    return (
        f"Yelp-demo app at {root}. "
        "POST /api/search calls rt.agent.run_turn and omits chat_request so "
        "catalog.load_for_turn reads "
        f"data/chat_requests/{_SCOPE_DIR}/{_CATALOG_NAME}. "
        "Suggest, the header count, and the business page page find on User "
        "and keep biz: rows. "
        "Put LLM_API_KEY in .env. config.json llm.api_key_env stays LLM_API_KEY. "
        "Run verify_local_setup, then uvicorn main:app --port "
        f"{YELP_PORT}. "
        f"{ENV_YELP_DIR}={root}."
    )


def write_yelp_sample(
    cfg: HelperConfig,
    target_dir: str | Path,
    *,
    project_name: str = DEFAULT_YELP_DIR_NAME,
    force: bool = False,
) -> dict[str, Any]:
    """Write the yelp-demo app. Search is the catalog turn."""
    from zeus_dev_helper_mcp.app_env import basic_login_blocked
    from zeus_dev_helper_mcp.checklist import set_item_status

    root = Path(target_dir).expanduser().resolve()
    blocked = basic_login_blocked(cfg)
    if blocked is not None:
        blocked["local_dir"] = str(root)
        blocked["do_not"] = list(_DO_NOT)
        return blocked

    name = sanitize_yelp_dir_name(project_name) if project_name else root.name
    upgrading = False
    if root.exists() and _nonempty(root) and not force:
        if looks_like_yelp_app(root):
            try:
                main_text = (root / "main.py").read_text(encoding="utf-8", errors="replace")
            except OSError:
                main_text = ""
            if yelp_bff_is_current(main_text):
                env_path = set_demo_yelp_sample_dir_env(root)
                save_yelp_sample_dir(cfg, root)
                return _attach(
                    cfg,
                    root,
                    {
                        "ok": True,
                        "written": False,
                        "cloned": False,
                        "local_dir": str(root),
                        "project_name": root.name,
                        "layout": _layout(root),
                        "env": {ENV_YELP_DIR: env_path},
                        "do_not": list(_DO_NOT),
                        "next_action": _next_action(root),
                    },
                )
            upgrading = True
        else:
            return {
                "ok": False,
                "written": False,
                "cloned": False,
                "failure_class": "foreign_sample_dir",
                "error": f"target_dir not empty and does not look like the yelp-demo app: {root}",
                "local_dir": str(root),
                "do_not": list(_DO_NOT),
                "next_action": (
                    f"{root} is not the yelp-demo app and was not written. "
                    "Pick an empty directory or another project_name. "
                    "Do not replace it with a local scan of User biz: rows."
                ),
            }

    root.mkdir(parents=True, exist_ok=True)
    written = _write_tree(cfg, root, name)
    meta = {
        "sample": "demo_yelp",
        "app_kind": "ui",
        "llm_required": True,
        "bucket": yelp_target(cfg)[0],
        "scope": yelp_target(cfg)[1],
        "catalog": f"data/chat_requests/{scope_catalog_dirname(*yelp_target(cfg))}/{_CATALOG_NAME}",
        "bff": "POST /api/search calls rt.agent.run_turn and omits chat_request",
        "client_floor": "client-floor-6.1",
    }
    meta_path = root / "sample_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    written.append(str(meta_path))
    env_path = set_demo_yelp_sample_dir_env(root)
    save_yelp_sample_dir(cfg, root)
    try:
        set_item_status(cfg, "0.2", "done", evidence=f"yelp_layout={root}")
        set_item_status(cfg, "3.1", "done", evidence=f"yelp_dir={root}")
    except Exception:  # noqa: BLE001, S110
        pass
    return _attach(
        cfg,
        root,
        {
            "ok": True,
            "written": True,
            "upgraded": upgrading,
            "cloned": False,
            "local_dir": str(root),
            "target_dir": str(root),
            "project_name": name,
            "files": written,
            "layout": _layout(root),
            "env": {ENV_YELP_DIR: env_path},
            "do_not": list(_DO_NOT),
            "run": (
                f"cd {root} && python3 -m venv .venv && source .venv/bin/activate && "
                "pip install -r requirements.txt && cp -n .env.example .env && "
                f"uvicorn main:app --host 127.0.0.1 --port {YELP_PORT}"
            ),
            "next_action": _next_action(root),
            "docs": {"using": docs_url("zeus-client/using-zeus-client.md")},
        },
    )


def ensure_yelp_app(
    cfg: HelperConfig,
    *,
    sample_dir: str = "",
    project_name: str = "",
    parent_dir: str = "",
    clone_if_missing: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """Write the yelp-demo app and set DEMO_YELP_SAMPLE_DIR.

    A foreign directory (including a demo_yelp git checkout) is left in place.
    The default name then moves to the next open sibling.
    """
    del clone_if_missing
    dir_name = sanitize_yelp_dir_name(project_name)
    dest = _resolve_clone_dest(
        sample_dir=sample_dir,
        project_name=project_name,
        parent_dir=parent_dir,
    )
    explicit = bool(sample_dir.strip()) or (
        bool(project_name.strip()) and sanitize_yelp_dir_name(project_name) != DEFAULT_YELP_DIR_NAME
    )
    relocated_from = ""
    if (
        not explicit
        and not force
        and _foreign_yelp_dir(dest)
        and dest.name == DEFAULT_YELP_DIR_NAME
    ):
        sibling = _next_open_yelp_dir(dest.parent)
        if sibling is None:
            return {
                "ok": False,
                "cloned": False,
                "local_dir": str(dest),
                "project_name": dir_name,
                "failure_class": "foreign_sample_dir",
                "do_not": list(_DO_NOT),
                "next_action": (
                    f"{dest} is not the yelp-demo app and was not written. "
                    "Pass project_name for an empty directory."
                ),
            }
        relocated_from = str(dest)
        dest = sibling
        dir_name = dest.name
    result = write_yelp_sample(cfg, dest, project_name=dir_name, force=force)
    if relocated_from and result.get("ok"):
        result["relocated_from"] = relocated_from
        prior = str(result.get("next_action") or "").strip()
        result["next_action"] = (
            f"Left {relocated_from} unchanged and wrote the yelp-demo app at {dest}. " + prior
        ).strip()
    return result
