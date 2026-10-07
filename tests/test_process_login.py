"""ZDM-23: load a mode-600 env file into this process. Names only."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from zeus_dev_helper_mcp.process_login import load_process_login

PASSWORD = "zdm23-password-sentinel"
USER = "zdm23-user"
LLM = "zdm23-llm-sentinel"
_KEYS = (
    "ZEUS_USERNAME",
    "ZEUS_USER",
    "ZEUS_PASSWORD",
    "ZEUS_BEARER_TOKEN",
    "ZEUS_TOKEN",
    "LLM_API_KEY",
    "XAI_API_KEY",
    "OPENAI_API_KEY",
)


@pytest.fixture
def clean_login() -> None:
    """Restore login env even when the tool assigns os.environ directly."""
    saved = {name: os.environ.get(name) for name in _KEYS}
    for name in _KEYS:
        os.environ.pop(name, None)
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _write(path: Path, text: str, mode: int = 0o600) -> None:
    path.write_text(text, encoding="utf-8")
    os.chmod(path, mode)


def test_loads_names_and_hides_values(tmp_path: Path, clean_login: None) -> None:
    path = tmp_path / "login.env"
    _write(
        path,
        f"ZEUS_USER={USER}\nZEUS_PASSWORD={PASSWORD}\nLLM_API_KEY={LLM}\nOTHER=nope\n",
    )
    out = load_process_login(str(path))
    blob = json.dumps(out)
    assert out["ok"] is True
    assert out["failure_class"] is None
    assert "ZEUS_USERNAME" in out["loaded"]
    assert "ZEUS_PASSWORD" in out["loaded"]
    assert "LLM_API_KEY" in out["loaded"]
    assert "OTHER" not in out["loaded"]
    assert os.environ["ZEUS_USERNAME"] == USER
    assert os.environ["ZEUS_PASSWORD"] == PASSWORD
    assert os.environ["LLM_API_KEY"] == LLM
    assert PASSWORD not in blob
    assert LLM not in blob
    assert USER not in blob
    assert "readiness_check" in out["next_action"]


def test_refuses_a_loose_mode(tmp_path: Path, clean_login: None) -> None:
    path = tmp_path / "login.env"
    _write(path, f"ZEUS_USERNAME={USER}\nZEUS_PASSWORD={PASSWORD}\n", mode=0o644)
    out = load_process_login(str(path))
    blob = json.dumps(out)
    assert out["ok"] is False
    assert out["failure_class"] == "login_not_in_process"
    assert "mode 600" in out["next_action"]
    assert PASSWORD not in blob
    assert os.environ.get("ZEUS_PASSWORD") in (None, "")


def test_refuses_a_missing_file(tmp_path: Path, clean_login: None) -> None:
    out = load_process_login(str(tmp_path / "missing.env"))
    assert out["ok"] is False
    assert out["loaded"] == []
    assert "not on disk" in out["next_action"]
    empty = load_process_login("  ")
    assert empty["ok"] is False
    assert "mode-600" in empty["next_action"]


def test_incomplete_file_stays_red(tmp_path: Path, clean_login: None) -> None:
    path = tmp_path / "login.env"
    _write(path, f"ZEUS_USERNAME={USER}\n")
    out = load_process_login(str(path))
    assert out["ok"] is False
    assert out["failure_class"] == "login_not_in_process"
    assert "ZEUS_PASSWORD" in out["next_action"]
    assert USER not in json.dumps(out)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
