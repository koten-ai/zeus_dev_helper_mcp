"""Python 3.11 floor before a sample installs kotenai-zeus-client."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from zeus_dev_helper_mcp.checklist import load_checklist
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.python_runtime import (
    inspect_app_python,
    launcher,
    pip_block,
    read_version,
    sync_checklist_python,
)
from zeus_dev_helper_mcp.scaffold import scaffold_app, verify_local_setup
from zeus_dev_helper_mcp.website_green import install_app


def _fake_python(path: Path, version: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/sh\necho {version}\n", encoding="utf-8")
    path.chmod(0o755)


def test_this_interpreter_meets_the_floor() -> None:
    version = read_version(sys.executable)
    assert version is not None
    assert version[:2] >= (3, 11)


def test_old_venv_blocks_pip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "app"
    root.mkdir()
    (root / "requirements.txt").write_text(
        "kotenai-zeus-client>=2.4.0,<2.5\n", encoding="utf-8"
    )
    _fake_python(root / ".venv" / "bin" / "python", "3.9.6")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("pip must not run")

    monkeypatch.setattr("zeus_dev_helper_mcp.website_green.subprocess.run", boom)
    out = install_app(root)
    assert out["ok"] is False
    assert out["installed"] is False
    assert out["failure_class"] == "install_failed"
    assert "3.9.6" in out["next_action"]
    assert "3.11" in out["next_action"]


def test_current_venv_reaches_pip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "app"
    root.mkdir()
    (root / "requirements.txt").write_text("python-dotenv>=1.0.0\n", encoding="utf-8")
    _fake_python(root / ".venv" / "bin" / "python", "3.12.1")
    seen: dict[str, object] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> object:
        seen["cmd"] = list(cmd)
        seen["cwd"] = kwargs["cwd"]
        return type("Proc", (), {"returncode": 0})()

    monkeypatch.setattr("zeus_dev_helper_mcp.website_green.subprocess.run", fake_run)
    out = install_app(root)
    assert out["ok"] is True
    assert seen["cmd"][-2:] == ["-r", str(root / "requirements.txt")]
    assert seen["cwd"] == root


def test_launcher_skips_old_python3(monkeypatch: pytest.MonkeyPatch) -> None:
    found = {
        "python3": "/usr/bin/python3",
        "python3.12": "/opt/python3.12",
    }

    def which(name: str) -> str | None:
        return found.get(name)

    def version(exe: str) -> tuple[int, int, int] | None:
        if exe == "/usr/bin/python3":
            return (3, 9, 6)
        if exe == "/opt/python3.12":
            return (3, 12, 1)
        return None

    monkeypatch.setattr("zeus_dev_helper_mcp.python_runtime.shutil.which", which)
    monkeypatch.setattr("zeus_dev_helper_mcp.python_runtime.read_version", version)
    info = launcher()
    assert info["command"] == "python3.12 -m venv .venv"
    assert info["recreate"] == "python3.12 -m venv --clear .venv"
    assert "3.9.6" in info["note"]
    assert info["via"] == "python3.12"


def test_launcher_uses_uv_when_no_newer_python(monkeypatch: pytest.MonkeyPatch) -> None:
    def which(name: str) -> str | None:
        if name == "python3":
            return "/usr/bin/python3"
        if name == "uv":
            return "/usr/bin/uv"
        return None

    monkeypatch.setattr("zeus_dev_helper_mcp.python_runtime.shutil.which", which)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.python_runtime.read_version",
        lambda exe: (3, 9, 6) if exe == "/usr/bin/python3" else None,
    )
    info = launcher()
    assert info["command"] == "uv venv --python 3.12 .venv"
    assert info["recreate"] == "uv venv --python 3.12 --clear .venv"


def test_verify_blocks_old_venv(tmp_path: Path) -> None:
    root = tmp_path / "app"
    root.mkdir()
    _fake_python(root / ".venv" / "bin" / "python", "3.9.6")
    cfg = HelperConfig(state_dir=tmp_path / "state")
    out = verify_local_setup(cfg, str(root))
    assert out["ok"] is False
    python = next(item for item in out["checks"] if item["name"] == "python")
    assert python["ok"] is False
    assert python["version"] == "3.9.6"
    data = load_checklist(cfg)
    item = next(
        row
        for phase in data["phases"]
        for row in phase["items"]
        if row["id"] == "1.1"
    )
    assert item["status"] == "blocked"
    assert "3.9.6" in item["evidence"]
    assert "need >=3.11" in item["evidence"]


def test_verify_marks_python3_done(tmp_path: Path) -> None:
    cfg = HelperConfig(state_dir=tmp_path / "state")
    report = inspect_app_python(None)
    if not report["ok"]:
        pytest.skip("python3 on PATH is older than 3.11")
    out = verify_local_setup(cfg, "")
    python = next(item for item in out["checks"] if item["name"] == "python")
    assert python["ok"] is True
    sync_checklist_python(cfg, report)
    data = load_checklist(cfg)
    item = next(
        row
        for phase in data["phases"]
        for row in phase["items"]
        if row["id"] == "1.1"
    )
    assert item["status"] == "done"


def test_scaffold_run_uses_probed_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.python_runtime.venv_setup_shell",
        lambda: "python3.12 -m venv .venv && source .venv/bin/activate",
    )
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.python_runtime.launch_note",
        lambda: "python3 is 3.9.6. kotenai-zeus-client needs Python 3.11 or newer.",
    )
    cfg = HelperConfig(
        zeus_url="http://localhost:8080",
        default_bucket="beer-sample",
        default_scope="_default",
        state_dir=tmp_path / "state",
    )
    out = scaffold_app(cfg, str(tmp_path / "app"), project_name="demo_app")
    assert out["ok"] is True
    assert "python3.12 -m venv .venv" in out["run"]
    assert "3.9.6" in out["next_action"]
    readme = (Path(out["target_dir"]) / "README.md").read_text(encoding="utf-8")
    assert "python3.12 -m venv .venv" in readme
    assert "Python 3.11 or newer" in readme


def test_pip_block_allows_this_interpreter() -> None:
    assert pip_block(sys.executable, source="the Helper interpreter") is None


def test_beer_quick_start_uses_probed_interpreter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.python_runtime.venv_setup_shell",
        lambda: "python3.12 -m venv .venv && source .venv/bin/activate",
    )
    from zeus_dev_helper_mcp.beer import beer_quick_start

    start = beer_quick_start()
    assert start.startswith("python3.12 -m venv .venv && source .venv/bin/activate && ")
    assert "pip install -r requirements.txt" in start


def test_doctor_blocks_old_python3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("DEMO_BEER_SAMPLE_DIR", raising=False)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.python_runtime.inspect_app_python",
        lambda _root: {
            "ok": False,
            "version": "3.9.6",
            "path": "/usr/bin/python3",
            "source": "python3",
            "evidence": "python3 3.9.6; need >=3.11",
            "message": (
                "python3 is Python 3.9.6. "
                "kotenai-zeus-client needs Python 3.11 or newer."
            ),
        },
    )
    from zeus_dev_helper_mcp.server import doctor

    out = doctor("health")
    assert out["ok"] is False
    assert out["failure_class"] == "install_failed"
    assert out["python"]["version"] == "3.9.6"
    assert "3.9.6" in out["next_action"]
    data = load_checklist(HelperConfig(state_dir=tmp_path / "state"))
    item = next(
        row
        for phase in data["phases"]
        for row in phase["items"]
        if row["id"] == "1.1"
    )
    assert item["status"] == "blocked"
