"""Beer-sample catalog search planner.

Standalone stdlib planner kept for tests and diagnosis. The written beer
sample does not inline it; search there is ``rt.agent.run_turn``. Plans Direct
verbs only: ``find`` or FTS
``search``, then ``get`` of the ``n_*`` ids from that recall. Does not call
Zeus and does not build a ``pipeline``.

``find.query`` matches name and snippet only. A question whose content tokens
are exactly one style or category uses ``where``. Anything else is a name
lookup, then that ``where`` if the name lookup is empty and a facet matched,
then FTS on the content words. The raw question is never ``find.query`` or
``search.query_text``. Empty recall skips ``get``.
"""

import json
import re
from typing import Any

PAGE_CAP = 50
FTS_TIMEOUT_MS = 8000

# Dropped before plural-fold. Generic beer words are dropped after the fold so
# "beers" becomes "beer" and is removed, while "fruits" becomes "fruit" and stays.
FUNCTION_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "and",
        "or",
        "to",
        "in",
        "on",
        "for",
        "with",
        "from",
        "by",
        "at",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "what",
        "which",
        "who",
        "where",
        "when",
        "why",
        "how",
        "made",
        "make",
        "makes",
        "using",
        "use",
        "used",
        "show",
        "list",
        "find",
        "get",
        "give",
        "me",
        "please",
        "any",
        "some",
        "all",
        "that",
        "this",
        "those",
        "these",
        "do",
        "does",
        "did",
        "can",
        "you",
        "i",
        "we",
        "there",
        "about",
        "like",
        "have",
        "has",
        "had",
        "it",
        "its",
        "they",
        "them",
        "my",
        "your",
        "our",
        "not",
        "no",
        "into",
        "onto",
        "over",
        "under",
        "than",
        "then",
        "so",
        "if",
        "but",
    }
)

GENERIC_BEER_WORDS = frozenset({"beer", "ale", "lager", "style", "brew", "brewing"})

QUESTION_STARTS = frozenset(
    {"what", "which", "who", "where", "when", "why", "how", "list", "show", "find"}
)

# Whole-token expansions only. Applied after the plural fold.
ABBREVIATIONS = {
    "ipa": ("india", "pale"),
    "pilsner": ("pilsener",),
    "fruity": ("fruit",),
    "wit": ("white",),
}

_SMALL_WORDS = frozenset({"or", "and", "of", "the", "de"})
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_WS_RE = re.compile(r"\s+")
_SEP_RE = re.compile(r"([-/])")

# Lowercase Brewers Association names stored on beer-sample Beer.style.
_STYLE_LOWER = (
    "aged beer",
    "american rye ale or lager",
    "american-style amber lager",
    "american-style amber/red ale",
    "american-style barley wine ale",
    "american-style brown ale",
    "american-style cream ale or lager",
    "american-style dark lager",
    "american-style ice lager",
    "american-style imperial porter",
    "american-style imperial stout",
    "american-style india black ale",
    "american-style india pale ale",
    "american-style lager",
    "american-style light lager",
    "american-style low-carb light lager",
    "american-style malt liquor",
    "american-style marzen/oktoberfest",
    "american-style pale ale",
    "american-style pilsener",
    "american-style premium lager",
    "american-style sour ale",
    "american-style stout",
    "american-style strong pale ale",
    "american-style wheat wine ale",
    "australasian-style light lager",
    "australasian-style pale ale",
    "baltic-style porter",
    "bamberg-style bock rauchbier",
    "bamberg-style helles rauchbier",
    "bamberg-style marzen",
    "bamberg-style weiss rauchbier",
    "belgian-style blonde ale",
    "belgian-style dark strong ale",
    "belgian-style dubbel",
    "belgian-style flanders/oud bruin",
    "belgian-style fruit lambic",
    "belgian-style gueuze lambic",
    "belgian-style lambic",
    "belgian-style pale ale",
    "belgian-style pale strong ale",
    "belgian-style quadrupel",
    "belgian-style table beer",
    "belgian-style tripel",
    "belgian-style white",
    "berliner-style weisse",
    "bohemian-style pilsener",
    "british-style barley wine ale",
    "british-style imperial stout",
    "brown porter",
    "california common beer",
    "chocolate/cocoa-flavored beer",
    "classic english-style pale ale",
    "classic irish-style dry stout",
    "coffee-flavored beer",
    "dark american wheat ale or lager",
    "dark american-belgo-style ale",
    "dortmunder/european-style export",
    "dry lager",
    "english-style brown ale",
    "english-style dark mild ale",
    "english-style india pale ale",
    "english-style pale mild ale",
    "english-style summer ale",
    "european low-alcohol lager",
    "european-style dark",
    "experimental beer",
    "extra special bitter",
    "field beer",
    "foreign (export)-style stout",
    "french & belgian-style saison",
    "french-style biere de garde",
    "fresh hop ale",
    "fruit beer",
    "fruit wheat ale or lager",
    "german-style brown ale/altbier",
    "german-style doppelbock",
    "german-style eisbock",
    "german-style heller bock/maibock",
    "german-style kolsch",
    "german-style leichtes weizen",
    "german-style marzen",
    "german-style oktoberfest",
    "german-style pilsener",
    "german-style rye ale",
    "german-style schwarzbier",
    "gluten-free beer",
    "golden or blonde ale",
    "herb and spice beer",
    "imperial or double india pale ale",
    "imperial or double red ale",
    "international-style pale ale",
    "international-style pilsener",
    "irish-style red ale",
    "japanese sake-yeast beer",
    "kellerbier - ale",
    "kellerbier - lager",
    "latin american-style light lager",
    "leipzig-style gose",
    "light american wheat ale or lager",
    "munchner-style helles",
    "non-alcoholic beer",
    "oatmeal stout",
    "old ale",
    "ordinary bitter",
    "other belgian-style ales",
    "other strong ale or lager",
    "out of category",
    "pale american-belgo-style ale",
    "porter",
    "pumpkin beer",
    "robust porter",
    "scotch ale",
    "scottish-style export ale",
    "scottish-style heavy ale",
    "scottish-style light ale",
    "session beer",
    "smoke beer",
    "smoke porter",
    "south german-style bernsteinfarbenes weizen",
    "south german-style dunkel weizen",
    "south german-style hefeweizen",
    "south german-style kristal weizen",
    "south german-style weizenbock",
    "special bitter or best bitter",
    "specialty beer",
    "specialty honey lager or ale",
    "specialty stouts",
    "strong ale",
    "sweet stout",
    "traditional german-style bock",
    "tropical-style light lager",
    "vienna-style lager",
    "winter warmer",
    "wood- and barrel-aged beer",
    "wood- and barrel-aged dark beer",
    "wood- and barrel-aged pale to amber beer",
    "wood- and barrel-aged sour beer",
    "wood- and barrel-aged strong beer",
)

# beer-sample Beer.category labels. "and" stays lowercase, matching the bucket.
BEER_CATEGORIES = (
    "Belgian and French Ale",
    "British Ale",
    "German Ale",
    "German Lager",
    "International Ale",
    "International Lager",
    "Irish Ale",
    "North American Ale",
    "North American Lager",
    "Other Lager",
    "Other Style",
)


def _cap_piece(piece: str) -> str:
    if not piece:
        return piece
    if piece.startswith("(") and piece.endswith(")") and len(piece) > 2:
        return "(" + _cap_piece(piece[1:-1]) + ")"
    if piece.startswith("("):
        return "(" + _cap_piece(piece[1:])
    if piece.endswith(")"):
        return _cap_piece(piece[:-1]) + ")"
    if piece.casefold() in _SMALL_WORDS:
        return piece.casefold()
    return piece[0].upper() + piece[1:]


def canonical_label(lower: str) -> str:
    """Title-case a beer-sample style name, keeping hyphen and slash parts."""
    words: list[str] = []
    for word in (lower or "").split(" "):
        parts = _SEP_RE.split(word)
        words.append("".join(part if part in "-/" else _cap_piece(part) for part in parts))
    return " ".join(words)


BEER_STYLES = tuple(canonical_label(name) for name in _STYLE_LOWER)


def tokenize_beer_query(q: str) -> list[str]:
    return _TOKEN_RE.findall((q or "").lower())


def _fold_plural(token: str) -> str:
    if len(token) >= 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def content_tokens(q: str) -> list[str]:
    """Content words: drop function words, fold a trailing s, drop beer generics, expand abbreviations."""
    out: list[str] = []
    for token in tokenize_beer_query(q):
        if token in FUNCTION_WORDS:
            continue
        token = _fold_plural(token)
        if token in FUNCTION_WORDS or token in GENERIC_BEER_WORDS:
            continue
        out.extend(ABBREVIATIONS.get(token, (token,)))
    return out


def _norm_label(text: str) -> str:
    return _WS_RE.sub(" ", (text or "").strip()).casefold()


def _token_key(label: str) -> tuple[str, ...]:
    return tuple(sorted(content_tokens(label)))


def _index_labels(labels: tuple[str, ...]) -> dict[tuple[str, ...], str]:
    grouped: dict[tuple[str, ...], list[str]] = {}
    for label in labels:
        key = _token_key(label)
        if not key:
            continue
        grouped.setdefault(key, []).append(label)
    chosen: dict[tuple[str, ...], str] = {}
    for key, group in grouped.items():
        group.sort(key=lambda label: (len(label), label.casefold()))
        chosen[key] = group[0]
    return chosen


_STYLE_BY_TOKENS = _index_labels(BEER_STYLES)
_CATEGORY_BY_TOKENS = _index_labels(BEER_CATEGORIES)
_STYLE_BY_NORM = {_norm_label(label): label for label in BEER_STYLES}
_CATEGORY_BY_NORM = {_norm_label(label): label for label in BEER_CATEGORIES}


def is_question(q: str) -> bool:
    raw = q or ""
    if "?" in raw:
        return True
    tokens = tokenize_beer_query(raw)
    return bool(tokens) and tokens[0] in QUESTION_STARTS


def normalize_entity(entity: str | None) -> str:
    folded = (entity or "").strip().casefold()
    if folded in {"", "beer"}:
        return "Beer"
    if folded == "brewery":
        return "Brewery"
    text = (entity or "").strip()
    return text or "Beer"


def match_facet(tokens: list[str]) -> dict[str, str] | None:
    """Style wins over category. Partial overlap is not a match."""
    key = tuple(sorted(tokens))
    if not key:
        return None
    style = _STYLE_BY_TOKENS.get(key)
    if style:
        return {"field": "style", "value": style}
    category = _CATEGORY_BY_TOKENS.get(key)
    if category:
        return {"field": "category", "value": category}
    return None


def exact_label_facet(q: str) -> dict[str, str] | None:
    key = _norm_label(q)
    if not key:
        return None
    style = _STYLE_BY_NORM.get(key)
    if style:
        return {"field": "style", "value": style}
    category = _CATEGORY_BY_NORM.get(key)
    if category:
        return {"field": "category", "value": category}
    return None


def _facet_views(facet: dict[str, str] | None) -> tuple[str | None, str | None]:
    if not facet:
        return None, None
    if facet["field"] == "style":
        return facet["value"], None
    if facet["field"] == "category":
        return None, facet["value"]
    return None, None


def plan_beer_query(q: str, entity: str = "Beer") -> dict[str, Any]:
    """Plan one catalog search.

    Immediate ``where`` when the text is a facet label, or when it is a question
    whose content tokens equal exactly one beer facet. Brewery searches never
    use a beer facet. Otherwise the name needle is the raw string, or the
    content words when the text is a question.
    """
    raw = (q or "").strip()
    ent = normalize_entity(entity)
    tokens = content_tokens(raw)
    question = is_question(raw)
    token_facet = match_facet(tokens) if ent == "Beer" else None
    label_facet = exact_label_facet(raw) if ent == "Beer" else None
    fts_query_text = " ".join(tokens)
    where = label_facet or token_facet
    style, category = _facet_views(where)
    plan: dict[str, Any] = {
        "raw": raw,
        "entity": ent,
        "question": question,
        "tokens": tokens,
        "facet": where,
        "style": style,
        "category": category,
        "fts_query_text": fts_query_text,
        "find_query": None,
        "where": where,
        "mode": "empty",
    }
    if not raw:
        return plan
    if ent == "Beer" and (label_facet or (question and token_facet)):
        plan["mode"] = "where"
        plan["where"] = label_facet or token_facet
        plan["facet"] = plan["where"]
        plan["style"], plan["category"] = _facet_views(plan["where"])
        return plan
    needle = fts_query_text if question else raw
    if ent == "Beer" and token_facet and needle:
        plan["mode"] = "name_then_where"
        plan["find_query"] = needle
        plan["where"] = token_facet
        plan["facet"] = token_facet
        plan["style"], plan["category"] = _facet_views(token_facet)
        return plan
    if needle:
        plan["mode"] = "name_then_fts"
        plan["find_query"] = needle
        plan["where"] = None
        plan["facet"] = None
        plan["style"] = None
        plan["category"] = None
        return plan
    if fts_query_text:
        plan["mode"] = "fts"
        return plan
    return plan


def clamp_limit(limit: int | None) -> int:
    try:
        number = int(PAGE_CAP if limit is None else limit)
    except (TypeError, ValueError):
        number = PAGE_CAP
    if number < 1:
        return 1
    if number > PAGE_CAP:
        return PAGE_CAP
    return number


def _find_body(
    *,
    entity: str,
    limit: int,
    where: dict[str, str] | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "entity_type": entity,
        "return": "rows",
        "limit": limit,
    }
    if where:
        body["where"] = {where["field"]: where["value"]}
    if query is not None:
        body["query"] = query
    return body


def _fts_body(*, entity: str, limit: int, query_text: str) -> dict[str, Any]:
    return {
        "strategy": "fts",
        "query_text": query_text,
        "entity_type": entity,
        "limit": limit,
        "timeout_ms": FTS_TIMEOUT_MS,
    }


def search_steps(plan: dict[str, Any], limit: int | None = None) -> list[dict[str, Any]]:
    """Ordered Zeus calls. Stop at the first call that returns rows."""
    lim = clamp_limit(limit if limit is not None else PAGE_CAP)
    ent = str(plan.get("entity") or "Beer")
    mode = plan.get("mode")
    where = plan.get("where") if isinstance(plan.get("where"), dict) else None
    needle = plan.get("find_query")
    fts = str(plan.get("fts_query_text") or "").strip()
    steps: list[dict[str, Any]] = []

    def add_where() -> None:
        if not where:
            return
        steps.append(
            {
                "verb": "find",
                "body": _find_body(entity=ent, limit=lim, where=where),
                "match": {"field": where["field"], "value": where["value"]},
            }
        )

    def add_name() -> None:
        if not needle:
            return
        steps.append(
            {
                "verb": "find",
                "body": _find_body(entity=ent, limit=lim, query=str(needle)),
                "match": {"field": "name", "value": needle},
            }
        )

    def add_fts() -> None:
        if not fts:
            return
        steps.append(
            {
                "verb": "search",
                "body": _fts_body(entity=ent, limit=lim, query_text=fts),
                "match": {"field": "fts", "value": fts},
            }
        )

    if mode == "where":
        add_where()
        add_fts()
    elif mode == "name_then_where":
        add_name()
        add_where()
        add_fts()
    elif mode == "name_then_fts":
        add_name()
        add_fts()
    elif mode == "fts":
        add_fts()
    return steps


def list_find_body(entity: str, limit: int | None = None) -> dict[str, Any]:
    return _find_body(entity=normalize_entity(entity), limit=clamp_limit(limit))


def name_from_doc_key(doc_key: str) -> str:
    """Display name from an FTS doc key suffix (``brewery_id-beer_slug``)."""
    title = (doc_key or "").strip()
    if "::" in title:
        title = title.split("::", 1)[1]
    if "-" in title:
        title = title.rsplit("-", 1)[1]
    pretty = title.replace("_", " ").strip()
    return pretty or (doc_key or "").strip()


def detail_lookup(entity: str, item_id: str) -> dict[str, Any]:
    """``n_*`` and ``file::`` go to ``get``. A doc key is ``find`` ``where.name``."""
    ent = normalize_entity(entity)
    ident = (item_id or "").strip()
    if ident.startswith(("n_", "file::")):
        return {"kind": "get", "body": {"ids": [ident], "include": ["body"]}}
    return {
        "kind": "find",
        "body": _find_body(
            entity=ent,
            limit=1,
            where={"field": "name", "value": name_from_doc_key(ident)},
        ),
    }


def search_lede(
    match: dict[str, Any] | None,
    *,
    entity: str = "Beer",
    truncated: bool = False,
) -> str:
    noun = "breweries" if normalize_entity(entity) == "Brewery" else "beers"
    if not match:
        text = f"No {noun} matched."
    else:
        field = str(match.get("field") or "")
        value = str(match.get("value") or "")
        if field in {"style", "category"}:
            text = f"Showing {noun} whose {field} is {value}."
        elif field == "name":
            text = f"Showing {noun} whose name matches {value}."
        elif field == "fts":
            text = f"Showing {noun} matching {value}."
        else:
            text = f"Showing {noun}."
    if truncated:
        text += " This page is a partial pour."
    return text


def select_beer_get_ids(data: dict[str, Any]) -> list[str]:
    """Public ``n_*`` ids to pass to ``get``.

    Find rows carry those ids. ``file::`` is the internal id and is not the
    catalog handle. Doc-key-only FTS hits return no get ids.
    """
    found: list[str] = []
    items = data.get("items") or data.get("nodes") or []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            node = item.get("node") if isinstance(item.get("node"), dict) else item
            if not isinstance(node, dict):
                continue
            chosen = ""
            for key in ("id", "node_id"):
                candidate = str(node.get(key) or item.get(key) or "").strip()
                if candidate.startswith("n_"):
                    chosen = candidate
                    break
            if chosen:
                found.append(chosen)
    if found:
        return found[:PAGE_CAP]
    raw = data.get("node_ids") or data.get("ids") or []
    if isinstance(raw, list):
        for value in raw:
            text = str(value).strip()
            if text.startswith("n_"):
                found.append(text)
    return found[:PAGE_CAP]


def _items(data: dict[str, Any]) -> list[Any]:
    raw = data.get("items") or data.get("nodes") or []
    return list(raw) if isinstance(raw, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def snippet_doc(node: dict[str, Any]) -> dict[str, Any]:
    """Zeus ``get`` often returns the source document as JSON text on ``snippet``."""
    raw = node.get("snippet")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip().startswith("{"):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def pretty_brewery(value: Any) -> Any:
    if isinstance(value, str) and " " not in value and "_" in value:
        return value.replace("_", " ")
    return value


def _row_shell(item: dict[str, Any]) -> dict[str, Any]:
    node = item.get("node") if isinstance(item.get("node"), dict) else item
    if not isinstance(node, dict):
        node = {}
    doc_key = str(
        node.get("doc_key") or item.get("doc_key") or node.get("source") or item.get("source") or ""
    ).strip()
    return {
        "id": str(node.get("id") or item.get("id") or "").strip(),
        "name": node.get("name") or item.get("name"),
        "doc_key": doc_key or None,
        "type": node.get("type") or item.get("type"),
    }


def card_from_payload(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    node = item.get("node") if isinstance(item.get("node"), dict) else item
    if not isinstance(node, dict):
        return None
    nested = _as_dict(node.get("node"))
    body = _as_dict(node.get("body")) or _as_dict(nested.get("body"))
    meta = _as_dict(node.get("metadata")) or _as_dict(nested.get("metadata"))
    snippet = snippet_doc(node) or snippet_doc(nested) or snippet_doc(item)
    shell = _row_shell(item)
    doc_key = shell.get("doc_key") or first_present(body.get("doc_key"), snippet.get("doc_key"))
    name = first_present(
        body.get("name"),
        body.get("title"),
        shell.get("name"),
        meta.get("name"),
        snippet.get("name"),
    )
    if not name and doc_key:
        name = name_from_doc_key(str(doc_key))
    if not name and shell.get("id"):
        name = shell["id"]
    if not name:
        return None
    nid = str(shell.get("id") or "")
    return {
        "id": nid or doc_key or str(name),
        "name": str(name),
        "style": first_present(body.get("style"), node.get("style"), meta.get("style"), snippet.get("style")),
        "category": first_present(
            body.get("category"), node.get("category"), meta.get("category"), snippet.get("category")
        ),
        "abv": first_present(body.get("abv"), node.get("abv"), meta.get("abv"), snippet.get("abv")),
        "ibu": first_present(body.get("ibu"), node.get("ibu"), meta.get("ibu"), snippet.get("ibu")),
        "srm": first_present(body.get("srm"), node.get("srm"), snippet.get("srm")),
        "description": first_present(
            body.get("description"),
            body.get("desc"),
            node.get("description"),
            snippet.get("description"),
        ),
        "brewery": pretty_brewery(
            first_present(
                body.get("brewery"),
                body.get("brewery_id"),
                node.get("brewery"),
                meta.get("brewery_id"),
                snippet.get("brewery"),
                snippet.get("brewery_id"),
            )
        ),
        "doc_key": doc_key or None,
        "source": "get" if nid.startswith("n_") else "find",
    }


def _merge_card(shell: dict[str, Any], got: dict[str, Any] | None) -> dict[str, Any]:
    hydrated = got or {}
    nid = str(shell.get("id") or hydrated.get("id") or "")
    return {
        "id": nid,
        "name": hydrated.get("name") or shell.get("name"),
        "style": hydrated.get("style"),
        "category": hydrated.get("category"),
        "abv": hydrated.get("abv"),
        "ibu": hydrated.get("ibu"),
        "srm": hydrated.get("srm"),
        "description": hydrated.get("description"),
        "brewery": hydrated.get("brewery"),
        "doc_key": hydrated.get("doc_key") or shell.get("doc_key"),
        "source": "get" if nid.startswith("n_") else (hydrated.get("source") or "find"),
    }


def hydrate_cards(find_data: dict[str, Any], get_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Attach ``get`` fields onto find rows and keep each row's ``n_*`` id."""
    shells = [_row_shell(item) for item in _items(find_data) if isinstance(item, dict)]
    shells = [shell for shell in shells if shell.get("id") or shell.get("name")]
    got = [card for item in _items(get_data) if (card := card_from_payload(item))]
    by_id = {card["id"]: card for card in got if card.get("id")}
    if shells and got and len(shells) == len(got):
        return [_merge_card(shell, card) for shell, card in zip(shells, got)]
    if shells:
        return [_merge_card(shell, by_id.get(str(shell.get("id") or ""))) for shell in shells]
    return got


def cards_from_doc_keys(data: dict[str, Any]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for item in _items(data):
        if not isinstance(item, dict):
            continue
        node = item.get("node") if isinstance(item.get("node"), dict) else item
        if not isinstance(node, dict):
            continue
        nid = str(node.get("id") or item.get("id") or "").strip()
        doc_key = str(node.get("doc_key") or item.get("doc_key") or "").strip()
        if not doc_key or nid.startswith("n_"):
            continue
        cards.append(
            {
                "id": doc_key,
                "name": name_from_doc_key(doc_key),
                "doc_key": doc_key,
                "style": None,
                "category": None,
                "abv": None,
                "ibu": None,
                "srm": None,
                "description": None,
                "brewery": None,
                "source": "doc_key",
            }
        )
    return cards


def result_truncated(data: dict[str, Any]) -> bool:
    return bool(data.get("truncated"))


def result_partial(data: dict[str, Any]) -> bool:
    if str(data.get("status") or "").lower() == "partial":
        return True
    missing = data.get("missing_node_ids")
    return isinstance(missing, list) and len(missing) > 0


def step_path(step: dict[str, Any]) -> str:
    body = step.get("body") if isinstance(step.get("body"), dict) else {}
    if step.get("verb") == "find" and isinstance(body.get("where"), dict) and body["where"]:
        field, value = next(iter(body["where"].items()))
        return f"find:where.{field}={value}"
    if step.get("verb") == "find":
        return f"find:query={body.get('query')}"
    return f"search:fts={body.get('query_text')}"


def get_body(ids: list[str]) -> dict[str, Any]:
    """Hydrate known ``n_*`` ids. Direct ``get`` — never a ``pipeline`` step."""
    return {"ids": list(ids), "include": ["body"]}


def _public_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": plan.get("mode"),
        "tokens": plan.get("tokens") or [],
        "question": bool(plan.get("question")),
        "find_query": plan.get("find_query"),
        "fts_query_text": plan.get("fts_query_text") or "",
        "where": plan.get("where"),
    }


def _done(
    base: dict[str, Any],
    path: list[str],
    items: list[dict[str, Any]],
    match: dict[str, Any] | None,
    truncated: bool,
    partial: bool,
    entity: str,
) -> dict[str, Any]:
    out = dict(base)
    out["items"] = items
    out["cards"] = items
    out["match"] = match
    out["truncated"] = truncated
    out["partial"] = partial
    out["path"] = path
    out["lede"] = search_lede(match, entity=entity, truncated=truncated)
    return out


async def _recall_then_get(
    fetch: Any, verb: str, body: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """One Direct recall. ``get`` runs only when the recall returned ``n_*`` ids."""
    found = await fetch(verb, body)
    if not isinstance(found, dict):
        found = {}
    ids = select_beer_get_ids(found)
    if not ids:
        return found, {}, ids
    rows = await fetch("get", get_body(ids))
    if not isinstance(rows, dict):
        rows = {}
    return found, rows, ids


async def execute_search(plan: dict[str, Any], limit: int | None, fetch: Any) -> dict[str, Any]:
    """Run the plan as Direct ``find`` / ``search`` / ``get``. No pipeline verb."""
    ent = str(plan.get("entity") or "Beer")
    steps = search_steps(plan, limit)
    path = [f"plan:{plan.get('mode') or 'empty'}"]
    base = {
        "ok": True,
        "query": plan.get("raw") or "",
        "entity": ent,
        "items": [],
        "cards": [],
        "match": None,
        "truncated": False,
        "partial": False,
        "path": path,
        "plan": _public_plan(plan),
        "lede": search_lede(None, entity=ent),
    }
    if not steps:
        return base
    for index, step in enumerate(steps):
        verb = str(step["verb"])
        found, rows, ids = await _recall_then_get(fetch, verb, step["body"])
        path.append(step_path(step))
        if verb == "find":
            if not ids:
                path.append("skip_get")
                if index < len(steps) - 1:
                    continue
                base["path"] = path
                return base
            path.append("get")
            items = hydrate_cards(found, rows)
            return _done(
                base,
                path,
                items,
                step.get("match"),
                result_truncated(found),
                result_partial(rows),
                ent,
            )
        partial = False
        if ids:
            path.append("get")
            items = hydrate_cards(found, rows)
            partial = result_partial(rows)
        else:
            items = cards_from_doc_keys(found)
            if items:
                path.append("doc_key")
            else:
                path.append("skip_get")
        if items or index == len(steps) - 1:
            match = step.get("match") if items else None
            return _done(base, path, items, match, result_truncated(found), partial, ent)
    base["path"] = path
    return base


async def execute_list(entity: str, limit: int | None, fetch: Any) -> dict[str, Any]:
    ent = normalize_entity(entity)
    body = list_find_body(ent, limit)
    found, rows, ids = await _recall_then_get(fetch, "find", body)
    partial = False
    if ids:
        items = hydrate_cards(found, rows)
        partial = result_partial(rows)
    else:
        items = []
    return {
        "ok": True,
        "entity": ent,
        "items": items,
        "truncated": result_truncated(found),
        "partial": partial,
    }


async def execute_detail(entity: str, item_id: str, fetch: Any) -> dict[str, Any]:
    look = detail_lookup(entity, item_id)
    partial = False
    if look["kind"] == "get":
        data = await fetch("get", look["body"])
        if not isinstance(data, dict):
            data = {}
        partial = result_partial(data)
        items = [card for item in _items(data) if (card := card_from_payload(item))]
        requested = (look["body"].get("ids") or [None])[0]
        if items and requested and str(requested).startswith("n_"):
            items[0]["id"] = requested
    else:
        found, rows, ids = await _recall_then_get(fetch, "find", look["body"])
        if not ids:
            return {"ok": False, "error": "not_found"}
        partial = result_partial(rows)
        items = hydrate_cards(found, rows)
    if not items:
        return {"ok": False, "error": "not_found"}
    return {"ok": True, "item": items[0], "partial": partial}
