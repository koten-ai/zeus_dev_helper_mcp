"""Business page and search-card fixes applied with the yelp live-search patch.

A stock LocalAI checkout searches a bundled catalog for ``/business/{id}`` and
renders a graph ``rev:`` key when the review body did not come back. use_sample
applies this so the next yelp-demo app matches the working checkout:

- search cards keep a nested Zeus ``node`` and a pipeline ``data.rows`` envelope
- ``/business/{id}`` loads ``GET /api/business/{id}`` when the id is not in the
  bundled catalog
- review text is the Couchbase source document, not the ``rev:`` doc key
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_CLIENT = Path("frontend/src/api/client.ts")
_DETAIL = Path("src/local_guide/detail.py")
_RESULTS = Path("src/local_guide/results_parser.py")
_ANSWER = Path("src/local_guide/answer_parser.py")

_OLD_CLIENT = '''export async function fetchBusiness(businessId: string) {
  await delay(180);
  const business = findBusiness(businessId);
  if (!business) throw new Error("Business not found");
  return { business };
}

export async function fetchReviews(businessId: string, limit = 20): Promise<ReviewsResponse> {
  const empty: ReviewsResponse = {
    business_id: businessId,
    reviews: [],
    count: 0,
    source: "sample",
  };
  try {
    await delay(160);
    const business = findBusiness(businessId);
    if (!business) return { ...empty, source: "empty" };
    const reviews = reviewsFor(business).slice(0, Math.max(1, Math.min(limit, 50)));
    return {
      business_id: business.business_id || businessId,
      reviews,
      count: reviews.length,
      source: "sample",
      error: null,
    };
  } catch (e) {
    return {
      ...empty,
      source: "error",
      error: e instanceof Error ? e.message : String(e),
    };
  }
}

export async function fetchInsight(businessId: string): Promise<InsightResponse> {
  await delay(280);
  const business = findBusiness(businessId);
  if (!business) {
    return {
      business_id: businessId,
      summary: "",
      the_good: [],
      the_bad: [],
      best_for: [],
      reviews: [],
      error: "Business not found",
    };
  }
  return insightFor(business);
}
'''

_NEW_CLIENT = '''function requestedId(businessId: string): string {
  return decodeURIComponent(businessId || "").trim();
}

/** Zeus detail returns a named card. A miss is a placeholder whose name is the id. */
function isLiveBusiness(card: BusinessCard | null | undefined, id: string): card is BusinessCard {
  if (!card || typeof card.name !== "string") return false;
  const name = card.name.trim();
  if (!name || name === id || name === `biz:${id}`) return false;
  return true;
}

async function readJson(url: string, init?: RequestInit): Promise<{ ok: boolean; data: Record<string, unknown> }> {
  const res = await fetch(url, init);
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  return { ok: res.ok, data };
}

export async function fetchBusiness(businessId: string) {
  const id = requestedId(businessId);
  const local = findBusiness(id);
  if (local) return { business: local };
  try {
    const { ok, data } = await readJson(`/api/business/${encodeURIComponent(id)}`);
    const card = data.business as BusinessCard | undefined;
    if (ok && isLiveBusiness(card, id)) return { business: card };
  } catch {
    // Leave the not-found error below when Zeus is unreachable.
  }
  throw new Error("Business not found");
}

export async function fetchReviews(businessId: string, limit = 20): Promise<ReviewsResponse> {
  const id = requestedId(businessId);
  const empty: ReviewsResponse = {
    business_id: id,
    reviews: [],
    count: 0,
    source: "sample",
  };
  const local = findBusiness(id);
  if (local) {
    try {
      await delay(160);
      const reviews = reviewsFor(local).slice(0, Math.max(1, Math.min(limit, 50)));
      return {
        business_id: local.business_id || id,
        reviews,
        count: reviews.length,
        source: "sample",
        error: null,
      };
    } catch (e) {
      return {
        ...empty,
        source: "error",
        error: e instanceof Error ? e.message : String(e),
      };
    }
  }
  try {
    const cap = Math.max(1, Math.min(limit, 50));
    const { ok, data } = await readJson(
      `/api/business/${encodeURIComponent(id)}/reviews?limit=${cap}`
    );
    const reviews = Array.isArray(data.reviews) ? (data.reviews as ReviewItem[]) : [];
    if (!ok) {
      return {
        ...empty,
        source: "error",
        error: typeof data.error === "string" ? data.error : "reviews failed",
      };
    }
    return {
      business_id: typeof data.business_id === "string" ? data.business_id : id,
      reviews,
      count: typeof data.count === "number" ? data.count : reviews.length,
      source: typeof data.source === "string" ? data.source : "zeus",
      error: null,
    };
  } catch (e) {
    return {
      ...empty,
      source: "error",
      error: e instanceof Error ? e.message : String(e),
    };
  }
}

export async function fetchInsight(businessId: string): Promise<InsightResponse> {
  const id = requestedId(businessId);
  const local = findBusiness(id);
  if (local) {
    await delay(280);
    return insightFor(local);
  }
  try {
    const { ok, data } = await readJson(`/api/business/${encodeURIComponent(id)}/insight`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "{}",
    });
    const reviews = Array.isArray(data.reviews) ? (data.reviews as ReviewItem[]) : [];
    const asList = (value: unknown): string[] =>
      Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
    const insight: InsightResponse = {
      business_id: typeof data.business_id === "string" ? data.business_id : id,
      business: isLiveBusiness(data.business as BusinessCard | undefined, id)
        ? (data.business as BusinessCard)
        : null,
      summary: typeof data.summary === "string" ? data.summary : "",
      the_good: asList(data.the_good),
      the_bad: asList(data.the_bad),
      best_for: asList(data.best_for),
      reviews,
      error: typeof data.error === "string" ? data.error : undefined,
    };
    if (!ok && !insight.error) insight.error = "insight failed";
    return insight;
  } catch (e) {
    return {
      business_id: id,
      summary: "",
      the_good: [],
      the_bad: [],
      best_for: [],
      reviews: [],
      error: e instanceof Error ? e.message : String(e),
    };
  }
}
'''

_OLD_NORMALIZE = '''def _normalize_row(row: Any) -> dict[str, str] | None:
    if not isinstance(row, dict):
        return None

    # Skip pure review rows for card list (unless they carry a business name)
    et = str(row.get("entity_type") or "").lower()
'''

_NEW_NORMALIZE = '''def _prefer_nested_node(row: dict[str, Any]) -> dict[str, Any]:
    """Hybrid hits are ``{node: {name, doc_key, ...}, score}``."""
    node = row.get("node")
    if not isinstance(node, dict) or _first_str(row, NAME_KEYS):
        return row
    merged = dict(node)
    for key, val in row.items():
        if key in {"node", "score"}:
            continue
        if merged.get(key) in (None, "", "null"):
            merged[key] = val
    return merged


def _normalize_row(row: Any) -> dict[str, str] | None:
    if not isinstance(row, dict):
        return None
    if row.get("missing") is True:
        return None
    row = _prefer_nested_node(row)

    # Skip pure review rows for card list (unless they carry a business name)
    et = str(row.get("entity_type") or row.get("type") or "").lower()
'''

_OLD_COLLECT = '''def _collect_arrays(obj: Any, found: list) -> None:
    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                found.append(item)
        return
    if not isinstance(obj, dict):
        return
    for key in ("rows", "items", "results", "data", "businesses", "matches", "nodes"):
        val = obj.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    found.append(item)
    for key in ("return", "output"):
        val = obj.get(key)
        if isinstance(val, dict):
            _collect_arrays(val, found)
        elif isinstance(val, list):
            _collect_arrays(val, found)
    steps = obj.get("steps")
    if isinstance(steps, dict):
        for step_val in steps.values():
            if isinstance(step_val, dict):
                _collect_arrays(step_val, found)
'''

_NEW_COLLECT = '''def _collect_arrays(obj: Any, found: list, _depth: int = 0) -> None:
    """Collect row dicts from Zeus tool payloads.

    Live envelopes nest the rows: ``{result: {items|rows}}`` and pipeline
    ``{data: {rows: {rows: [...]}}}``. Dict-valued containers are walked;
    list items are the candidate rows (hybrid ``node`` unwrap happens later).
    """
    if _depth > 8:
        return
    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                found.append(item)
        return
    if not isinstance(obj, dict):
        return
    for key in ("rows", "items", "results", "data", "businesses", "matches", "nodes"):
        val = obj.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    found.append(item)
        elif isinstance(val, dict):
            _collect_arrays(val, found, _depth + 1)
    for key in ("return", "output", "result"):
        val = obj.get(key)
        if isinstance(val, (dict, list)):
            _collect_arrays(val, found, _depth + 1)
    steps = obj.get("steps")
    if isinstance(steps, dict):
        for step_val in steps.values():
            if isinstance(step_val, dict):
                _collect_arrays(step_val, found, _depth + 1)
    elif isinstance(steps, list):
        _collect_arrays(steps, found, _depth + 1)
'''

_OLD_NUMBERED = '_NUMBERED_ITEM = re.compile(r"^\\d+\\.\\s+\\*\\*(.+?)\\*\\*\\s*$", re.MULTILINE)\n'
_NEW_NUMBERED = '''# Bold names (``1. **Oggi**``) or a short plain name (``1. Oggi Italian``).
# Plain lines longer than 80 characters are sentences, not business titles.
_NUMBERED_ITEM = re.compile(
    r"^\\d+\\.\\s+(?:\\*\\*(.+?)\\*\\*|([^\\n*]{1,80}?))\\s*$",
    re.MULTILINE,
)
'''

_OLD_ITEM_NAME = '        parsed = _parse_item_block(match.group(1) + "\\n" + body[start:end])\n'
_NEW_ITEM_NAME = (
    '        name = (match.group(1) if match.group(1) is not None else match.group(2)) or ""\n'
    '        parsed = _parse_item_block(name.strip() + "\\n" + body[start:end])\n'
)

_SOURCE_KEY_FN = '''
def _looks_like_source_key(value: str) -> bool:
    """True for graph doc keys such as ``rev:yelp:<id>``, which are not review text."""
    s = (value or "").strip()
    if not s or " " in s:
        return False
    head, _, tail = s.partition(":")
    if head in {"rev", "biz", "user", "tip", "checkin"} and tail:
        return True
    return False


'''

_QUERY_FN = '''def _query_on_zeus_host(cb, zeus_url: str):
    """Use the Zeus host query port when config points at loopback.

    config.example.json uses host.docker.internal:8093, which becomes
    127.0.0.1 outside Docker. Review text is on the cluster that serves ZEUS_URL.
    """
    if cb is None:
        return None
    from urllib.parse import urlparse

    host = (urlparse(getattr(cb, "query_url", "") or "").hostname or "").lower()
    zeus_host = (urlparse(zeus_url or "").hostname or "").lower()
    loopback = {"127.0.0.1", "localhost", "::1", "host.docker.internal"}
    if host not in loopback or not zeus_host or zeus_host in loopback:
        return cb
    try:
        from dataclasses import replace

        return replace(cb, query_url=f"http://{zeus_host}:8093")
    except TypeError:
        return cb


'''

_OLD_AUTHOR = '''    # Opaque Yelp ids are not display names when User join missed.
    if not display_name and _looks_like_yelp_opaque_id(author):
        author = "Reviewer"
'''

_NEW_AUTHOR = '''    # Opaque Yelp ids and source keys are not display names when User join missed.
    if not display_name and (
        _looks_like_yelp_opaque_id(author) or _looks_like_source_key(author)
    ):
        author = "Reviewer"
'''

_OLD_CB = '''    cb = CouchbaseQueryConfig.from_mapping(
        cb_raw,
        zeus_url=zeus_url,
        allow_host_default=False,
    )
'''

_NEW_CB = '''    cb = _query_on_zeus_host(
        CouchbaseQueryConfig.from_mapping(
            cb_raw,
            zeus_url=zeus_url,
            allow_host_default=False,
        ),
        zeus_url,
    )
'''


def _read(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _patch_client(text: str) -> str | None:
    if "function isLiveBusiness" in text and "/api/business/" in text:
        return None
    if _OLD_CLIENT not in text:
        return None
    return text.replace(_OLD_CLIENT, _NEW_CLIENT, 1)


def _patch_results(text: str) -> str | None:
    if "_prefer_nested_node" in text and '"result"' in text and "_depth" in text:
        return None
    updated = text
    if _OLD_NORMALIZE in updated:
        updated = updated.replace(_OLD_NORMALIZE, _NEW_NORMALIZE, 1)
    if _OLD_COLLECT in updated:
        updated = updated.replace(_OLD_COLLECT, _NEW_COLLECT, 1)
    if updated == text:
        return None
    return updated


def _patch_answer(text: str) -> str | None:
    if "([^\\n*]{1,80}?)" in text and "match.group(2)" in text:
        return None
    updated = text
    if _OLD_NUMBERED in updated:
        updated = updated.replace(_OLD_NUMBERED, _NEW_NUMBERED, 1)
    if _OLD_ITEM_NAME in updated:
        updated = updated.replace(_OLD_ITEM_NAME, _NEW_ITEM_NAME, 1)
    if updated == text:
        return None
    return updated


def _patch_detail(text: str) -> str | None:
    updated = text
    if "_N1QL_TIMEOUT_S" not in updated and "MAX_REVIEW_LIMIT = 50\n" in updated:
        updated = updated.replace(
            "MAX_REVIEW_LIMIT = 50\n",
            "MAX_REVIEW_LIMIT = 50\n"
            "# mDNS to the Zeus host query port often exceeds the client default of 3s.\n"
            "_N1QL_TIMEOUT_S = 15.0\n",
            1,
        )
    if "_looks_like_source_key" not in updated and "def _user_lookup_keys(" in updated:
        updated = updated.replace("def _user_lookup_keys(", _SOURCE_KEY_FN + "def _user_lookup_keys(", 1)
    if "_looks_like_source_key(text)" not in updated:
        needle = '    text = _str_field(row.get("text") or row.get("description"))\n'
        if needle in updated:
            updated = updated.replace(
                needle,
                needle + "    if _looks_like_source_key(text):\n        text = \"\"\n",
                1,
            )
    if _OLD_AUTHOR in updated:
        updated = updated.replace(_OLD_AUTHOR, _NEW_AUTHOR, 1)
    for fields in ("_REVIEW_N1QL_FIELDS", "_USER_N1QL_FIELDS", "_BUSINESS_N1QL_FIELDS"):
        needle = f"                fields={fields},\n            )"
        repl = f"                fields={fields},\n                timeout_s=_N1QL_TIMEOUT_S,\n            )"
        if needle in updated:
            updated = updated.replace(needle, repl, 1)
    if "def _query_on_zeus_host" not in updated and "async def fetch_business_reviews(" in updated:
        updated = updated.replace(
            "async def fetch_business_reviews(",
            _QUERY_FN + "async def fetch_business_reviews(",
            1,
        )
    if _OLD_CB in updated:
        updated = updated.replace(_OLD_CB, _NEW_CB)
    if updated == text:
        return None
    return updated


def apply_yelp_pages(root: Path) -> dict[str, Any]:
    """Wire the business page and the search cards that link to it.

    Idempotent. Files that are already patched, or that are not the LocalAI
    template, are left unchanged.
    """
    root = root.expanduser().resolve()
    patched: list[str] = []
    missing: list[str] = []
    jobs = (
        (_CLIENT, _patch_client),
        (_DETAIL, _patch_detail),
        (_RESULTS, _patch_results),
        (_ANSWER, _patch_answer),
    )
    for rel, patch in jobs:
        path = root / rel
        text = _read(path)
        if text is None:
            missing.append(rel.as_posix())
            continue
        updated = patch(text)
        if updated is None or updated == text:
            continue
        _write(path, updated)
        patched.append(rel.as_posix())
    client = _read(root / _CLIENT) or ""
    detail = _read(root / _DETAIL) or ""
    results = _read(root / _RESULTS) or ""
    answer = _read(root / _ANSWER) or ""
    return {
        "patched": patched,
        "missing": missing,
        "business_page": "function isLiveBusiness" in client and "/api/business/" in client,
        "review_text": (
            "_looks_like_source_key" in detail
            and "_N1QL_TIMEOUT_S" in detail
            and "def _query_on_zeus_host" in detail
        ),
        "search_cards": "_prefer_nested_node" in results and "match.group(2)" in answer,
    }
