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
    if _force_closed(answer) or _force_closed(err_text):
        raise HTTPException(
            status_code=503,
            detail={"error": "session_force_closed", "req_ids": _req_ids(result)},
        )
    if result.status == TurnStatus.ERROR:
        raise HTTPException(
            status_code=502,
            detail={
                "error": err_text or "agent turn failed",
                "req_ids": _req_ids(result),
            },
        )

    items = collect_beer_cards(_turn_blobs(result), limit=cap)
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


@app.get("/api/config")
async def api_config() -> dict[str, Any]:
    cfg = _runtime().config
    return {
        "zeus_url": cfg.zeus.url,
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
async def api_beers(limit: int = Query(PAGE_CAP, ge=1, le=PAGE_CAP)) -> dict[str, Any]:
    return await _run_search("List beers", limit=limit)


@app.get("/api/breweries")
async def api_breweries(limit: int = Query(PAGE_CAP, ge=1, le=PAGE_CAP)) -> dict[str, Any]:
    return await _run_search("List breweries", limit=limit)


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
    for fn in (_parse_blob, _card_from_row, _card_score, _matching_card_index, collect_beer_cards):
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
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%23e8a838'/%3E%3Cpath d='M9 6h3.2v9.2H9zM8 8.2h8.4v2.2H8zM13 16.2h8.2v7.2a4.1 4.1 0 0 1-8.2 0z' fill='%231a1208'/%3E%3C/svg%3E" />
  <style>
    :root {
      --bg: #1a1410;
      --panel: #2a2118;
      --ink: #f5e6d3;
      --muted: #b8a48c;
      --accent: #e8a838;
      --chip: #3d3024;
      --chip-on: #c4782a;
      --card: #32271d;
      --ok: #7ec88a;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; font-family: "Segoe UI", system-ui, sans-serif;
      background: radial-gradient(ellipse at top, #2c2118, var(--bg));
      color: var(--ink); min-height: 100vh;
    }
    header {
      padding: 1.5rem 1.25rem 0.5rem; max-width: 960px; margin: 0 auto;
    }
    h1 { margin: 0 0 0.25rem; font-size: 1.75rem; letter-spacing: 0.02em; }
    .brand { display: flex; align-items: center; gap: 0.85rem; }
    .brand-copy { min-width: 0; }
    .logo {
      width: 3rem; height: 3rem; flex: none; border-radius: 14px;
      background: linear-gradient(160deg, var(--accent), var(--chip-on));
      color: #1a1208; display: grid; place-items: center;
    }
    .logo svg { width: 1.75rem; height: 1.75rem; display: block; }
    .sub { color: var(--muted); font-size: 0.95rem; margin: 0; }
    main { max-width: 960px; margin: 0 auto; padding: 1rem 1.25rem 3rem; }
    .search-row { display: flex; gap: 0.5rem; margin: 1rem 0 0.75rem; }
    input[type=search] {
      flex: 1; padding: 0.75rem 1rem; border-radius: 999px; border: 1px solid #5a4634;
      background: var(--panel); color: var(--ink); font-size: 1rem;
    }
    button {
      padding: 0.75rem 1.1rem; border-radius: 999px; border: none;
      background: var(--accent); color: #1a1208; font-weight: 600; cursor: pointer;
    }
    button:disabled { opacity: 0.5; cursor: wait; }
    .chips { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 1rem; }
    .chip {
      background: var(--chip); color: var(--ink); border: 1px solid #5a4634;
      padding: 0.35rem 0.75rem; border-radius: 999px; cursor: pointer; font-size: 0.9rem;
    }
    .chip.on, .chip:hover { background: var(--chip-on); border-color: var(--accent); }
    .meta { color: var(--muted); font-size: 0.85rem; margin-bottom: 0.75rem; min-height: 1.2em; }
    .meta code { color: var(--ok); }
    .cards {
      display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 0.75rem;
    }
    .card {
      background: var(--card); border: 1px solid #4a3a2c; border-radius: 12px;
      padding: 0.9rem 1rem; box-shadow: 0 8px 24px rgba(0,0,0,0.25);
    }
    .card-top { display: flex; gap: 0.75rem; align-items: flex-start; }
    .mark {
      width: 2.5rem; height: 2.5rem; flex: none; margin-top: 0.1rem;
      border-radius: 10px; background: #3d3024; color: var(--accent);
      border: 1px solid #5a4634; display: grid; place-items: center;
    }
    .mark svg { width: 1.35rem; height: 1.35rem; display: block; }
    .card-copy { min-width: 0; flex: 1; }
    .card h3 { margin: 0 0 0.2rem; font-size: 1.05rem; }
    .card .eyebrow {
      color: var(--muted); font-size: 0.72rem; letter-spacing: 0.04em;
      text-transform: uppercase; margin-bottom: 0.25rem;
    }
    .card .style { color: var(--accent); font-size: 0.85rem; margin: 0.15rem 0 0.35rem; }
    .card p { margin: 0.2rem 0 0; color: var(--muted); font-size: 0.85rem; line-height: 1.35; }
    .lede { margin: 0 0 0.35rem; color: var(--ink); font-size: 1rem; }
    .empty { color: var(--muted); padding: 2rem 0; text-align: center; }
    footer { max-width: 960px; margin: 0 auto; padding: 0 1.25rem 2rem; color: var(--muted); font-size: 0.8rem; }
    @media (max-width: 640px) {
      header, main, footer { padding-left: 0.75rem; padding-right: 0.75rem; }
      h1 { font-size: 1.45rem; }
      .logo { width: 2.5rem; height: 2.5rem; border-radius: 12px; }
      .logo svg { width: 1.45rem; height: 1.45rem; }
      .search-row { flex-direction: column; }
      .cards { grid-template-columns: 1fr; }
      input[type=search], button { width: 100%; }
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="logo" aria-hidden="true">
        <svg viewBox="0 0 32 32" fill="none">
          <path d="M9 5h3.2v9.2H9V5z" fill="currentColor"/>
          <path d="M8.2 7.2h8.2v2.4H8.2V7.2z" fill="currentColor"/>
          <path d="M12.4 14.4h8.6c.9 0 1.6.7 1.6 1.6v6.4c0 3.5-2.6 5.8-5.9 5.8s-5.9-2.3-5.9-5.8v-6.4c0-.9.7-1.6 1.6-1.6z" stroke="currentColor" stroke-width="1.8"/>
          <path d="M22.6 17.2h3.1c.7 0 1.3.6 1.3 1.3v2.5c0 .7-.6 1.3-1.3 1.3h-3.1" stroke="currentColor" stroke-width="1.8"/>
        </svg>
      </div>
      <div class="brand-copy">
        <h1>The Sample Tap</h1>
        <p class="sub">Catalog UI on <strong>beer-sample</strong>. Search runs a Zeus Client turn so the request includes the scope MINI-SCHEMA.</p>
      </div>
    </div>
  </header>
  <main>
    <div class="search-row">
      <input id="q" type="search" placeholder="What beers are made from fruits?" autocomplete="off" />
      <button id="go" type="button">Search</button>
    </div>
    <div class="chips" id="chips"></div>
    <div class="meta" id="meta"></div>
    <div class="cards" id="cards"></div>
  </main>
  <footer>
    Same-origin BFF proxies Zeus public API :8080. Semantic cache off. Contract hash never invented here.
  </footer>
  <script>
    const CHIPS = ["Fruit Beer", "Pumpkin Beer", "Belgian and French Ale", "ipa", "porter", "Duvel"];
    const chipsEl = document.getElementById("chips");
    const cardsEl = document.getElementById("cards");
    const metaEl = document.getElementById("meta");
    const qEl = document.getElementById("q");
    const goEl = document.getElementById("go");
    const pageParams = new URLSearchParams(location.search);

    CHIPS.forEach((label) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip";
      b.textContent = label;
      b.addEventListener("click", () => {
        qEl.value = label;
        [...chipsEl.children].forEach((c) => c.classList.toggle("on", c.textContent === label));
        search(label);
      });
      chipsEl.appendChild(b);
    });

    function abvText(value) {
      if (value == null || value === "" || Number(value) === 0) return "ABV —";
      return "ABV " + value;
    }

    const MARKS = {
      pint: '<path fill="currentColor" d="M7 3h8v10.2A4 4 0 0 1 7 13.2V3z"/><path fill="currentColor" d="M15 6.2h2.4a1.6 1.6 0 0 1 0 3.2H15z"/>',
      hop: '<circle cx="12" cy="12" r="2.1" fill="currentColor"/><path fill="currentColor" d="M12 3.6c1.1 2.3.6 4.2-.2 5.2-.8-1-1.3-2.9-.2-5.2zM12 20.4c-1.1-2.3-.6-4.2.2-5.2.8 1 1.3 2.9.2 5.2zM3.6 12c2.3-1.1 4.2-.6 5.2.2-1 .8-2.9 1.3-5.2.2zM20.4 12c-2.3 1.1-4.2.6-5.2-.2 1-.8 2.9-1.3 5.2-.2zM6.2 6.2c2.2.8 3.2 2.4 3.4 3.6-1.6-.2-3.4-1.2-3.4-3.6zM17.8 17.8c-2.2-.8-3.2-2.4-3.4-3.6 1.6.2 3.4 1.2 3.4 3.6zM17.8 6.2c-.8 2.2-2.4 3.2-3.6 3.4.2-1.6 1.2-3.4 3.6-3.4zM6.2 17.8c.8-2.2 2.4-3.2 3.6-3.4-.2 1.6-1.2 3.4-3.6 3.4z"/>',
      fruit: '<circle cx="12" cy="14" r="5" fill="currentColor"/><path fill="currentColor" d="M11.2 9.2c.6-2.6 2.6-4 4.6-4.2-.8 1.6-.4 3-1.2 4.2h-3.4z"/><path fill="currentColor" d="M13.6 6.2c1.6-.2 2.8.6 3.2 1.8-1.4.2-2.4-.2-3.2-1.8z"/>',
      pumpkin: '<circle cx="8.4" cy="14.2" r="3.5" fill="currentColor"/><circle cx="15.6" cy="14.2" r="3.5" fill="currentColor"/><circle cx="12" cy="13.4" r="4.1" fill="currentColor"/><path fill="currentColor" d="M11.2 6.1h1.6c.2 1 .1 2.1-.3 2.8h-1c-.4-.7-.5-1.8-.3-2.8z"/>',
      stout: '<path fill="currentColor" d="M6.6 3h8.2v10.6a4.1 4.1 0 0 1-8.2 0V3z"/><path fill="currentColor" d="M14.8 6.2h2.6a1.7 1.7 0 0 1 0 3.4h-2.6z"/>',
      lager: '<path fill="currentColor" d="M8.2 2.8h7.6v14a3.8 3.8 0 0 1-7.6 0v-14z"/><path fill="#3d3024" d="M8.8 7.4h6.4v1.3H8.8z"/>',
      goblet: '<path fill="currentColor" d="M6.6 3.4h10.8l-1.3 7.4a4.1 4.1 0 0 1-8.2 0L6.6 3.4z"/><path fill="currentColor" d="M11.1 15.2h1.8V19h2.6v1.6H8.5V19h2.6v-3.8z"/>'
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

    function markSvg(card) {
      const kind = markKind(card);
      return `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">${MARKS[kind] || MARKS.pint}</svg>`;
    }

    async function search(q) {
      const query = (q ?? qEl.value ?? "").trim();
      qEl.value = query;
      goEl.disabled = true;
      metaEl.textContent = "Searching…";
      cardsEl.innerHTML = "";
      try {
        const params = new URLSearchParams();
        params.set("q", query);
        if (pageParams.get("entity")) params.set("entity", pageParams.get("entity"));
        if (pageParams.get("limit")) params.set("limit", pageParams.get("limit"));
        const res = await fetch("/api/search?" + params.toString());
        const data = await res.json();
        if (!res.ok) throw new Error((data && data.detail && JSON.stringify(data.detail)) || res.statusText);
        const cards = data.items || data.cards || [];
        const path = (data.path || []).join(" → ");
        const reqs = (data.req_ids || []).filter(Boolean).join(", ");
        const lede = data.lede || "";
        const count = cards.length ? `<span>${cards.length} result(s)</span> · ` : "";
        metaEl.innerHTML = (lede ? `<p class="lede">${escapeHtml(lede)}</p>` : "") +
          count + `<code>${path || "—"}</code>` +
          (reqs ? ` · req_id <code>${reqs}</code>` : "");
        if (!cards.length) {
          cardsEl.innerHTML = '<div class="empty">No beers matched.</div>';
          return;
        }
        cardsEl.innerHTML = cards.map((c) => {
          const eyebrow = c.category ? `<div class="eyebrow">${escapeHtml(String(c.category))}</div>` : "";
          const style = c.style ? `<div class="style">${escapeHtml(String(c.style))}</div>` : "";
          const bits = [abvText(c.abv)];
          if (c.ibu != null && c.ibu !== "" && Number(c.ibu) !== 0) bits.push("IBU " + c.ibu);
          if (c.brewery) bits.push(String(c.brewery));
          const desc = c.description ? `<p>${escapeHtml(String(c.description).slice(0, 160))}</p>` : "";
          return `<article class="card"><div class="card-top"><div class="mark">${markSvg(c)}</div><div class="card-copy">${eyebrow}<h3>${escapeHtml(String(c.name || c.id || "beer"))}</h3>${style}<p>${escapeHtml(bits.join(" · "))}</p>${desc}</div></div></article>`;
        }).join("");
      } catch (err) {
        metaEl.textContent = "Error: " + (err && err.message ? err.message : err);
      } finally {
        goEl.disabled = false;
      }
    }

    function escapeHtml(s) {
      return s.replace(/[&<>"']/g, (ch) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      })[ch]);
    }

    goEl.addEventListener("click", () => search());
    qEl.addEventListener("keydown", (e) => { if (e.key === "Enter") search(); });
    if (pageParams.get("q")) {
      qEl.value = pageParams.get("q");
      search(pageParams.get("q"));
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

An **LLM key is required** for search. `client_floor` is `client-floor-6.1`.
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
| `LLM_API_KEY` | — | Required. OpenAI-compatible key for the turn |
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

`GET /api/beers`, `GET /api/breweries`, and the id routes use the same turn.

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


def analytics_catalog_source(cfg: HelperConfig | None = None) -> Path | None:
    """base-6.1 analytics template. It has no SCOPE BRIEF, so load_for_turn can merge a live one."""
    roots: list[Path] = []
    if cfg is not None and cfg.chat_request_dir is not None:
        roots.append(Path(cfg.chat_request_dir))
    env = os.environ.get("ZEUS_CHAT_REQUEST_DIR", "").strip()
    if env:
        roots.append(Path(env).expanduser())
    here = Path(__file__).resolve()
    roots.append(here.parents[3] / "zeus_chat_request")
    seen: set[Path] = set()
    for root in roots:
        try:
            resolved = root.expanduser().resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        path = resolved / _ANALYTICS_CATALOG_REL
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


def _write_generated_tree(cfg: HelperConfig, root: Path, name: str) -> list[str]:
    files: dict[str, str] = {
        "main.py": _MAIN_PY,
        "requirements.txt": _REQUIREMENTS,
        "README.md": _README.format(project_name=name),
        "static/index.html": _INDEX_HTML,
    }
    written: list[str] = []
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        written.append(str(path))
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
                return {
                    "ok": True,
                    "written": False,
                    "local_dir": str(root),
                    "project_name": root.name,
                    "layout": layout,
                    "env": {ENV_BEER_DIR: env_path},
                    "next_action": (
                        f"Existing beer catalog UI at {root}. "
                        "Set ZEUS_URL and LLM_API_KEY in .env; "
                        f"pip install -r requirements.txt; "
                        f"uvicorn main:app --port ${{PORT:-8090}}"
                    ),
                }
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
        set_item_status(cfg, "3.2", "done", evidence=str(root / ".env.example"))
    except Exception:  # noqa: BLE001, S110
        pass

    port = 8090
    run_cmd = (
        f"cd {root} && python3 -m venv .venv && source .venv/bin/activate && "
        "pip install -r requirements.txt && cp .env.example .env && "
        f"uvicorn main:app --host 127.0.0.1 --port {port}"
    )
    return {
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
            "Search calls rt.agent.run_turn and omits chat_request so the client "
            "merges SCOPE BRIEF + MINI-SCHEMA. "
            f"Install deps and run uvicorn on PORT={port}."
        ),
        "docs": {
            "using": docs_url("zeus-client/using-zeus-client.md"),
            "design": "docs/DESIGN-zdm-1-beer-first-green.md",
        },
    }


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
