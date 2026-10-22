"""ZDM-39: smoke sync stays off the zeus_chat_request checkout."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from zeus_dev_helper_mcp.catalog import (
    empty_template_next_action,
    fetch_chat_request,
    is_template_repo,
    list_modes,
)
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.smoke import smoke_catalog_dir


def _cfg(tmp_path: Path, catalog: Path | None) -> HelperConfig:
    return HelperConfig(
        zeus_url="http://127.0.0.1:8080",
        default_bucket="beer-sample",
        default_scope="_default",
        default_mode="analytics",
        chat_request_dir=catalog,
        state_dir=tmp_path / "state",
    )


def _template(root: Path, *, catalogs: list[dict] | None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "v2").mkdir()
    (root / "catalog-index.json").write_text("{}\n", encoding="utf-8")
    manifest: dict = {
        "version": 1,
        "synced_at": 1,
        "files": [],
    }
    if catalogs is not None:
        manifest = {
            "profile": "v2_min",
            "schema_version": 2,
            "repo": "koten-ai/zeus_chat_request",
            "catalogs": catalogs,
        }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _min_template(root: Path) -> None:
    folder = root / "v2" / "min"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "chat_request_analytics_v2_min.json").write_text(
        json.dumps(
            {
                "_format": "zeus.chat_request.v2",
                "verbs": [{"name": "find"}],
            }
        ),
        encoding="utf-8",
    )


def test_sync_index_without_v2_min_is_not_a_template(tmp_path: Path) -> None:
    app = tmp_path / "data" / "chat_requests"
    app.mkdir(parents=True)
    (app / "manifest.json").write_text(
        json.dumps({"version": 1, "files": ["a"], "synced_at": 1}),
        encoding="utf-8",
    )
    (app / "chat_request_analytics_v2.json").write_text("{}\n", encoding="utf-8")
    assert is_template_repo(app) is False
    out = list_modes(_cfg(tmp_path, app))
    assert out["modes"] == []
    assert out["profile"] is None


def test_v2_min_recovers_modes_from_a_sync_index(tmp_path: Path) -> None:
    root = _template(tmp_path / "zeus_chat_request", catalogs=None)
    _min_template(root)
    cfg = _cfg(tmp_path, root)
    out = list_modes(cfg)
    assert out["profile"] == "v2_min"
    assert {row["mode"] for row in out["modes"]} == {"analytics"}
    assert out["modes"][0]["file"] == "v2/min/chat_request_analytics_v2_min.json"
    fetched = fetch_chat_request(cfg, "analytics", detail="summary")
    assert fetched["verb_count"] == 1
    assert fetched["file"] == "v2/min/chat_request_analytics_v2_min.json"


def test_manifest_catalogs_win_over_the_tree(tmp_path: Path) -> None:
    root = _template(
        tmp_path / "zeus_chat_request",
        catalogs=[
            {
                "mode": "analytics",
                "file": "v2/min/chat_request_analytics_v2_min.json",
                "verb_count": 4,
            }
        ],
    )
    _min_template(root)
    out = list_modes(_cfg(tmp_path, root))
    assert out["profile"] == "v2_min"
    assert out["modes"][0]["verb_count"] == 4


def test_empty_local_manifest_names_the_template_index(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "manifest.json").write_text(
        json.dumps({"version": 1, "files": [], "synced_at": 1}),
        encoding="utf-8",
    )
    out = list_modes(_cfg(tmp_path, root))
    assert out["modes"] == []
    action = empty_template_next_action(local_dir=out["local_dir"])
    assert "manifest.json has no catalogs list" in action
    assert "template index" in action
    assert "catalog.sync" in action
    unset = empty_template_next_action(local_dir=None)
    assert "ZEUS_CHAT_REQUEST_DIR" in unset
    assert "clone" in unset.lower()


def test_temp_catalog_stays_the_smoke_store(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    (catalog / "chat_request_analytics_v2.json").write_text("{}\n", encoding="utf-8")
    cfg = _cfg(tmp_path, catalog)
    assert is_template_repo(catalog) is False
    assert smoke_catalog_dir(cfg) == catalog


def test_template_repo_sync_lands_in_the_app_or_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("zeus_client")
    from zeus_client.api.agent import AgentAPI
    from zeus_client.api.catalog import CatalogAPI

    from zeus_dev_helper_mcp.beer import save_beer_sample_dir
    from zeus_dev_helper_mcp.checklist import load_checklist, save_checklist
    from zeus_dev_helper_mcp.smoke import smoke_test_agent

    template = _template(
        tmp_path / "zeus_chat_request",
        catalogs=[
            {
                "mode": "analytics",
                "file": "v2/min/chat_request_analytics_v2_min.json",
            }
        ],
    )
    original = (template / "manifest.json").read_bytes()
    app = tmp_path / "demo_beer_sample"
    chat = app / "data" / "chat_requests"
    chat.mkdir(parents=True)
    (app / "main.py").write_text("print('beer')\n", encoding="utf-8")
    (app / "config.json").write_text(
        json.dumps({"chat_requests_dir": "data/chat_requests"}),
        encoding="utf-8",
    )
    cfg = _cfg(tmp_path, template)
    data = load_checklist(cfg)
    data["meta"] = {"sample": "beer"}
    save_checklist(cfg, data)
    save_beer_sample_dir(cfg, app)

    monkeypatch.setenv("LLM_API_KEY", "test-not-sent")
    captured: dict[str, str] = {}

    async def stop_turn(self, message, **kwargs):
        raise RuntimeError("stop-before-turn")

    async def write_on_sync(self, *args, **kwargs):
        root = Path(self._store().root)
        captured["root"] = str(root)
        (root / "manifest.json").write_text(
            json.dumps({"version": 1, "synced_at": 1, "files": ["x"]}),
            encoding="utf-8",
        )
        return SimpleNamespace(synced=[{"path": "x"}])

    monkeypatch.setattr(AgentAPI, "run_turn", stop_turn)
    monkeypatch.setattr(CatalogAPI, "sync", write_on_sync)
    smoke_test_agent(cfg, update_checklist=False)
    assert (template / "manifest.json").read_bytes() == original
    assert Path(captured["root"]).resolve() == chat.resolve()
    assert "test-not-sent" not in (chat / "manifest.json").read_text(encoding="utf-8")

    loose = _cfg(tmp_path / "loose", template)
    captured.clear()
    smoke_test_agent(loose, update_checklist=False)
    assert (template / "manifest.json").read_bytes() == original
    assert Path(captured["root"]).resolve() == (loose.state_dir / "chat_requests").resolve()
