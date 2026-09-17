"""Public demo_travel_sample clone + DEMO_TRAVEL_SAMPLE_DIR."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.scaffold import use_sample
from zeus_dev_helper_mcp.travel import (
    DEFAULT_TRAVEL_DIR_NAME,
    ENV_TRAVEL_DIR,
    clone_travel_sample,
    ensure_travel_sample,
    sanitize_travel_dir_name,
)


def _cfg(tmp_path: Path) -> HelperConfig:
    return HelperConfig(state_dir=tmp_path / "state")


def test_sanitize_travel_dir_name() -> None:
    assert sanitize_travel_dir_name("") == DEFAULT_TRAVEL_DIR_NAME
    assert sanitize_travel_dir_name("  My App  ") == "My-App"
    assert sanitize_travel_dir_name("../etc") == DEFAULT_TRAVEL_DIR_NAME
    assert sanitize_travel_dir_name("zeus_travel_ui") == "zeus_travel_ui"


def test_clone_travel_sample_success(tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "demo_travel_sample"

    def fake_run(cmd, **kwargs):
        dest.mkdir(parents=True)
        (dest / "README.md").write_text("# demo\n", encoding="utf-8")
        (dest / "requirements.txt").write_text("x\n", encoding="utf-8")
        m = MagicMock()
        m.returncode = 0
        m.stderr = ""
        m.stdout = "Cloning...\n"
        return m

    monkeypatch.setattr("zeus_dev_helper_mcp.travel.subprocess.run", fake_run)
    out = clone_travel_sample(dest=dest)
    assert out["ok"] is True
    assert out["cloned"] is True
    assert dest.is_dir()


def test_clone_travel_sample_dest_exists(tmp_path: Path) -> None:
    dest = tmp_path / "demo_travel_sample"
    dest.mkdir()
    out = clone_travel_sample(dest=dest)
    assert out["ok"] is False
    assert out["cloned"] is False


def test_ensure_clones_and_sets_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(ENV_TRAVEL_DIR, raising=False)
    parent = tmp_path / "apps"
    parent.mkdir()
    dest = parent / "my_travel_boot"

    def fake_run(cmd, **kwargs):
        dest.mkdir(parents=True)
        (dest / "README.md").write_text("# demo\n", encoding="utf-8")
        (dest / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
        m = MagicMock()
        m.returncode = 0
        m.stderr = ""
        m.stdout = ""
        return m

    monkeypatch.setattr("zeus_dev_helper_mcp.travel.subprocess.run", fake_run)
    # Avoid discovering real sibling demo_travel_sample on this machine.
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.travel._find_travel_dir",
        lambda explicit="", cfg=None: None,
    )
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.travel._default_clone_parent",
        lambda: parent,
    )

    cfg = _cfg(tmp_path)
    out = ensure_travel_sample(cfg, project_name="my_travel_boot", parent_dir=str(parent))
    assert out["ok"] is True
    assert out["cloned"] is True
    assert out["local_dir"] == str(dest.resolve())
    assert os.environ.get(ENV_TRAVEL_DIR) == str(dest.resolve())
    assert out["env"][ENV_TRAVEL_DIR] == str(dest.resolve())
    assert (cfg.state_dir / "travel_sample.json").is_file()


def test_ensure_uses_existing_sample_dir(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "already"
    root.mkdir()
    (root / "README.md").write_text("# ok\n", encoding="utf-8")
    (root / "requirements.txt").write_text("x\n", encoding="utf-8")
    monkeypatch.delenv(ENV_TRAVEL_DIR, raising=False)
    called = {"n": 0}

    def no_clone(**kwargs):
        called["n"] += 1
        return {"ok": False}

    monkeypatch.setattr("zeus_dev_helper_mcp.travel.clone_travel_sample", no_clone)
    cfg = _cfg(tmp_path)
    out = ensure_travel_sample(cfg, sample_dir=str(root))
    assert out["ok"] is True
    assert out["cloned"] is False
    assert called["n"] == 0
    assert os.environ[ENV_TRAVEL_DIR] == str(root.resolve())


def test_use_sample_passes_project_name(tmp_path: Path, monkeypatch) -> None:
    parent = tmp_path / "ws"
    parent.mkdir()
    dest = parent / "BootApp"

    def fake_run(cmd, **kwargs):
        dest.mkdir(parents=True)
        (dest / "README.md").write_text("# demo\n", encoding="utf-8")
        (dest / "src").mkdir()
        m = MagicMock()
        m.returncode = 0
        m.stderr = ""
        m.stdout = ""
        return m

    monkeypatch.setattr("zeus_dev_helper_mcp.travel.subprocess.run", fake_run)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.travel._find_travel_dir",
        lambda explicit="", cfg=None: None,
    )
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.travel._default_clone_parent",
        lambda: parent,
    )
    monkeypatch.delenv(ENV_TRAVEL_DIR, raising=False)

    cfg = _cfg(tmp_path)
    out = use_sample(cfg, sample="travel", project_name="BootApp", parent_dir=str(parent))
    assert out["ok"] is True
    assert out["cloned"] is True
    assert out["project_name"] == "BootApp"
    assert out["local_dir"] == str(dest.resolve())
    assert os.environ[ENV_TRAVEL_DIR] == str(dest.resolve())
