"""Yelp-demo app: search loads the chat request; list routes stay on find."""

from __future__ import annotations

import json
from pathlib import Path

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.yelp import ensure_yelp_sample
from zeus_dev_helper_mcp.yelp_app import (
    _search_source,
    collect_yelp_cards,
    install_yelp_catalog,
    is_biz_user,
    write_yelp_sample,
    yelp_bff_is_current,
)


def _cfg(tmp_path: Path) -> HelperConfig:
    return HelperConfig(state_dir=tmp_path / "state")


def test_cards_drop_verb_names_and_keep_business_signals() -> None:
    blobs = [
        {"name": "pipeline"},
        {"name": "find"},
        {"name": "search"},
        {"name": "describe"},
        {"name": "Only a label"},
        {"name": "find", "city": "Philadelphia"},
        {
            "name": "Joe's Seafood",
            "doc_key": "biz:abc",
            "city": "Philadelphia",
            "category": "Seafood",
            "rating": 4.5,
            "review_count": 12,
            "address": "1 Dock St",
        },
        {"name": "City Only", "city": "Austin"},
        {"name": "Rated", "stars": 5},
        {"name": "Reviewed", "metadata": {"review_count": 3}},
        {"name": "Addressed", "address": "9 Main"},
        {"name": "Categorized", "categories": ["Food"]},
        {"title": "Keyed", "id": "biz:keyed"},
        {
            "name": "find",
            "result_json": json.dumps(
                {"items": [{"name": "Nested", "doc_key": "biz:nest", "city": "Boston"}]}
            ),
        },
    ]
    names = [card["name"] for card in collect_yelp_cards(blobs)]
    assert names == [
        "Joe's Seafood",
        "City Only",
        "Rated",
        "Reviewed",
        "Addressed",
        "Categorized",
        "Keyed",
        "Nested",
    ]


def test_direct_rows_keep_user_biz_keys() -> None:
    assert is_biz_user({"type": "User", "doc_key": "biz:1", "name": "A"})
    assert is_biz_user({"doc_key": "biz:1", "name": "A"})
    assert not is_biz_user({"type": "User", "doc_key": "rev:1", "name": "A"})
    assert not is_biz_user({"type": "Tip", "doc_key": "biz:1", "name": "A"})


def test_written_search_loads_scope_catalog(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "pack.json"
    body = {
        "messages": [
            {
                "role": "system",
                "content": (
                    "SCOPE BRIEF = a definition. MINI-SCHEMA = a definition. "
                    "Example entity_type Beer."
                ),
            }
        ]
    }
    src.write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp_app._catalog_sources",
        lambda cfg: [src],
    )
    root = tmp_path / "app"
    out = write_yelp_sample(_cfg(tmp_path), root, project_name="demo_yelp")
    assert out["ok"] is True
    assert out["written"] is True
    main = (root / "main.py").read_text(encoding="utf-8")
    assert yelp_bff_is_current(main)
    search = _search_source(main)
    assert "agent.run_turn" in search
    assert "catalog.load_for_turn" in search
    assert "collect_yelp_cards" in search
    assert ".find(" not in search
    assert "biz:" not in search
    assert "_page_businesses" not in search
    assert "chat_request=" not in main
    assert "pipeline_body" not in main
    assert 'entity_type": "User"' in main
    assert "_FIND_PAGES" in main
    assert "next_offset" in main
    assert "rt.data.get" not in main
    catalog = root / "data" / "chat_requests" / "yelp-demo__default" / "chat_request_analytics_v2.json"
    assert catalog.is_file()
    copied = catalog.read_text(encoding="utf-8")
    assert copied == src.read_text(encoding="utf-8")
    assert "## SCOPE BRIEF" not in copied
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    assert config["target"]["bucket"] == "yelp-demo"
    assert config["target"]["scope"] == "_default"
    assert config["llm"]["api_key_env"] == "LLM_API_KEY"
    assert config["settings"]["durable_sessions"] is False
    assert config["session"]["semantic_cache"]["enabled"] is False
    assert "base_id" not in config
    page = (root / "static" / "index.html").read_text(encoding="utf-8")
    assert 'fetch("/api/search"' in page
    assert 'fetch("/api/suggest' in page
    assert 'fetch("/api/businesses' in page
    assert 'fetch("/api/business/' in page


def test_rewrite_replaces_a_local_biz_scan(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp_app._catalog_sources",
        lambda cfg: [],
    )
    # A missing catalog still has to leave a path check possible. Provide one file.
    src = tmp_path / "pack.json"
    src.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp_app._catalog_sources",
        lambda cfg: [src],
    )
    root = tmp_path / "app"
    cfg = _cfg(tmp_path)
    first = write_yelp_sample(cfg, root)
    assert first["ok"] is True
    main_path = root / "main.py"
    main_path.write_text(
        main_path.read_text(encoding="utf-8").replace(
            "async def _run_search(query: str, *, limit: int) -> dict[str, Any]:",
            "async def _run_search(query: str, *, limit: int) -> dict[str, Any]:\n"
            '    rows = [row for row in [] if str(row.get("doc_key", "")).startswith("biz:")]\n'
            "    return {'items': rows}\n\n"
            "async def _run_search_original(query: str, *, limit: int) -> dict[str, Any]:",
        ),
        encoding="utf-8",
    )
    assert yelp_bff_is_current(main_path.read_text(encoding="utf-8")) is False
    second = write_yelp_sample(cfg, root)
    assert second["ok"] is True
    assert second["upgraded"] is True
    assert yelp_bff_is_current(main_path.read_text(encoding="utf-8"))


def test_foreign_default_dir_writes_sibling(tmp_path: Path) -> None:
    foreign = tmp_path / "demo_yelp"
    foreign.mkdir()
    (foreign / "frontend").mkdir()
    (foreign / "README.md").write_text("git checkout\n", encoding="utf-8")
    blocked = tmp_path / "demo_yelp-2"
    blocked.mkdir()
    (blocked / "legacy.txt").write_text("also foreign\n", encoding="utf-8")
    out = ensure_yelp_sample(_cfg(tmp_path), parent_dir=str(tmp_path))
    assert out["ok"] is True
    assert out.get("relocated_from") == str(foreign.resolve())
    written = Path(out["local_dir"])
    assert written.name == "demo_yelp-3"
    assert (written / "main.py").is_file()
    assert (foreign / "README.md").read_text(encoding="utf-8") == "git checkout\n"
    assert not (foreign / "main.py").exists()
    assert not (blocked / "main.py").exists()


def test_install_does_not_invent_a_scope_brief(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "pack.json"
    src.write_text(
        json.dumps({"messages": [{"content": "The SCOPE BRIEF is defined here."}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp_app._catalog_sources",
        lambda cfg: [src],
    )
    root = tmp_path / "app"
    info = install_yelp_catalog(_cfg(tmp_path), root)
    assert info["ok"] is True
    text = Path(info["path"]).read_text(encoding="utf-8")
    assert text == src.read_text(encoding="utf-8")
    assert "## SCOPE BRIEF" not in text
