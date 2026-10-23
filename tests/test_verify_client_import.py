"""ZDM-42: a missing zeus_client import names the Helper interpreter."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.sample_support import observe_sample_support
from zeus_dev_helper_mcp.scaffold import missing_zeus_client_action, verify_local_setup

_SECRET = "sk-live-abcdefghijklmnopqrstuvwxyz"
_NOW = datetime(2026, 10, 23, 19, 55, 26, tzinfo=UTC)
_LAUNCH = "uvx --from 'zeus-dev-helper-mcp[agent]' zeus-dev-helper-mcp"


def test_missing_import_names_the_helper_and_the_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom() -> object:
        raise ImportError(f"No module named 'zeus_client' {_SECRET}")

    monkeypatch.setattr("zeus_dev_helper_mcp.scaffold._load_zeus_client", _boom)
    cfg = HelperConfig(state_dir=tmp_path / "state")
    app = tmp_path / "beer-explorer"
    app.mkdir()
    (app / ".env").write_text(f"LLM_API_KEY={_SECRET}\n", encoding="utf-8")

    out = verify_local_setup(cfg, str(app))

    assert out["ok"] is False
    check = next(item for item in out["checks"] if item["name"] == "import_zeus_client")
    action = missing_zeus_client_action()
    assert check["ok"] is False
    assert check["error"] == "No module named 'zeus_client'"
    assert check["interpreter"] == sys.executable
    assert check["next_action"] == action
    assert out["next_action"] == action
    assert sys.executable in action
    assert "zeus_client" in action
    assert "app .venv does not satisfy this check" in action
    assert "zeus-dev-helper-mcp[agent]" in action
    assert "restart the MCP server" in action
    blob = json.dumps(out)
    assert _SECRET not in blob
    assert "pip install kotenai-zeus-client" not in blob

    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / "checklist.json").write_text(
        json.dumps({"meta": {"sample": "beer"}, "phases": []}),
        encoding="utf-8",
    )
    (cfg.state_dir / "beer-sample-build.md").write_text("creation\n", encoding="utf-8")
    observe_sample_support(
        cfg,
        "verify_local_setup",
        {"target_dir": str(app)},
        out,
        now=_NOW,
    )
    journal = (cfg.state_dir / "beer-sample-support.md").read_text(encoding="utf-8")
    assert action in journal
    assert "Install missing deps or scaffold_app if files missing" not in journal
    assert _SECRET not in journal
    assert "pip install kotenai-zeus-client" not in journal


def test_host_docs_launch_uvx_with_the_agent_extra() -> None:
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    matrix = (root / "docs" / "HOST-MATRIX.md").read_text(encoding="utf-8")
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert _LAUNCH in agents
    for text in (readme, matrix):
        assert _LAUNCH in text
        assert "default_permissions = \"workspace-net\"" in text
        assert "extends = \":workspace\"" in text
        assert "enabled = true" in text
        assert "[Errno -2]" in text
        assert "EAI_NONAME" in text
        assert "sandbox_mode" in text
        assert "sandbox_workspace_write" in text
        assert "requirements.txt" in text
    assert "uvx zeus-dev-helper-mcp\n" not in readme
    assert "uvx zeus-dev-helper-mcp\n" not in matrix
