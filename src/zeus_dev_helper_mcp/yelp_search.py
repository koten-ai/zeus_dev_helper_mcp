"""Default yelp-demo search: the live scope chat request is the session body.

use_sample applies this to the LocalAI checkout. A stock clone ranks a bundled
catalog in the browser and loads a base catalog in run_agent. After this step,
POST /api/search loads chat_request.json for the scope and passes that document
as chat_req_override.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_SEARCH_PY = Path("src/local_guide/search.py")
_CLIENT_TS = Path("frontend/src/api/client.ts")
_VITE = Path("frontend/vite.config.ts")

_HELPERS = '''def _llm_key_from_env(provider: dict) -> str:
    """Read the LLM key from the env name. Do not copy the key into config.json."""
    import os

    env_name = str(provider.get("api_key_env") or "LLM_API_KEY").strip() or "LLM_API_KEY"
    found = (os.environ.get(env_name) or "").strip()
    if found:
        return found
    for name in ("LLM_API_KEY", "XAI_API_KEY", "OPENAI_API_KEY"):
        if name == env_name:
            continue
        found = (os.environ.get(name) or "").strip()
        if found:
            return found
    raw = str(provider.get("api_key") or "").strip()
    if raw and raw != env_name:
        return raw
    return ""


def _chat_request_text(doc: dict) -> str:
    messages = doc.get("messages") if isinstance(doc.get("messages"), list) else []
    if messages and isinstance(messages[0], dict):
        return str(messages[0].get("content") or "")
    return ""


async def fetch_search_chat_request(
    zeus_url: str,
    mode: str,
    bucket: str,
    scope: str,
) -> dict:
    """Live ``chat_request.json`` for this scope. That document is the session body.

    A base-catalog file selected by ``base_id`` is not this document.
    """
    from zeus_client.zeus.catalog import load_live_chat_request

    doc = await load_live_chat_request(zeus_url, mode, bucket, scope, {})
    if not isinstance(doc, dict):
        raise ValueError(f"live chat_request for {bucket}/{scope} was not a JSON object")
    content = _chat_request_text(doc)
    if "## SCOPE BRIEF" not in content or "## MINI-SCHEMA" not in content:
        raise ValueError(
            f"live chat_request for {bucket}/{scope} mode {mode} "
            "has no scope brief or mini-schema"
        )
    return doc


async def _run_search_agent(
    *,
    zeus_url: str,
    zcfg: dict,
    base_url: str,
    api_key: str,
    model: str,
    api_version: str,
    mode: str,
    bucket: str,
    scope: str,
    collection: str,
    message: str,
    prior_turns: list,
    provider_id: str,
    chat_id: str,
    prior_sid: str,
    prior_round: int,
    settings: ClientSettings,
    base_id: str | None,
    base_catalog_dirs: list[Path] | None,
    chat_request: dict,
):
    """One agent turn. ``chat_request`` is the session create body."""
    return await run_agent(
        zeus_url,
        zcfg,
        base_url,
        api_key,
        model,
        api_version,
        mode,
        bucket,
        scope,
        collection,
        message,
        prior_turns,
        optimized=True,
        provider_id=provider_id,
        conv_id=chat_id,
        zeus_session_id=prior_sid,
        zeus_round=prior_round,
        structured=True,
        output_schema=DEMO_OUTPUT_SCHEMA,
        settings=settings,
        base_id=base_id,
        base_catalog_dirs=base_catalog_dirs,
        chat_req_override=chat_request,
    )


'''

_OLD_CALL = """        settings = ClientSettings(ai_process_result=bool(ai_process_result))
        answer, trace, new_turns, session_meta, structured = await run_agent(
"""

_NEW_CALL = """        settings = ClientSettings(ai_process_result=bool(ai_process_result))
        chat_request = await fetch_search_chat_request(zeus_url, mode, bucket, scope)
        answer, trace, new_turns, session_meta, structured = await _run_search_agent(
            zeus_url=zeus_url,
            zcfg=zcfg,
            base_url=base_url,
            api_key=api_key,
            model=model,
            api_version=api_version,
            mode=mode,
            bucket=bucket,
            scope=scope,
            collection=collection,
            message=message,
            prior_turns=prior_turns,
            provider_id=provider_id,
            chat_id=chat_id,
            prior_sid=prior_sid,
            prior_round=prior_round,
            settings=settings,
            base_id=base_id,
            base_catalog_dirs=base_catalog_dirs,
            chat_request=chat_request,
        )
"""

# 0.7.6 inserted this retry. A 401 must stay red (ZDM-23).
_AUTH_NONE_RETRY = '''        turn_zcfg = zcfg
        try:
            answer, trace, new_turns, session_meta, structured = await _run_search_agent(
                zeus_url=zeus_url,
                zcfg=turn_zcfg,'''

_AUTH_NONE_ASSIGN = 'public["auth_mode"] = "none"'

_OLD_LLM_KEY = '    api_key = provider.get("api_key") or ""'
_NEW_LLM_KEY = "    api_key = _llm_key_from_env(provider)"

_OLD_HEALTH = """export async function fetchHealth(): Promise<HealthResponse> {
  return {
    ok: true,
    app_version: "0.1.0",
    business_count: BUSINESSES.length,
    corpus_label: "businesses",
    corpus_source: "sample",
  };
}
"""

_NEW_HEALTH = """export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch("/api/health");
  if (!res.ok) {
    throw new Error(`health failed (${res.status})`);
  }
  return (await res.json()) as HealthResponse;
}
"""

_OLD_UI_SEARCH = """export async function search(
  query: string,
  chatId?: string | null,
  options?: SearchOptions
): Promise<SearchResponse> {
  const q = query.trim();
  await delay(420, options?.signal);
"""

_NEW_UI_SEARCH = """export async function search(
  query: string,
  chatId?: string | null,
  options?: SearchOptions
): Promise<SearchResponse> {
  const q = query.trim();
  if (!q) {
    return {
      chat_id: chatId || "",
      query: "",
      answer: "",
      structured_answer: null,
      results: [],
    };
  }
  const res = await fetch("/api/search", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      query: q,
      chat_id: chatId || null,
      ai_process_result: Boolean(options?.summarize),
    }),
    signal: options?.signal,
  });
  const data = (await res.json().catch(() => ({}))) as SearchResponse & {
    error?: string;
    detail?: { error?: string } | string;
  };
  if (!res.ok) {
    const detail = data.detail;
    const message =
      data.error ||
      (typeof detail === "string" ? detail : detail?.error) ||
      `search failed (${res.status})`;
    throw new Error(message);
  }
  const results = Array.isArray(data.results) ? data.results : [];
  if (data.chat_id) lastResultsByChat.set(data.chat_id, results);
  return {
    chat_id: data.chat_id || chatId || "",
    query: data.query || q,
    answer: typeof data.answer === "string" ? data.answer : "",
    structured_answer: data.structured_answer ?? null,
    results,
  };
}
"""

_VITE_PROXY = """    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:5000",
        timeout: 180000,
      },
    },
"""

# Search project lists omit latitude/longitude, so the map has nothing to plot.
# The source document key is biz:yelp:<id>.
_PROMPT_BEFORE_COORDS = (
    '    "- After FTS/hybrid, project using @step.ids / node_ids returned by that step — "\n'
    '    "do not batch_get raw source keys like biz:… alone if get returns missing.\\n"\n'
    '    "- pipeline confidence must be a STRING: high|med|low (never an object).\\n"\n'
)
_PROMPT_WITH_COORDS = (
    '    "- After FTS/hybrid, project using @step.ids / node_ids returned by that step — "\n'
    '    "do not batch_get raw source keys like biz:… alone if get returns missing.\\n"\n'
    '    "- Every Business project fields list must include \\"latitude\\" and \\"longitude\\" "\n'
    '    "together with name, stars, review_count, categories, address, city, and state. "\n'
    '    "Search cards plot those coordinates.\\n"\n'
    '    "- pipeline confidence must be a STRING: high|med|low (never an object).\\n"\n'
)

_COORD_HELPERS = '''def yelp_business_doc_key(business_id: str) -> str:
    """Couchbase key for a Yelp business source doc: ``biz:yelp:<id>``."""
    bid = (business_id or "").strip()
    if not bid or bid.startswith("file:") or bid.startswith("n_"):
        return ""
    if bid.startswith("biz:yelp:"):
        bare = bid[len("biz:yelp:") :].strip()
    elif bid.startswith("biz:"):
        bare = bid[4:].strip()
    else:
        bare = bid
    if not bare or bare.startswith("file:") or bare.startswith("n_"):
        return ""
    return f"biz:yelp:{bare}"


def _coordinate_text(val: object) -> str:
    if val is None or isinstance(val, (dict, list, bool)):
        return ""
    text = str(val).strip()
    if not text or text.lower() in {"null", "none", "nan"}:
        return ""
    return text


def _card_needs_coordinates(card: dict) -> bool:
    return not _coordinate_text(card.get("latitude")) or not _coordinate_text(
        card.get("longitude")
    )


def apply_coordinate_rows(cards: list[dict], rows: list[dict]) -> None:
    """Copy latitude/longitude onto cards that omitted them. Match on source key."""
    by_key: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        for raw in (row.get("business_id"), row.get("doc_key"), row.get("id")):
            key = yelp_business_doc_key(str(raw or ""))
            if key:
                by_key[key] = row
    for card in cards:
        if not isinstance(card, dict) or not _card_needs_coordinates(card):
            continue
        row = by_key.get(yelp_business_doc_key(str(card.get("business_id") or "")))
        if not row:
            continue
        if not _coordinate_text(card.get("latitude")):
            lat = _coordinate_text(row.get("latitude"))
            if lat:
                card["latitude"] = lat
        if not _coordinate_text(card.get("longitude")):
            lon = _coordinate_text(row.get("longitude"))
            if lon:
                card["longitude"] = lon


async def fill_missing_coordinates(cards: list[dict] | None) -> list[dict]:
    """Add latitude and longitude from Yelp source docs when a card omitted them.

    Search project lists often leave coordinates out. The source document key
    is ``biz:yelp:<id>``; one ``USE KEYS`` read fills every missing card.
    """
    if not cards:
        return []
    pending_keys: list[str] = []
    seen: set[str] = set()
    for card in cards:
        if not isinstance(card, dict) or not _card_needs_coordinates(card):
            continue
        key = yelp_business_doc_key(str(card.get("business_id") or ""))
        if key and key not in seen:
            seen.add(key)
            pending_keys.append(key)
    if not pending_keys:
        return cards

    try:
        cfg = await load_config()
    except Exception as e:
        logger.warning("coordinate fill skipped; config: %s", e)
        return cards

    cb_raw = cfg.get("couchbase") if isinstance(cfg.get("couchbase"), dict) else None
    if not cb_raw:
        return cards

    from zeus_client import CouchbaseQueryConfig
    from zeus_client.zeus.suggest import n1ql_hydrate_keys

    zcfg = resolve_zeus_config(cfg)
    zeus_url = str(zcfg.get("url") or "")
    sample = cfg.get("default_sample", "yelp-demo")
    triple = (cfg.get("samples") or {}).get(sample) or {}
    bucket = str(triple.get("bucket") or sample or "")
    scope = str(triple.get("scope") or "_default")
    collection = str(triple.get("collection") or "_default")
    if not bucket:
        return cards
    try:
        cb = CouchbaseQueryConfig.from_mapping(
            cb_raw,
            zeus_url=zeus_url,
            allow_host_default=False,
        )
    except Exception as e:
        logger.warning("coordinate fill skipped; couchbase config: %s", e)
        return cards
    if cb is None:
        return cards
    try:
        rows = await n1ql_hydrate_keys(
            cb,
            bucket,
            scope,
            collection,
            pending_keys,
            fields=("business_id", "latitude", "longitude"),
            # mDNS to the Zeus query port often exceeds a few seconds.
            timeout_s=15.0,
        )
    except Exception as e:
        logger.warning("coordinate fill failed: %s", e)
        return cards
    apply_coordinate_rows(cards, rows)
    return cards


'''

_LAST_RESULTS = '        CHATS[chat_id]["last_results"] = results\n'
_LAST_RESULTS_WITH_COORDS = (
    "        results = await fill_missing_coordinates(results)\n" + _LAST_RESULTS
)

_DETAIL_PY = Path("src/local_guide/detail.py")
_OLD_DETAIL_CACHE = """    cached = find_cached_business(business_id)
    if cached:
        apply_local_images(cached)
        return {
            "business": cached,
            "chat_id": None,
            "source": "cache",
            "ai_process_result": False,
        }
"""
_NEW_DETAIL_CACHE = """    cached = find_cached_business(business_id)
    if cached:
        # Search cards often omit coordinates. Fill them before the detail map
        # reuses this cached card.
        from local_guide.search import fill_missing_coordinates

        await fill_missing_coordinates([cached])
        apply_local_images(cached)
        return {
            "business": cached,
            "chat_id": None,
            "source": "cache",
            "ai_process_result": False,
        }
"""


def _read(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _patch_search_py(text: str) -> str | None:
    updated = text
    if _AUTH_NONE_ASSIGN in updated and "login failed" in updated:
        start = updated.find(_AUTH_NONE_RETRY)
        marker = '\n\n        CHATS[chat_id]["turns"] = new_turns'
        end = updated.find(marker, max(start, 0))
        if start >= 0 and end > start:
            # Settings and the fetch line already sit above the retry.
            kept = (
                "        settings = ClientSettings(ai_process_result=bool(ai_process_result))\n"
                "        chat_request = await fetch_search_chat_request(zeus_url, mode, bucket, scope)\n"
            )
            if kept in updated[:start] or "chat_request = await fetch_search_chat_request" in updated[:start]:
                call = _NEW_CALL.removeprefix(kept)
            else:
                call = _NEW_CALL
            updated = updated[:start] + call + updated[end:]
    elif "chat_req_override=chat_request" not in updated or "def fetch_search_chat_request" not in updated:
        if _OLD_CALL in updated and "async def run_search(" in updated:
            draft = updated
            if "def fetch_search_chat_request" not in draft:
                draft = draft.replace(
                    "async def run_search(", _HELPERS + "async def run_search(", 1
                )
            start = draft.find(_OLD_CALL)
            end = draft.find('\n\n        CHATS[chat_id]["turns"] = new_turns', start)
            if start >= 0 and end > start:
                updated = draft[:start] + _NEW_CALL + draft[end:]
    if _OLD_LLM_KEY in updated and "def _llm_key_from_env" not in updated:
        updated = updated.replace(
            "async def run_search(",
            _HELPERS + "async def run_search(",
            1,
        )
        updated = updated.replace(_OLD_LLM_KEY, _NEW_LLM_KEY, 1)
    elif _OLD_LLM_KEY in updated:
        updated = updated.replace(_OLD_LLM_KEY, _NEW_LLM_KEY, 1)
    if updated == text:
        return None
    return updated


def _patch_client_ts(text: str) -> str | None:
    updated = text
    if 'fetch("/api/search"' not in updated:
        start = updated.find(_OLD_UI_SEARCH)
        end = updated.find("\nexport async function fetchBusiness(", start if start >= 0 else 0)
        if start >= 0 and end > start:
            updated = updated[:start] + _NEW_UI_SEARCH + updated[end + 1 :]
    if _OLD_HEALTH in updated:
        updated = updated.replace(_OLD_HEALTH, _NEW_HEALTH, 1)
    if updated == text:
        return None
    return updated


def _patch_search_coordinates(text: str) -> str | None:
    """Fill latitude and longitude on search cards when the project step omits them."""
    original = text
    if "Every Business project fields list must include" not in text and _PROMPT_BEFORE_COORDS in text:
        text = text.replace(_PROMPT_BEFORE_COORDS, _PROMPT_WITH_COORDS, 1)
    if (
        "def fill_missing_coordinates" not in text
        and "def synthesize_answer_from_results(" in text
    ):
        text = text.replace(
            "def synthesize_answer_from_results(",
            _COORD_HELPERS + "def synthesize_answer_from_results(",
            1,
        )
    if (
        "def fill_missing_coordinates" in text
        and "await fill_missing_coordinates(results)" not in text
        and _LAST_RESULTS in text
    ):
        text = text.replace(_LAST_RESULTS, _LAST_RESULTS_WITH_COORDS, 1)
    if text == original:
        return None
    return text


def _patch_detail_coordinates(text: str) -> str | None:
    """Fill coordinates when the business page replays a search card from cache."""
    if "await fill_missing_coordinates([cached])" in text:
        return None
    if _OLD_DETAIL_CACHE not in text:
        return None
    return text.replace(_OLD_DETAIL_CACHE, _NEW_DETAIL_CACHE, 1)


def _patch_vite(text: str) -> str | None:
    if "127.0.0.1:5000" in text and '"/api"' in text:
        return None
    needle = "    port: 5173,\n"
    if needle not in text or "proxy:" in text:
        return None
    return text.replace(needle, _VITE_PROXY, 1)


def apply_yelp_live_search(root: Path) -> dict[str, Any]:
    """Make this checkout's search send the live scope chat request.

    Idempotent. A directory without the LocalAI search files is left unchanged.
    """
    root = root.expanduser().resolve()
    patched: list[str] = []
    missing: list[str] = []
    jobs = (
        (_SEARCH_PY, _patch_search_py),
        (_SEARCH_PY, _patch_search_coordinates),
        (_CLIENT_TS, _patch_client_ts),
        (_VITE, _patch_vite),
        (_DETAIL_PY, _patch_detail_coordinates),
    )
    for rel, patch in jobs:
        path = root / rel
        text = _read(path)
        if text is None:
            rel_name = rel.as_posix()
            if rel_name not in missing:
                missing.append(rel_name)
            continue
        updated = patch(text)
        if updated is None or updated == text:
            continue
        _write(path, updated)
        rel_name = rel.as_posix()
        if rel_name not in patched:
            patched.append(rel_name)
    from zeus_dev_helper_mcp.yelp_pages import apply_yelp_pages

    pages = apply_yelp_pages(root)
    for rel in pages["patched"]:
        if rel not in patched:
            patched.append(rel)
    for rel in pages["missing"]:
        if rel not in missing:
            missing.append(rel)
    search_text = _read(root / _SEARCH_PY) or ""
    client_text = _read(root / _CLIENT_TS) or ""
    detail_text = _read(root / _DETAIL_PY) or ""
    live = (
        "chat_req_override=chat_request" in search_text
        and "def fetch_search_chat_request" in search_text
        and 'fetch("/api/search"' in client_text
    )
    coordinates = (
        "def fill_missing_coordinates" in search_text
        and "await fill_missing_coordinates(results)" in search_text
        and "await fill_missing_coordinates([cached])" in detail_text
    )
    return {
        "live_chat_request": live,
        "coordinates": coordinates,
        "business_page": pages["business_page"],
        "review_text": pages["review_text"],
        "search_cards": pages["search_cards"],
        "patched": patched,
        "missing": missing,
        "scope": "yelp-demo/_default",
        "mode": "analytics",
    }
