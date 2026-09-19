"""ZDM-7: beer Direct NL planner (Hub-Chat-like where.style / FTS tokens)."""

from __future__ import annotations

from pathlib import Path

from zeus_dev_helper_mcp.beer import (
    BEER_NL_STOPWORDS,
    plan_beer_query,
    select_beer_get_ids,
    write_beer_sample,
)
from zeus_dev_helper_mcp.config import HelperConfig

FRUIT_Q = "What beers are made from fruit?"


def test_plan_fruit_sentence_maps_to_fruit_beer_style() -> None:
    plan = plan_beer_query(FRUIT_Q)
    assert plan["mode"] == "where_style"
    assert plan["style"] == "Fruit Beer"
    assert plan["tokens"] == ["fruit"]
    assert plan["fts_query_text"] == "fruit"
    assert plan["find_query"] is None
    assert "what" in BEER_NL_STOPWORDS
    assert "made" in BEER_NL_STOPWORDS
    assert "from" in BEER_NL_STOPWORDS
    assert "beers" in BEER_NL_STOPWORDS


def test_plan_never_uses_full_sentence_as_find_query() -> None:
    plan = plan_beer_query(FRUIT_Q)
    assert plan["find_query"] != FRUIT_Q
    assert plan.get("find_query") in (None, "fruit")
    multi = plan_beer_query("beers with chocolate notes please")
    assert multi["mode"] == "fts"
    assert multi["fts_query_text"] == "chocolate notes"
    assert multi["find_query"] is None
    assert "chocolate notes please" not in (multi["find_query"] or "")


def test_plan_pumpkin_and_chip_styles() -> None:
    assert plan_beer_query("pumpkin")["style"] == "Pumpkin Beer"
    assert plan_beer_query("Pumpkin Beer")["style"] == "Pumpkin Beer"
    assert plan_beer_query("what pumpkin beers are there?")["style"] == "Pumpkin Beer"
    assert plan_beer_query("ipa")["mode"] == "where_style"
    assert plan_beer_query("ipa")["style"] == "American IPA"
    assert plan_beer_query("Fruit Beer")["style"] == "Fruit Beer"


def test_plan_single_unknown_token_uses_find_query() -> None:
    plan = plan_beer_query("guinness")
    assert plan["mode"] == "find_query"
    assert plan["find_query"] == "guinness"
    assert plan["style"] is None


def test_select_get_ids_prefers_file_over_n_when_both() -> None:
    data = {
        "node_ids": ["n_abc", "file::beer/1", "n_def"],
        "items": [{"id": "n_local"}],
    }
    ids = select_beer_get_ids(data)
    assert "file::beer/1" in ids
    assert all(not i.startswith("n_") for i in ids)


def test_select_get_ids_prefers_top_level_node_ids() -> None:
    data = {
        "node_ids": ["file::a"],
        "items": [{"id": "n_item"}],
    }
    assert select_beer_get_ids(data) == ["file::a"]


def test_select_get_ids_keeps_n_when_only_n() -> None:
    data = {"node_ids": ["n_1", "n_2"]}
    assert select_beer_get_ids(data) == ["n_1", "n_2"]


def test_written_main_py_embeds_planner(tmp_path: Path) -> None:
    cfg = HelperConfig(state_dir=tmp_path / "state", default_bucket="beer-sample")
    out = write_beer_sample(cfg, tmp_path / "demo_beer_sample")
    assert out["ok"] is True
    main = (Path(out["local_dir"]) / "main.py").read_text(encoding="utf-8")
    readme = (Path(out["local_dir"]) / "README.md").read_text(encoding="utf-8")

    assert "STOPWORDS" in main
    assert "plan_query" in main
    assert "Pumpkin Beer" in main
    assert "Fruit Beer" in main
    assert "_select_get_ids" in main
    assert "file::" in main
    assert "what" in main and "made" in main and "from" in main
    # Must not keep the old short-token-only path that used full query as find.query for NL
    assert "Never sends a full NL sentence as find.query" in main or "never find.query=full sentence" in main.lower() or "never find.query" in main.lower()

    assert "bad plan" in readme.lower() or "0 rows on a sentence" in readme.lower()
    assert "Fruit Beer" in readme
    assert "tokenize" in readme.lower() or "stopword" in readme.lower()
