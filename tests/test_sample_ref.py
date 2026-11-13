"""One resolver for beer, travel, and yelp sample clones."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from zeus_dev_helper_mcp.beer import BEER_REPO_GIT, ENV_BEER_DIR, clone_beer_sample
from zeus_dev_helper_mcp.sample_ref import (
    advertised_clone_command,
    latest_semver_tag,
    manual_clone_command,
    parse_remote_tags,
    resolve_ref,
    shallow_clone_ref,
)
from zeus_dev_helper_mcp.travel import (
    ENV_TRAVEL_DIR,
    TRAVEL_REPO_GIT,
    clone_travel_sample,
)
from zeus_dev_helper_mcp.yelp import ENV_YELP_DIR, YELP_REPO_GIT, clone_yelp_sample

_REPO = "https://example.test/sample.git"
_ENV = "DEMO_BEER_SAMPLE_DIR"
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

    monkeypatch.setattr("zeus_dev_helper_mcp.sample_ref.subprocess.run", fake_run)
    return cmds


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


@pytest.mark.parametrize(("version", "tags", "branch"), _REF_CASES)
def test_shallow_clone_resolves_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version, tags, branch
) -> None:
    dest = tmp_path / "sample"
    cmds = _git_calls(monkeypatch, tags, dest)
    kwargs = {} if version is None else {"version": version}
    out = shallow_clone_ref(dest=dest, repo_url=_REPO, env_name=_ENV, **kwargs)
    clones = [cmd for cmd in cmds if len(cmd) > 1 and cmd[1] == "clone"]
    assert out["ok"] is True
    assert out["ref"] == branch
    assert out["requested_version"] == ("" if version is None else version)
    assert len(clones) == 1
    assert _branch_of(clones[0]) == branch
    assert out["clone_cmd"] == " ".join(clones[0])
    assert advertised_clone_command(_REPO, out) == out["clone_cmd"]


def test_ls_remote_failure_does_not_invent_a_clone_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "sample"
    cmds: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        del kwargs
        cmds.append(list(cmd))
        proc = MagicMock()
        proc.returncode = 128
        proc.stderr = "fatal: unable to access"
        proc.stdout = ""
        return proc

    monkeypatch.setattr("zeus_dev_helper_mcp.sample_ref.subprocess.run", fake_run)
    out = shallow_clone_ref(dest=dest, repo_url=_REPO, version="0.1.0", env_name=_ENV)
    assert out["ok"] is False
    assert out["failure_class"] == "clone_failed"
    assert out.get("ref") is None
    assert not any(len(cmd) > 1 and cmd[1] == "clone" for cmd in cmds)
    assert "git clone" not in out["next_action"]
    assert "clone manually" in out["next_action"]
    assert _ENV in out["next_action"]
    assert advertised_clone_command(_REPO, out) == ""
    assert not dest.exists()


def test_missing_git_before_a_ref_does_not_name_a_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "sample"

    def fake_run(cmd, **kwargs):
        del cmd, kwargs
        raise FileNotFoundError("git")

    monkeypatch.setattr("zeus_dev_helper_mcp.sample_ref.subprocess.run", fake_run)
    out = shallow_clone_ref(dest=dest, repo_url=_REPO, version="0.1.0", env_name=_ENV)
    assert out["ok"] is False
    assert out["error"] == "git not found on PATH"
    assert "git clone" not in out["next_action"]
    assert not dest.exists()


def test_clone_timeout_names_the_resolved_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "sample"

    def fake_run(cmd, **kwargs):
        del kwargs
        cmd = list(cmd)
        if "ls-remote" in cmd:
            proc = MagicMock()
            proc.returncode = 0
            proc.stderr = ""
            proc.stdout = _tag_text(["0.1.0"])
            return proc
        dest.mkdir()
        (dest / "PARTIAL").write_text("left behind", encoding="utf-8")
        raise subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr("zeus_dev_helper_mcp.sample_ref.subprocess.run", fake_run)
    out = shallow_clone_ref(dest=dest, repo_url=_REPO, version="9.9.9", env_name=_ENV)
    assert out["ok"] is False
    assert out["ref"] == "0.1.0"
    assert out["next_action"] == (
        f"Retry use_sample or {manual_clone_command(_REPO, '0.1.0')} and set {_ENV}"
    )
    assert advertised_clone_command(_REPO, out) == out["clone_cmd"]
    assert "--branch 0.1.0" in out["clone_cmd"]
    assert not dest.exists()


def test_failed_clone_names_the_resolved_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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

    monkeypatch.setattr("zeus_dev_helper_mcp.sample_ref.subprocess.run", fake_run)
    out = shallow_clone_ref(dest=dest, repo_url=_REPO, version="0.2.0", env_name=_ENV)
    clones = [cmd for cmd in cmds if len(cmd) > 1 and cmd[1] == "clone"]
    assert out["ok"] is False
    assert out["ref"] == "0.2.0"
    assert len(clones) == 1
    assert out["next_action"] == (
        f"Fix network/git access, or {manual_clone_command(_REPO, '0.2.0')} and set {_ENV}"
    )
    assert not dest.exists()


@pytest.mark.parametrize(
    ("clone", "repo", "env_name"),
    [
        (clone_beer_sample, BEER_REPO_GIT, ENV_BEER_DIR),
        (clone_travel_sample, TRAVEL_REPO_GIT, ENV_TRAVEL_DIR),
        (clone_yelp_sample, YELP_REPO_GIT, ENV_YELP_DIR),
    ],
)
def test_wrapper_passes_version_and_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    clone,
    repo: str,
    env_name: str,
) -> None:
    seen: dict[str, object] = {}

    def fake(**kwargs):
        seen.update(kwargs)
        return {
            "ok": False,
            "cloned": False,
            "failure_class": "clone_failed",
            "error": "stop",
            "next_action": "stop",
        }

    monkeypatch.setattr("zeus_dev_helper_mcp.sample_ref.shallow_clone_ref", fake)
    out = clone(dest=tmp_path / "sample", version="0.1.0")
    assert out["ok"] is False
    assert seen["version"] == "0.1.0"
    assert seen["repo_url"] == repo
    assert seen["env_name"] == env_name
