"""demo_yelp clone + DEMO_YELP_SAMPLE_DIR. Bare sample=yelp stays the multi gate."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

from zeus_dev_helper_mcp.checklist import load_checklist
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.explain import explain_topic
from zeus_dev_helper_mcp.scaffold import use_sample
from zeus_dev_helper_mcp.yelp import (
    DEFAULT_YELP_DIR_NAME,
    ENV_YELP_DIR,
    YELP_REPO_GIT,
    clone_yelp_sample,
    ensure_yelp_sample,
    is_yelp_demo_sample,
    sanitize_yelp_dir_name,
    validate_yelp_layout,
)


def _cfg(tmp_path: Path) -> HelperConfig:
    return HelperConfig(state_dir=tmp_path / "state")


def _write_layout(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "README.md").write_text("# yelp\n", encoding="utf-8")
    frontend = dest / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text("{}\n", encoding="utf-8")


def test_sanitize_and_aliases() -> None:
    assert sanitize_yelp_dir_name("") == DEFAULT_YELP_DIR_NAME
    assert sanitize_yelp_dir_name("../etc") == DEFAULT_YELP_DIR_NAME
    assert sanitize_yelp_dir_name("my_yelp") == "my_yelp"
    assert is_yelp_demo_sample("yelp") is False
    assert is_yelp_demo_sample("multi") is False
    assert is_yelp_demo_sample("yelp-demo") is True
    assert is_yelp_demo_sample("demo_yelp") is True
    assert is_yelp_demo_sample("yelpdemo") is True


def test_validate_layout(tmp_path: Path) -> None:
    root = tmp_path / "demo_yelp"
    root.mkdir()
    assert validate_yelp_layout(root)["ok"] is False
    (root / "README.md").write_text("# yelp\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='local-guide'\n", encoding="utf-8")
    assert validate_yelp_layout(root)["ok"] is True


def test_clone_yelp_sample_success(tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "demo_yelp"
    seen: dict[str, list[str]] = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = list(cmd)
        _write_layout(dest)
        proc = MagicMock()
        proc.returncode = 0
        proc.stderr = ""
        proc.stdout = "Cloning...\n"
        return proc

    monkeypatch.setattr("zeus_dev_helper_mcp.yelp.subprocess.run", fake_run)
    out = clone_yelp_sample(dest=dest)
    assert out["ok"] is True
    assert out["cloned"] is True
    assert dest.is_dir()
    assert seen["cmd"][:4] == ["git", "clone", "--depth", "1"]
    assert seen["cmd"][4] == YELP_REPO_GIT


def test_clone_yelp_sample_dest_exists(tmp_path: Path) -> None:
    dest = tmp_path / "demo_yelp"
    dest.mkdir()
    out = clone_yelp_sample(dest=dest)
    assert out["ok"] is False
    assert out["cloned"] is False


def test_ensure_clones_and_sets_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(ENV_YELP_DIR, raising=False)
    parent = tmp_path / "apps"
    parent.mkdir()
    dest = parent / "my_yelp_boot"

    def fake_run(cmd, **kwargs):
        _write_layout(dest)
        proc = MagicMock()
        proc.returncode = 0
        proc.stderr = ""
        proc.stdout = ""
        return proc

    monkeypatch.setattr("zeus_dev_helper_mcp.yelp.subprocess.run", fake_run)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp._find_yelp_dir",
        lambda explicit="", cfg=None: None,
    )
    monkeypatch.setattr("zeus_dev_helper_mcp.yelp._default_clone_parent", lambda: parent)

    cfg = _cfg(tmp_path)
    out = ensure_yelp_sample(cfg, project_name="my_yelp_boot", parent_dir=str(parent))
    assert out["ok"] is True
    assert out["cloned"] is True
    assert out["local_dir"] == str(dest.resolve())
    assert os.environ.get(ENV_YELP_DIR) == str(dest.resolve())
    assert out["env"][ENV_YELP_DIR] == str(dest.resolve())
    assert "npm install" in out["next_action"]
    assert "yelp-demo" in out["next_action"]
    saved = json.loads((cfg.state_dir / "yelp_sample.json").read_text(encoding="utf-8"))
    assert saved["yelp_sample_dir"] == str(dest.resolve())


def test_ensure_uses_existing_sample_dir(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "already"
    _write_layout(root)
    monkeypatch.delenv(ENV_YELP_DIR, raising=False)
    called = {"n": 0}

    def no_clone(**kwargs):
        called["n"] += 1
        return {"ok": False}

    monkeypatch.setattr("zeus_dev_helper_mcp.yelp.clone_yelp_sample", no_clone)
    cfg = _cfg(tmp_path)
    out = ensure_yelp_sample(cfg, sample_dir=str(root))
    assert out["ok"] is True
    assert out["cloned"] is False
    assert called["n"] == 0
    assert os.environ[ENV_YELP_DIR] == str(root.resolve())


def test_use_sample_yelp_demo_passes_project_name(tmp_path: Path, monkeypatch) -> None:
    parent = tmp_path / "ws"
    parent.mkdir()
    dest = parent / "BootYelp"

    def fake_run(cmd, **kwargs):
        _write_layout(dest)
        proc = MagicMock()
        proc.returncode = 0
        proc.stderr = ""
        proc.stdout = ""
        return proc

    monkeypatch.setattr("zeus_dev_helper_mcp.yelp.subprocess.run", fake_run)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp._find_yelp_dir",
        lambda explicit="", cfg=None: None,
    )
    monkeypatch.setattr("zeus_dev_helper_mcp.yelp._default_clone_parent", lambda: parent)
    monkeypatch.delenv(ENV_YELP_DIR, raising=False)

    cfg = _cfg(tmp_path)
    out = use_sample(cfg, sample="yelp-demo", project_name="BootYelp", parent_dir=str(parent))
    assert out["ok"] is True
    assert out["cloned"] is True
    assert out["project_name"] == "BootYelp"
    assert out["local_dir"] == str(dest.resolve())
    assert out["sample"]["sample"] == "demo_yelp"
    assert out["sample"]["name"] == "demo_yelp"
    assert out["app_kind"] == "ui"
    assert os.environ[ENV_YELP_DIR] == str(dest.resolve())
    data = load_checklist(cfg)
    statuses = {
        item["id"]: item["status"]
        for phase in data["phases"]
        for item in phase["items"]
    }
    assert statuses["0.2"] == "done"
    assert statuses["3.1"] == "done"


def test_use_sample_bare_yelp_stays_blocked(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    out = use_sample(cfg, sample="yelp")
    assert out["ok"] is False
    assert out["blocked"] is True


def test_failed_clone_does_not_fall_through(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DEMO_TRAVEL_SAMPLE_DIR", raising=False)
    monkeypatch.delenv(ENV_YELP_DIR, raising=False)
    parent = tmp_path / "apps"
    parent.mkdir()
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp._find_yelp_dir",
        lambda explicit="", cfg=None: None,
    )
    monkeypatch.setattr("zeus_dev_helper_mcp.yelp._default_clone_parent", lambda: parent)

    def fake_run(cmd, **kwargs):
        proc = MagicMock()
        proc.returncode = 1
        proc.stderr = "authentication failed"
        proc.stdout = ""
        return proc

    monkeypatch.setattr("zeus_dev_helper_mcp.yelp.subprocess.run", fake_run)
    cfg = _cfg(tmp_path)
    out = use_sample(cfg, sample="demo_yelp", parent_dir=str(parent))
    assert out["ok"] is False
    assert out.get("blocked") is not True
    assert out["sample"]["sample"] == "demo_yelp"
    assert "DEMO_YELP_SAMPLE_DIR" in (out.get("next_action") or "")
    assert os.environ.get("DEMO_TRAVEL_SAMPLE_DIR") is None
    assert os.environ.get(ENV_YELP_DIR) is None
    assert list(parent.rglob("main.py")) == []


def test_start_project_demo_yelp(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    from zeus_dev_helper_mcp.checklist import set_item_status
    from zeus_dev_helper_mcp.config import reload_config
    from zeus_dev_helper_mcp.server import start_project
    from zeus_dev_helper_mcp.walkthrough import enriched_next_step

    out = start_project(sample="yelp-demo")
    assert out["started"] is True
    assert out.get("blocked") is not True
    assert out["sample"] == "demo_yelp"
    assert out["track"] == "ui"
    assert out["app_kind"] == "ui"
    tools = out.get("recommended_tools") or []
    assert "use_sample" in tools
    assert "smoke_test_agent" in tools

    cfg = reload_config()
    set_item_status(cfg, "0.1", "done", evidence="test")
    nxt = enriched_next_step(cfg)
    assert nxt.get("app_track") == "ui"
    assert "use_sample" in (nxt.get("recommended_tools") or [])
    hint = nxt.get("use_sample_args_hint") or {}
    assert hint.get("sample") == "demo_yelp"
    assert hint.get("project_name") == "demo_yelp"


def test_start_project_bare_yelp_still_blocked(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    from zeus_dev_helper_mcp.server import start_project

    out = start_project(sample="yelp")
    assert out["started"] is False
    assert out["blocked"] is True


def test_probe_target_and_glossary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    from zeus_dev_helper_mcp.clarify import probe_target

    assert probe_target("yelp-demo") == ("yelp-demo", "_default")
    assert probe_target("yelp") is None
    cfg = _cfg(tmp_path)
    topic = explain_topic(cfg, "yelp-demo")
    assert topic["found"] is True
    assert topic["topic"] == "demo_yelp"
