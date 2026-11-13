"""use_sample(sample=beer) shallow-clones public demo_beer_sample."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from zeus_dev_helper_mcp.beer import BEER_REPO_GIT, clone_beer_sample
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.sample_ref import (
    latest_semver_tag,
    parse_remote_tags,
    resolve_ref,
)
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

    monkeypatch.setattr("zeus_dev_helper_mcp.beer.subprocess.run", fake_run)
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

    monkeypatch.setattr("zeus_dev_helper_mcp.beer.subprocess.run", boom)
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

    monkeypatch.setattr("zeus_dev_helper_mcp.beer.subprocess.run", fake_run)
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
    assert not (tmp_path / "demo_beer_sample" / "main.py").exists()


_REF_CASES = [
    ("0.1.0", ["0.1.0"], "0.1.0"),
    ("0.1.0", ["0.1.0", "0.2.0"], "0.1.0"),
    (None, ["0.1.0", "0.2.0"], "0.2.0"),
    ("9.9.9", ["0.1.0"], "0.1.0"),
    (None, [], "main"),
    ("0.1.0", [], "main"),
    ("v0.1.0", ["v0.1.0", "0.2.0"], "v0.1.0"),
    (None, ["0.9.0", "0.10.0", "v0.10.0"], "0.10.0"),
]


def _tag_text(names: list[str]) -> str:
    lines: list[str] = []
    for index, name in enumerate(names):
        sha = f"{index:040d}"
        lines.append(f"{sha} refs/tags/{name}")
        lines.append(f"{sha} refs/tags/{name}^{{}}")
    return "\n".join(lines)


def _branch_of(cmd: list[str]) -> str:
    return cmd[cmd.index("--branch") + 1]


def _git_calls(monkeypatch: pytest.MonkeyPatch, tags: list[str], dest: Path):
    cmds: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        del kwargs
        cmd = list(cmd)
        cmds.append(cmd)
        if "ls-remote" in cmd:
            proc = MagicMock()
            proc.returncode = 0
            proc.stderr = ""
            proc.stdout = _tag_text(tags)
            return proc
        dest.mkdir(parents=True, exist_ok=True)
        proc = MagicMock()
        proc.returncode = 0
        proc.stderr = ""
        proc.stdout = ""
        return proc

    monkeypatch.setattr("zeus_dev_helper_mcp.beer.subprocess.run", fake_run)
    return cmds


@pytest.mark.parametrize(("version", "tags", "branch"), _REF_CASES)
def test_clone_resolves_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version, tags, branch) -> None:
    dest = tmp_path / "sample"
    cmds = _git_calls(monkeypatch, tags, dest)
    kwargs = {} if version is None else {"version": version}
    out = clone_beer_sample(dest=dest, **kwargs)
    clones = [cmd for cmd in cmds if len(cmd) > 1 and cmd[1] == "clone"]
    assert out["ok"] is True
    assert out["cloned"] is True
    assert out["ref"] == branch
    assert out["requested_version"] == ("" if version is None else version)
    assert len(clones) == 1
    assert _branch_of(clones[0]) == branch
    assert "--branch" in out["clone_cmd"]
    assert branch in out["clone_cmd"]


def test_ls_remote_failure_does_not_clone_main(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "sample"
    cmds: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        del kwargs
        cmd = list(cmd)
        cmds.append(cmd)
        proc = MagicMock()
        proc.returncode = 128
        proc.stderr = "fatal: unable to access"
        proc.stdout = ""
        return proc

    monkeypatch.setattr("zeus_dev_helper_mcp.beer.subprocess.run", fake_run)
    out = clone_beer_sample(dest=dest, version="0.1.0")
    assert out["ok"] is False
    assert out["failure_class"] == "clone_failed"
    assert out["cloned"] is False
    assert out.get("ref") is None
    assert not any(len(cmd) > 1 and cmd[1] == "clone" for cmd in cmds)
    assert "main" not in (out.get("clone_cmd") or "")
    assert not dest.exists()


def test_missing_git_is_clone_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "sample"

    def fake_run(cmd, **kwargs):
        del cmd, kwargs
        raise FileNotFoundError("git")

    monkeypatch.setattr("zeus_dev_helper_mcp.beer.subprocess.run", fake_run)
    out = clone_beer_sample(dest=dest, version="0.1.0")
    assert out["ok"] is False
    assert out["failure_class"] == "clone_failed"
    assert out["error"] == "git not found on PATH"
    assert not dest.exists()


def test_clone_timeout_does_not_fall_through(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "sample"
    cmds: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        del kwargs
        cmd = list(cmd)
        cmds.append(cmd)
        if "ls-remote" in cmd:
            proc = MagicMock()
            proc.returncode = 0
            proc.stderr = ""
            proc.stdout = _tag_text(["0.1.0"])
            return proc
        dest.mkdir()
        (dest / "PARTIAL").write_text("left behind", encoding="utf-8")
        raise subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr("zeus_dev_helper_mcp.beer.subprocess.run", fake_run)
    out = clone_beer_sample(dest=dest, version="9.9.9")
    clones = [cmd for cmd in cmds if len(cmd) > 1 and cmd[1] == "clone"]
    assert out["ok"] is False
    assert out["failure_class"] == "clone_failed"
    assert out["ref"] == "0.1.0"
    assert len(clones) == 1
    assert _branch_of(clones[0]) == "0.1.0"
    assert not dest.exists()


def test_failed_clone_removes_partial_and_does_not_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "sample"
    cmds: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        del kwargs
        cmd = list(cmd)
        cmds.append(cmd)
        proc = MagicMock()
        proc.stderr = ""
        proc.stdout = ""
        if "ls-remote" in cmd:
            proc.returncode = 0
            proc.stdout = _tag_text(["0.2.0"])
            return proc
        dest.mkdir()
        (dest / "PARTIAL").write_text("left behind", encoding="utf-8")
        proc.returncode = 1
        proc.stderr = "fatal: clone failed"
        return proc

    monkeypatch.setattr("zeus_dev_helper_mcp.beer.subprocess.run", fake_run)
    out = clone_beer_sample(dest=dest, version="0.2.0")
    clones = [cmd for cmd in cmds if len(cmd) > 1 and cmd[1] == "clone"]
    assert out["ok"] is False
    assert out["failure_class"] == "clone_failed"
    assert out["ref"] == "0.2.0"
    assert len(clones) == 1
    assert _branch_of(clones[0]) == "0.2.0"
    assert not dest.exists()


def test_parse_remote_tags_ignores_peeled_duplicates() -> None:
    text = (
        "aaa refs/tags/0.9.0\n"
        "bbb refs/tags/0.10.0\n"
        "bbb refs/tags/0.10.0^{}\n"
        "ccc refs/tags/v0.10.0\n"
        "ddd refs/tags/not-a-version"
    )
    tags = parse_remote_tags(text)
    assert tags == ["0.9.0", "0.10.0", "v0.10.0", "not-a-version"]
    assert latest_semver_tag(tags) == "0.10.0"
    assert resolve_ref(tags, "0.9.0") == "0.9.0"
    assert resolve_ref(tags, "") == "0.10.0"
    assert resolve_ref(tags, "9.9.9") == "0.10.0"
    assert resolve_ref([], "0.1.0") == "main"
    assert resolve_ref(["v0.2.0"], "") == "v0.2.0"


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

