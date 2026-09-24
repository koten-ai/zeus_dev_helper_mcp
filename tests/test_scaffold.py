import inspect
from pathlib import Path

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.config_lint import lint_app_code, lint_runtime_config
from zeus_dev_helper_mcp.scaffold import scaffold_app, use_sample, verify_local_setup
from zeus_dev_helper_mcp.smoke import smoke_test_agent


def test_scaffold_writes_runtime_files(tmp_path: Path) -> None:
    cfg = HelperConfig(
        zeus_url="http://localhost:8080",
        default_bucket="beer-sample",
        default_scope="_default",
        state_dir=tmp_path / "state",
    )
    out = scaffold_app(cfg, str(tmp_path / "app"), project_name="demo_app")
    assert out["ok"] is True
    root = Path(out["target_dir"])
    assert (root / "main.py").is_file()
    assert (root / "config.json").is_file()
    assert (root / "requirements.txt").is_file()
    assert (root / ".env.example").is_file()
    text = (root / "main.py").read_text()
    reqs = (root / "requirements.txt").read_text()
    assert "ZeusRuntime" in text
    assert "from_config" in text
    assert "HttpxZeusPort" in text
    assert "OpenAICompatibleLlmClient" in text
    assert "run_turn" in text
    assert "run_agent" not in text
    assert "ZeusClient" not in text
    assert "sync_chat_requests" not in text
    assert "kotenai-zeus-client>=2.3.0" in reqs
    assert "beer-sample" in (root / "config.json").read_text()


def test_scaffold_agrees_with_linters(tmp_path: Path) -> None:
    cfg = HelperConfig(
        zeus_url="http://localhost:8080",
        zeus_auth_mode="none",
        default_bucket="beer-sample",
        default_scope="_default",
        default_collection="_default",
        state_dir=tmp_path / "state",
    )
    out = scaffold_app(cfg, str(tmp_path / "app"), project_name="demo_app")
    root = Path(out["target_dir"])
    app = lint_app_code(cfg, path=str(root))
    assert app["ok"] is True
    blob = " ".join(i["message"] for i in app["issues"]).lower()
    assert "zeusclient" not in blob
    assert "run_agent" not in blob
    cfg_lint = lint_runtime_config(cfg, path=str(root / "config.json"))
    assert cfg_lint["ok"] is True


def test_helper_does_not_emit_v1_client_api() -> None:
    from zeus_dev_helper_mcp import scaffold as scaffold_mod
    from zeus_dev_helper_mcp import smoke as smoke_mod

    for src in (inspect.getsource(scaffold_mod.scaffold_app), inspect.getsource(smoke_test_agent)):
        assert "ZeusClient" not in src
        assert "run_agent" not in src
        assert "sync_chat_requests" not in src
    assert "ZeusRuntime" in inspect.getsource(scaffold_mod)
    assert "run_turn" in inspect.getsource(smoke_mod.smoke_test_agent)


def test_use_sample_travel(tmp_path: Path) -> None:
    cfg = HelperConfig(state_dir=tmp_path / "state")
    out = use_sample(cfg, "travel")
    assert out["ok"] is True
    assert "demo_travel_sample" in out["sample"]["repo"]
    assert out.get("app_kind") == "ui"


def test_use_sample_api_redirects_to_scaffold(tmp_path: Path) -> None:
    cfg = HelperConfig(state_dir=tmp_path / "state")
    out = use_sample(cfg, "api")
    assert out["ok"] is False
    assert out["app_kind"] == "api"
    assert "scaffold_app" in (out.get("next_action") or "")


def test_use_sample_beer_direct(tmp_path: Path) -> None:
    cfg = HelperConfig(
        zeus_url="http://localhost:8080",
        default_bucket="beer-sample",
        state_dir=tmp_path / "state",
    )
    out = use_sample(
        cfg,
        sample="beer",
        project_name="demo_beer_sample",
        parent_dir=str(tmp_path),
    )
    assert out["ok"] is True
    assert out.get("app_kind") == "ui"
    assert out.get("track") == "ui-direct"
    root = Path(out["local_dir"])
    assert (root / "main.py").is_file()
    main = (root / "main.py").read_text()
    assert "HttpxZeusPort" in main
    assert "agent.run_turn" in main
    assert "catalog.load_for_turn" in main
    assert "chat_request=" not in main
    assert "pipeline_body" not in main


def test_scaffold_api_fastapi(tmp_path: Path) -> None:
    cfg = HelperConfig(
        zeus_url="http://localhost:8080",
        default_bucket="travel-sample",
        default_scope="_default",
        state_dir=tmp_path / "state",
    )
    out = scaffold_app(
        cfg,
        str(tmp_path / "api_app"),
        project_name="zeus_first_api",
        app_kind="api",
        coding_language="python",
    )
    assert out["ok"] is True
    assert out["app_kind"] == "api"
    assert out["coding_language"] == "python"
    root = Path(out["target_dir"])
    main = (root / "main.py").read_text()
    reqs = (root / "requirements.txt").read_text()
    meta = (root / "scaffold_meta.json").read_text()
    assert "FastAPI" in main
    assert "POST" in main or "/turn" in main
    assert "run_turn" in main
    assert "ZeusRuntime" in main
    assert "run_agent" not in main
    assert "fastapi" in reqs
    assert "uvicorn" in reqs
    assert '"app_kind": "api"' in meta
    assert "ZEUS_PASSWORD=" not in main
    assert "password_env" not in main


def test_scaffold_rejects_unsupported_coding_language(tmp_path: Path) -> None:
    cfg = HelperConfig(state_dir=tmp_path / "state")
    out = scaffold_app(
        cfg,
        str(tmp_path / "go_app"),
        app_kind="api",
        coding_language="golang",
    )
    assert out["ok"] is False
    assert out["failure_class"] == "unsupported_coding_language"
    assert not (tmp_path / "go_app" / "main.py").exists()


def test_start_project_api_track(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    from zeus_dev_helper_mcp.config import reload_config
    from zeus_dev_helper_mcp.server import start_project
    from zeus_dev_helper_mcp.walkthrough import enriched_next_step

    out = start_project(sample="api")
    assert out["started"] is True
    assert out["track"] == "api"
    assert out["app_kind"] == "api"
    cfg = reload_config()
    nxt = enriched_next_step(cfg)
    # After start, first open item may be 0.1; force check meta-aware hints on 0.2/3.1
    assert nxt.get("app_track") == "api"


def test_verify_local_setup(tmp_path: Path) -> None:
    cfg = HelperConfig(state_dir=tmp_path / "state")
    out = verify_local_setup(cfg, str(tmp_path))
    assert "checks" in out
