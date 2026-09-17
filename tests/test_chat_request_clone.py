"""Public zeus_chat_request clone + ZEUS_CHAT_REQUEST_DIR."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

from zeus_dev_helper_mcp.catalog import (
    DEFAULT_CHAT_REQUEST_DIR_NAME,
    ENV_CHAT_REQUEST_DIR,
    clone_chat_request,
    ensure_chat_request_dir,
    list_modes,
)
from zeus_dev_helper_mcp.config import HelperConfig


def _cfg(tmp_path: Path) -> HelperConfig:
    return HelperConfig(state_dir=tmp_path / "state")


def test_clone_chat_request_success(tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "zeus_chat_request"

    def fake_run(cmd, **kwargs):
        dest.mkdir(parents=True)
        (dest / "manifest.json").write_text('{"profile":"v2_min","catalogs":[]}\n', encoding="utf-8")
        m = MagicMock()
        m.returncode = 0
        m.stderr = ""
        m.stdout = "Cloning...\n"
        return m

    monkeypatch.setattr("zeus_dev_helper_mcp.catalog.subprocess.run", fake_run)
    out = clone_chat_request(dest=dest)
    assert out["ok"] is True
    assert out["cloned"] is True
    assert dest.is_dir()


def test_clone_chat_request_dest_exists(tmp_path: Path) -> None:
    dest = tmp_path / "zeus_chat_request"
    dest.mkdir()
    out = clone_chat_request(dest=dest)
    assert out["ok"] is False
    assert out["cloned"] is False


def test_ensure_clones_and_sets_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(ENV_CHAT_REQUEST_DIR, raising=False)
    parent = tmp_path / "apps"
    parent.mkdir()
    dest = parent / DEFAULT_CHAT_REQUEST_DIR_NAME

    def fake_run(cmd, **kwargs):
        dest.mkdir(parents=True)
        (dest / "manifest.json").write_text(
            '{"profile":"v2_min","catalogs":[{"mode":"analytics","file":"v2/min/a.json"}]}\n',
            encoding="utf-8",
        )
        m = MagicMock()
        m.returncode = 0
        m.stderr = ""
        m.stdout = ""
        return m

    monkeypatch.setattr("zeus_dev_helper_mcp.catalog.subprocess.run", fake_run)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.catalog._find_chat_request_dir",
        lambda cfg, explicit="": None,
    )
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.catalog._default_clone_parent",
        lambda: parent,
    )

    cfg = _cfg(tmp_path)
    out = ensure_chat_request_dir(cfg, parent_dir=str(parent))
    assert out["ok"] is True
    assert out["cloned"] is True
    assert out["local_dir"] == str(dest.resolve())
    assert os.environ.get(ENV_CHAT_REQUEST_DIR) == str(dest.resolve())
    assert out["env"][ENV_CHAT_REQUEST_DIR] == str(dest.resolve())
    assert cfg.chat_request_dir == dest.resolve()
    assert (cfg.state_dir / "chat_request.json").is_file()


def test_ensure_uses_existing_dir(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "already"
    root.mkdir()
    (root / "manifest.json").write_text('{"profile":"v2_min","catalogs":[]}\n', encoding="utf-8")
    monkeypatch.delenv(ENV_CHAT_REQUEST_DIR, raising=False)
    called = {"n": 0}

    def no_clone(**kwargs):
        called["n"] += 1
        return {"ok": False}

    monkeypatch.setattr("zeus_dev_helper_mcp.catalog.clone_chat_request", no_clone)
    cfg = _cfg(tmp_path)
    cfg.chat_request_dir = root
    out = ensure_chat_request_dir(cfg)
    assert out["ok"] is True
    assert out["cloned"] is False
    assert called["n"] == 0
    assert os.environ[ENV_CHAT_REQUEST_DIR] == str(root.resolve())


def test_list_modes_sets_env_when_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(ENV_CHAT_REQUEST_DIR, raising=False)
    parent = tmp_path / "ws"
    parent.mkdir()
    dest = parent / DEFAULT_CHAT_REQUEST_DIR_NAME
    dest.mkdir()
    (dest / "manifest.json").write_text(
        '{"profile":"v2_min","catalogs":[{"mode":"analytics","file":"x.json","verb_count":1}]}\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "zeus_dev_helper_mcp.catalog._find_chat_request_dir",
        lambda cfg, explicit="": dest.resolve(),
    )
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.catalog.clone_chat_request",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not clone")),
    )

    cfg = _cfg(tmp_path)
    out = list_modes(cfg)
    assert out["profile"] == "v2_min"
    assert out["source"] == "local"
    assert out["cloned"] is False
    assert os.environ[ENV_CHAT_REQUEST_DIR] == str(dest.resolve())
    assert "analytics" in {m["mode"] for m in out["modes"]}
