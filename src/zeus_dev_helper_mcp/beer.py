"""Beer-sample Direct catalog UI template (ZDM-6).

Zero-LLM same-origin FastAPI BFF + static page. Sequential find → get
(+ FTS fallback). Never POST pipeline.
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
        "Zero-LLM Direct catalog UI for beer-sample. "
        "use_sample(sample=beer) writes a FastAPI BFF + static page (find→get, no pipeline)."
    ),
    "related": [
        docs_url("zeus-client/using-zeus-client.md"),
        "https://github.com/koten-ai/zeus_dev_helper_mcp",
    ],
}

_MAIN_PY = '''#!/usr/bin/env python3
"""Beer-sample Direct catalog UI — FastAPI BFF (zero LLM).

Sequential find → get (+ FTS fallback). Direct-safe: no multi-step DAG verb.
Scaffolded by zeus_dev_helper_mcp use_sample(sample=beer).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")

ZEUS_URL = (os.environ.get("ZEUS_URL") or "http://localhost:8080").rstrip("/")
ZEUS_BUCKET = os.environ.get("ZEUS_BUCKET") or "beer-sample"
ZEUS_SCOPE = os.environ.get("ZEUS_SCOPE") or "_default"
ZEUS_COLLECTION = os.environ.get("ZEUS_COLLECTION") or "_default"
PORT = int(os.environ.get("PORT") or "8090")

# Chip label / short token → find where.style value (equality-only).
KNOWN_STYLES: dict[str, str] = {
    "ipa": "American IPA",
    "american ipa": "American IPA",
    "porter": "Porter",
    "stout": "Stout",
    "lager": "Lager",
    "pilsner": "Pilsner",
    "wheat": "Wheat Beer",
    "wheat beer": "Wheat Beer",
    "fruit": "Fruit Beer",
    "fruit beer": "Fruit Beer",
    "sour": "Sour Beer",
    "belgian": "Belgian Ale",
    "pale ale": "American Pale Ale",
    "apa": "American Pale Ale",
}

app = FastAPI(title="Beer Direct catalog UI", version="0.1.0")
_static = _ROOT / "static"
if _static.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static)), name="static")


def _auth() -> tuple[str, str] | None:
    user = (os.environ.get("ZEUS_USERNAME") or os.environ.get("ZEUS_USER") or "").strip()
    password = (os.environ.get("ZEUS_PASSWORD") or "").strip()
    if user and password:
        return user, password
    return None


def _headers() -> dict[str, str]:
    h = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "demo-beer-sample",
    }
    token = (os.environ.get("ZEUS_BEARER_TOKEN") or os.environ.get("ZEUS_TOKEN") or "").strip()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _verb_url(verb: str) -> str:
    return f"{ZEUS_URL}/v2/{ZEUS_BUCKET}/{ZEUS_SCOPE}/{ZEUS_COLLECTION}/{verb}"


def _unwrap(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    result = payload.get("result")
    if isinstance(result, dict):
        return result
    return payload


def _node_ids(data: dict[str, Any]) -> list[str]:
    raw = data.get("node_ids") or data.get("ids") or []
    out: list[str] = []
    if isinstance(raw, list):
        for x in raw:
            s = str(x).strip()
            if s:
                out.append(s)
    return out


def _items(data: dict[str, Any]) -> list[Any]:
    raw = data.get("items") or data.get("nodes") or []
    return list(raw) if isinstance(raw, list) else []


def _parse_doc_key(doc_key: str) -> dict[str, str]:
    """Turn FTS doc_key (e.g. beer::21st_amendment_brewery_cafe-21a_ipa) into a card."""
    key = (doc_key or "").strip()
    title = key
    if "::" in key:
        title = key.split("::", 1)[1]
    elif ":" in key:
        title = key.split(":", 1)[1]
    pretty = title.replace("_", " ").replace("-", " ").strip() or key
    return {"id": key, "name": pretty, "doc_key": key, "source": "doc_key"}


def _card_from_node(node: Any) -> dict[str, Any] | None:
    if not isinstance(node, dict):
        return None
    nested = node.get("node") if isinstance(node.get("node"), dict) else None
    body = node.get("body") if isinstance(node.get("body"), dict) else None
    if body is None and nested is not None and isinstance(nested.get("body"), dict):
        body = nested.get("body")
    if body is None:
        body = nested if nested is not None else node
    if not isinstance(body, dict):
        body = {}
    nid = str(
        node.get("id")
        or (nested or {}).get("id")
        or body.get("id")
        or ""
    ).strip()
    doc_key = str(
        node.get("doc_key")
        or body.get("doc_key")
        or (nested or {}).get("doc_key")
        or ""
    ).strip()
    name = body.get("name") or body.get("title") or node.get("name")
    if not name and doc_key:
        return _parse_doc_key(doc_key)
    if not name and nid:
        name = nid
    if not name:
        return None
    card: dict[str, Any] = {
        "id": nid or doc_key or str(name),
        "name": str(name),
        "style": body.get("style") or node.get("style"),
        "abv": body.get("abv") or node.get("abv"),
        "ibu": body.get("ibu") or node.get("ibu"),
        "description": body.get("description") or body.get("desc") or node.get("description"),
        "brewery": body.get("brewery") or body.get("brewery_id") or node.get("brewery"),
        "doc_key": doc_key or None,
        "source": "get" if nid.startswith("n_") else "find",
    }
    return card


def _cards_from_find_or_fts(data: dict[str, Any], *, source: str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for item in _items(data):
        if not isinstance(item, dict):
            continue
        node = item.get("node") if isinstance(item.get("node"), dict) else item
        if not isinstance(node, dict):
            continue
        nid = str(node.get("id") or item.get("id") or "").strip()
        doc_key = str(node.get("doc_key") or item.get("doc_key") or "").strip()
        # FTS often returns doc_key with empty graph ids — card from doc_key, never get.
        if doc_key and not nid.startswith("n_"):
            card = _parse_doc_key(doc_key)
            card["source"] = source
            cards.append(card)
            continue
        card = _card_from_node(item)
        if card:
            card["source"] = source
            cards.append(card)
    return cards


async def _post_verb(verb: str, body: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    url = _verb_url(verb)
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
        r = await client.post(url, json=body, headers=_headers(), auth=_auth())
    req_id = r.headers.get("X-Zeus-Req-Id") or r.headers.get("x-zeus-req-id")
    if r.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "error": f"zeus {verb} HTTP {r.status_code}",
                "body_preview": (r.text or "")[:400],
                "req_id": req_id,
                "url": url,
            },
        )
    try:
        payload = r.json()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"invalid JSON from Zeus {verb}: {e}") from e
    return _unwrap(payload), req_id


async def _find(body: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    return await _post_verb("find", body)


async def _get(ids: list[str]) -> tuple[dict[str, Any], str | None]:
    # abort_if_empty: never get on empty node_ids
    if not ids:
        return {"items": [], "node_ids": []}, None
    return await _post_verb("get", {"ids": ids[:50], "include": ["body"]})


async def _fts(query_text: str) -> tuple[dict[str, Any], str | None]:
    return await _post_verb(
        "search",
        {"strategy": "fts", "query_text": query_text, "limit": 20},
    )


def _resolve_style(q: str) -> str | None:
    key = (q or "").strip().lower()
    if not key:
        return None
    if key in KNOWN_STYLES:
        return KNOWN_STYLES[key]
    # Exact chip values already canonical
    for canon in KNOWN_STYLES.values():
        if key == canon.lower():
            return canon
    return None


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
async def api_config() -> dict[str, Any]:
    return {
        "zeus_url": ZEUS_URL,
        "bucket": ZEUS_BUCKET,
        "scope": ZEUS_SCOPE,
        "collection": ZEUS_COLLECTION,
        "llm_required": False,
        "styles": sorted(set(KNOWN_STYLES.values())),
        "chips": ["ipa", "porter", "stout", "lager", "Fruit Beer", "pale ale", "sour"],
    }


@app.get("/api/search")
async def api_search(q: str = Query("", min_length=0, max_length=200)) -> dict[str, Any]:
    """Catalog search: known style → find where.style; short token → find query; else FTS.

    Never calls get when node_ids is empty (abort_if_empty behavior).
    On empty find: FTS fallback; doc_key-only hits become cards without get.
    """
    query = (q or "").strip()
    if not query:
        return {"ok": True, "query": query, "cards": [], "path": [], "req_ids": []}

    path: list[str] = []
    req_ids: list[str] = []
    style = _resolve_style(query)

    find_body: dict[str, Any]
    if style:
        find_body = {
            "entity_type": "Beer",
            "where": {"style": style},
            "return": "ids",
            "limit": 20,
        }
        path.append(f"find:where.style={style}")
    else:
        # Short tokens → find query= (not NL sentences)
        find_body = {
            "entity_type": "Beer",
            "query": query,
            "return": "ids",
            "limit": 20,
        }
        path.append(f"find:query={query}")

    find_data, rid = await _find(find_body)
    if rid:
        req_ids.append(rid)
    ids = _node_ids(find_data)

    # abort_if_empty: empty find → do not get; try FTS
    if not ids:
        path.append("abort_if_empty")
        fts_data, frid = await _fts(query)
        if frid:
            req_ids.append(frid)
        path.append("search:fts")
        fts_ids = _node_ids(fts_data)
        if fts_ids:
            get_data, grid = await _get(fts_ids)
            if grid:
                req_ids.append(grid)
            path.append("get")
            cards = []
            for item in _items(get_data):
                card = _card_from_node(item if isinstance(item, dict) else {})
                if card:
                    cards.append(card)
            if not cards:
                cards = _cards_from_find_or_fts(fts_data, source="fts")
            return {
                "ok": True,
                "query": query,
                "cards": cards,
                "path": path,
                "req_ids": req_ids,
                "node_ids": fts_ids,
            }
        # node_ids=[] but items may carry doc_key — parse into cards; never get
        cards = _cards_from_find_or_fts(fts_data, source="fts_doc_key")
        if cards:
            path.append("doc_key")
        return {
            "ok": True,
            "query": query,
            "cards": cards,
            "path": path,
            "req_ids": req_ids,
            "node_ids": [],
            "note": "FTS doc_key-only or empty; skipped get",
        }

    get_data, grid = await _get(ids)
    if grid:
        req_ids.append(grid)
    path.append("get")
    cards = []
    for item in _items(get_data):
        card = _card_from_node(item if isinstance(item, dict) else {})
        if card:
            cards.append(card)
    if not cards:
        cards = _cards_from_find_or_fts(find_data, source="find")
    return {
        "ok": True,
        "query": query,
        "cards": cards,
        "path": path,
        "req_ids": req_ids,
        "node_ids": ids,
    }


@app.get("/")
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
'''

_INDEX_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>The Sample Tap — beer-sample Direct</title>
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
    .sub { color: var(--muted); font-size: 0.95rem; }
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
    .card h3 { margin: 0 0 0.35rem; font-size: 1.05rem; }
    .card .style { color: var(--accent); font-size: 0.85rem; margin-bottom: 0.35rem; }
    .card p { margin: 0; color: var(--muted); font-size: 0.85rem; line-height: 1.35; }
    .empty { color: var(--muted); padding: 2rem 0; text-align: center; }
    footer { max-width: 960px; margin: 0 auto; padding: 0 1.25rem 2rem; color: var(--muted); font-size: 0.8rem; }
  </style>
</head>
<body>
  <header>
    <h1>The Sample Tap</h1>
    <p class="sub">Zero-LLM Direct UI on <strong>beer-sample</strong> — find → get (+ FTS). No pipeline. No LLM key.</p>
  </header>
  <main>
    <div class="search-row">
      <input id="q" type="search" placeholder="Search beers (ipa, porter, fruit…)" autocomplete="off" />
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
    const CHIPS = ["ipa", "porter", "stout", "lager", "Fruit Beer", "pale ale", "sour"];
    const chipsEl = document.getElementById("chips");
    const cardsEl = document.getElementById("cards");
    const metaEl = document.getElementById("meta");
    const qEl = document.getElementById("q");
    const goEl = document.getElementById("go");
    let activeChip = "";

    CHIPS.forEach((label) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip";
      b.textContent = label;
      b.addEventListener("click", () => {
        activeChip = label;
        qEl.value = label;
        [...chipsEl.children].forEach((c) => c.classList.toggle("on", c.textContent === label));
        search(label);
      });
      chipsEl.appendChild(b);
    });

    async function search(q) {
      const query = (q ?? qEl.value ?? "").trim();
      goEl.disabled = true;
      metaEl.textContent = "Searching…";
      cardsEl.innerHTML = "";
      try {
        const res = await fetch("/api/search?q=" + encodeURIComponent(query));
        const data = await res.json();
        if (!res.ok) throw new Error((data && data.detail && JSON.stringify(data.detail)) || res.statusText);
        const cards = data.cards || [];
        const path = (data.path || []).join(" → ");
        const reqs = (data.req_ids || []).filter(Boolean).join(", ");
        metaEl.innerHTML = cards.length
          ? `<span>${cards.length} result(s)</span> · <code>${path || "—"}</code>` +
            (reqs ? ` · req_id <code>${reqs}</code>` : "")
          : `No rows · <code>${path || "—"}</code>`;
        if (!cards.length) {
          cardsEl.innerHTML = '<div class="empty">No beers matched. Try a style chip or a short token.</div>';
          return;
        }
        cardsEl.innerHTML = cards.map((c) => {
          const style = c.style ? `<div class="style">${escapeHtml(String(c.style))}</div>` : "";
          const bits = [];
          if (c.abv != null) bits.push("ABV " + c.abv);
          if (c.ibu != null) bits.push("IBU " + c.ibu);
          if (c.brewery) bits.push(String(c.brewery));
          const desc = c.description ? `<p>${escapeHtml(String(c.description).slice(0, 160))}</p>` : "";
          const sub = bits.length ? `<p>${escapeHtml(bits.join(" · "))}</p>` : "";
          return `<article class="card"><h3>${escapeHtml(String(c.name || c.id || "beer"))}</h3>${style}${sub}${desc}</article>`;
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
  </script>
</body>
</html>
"""

_REQUIREMENTS = """\
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
httpx>=0.27.0
python-dotenv>=1.0.0
"""

_README = """\
# {project_name}

Zero-LLM **Direct** catalog UI for Couchbase **beer-sample**, written by
Developer Helper MCP `use_sample(sample=beer)`.

Same-origin **FastAPI BFF** + static page. The BFF talks to Zeus public API
**`:8080`** with sequential **`find` → `get`** and an **FTS `search` fallback**.
It never POSTs **`pipeline`** (Direct / ErrorCode `060010`).

**No LLM key required.**

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set ZEUS_URL (and auth if needed)
```

## Run

```bash
uvicorn main:app --host 127.0.0.1 --port ${{PORT:-8090}}
# or: python main.py
```

Open `http://127.0.0.1:8090/`. Try chips **ipa** / **porter** / **Fruit Beer**,
or a short search token. Cards show `req_id` from the BFF path.

## Env

| Variable | Default | Notes |
| --- | --- | --- |
| `ZEUS_URL` | `http://localhost:8080` | Public API only — not Hub `:9091` |
| `ZEUS_BUCKET` | `beer-sample` | |
| `ZEUS_SCOPE` | `_default` | |
| `ZEUS_COLLECTION` | `_default` | |
| `PORT` | `8090` | BFF listen port |
| `ZEUS_USERNAME` / `ZEUS_PASSWORD` | — | Optional basic auth |
| `ZEUS_BEARER_TOKEN` | — | Optional bearer |

No `LLM_API_KEY` / OpenAI key is required for first paint.

## Search path (BFF)

1. Known styles (chip / alias) → `find` with `where.style=…`
2. Other short tokens → `find` with `query=`
3. Empty `node_ids` → **abort_if_empty** (skip `get`) → FTS `search`
4. FTS with ids → `get`; FTS with `doc_key` only → parse cards (no `get`)
5. Never call `get` when `node_ids` is empty

## Docs

- https://docs.koten.ai/zeus-client/using-zeus-client
- Helper design: ZDM-1 beer first-green / ZDM-6 Direct UI
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
    if ok and main.is_file():
        try:
            text = main.read_text(encoding="utf-8", errors="replace")
            # Reject only callable pipeline surfaces, not prose that says "no pipeline".
            calls_pipeline = (
                "/pipeline" in text
                or '"pipeline"' in text
                or "'pipeline'" in text
            )
            ok = (
                not calls_pipeline
                and ("/find" in text or '"find"' in text or "find" in text)
                and "abort_if_empty" in text
            )
        except Exception:  # noqa: BLE001
            ok = False
    return {
        "ok": ok,
        "root": str(root),
        "found": found,
        "missing": missing,
        "note": "Beer Direct UI markers (FastAPI BFF + static, no pipeline)",
    }


def looks_like_beer_sample(root: Path) -> bool:
    return bool(validate_beer_layout(root).get("ok"))


def write_beer_env_example(cfg: HelperConfig, target_dir: str | Path) -> dict[str, Any]:
    root = Path(target_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = root / ".env.example"
    content = f"""# Copy to .env (never commit .env). No LLM key required.
ZEUS_URL={cfg.zeus_url or "http://localhost:8080"}
ZEUS_BUCKET={cfg.default_bucket or "beer-sample"}
ZEUS_SCOPE={cfg.default_scope or "_default"}
ZEUS_COLLECTION={cfg.default_collection or "_default"}
PORT=8090
# ZEUS_USERNAME=
# ZEUS_PASSWORD=
# ZEUS_BEARER_TOKEN=
"""
    path.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(path), "note": "No secrets written — placeholders only"}


def write_beer_sample(
    cfg: HelperConfig,
    target_dir: str | Path,
    *,
    project_name: str = DEFAULT_BEER_DIR_NAME,
    force: bool = False,
) -> dict[str, Any]:
    """Write runnable beer Direct UI under target_dir."""
    root = Path(target_dir).expanduser().resolve()
    name = sanitize_beer_dir_name(project_name) if project_name else root.name
    if name == DEFAULT_BEER_DIR_NAME and project_name:
        name = sanitize_beer_dir_name(project_name)

    if root.exists() and any(root.iterdir()) and not force:
        if looks_like_beer_sample(root):
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
                    f"Existing beer Direct UI at {root}. "
                    f"cp .env.example .env; pip install -r requirements.txt; "
                    f"uvicorn main:app --port ${{PORT:-8090}}"
                ),
            }
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
        if path.exists() and not force:
            continue
        path.write_text(body, encoding="utf-8")
        written.append(str(path))

    env_info = write_beer_env_example(cfg, root)
    written.append(str(env_info["path"]))

    meta = {
        "sample": "beer",
        "app_kind": "ui",
        "track": "ui-direct",
        "llm_required": False,
        "zeus_url": cfg.zeus_url or "http://localhost:8080",
        "bucket": cfg.default_bucket or "beer-sample",
        "scope": cfg.default_scope or "_default",
        "from": "zeus_dev_helper_mcp.beer.write_beer_sample",
        "bff": "find→get (+ FTS); no pipeline",
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
        set_item_status(cfg, "3.2", "done", evidence=str(env_info.get("path")))
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
        "target_dir": str(root),
        "local_dir": str(root),
        "project_name": name,
        "files": written,
        "layout": layout,
        "env_example": env_info,
        "env": {ENV_BEER_DIR: env_path},
        "run": run_cmd,
        "llm_required": False,
        "next_action": (
            "Put ZEUS_URL (and optional auth) in .env — no LLM key. "
            f"Install deps and run uvicorn on PORT={port}; then smoke_test_zeus. "
            "Do not require smoke_test_agent on this Direct track."
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

    if sample_dir.strip():
        explicit = Path(sample_dir).expanduser().resolve()
        if explicit.is_dir() and looks_like_beer_sample(explicit):
            env_path = set_demo_beer_sample_dir_env(explicit)
            save_beer_sample_dir(cfg, explicit)
            return {
                "ok": True,
                "local_dir": str(explicit),
                "written": False,
                "project_name": explicit.name,
                "layout": validate_beer_layout(explicit),
                "env": {ENV_BEER_DIR: env_path},
                "next_action": (
                    f"Using existing beer sample at {explicit}. "
                    "Continue readiness_check / smoke_test_zeus (no LLM)."
                ),
            }

    return write_beer_sample(
        cfg,
        dest,
        project_name=dir_name,
        force=force,
    )
