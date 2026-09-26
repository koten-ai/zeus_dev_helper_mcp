"""Beer-sample catalog UI template.

Same-origin FastAPI BFF + static page. Search follows demo_travel_sample:
``rt.agent.run_turn`` with ``chat_request`` omitted so the client calls
``catalog.load_for_turn`` and merges the live SCOPE BRIEF + MINI-SCHEMA
into the model request. The BFF does not build a pipeline body.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from zeus_dev_helper_mcp.checklist import set_item_status
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.docs_links import docs_url

DEFAULT_BEER_DIR_NAME = "demo_beer_sample"
ENV_BEER_DIR = "DEMO_BEER_SAMPLE_DIR"
_DIR_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

BEER_ALIASES = frozenset(
    {
        "beer",
        "beer-sample",
        "beer_sample",
        "beersample",
        "demo_beer",
        "demo_beer_sample",
        "direct",
        "ui-direct",
        "ui_direct",
        "direct-ui",
        "direct_ui",
        "catalog-ui",
        "catalog_ui",
    }
)

BEER_BUCKET_HINTS = frozenset({"beer-sample", "beer_sample", "beersample", "beer"})

_CARD_DISPLAY_KEYS = ("style", "category", "abv", "ibu", "srm", "brewery", "description")
_CARD_SKIP_KEYS = frozenset(
    {
        "job_fingerprint",
        "meta",
        "decomposition",
        "query_decomposition",
        "provenance",
        "entity_refs",
        "node_refs",
        "step_costs",
        "wish_i_knew",
    }
)
_CARD_LIST_KEYS = (
    "rows",
    "items",
    "results",
    "entities",
    "matches",
    "nodes",
    "data",
    "result",
    "body",
    "result_json",
    "snippet",
)
_CARD_FILTER_KEYS = frozenset(
    {
        "where",
        "predicates",
        "limit",
        "offset",
        "return",
        "entity_type",
        "query",
        "query_text",
    }
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


def _card_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Beer card from a find/get row. A where-bag is not a product row."""
    body = row.get("body")
    merged = dict(row)
    if isinstance(body, dict):
        merged = dict(body)
        for key in ("id", "node_id", "doc_key"):
            if row.get(key) and not merged.get(key):
                merged[key] = row[key]
    name = merged.get("name") or merged.get("title")
    if not isinstance(name, str) or not name.strip():
        return None
    if set(merged) <= _CARD_FILTER_KEYS:
        return None
    if not any(k in merged and merged.get(k) not in (None, "") for k in _CARD_DISPLAY_KEYS):
        return None
    description = merged.get("description") or merged.get("snippet") or ""
    if not isinstance(description, str):
        description = ""
    return {
        "id": str(merged.get("id") or merged.get("node_id") or ""),
        "name": name.strip(),
        "style": merged.get("style") or "",
        "category": merged.get("category") or "",
        "abv": merged.get("abv"),
        "ibu": merged.get("ibu"),
        "brewery": merged.get("brewery") or "",
        "description": description,
    }


def _card_score(card: dict[str, Any]) -> int:
    return sum(
        1
        for key in ("style", "category", "abv", "ibu", "brewery", "description")
        if card.get(key) not in (None, "")
    )


def _matching_card_index(found: list[dict[str, Any]], card: dict[str, Any]) -> int | None:
    name = card["name"].casefold()
    for index, prev in enumerate(found):
        if card["id"] and prev["id"] and card["id"] == prev["id"]:
            return index
        if prev["name"].casefold() == name:
            return index
    return None


def collect_beer_cards(blobs: list[Any], *, limit: int = 50) -> list[dict[str, Any]]:
    """Pull beer cards out of agent-turn hops / public_trace payloads."""
    found: list[dict[str, Any]] = []

    def walk(payload: Any, depth: int = 0) -> None:
        if depth > 8:
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
        card = _card_from_row(payload)
        if card is not None:
            score = _card_score(card)
            prev_at = _matching_card_index(found, card)
            if prev_at is None:
                found.append(card)
            elif score > _card_score(found[prev_at]):
                found[prev_at] = card
        for key, val in payload.items():
            if key in _CARD_SKIP_KEYS:
                continue
            if (
                key in _CARD_LIST_KEYS
                or isinstance(val, (dict, list))
                or (isinstance(val, str) and val.lstrip()[:1] in "{[")
            ):
                walk(val, depth + 1)

    for blob in blobs:
        walk(blob)
        if len(found) >= limit:
            break
    return found[: max(0, limit)]


def _pretty_label(value: Any) -> str:
    """Turn a doc-key token (``central_waters_brewing_company``) into words."""
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if text and " " not in text and "_" in text:
        return text.replace("_", " ")
    return text


def _catalog_card(item: dict[str, Any]) -> dict[str, Any] | None:
    """Card from one Direct get/find item. Metadata and snippet fill the fields."""
    if not isinstance(item, dict):
        return None
    meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    snippet = _parse_blob(item.get("snippet"))
    extra = snippet if isinstance(snippet, dict) else {}

    def pick(*keys: str) -> Any:
        for source in (item, meta, extra):
            for key in keys:
                val = source.get(key)
                if val not in (None, ""):
                    return val
        return None

    name = pick("name", "title")
    if not isinstance(name, str) or not name.strip():
        return None
    description = pick("description") or ""
    if not isinstance(description, str):
        description = ""
    brewery = pick("brewery") or _pretty_label(str(pick("brewery_id") or ""))
    return {
        "id": str(pick("id", "node_id") or ""),
        "name": name.strip(),
        "style": pick("style") or "",
        "category": pick("category") or "",
        "abv": pick("abv"),
        "ibu": pick("ibu"),
        "brewery": brewery or "",
        "description": description,
        "city": pick("city") or "",
        "state": pick("state") or "",
        "country": pick("country") or "",
    }


def is_beer_sample(name: str) -> bool:
    return (name or "").lower().strip() in BEER_ALIASES


def prereqs_prefer_beer_direct(prereqs: dict[str, Any] | None) -> bool:
    """True when stored prereqs say beer bucket/sample and LLM is not required."""
    p = prereqs or {}
    bucket = str(p.get("bucket") or "").lower().strip()
    sample = str(p.get("sample") or "").lower().strip()
    has_llm = p.get("has_llm_key")
    if has_llm is True:
        return False
    return is_beer_sample(sample) or bucket in BEER_BUCKET_HINTS


BEER_MARKERS = (
    "README.md",
    "main.py",
    "requirements.txt",
    ".env.example",
    "static/index.html",
)

SAMPLE_BEER = {
    "name": "demo_beer_sample",
    "note": (
        "beer-sample catalog UI. use_sample(sample=beer) writes a FastAPI BFF "
        "+ static page. Search is rt.agent.run_turn with chat_request omitted "
        "(catalog.load_for_turn merges SCOPE BRIEF + MINI-SCHEMA)."
    ),
    "related": [
        docs_url("zeus-client/using-zeus-client.md"),
        "https://github.com/koten-ai/zeus_dev_helper_mcp",
    ],
}

_MAIN_PREFIX = r"""
#!/usr/bin/env python3
'''Beer-sample catalog UI — FastAPI BFF.

Search follows demo_travel_sample: call rt.agent.run_turn and omit
chat_request so AgentAPI.run_turn calls catalog.load_for_turn
(SCOPE BRIEF + MINI-SCHEMA merge). Do not pass a frozen catalog body.
This BFF does not build a pipeline request.
Scaffolded by zeus_dev_helper_mcp use_sample(sample=beer).
'''
from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from zeus_client import TurnStatus, ZeusRuntime, user_facing_answer
from zeus_client.adapters.catalog_fs.store import FsCatalogStore
from zeus_client.adapters.llm_openai_compatible import OpenAICompatibleLlmClient
from zeus_client.adapters.zeus_http import HttpxZeusPort
from zeus_client.adapters.zeus_http.catalog_remote import HttpxCatalogRemote
from zeus_client.domain.errors import ZeusClientError

_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")

PAGE_CAP = 50
PORT = int(os.environ.get("PORT") or "8090")

_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_runtime_obj: ZeusRuntime | None = None


def _overlay_client_env() -> None:
    '''Map beer .env names onto the client loader's ZEUS_CLIENT_* keys.'''
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
    '''Wire Zeus, LLM, catalog store, and catalog remote the way travel does.'''
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


app = FastAPI(title="Beer catalog UI", version="0.1.0", lifespan=_lifespan)
_static = _ROOT / "static"
if _static.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static)), name="static")


def _cache_ttl() -> float:
    raw = (os.environ.get("CELLAR_CACHE_TTL") or "600").strip()
    try:
        return float(raw)
    except ValueError:
        return 600.0


def _force_closed(text: str) -> bool:
    return "session_force_closed" in (text or "").lower()
"""

_MAIN_SUFFIX = r"""
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


def _hop_path(result: Any) -> list[str]:
    path = ["run_turn", "catalog.load_for_turn"]
    debug = getattr(result, "debug", None)
    for hop in getattr(debug, "hops", None) or ():
        if isinstance(hop, dict) and hop.get("name"):
            path.append(str(hop["name"]))
    return path


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


def _exact_total(result: dict[str, Any]) -> int | None:
    '''Live count only. An approximate entity total is not a page count.'''
    if result.get("approximate") is True:
        return None
    raw = result.get("total_count")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return max(0, int(raw))


async def _run_list(entity: str, *, limit: int, offset: int) -> dict[str, Any]:
    '''One catalog page via Direct find, then get.

    find is ordered by id and honors offset, so page 2 is the next rows
    rather than another model sample of the same list.
    '''
    cap = max(1, min(int(limit or 24), PAGE_CAP))
    skip = max(0, int(offset or 0))
    ttl = _cache_ttl()
    key = json.dumps({"list": entity, "limit": cap, "offset": skip}, sort_keys=True)
    now = time.time()
    if ttl > 0:
        hit = _cache.get(key)
        if hit is not None and now - hit[0] <= ttl:
            return hit[1]
        if hit is not None:
            _cache.pop(key, None)

    rt = _runtime()
    try:
        counted = await rt.data.find({
            "entity_type": entity,
            "return": "count",
            "exact": True,
        })
        found = await rt.data.find({
            "entity_type": entity,
            "return": "rows",
            "limit": cap,
            "offset": skip,
            "order_by": "id",
            "asc": True,
        })
    except ZeusClientError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": exc.public_message or str(exc)},
        ) from exc
    if not getattr(found, "ok", False):
        raise HTTPException(
            status_code=502,
            detail={"error": getattr(found, "error", None) or "find failed", "req_ids": _verb_req_ids(found)},
        )

    found_body = _verb_result(found)
    total = _exact_total(_verb_result(counted)) if getattr(counted, "ok", False) else None
    raw_items = found_body.get("items") if isinstance(found_body.get("items"), list) else []
    ids: list[str] = []
    thin: list[dict[str, Any]] = []
    for row in raw_items:
        if not isinstance(row, dict):
            continue
        ident = str(row.get("id") or "")
        if ident.startswith("n_") and ident not in ids:
            ids.append(ident)
        card = _catalog_card(row)
        if card is not None:
            thin.append(card)

    items: list[dict[str, Any]] = []
    got_ok = False
    if ids:
        try:
            got = await rt.data.get({"ids": ids[:PAGE_CAP], "include": ["body"]})
        except ZeusClientError:
            got = None
        if got is not None and getattr(got, "ok", False):
            got_ok = True
            by_id = {
                str(row.get("id")): row
                for row in (_verb_result(got).get("items") or [])
                if isinstance(row, dict) and row.get("id")
            }
            for ident in ids:
                row = by_id.get(ident)
                card = _catalog_card(row) if isinstance(row, dict) else None
                if card is not None:
                    items.append(card)
    if not items:
        items = thin

    returned = len(items)
    if total is None:
        truncated = bool(found_body.get("truncated")) or returned >= cap
    else:
        truncated = skip + returned < total
    if returned == 0:
        truncated = False
    pages = (max(1, (total + cap - 1) // cap) if total else (1 if returned == 0 else None))
    start = skip + 1 if returned else 0
    end = skip + returned
    noun = "breweries" if entity == "Brewery" else "beers"
    if returned:
        lede = "Showing " + noun + " " + str(start) + "–" + str(end)
        if total is not None:
            lede += " of " + str(total)
        lede += "."
    else:
        lede = "No " + noun + " on this page."
    req_ids = _verb_req_ids(found)
    if got_ok:
        req_ids.extend(item for item in _verb_req_ids(got) if item not in req_ids)
    payload = {
        "ok": True,
        "paged": True,
        "items": items,
        "cards": items,
        "limit": cap,
        "offset": skip,
        "total": total,
        "pages": pages,
        "truncated": truncated,
        "entity": entity,
        "lede": lede,
        "answer": lede,
        "path": ["find", "get"] if got_ok else ["find"],
        "req_ids": req_ids,
    }
    if ttl > 0:
        _cache[key] = (now, payload)
    return payload


def _hops_force_closed(result: Any) -> bool:
    '''True when a hop was refused for the shared session round cap.'''
    debug = getattr(result, "debug", None)
    for hop in getattr(debug, "hops", None) or ():
        if not isinstance(hop, dict):
            continue
        if _force_closed(str(hop.get("error") or "")):
            return True
        if _force_closed(str(hop.get("result_json") or "")):
            return True
    return False


async def _run_search(query: str, *, limit: int) -> dict[str, Any]:
    '''One catalog search via rt.agent.run_turn.

    chat_request is omitted on purpose. AgentAPI.run_turn then calls
    catalog.load_for_turn, which loads the analytics catalog and merges the
    live SCOPE BRIEF + MINI-SCHEMA into the system message sent to the model.
    '''
    message = (query or "").strip()
    if not message:
        return {
            "ok": True,
            "items": [],
            "cards": [],
            "lede": "",
            "answer": "",
            "path": [],
            "req_ids": [],
        }
    cap = max(1, min(int(limit or PAGE_CAP), PAGE_CAP))
    ttl = _cache_ttl()
    key = json.dumps({"q": message, "limit": cap}, sort_keys=True)
    now = time.time()
    if ttl > 0:
        hit = _cache.get(key)
        if hit is not None and now - hit[0] <= ttl:
            return hit[1]
        if hit is not None:
            _cache.pop(key, None)

    rt = _runtime()
    cfg = rt.config
    chat_id = "beer_" + uuid.uuid4().hex[:12]
    # Omit chat_request so 2.4 AgentAPI.run_turn calls catalog.load_for_turn
    # (SCOPE BRIEF + MINI-SCHEMA merge). Do not pass a frozen body here.
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
            detail={
                "error": err_text or "agent turn failed",
                "req_ids": _req_ids(result),
            },
        )

    items = collect_beer_cards(_turn_blobs(result), limit=cap)
    if not items and (
        _force_closed(answer) or _force_closed(err_text) or _hops_force_closed(result)
    ):
        raise HTTPException(
            status_code=503,
            detail={"error": "session_force_closed", "req_ids": _req_ids(result)},
        )
    payload = {
        "ok": True,
        "items": items,
        "cards": items,
        "lede": answer,
        "answer": answer,
        "path": _hop_path(result),
        "req_ids": _req_ids(result),
        "status": result.status.value if hasattr(result.status, "value") else str(result.status),
    }
    if ttl > 0:
        _cache[key] = (now, payload)
    return payload


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


def _zeus_version(url: str) -> str:
    '''Public Zeus /version. Empty when the endpoint does not answer.'''
    if not url:
        return ""
    try:
        import httpx

        resp = httpx.get(url.rstrip("/") + "/version", timeout=2.0)
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("version") or "").strip()


@app.get("/api/config")
async def api_config() -> dict[str, Any]:
    cfg = _runtime().config
    url = cfg.zeus.url or ""
    return {
        "zeus_url": url,
        "zeus_version": _zeus_version(url),
        "bucket": cfg.target.bucket,
        "scope": cfg.target.scope,
        "collection": cfg.target.collection,
        "mode": cfg.settings.mode,
        "llm_required": True,
        "page_cap": PAGE_CAP,
        "chips": [
            "Fruit Beer",
            "Pumpkin Beer",
            "Belgian and French Ale",
            "ipa",
            "porter",
            "Duvel",
        ],
    }


@app.get("/api/search")
async def api_search(
    q: str = Query("", max_length=500),
    limit: int = Query(PAGE_CAP, ge=1, le=PAGE_CAP),
    entity: str = Query(""),
) -> dict[str, Any]:
    '''Catalog search. Raw question goes to run_turn; the catalog supplies MINI-SCHEMA.'''
    message = (q or "").strip()
    kind = (entity or "").strip()
    if message and kind and kind.lower() not in {"beer", "beers"}:
        message = message + "\nEntity type: " + kind
    return await _run_search(message, limit=limit)


@app.get("/api/beers")
async def api_beers(
    limit: int = Query(24, ge=1, le=PAGE_CAP),
    offset: int = Query(0, ge=0, le=100000),
) -> dict[str, Any]:
    return await _run_list("Beer", limit=limit, offset=offset)


@app.get("/api/breweries")
async def api_breweries(
    limit: int = Query(24, ge=1, le=PAGE_CAP),
    offset: int = Query(0, ge=0, le=100000),
) -> dict[str, Any]:
    return await _run_list("Brewery", limit=limit, offset=offset)


@app.get("/api/beer/{item_id}")
async def api_beer(item_id: str) -> dict[str, Any]:
    out = await _run_search("Get the beer with id " + item_id, limit=1)
    if not out.get("items"):
        raise HTTPException(status_code=404, detail="not found")
    out["item"] = out["items"][0]
    return out


@app.get("/api/brewery/{item_id}")
async def api_brewery(item_id: str) -> dict[str, Any]:
    out = await _run_search("Get the brewery with id " + item_id, limit=1)
    if not out.get("items"):
        raise HTTPException(status_code=404, detail="not found")
    out["item"] = out["items"][0]
    return out


@app.get("/")
@app.get("/search")
async def index() -> FileResponse:
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
"""

def _embedded_card_source() -> str:
    """Stdlib card helpers pasted into the generated BFF."""
    import inspect
    import textwrap

    chunks = [
        f"_CARD_DISPLAY_KEYS = {_CARD_DISPLAY_KEYS!r}",
        f"_CARD_SKIP_KEYS = frozenset({set(_CARD_SKIP_KEYS)!r})",
        f"_CARD_LIST_KEYS = {_CARD_LIST_KEYS!r}",
        f"_CARD_FILTER_KEYS = frozenset({set(_CARD_FILTER_KEYS)!r})",
    ]
    for fn in (
        _parse_blob,
        _card_from_row,
        _card_score,
        _matching_card_index,
        collect_beer_cards,
        _pretty_label,
        _catalog_card,
    ):
        chunks.append(textwrap.dedent(inspect.getsource(fn)).rstrip())
    return "\n\n".join(chunks) + "\n"


_MAIN_PY = _MAIN_PREFIX + "\n" + _embedded_card_source() + "\n" + _MAIN_SUFFIX

_INDEX_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>The Sample Tap — beer-sample Direct</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='16' fill='%23e7c48a'/%3E%3Cpath d='M11 9h8v9.2a4 4 0 0 1-8 0V9z' fill='%23f7f1e6'/%3E%3Cpath d='M19 12.2h2.4a1.7 1.7 0 0 1 0 3.4H19' fill='none' stroke='%23f7f1e6' stroke-width='1.4'/%3E%3C/svg%3E" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Outfit:wght@400;500;600&display=swap" rel="stylesheet" />
  <style>
    :root {
      --bg: #14110e;
      --ink: #f6f1ea;
      --muted: #b7a898;
      --gold: #e0a45a;
      --cream: #f4efe6;
      --card: #241c17;
      --line: #3a3028;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--ink);
      font-family: Outfit, "Segoe UI", system-ui, sans-serif;
    }
    button, input { font-family: inherit; }
    .topbar {
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      align-items: center;
      gap: 1rem;
      padding: 0.85rem 1.6rem;
      background: #16130f;
      border-bottom: 1px solid #2a231c;
    }
    .brand { display: flex; align-items: center; gap: 0.75rem; min-width: 0; }
    .logo {
      width: 2.5rem; height: 2.5rem; flex: none; border-radius: 999px;
      display: grid; place-items: center;
    }
    .logo svg { width: 2.5rem; height: 2.5rem; display: block; }
    h1 {
      margin: 0;
      font-family: Fraunces, Georgia, "Times New Roman", serif;
      font-size: 1.35rem;
      font-weight: 560;
      letter-spacing: -0.02em;
    }
    .brand-sub {
      margin: 0.1rem 0 0;
      color: #a89888;
      font-size: 0.68rem;
      letter-spacing: 0.08em;
    }
    .modes {
      display: flex;
      gap: 0.15rem;
      padding: 0.22rem;
      background: #2a241e;
      border-radius: 999px;
    }
    .mode {
      border: none;
      background: transparent;
      color: #eadfd4;
      border-radius: 999px;
      padding: 0.42rem 0.95rem;
      cursor: pointer;
      font-weight: 500;
    }
    .mode.on { background: var(--cream); color: #1a140f; }
    .endpoint { justify-self: end; text-align: right; line-height: 1.25; }
    .endpoint .host { font-size: 0.82rem; color: #e6d9cc; }
    .endpoint .scope { font-size: 0.72rem; color: #8f8174; }
    .hero {
      position: relative;
      min-height: 440px;
      display: flex;
      align-items: center;
      background:
        linear-gradient(90deg, rgba(14,10,8,0.82) 0%, rgba(14,10,8,0.55) 34%, rgba(14,10,8,0.12) 58%, rgba(14,10,8,0.38) 100%),
        url("/static/hero.jpg") center 42% / cover no-repeat,
        #120e0b;
    }
    .hero-copy { position: relative; z-index: 1; width: min(40rem, 100%); padding: 2.6rem 1.8rem 2.2rem; }
    .kicker {
      margin: 0 0 0.45rem;
      color: #d7b07a;
      font-size: 0.72rem;
      letter-spacing: 0.14em;
    }
    .display {
      margin: 0;
      font-family: Fraunces, Georgia, "Times New Roman", serif;
      font-weight: 500;
      font-size: clamp(3.1rem, 6vw, 5.1rem);
      letter-spacing: -0.03em;
      line-height: 0.95;
      color: #f7f2ea;
    }
    .deck { margin: 0.9rem 0 0; max-width: 34rem; font-size: 1.05rem; line-height: 1.45; color: #f3eadf; }
    .deck .em { color: var(--gold); }
    .search-row { display: flex; align-items: center; gap: 0.7rem; margin-top: 1.35rem; max-width: 36rem; }
    input[type=search] {
      flex: 1;
      min-width: 0;
      padding: 0.85rem 1.15rem;
      border-radius: 999px;
      border: 1.5px solid #c9843a;
      background: rgba(18, 12, 9, 0.45);
      color: var(--ink);
      font-size: 1rem;
    }
    input[type=search]::placeholder { color: #cbbba8; }
    input[type=search]:focus { outline: 2px solid rgba(224, 164, 90, 0.45); outline-offset: 2px; }
    #go {
      border: none;
      background: var(--gold);
      color: #2a1c10;
      font-weight: 600;
      border-radius: 999px;
      padding: 0.85rem 1.3rem;
      cursor: pointer;
    }
    #go:disabled { opacity: 0.55; cursor: wait; }
    .ready { margin: 0.85rem 0 0; color: #cbbbaa; font-size: 0.85rem; }
    .board { padding: 1.15rem 1.6rem 3rem; }
    .chips { display: flex; flex-wrap: wrap; justify-content: center; gap: 0.45rem; margin: 0.2rem 0 1.35rem; }
    .chips[hidden] { display: none; }
    .chip {
      background: transparent;
      color: var(--cream);
      border: 1px solid #4a3e36;
      border-radius: 999px;
      padding: 0.38rem 0.85rem;
      cursor: pointer;
      font-size: 0.92rem;
    }
    .chip.on { background: var(--cream); color: #1a140f; border-color: var(--cream); }
    .chip:hover { border-color: #c9843a; }
    .section-head { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; margin-bottom: 0.9rem; }
    .section-head h2 {
      margin: 0;
      font-family: Fraunces, Georgia, serif;
      font-weight: 500;
      font-size: 2rem;
    }
    .meta { color: var(--muted); font-size: 0.9rem; text-align: right; }
    .cards { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.85rem; }
    .card {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 1rem 1rem 0.95rem;
      min-height: 124px;
    }
    .card-top { display: flex; gap: 0.8rem; align-items: flex-start; }
    .mark { width: 2rem; flex: none; margin-top: 0.15rem; }
    .mark svg { width: 1.7rem; height: 2.7rem; display: block; }
    .card-copy { min-width: 0; }
    .card h3 { margin: 0; font-size: 1.12rem; font-weight: 600; letter-spacing: -0.015em; line-height: 1.25; }
    .subline { margin: 0.22rem 0 0; color: var(--muted); font-size: 0.86rem; line-height: 1.35; }
    .abv {
      display: inline-block;
      margin-top: 0.55rem;
      padding: 0.12rem 0.55rem;
      border-radius: 999px;
      background: #1a140f;
      border: 1px solid #3d332c;
      color: var(--cream);
      font-size: 0.75rem;
    }
    .empty { color: var(--muted); padding: 2rem 0; text-align: center; }
    .pager {
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      align-items: center;
      gap: 0.4rem;
      margin-top: 1.35rem;
    }
    .pager[hidden] { display: none; }
    .pager button, .pager .gap {
      border: 1px solid #4a3e36;
      background: transparent;
      color: var(--cream);
      border-radius: 999px;
      min-width: 2.4rem;
      padding: 0.42rem 0.8rem;
      font-size: 0.92rem;
    }
    .pager button { cursor: pointer; font-family: inherit; }
    .pager button.on { background: var(--cream); color: #1a140f; border-color: var(--cream); }
    .pager button:disabled { opacity: 0.38; cursor: default; }
    .pager button:not(:disabled):hover { border-color: #c9843a; }
    .pager .gap { border: none; color: var(--muted); min-width: 0; padding: 0 0.15rem; }
    @media (max-width: 1100px) {
      .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 640px) {
      .topbar { grid-template-columns: 1fr; padding: 0.85rem 0.9rem; }
      .endpoint { justify-self: start; text-align: left; }
      .hero { min-height: 520px; background-position: center; }
      .hero-copy { padding: 1.6rem 0.9rem 1.4rem; }
      .search-row { flex-direction: column; align-items: stretch; }
      input[type=search], #go { width: 100%; }
      .board { padding: 1rem 0.9rem 2.4rem; }
      .cards { grid-template-columns: 1fr; }
      .section-head { flex-direction: column; align-items: flex-start; }
      .meta { text-align: left; }
    }
  </style>
</head>
<body>
  <header class="topbar">
    <div class="brand">
      <div class="logo" aria-hidden="true">
        <svg viewBox="0 0 32 32">
          <circle cx="16" cy="16" r="16" fill="#e7c48a"/>
          <path fill="#f7f1e6" d="M11 9.2h7.6v8.6a3.8 3.8 0 0 1-7.6 0V9.2z"/>
          <path fill="none" stroke="#f7f1e6" stroke-width="1.5" d="M18.6 12.2h2.3a1.6 1.6 0 0 1 0 3.2h-2.3"/>
        </svg>
      </div>
      <div class="brand-copy">
        <h1>The Sample Tap</h1>
        <p class="brand-sub">BEER-SAMPLE VIA ZEUS DIRECT</p>
      </div>
    </div>
    <nav class="modes" aria-label="Catalog">
      <button type="button" class="mode on" id="mode-beers" data-mode="beers">Beers</button>
      <button type="button" class="mode" id="mode-breweries" data-mode="breweries">Breweries</button>
    </nav>
    <div class="endpoint">
      <div class="host" id="host"></div>
      <div class="scope" id="scope"></div>
    </div>
  </header>
  <section class="hero">
    <div class="hero-copy">
      <p class="kicker" id="kicker">COUCHBASE BEER-SAMPLE · ZEUS _DEFAULT · ANALYTICS</p>
      <h2 class="display">What's on tap.</h2>
      <p class="deck">Live beer-sample through Zeus Direct: one <span class="em">pipeline</span> per pour (<span class="em">find</span>, then <span class="em">get</span>).</p>
      <form class="search-row" id="pour-form">
        <input id="q" type="search" placeholder="IPA, Portland, Duvel, chocolate stout..." autocomplete="off" />
        <button id="go" type="submit">Pour</button>
      </form>
      <p class="ready" id="ready">Zeus · ready</p>
    </div>
  </section>
  <main class="board">
    <div class="chips" id="chips"></div>
    <div class="section-head">
      <h2 id="section-title">Beers</h2>
      <div class="meta" id="meta"></div>
    </div>
    <div class="cards" id="cards"></div>
    <nav class="pager" id="pager" hidden aria-label="Pages"></nav>
  </main>
  <script>
    const CHIPS = ["All", "IPA", "Porter", "Stout", "Pale Ale", "Lager", "Pilsner", "Wheat", "Belgian", "Amber", "Brown Ale", "Hefeweizen", "Barleywine"];
    const chipsEl = document.getElementById("chips");
    const cardsEl = document.getElementById("cards");
    const metaEl = document.getElementById("meta");
    const qEl = document.getElementById("q");
    const goEl = document.getElementById("go");
    const titleEl = document.getElementById("section-title");
    const pageParams = new URLSearchParams(location.search);
    const PAGE_SIZE = 24;
    let mode = "beers";
    let pageIndex = 1;
    let requestToken = 0;

    CHIPS.forEach((label) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip" + (label === "All" ? " on" : "");
      b.textContent = label;
      b.addEventListener("click", () => {
        setChip(label);
        if (label === "All") {
          qEl.value = "";
          pageIndex = 1;
          rememberPage();
          loadList();
        } else {
          qEl.value = label;
          search(label);
        }
      });
      chipsEl.appendChild(b);
    });

    function setChip(label) {
      [...chipsEl.children].forEach((c) => c.classList.toggle("on", c.textContent === label));
    }

    function setMode(next) {
      mode = next === "breweries" ? "breweries" : "beers";
      document.getElementById("mode-beers").classList.toggle("on", mode === "beers");
      document.getElementById("mode-breweries").classList.toggle("on", mode === "breweries");
      titleEl.textContent = mode === "breweries" ? "Breweries" : "Beers";
      chipsEl.hidden = mode === "breweries";
      qEl.value = "";
      pageIndex = 1;
      rememberPage();
      setChip(mode === "beers" ? "All" : "");
      loadList();
    }

    document.getElementById("mode-beers").addEventListener("click", () => setMode("beers"));
    document.getElementById("mode-breweries").addEventListener("click", () => setMode("breweries"));

    const MARKS = {
      pint: "pint",
      hop: "hop",
      fruit: "fruit",
      pumpkin: "pumpkin",
      stout: "stout",
      lager: "lager",
      goblet: "goblet"
    };

    function markKind(card) {
      const blob = [card.style, card.category, card.name].filter(Boolean).join(" ").toLowerCase();
      if (blob.includes("pumpkin")) return "pumpkin";
      if (blob.includes("fruit") || blob.includes("berry") || blob.includes("lambic")) return "fruit";
      if (blob.includes("ipa") || blob.includes("pale ale")) return "hop";
      if (blob.includes("porter") || blob.includes("stout")) return "stout";
      if (blob.includes("lager") || blob.includes("pils")) return "lager";
      if (blob.includes("belgian") || blob.includes("french ale")) return "goblet";
      return "pint";
    }

    function glassFill(card) {
      const fills = {
        stout: "#5a3018",
        hop: "#e2b15a",
        lager: "#d7a441",
        fruit: "#c45c3e",
        pumpkin: "#e08a32",
        goblet: "#c9843c",
        pint: "#c47a32"
      };
      const kind = markKind(card);
      return fills[MARKS[kind] ? kind : "pint"] || fills.pint;
    }

    function markSvg(card) {
      const fill = glassFill(card);
      return `<svg viewBox="0 0 28 46" aria-hidden="true"><path d="M6 2.5h16v27.5c0 5.2-3.6 9.2-8 9.2s-8-4-8-9.2V2.5z" fill="none" stroke="#efe6da" stroke-width="1.6"/><path d="M7.5 14h13V30.2c0 3.8-2.9 6.6-6.5 6.6s-6.5-2.8-6.5-6.6V14z" fill="${fill}"/><path d="M7.3 5.2h13.4v7.2H7.3z" fill="#f6f1e8"/></svg>`;
    }

    function abvBadge(value) {
      if (value == null || value === "" || Number(value) === 0) return "";
      const n = Number(value);
      if (!Number.isFinite(n)) return "";
      return `<span class="abv">${n.toFixed(1)}% ABV</span>`;
    }

    function subline(card) {
      if (mode === "breweries") {
        const place = [card.city, card.state, card.country].filter(Boolean).join(", ");
        return place || card.category || card.style || "";
      }
      return [card.style, card.brewery].filter(Boolean).join(" · ");
    }

    function rangeLabel(data, count) {
      if (data && data.paged) {
        const offset = Number(data.offset) || 0;
        if (!count) return "0 shown";
        const start = offset + 1;
        const end = offset + count;
        const total = Number(data.total);
        if (Number.isFinite(total) && total >= 0) {
          return start.toLocaleString() + "–" + end.toLocaleString() + " of " + total.toLocaleString();
        }
        return start.toLocaleString() + "–" + end.toLocaleString() + " shown";
      }
      return count + " shown";
    }

    function pageWindow(current, pages) {
      if (pages <= 7) {
        const all = [];
        for (let n = 1; n <= pages; n += 1) all.push(n);
        return all;
      }
      const items = [1];
      const start = Math.max(2, current - 1);
      const end = Math.min(pages - 1, current + 1);
      if (start > 2) items.push("…");
      for (let n = start; n <= end; n += 1) items.push(n);
      if (end < pages - 1) items.push("…");
      items.push(pages);
      return items;
    }

    function renderPager(data) {
      const pager = document.getElementById("pager");
      const cards = (data && (data.items || data.cards)) || [];
      if (!data || !data.paged) {
        pager.hidden = true;
        pager.innerHTML = "";
        return;
      }
      const limit = Number(data.limit) || PAGE_SIZE;
      const offset = Number(data.offset) || 0;
      const total = Number(data.total);
      const hasTotal = Number.isFinite(total) && total >= 0;
      const pages = hasTotal ? Math.max(1, Math.ceil(total / limit)) : 0;
      const current = Math.floor(offset / limit) + 1;
      const hasPrev = offset > 0;
      const hasNext = data.truncated === true || (hasTotal && offset + cards.length < total);
      if (!hasPrev && !hasNext) {
        pager.hidden = true;
        pager.innerHTML = "";
        return;
      }
      pager.hidden = false;
      const parts = [];
      parts.push('<button type="button" data-page="' + (current - 1) + '"' + (hasPrev ? "" : " disabled") + ">Previous</button>");
      if (pages > 1) {
        pageWindow(current, pages).forEach((item) => {
          if (item === "…") {
            parts.push('<span class="gap" aria-hidden="true">…</span>');
            return;
          }
          const on = item === current ? " on" : "";
          const currentAttr = item === current ? ' aria-current="page"' : "";
          parts.push('<button type="button" class="page' + on + '" data-page="' + item + '"' + currentAttr + ">" + item + "</button>");
        });
      } else {
        parts.push('<span class="gap">Page ' + current + "</span>");
      }
      parts.push('<button type="button" data-page="' + (current + 1) + '"' + (hasNext ? "" : " disabled") + ">Next</button>");
      pager.innerHTML = parts.join("");
    }

    function paint(data) {
      if (data && data.paged && Number(data.pages) >= 1 && pageIndex > Number(data.pages)) {
        pageIndex = Number(data.pages);
        rememberPage();
        loadList(true);
        return;
      }
      const cards = data.items || data.cards || [];
      const rawPath = data.path || [];
      const hops = rawPath.filter((name) => name !== "run_turn" && name !== "catalog.load_for_turn");
      const path = (hops.length ? hops : rawPath).join(" → ");
      const lede = data.lede || "";
      titleEl.title = lede;
      metaEl.textContent = rangeLabel(data, cards.length) + (path ? " · " + path : "");
      renderPager(data);
      if (!cards.length) {
        const noun = mode === "breweries" ? "breweries" : "beers";
        cardsEl.innerHTML = '<div class="empty">No ' + noun + " matched.</div>";
        return;
      }
      cardsEl.innerHTML = cards.map((c) => {
        const line = subline(c);
        const badge = abvBadge(c.abv);
        return `<article class="card"><div class="card-top"><div class="mark">${markSvg(c)}</div><div class="card-copy"><h3>${escapeHtml(String(c.name || c.id || "beer"))}</h3>${line ? `<p class="subline">${escapeHtml(String(line))}</p>` : ""}${badge}</div></div></article>`;
      }).join("");
    }

    async function run(url, scroll) {
      const token = ++requestToken;
      goEl.disabled = true;
      document.querySelectorAll("#pager button").forEach((button) => { button.disabled = true; });
      metaEl.textContent = "Pouring…";
      cardsEl.innerHTML = "";
      try {
        const res = await fetch(url);
        const data = await res.json();
        if (token !== requestToken) return;
        if (!res.ok) throw new Error((data && data.detail && JSON.stringify(data.detail)) || res.statusText);
        paint(data);
        if (scroll) document.getElementById("section-title").scrollIntoView({ block: "start" });
      } catch (err) {
        if (token !== requestToken) return;
        metaEl.textContent = "Error: " + (err && err.message ? err.message : err);
        renderPager(null);
      } finally {
        if (token === requestToken) goEl.disabled = false;
      }
    }

    function rememberPage() {
      const url = new URL(location.href);
      const querying = (qEl.value || "").trim();
      if (!querying && pageIndex > 1) url.searchParams.set("page", String(pageIndex));
      else url.searchParams.delete("page");
      history.replaceState(null, "", url.pathname + url.search + url.hash);
    }

    function loadList(scroll) {
      const params = new URLSearchParams();
      params.set("limit", String(PAGE_SIZE));
      params.set("offset", String((pageIndex - 1) * PAGE_SIZE));
      const path = mode === "breweries" ? "/api/breweries" : "/api/beers";
      return run(path + "?" + params.toString(), scroll);
    }

    function goPage(page) {
      const next = Math.max(1, Math.floor(Number(page)));
      if (!Number.isFinite(next) || next === pageIndex) return;
      pageIndex = next;
      rememberPage();
      return loadList(true);
    }

    function search(q) {
      const query = (q ?? qEl.value ?? "").trim();
      qEl.value = query;
      pageIndex = 1;
      rememberPage();
      if (!query) return loadList();
      const params = new URLSearchParams();
      params.set("q", query);
      params.set("limit", pageParams.get("limit") || "24");
      if (mode === "breweries") params.set("entity", "Brewery");
      else if (pageParams.get("entity")) params.set("entity", pageParams.get("entity"));
      const match = CHIPS.find((label) => label.toLowerCase() === query.toLowerCase());
      setChip(match || "");
      return run("/api/search?" + params.toString());
    }

    function escapeHtml(s) {
      return s.replace(/[&<>"']/g, (ch) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      })[ch]);
    }

    async function loadConfig() {
      try {
        const res = await fetch("/api/config");
        const cfg = await res.json();
        const raw = String(cfg.zeus_url || "");
        const scheme = "://";
        const schemeAt = raw.indexOf(scheme);
        const host = schemeAt >= 0 ? raw.slice(schemeAt + scheme.length) : raw;
        document.getElementById("host").textContent = host;
        document.getElementById("scope").textContent = [cfg.bucket, cfg.scope, cfg.collection].filter(Boolean).join("/");
        const bucket = String(cfg.bucket || "beer-sample").toUpperCase();
        const scope = String(cfg.scope || "_default").toUpperCase();
        const tone = String(cfg.mode || "analytics").toUpperCase();
        document.getElementById("kicker").textContent = "COUCHBASE " + bucket + " · ZEUS " + scope + " · " + tone;
        document.getElementById("ready").textContent = cfg.zeus_version ? ("Zeus " + cfg.zeus_version + " · ready") : "Zeus · ready";
      } catch (err) {
        document.getElementById("ready").textContent = "Zeus · unreachable";
      }
    }

    document.getElementById("pour-form").addEventListener("submit", (e) => {
      e.preventDefault();
      search();
    });
    document.getElementById("pager").addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (!button || button.disabled) return;
      const page = Number(button.dataset.page);
      if (!Number.isFinite(page) || page < 1) return;
      goPage(page);
    });

    loadConfig();
    if ((pageParams.get("entity") || "").toLowerCase().startsWith("brew")) {
      mode = "breweries";
      document.getElementById("mode-beers").classList.remove("on");
      document.getElementById("mode-breweries").classList.add("on");
      titleEl.textContent = "Breweries";
      chipsEl.hidden = true;
    }
    if (pageParams.get("q")) {
      qEl.value = pageParams.get("q");
      search(pageParams.get("q"));
    } else {
      const initialPage = Number(pageParams.get("page") || "1");
      if (Number.isFinite(initialPage) && initialPage >= 1) pageIndex = Math.floor(initialPage);
      loadList();
    }
  </script>
</body>
</html>
"""
_REQUIREMENTS = """\
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
kotenai-zeus-client>=2.4.0,<2.5
python-dotenv>=1.0.0
"""

_README = """\
# {project_name}

Catalog UI for Couchbase **beer-sample**, written by Developer Helper MCP
`use_sample(sample=beer)`.

Same-origin **FastAPI BFF** + static page. Search follows
`demo_travel_sample`: the BFF calls `rt.agent.run_turn` and **omits**
`chat_request`, so `AgentAPI.run_turn` calls `catalog.load_for_turn`. That
loads the analytics catalog and merges the live **SCOPE BRIEF** and
**MINI-SCHEMA** into the system message on the model request. The BFF does
not build a pipeline body; tool calls stay inside the client turn.

An **LLM key is required** for search. Put it in `.env` as `LLM_API_KEY`.
`config.json` `llm.api_key_env` stays the name `LLM_API_KEY`. Do not paste
the secret into that field. `client_floor` is `client-floor-6.1`.
The semantic cache stays off.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set ZEUS_URL and LLM_API_KEY
```

## Run

```bash
uvicorn main:app --host 127.0.0.1 --port ${{PORT:-8090}}
# or: python main.py
```

Open `http://127.0.0.1:8090/`. Try **Fruit Beer**, **ipa**, **Duvel**, or
“What beers are made from fruits?”. The search box keeps the question.
`/search?q=…` opens the same page.

## Env

| Variable | Default | Notes |
| --- | --- | --- |
| `ZEUS_URL` | `http://localhost:8080` | Public API only — not Hub `:9091` |
| `ZEUS_BUCKET` | `beer-sample` | |
| `ZEUS_SCOPE` | `_default` | |
| `ZEUS_COLLECTION` | `_default` | |
| `PORT` | `8090` | BFF listen port |
| `CELLAR_CACHE_TTL` | `600` | Seconds to cache a successful turn |
| `LLM_API_KEY` | — | Required. The secret lives here. `config.json` `llm.api_key_env` names this variable |
| `LLM_BASE_URL` | `https://api.x.ai/v1` | |
| `LLM_MODEL` | `grok-4-1-fast-non-reasoning` | |
| `ZEUS_USERNAME` / `ZEUS_PASSWORD` | — | Optional basic auth |
| `ZEUS_BEARER_TOKEN` | — | Optional bearer |

## Search path (BFF)

`GET /api/search` sends the raw question to `rt.agent.run_turn` with the
runtime target and settings. `chat_request` is not passed. The client loads
`data/chat_requests/chat_request_analytics_v2.json` (analytics template, no
baked scope brief) and fetches the live brief for this bucket/scope so
`## MINI-SCHEMA` is part of the model request. Cards on the page are beer
rows taken from the turn's tool results.

`GET /api/beers` and `GET /api/breweries` page the catalog. `limit` defaults to 24 and `offset` selects the page (`/api/beers?limit=24&offset=24` is page 2). Each page is a Direct `find` ordered by id, then `get` for the card fields. The page shows Previous, page numbers, and Next. Pour search stays on `run_turn`. The id routes use that same turn.

## Docs

- https://docs.koten.ai/zeus-client/using-zeus-client
- Travel search: `demo_travel_sample` `rt.agent.run_turn` + `catalog.load_for_turn`
"""


def sanitize_beer_dir_name(project_name: str = "") -> str:
    raw = (project_name or "").strip()
    if not raw:
        return DEFAULT_BEER_DIR_NAME
    if any(sep in raw for sep in ("/", "\\", "..")):
        return DEFAULT_BEER_DIR_NAME
    name = raw.replace(" ", "-")
    if not name or name in {".", ".."} or not _DIR_NAME_RE.match(name):
        return DEFAULT_BEER_DIR_NAME
    return name


def _default_parent() -> Path:
    here = Path(__file__).resolve()
    helper_root = here.parents[2]
    monorepo = helper_root.parent
    if monorepo.is_dir():
        return monorepo
    return Path.cwd()


def resolve_beer_dest(
    *,
    sample_dir: str = "",
    project_name: str = "",
    parent_dir: str = "",
) -> Path:
    parent = (
        Path(parent_dir).expanduser().resolve()
        if parent_dir.strip()
        else _default_parent()
    )
    raw = sample_dir.strip()
    if raw:
        p = Path(raw).expanduser()
        if p.is_absolute() or len(p.parts) > 1:
            return p.resolve()
        name = sanitize_beer_dir_name(project_name or p.name)
        return parent / name
    return parent / sanitize_beer_dir_name(project_name)


def _beer_state_path(cfg: HelperConfig) -> Path:
    return cfg.state_dir / "beer_sample.json"


def save_beer_sample_dir(cfg: HelperConfig, root: Path) -> None:
    try:
        cfg.state_dir.mkdir(parents=True, exist_ok=True)
        _beer_state_path(cfg).write_text(
            json.dumps({"beer_sample_dir": str(root.resolve())}) + "\n",
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001, S110
        pass


def set_demo_beer_sample_dir_env(root: Path) -> str:
    path = str(root.expanduser().resolve())
    os.environ[ENV_BEER_DIR] = path
    return path


def beer_bff_is_current(text: str) -> bool:
    """True when search is a travel-style run_turn and the BFF builds no pipeline."""
    return (
        "agent.run_turn" in text
        and "catalog.load_for_turn" in text
        and "HttpxCatalogRemote" in text
        and "OpenAICompatibleLlmClient" in text
        and "FsCatalogStore" in text
        and "chat_request=" not in text
        and "pipeline_body" not in text
        and 'fetch("pipeline"' not in text
        and "fetch('pipeline'" not in text
    )


def validate_beer_layout(root: Path) -> dict[str, Any]:
    found: list[str] = []
    missing: list[str] = []
    for name in BEER_MARKERS:
        p = root / name
        if p.exists():
            found.append(name)
        else:
            missing.append(name)
    main = root / "main.py"
    readme = root / "README.md"
    ok = main.is_file() and readme.is_file() and (root / "requirements.txt").is_file()
    current = False
    if ok and main.is_file():
        try:
            current = beer_bff_is_current(main.read_text(encoding="utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            current = False
        ok = current
    return {
        "ok": ok,
        "current": current,
        "root": str(root),
        "found": found,
        "missing": missing,
        "note": "Beer catalog UI (FastAPI BFF + static). Search is rt.agent.run_turn with catalog.load_for_turn.",
    }


def looks_like_beer_sample(root: Path) -> bool:
    return (
        (root / "main.py").is_file()
        and (root / "README.md").is_file()
        and (root / "requirements.txt").is_file()
        and (root / "static" / "index.html").is_file()
    )


_ANALYTICS_CATALOG_REL = Path("v2/base/base-6.1/min/chat_request_analytics_base-6.1.json")


def _packaged_analytics_catalog() -> Path:
    """Template shipped with the Helper. Used when no zeus_chat_request checkout is present."""
    return Path(__file__).resolve().parent / "assets" / "chat_request_analytics_v2.json"


def _sibling_chat_request_root() -> Path:
    return Path(__file__).resolve().parents[3] / "zeus_chat_request"


def analytics_catalog_source(cfg: HelperConfig | None = None) -> Path | None:
    """base-6.1 analytics template. It has no SCOPE BRIEF, so load_for_turn can merge a live one.

    A local zeus_chat_request checkout wins. The packaged copy is the fallback for
    a PyPI install that has no sibling clone.
    """
    roots: list[Path] = []
    if cfg is not None and cfg.chat_request_dir is not None:
        roots.append(Path(cfg.chat_request_dir))
    env = os.environ.get("ZEUS_CHAT_REQUEST_DIR", "").strip()
    if env:
        roots.append(Path(env).expanduser())
    roots.append(_sibling_chat_request_root())
    seen: set[Path] = set()
    candidates: list[Path] = []
    for root in roots:
        try:
            resolved = root.expanduser().resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        candidates.append(resolved / _ANALYTICS_CATALOG_REL)
    candidates.append(_packaged_analytics_catalog())
    for path in candidates:
        if path.is_file():
            return path
    return None


def install_beer_catalog(cfg: HelperConfig, root: Path) -> dict[str, Any]:
    """Copy the brief-free analytics catalog to the filename FsCatalogStore loads."""
    dest_dir = root / "data" / "chat_requests"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "chat_request_analytics_v2.json"
    src = analytics_catalog_source(cfg)
    if src is None:
        return {"ok": False, "copied": False, "path": str(dest_dir)}
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return {"ok": True, "copied": True, "path": str(dest), "source": str(src)}


def _attach_llm_key(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Add a presence-only key report. Never include the secret."""
    from zeus_dev_helper_mcp.llm_key import inspect_app_llm_key

    report = inspect_app_llm_key(root)
    payload["llm_key"] = report
    if report.get("applies") and not report.get("ok") and report.get("message"):
        rest = str(payload.get("next_action") or "").strip()
        message = str(report["message"])
        payload["next_action"] = f"{message} {rest}".strip() if rest else message
    return payload


def write_beer_env_example(cfg: HelperConfig, target_dir: str | Path) -> dict[str, Any]:
    root = Path(target_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = root / ".env.example"
    content = f"""# Copy to .env (never commit .env). Search needs an LLM key.
ZEUS_URL={cfg.zeus_url or "http://localhost:8080"}
ZEUS_BUCKET={cfg.default_bucket or "beer-sample"}
ZEUS_SCOPE={cfg.default_scope or "_default"}
ZEUS_COLLECTION={cfg.default_collection or "_default"}
ZEUS_MODE=analytics
PORT=8090
CELLAR_CACHE_TTL=600
LLM_BASE_URL=https://api.x.ai/v1
LLM_API_KEY=
LLM_MODEL=grok-4-1-fast-non-reasoning
# ZEUS_USERNAME=
# ZEUS_PASSWORD=
# ZEUS_BEARER_TOKEN=
"""
    path.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(path), "note": "No secrets written — placeholders only"}


def write_beer_config(cfg: HelperConfig, target_dir: str | Path) -> dict[str, Any]:
    """Runtime pin for a travel-style turn. Floor matches live base-6.1."""
    root = Path(target_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = root / "config.json"
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
            "bucket": cfg.default_bucket or "beer-sample",
            "scope": cfg.default_scope or "_default",
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
            "durable_sessions": True,
            "ai_process_result": False,
            "max_rounds": 12,
            "ignore_user_tool_path_hints": True,
        },
        "session": {"semantic_cache": {"enabled": False}},
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "path": str(path)}


def _hero_asset() -> Path:
    return Path(__file__).resolve().parent / "assets" / "beer-hero.jpg"


def beer_page_is_current(root: Path) -> bool:
    """True when the served page is the Sample Tap hero layout."""
    html = root / "static" / "index.html"
    hero = root / "static" / "hero.jpg"
    if not html.is_file() or not hero.is_file():
        return False
    try:
        text = html.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return "What's on tap." in text and 'id="go"' in text and ">Pour<" in text


def install_beer_page(root: Path) -> list[str]:
    """Write the Sample Tap page and hero photo. Leaves the BFF alone."""
    root = Path(root)
    static = root / "static"
    static.mkdir(parents=True, exist_ok=True)
    html_path = static / "index.html"
    html_path.write_text(_INDEX_HTML, encoding="utf-8")
    written = [str(html_path)]
    hero_src = _hero_asset()
    if hero_src.is_file():
        hero_path = static / "hero.jpg"
        hero_path.write_bytes(hero_src.read_bytes())
        written.append(str(hero_path))
    return written


def _write_generated_tree(cfg: HelperConfig, root: Path, name: str) -> list[str]:
    files: dict[str, str] = {
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
    written.extend(install_beer_page(root))
    env_info = write_beer_env_example(cfg, root)
    written.append(str(env_info["path"]))
    catalog_info = install_beer_catalog(cfg, root)
    written.append(str(catalog_info["path"]))
    cfg_info = write_beer_config(cfg, root)
    written.append(str(cfg_info["path"]))
    return written


def write_beer_sample(
    cfg: HelperConfig,
    target_dir: str | Path,
    *,
    project_name: str = DEFAULT_BEER_DIR_NAME,
    force: bool = False,
) -> dict[str, Any]:
    """Write the beer catalog UI. Search uses rt.agent.run_turn like travel."""
    root = Path(target_dir).expanduser().resolve()
    name = sanitize_beer_dir_name(project_name) if project_name else root.name
    if name == DEFAULT_BEER_DIR_NAME and project_name:
        name = sanitize_beer_dir_name(project_name)

    upgrading = False
    if root.exists() and any(root.iterdir()) and not force:
        if looks_like_beer_sample(root):
            main_text = (root / "main.py").read_text(encoding="utf-8", errors="replace")
            if beer_bff_is_current(main_text):
                env_path = set_demo_beer_sample_dir_env(root)
                save_beer_sample_dir(cfg, root)
                layout = validate_beer_layout(root)
                if beer_page_is_current(root):
                    return _attach_llm_key(
                        root,
                        {
                            "ok": True,
                            "written": False,
                            "local_dir": str(root),
                            "project_name": root.name,
                            "layout": layout,
                            "env": {ENV_BEER_DIR: env_path},
                            "next_action": (
                                f"Existing beer catalog UI at {root}. "
                                "Set ZEUS_URL and LLM_API_KEY in .env. "
                                "Leave config.json llm.api_key_env as LLM_API_KEY. "
                                "Run verify_local_setup before uvicorn. "
                                "pip install -r requirements.txt; "
                                f"uvicorn main:app --port ${{PORT:-8090}}"
                            ),
                        },
                    )
                page_files = install_beer_page(root)
                return _attach_llm_key(
                    root,
                    {
                        "ok": True,
                        "written": True,
                        "upgraded": True,
                        "page_only": True,
                        "local_dir": str(root),
                        "project_name": root.name,
                        "files": page_files,
                        "layout": layout,
                        "env": {ENV_BEER_DIR: env_path},
                        "next_action": (
                            f"Updated the Sample Tap page at {root / 'static' / 'index.html'}. "
                            "Leave config.json llm.api_key_env as LLM_API_KEY. "
                            "Run verify_local_setup before uvicorn. "
                            "Restart uvicorn if it is already running."
                        ),
                    },
                )
            upgrading = True
        else:
            return {
                "ok": False,
                "error": f"target_dir not empty and does not look like beer sample: {root}",
                "local_dir": str(root),
                "next_action": (
                    "Pick an empty directory / unused project_name, or point sample_dir "
                    "at an existing demo_beer_sample tree"
                ),
            }

    root.mkdir(parents=True, exist_ok=True)
    (root / "static").mkdir(parents=True, exist_ok=True)
    written = _write_generated_tree(cfg, root, name)

    meta = {
        "sample": "beer",
        "app_kind": "ui",
        "track": "ui-direct",
        "llm_required": True,
        "zeus_url": cfg.zeus_url or "http://localhost:8080",
        "bucket": cfg.default_bucket or "beer-sample",
        "scope": cfg.default_scope or "_default",
        "from": "zeus_dev_helper_mcp.beer.write_beer_sample",
        "bff": "rt.agent.run_turn omits chat_request; catalog.load_for_turn merges MINI-SCHEMA",
        "client_floor": "client-floor-6.1",
        "client": "kotenai-zeus-client>=2.4.0,<2.5",
    }
    meta_path = root / "sample_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    written.append(str(meta_path))

    env_path = set_demo_beer_sample_dir_env(root)
    save_beer_sample_dir(cfg, root)
    layout = validate_beer_layout(root)

    try:
        set_item_status(cfg, "0.2", "done", evidence=f"beer_layout={root}")
        set_item_status(cfg, "3.1", "done", evidence=f"beer_dir={root}")
    except Exception:  # noqa: BLE001, S110
        pass

    port = 8090
    run_cmd = (
        f"cd {root} && python3 -m venv .venv && source .venv/bin/activate && "
        "pip install -r requirements.txt && cp -n .env.example .env"
    )
    result = {
        "ok": True,
        "written": True,
        "upgraded": upgrading,
        "target_dir": str(root),
        "local_dir": str(root),
        "project_name": name,
        "files": written,
        "layout": layout,
        "env_example": {"ok": True, "path": str(root / ".env.example")},
        "env": {ENV_BEER_DIR: env_path},
        "run": run_cmd,
        "llm_required": True,
        "next_action": (
            "Put ZEUS_URL and LLM_API_KEY in .env. "
            "Leave config.json llm.api_key_env as LLM_API_KEY. "
            "Run verify_local_setup before uvicorn. "
            "Search calls rt.agent.run_turn and omits chat_request so the client "
            "merges SCOPE BRIEF + MINI-SCHEMA. "
            f"Install deps and run uvicorn on PORT={port}."
        ),
        "docs": {
            "using": docs_url("zeus-client/using-zeus-client.md"),
            "design": "docs/DESIGN-zdm-1-beer-first-green.md",
        },
    }
    return _attach_llm_key(root, result)


def ensure_beer_sample(
    cfg: HelperConfig,
    *,
    sample_dir: str = "",
    project_name: str = "",
    parent_dir: str = "",
    force: bool = False,
) -> dict[str, Any]:
    """Locate an existing beer Direct UI or write a fresh template."""
    dir_name = sanitize_beer_dir_name(project_name)
    dest = resolve_beer_dest(
        sample_dir=sample_dir,
        project_name=project_name,
        parent_dir=parent_dir,
    )

    return write_beer_sample(
        cfg,
        dest,
        project_name=dir_name,
        force=force,
    )
