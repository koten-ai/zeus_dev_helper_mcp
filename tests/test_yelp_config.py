"""ZDM-23: yelp config.json is mode 600 and the client pin is the git tag."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.yelp import ensure_yelp_sample
from zeus_dev_helper_mcp.yelp_config import pin_yelp_client, write_yelp_config

PASSWORD = "zdm23-password-sentinel"
USER = "zdm23-user"
LLM = "zdm23-llm-sentinel"


def _cfg(tmp_path: Path, *, auth: str = "none") -> HelperConfig:
    return HelperConfig(
        state_dir=tmp_path / "state",
        zeus_url="http://lab.example:8080",
        zeus_auth_mode=auth,
        default_bucket="yelp-demo",
        default_scope="_default",
    )


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "ZEUS_USERNAME",
        "ZEUS_USER",
        "ZEUS_PASSWORD",
        "LLM_API_KEY",
        "XAI_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def _layout(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text("# yelp\n", encoding="utf-8")
    frontend = root / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text("{}\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        "[project]\n"
        'name = "local-guide"\n'
        "dependencies = [\n"
        '  "kotenai-zeus-client @ file:../zeus_client_python",\n'
        "]\n",
        encoding="utf-8",
    )


def test_config_is_private_and_omits_the_llm_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("ZEUS_USERNAME", USER)
    monkeypatch.setenv("ZEUS_PASSWORD", PASSWORD)
    monkeypatch.setenv("LLM_API_KEY", LLM)
    root = tmp_path / "demo_yelp"
    _layout(root)
    (root / "config.example.json").write_text(
        json.dumps({"scope_contracts": {"yelp-demo/_default": {"hash": "abc123"}}}) + "\n",
        encoding="utf-8",
    )
    cfg = _cfg(tmp_path, auth="basic")
    out = ensure_yelp_sample(cfg, sample_dir=str(root))
    blob = json.dumps(out)
    assert out["ok"] is True
    assert PASSWORD not in blob
    assert LLM not in blob
    path = root / "config.json"
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert "config.json" in (root / ".gitignore").read_text(encoding="utf-8")
    assert data["zeus"]["url"] == "http://lab.example:8080"
    assert data["zeus"]["username"] == USER
    assert data["zeus"]["password"] == PASSWORD
    assert data["zeus"]["enable_durable_sessions"] is False
    assert data["zeus"]["scope_credentials"]["yelp-demo/_default"]["password"] == PASSWORD
    assert data["llm_provider"]["api_key"] == ""
    assert data["llm_provider"]["api_key_env"] == "LLM_API_KEY"
    assert data["scope_contracts"]["yelp-demo/_default"]["hash"] == "abc123"
    assert LLM not in text
    assert "zeus.password" in out["app_config"]["fields"]
    pinned = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert "file:../zeus_client_python" not in pinned
    assert "kotenai-zeus-client @ git+ssh://git@github.com/koten-ai/zeus_client_python.git@0.3.1-alpha" in pinned
    assert pinned.count("kotenai-zeus-client") == 1


def test_missing_basic_login_keeps_the_clone_and_skips_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear(monkeypatch)
    root = tmp_path / "demo_yelp"
    _layout(root)
    cfg = _cfg(tmp_path, auth="basic")
    out = ensure_yelp_sample(cfg, sample_dir=str(root))
    assert out["ok"] is False
    assert out["failure_class"] == "login_not_in_process"
    assert out["local_dir"] == str(root.resolve())
    assert "load_process_login" in out["next_action"]
    assert not (root / "config.json").exists()
    assert PASSWORD not in json.dumps(out)


def test_auth_none_writes_config_without_a_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("LLM_API_KEY", LLM)
    root = tmp_path / "demo_yelp"
    _layout(root)
    out = write_yelp_config(_cfg(tmp_path), root)
    data = json.loads((root / "config.json").read_text(encoding="utf-8"))
    assert out["created"] is True
    assert "password" not in data["zeus"]
    assert "scope_contracts" not in data
    assert LLM not in (root / "config.json").read_text(encoding="utf-8")
    assert LLM not in json.dumps(out)


def test_existing_config_is_left_in_place(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("ZEUS_PASSWORD", PASSWORD)
    root = tmp_path / "demo_yelp"
    _layout(root)
    path = root / "config.json"
    path.write_text('{"keep": true}\n', encoding="utf-8")
    os.chmod(path, 0o644)
    out = write_yelp_config(_cfg(tmp_path, auth="basic"), root)
    assert out["created"] is False
    assert path.read_text(encoding="utf-8") == '{"keep": true}\n'
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert PASSWORD not in json.dumps(out)
    assert pin_yelp_client(root)["patched"] is True
