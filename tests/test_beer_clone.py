"""use_sample(sample=beer) shallow-clones public demo_beer_sample."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from zeus_dev_helper_mcp.beer import BEER_REPO_GIT, clone_beer_sample
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.scaffold import use_sample


def test_clone_beer_sample_uses_the_public_repo(tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "demo_beer_sample"
    seen: dict[str, object] = {}

    def fake_run(cmd, **kwargs):
        del kwargs
        cmd = list(cmd)
        if "ls-remote" in cmd:
            proc = MagicMock()
            proc.returncode = 0
            proc.stderr = ""
            proc.stdout = ""
            return proc
        seen["cmd"] = cmd
        dest.mkdir(parents=True)
        (dest / "README.md").write_text("# The Sample Tap\npython main.py\n", encoding="utf-8")
        (dest / "main.py").write_text("def main():\n    pass\n", encoding="utf-8")
        (dest / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
        (dest / "static").mkdir()
        (dest / "static" / "index.html").write_text("<html></html>\n", encoding="utf-8")
        proc = MagicMock()
        proc.returncode = 0
        proc.stderr = ""
        proc.stdout = ""
        return proc

    monkeypatch.setattr("zeus_dev_helper_mcp.sample_ref.subprocess.run", fake_run)
    out = clone_beer_sample(dest=dest)
    assert out["ok"] is True
    assert out["cloned"] is True
    assert out["requested_version"] == ""
    assert out["ref"] == "main"
    assert seen["cmd"][:6] == ["git", "clone", "--depth", "1", "--branch", "main"]
    assert seen["cmd"][6] == BEER_REPO_GIT
    assert seen["cmd"][7] == str(dest.resolve())


def test_clone_beer_sample_refuses_an_existing_directory(tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "demo_beer_sample"
    dest.mkdir()

    def boom(*_args, **_kwargs):
        raise AssertionError("git was called")

    monkeypatch.setattr("zeus_dev_helper_mcp.sample_ref.subprocess.run", boom)
    out = clone_beer_sample(dest=dest, version="0.1.0")
    assert out["ok"] is False
    assert out["cloned"] is False


def test_use_sample_beer_clone_failure_does_not_write_a_tree(
    tmp_path: Path, monkeypatch
) -> None:
    def fake_run(cmd, **kwargs):
        proc = MagicMock()
        proc.returncode = 1
        proc.stderr = "fatal: repository not found"
        proc.stdout = ""
        return proc

    monkeypatch.setattr("zeus_dev_helper_mcp.sample_ref.subprocess.run", fake_run)
    cfg = HelperConfig(state_dir=tmp_path / "state", default_bucket="beer-sample")
    out = use_sample(
        cfg,
        sample="beer",
        parent_dir=str(tmp_path),
        project_name="demo_beer_sample",
    )
    assert out["ok"] is False
    assert out.get("failure_class") == "clone_failed"
    assert out.get("cloned") is False
    assert "git clone" not in str(out.get("next_action") or "")
    card = out.get("sample") if isinstance(out.get("sample"), dict) else {}
    assert "git clone --depth 1" not in str(card.get("clone") or "")
    assert not (tmp_path / "demo_beer_sample" / "main.py").exists()


def test_use_sample_passes_version_to_beer_clone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_clone(**kwargs):
        seen.update(kwargs)
        return {"ok": False, "cloned": False, "error": "stop", "next_action": "stop"}

    monkeypatch.setattr("zeus_dev_helper_mcp.beer.clone_beer_sample", fake_clone)
    cfg = HelperConfig(state_dir=tmp_path / "state", default_bucket="beer-sample")
    out = use_sample(
        cfg,
        sample="beer",
        parent_dir=str(tmp_path),
        project_name="fresh-beer",
        version="0.1.0",
    )
    assert seen["version"] == "0.1.0"
    assert out.get("failure_class") == "clone_failed"

