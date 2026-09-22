"""ZDM-6: beer Direct UI via use_sample(sample=beer) / start_project."""

from __future__ import annotations

from pathlib import Path

from zeus_dev_helper_mcp.beer import ensure_beer_sample, looks_like_beer_sample, write_beer_sample
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
    assert out.get("llm_required") is False
    root = Path(out["local_dir"])
    assert root.name == "demo_beer_sample"
    assert (root / "main.py").is_file()
    assert (root / "static" / "index.html").is_file()
    assert (root / "requirements.txt").is_file()
    assert (root / ".env.example").is_file()
    assert (root / "README.md").is_file()


def test_beer_sources_have_no_pipeline_and_find_get(tmp_path: Path) -> None:
    cfg = HelperConfig(state_dir=tmp_path / "state", default_bucket="beer-sample")
    out = write_beer_sample(cfg, tmp_path / "demo_beer_sample")
    assert out["ok"] is True
    root = Path(out["local_dir"])
    main = (root / "main.py").read_text(encoding="utf-8")
    html = (root / "static" / "index.html").read_text(encoding="utf-8")
    reqs = (root / "requirements.txt").read_text(encoding="utf-8")
    env = (root / ".env.example").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")

    # Executable BFF must never call the pipeline verb
    assert "/pipeline" not in main
    assert '"pipeline"' not in main
    assert "'pipeline'" not in main
    assert "abort_if_empty" in main
    assert "doc_key" in main
    assert "/find" in main or '"find"' in main
    assert "/get" in main or '"get"' in main
    assert "strategy" in main and "fts" in main
    assert "plan_beer_query" in main
    assert "Fruit Beer" in main
    assert "Pumpkin Beer" in main
    assert "select_beer_get_ids" in main
    assert "CELLAR_CACHE_TTL" in env
    assert "fastapi" in reqs
    assert "uvicorn" in reqs
    assert "httpx" in reqs
    assert "ZEUS_URL" in env
    assert "ZEUS_BUCKET=beer-sample" in env
    assert "PORT" in env
    assert "LLM_API_KEY" not in env
    assert "no llm" in readme.lower()
    assert "PORT" in readme
    assert "ZEUS_URL" in readme
    assert "bad plan" in readme.lower() or "0 rows on a sentence" in readme.lower()
    assert "pipeline" not in reqs.lower()
    assert "pipeline" not in env.lower()


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
