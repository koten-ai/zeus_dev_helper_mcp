"""ZDM-48: a rewrite of an existing app .env shows up as an env change."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from zeus_dev_helper_mcp.config import HelperConfig

PASSWORD = "zdm48-password-sentinel"
BEARER = "zdm48-bearer-sentinel"
LLM = "zdm48-llm-sentinel"


def _cfg(tmp_path: Path, **kwargs: object) -> HelperConfig:
    values = {
        "zeus_url": "http://lab.example:8080",
        "default_bucket": "beer-sample",
        "default_scope": "_default",
        "state_dir": tmp_path / "state",
    }
    values.update(kwargs)
    return HelperConfig(**values)  # type: ignore[arg-type]


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_populated_values_stay_and_secrets_stay_presence_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zeus_dev_helper_mcp.app_env import ensure_app_env

    monkeypatch.delenv("ZEUS_AUTH_MODE", raising=False)
    monkeypatch.setenv("ZEUS_USERNAME", "process-user")
    monkeypatch.setenv("ZEUS_PASSWORD", "process-password")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("LLM_MODEL", "gpt-5.6-sol")
    monkeypatch.setenv("LLM_API_KEY", "process-key")
    root = tmp_path / "app"
    root.mkdir()
    (root / ".env.example").write_text(
        "ZEUS_URL=\n"
        "ZEUS_AUTH_MODE=\n"
        "ZEUS_USERNAME=\n"
        "ZEUS_PASSWORD=\n"
        "ZEUS_BEARER_TOKEN=\n"
        "LLM_BASE_URL=\n"
        "LLM_MODEL=\n"
        "LLM_API_KEY=\n",
        encoding="utf-8",
    )
    (root / ".env").write_text(
        "\n".join(
            [
                "ZEUS_URL=http://kept.example:8080",
                "ZEUS_AUTH_MODE=basic",
                "ZEUS_USERNAME=kept-user",
                f"ZEUS_PASSWORD={PASSWORD}",
                f"ZEUS_BEARER_TOKEN={BEARER}",
                "LLM_BASE_URL=https://kept.example/v1",
                "LLM_MODEL=kept-model",
                f"LLM_API_KEY={LLM}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    out = ensure_app_env(_cfg(tmp_path, zeus_auth_mode="basic"), root)
    text = (root / ".env").read_text(encoding="utf-8")
    assert "ZEUS_USERNAME=kept-user" in text
    assert "LLM_MODEL=kept-model" in text
    assert "ZEUS_BUCKET=beer-sample" in text
    assert "process-user" not in text
    assert "gpt-5.6-sol" not in text
    assert out["env_change"] is True
    assert out["settings_written"] == []
    assert out["settings_kept"] == {
        "ZEUS_AUTH_MODE": "basic",
        "ZEUS_USERNAME": "kept-user",
        "LLM_BASE_URL": "https://kept.example/v1",
        "LLM_MODEL": "kept-model",
    }
    assert out["secret_presence"] == {
        "ZEUS_PASSWORD": True,
        "ZEUS_BEARER_TOKEN": True,
        "LLM_API_KEY": True,
    }
    blob = json.dumps(out)
    assert PASSWORD not in blob
    assert BEARER not in blob
    assert LLM not in blob
    assert "process-password" not in blob
    assert "process-key" not in blob


def test_filling_an_empty_model_is_an_env_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zeus_dev_helper_mcp.app_env import annotate_app_env, attach_env_change_note

    monkeypatch.delenv("ZEUS_AUTH_MODE", raising=False)
    monkeypatch.setenv("LLM_BASE_URL", "https://api.x.ai/v1")
    monkeypatch.setenv("LLM_MODEL", "grok-4.5-latest")
    monkeypatch.setenv("LLM_API_KEY", LLM)
    root = tmp_path / "app"
    root.mkdir()
    (root / ".env.example").write_text(
        "ZEUS_USERNAME=\nLLM_BASE_URL=\nLLM_MODEL=\nLLM_API_KEY=\n",
        encoding="utf-8",
    )
    (root / ".env").write_text(
        "ZEUS_USERNAME=kept-user\nLLM_BASE_URL=\nLLM_MODEL=\nLLM_API_KEY=\n",
        encoding="utf-8",
    )
    out = attach_env_change_note(
        annotate_app_env(
            _cfg(tmp_path),
            root,
            {"next_action": "Start the app."},
            report=True,
        )
    )
    text = (root / ".env").read_text(encoding="utf-8")
    assert "ZEUS_USERNAME=kept-user" in text
    assert "LLM_MODEL=grok-4.5-latest" in text
    assert out["env_change"] is True
    assert "LLM_MODEL" in out["settings_written"]
    assert "LLM_BASE_URL" in out["settings_written"]
    assert out["settings_kept"]["ZEUS_USERNAME"] == "kept-user"
    assert "ZEUS_USERNAME" not in out["settings_written"]
    assert out["secret_presence"]["LLM_API_KEY"] is True
    assert "Env report: env change." in out["next_action"]
    assert "Restart the app before run_turn." in out["next_action"]
    assert "Start the app." in out["next_action"]
    assert LLM not in json.dumps(out)
    assert _mode(root / ".env") == 0o600


def test_overlay_rewrite_names_the_new_settings_and_keeps_the_secret(
    tmp_path: Path,
) -> None:
    from zeus_dev_helper_mcp.scaffold import apply_create_answers

    root = tmp_path / "demo_beer_sample"
    root.mkdir()
    env = root / ".env"
    env.write_text(
        "\n".join(
            [
                "ZEUS_AUTH_MODE=none",
                "ZEUS_USERNAME=old-user",
                f"ZEUS_PASSWORD={PASSWORD}",
                "LLM_BASE_URL=https://kept.example/v1",
                "LLM_MODEL=kept-model",
                f"LLM_API_KEY={LLM}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    class Gate:
        cards_accepted = True
        zeus_url = ""
        auth_mode = "basic"
        zeus_username = "edited-user"
        llm_provider = "grok"
        llm_base_url = "https://api.x.ai/v1"
        llm_model = "grok-4.5-latest"

    payload = {
        "ok": True,
        "local_dir": str(root),
        "created_env": False,
        "env_change": False,
        "settings_written": [],
        "settings_kept": {
            "ZEUS_AUTH_MODE": "none",
            "ZEUS_USERNAME": "old-user",
            "LLM_BASE_URL": "https://kept.example/v1",
            "LLM_MODEL": "kept-model",
        },
        "secret_presence": {
            "ZEUS_PASSWORD": True,
            "ZEUS_BEARER_TOKEN": False,
            "LLM_API_KEY": True,
        },
        "app_env": {},
        "next_action": "Start python main.py.",
        "ask_user": [{"env": "ZEUS_USERNAME"}],
    }
    out = apply_create_answers(payload, Gate())
    text = env.read_text(encoding="utf-8")
    assert "ZEUS_AUTH_MODE=basic" in text
    assert "ZEUS_USERNAME=edited-user" in text
    assert "LLM_BASE_URL=https://api.x.ai/v1" in text
    assert "LLM_MODEL=grok-4.5-latest" in text
    assert f"ZEUS_PASSWORD={PASSWORD}" in text
    assert f"LLM_API_KEY={LLM}" in text
    assert out["env_change"] is True
    assert out["settings_written"] == [
        "ZEUS_AUTH_MODE",
        "ZEUS_USERNAME",
        "LLM_BASE_URL",
        "LLM_MODEL",
    ]
    assert out["settings_kept"] == {}
    assert out["secret_presence"]["ZEUS_PASSWORD"] is True
    assert out["secret_presence"]["LLM_API_KEY"] is True
    assert "ask_user" not in out
    assert "Env report: env change." in out["next_action"]
    assert "Restart the app before run_turn." in out["next_action"]
    assert "Start python main.py." in out["next_action"]
    blob = json.dumps(out)
    assert PASSWORD not in blob
    assert LLM not in blob


def test_first_create_stays_quiet_when_the_overlay_edits_the_new_file() -> None:
    from zeus_dev_helper_mcp.app_env import refresh_env_report

    report = refresh_env_report(
        {
            "created_env": True,
            "env_change": False,
            "settings_written": ["ZEUS_USERNAME"],
            "settings_kept": {},
        },
        f"ZEUS_USERNAME=tester_beer\nZEUS_PASSWORD={PASSWORD}\n",
        f"ZEUS_USERNAME=edited-user\nZEUS_PASSWORD={PASSWORD}\n",
    )
    assert report is not None
    assert report["env_change"] is False
    assert report["settings_written"] == ["ZEUS_USERNAME"]
    assert report["settings_kept"] == {}
    assert report["secret_presence"]["ZEUS_PASSWORD"] is True
    assert PASSWORD not in json.dumps(report)


def test_a_result_that_never_wrote_env_is_left_unchanged(tmp_path: Path) -> None:
    from zeus_dev_helper_mcp.scaffold import apply_create_answers

    root = tmp_path / "demo_yelp"
    root.mkdir()

    class Gate:
        cards_accepted = True
        zeus_url = "http://lab.example:8080"
        auth_mode = "basic"
        zeus_username = "edited-user"
        llm_provider = "grok"
        llm_base_url = "https://api.x.ai/v1"
        llm_model = "grok-4.5-latest"

    payload = {
        "ok": True,
        "local_dir": str(root),
        "next_action": "Start the yelp demo.",
        "ask_user": [{"env": "ZEUS_USERNAME"}],
    }
    out = apply_create_answers(payload, Gate())
    assert not (root / ".env").exists()
    assert "settings_written" not in out
    assert "env_change" not in out
    assert "settings_kept" not in out
    assert "Env report:" not in out["next_action"]
    assert out["next_action"] == "Start the yelp demo."
    assert "ask_user" not in out


def test_kept_base_url_omits_userinfo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zeus_dev_helper_mcp.app_env import describe_env_change, ensure_app_env

    secret = "zdm48-userinfo-sentinel"
    raw = f"https://user:{secret}@api.example/v1"
    monkeypatch.delenv("ZEUS_AUTH_MODE", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    root = tmp_path / "app"
    root.mkdir()
    (root / ".env").write_text(
        "ZEUS_USERNAME=kept-user\n"
        f"LLM_BASE_URL={raw}\n"
        "LLM_MODEL=kept-model\n"
        f"LLM_API_KEY={LLM}\n",
        encoding="utf-8",
    )
    out = ensure_app_env(_cfg(tmp_path), root)
    text = (root / ".env").read_text(encoding="utf-8")
    assert raw in text
    assert out["settings_kept"]["LLM_BASE_URL"] == "https://api.example/v1"
    assert secret not in json.dumps(out)
    note = describe_env_change(out)
    assert secret not in note
    assert "https://api.example/v1" in note
    assert "Restart the app before run_turn." not in note


def test_journals_do_not_receive_secret_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zeus_dev_helper_mcp.app_env import describe_env_change, ensure_app_env
    from zeus_dev_helper_mcp.sample_log import observe_sample_build
    from zeus_dev_helper_mcp.sample_support import observe_sample_support

    monkeypatch.delenv("ZEUS_AUTH_MODE", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    root = tmp_path / "demo_beer_sample"
    root.mkdir()
    (root / ".env").write_text(
        f"ZEUS_USERNAME=kept-user\nZEUS_PASSWORD={PASSWORD}\n"
        f"ZEUS_BEARER_TOKEN={BEARER}\nLLM_API_KEY={LLM}\n",
        encoding="utf-8",
    )
    cfg = _cfg(tmp_path)
    report = ensure_app_env(cfg, root)
    result = {
        "ok": False,
        "failure_class": "login_not_in_process",
        "local_dir": str(root),
        "next_action": f"Blocked. {describe_env_change(report)}",
        **{key: report[key] for key in (
            "settings_written",
            "settings_kept",
            "secret_presence",
            "env_change",
        )},
    }
    observe_sample_build(cfg, "use_sample", {"sample": "beer"}, result)
    observe_sample_support(cfg, "use_sample", {"sample": "beer"}, result)
    written = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "state").rglob("*")
        if path.is_file()
    )
    assert PASSWORD not in written
    assert BEARER not in written
    assert LLM not in written
    build_log = tmp_path / "state" / "beer-sample-build.md"
    if build_log.is_file():
        assert "kept-user" not in build_log.read_text(encoding="utf-8")
