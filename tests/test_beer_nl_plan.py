"""Beer Direct catalog planner: style/category where, name lookup, FTS tokens."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from zeus_dev_helper_mcp.beer import write_beer_sample
from zeus_dev_helper_mcp.beer_plan import (
    FUNCTION_WORDS,
    content_tokens,
    detail_lookup,
    execute_detail,
    execute_list,
    execute_search,
    list_find_body,
    plan_beer_query,
    search_steps,
    select_beer_get_ids,
)
from zeus_dev_helper_mcp.config import HelperConfig

FRUIT_Q = "What beers are made from fruits?"


def _bodies(plan: dict) -> str:
    return json.dumps(search_steps(plan))


def test_plan_fruit_question_is_style_where() -> None:
    plan = plan_beer_query(FRUIT_Q)
    assert plan["mode"] == "where"
    assert plan["question"] is True
    assert plan["tokens"] == ["fruit"]
    assert plan["style"] == "Fruit Beer"
    assert plan["where"] == {"field": "style", "value": "Fruit Beer"}
    assert plan["find_query"] is None
    assert plan["fts_query_text"] == "fruit"
    assert "what" in FUNCTION_WORDS
    assert "made" in FUNCTION_WORDS
    assert "from" in FUNCTION_WORDS
    assert "beers" not in FUNCTION_WORDS
    assert content_tokens("beers") == []
    assert content_tokens("fruits") == ["fruit"]
    body = search_steps(plan)[0]["body"]
    assert body == {
        "entity_type": "Beer",
        "where": {"style": "Fruit Beer"},
        "return": "rows",
        "limit": 50,
    }
    assert FRUIT_Q not in _bodies(plan)


def test_plan_singular_fruit_question_matches_too() -> None:
    plan = plan_beer_query("What beers are made from fruit?")
    assert plan["mode"] == "where"
    assert plan["where"]["value"] == "Fruit Beer"


def test_fruit_token_does_not_match_lambic() -> None:
    plan = plan_beer_query("What beers are made from fruits?")
    assert plan["where"]["value"] == "Fruit Beer"
    lambic = plan_beer_query("belgian fruit lambic")
    assert lambic["where"]["value"] == "Belgian-Style Fruit Lambic"


def test_bare_fruit_ipa_and_duvel_are_name_lookups() -> None:
    fruit = plan_beer_query("fruit")
    assert fruit["mode"] == "name_then_where"
    assert fruit["find_query"] == "fruit"
    assert fruit["where"] == {"field": "style", "value": "Fruit Beer"}

    ipa = plan_beer_query("IPA")
    assert ipa["mode"] == "name_then_fts"
    assert ipa["find_query"] == "IPA"
    assert ipa["where"] is None
    assert ipa["fts_query_text"] == "india pale"

    duvel = plan_beer_query("Duvel")
    assert duvel["mode"] == "name_then_fts"
    assert duvel["find_query"] == "Duvel"
    assert duvel["style"] is None


def test_fruits_without_question_falls_through_after_name_miss() -> None:
    plan = plan_beer_query("fruits")
    assert plan["question"] is False
    assert plan["mode"] == "name_then_where"
    assert plan["find_query"] == "fruits"
    steps = search_steps(plan)
    assert steps[0]["body"]["query"] == "fruits"
    assert steps[1]["body"]["where"] == {"style": "Fruit Beer"}


def test_exact_labels_and_pumpkin_question() -> None:
    assert plan_beer_query("Pumpkin Beer")["mode"] == "where"
    assert plan_beer_query("Pumpkin Beer")["where"] == {"field": "style", "value": "Pumpkin Beer"}
    assert plan_beer_query("what pumpkin beers are there?")["where"]["value"] == "Pumpkin Beer"
    assert plan_beer_query("Fruit Beer")["where"] == {"field": "style", "value": "Fruit Beer"}
    belgian = plan_beer_query("Belgian and French Ale")
    assert belgian["mode"] == "where"
    assert belgian["where"] == {"field": "category", "value": "Belgian and French Ale"}
    assert search_steps(belgian, limit=5)[0]["body"]["limit"] == 5


def test_bare_pumpkin_is_name_then_style() -> None:
    plan = plan_beer_query("pumpkin")
    assert plan["mode"] == "name_then_where"
    assert plan["find_query"] == "pumpkin"
    assert plan["where"]["value"] == "Pumpkin Beer"


def test_duvel_question_uses_content_words_then_fts() -> None:
    plan = plan_beer_query("What is Duvel?")
    assert plan["mode"] == "name_then_fts"
    assert plan["find_query"] == "duvel"
    assert plan["fts_query_text"] == "duvel"
    assert plan["where"] is None
    dumped = _bodies(plan)
    assert "What is Duvel?" not in dumped
    assert dumped.count("duvel") >= 1


def test_brewery_fruit_question_skips_beer_facet() -> None:
    plan = plan_beer_query(FRUIT_Q, entity="Brewery")
    assert plan["where"] is None
    assert plan["mode"] == "name_then_fts"
    assert plan["find_query"] == "fruit"
    steps = search_steps(plan)
    assert steps[0]["body"]["entity_type"] == "Brewery"
    assert steps[0]["body"]["query"] == "fruit"
    assert "where" not in steps[0]["body"]
    assert steps[1]["body"]["strategy"] == "fts"
    assert steps[1]["body"]["query_text"] == "fruit"
    assert steps[1]["body"]["timeout_ms"] == 8000
    assert FRUIT_Q not in json.dumps(steps)


def test_non_question_sentence_name_then_content_fts() -> None:
    plan = plan_beer_query("beers with chocolate notes please")
    assert plan["mode"] == "name_then_fts"
    assert plan["find_query"] == "beers with chocolate notes please"
    assert plan["fts_query_text"] == "chocolate note"
    assert plan["where"] is None


def test_execute_fruit_question_hydrates_n_ids() -> None:
    calls: list[tuple[str, dict]] = []

    async def fetch(verb: str, body: dict) -> dict:
        calls.append((verb, body))
        if verb == "find":
            return {
                "items": [
                    {"id": "n_728444f85942a4", "name": "Wild Blue", "type": "Beer", "doc_key": "ab-wild_blue"}
                ],
                "node_ids": ["file::446030a3c1a57314"],
                "truncated": True,
                "status": "ok",
            }
        assert verb == "get"
        assert body == {"ids": ["n_728444f85942a4"], "include": ["body"]}
        return {
            "status": "ok",
            "items": [
                {
                    "id": "file::446030a3c1a57314",
                    "snippet": json.dumps(
                        {
                            "name": "Wild Blue",
                            "style": "Fruit Beer",
                            "category": "Other Style",
                            "abv": 0,
                            "brewery_id": "anheuser_busch",
                        }
                    ),
                }
            ],
        }

    out = asyncio.run(execute_search(plan_beer_query(FRUIT_Q), 50, fetch))
    assert [verb for verb, _body in calls] == ["find", "get"]
    assert calls[0][1]["where"] == {"style": "Fruit Beer"}
    assert out["match"] == {"field": "style", "value": "Fruit Beer"}
    assert out["truncated"] is True
    assert out["partial"] is False
    assert out["lede"] == "Showing beers whose style is Fruit Beer. This page is a partial pour."
    assert out["items"][0]["id"] == "n_728444f85942a4"
    assert out["items"][0]["style"] == "Fruit Beer"
    assert out["items"][0]["category"] == "Other Style"
    assert out["items"][0]["abv"] == 0
    assert out["items"][0]["brewery"] == "anheuser busch"
    assert "abort_if_empty" not in out["path"]


def test_execute_bare_fruit_stops_on_name_hits() -> None:
    calls: list[dict] = []

    async def fetch(verb: str, body: dict) -> dict:
        calls.append(body)
        if verb == "get":
            return {"status": "ok", "items": []}
        assert verb == "find"
        assert body["query"] == "fruit"
        return {
            "truncated": False,
            "items": [
                {"id": "n_1", "name": "Fruit Bat"},
                {"id": "n_2", "name": "Fruit"},
            ],
        }

    out = asyncio.run(execute_search(plan_beer_query("fruit"), 50, fetch))
    assert len(calls) == 2  # find + get, no style where
    assert "where" not in calls[0]
    assert out["match"] == {"field": "name", "value": "fruit"}
    assert len(out["items"]) == 2
    assert out["truncated"] is False
    assert "partial pour" not in out["lede"]


def test_execute_fruits_name_miss_then_style_where() -> None:
    seen: list[dict] = []

    async def fetch(verb: str, body: dict) -> dict:
        seen.append(body)
        if body.get("query") == "fruits":
            return {"items": [], "node_ids": []}
        if body.get("where") == {"style": "Fruit Beer"}:
            return {
                "truncated": True,
                "items": [{"id": "n_9", "name": "Kriek", "type": "Beer"}],
            }
        return {"items": [{"id": "n_9", "snippet": json.dumps({"name": "Kriek", "style": "Fruit Beer"})}]}

    out = asyncio.run(execute_search(plan_beer_query("fruits"), 50, fetch))
    assert seen[0]["query"] == "fruits"
    assert seen[1]["where"] == {"style": "Fruit Beer"}
    assert out["match"]["field"] == "style"
    assert out["items"][0]["style"] == "Fruit Beer"
    assert "abort_if_empty" in out["path"]


def test_execute_fts_doc_key_skips_get() -> None:
    calls: list[str] = []

    async def fetch(verb: str, body: dict) -> dict:
        calls.append(verb)
        if verb == "find":
            return {"items": [], "node_ids": []}
        return {
            "node_ids": [],
            "items": [{"node": {"doc_key": "storm_brewing-fruit_lambics"}}],
        }

    out = asyncio.run(execute_search(plan_beer_query("What is Duvel?"), 50, fetch))
    assert calls == ["find", "search"]
    assert "get" not in calls
    assert out["items"][0]["id"] == "storm_brewing-fruit_lambics"
    assert out["items"][0]["name"] == "fruit lambics"
    assert "doc_key" in out["path"]


def test_list_find_has_no_query_and_detail_uses_get() -> None:
    body = list_find_body("Beer", 2)
    assert body == {"entity_type": "Beer", "return": "rows", "limit": 2}
    assert "query" not in body
    assert detail_lookup("Beer", "n_728444f85942a4")["body"] == {
        "ids": ["n_728444f85942a4"],
        "include": ["body"],
    }
    doc = detail_lookup("Beer", "storm_brewing-fruit_lambics")
    assert doc["kind"] == "find"
    assert doc["body"]["where"] == {"name": "fruit lambics"}

    async def fetch(verb: str, body: dict) -> dict:
        if verb == "get":
            return {
                "status": "ok",
                "items": [
                    {
                        "id": "n_1",
                        "snippet": json.dumps(
                            {"name": "Kriek", "style": "Fruit Beer", "brewery_id": "storm_brewing"}
                        ),
                    }
                ],
            }
        return {"items": [{"id": "n_1", "name": "Kriek"}], "truncated": False}

    listed = asyncio.run(execute_list("Beer", 2, fetch))
    assert listed["items"][0]["style"] == "Fruit Beer"
    detail = asyncio.run(execute_detail("Beer", "n_1", fetch))
    assert detail["ok"] is True
    assert detail["item"]["style"] == "Fruit Beer"
    assert detail["item"]["brewery"] == "storm brewing"
    assert detail["partial"] is False


def test_select_get_ids_prefers_row_n_over_file() -> None:
    data = {
        "node_ids": ["file::beer/1", "n_abc"],
        "items": [{"id": "n_row"}],
    }
    assert select_beer_get_ids(data) == ["n_row"]


def test_select_get_ids_uses_public_node_ids_when_items_have_none() -> None:
    data = {"node_ids": ["n_1", "file::a", "n_2"], "items": [{"doc_key": "only-key"}]}
    assert select_beer_get_ids(data) == ["n_1", "n_2"]


def test_select_get_ids_skips_file_only() -> None:
    assert select_beer_get_ids({"node_ids": ["file::a"]}) == []


def test_written_main_embeds_planner(tmp_path: Path) -> None:
    cfg = HelperConfig(state_dir=tmp_path / "state", default_bucket="beer-sample")
    out = write_beer_sample(cfg, tmp_path / "demo_beer_sample")
    assert out["ok"] is True
    root = Path(out["local_dir"])
    main = (root / "main.py").read_text(encoding="utf-8")
    html = (root / "static" / "index.html").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    planner = Path("src/zeus_dev_helper_mcp/beer_plan.py").read_text(encoding="utf-8")

    assert planner in main
    assert "plan_beer_query" in main
    assert "execute_search" in main
    assert "Fruit Beer" in main
    assert "Pumpkin Beer" in main
    assert "Belgian and French Ale" in main
    assert "belgian-style fruit lambic" in main
    assert '"return": "rows"' in main
    assert "timeout_ms" in main
    assert "abort_if_empty" in main
    assert "CELLAR_CACHE_TTL" in main
    assert "@app.get(\"/search\")" in main or '@app.get("/search")' in main
    assert "/api/beers" in main
    assert "never" in main.lower() and "find.query" in main

    assert "lede" in html
    assert "max-width: 640px" in html
    assert "ABV" in html
    assert "URLSearchParams" in html
    assert "What beers are made from fruits?" in html

    assert "bad plan" in readme.lower() or "0 rows on a sentence" in readme.lower()
    assert "Fruit Beer" in readme
    assert "fruits" in readme.lower()
