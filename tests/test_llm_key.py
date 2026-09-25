"""LLM key must be in the environment before a live turn. Never echo the secret."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zeus_dev_helper_mcp.checklist import (
    load_checklist,
    save_checklist,
    set_item_status,
)
from zeus_dev_helper_mcp.config import HelperConfig, reload_config
from zeus_dev_helper_mcp.config_lint import lint_runtime_config
from zeus_dev_helper_mcp.prereqs import save_prereqs
from zeus_dev_helper_mcp.readiness import _finish
from zeus_dev_helper_mcp.scaffold import verify_local_setup

SECRET = "sk-test-not-real"


def _clear_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("LLM_API_KEY", "XAI_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def _item(cfg: HelperConfig, item_id: str) -> dict:
    for phase in load_checklist(cfg)["phases"]:
        for item in phase["items"]:
            if item["id"] == item_id:
                return item
    raise AssertionError(item_id)


def test_stored_flag_is_not_the_process_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_llm(monkeypatch)
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    cfg = reload_config()
    save_prereqs(cfg, {"has_llm_key": True, "zeus_url": "http://127.0.0.1:8080"})
    cfg = reload_config()
    assert cfg.has_llm_key is False
    monkeypatch.setenv("LLM_API_KEY", SECRET)
    cfg = reload_config()
    assert cfg.has_llm_key is True
    assert SECRET not in json.dumps(cfg.public_view())


def test_inspect_rejects_secret_in_api_key_env(tmp_path: Path) -> None:
    from zeus_dev_helper_mcp.llm_key import inspect_app_llm_key

    root = tmp_path / "app"
    root.mkdir()
    (root / "config.json").write_text(
        json.dumps({"llm": {"api_key_env": SECRET}}),
        encoding="utf-8",
    )
    (root / ".env").write_text(f"LLM_API_KEY={SECRET}\n", encoding="utf-8")
    report = inspect_app_llm_key(root)
    assert report["applies"] is True
    assert report["ok"] is False
    assert "variable name" in report["message"]
    assert SECRET not in json.dumps(report)


def test_inspect_requires_dotenv_value_for_the_configured_name(tmp_path: Path) -> None:
    from zeus_dev_helper_mcp.llm_key import inspect_app_llm_key

    root = tmp_path / "app"
    root.mkdir()
    (root / "config.json").write_text(
        json.dumps({"llm": {"api_key_env": "LLM_API_KEY"}}),
        encoding="utf-8",
    )
    missing = inspect_app_llm_key(root)
    assert missing["ok"] is False
    assert missing["api_key_env"] == "LLM_API_KEY"
    (root / ".env").write_text('export LLM_API_KEY="sk-quoted"\n', encoding="utf-8")
    ready = inspect_app_llm_key(root)
    assert ready["ok"] is True
    assert "sk-quoted" not in json.dumps(ready)
    assert ready["evidence"] == "api_key_env=LLM_API_KEY present in .env"


def test_readiness_keeps_12_open_until_process_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_llm(monkeypatch)
    cfg = HelperConfig(zeus_url="http://127.0.0.1:8080", state_dir=tmp_path / "state")
    data = load_checklist(cfg)
    data["meta"] = {"sample": "beer"}
    save_checklist(cfg, data)
    save_prereqs(cfg, {"has_llm_key": False, "bucket": "beer-sample"})
    _finish(cfg, [], update_checklist=True)
    assert _item(cfg, "1.2")["status"] == "todo"

    set_item_status(cfg, "1.2", "done", evidence="ZEUS_URL set")
    _finish(cfg, [], update_checklist=True)
    assert _item(cfg, "1.2")["status"] == "todo"

    monkeypatch.setenv("LLM_API_KEY", SECRET)
    _finish(cfg, [], update_checklist=True)
    item = _item(cfg, "1.2")
    assert item["status"] == "done"
    assert item["evidence"] == "ZEUS_URL set; LLM key present"
    assert SECRET not in json.dumps(load_checklist(cfg))


def test_readiness_direct_opt_out_does_not_require_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_llm(monkeypatch)
    cfg = HelperConfig(zeus_url="http://127.0.0.1:8080", state_dir=tmp_path / "state")
    data = load_checklist(cfg)
    data["meta"] = {"sample": "travel"}
    save_checklist(cfg, data)
    save_prereqs(cfg, {"has_llm_key": False, "bucket": "travel-sample"})
    _finish(cfg, [], update_checklist=True)
    item = _item(cfg, "1.2")
    assert item["status"] == "done"
    assert "not required" in item["evidence"]


def test_validate_env_errors_when_the_path_calls_the_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_llm(monkeypatch)
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ZEUS_URL", "http://127.0.0.1:8080")
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.server.list_modes",
        lambda cfg: {"modes": [{"mode": "analytics"}]},
    )
    from zeus_dev_helper_mcp.server import validate_env

    reload_config()
    out = validate_env()
    assert out["ok"] is False
    issue = next(i for i in out["issues"] if i["field"] == "LLM_API_KEY")
    assert issue["level"] == "error"
    assert issue["failure_class"] == "llm_key_missing"
    assert "has_llm_key=true" in out["next_action"]

    cfg = reload_config()
    save_prereqs(
        cfg,
        {
            "has_llm_key": True,
            "zeus_url": "http://127.0.0.1:8080",
            "bucket": "travel-sample",
            "scope": "_default",
        },
    )
    flagged = validate_env()
    assert flagged["ok"] is False
    assert flagged["config"]["has_llm_key"] is False


def test_validate_env_warns_on_direct_opt_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_llm(monkeypatch)
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.server.list_modes",
        lambda cfg: {"modes": []},
    )
    from zeus_dev_helper_mcp.server import validate_env

    cfg = reload_config()
    save_prereqs(
        cfg,
        {
            "has_llm_key": False,
            "zeus_url": "http://127.0.0.1:8080",
            "bucket": "travel-sample",
            "scope": "_default",
        },
    )
    data = load_checklist(cfg)
    data["meta"] = {"sample": "travel"}
    save_checklist(cfg, data)
    out = validate_env()
    issue = next(i for i in out["issues"] if i["field"] == "LLM_API_KEY")
    assert issue["level"] == "warn"
    assert out["ok"] is True


def test_beer_sample_stays_on_32_until_dotenv_is_filled(tmp_path: Path) -> None:
    from zeus_dev_helper_mcp.beer import write_beer_sample

    cfg = HelperConfig(state_dir=tmp_path / "state", default_bucket="beer-sample")
    out = write_beer_sample(cfg, tmp_path / "demo_beer_sample")
    root = Path(out["local_dir"])
    assert _item(cfg, "3.2")["status"] == "todo"
    assert out["llm_key"]["ok"] is False
    assert "api_key_env" in out["next_action"]

    blocked = verify_local_setup(cfg, str(root))
    assert _item(cfg, "3.2")["status"] == "blocked"
    assert any(c["name"] == "llm_api_key" and c["ok"] is False for c in blocked["checks"])

    (root / ".env").write_text(f"LLM_API_KEY={SECRET}\n", encoding="utf-8")
    ready = verify_local_setup(cfg, str(root))
    assert SECRET not in json.dumps(ready)
    llm = next(c for c in ready["checks"] if c["name"] == "llm_api_key")
    assert llm["ok"] is True
    done = _item(cfg, "3.2")
    assert done["status"] == "done"
    assert SECRET not in json.dumps(load_checklist(cfg))

    doc = json.loads((root / "config.json").read_text(encoding="utf-8"))
    doc["llm"]["api_key_env"] = SECRET
    (root / "config.json").write_text(json.dumps(doc), encoding="utf-8")
    bad = verify_local_setup(cfg, str(root))
    assert SECRET not in json.dumps(bad)
    assert any(c["name"] == "llm_api_key" and c["ok"] is False for c in bad["checks"])
    lint = lint_runtime_config(cfg, path=str(root / "config.json"))
    assert lint["ok"] is False
    assert any(i.get("failure_class") == "llm_key_missing" for i in lint["issues"])
    assert SECRET not in json.dumps(lint)


def test_next_step_32_asks_for_verify_before_smoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_llm(monkeypatch)
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    from zeus_dev_helper_mcp.walkthrough import enriched_next_step

    cfg = reload_config()
    data = load_checklist(cfg)
    data["meta"] = {"sample": "beer"}
    save_checklist(cfg, data)
    for item_id in ("0.1", "0.2", "1.1", "1.2", "2.1", "2.2", "2.3", "3.1"):
        set_item_status(cfg, item_id, "done", evidence="test")
    nxt = enriched_next_step(cfg)
    assert nxt["item"]["id"] == "3.2"
    assert "verify_local_setup" in nxt["recommended_tools"]
    assert "lint_runtime_config" in nxt["recommended_tools"]
    assert "api_key_env" in nxt["note"]
    assert "smoke_test_agent" not in nxt["recommended_tools"]


def test_smoke_test_agent_ignores_stored_flag_when_client_imports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("zeus_client")
    _clear_llm(monkeypatch)
    from zeus_dev_helper_mcp.smoke import smoke_test_agent

    cfg = HelperConfig(
        has_llm_key=True,
        zeus_url="http://127.0.0.1:8080",
        state_dir=tmp_path / "state",
    )
    out = smoke_test_agent(cfg, update_checklist=False)
    assert out["ok"] is False
    assert out["failure_class"] == "llm_key_missing"
    assert "has_llm_key" in out["next_action"]
