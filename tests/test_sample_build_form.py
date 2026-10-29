"""ZDM-48: every sample build asks for auth and LLM settings."""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.scaffold import scaffold_app, use_sample

PASSWORD = "zdm48-password-sentinel"
BEARER = "zdm48-bearer-sentinel"
LLM = "zdm48-llm-sentinel"
USER = "tap-user"
MODEL = "grok-custom"


def _cfg(tmp_path: Path, **kwargs: object) -> HelperConfig:
    data = {
        "zeus_url": "http://lab.example:8080",
        "default_bucket": "beer-sample",
        "default_scope": "_default",
        "state_dir": tmp_path / "state",
    }
    data.update(kwargs)
    return HelperConfig(**data)  # type: ignore[arg-type]


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
        "ZEUS_AUTH_MODE",
    ):
        monkeypatch.delenv(name, raising=False)


def _secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZEUS_USERNAME", USER)
    monkeypatch.setenv("ZEUS_PASSWORD", PASSWORD)
    monkeypatch.setenv("ZEUS_BEARER_TOKEN", BEARER)
    monkeypatch.setenv("LLM_API_KEY", LLM)
    monkeypatch.setenv("LLM_MODEL", MODEL)


def _assert_form(out: dict) -> None:
    assert out["sample_build_form"] is True
    rows = out["ask_user"]
    envs = [row["env"] for row in rows if row.get("env")]
    assert envs[0] == "ZEUS_AUTH_MODE"
    assert envs[-1] == "LLM_API_KEY"
    by_env = {row["env"]: row for row in rows if row.get("env")}
    assert by_env["ZEUS_USERNAME"]["default"] == USER
    assert by_env["LLM_MODEL"]["default"] == MODEL
    assert by_env["ZEUS_PASSWORD"]["kind"] == "password"
    assert "default" not in by_env["ZEUS_PASSWORD"]
    assert by_env["ZEUS_BEARER_TOKEN"]["when"]["equals"] == "bearer"
    assert "default" not in by_env["LLM_API_KEY"]
    blob = json.dumps(out)
    assert PASSWORD not in blob
    assert BEARER not in blob
    assert LLM not in blob
    assert "load_process_login" in out["next_action"]
    assert "LLM_API_KEY" in out["next_action"]


def _closed_port() -> str:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return str(sock.getsockname()[1])


def _pin_port(root: Path, port: str) -> None:
    path = root / ".env"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    lines = [line for line in text.splitlines() if not line.startswith("PORT=")]
    lines.append(f"PORT={port}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_beer_asks_on_every_build_including_the_second(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zeus_dev_helper_mcp.beer import write_beer_sample

    _clear(monkeypatch)
    _secrets(monkeypatch)
    cfg = _cfg(tmp_path, zeus_auth_mode="basic")
    root = tmp_path / "demo_beer_sample"
    assert write_beer_sample(cfg, root)["ok"] is True
    _pin_port(root, _closed_port())
    first = use_sample(cfg, sample="beer", sample_dir=str(root))
    second = use_sample(cfg, sample="beer", sample_dir=str(root))
    _assert_form(first)
    _assert_form(second)
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    assert config["llm"]["api_key_env"] == "LLM_API_KEY"


def test_blocked_beer_build_still_asks_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("ZEUS_PASSWORD", PASSWORD)
    monkeypatch.setenv("LLM_API_KEY", LLM)
    cfg = _cfg(tmp_path, zeus_auth_mode="basic")
    dest = tmp_path / "missing-beer"
    out = use_sample(cfg, sample="beer", sample_dir=str(dest))
    assert out["ok"] is False
    assert out["failure_class"] == "login_not_in_process"
    assert out["sample_build_form"] is True
    username = next(row for row in out["ask_user"] if row.get("env") == "ZEUS_USERNAME")
    assert username["default"] == "tester_beer"
    assert username["kind"] == "text"
    blob = json.dumps(out)
    assert PASSWORD not in blob
    assert LLM not in blob
    assert not dest.exists()


def test_travel_and_yelp_ask_on_the_second_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear(monkeypatch)
    _secrets(monkeypatch)
    monkeypatch.setenv("ZEUS_DEV_HELPER_SKIP_YELP_IMAGES", "1")
    travel = tmp_path / "demo_travel_sample"
    travel.mkdir()
    (travel / "README.md").write_text("# travel\n", encoding="utf-8")
    (travel / "requirements.txt").write_text("httpx\n", encoding="utf-8")
    cfg = _cfg(tmp_path, default_bucket="travel-sample")
    first = use_sample(cfg, sample="travel", sample_dir=str(travel))
    second = use_sample(cfg, sample="travel", sample_dir=str(travel))
    _assert_form(first)
    _assert_form(second)

    yelp = tmp_path / "demo_yelp"
    yelp.mkdir()
    (yelp / "README.md").write_text("# yelp\n", encoding="utf-8")
    (yelp / "frontend").mkdir()
    (yelp / "frontend" / "package.json").write_text("{}\n", encoding="utf-8")
    (yelp / "pyproject.toml").write_text("[project]\nname='local-guide'\n", encoding="utf-8")
    yelp_cfg = _cfg(tmp_path / "yelp-state", default_bucket="yelp-demo", zeus_auth_mode="none")
    yelp_first = use_sample(yelp_cfg, sample="demo_yelp", sample_dir=str(yelp))
    yelp_second = use_sample(yelp_cfg, sample="demo_yelp", sample_dir=str(yelp))
    _assert_form(yelp_first)
    _assert_form(yelp_second)
    assert "ask_user" not in (yelp_first.get("app_config") or {})


def test_other_samples_do_not_grow_the_build_form(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear(monkeypatch)
    _secrets(monkeypatch)

    def _catalog(*_args: object, **_kwargs: object) -> dict:
        return {"ok": True, "local_dir": str(tmp_path / "catalog")}

    monkeypatch.setattr(
        "zeus_dev_helper_mcp.explain_scope.use_catalog_sample",
        _catalog,
    )
    cfg = _cfg(tmp_path)
    catalog = use_sample(cfg, sample="catalog", parent_dir=str(tmp_path))
    assert "sample_build_form" not in catalog
    bare = use_sample(cfg, sample="yelp")
    assert "sample_build_form" not in bare
    api = use_sample(cfg, sample="api")
    assert "sample_build_form" not in api


def test_api_scaffold_asks_and_cli_scaffold_does_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear(monkeypatch)
    cfg = _cfg(tmp_path, zeus_auth_mode="basic")
    blocked = scaffold_app(cfg, str(tmp_path / "blocked-api"), app_kind="api")
    assert blocked["ok"] is False
    assert blocked["sample_build_form"] is True
    first_env = next(row["env"] for row in blocked["ask_user"] if row.get("env"))
    assert first_env == "ZEUS_AUTH_MODE"
    assert not (tmp_path / "blocked-api" / "main.py").exists()

    _secrets(monkeypatch)
    cli = scaffold_app(cfg, str(tmp_path / "cli-app"), app_kind="cli")
    assert cli["ok"] is True
    assert "sample_build_form" not in cli
    api = scaffold_app(cfg, str(tmp_path / "api-app"), app_kind="api")
    _assert_form(api)
    config = json.loads((tmp_path / "api-app" / "config.json").read_text(encoding="utf-8"))
    assert config["llm"]["api_key_env"] == "LLM_API_KEY"
    assert PASSWORD not in json.dumps(api)


def test_journals_keep_the_secret_values_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zeus_dev_helper_mcp.env_questions import attach_sample_build_ask
    from zeus_dev_helper_mcp.sample_log import observe_sample_build
    from zeus_dev_helper_mcp.sample_support import observe_sample_support

    _clear(monkeypatch)
    _secrets(monkeypatch)
    cfg = _cfg(tmp_path, zeus_auth_mode="basic")
    result = attach_sample_build_ask(
        {
            "ok": False,
            "failure_class": "login_not_in_process",
            "local_dir": str(tmp_path / "demo_beer_sample"),
            "next_action": "blocked",
        },
        sample="beer",
        cfg=cfg,
    )
    observe_sample_build(
        cfg,
        "use_sample",
        {"sample": "beer"},
        result,
    )
    observe_sample_support(
        cfg,
        "use_sample",
        {"sample": "beer"},
        result,
    )
    state = tmp_path / "state"
    written = "\n".join(
        path.read_text(encoding="utf-8") for path in state.rglob("*") if path.is_file()
    )
    assert PASSWORD not in written
    assert BEARER not in written
    assert LLM not in written
    assert PASSWORD not in json.dumps(result)
