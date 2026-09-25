"""ZDM-6: beer Direct UI via use_sample(sample=beer) / start_project."""

from __future__ import annotations

from pathlib import Path

from zeus_dev_helper_mcp.beer import (
    _packaged_analytics_catalog,
    analytics_catalog_source,
    ensure_beer_sample,
    looks_like_beer_sample,
    write_beer_sample,
)
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.scaffold import use_sample


def test_use_sample_beer_writes_tree(tmp_path: Path) -> None:
    cfg = HelperConfig(
        zeus_url="http://192.168.0.219:8080",
        default_bucket="beer-sample",
        default_scope="_default",
        state_dir=tmp_path / "state",
    )
    out = use_sample(
        cfg,
        sample="beer",
        project_name="demo_beer_sample",
        parent_dir=str(tmp_path),
    )
    assert out["ok"] is True
    assert out.get("track") == "ui-direct"
    assert out.get("llm_required") is True
    root = Path(out["local_dir"])
    assert root.name == "demo_beer_sample"
    assert (root / "main.py").is_file()
    assert (root / "static" / "index.html").is_file()
    assert (root / "requirements.txt").is_file()
    assert (root / ".env.example").is_file()
    assert (root / "README.md").is_file()


def test_analytics_catalog_falls_back_to_packaged_template(tmp_path: Path, monkeypatch) -> None:
    packaged = _packaged_analytics_catalog()
    assert packaged.is_file()
    text = packaged.read_text(encoding="utf-8")
    assert "## MINI-SCHEMA" not in text
    assert "## SCOPE BRIEF" not in text
    monkeypatch.delenv("ZEUS_CHAT_REQUEST_DIR", raising=False)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.beer._sibling_chat_request_root",
        lambda: tmp_path / "absent-zeus-chat-request",
    )
    cfg = HelperConfig(state_dir=tmp_path / "state")
    cfg.chat_request_dir = None
    assert analytics_catalog_source(cfg) == packaged.resolve()


def test_beer_sources_use_direct_find_then_get(tmp_path: Path) -> None:
    cfg = HelperConfig(state_dir=tmp_path / "state", default_bucket="beer-sample")
    out = write_beer_sample(cfg, tmp_path / "demo_beer_sample")
    assert out["ok"] is True
    root = Path(out["local_dir"])
    main = (root / "main.py").read_text(encoding="utf-8")
    reqs = (root / "requirements.txt").read_text(encoding="utf-8")
    env = (root / ".env.example").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")

    assert "pipeline_body" not in main
    assert 'fetch("pipeline"' not in main
    assert "chat_request=" not in main
    assert "HttpxZeusPort" in main
    assert "HttpxCatalogRemote" in main
    assert "FsCatalogStore" in main
    assert "OpenAICompatibleLlmClient" in main
    assert "agent.run_turn" in main
    assert "catalog.load_for_turn" in main
    assert "MINI-SCHEMA" in main
    assert "Fruit Beer" in main
    assert "Pumpkin Beer" in main
    assert "collect_beer_cards" in main
    assert "CELLAR_CACHE_TTL" in env
    assert "fastapi" in reqs
    assert "uvicorn" in reqs
    assert "kotenai-zeus-client>=2.4.0,<2.5" in reqs
    cfg_text = (root / "config.json").read_text(encoding="utf-8")
    assert "client-floor-6.1" in cfg_text
    assert "durable_sessions" in cfg_text
    assert "chat_requests_dir" in cfg_text
    assert "LLM_API_KEY" in cfg_text
    catalog = root / "data" / "chat_requests" / "chat_request_analytics_v2.json"
    assert catalog.is_file()
    catalog_text = catalog.read_text(encoding="utf-8")
    assert "## MINI-SCHEMA" not in catalog_text
    assert "## SCOPE BRIEF" not in catalog_text
    assert "ZEUS_URL" in env
    assert "ZEUS_BUCKET=beer-sample" in env
    assert "PORT" in env
    assert "LLM_API_KEY=" in env
    assert "mini-schema" in readme.lower()
    assert "run_turn" in readme
    assert "PORT" in readme
    assert "ZEUS_URL" in readme
    assert "pipeline" not in reqs.lower()
    assert "pipeline" not in env.lower()
    assert "pipeline" not in cfg_text.lower()


def test_beer_old_pipeline_bff_is_rewritten(tmp_path: Path) -> None:
    root = tmp_path / "demo_beer_sample"
    (root / "static").mkdir(parents=True)
    (root / "main.py").write_text(
        'fetch("pipeline", {"steps": []})\nabort_if_empty\n@found.node_ids\n',
        encoding="utf-8",
    )
    (root / "README.md").write_text("beer sample\n", encoding="utf-8")
    (root / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    (root / "static" / "index.html").write_text("<html></html>\n", encoding="utf-8")
    (root / ".env").write_text("ZEUS_URL=http://lab.example:8080\n", encoding="utf-8")
    cfg = HelperConfig(state_dir=tmp_path / "state", default_bucket="beer-sample")
    out = write_beer_sample(cfg, root)
    assert out["ok"] is True
    assert out.get("upgraded") is True
    main = (root / "main.py").read_text(encoding="utf-8")
    assert "HttpxZeusPort" in main
    assert "pipeline_body" not in main
    assert (root / ".env").read_text(encoding="utf-8") == "ZEUS_URL=http://lab.example:8080\n"


def test_beer_existing_dir_ok_if_looks_like_sample(tmp_path: Path) -> None:
    cfg = HelperConfig(state_dir=tmp_path / "state")
    first = write_beer_sample(cfg, tmp_path / "demo_beer_sample")
    assert first["ok"] is True
    again = use_sample(
        cfg,
        sample="beer",
        sample_dir=str(tmp_path / "demo_beer_sample"),
    )
    assert again["ok"] is True
    assert again.get("written") is False
    assert looks_like_beer_sample(Path(again["local_dir"]))


def test_beer_nonempty_unrelated_dir_errors(tmp_path: Path) -> None:
    cfg = HelperConfig(state_dir=tmp_path / "state")
    junk = tmp_path / "other"
    junk.mkdir()
    (junk / "notes.txt").write_text("not a beer sample\n", encoding="utf-8")
    out = ensure_beer_sample(cfg, sample_dir=str(junk), project_name="other")
    assert out["ok"] is False
    assert "not empty" in (out.get("error") or "").lower() or "does not look" in (
        out.get("error") or ""
    ).lower()


def test_start_project_reroutes_travel_when_beer_no_llm(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    from zeus_dev_helper_mcp.config import HelperConfig, reload_config
    from zeus_dev_helper_mcp.prereqs import save_prereqs
    from zeus_dev_helper_mcp.server import start_project
    from zeus_dev_helper_mcp.walkthrough import enriched_next_step

    cfg = HelperConfig(state_dir=tmp_path / "state")
    save_prereqs(
        cfg,
        {
            "zeus_url": "http://192.168.0.219:8080",
            "bucket": "beer-sample",
            "scope": "_default",
            "has_llm_key": False,
        },
    )
    out = start_project(sample="travel")
    assert out["started"] is True
    assert out["sample"] == "beer"
    assert out["track"] == "ui-direct"
    assert out.get("rerouted_from") == "travel"
    assert "smoke_test_agent" not in (out.get("recommended_tools") or [])
    nxt = enriched_next_step(reload_config())
    assert nxt.get("app_track") == "ui-direct"
    assert "smoke_test_agent" not in (nxt.get("recommended_tools") or [])


def test_start_project_beer_sets_track(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    from zeus_dev_helper_mcp.config import reload_config
    from zeus_dev_helper_mcp.server import start_project
    from zeus_dev_helper_mcp.walkthrough import enriched_next_step

    out = start_project(sample="beer-sample")
    assert out["started"] is True
    assert out["sample"] == "beer"
    assert out["track"] == "ui-direct"
    assert out.get("llm_required") is False
    tools = out.get("recommended_tools") or []
    assert "use_sample" in tools
    assert "smoke_test_agent" not in tools

    cfg = reload_config()
    # Force checklist item 0.2 open by reading next_step after marking 0.1 done
    from zeus_dev_helper_mcp.checklist import set_item_status

    set_item_status(cfg, "0.1", "done", evidence="test")
    nxt = enriched_next_step(cfg)
    assert nxt.get("app_track") == "ui-direct"
    assert "use_sample" in (nxt.get("recommended_tools") or [])


def test_walkthrough_beer_skips_agent_smoke_primary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    from zeus_dev_helper_mcp.checklist import set_item_status
    from zeus_dev_helper_mcp.config import reload_config
    from zeus_dev_helper_mcp.server import start_project
    from zeus_dev_helper_mcp.walkthrough import enriched_next_step

    start_project(sample="beer")
    cfg = reload_config()
    for iid in ("0.1", "0.2", "1.1", "1.2", "2.1", "2.2", "2.3", "3.1", "3.2", "4.1", "4.2", "5.1"):
        set_item_status(cfg, iid, "done", evidence="test")
    nxt = enriched_next_step(cfg)
    assert nxt.get("app_track") == "ui-direct"
    tools = nxt.get("recommended_tools") or []
    assert "smoke_test_agent" not in tools or tools[0] != "smoke_test_agent"
    assert "smoke_test_zeus" in tools or "recommend_surface" in tools
