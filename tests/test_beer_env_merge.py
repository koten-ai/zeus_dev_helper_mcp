"""ZDM-41: beer .env merges the sample template and resolves the LLM group."""

from __future__ import annotations

import json
import stat
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.scaffold import use_sample

OPENAI_KEY = "zdm41-openai-sentinel"
XAI_KEY = "zdm41-xai-sentinel"
KEPT_KEY = "zdm41-kept-sentinel"
PASSWORD = "zdm41-password-sentinel"
BEARER = "zdm41-bearer-sentinel"
USER = "tap-user"

_EXAMPLE = """\
# Copy to .env (never commit .env). LLM_API_KEY is required for this sample to work.
ZEUS_URL=http://localhost:8080
ZEUS_BUCKET=beer-sample
ZEUS_SCOPE=_default
ZEUS_COLLECTION=_default
ZEUS_MODE=analytics
PORT=8090
CELLAR_CACHE_TTL=600
LLM_BASE_URL=https://api.x.ai/v1
LLM_API_KEY=
LLM_MODEL=grok-4.5-latest
# ZEUS_USERNAME=
# ZEUS_PASSWORD=
# ZEUS_BEARER_TOKEN=
"""

_CONFIG = """\
{
  "llm": {
    "provider": "xai",
    "base_url": "LLM_BASE_URL",
    "model": "LLM_MODEL",
    "api_key_env": "LLM_API_KEY"
  }
}
"""

_CURRENT_MAIN = """\
agent.run_turn
catalog.load_for_turn
HttpxCatalogRemote
OpenAICompatibleLlmClient
FsCatalogStore
pour_enabled
catalog_find_body
search_hit_state
offset_page_differs
"""


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "ZEUS_USERNAME",
        "ZEUS_USER",
        "ZEUS_PASSWORD",
        "ZEUS_BEARER_TOKEN",
        "ZEUS_TOKEN",
        "LLM_API_KEY",
        "XAI_API_KEY",
        "OPENAI_API_KEY",
        "LLM_BASE_URL",
        "LLM_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)


def _cfg(tmp_path: Path, **kwargs: object) -> HelperConfig:
    values = {
        "zeus_url": "http://lab.example:8080",
        "default_bucket": "beer-sample",
        "default_scope": "_default",
        "state_dir": tmp_path / "state",
    }
    values.update(kwargs)
    return HelperConfig(**values)  # type: ignore[arg-type]


def _plant(dest: Path, *, env: str = "") -> None:
    dest.mkdir(parents=True)
    (dest / "README.md").write_text("# The Sample Tap\npython main.py\n", encoding="utf-8")
    (dest / "main.py").write_text(_CURRENT_MAIN, encoding="utf-8")
    (dest / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    (dest / "static").mkdir()
    (dest / "static" / "index.html").write_text("<html></html>\n", encoding="utf-8")
    (dest / ".env.example").write_text(_EXAMPLE, encoding="utf-8")
    (dest / "config.json").write_text(_CONFIG, encoding="utf-8")
    if env:
        (dest / ".env").write_text(env, encoding="utf-8")


def _fake_clone(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd, **kwargs):
        del kwargs
        dest = Path(cmd[-1])
        _plant(dest)
        proc = MagicMock()
        proc.returncode = 0
        proc.stderr = ""
        proc.stdout = ""
        return proc

    monkeypatch.setattr("zeus_dev_helper_mcp.beer.subprocess.run", fake_run)


def _assert_no_secrets(payload: dict) -> None:
    blob = json.dumps(payload)
    for secret in (OPENAI_KEY, XAI_KEY, KEPT_KEY, PASSWORD, BEARER):
        assert secret not in blob


def _assert_coach(out: dict) -> None:
    action = str(out.get("next_action") or "")
    run = str(out.get("run") or "")
    assert "cp .env.example .env" not in action
    assert "cp .env.example .env" not in run
    assert out["configuration_policy"] == "preserve_existing_then_fill_missing"
    assert out["env_template"] == ".env.example"
    assert out["env_target"] == ".env"
    assert out["verification"] == {
        "authentication": "not_checked",
        "beer_list": "not_checked",
        "brewery_list": "not_checked",
        "search": "not_checked",
    }
    assert "sibling sample .env" in action
    assert "not proof the user has no key" in action
    assert "load_process_login" in action
    assert "Restart the app after an env change." in action
    assert "website_green" in action
    assert "named beer cards" in action
    assert "brewery-card check stays separate" in action
    assert "describe 200 does not mark the page ready" in action
    assert "Do not clone demo_travel_sample." in action
    assert "https://github.com/koten-ai/demo_beer_sample" in action
    assert "python main.py" in action


def test_fresh_clone_merges_the_sample_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear(monkeypatch)
    _fake_clone(monkeypatch)
    out = use_sample(
        _cfg(tmp_path),
        sample="beer",
        parent_dir=str(tmp_path),
        project_name="demo_beer_sample",
    )
    assert out["ok"] is True
    assert out["cloned"] is True
    root = Path(out["local_dir"])
    env = (root / ".env").read_text(encoding="utf-8")
    assert "LLM_MODEL=grok-4.5-latest" in env
    assert "LLM_BASE_URL=https://api.x.ai/v1" in env
    assert "ZEUS_URL=http://lab.example:8080" in env
    assert "grok-4-1-fast-non-reasoning" not in env
    assert "LLM_API_KEY=" in env
    assert stat.S_IMODE((root / ".env").stat().st_mode) == 0o600
    config = (root / "config.json").read_text(encoding="utf-8")
    assert '"model": "LLM_MODEL"' in config
    assert "grok-4-1-fast-non-reasoning" not in config
    assert "LLM_API_KEY" in config
    assert out["missing_app_settings"] == ["LLM_API_KEY"]
    assert "LLM_BASE_URL" not in out["missing_app_settings"]
    assert "LLM_MODEL" not in out["missing_app_settings"]
    assert "LLM_API_KEY" in out["missing_process_settings"]
    assert "LLM_BASE_URL" not in out["missing_process_settings"]
    assert "LLM_MODEL" not in out["missing_process_settings"]
    _assert_coach(out)
    _assert_no_secrets(out)
    assert "demo_travel_sample" not in str(out.get("repo"))


def test_existing_env_keeps_values_and_gains_template_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear(monkeypatch)
    root = tmp_path / "demo_beer_sample"
    _plant(
        root,
        env=(
            "ZEUS_URL=http://keep.example:8080\n"
            "PORT=54321\n"
            "LLM_API_KEY=" + KEPT_KEY + "\n"
        ),
    )
    config_before = (root / "config.json").read_text(encoding="utf-8")
    main_before = (root / "main.py").read_text(encoding="utf-8")
    out = use_sample(_cfg(tmp_path), sample="beer", sample_dir=str(root))
    assert out["ok"] is True
    assert out.get("cloned") is False
    env = (root / ".env").read_text(encoding="utf-8")
    assert "ZEUS_URL=http://keep.example:8080" in env
    assert "ZEUS_URL=http://localhost:8080" not in env
    assert f"LLM_API_KEY={KEPT_KEY}" in env
    assert "LLM_BASE_URL=https://api.x.ai/v1" in env
    assert "LLM_MODEL=grok-4.5-latest" in env
    assert "grok-4-1-fast-non-reasoning" not in env
    assert (root / "config.json").read_text(encoding="utf-8") == config_before
    assert (root / "main.py").read_text(encoding="utf-8") == main_before
    assert "LLM_API_KEY" not in out["missing_app_settings"]
    assert "LLM_API_KEY" in out["missing_process_settings"]
    assert stat.S_IMODE((root / ".env").stat().st_mode) == 0o600
    _assert_coach(out)
    _assert_no_secrets(out)


def test_openai_key_is_not_paired_with_the_xai_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", OPENAI_KEY)
    monkeypatch.setenv("ZEUS_BEARER_TOKEN", BEARER)
    _fake_clone(monkeypatch)
    out = use_sample(
        _cfg(tmp_path, zeus_auth_mode="basic"),
        sample="beer",
        parent_dir=str(tmp_path),
        project_name="demo_beer_sample",
    )
    # Basic auth with no username stops before the clone writes the app.
    assert out["ok"] is False
    assert out["failure_class"] == "login_not_in_process"

    monkeypatch.setenv("ZEUS_USERNAME", USER)
    monkeypatch.setenv("ZEUS_PASSWORD", PASSWORD)
    out = use_sample(
        _cfg(tmp_path, zeus_auth_mode="basic"),
        sample="beer",
        parent_dir=str(tmp_path),
        project_name="demo_beer_sample",
    )
    assert out["ok"] is True
    root = Path(out["local_dir"])
    env = (root / ".env").read_text(encoding="utf-8")
    assert "LLM_API_KEY=" in env
    assert OPENAI_KEY not in env
    assert "LLM_BASE_URL=https://api.x.ai/v1" in env
    assert "LLM_MODEL=grok-4.5-latest" in env
    assert f"ZEUS_USERNAME={USER}" in env
    assert f"ZEUS_PASSWORD={PASSWORD}" in env
    assert BEARER not in env
    assert "ZEUS_BEARER_TOKEN=" not in env or env.count(BEARER) == 0
    assert out["skipped_llm_alias"] == "OPENAI_API_KEY"
    assert out["missing_app_settings"] == ["LLM_API_KEY"]
    assert out["pour_enabled"] is False
    assert "smoke_test_agent" not in (out.get("recommended_tools") or [])
    action = str(out.get("next_action") or "")
    assert "OPENAI_API_KEY" in action
    assert "do not match that provider" in action
    _assert_coach(out)
    _assert_no_secrets(out)


def test_xai_key_copies_when_the_template_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("XAI_API_KEY", XAI_KEY)
    _fake_clone(monkeypatch)
    out = use_sample(
        _cfg(tmp_path),
        sample="beer",
        parent_dir=str(tmp_path),
        project_name="demo_beer_sample",
    )
    assert out["ok"] is True
    root = Path(out["local_dir"])
    env = (root / ".env").read_text(encoding="utf-8")
    assert f"LLM_API_KEY={XAI_KEY}" in env
    assert "LLM_MODEL=grok-4.5-latest" in env
    assert "grok-4-1-fast-non-reasoning" not in env
    assert "LLM_API_KEY" not in out["missing_app_settings"]
    assert out.get("skipped_llm_alias") in (None, "")
    _assert_no_secrets(out)
    _assert_coach(out)


def test_openai_pair_replaces_the_template_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", OPENAI_KEY)
    monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    _fake_clone(monkeypatch)
    out = use_sample(
        _cfg(tmp_path),
        sample="beer",
        parent_dir=str(tmp_path),
        project_name="demo_beer_sample",
    )
    assert out["ok"] is True
    env = (Path(out["local_dir"]) / ".env").read_text(encoding="utf-8")
    assert f"LLM_API_KEY={OPENAI_KEY}" in env
    assert "LLM_BASE_URL=https://api.openai.com/v1" in env
    assert "LLM_MODEL=gpt-4o" in env
    assert "https://api.x.ai/v1" not in env
    assert "grok-4.5-latest" not in env
    assert out["missing_app_settings"] == []
    _assert_no_secrets(out)
