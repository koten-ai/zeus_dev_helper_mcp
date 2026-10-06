"""Behavior of the business-page and search-card patch use_sample writes.

The clone test checks that the LocalAI files are edited. These tests load the
patched Python and run it: hybrid card unwrap, nested pipeline rows, review
text that is a doc key, and a loopback query URL.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.explain import explain_topic
from zeus_dev_helper_mcp.yelp_pages import _OLD_CLIENT, apply_yelp_pages

RESULTS_PY = """from typing import Any

NAME_KEYS = ("name", "business_name", "title")


def _first_str(row: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        val = row.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _normalize_row(row: Any) -> dict[str, str] | None:
    if not isinstance(row, dict):
        return None

    # Skip pure review rows for card list (unless they carry a business name)
    et = str(row.get("entity_type") or "").lower()
    return {"entity_type": et, "name": _first_str(row, NAME_KEYS)}


def _collect_arrays(obj: Any, found: list) -> None:
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
"""

DETAIL_PY = """MAX_REVIEW_LIMIT = 50


def _str_field(value: object) -> str:
    return "" if value is None else str(value)


def _looks_like_yelp_opaque_id(author: str) -> bool:
    return author == "opaque-id"


def _user_lookup_keys(user_ids: list[str]) -> list[str]:
    return []


def _review_row_to_ui(row: dict) -> dict[str, str]:
    text = _str_field(row.get("text") or row.get("description"))
    author = str(row.get("author") or "")
    display_name = str(row.get("display_name") or "")
    # Opaque Yelp ids are not display names when User join missed.
    if not display_name and _looks_like_yelp_opaque_id(author):
        author = "Reviewer"
    return {"text": text, "author": author}


async def fetch_business_reviews(
):
    cb = CouchbaseQueryConfig.from_mapping(
        cb_raw,
        zeus_url=zeus_url,
        allow_host_default=False,
    )
    rows = await n1ql_hydrate_keys(
                cb,
                bucket,
                scope,
                collection,
                doc_keys[:lim],
                fields=_REVIEW_N1QL_FIELDS,
            )
    return rows
"""

ANSWER_PY = r"""import re

_NUMBERED_ITEM = re.compile(r"^\d+\.\s+\*\*(.+?)\*\*\s*$", re.MULTILINE)


def _parse_item_block(text: str) -> str:
    return text.split("\n", 1)[0]


def parse_names(body: str) -> list[str]:
    matches = list(_NUMBERED_ITEM.finditer(body))
    found: list[str] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        parsed = _parse_item_block(match.group(1) + "\n" + body[start:end])
        found.append(parsed)
    return found
"""


def _load(path: Path) -> dict:
    namespace: dict = {"__name__": "yelp_under_test"}
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)  # noqa: S102
    return namespace


def _patched(tmp_path: Path) -> dict[str, dict]:
    root = tmp_path / "demo_yelp"
    client = root / "frontend" / "src" / "api"
    client.mkdir(parents=True)
    (client / "client.ts").write_text(_OLD_CLIENT, encoding="utf-8")
    guide = root / "src" / "local_guide"
    guide.mkdir(parents=True)
    (guide / "results_parser.py").write_text(RESULTS_PY, encoding="utf-8")
    (guide / "detail.py").write_text(DETAIL_PY, encoding="utf-8")
    (guide / "answer_parser.py").write_text(ANSWER_PY, encoding="utf-8")
    report = apply_yelp_pages(root)
    assert report["patched"] == [
        "frontend/src/api/client.ts",
        "src/local_guide/detail.py",
        "src/local_guide/results_parser.py",
        "src/local_guide/answer_parser.py",
    ]
    assert report["business_page"] is True
    assert report["review_text"] is True
    assert report["search_cards"] is True
    assert apply_yelp_pages(root)["patched"] == []
    return {
        "results": _load(guide / "results_parser.py"),
        "detail": _load(guide / "detail.py"),
        "answer": _load(guide / "answer_parser.py"),
    }


def test_apply_pages_reports_missing_files(tmp_path: Path) -> None:
    report = apply_yelp_pages(tmp_path)
    assert report["patched"] == []
    assert report["missing"] == [
        "frontend/src/api/client.ts",
        "src/local_guide/detail.py",
        "src/local_guide/results_parser.py",
        "src/local_guide/answer_parser.py",
    ]
    assert report["business_page"] is False
    assert report["review_text"] is False
    assert report["search_cards"] is False


def test_apply_pages_leaves_unrecognized_files(tmp_path: Path) -> None:
    root = tmp_path / "demo_yelp"
    client = root / "frontend" / "src" / "api"
    client.mkdir(parents=True)
    (client / "client.ts").write_text("export const ready = true;\n", encoding="utf-8")
    guide = root / "src" / "local_guide"
    guide.mkdir(parents=True)
    for name in ("detail.py", "results_parser.py", "answer_parser.py"):
        (guide / name).write_text(f"# {name} custom\n", encoding="utf-8")
    report = apply_yelp_pages(root)
    assert report["patched"] == []
    assert report["missing"] == []
    assert report["business_page"] is False
    assert (client / "client.ts").read_text(
        encoding="utf-8"
    ) == "export const ready = true;\n"
    assert (guide / "detail.py").read_text(encoding="utf-8") == "# detail.py custom\n"


def test_patched_cards_unwrap_hybrid_node_and_nested_rows(tmp_path: Path) -> None:
    results = _patched(tmp_path)["results"]
    normalize = results["_normalize_row"]
    prefer = results["_prefer_nested_node"]
    collect = results["_collect_arrays"]

    hybrid = {
        "node": {"name": "Oggi", "doc_key": "biz:1", "city": ""},
        "score": 0.9,
        "city": "Austin",
    }
    unwrapped = prefer(hybrid)
    assert unwrapped["name"] == "Oggi"
    assert unwrapped["doc_key"] == "biz:1"
    assert unwrapped["city"] == "Austin"
    assert "score" not in unwrapped
    assert "node" not in unwrapped
    assert prefer({"name": "Outer", "node": {"name": "Inner"}})["name"] == "Outer"
    assert prefer({"node": ["nope"], "name": ""}) == {"node": ["nope"], "name": ""}

    assert normalize("nope") is None
    assert normalize({"missing": True, "node": {"name": "Hidden"}}) is None
    assert normalize(hybrid) == {"entity_type": "", "name": "Oggi"}
    assert normalize({"type": "Business", "name": "Cafe"}) == {
        "entity_type": "business",
        "name": "Cafe",
    }
    assert normalize({"name": "Outer", "node": {"name": "Inner"}})["name"] == "Outer"

    payload = {
        "data": {"rows": {"rows": [hybrid, {"missing": True}, "skip"]}},
        "result": {"items": [{"name": "FromResult"}]},
        "steps": [{"name": "StepCard"}],
    }
    found: list = []
    collect(payload, found)
    names = [normalize(row)["name"] for row in found if normalize(row)]
    assert names == ["Oggi", "FromResult", "StepCard"]

    deep = {"rows": [{"name": "Leaf"}]}
    for _ in range(8):
        deep = {"data": deep}
    found = []
    collect(deep, found)
    assert [row["name"] for row in found] == ["Leaf"]
    deeper = {"data": deep}
    found = []
    collect(deeper, found)
    assert found == []


def test_patched_review_text_and_loopback_query_host(tmp_path: Path) -> None:
    detail = _patched(tmp_path)["detail"]
    review = detail["_review_row_to_ui"]
    source_key = detail["_looks_like_source_key"]
    query_host = detail["_query_on_zeus_host"]

    assert review({"text": "Great tacos", "author": "Jane"}) == {
        "text": "Great tacos",
        "author": "Jane",
    }
    assert review({"text": "rev:yelp:abc", "author": "Jane"}) == {
        "text": "",
        "author": "Jane",
    }
    dropped = review({"description": "biz:xyz", "author": "biz:xyz"})
    assert dropped == {"text": "", "author": "Reviewer"}
    assert review({"text": "Nice", "author": "opaque-id"})["author"] == "Reviewer"
    kept = review({"text": "Nice", "author": "rev:yelp:1", "display_name": "Ada"})
    assert kept["author"] == "rev:yelp:1"
    assert kept["text"] == "Nice"

    for key in (
        "rev:yelp:abc",
        "biz:1",
        "user:1",
        "tip:1",
        "checkin:1",
        "  rev:yelp:abc  ",
    ):
        assert source_key(key) is True
    for key in (
        "",
        "really good tacos",
        "rev:",
        "Rev:yelp:1",
        "other:1",
        "rev:yelp:has space",
    ):
        assert source_key(key) is False

    @dataclass
    class QueryConfig:
        query_url: str

    original = QueryConfig("http://127.0.0.1:8093")
    moved = query_host(original, "https://zeus.example:8080/v1")
    assert moved.query_url == "http://zeus.example:8093"
    assert original.query_url == "http://127.0.0.1:8093"
    for query_url in (
        "http://localhost:8093",
        "http://host.docker.internal:8093",
        "http://[::1]:8093",
        "http://LocalHost:8093/query",
    ):
        assert query_host(QueryConfig(query_url), "https://Zeus.Example").query_url == (
            "http://zeus.example:8093"
        )
    remote = QueryConfig("http://cb.internal:8093")
    assert (
        query_host(remote, "https://zeus.example").query_url
        == "http://cb.internal:8093"
    )
    loopback = QueryConfig("http://127.0.0.1:8093")
    assert query_host(loopback, "http://localhost:8080") is loopback
    assert query_host(loopback, "") is loopback
    assert query_host(None, "https://zeus.example") is None

    class Bag:
        def __init__(self) -> None:
            self.query_url = "http://127.0.0.1:8093"

    bag = Bag()
    assert query_host(bag, "https://zeus.example") is bag


def test_patched_answer_accepts_a_short_plain_name(tmp_path: Path) -> None:
    parse_names = _patched(tmp_path)["answer"]["parse_names"]
    sentence = "This is a sentence about dinner. " * 5
    body = "\n".join(
        [
            "1. **Oggi**",
            "pasta",
            "2. Cafe Luna",
            "coffee",
            f"3. {sentence}",
            "4. A * B",
            "5. **Noodle House**",
        ]
    )
    assert parse_names(body) == ["Oggi", "Cafe Luna", "Noodle House"]
    assert parse_names("1. " + ("A" * 80)) == ["A" * 80]
    assert parse_names("1. " + ("A" * 81)) == []
    assert parse_names("") == []


def test_demo_yelp_topic_describes_pages_and_photos(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    topic = explain_topic(HelperConfig(state_dir=tmp_path / "state"), "demo_yelp")
    summary = topic["summary"]
    assert topic["found"] is True
    assert "/api/business/{id}" in summary
    assert "rev:" in summary
    assert "hybrid node" in summary
    assert "frontend/public/business-images/<id>/{1,2,3}.png" in summary
    assert "no API key" in summary
