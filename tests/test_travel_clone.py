"""Public demo_travel_sample clone + DEMO_TRAVEL_SAMPLE_DIR."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from zeus_dev_helper_mcp.checklist import load_checklist, save_checklist, set_item_status
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.scaffold import use_sample
from zeus_dev_helper_mcp.travel import (
    DEFAULT_TRAVEL_DIR_NAME,
    ENV_TRAVEL_DIR,
    TRAVEL_REPO_GIT,
    clone_travel_sample,
    ensure_travel_sample,
    sanitize_travel_dir_name,
)

SECRET = "fixture-travel-secret-value"


def _cfg(tmp_path: Path) -> HelperConfig:
    return HelperConfig(state_dir=tmp_path / "state")


def test_sanitize_travel_dir_name() -> None:
    assert sanitize_travel_dir_name("") == DEFAULT_TRAVEL_DIR_NAME
    assert sanitize_travel_dir_name("  My App  ") == "My-App"
    assert sanitize_travel_dir_name("../etc") == DEFAULT_TRAVEL_DIR_NAME
    assert sanitize_travel_dir_name("zeus_travel_ui") == "zeus_travel_ui"


def test_clone_travel_sample_success(tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "demo_travel_sample"

    def fake_run(cmd, **kwargs):
        dest.mkdir(parents=True)
        (dest / "README.md").write_text("# demo\n", encoding="utf-8")
        (dest / "requirements.txt").write_text("x\n", encoding="utf-8")
        m = MagicMock()
        m.returncode = 0
        m.stderr = ""
        m.stdout = "Cloning...\n"
        return m

    monkeypatch.setattr("zeus_dev_helper_mcp.travel.subprocess.run", fake_run)
    out = clone_travel_sample(dest=dest)
    assert out["ok"] is True
    assert out["cloned"] is True
    assert dest.is_dir()


def test_clone_travel_sample_dest_exists(tmp_path: Path) -> None:
    dest = tmp_path / "demo_travel_sample"
    dest.mkdir()
    out = clone_travel_sample(dest=dest)
    assert out["ok"] is False
    assert out["cloned"] is False


def test_ensure_clones_and_sets_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(ENV_TRAVEL_DIR, raising=False)
    parent = tmp_path / "apps"
    parent.mkdir()
    dest = parent / "my_travel_boot"

    def fake_run(cmd, **kwargs):
        dest.mkdir(parents=True)
        (dest / "README.md").write_text("# demo\n", encoding="utf-8")
        (dest / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
        m = MagicMock()
        m.returncode = 0
        m.stderr = ""
        m.stdout = ""
        return m

    monkeypatch.setattr("zeus_dev_helper_mcp.travel.subprocess.run", fake_run)
    # Avoid discovering real sibling demo_travel_sample on this machine.
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.travel._find_travel_dir",
        lambda explicit="", cfg=None: None,
    )
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.travel._default_clone_parent",
        lambda: parent,
    )

    cfg = _cfg(tmp_path)
    out = ensure_travel_sample(cfg, project_name="my_travel_boot", parent_dir=str(parent))
    assert out["ok"] is True
    assert out["cloned"] is True
    assert out["local_dir"] == str(dest.resolve())
    assert os.environ.get(ENV_TRAVEL_DIR) == str(dest.resolve())
    assert out["env"][ENV_TRAVEL_DIR] == str(dest.resolve())
    assert (cfg.state_dir / "travel_sample.json").is_file()


def test_ensure_uses_existing_sample_dir(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "already"
    root.mkdir()
    (root / "README.md").write_text("# ok\n", encoding="utf-8")
    (root / "requirements.txt").write_text("x\n", encoding="utf-8")
    monkeypatch.delenv(ENV_TRAVEL_DIR, raising=False)
    called = {"n": 0}

    def no_clone(**kwargs):
        called["n"] += 1
        return {"ok": False}

    monkeypatch.setattr("zeus_dev_helper_mcp.travel.clone_travel_sample", no_clone)
    cfg = _cfg(tmp_path)
    out = ensure_travel_sample(cfg, sample_dir=str(root))
    assert out["ok"] is True
    assert out["cloned"] is False
    assert called["n"] == 0
    assert os.environ[ENV_TRAVEL_DIR] == str(root.resolve())


def test_use_sample_passes_project_name(tmp_path: Path, monkeypatch) -> None:
    parent = tmp_path / "ws"
    parent.mkdir()
    dest = parent / "BootApp"

    def fake_run(cmd, **kwargs):
        dest.mkdir(parents=True)
        (dest / "README.md").write_text("# demo\n", encoding="utf-8")
        (dest / "src").mkdir()
        m = MagicMock()
        m.returncode = 0
        m.stderr = ""
        m.stdout = ""
        return m

    monkeypatch.setattr("zeus_dev_helper_mcp.travel.subprocess.run", fake_run)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.travel._find_travel_dir",
        lambda explicit="", cfg=None: None,
    )
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.travel._default_clone_parent",
        lambda: parent,
    )
    monkeypatch.delenv(ENV_TRAVEL_DIR, raising=False)

    cfg = _cfg(tmp_path)
    out = use_sample(cfg, sample="travel", project_name="BootApp", parent_dir=str(parent))
    assert out["ok"] is True
    assert out["cloned"] is True
    assert out["project_name"] == "BootApp"
    assert out["local_dir"] == str(dest.resolve())
    assert os.environ[ENV_TRAVEL_DIR] == str(dest.resolve())


def _closed_probe(port: int, *, timeout: float = 0.6) -> dict[str, object]:
    del timeout
    return {
        "url": f"http://127.0.0.1:{int(port)}/",
        "reachable": False,
        "health_ok": False,
    }


def _clear_login(monkeypatch: pytest.MonkeyPatch) -> None:
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
        ENV_TRAVEL_DIR,
        "DEMO_BEER_SAMPLE_DIR",
    ):
        monkeypatch.delenv(name, raising=False)


def _layout(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text("# travel\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='travel'\n", encoding="utf-8")
    planner = root / "src" / "travel_planner"
    planner.mkdir(parents=True, exist_ok=True)
    (planner / "__init__.py").write_text("", encoding="utf-8")


def test_foreign_default_directory_clones_the_next_sibling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_login(monkeypatch)
    monkeypatch.setattr("zeus_dev_helper_mcp.travel.probe_travel_port", _closed_probe)
    parent = tmp_path / "apps"
    foreign = parent / "demo_travel_sample"
    foreign.mkdir(parents=True)
    (foreign / "notes.txt").write_text("keep\n", encoding="utf-8")
    seen: dict[str, list[str]] = {}

    def fake_run(cmd, **kwargs):
        del kwargs
        seen["cmd"] = list(cmd)
        dest = Path(cmd[-1])
        _layout(dest)
        proc = MagicMock()
        proc.returncode = 0
        proc.stderr = ""
        proc.stdout = ""
        return proc

    monkeypatch.setattr("zeus_dev_helper_mcp.travel.subprocess.run", fake_run)
    out = ensure_travel_sample(_cfg(tmp_path), parent_dir=str(parent))
    assert out["ok"] is True
    assert out["cloned"] is True
    assert Path(out["local_dir"]).name == "demo_travel_sample-2"
    assert out["repo"] == "https://github.com/koten-ai/demo_travel_sample"
    assert TRAVEL_REPO_GIT in seen["cmd"]
    assert "demo_beer_sample" not in " ".join(seen["cmd"])
    assert (foreign / "notes.txt").read_text(encoding="utf-8") == "keep\n"
    assert out["relocated_from"] == str(foreign.resolve())


def test_explicit_foreign_sample_dir_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_login(monkeypatch)
    foreign = tmp_path / "notes-app"
    foreign.mkdir()
    (foreign / "notes.txt").write_text("keep\n", encoding="utf-8")

    def fail_clone(*_args, **_kwargs):
        raise AssertionError("clone ran for a foreign sample_dir")

    monkeypatch.setattr("zeus_dev_helper_mcp.travel.clone_travel_sample", fail_clone)
    out = ensure_travel_sample(_cfg(tmp_path), sample_dir=str(foreign))
    assert out["ok"] is False
    assert out["failure_class"] == "foreign_sample_dir"
    assert out["cloned"] is False
    assert out["written"] is False
    assert (foreign / "notes.txt").read_text(encoding="utf-8") == "keep\n"
    assert not (foreign / ".git").exists()
    assert list(foreign.iterdir()) == [foreign / "notes.txt"]


def test_basic_auth_without_process_login_skips_clone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_login(monkeypatch)
    parent = tmp_path / "apps"
    parent.mkdir()

    def fail_clone(*_args, **_kwargs):
        raise AssertionError("clone ran before process login")

    monkeypatch.setattr("zeus_dev_helper_mcp.travel.clone_travel_sample", fail_clone)
    cfg = HelperConfig(state_dir=tmp_path / "state", zeus_auth_mode="basic")
    out = ensure_travel_sample(cfg, parent_dir=str(parent), project_name="fresh-travel")
    assert out["ok"] is False
    assert out["failure_class"] == "login_not_in_process"
    assert out["cloned"] is False
    assert not (parent / "fresh-travel").exists()
    assert SECRET not in json.dumps(out)


def test_live_travel_health_stays_put_without_host_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_login(monkeypatch)
    checkout = tmp_path / "recorded"
    _layout(checkout)
    (checkout / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
    (checkout / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    monkeypatch.setenv(ENV_TRAVEL_DIR, str(checkout))

    def live(port: int, *, timeout: float = 0.6) -> dict[str, object]:
        del timeout
        return {
            "url": f"http://127.0.0.1:{int(port)}/",
            "reachable": True,
            "health_ok": True,
        }

    def fail_clone(*_args, **_kwargs):
        raise AssertionError("serving checkout was relocated")

    monkeypatch.setattr("zeus_dev_helper_mcp.travel.probe_travel_port", live)
    monkeypatch.setattr("zeus_dev_helper_mcp.travel.clone_travel_sample", fail_clone)
    parent = tmp_path / "other"
    parent.mkdir()
    out = use_sample(_cfg(tmp_path), sample="travel", parent_dir=str(parent))
    assert out["ok"] is True
    assert out["already_serving"] is True
    assert out["cloned"] is False
    assert Path(out["local_dir"]) == checkout.resolve()
    assert "host_question" not in out
    assert "host_question" not in json.dumps(out)
    assert not (parent / "demo_travel_sample").exists()


def test_second_use_sample_keeps_env_and_hides_the_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zeus_dev_helper_mcp.sample_log import observe_sample_build, reset_memory
    from zeus_dev_helper_mcp.sample_support import observe_sample_support

    _clear_login(monkeypatch)
    monkeypatch.setattr("zeus_dev_helper_mcp.travel.probe_travel_port", _closed_probe)
    monkeypatch.setenv("ZEUS_USERNAME", "process-user")
    monkeypatch.setenv("ZEUS_PASSWORD", "process-should-not-replace")
    monkeypatch.setenv("LLM_API_KEY", "process-key-should-not-replace")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.x.ai/v1")
    monkeypatch.setenv("LLM_MODEL", "grok-4.5-latest")
    root = tmp_path / "apps" / "demo_travel_sample"
    _layout(root)
    (root / "config.example.json").write_text(
        json.dumps(
            {
                "zeus": {"username": "demo_1", "password": ""},
                "llm_provider": {"api_key": ""},
            }
        ),
        encoding="utf-8",
    )
    (root / ".env").write_text(
        "\n".join(
            [
                "ZEUS_URL=http://kept.example:8080",
                "ZEUS_BUCKET=kept-bucket",
                "ZEUS_SCOPE=kept-scope",
                "ZEUS_USERNAME=kept-user",
                f"ZEUS_PASSWORD={SECRET}",
                f"LLM_API_KEY={SECRET}",
                "LLM_BASE_URL=https://kept.example/v1",
                "LLM_MODEL=kept-model",
                "PORT=5000",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    cfg = HelperConfig(
        state_dir=tmp_path / "state",
        zeus_url="http://cfg.example:8080",
        default_bucket="cfg-bucket",
        default_scope="_default",
        zeus_auth_mode="basic",
    )
    first = use_sample(cfg, sample="travel", sample_dir=str(root))
    env_text = (root / ".env").read_text(encoding="utf-8")
    assert "ZEUS_URL=http://kept.example:8080" in env_text
    assert "ZEUS_USERNAME=kept-user" in env_text
    assert f"LLM_API_KEY={SECRET}" in env_text
    assert "LLM_MODEL=kept-model" in env_text
    assert "process-user" not in env_text
    assert "process-should-not-replace" not in env_text
    assert "process-key-should-not-replace" not in env_text
    assert stat.S_IMODE((root / ".env").stat().st_mode) == 0o600
    assert not (root / ".env.example").exists()
    copied = json.loads((root / "config.json").read_text(encoding="utf-8"))
    assert copied["zeus"]["password"] == ""
    assert copied["llm_provider"]["api_key"] == ""
    assert SECRET not in (root / "config.json").read_text(encoding="utf-8")
    copied["marker"] = "kept"
    (root / "config.json").write_text(json.dumps(copied), encoding="utf-8")

    second = use_sample(cfg, sample="travel", sample_dir=str(root))
    again = json.loads((root / "config.json").read_text(encoding="utf-8"))
    assert again["marker"] == "kept"
    assert (root / ".env").read_text(encoding="utf-8") == env_text
    for result in (first, second):
        blob = json.dumps(result)
        assert result["configuration_policy"] == "preserve_existing_then_fill_missing"
        assert "LLM_API_KEY" in result["app_env"]["env_keys"]
        assert "ZEUS_PASSWORD" in result["app_env"]["env_keys"]
        assert SECRET not in result["app_env"]["env_keys"]
        assert SECRET not in blob
        assert "process-should-not-replace" not in blob
        assert "process-key-should-not-replace" not in blob
        assert "copy the template" not in result["next_action"]
        assert "llm_provider.api_key" not in result["next_action"]
        assert result["env_template"] == "zeus_llm_names"
        assert "python3 -m venv .venv" in result["run"]
        assert 'pip install -e ".[dev]"' in result["run"]
        assert "python -m travel_planner" in result["run"]
        assert "python main.py" not in result["run"]

    reset_memory()
    observe_sample_build(
        cfg,
        "use_sample",
        {"sample": "travel"},
        first,
        bound_before={},
    )
    red = dict(first)
    red["ok"] = False
    observe_sample_support(cfg, "use_sample", {"sample": "travel"}, red)
    state = tmp_path / "state"
    build = (state / "travel-sample-build.md").read_text(encoding="utf-8")
    support = (state / "travel-sample-support.md").read_text(encoding="utf-8")
    checklist = (state / "checklist.json").read_text(encoding="utf-8")
    assert SECRET not in build
    assert SECRET not in support
    assert SECRET not in checklist


def test_bound_travel_next_step_uses_website_green_without_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zeus_dev_helper_mcp.walkthrough import enriched_next_step

    _clear_login(monkeypatch)
    monkeypatch.setenv("ZEUS_DEV_HELPER_TOOLSETS", "all")
    cfg = _cfg(tmp_path)
    data = load_checklist(cfg)
    data["meta"] = {"sample": "travel"}
    save_checklist(cfg, data)
    for item_id in (
        "0.1",
        "0.2",
        "1.1",
        "1.2",
        "2.1",
        "2.2",
        "2.3",
        "3.1",
        "3.2",
        "4.1",
        "4.2",
    ):
        set_item_status(cfg, item_id, "done", evidence="test")
    at_smoke = enriched_next_step(cfg)
    assert at_smoke["item"]["id"] == "5.1"
    assert at_smoke["recommended_tools"] == ["website_green"]
    assert "handoff_to_multi" not in at_smoke["recommended_tools"]
    assert "jobs.host_url" not in json.dumps(at_smoke)

    set_item_status(cfg, "5.1", "done", evidence="test")
    set_item_status(cfg, "5.2", "done", evidence="test")
    after = enriched_next_step(cfg)
    assert "website_green" in after["recommended_tools"]
    assert "handoff_to_multi" not in after["recommended_tools"]
    assert "handoff_to_multi" not in after["post_green"]["suggested_tools"]
    assert "jobs.host_url is not written" in after["post_green"]["note"]
    assert "handoff_to_multi" not in json.dumps(after["post_green"]["suggested_tools"])
