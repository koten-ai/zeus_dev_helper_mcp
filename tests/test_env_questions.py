"""Missing login and LLM settings tell the agent what to ask. No secret values."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.env_questions import (
    llm_options,
    llm_options_from_example,
    missing_login_names,
)

SECRET = "sk-env-question-sentinel"
_BEER_EXAMPLE = """
# Grok: https://api.x.ai/v1
# OpenAI: https://api.openai.com/v1
# Anthropic: https://api.anthropic.com/v1
# Gemini (OpenAI-compatible): https://generativelanguage.googleapis.com/v1beta/openai/
LLM_BASE_URL=https://api.x.ai/v1
LLM_API_KEY=
LLM_MODEL=grok-4.5-latest
"""


def test_builtin_options_use_the_env_example_defaults() -> None:
    options = llm_options()
    by_id = {row["id"]: row for row in options}
    assert list(by_id) == ["grok", "openai", "anthropic", "gemini", "other"]
    assert by_id["grok"]["base_url"] == "https://api.x.ai/v1"
    assert by_id["grok"]["model"] == "grok-4.5-latest"
    assert by_id["openai"]["base_url"] == "https://api.openai.com/v1"
    assert by_id["openai"]["model"] == "gpt-5.6-sol"
    assert by_id["anthropic"]["base_url"] == "https://api.anthropic.com/v1"
    assert by_id["anthropic"]["model"] == "claude-opus-5-5"
    assert by_id["gemini"]["base_url"].startswith(
        "https://generativelanguage.googleapis.com/v1beta/openai"
    )
    assert by_id["gemini"]["model"] == "gemini-3.8-flash"
    assert by_id["other"]["base_url"] == ""
    assert by_id["other"]["model"] == ""


def test_beer_example_comments_fill_the_same_models() -> None:
    parsed = llm_options_from_example(_BEER_EXAMPLE)
    assert parsed is not None
    by_id = {row["id"]: row for row in parsed}
    assert by_id["openai"]["model"] == "gpt-5.6-sol"
    assert by_id["anthropic"]["model"] == "claude-opus-5-5"
    assert by_id["gemini"]["model"] == "gemini-3.8-flash"
    assert by_id["gemini"]["label"] == "Gemini"
    assert by_id["other"]["id"] == "other"


def test_comment_model_overrides_the_default() -> None:
    parsed = llm_options_from_example("# OpenAI: https://api.openai.com/v1 model gpt-custom\n")
    assert parsed is not None
    assert parsed[0]["model"] == "gpt-custom"


def test_missing_login_names_follow_the_process(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZEUS_USERNAME", raising=False)
    monkeypatch.delenv("ZEUS_USER", raising=False)
    monkeypatch.delenv("ZEUS_PASSWORD", raising=False)
    assert missing_login_names() == ["ZEUS_USERNAME", "ZEUS_PASSWORD"]
    monkeypatch.setenv("ZEUS_USERNAME", "tap")
    assert missing_login_names() == ["ZEUS_PASSWORD"]


def test_validate_env_asks_for_the_provider_before_the_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ZEUS_URL", "http://127.0.0.1:8080")
    monkeypatch.setenv("ZEUS_AUTH_MODE", "basic")
    monkeypatch.delenv("ZEUS_USERNAME", raising=False)
    monkeypatch.delenv("ZEUS_USER", raising=False)
    monkeypatch.delenv("ZEUS_PASSWORD", raising=False)
    for name in ("LLM_API_KEY", "XAI_API_KEY", "OPENAI_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.server.list_modes",
        lambda cfg: {"modes": [{"mode": "analytics"}]},
    )
    from zeus_dev_helper_mcp.config import reload_config
    from zeus_dev_helper_mcp.server import validate_env

    reload_config()
    out = validate_env()
    blob = json.dumps(out)
    assert out["ok"] is False
    assert "has_llm_key=true" in out["next_action"]
    assert out["llm_choice_required"] is True
    ids = [row["id"] for row in out["llm_options"]]
    assert ids == ["grok", "openai", "anthropic", "gemini", "other"]
    envs = [row["env"] for row in out["ask_user"]]
    assert envs[:2] == ["ZEUS_USERNAME", "ZEUS_PASSWORD"]
    assert envs[2:] == ["LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"]
    assert SECRET not in blob
    openai = next(row for row in out["llm_options"] if row["id"] == "openai")
    assert openai["model"] == "gpt-5.6-sol"


def test_direct_opt_out_does_not_ask_for_an_llm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ZEUS_AUTH_MODE", "none")
    for name in ("LLM_API_KEY", "XAI_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.server.list_modes",
        lambda cfg: {"modes": []},
    )
    from zeus_dev_helper_mcp.checklist import load_checklist, save_checklist
    from zeus_dev_helper_mcp.config import reload_config
    from zeus_dev_helper_mcp.prereqs import save_prereqs
    from zeus_dev_helper_mcp.server import validate_env

    cfg = reload_config()
    save_prereqs(
        cfg,
        {
            "has_llm_key": False,
            "zeus_url": "http://127.0.0.1:8080",
            "bucket": "travel-sample",
            "scope": "_default",
            "auth_mode": "none",
        },
    )
    data = load_checklist(cfg)
    data["meta"] = {"sample": "travel"}
    save_checklist(cfg, data)
    out = validate_env()
    assert out["ok"] is True
    assert "llm_options" not in out
    assert "ask_user" not in out


def test_smoke_lists_providers_when_the_key_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("zeus_client")
    for name in ("LLM_API_KEY", "XAI_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    from zeus_dev_helper_mcp.smoke import smoke_test_agent

    cfg = HelperConfig(
        has_llm_key=True,
        zeus_url="http://127.0.0.1:8080",
        state_dir=tmp_path / "state",
    )
    out = smoke_test_agent(cfg, update_checklist=False)
    blob = json.dumps(out)
    assert out["failure_class"] == "llm_key_missing"
    assert out["llm_choice_required"] is True
    assert "has_llm_key" in out["next_action"]
    assert [row["env"] for row in out["ask_user"]] == [
        "LLM_BASE_URL",
        "LLM_MODEL",
        "LLM_API_KEY",
    ]
    assert SECRET not in blob


def test_verify_local_setup_asks_when_the_app_key_is_missing(tmp_path: Path) -> None:
    from zeus_dev_helper_mcp.beer import write_beer_env_example
    from zeus_dev_helper_mcp.scaffold import verify_local_setup

    root = tmp_path / "app"
    write_beer_env_example(
        HelperConfig(zeus_url="http://127.0.0.1:8080", default_bucket="beer-sample"),
        root,
    )
    (root / "config.json").write_text(
        json.dumps({"llm": {"api_key_env": "LLM_API_KEY"}}),
        encoding="utf-8",
    )
    (root / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (root / "requirements.txt").write_text("kotenai-zeus-client\n", encoding="utf-8")
    out = verify_local_setup(
        HelperConfig(state_dir=tmp_path / "state"),
        str(root),
    )
    assert out["llm_choice_required"] is True
    by_id = {row["id"]: row for row in out["llm_options"]}
    assert by_id["anthropic"]["model"] == "claude-opus-5-5"
    assert by_id["gemini"]["model"] == "gemini-3.8-flash"
    assert SECRET not in json.dumps(out)


def test_sample_build_questions_prefill_text_and_hide_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zeus_dev_helper_mcp.env_questions import sample_build_questions

    password = "zdm48-password-sentinel"
    bearer = "zdm48-bearer-sentinel"
    monkeypatch.setenv("ZEUS_USERNAME", "tap-user")
    monkeypatch.setenv("ZEUS_PASSWORD", password)
    monkeypatch.setenv("ZEUS_BEARER_TOKEN", bearer)
    monkeypatch.setenv("LLM_API_KEY", SECRET)
    monkeypatch.setenv("LLM_MODEL", "grok-custom")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("ZEUS_AUTH_MODE", raising=False)
    root = tmp_path / "app"
    root.mkdir()
    (root / ".env").write_text(
        "ZEUS_USERNAME=from-app\nZEUS_PASSWORD=from-app-secret\n",
        encoding="utf-8",
    )
    rows = sample_build_questions("travel", root=root, cfg=None)
    blob = json.dumps(rows)
    envs = [row["env"] for row in rows if row.get("env")]
    assert envs[0] == "ZEUS_AUTH_MODE"
    assert envs[-1] == "LLM_API_KEY"
    by_env = {row["env"]: row for row in rows if row.get("env")}
    assert by_env["ZEUS_USERNAME"]["kind"] == "text"
    assert by_env["ZEUS_USERNAME"]["default"] == "tap-user"
    assert by_env["ZEUS_USERNAME"]["when"] == {"env": "ZEUS_AUTH_MODE", "equals": "basic"}
    assert by_env["ZEUS_PASSWORD"]["kind"] == "password"
    assert "default" not in by_env["ZEUS_PASSWORD"]
    assert by_env["ZEUS_PASSWORD"]["when"]["equals"] == "basic"
    assert by_env["ZEUS_BEARER_TOKEN"]["kind"] == "password"
    assert by_env["ZEUS_BEARER_TOKEN"]["when"]["equals"] == "bearer"
    assert "default" not in by_env["ZEUS_BEARER_TOKEN"]
    assert by_env["LLM_BASE_URL"]["when"] == {"id": "llm_provider", "equals": "other"}
    assert "default" not in by_env["LLM_BASE_URL"]
    assert by_env["LLM_MODEL"]["kind"] == "text"
    assert by_env["LLM_MODEL"]["default"] == "grok-custom"
    assert by_env["LLM_API_KEY"]["kind"] == "password"
    assert "default" not in by_env["LLM_API_KEY"]
    provider = next(row for row in rows if row.get("id") == "llm_provider")
    assert provider["choices"] == ["grok", "openai", "anthropic", "gemini", "other"]
    other_name = next(row for row in rows if row.get("id") == "provider_name")
    assert other_name["kind"] == "text"
    assert "env" not in other_name
    assert other_name["when"]["equals"] == "other"
    assert password not in blob
    assert bearer not in blob
    assert SECRET not in blob
    assert "from-app-secret" not in blob


def test_beer_username_defaults_to_tester_beer_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from zeus_dev_helper_mcp.env_questions import sample_build_questions

    monkeypatch.delenv("ZEUS_USERNAME", raising=False)
    monkeypatch.delenv("ZEUS_USER", raising=False)
    rows = sample_build_questions("beer")
    username = next(row for row in rows if row.get("env") == "ZEUS_USERNAME")
    assert username["default"] == "tester_beer"


def test_sample_username_comes_from_the_app_env_example(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zeus_dev_helper_mcp.env_questions import sample_build_questions

    monkeypatch.delenv("ZEUS_USERNAME", raising=False)
    monkeypatch.delenv("ZEUS_USER", raising=False)
    root = tmp_path / "travel"
    root.mkdir()
    (root / ".env.example").write_text("ZEUS_USERNAME=from-example\n", encoding="utf-8")
    rows = sample_build_questions("travel", root=root)
    username = next(row for row in rows if row.get("env") == "ZEUS_USERNAME")
    assert username["default"] == "from-example"
