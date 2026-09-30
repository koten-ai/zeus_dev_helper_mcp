"""ZDM-19: app login comes from the process, not a stored presence flag."""

from __future__ import annotations

import json
import stat
from pathlib import Path
from typing import ClassVar

import pytest

from zeus_dev_helper_mcp.beer import write_beer_sample
from zeus_dev_helper_mcp.config import HelperConfig, reload_config
from zeus_dev_helper_mcp.prereqs import save_prereqs
from zeus_dev_helper_mcp.readiness import run_readiness_check
from zeus_dev_helper_mcp.scaffold import scaffold_app, use_sample

PASSWORD = "zdm19-password-sentinel"
LLM_KEY = "zdm19-llm-sentinel"
SESSION_ID = "zdm19-session-sentinel"
USER = "tap-user"


def _clear_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "ZEUS_USERNAME",
        "ZEUS_USER",
        "ZEUS_PASSWORD",
        "ZEUS_BEARER_TOKEN",
        "ZEUS_TOKEN",
        "LLM_API_KEY",
        "XAI_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


class _Resp:
    def __init__(self, status: int, payload: dict | None = None) -> None:
        self.status_code = status
        self._payload = {} if payload is None else payload
        self.content = b"{}"

    def json(self) -> dict:
        return self._payload


class _Client:
    calls: ClassVar[list[tuple[str, str]]] = []
    post_status: ClassVar[int] = 401
    post_body: ClassVar[dict] = {"session_id": SESSION_ID}

    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs

    def __enter__(self) -> _Client:  # noqa: PYI034
        return self

    def __exit__(self, *args: object) -> bool:
        del args
        return False

    def get(self, url: str, auth: object = None) -> _Resp:
        del auth
        _Client.calls.append(("GET", str(url)))
        return _Resp(200, {"status": "ok", "version": "0.9.0", "session_id": "from-describe"})

    def post(self, url: str, auth: object = None, headers: object = None) -> _Resp:
        del auth, headers
        _Client.calls.append(("POST", str(url)))
        return _Resp(_Client.post_status, dict(_Client.post_body))

    def close(self) -> None:
        return None


def test_stored_password_flag_is_not_process_presence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_secrets(monkeypatch)
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(state))
    cfg = reload_config()
    save_prereqs(
        cfg,
        {
            "has_username": True,
            "has_password": True,
            "zeus_url": "http://lab.example:8080",
            "auth_mode": "basic",
            "bucket": "beer-sample",
            "scope": "_default",
        },
    )
    cfg = reload_config()
    assert cfg.has_zeus_user is False
    assert cfg.has_zeus_password is False
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.server.list_modes",
        lambda _cfg: {"modes": [{"id": "analytics"}]},
    )
    from zeus_dev_helper_mcp.server import doctor

    out = doctor("health")
    creds = out["credentials"]
    assert creds["stored_has_username"] is True
    assert creds["stored_has_password"] is True
    assert creds["process_has_username"] is False
    assert creds["process_has_password"] is False
    assert PASSWORD not in json.dumps(out)
    monkeypatch.setenv("ZEUS_USERNAME", USER)
    monkeypatch.setenv("ZEUS_PASSWORD", PASSWORD)
    cfg = reload_config()
    assert cfg.has_zeus_user is True
    assert cfg.has_zeus_password is True
    present = doctor("env")
    assert present["credentials"]["process_has_password"] is True
    assert PASSWORD not in json.dumps(present)
    assert USER not in json.dumps(present["credentials"])


def test_basic_auth_without_username_does_not_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_secrets(monkeypatch)
    cfg = HelperConfig(
        zeus_url="http://lab.example:8080",
        zeus_auth_mode="basic",
        default_bucket="beer-sample",
        default_scope="_default",
        state_dir=tmp_path / "state",
    )
    dest = tmp_path / "demo_beer_sample"
    out = use_sample(cfg, sample="beer", sample_dir=str(dest))
    assert out["ok"] is False
    assert out["failure_class"] == "login_not_in_process"
    assert "ZEUS_USERNAME" in out["missing_env"]
    assert not (dest / "main.py").exists()
    blob = json.dumps(out)
    assert PASSWORD not in blob
    assert "smoke_test_agent" not in (out.get("recommended_tools") or [])


def test_process_env_writes_private_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_secrets(monkeypatch)
    monkeypatch.setenv("ZEUS_USERNAME", USER)
    monkeypatch.setenv("ZEUS_PASSWORD", PASSWORD)
    monkeypatch.setenv("LLM_API_KEY", LLM_KEY)
    cfg = HelperConfig(
        zeus_url="http://lab.example:8080",
        zeus_auth_mode="basic",
        default_bucket="beer-sample",
        default_scope="_default",
        state_dir=tmp_path / "state",
    )
    out = write_beer_sample(cfg, tmp_path / "demo_beer_sample")
    assert out["ok"] is True
    assert out["pour_enabled"] is True
    root = Path(out["local_dir"])
    env_text = (root / ".env").read_text(encoding="utf-8")
    assert f"ZEUS_USERNAME={USER}" in env_text
    assert f"ZEUS_PASSWORD={PASSWORD}" in env_text
    assert "ZEUS_URL=http://lab.example:8080" in env_text
    assert "ZEUS_BUCKET=beer-sample" in env_text
    assert f"LLM_API_KEY={LLM_KEY}" in env_text
    assert _mode(root / ".env") == 0o600
    example = (root / ".env.example").read_text(encoding="utf-8")
    assert PASSWORD not in example
    assert LLM_KEY not in example
    assert ".env" in (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "cp .env.example .env" not in (out.get("run") or "")
    assert "cp -n .env.example .env" not in (out.get("run") or "")
    config = (root / "config.json").read_text(encoding="utf-8")
    assert USER in config
    assert PASSWORD not in config
    assert "password_env" in config
    blob = json.dumps(out)
    assert PASSWORD not in blob
    assert LLM_KEY not in blob
    assert USER not in blob or USER in json.dumps(out["app_env"]["env_keys"])
    assert "ZEUS_PASSWORD" in out["app_env"]["env_keys"]
    assert PASSWORD not in out["app_env"]["env_keys"]


def test_missing_llm_key_disables_pour(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_secrets(monkeypatch)
    cfg = HelperConfig(
        zeus_url="http://lab.example:8080",
        default_bucket="beer-sample",
        default_scope="_default",
        state_dir=tmp_path / "state",
    )
    out = use_sample(cfg, sample="beer", parent_dir=str(tmp_path), project_name="demo_beer_sample")
    assert out["ok"] is True
    assert out["pour_enabled"] is False
    assert "smoke_test_agent" not in (out.get("recommended_tools") or [])
    assert "Do not call smoke_test_agent." in (out.get("next_action") or "")
    root = Path(out["local_dir"])
    html = (root / "static" / "index.html").read_text(encoding="utf-8")
    main = (root / "main.py").read_text(encoding="utf-8")
    assert 'id="go"' in html
    assert ">Pour<" in html
    assert "pourEnabled" in html
    assert "disabled" in html
    assert "pour_enabled" in main
    compile(main, str(root / "main.py"), "exec")
    assert LLM_KEY not in json.dumps(out)


def test_existing_dotenv_is_not_rewritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_secrets(monkeypatch)
    monkeypatch.setenv("ZEUS_PASSWORD", PASSWORD)
    root = tmp_path / "demo_beer_sample"
    (root / "static").mkdir(parents=True)
    (root / "main.py").write_text(
        'fetch("pipeline", {"steps": []})\nabort_if_empty\n',
        encoding="utf-8",
    )
    (root / "README.md").write_text("beer sample\n", encoding="utf-8")
    (root / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    (root / "static" / "index.html").write_text("<html></html>\n", encoding="utf-8")
    (root / ".env").write_text("ZEUS_URL=http://lab.example:8080\n", encoding="utf-8")
    cfg = HelperConfig(state_dir=tmp_path / "state", default_bucket="beer-sample")
    out = write_beer_sample(cfg, root)
    assert out["ok"] is True
    assert (root / ".env").read_text(encoding="utf-8") == "ZEUS_URL=http://lab.example:8080\n"
    assert PASSWORD not in json.dumps(out)


def test_scaffold_basic_login_and_private_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_secrets(monkeypatch)
    cfg = HelperConfig(
        zeus_url="http://lab.example:8080",
        zeus_auth_mode="basic",
        default_bucket="beer-sample",
        default_scope="_default",
        state_dir=tmp_path / "state",
    )
    blocked = scaffold_app(cfg, str(tmp_path / "api_app"), app_kind="api")
    assert blocked["ok"] is False
    assert blocked["failure_class"] == "login_not_in_process"
    assert not (tmp_path / "api_app" / "main.py").exists()

    monkeypatch.setenv("ZEUS_USERNAME", USER)
    monkeypatch.setenv("ZEUS_PASSWORD", PASSWORD)
    out = scaffold_app(cfg, str(tmp_path / "api_app"), app_kind="api")
    assert out["ok"] is True
    root = Path(out["target_dir"])
    env_text = (root / ".env").read_text(encoding="utf-8")
    assert f"ZEUS_PASSWORD={PASSWORD}" in env_text
    assert _mode(root / ".env") == 0o600
    assert PASSWORD not in (root / ".env.example").read_text(encoding="utf-8")
    assert PASSWORD not in json.dumps(out)
    assert "cp .env.example .env" not in (out.get("run") or "")
    assert "smoke_test_agent" not in (out.get("recommended_tools") or [])
    assert ".env" in (root / ".gitignore").read_text(encoding="utf-8").splitlines()


def _ready_cfg(tmp_path: Path) -> HelperConfig:
    return HelperConfig(
        zeus_url="http://lab.example:8080",
        zeus_auth_mode="basic",
        default_bucket="beer-sample",
        default_scope="_default",
        state_dir=tmp_path / "state",
        chat_request_dir=tmp_path / "catalog",
    )


def _patch_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    _Client.calls = []
    monkeypatch.setattr("zeus_dev_helper_mcp.readiness.httpx.Client", _Client)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.readiness.list_modes",
        lambda _cfg: {"modes": [{"name": "analytics"}]},
    )


def test_session_401_stops_and_hides_session_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_secrets(monkeypatch)
    monkeypatch.setenv("ZEUS_USERNAME", USER)
    monkeypatch.setenv("ZEUS_PASSWORD", PASSWORD)
    _patch_readiness(monkeypatch)
    _Client.post_status = 401
    _Client.post_body = {"session_id": SESSION_ID}
    out = run_readiness_check(_ready_cfg(tmp_path), update_checklist=False)
    blob = json.dumps(out)
    assert PASSWORD not in blob
    assert SESSION_ID not in blob
    assert "from-describe" not in blob
    auth = next(gate for gate in out["gates"] if gate["id"] == "auth")
    assert auth["status"] == "fail"
    assert auth["failure_class"] == "auth_failed"
    assert auth["evidence"]["has_session_id"] is False
    assert auth["evidence"]["bucket"] == "beer-sample"
    bootstrap = next(gate for gate in out["gates"] if gate["id"] == "bootstrap_scope")
    assert bootstrap["status"] == "skip"
    assert not any("bootstrap" in url or "chat_request" in url for _method, url in _Client.calls)
    assert any(url.endswith("/auth/session") for _method, url in _Client.calls)


def test_describe_200_is_not_a_login(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_secrets(monkeypatch)
    _patch_readiness(monkeypatch)
    _Client.post_status = 200
    _Client.post_body = {"session_id": SESSION_ID}
    # No process login: every GET is 200, including a describe-shaped body.
    out = run_readiness_check(_ready_cfg(tmp_path), update_checklist=False)
    auth = next(gate for gate in out["gates"] if gate["id"] == "auth")
    assert auth["status"] == "fail"
    assert auth["failure_class"] == "login_not_in_process"
    assert "from-describe" not in json.dumps(out)
    assert not any(method == "POST" for method, _url in _Client.calls)

    monkeypatch.setenv("ZEUS_USERNAME", USER)
    monkeypatch.setenv("ZEUS_PASSWORD", PASSWORD)
    _Client.calls = []
    minted = run_readiness_check(_ready_cfg(tmp_path), update_checklist=False)
    passed = next(gate for gate in minted["gates"] if gate["id"] == "auth")
    assert passed["status"] == "pass"
    assert passed["evidence"]["has_session_id"] is True
    blob = json.dumps(minted)
    assert SESSION_ID not in blob
    assert PASSWORD not in blob
    assert any("bootstrap" in url for _method, url in _Client.calls)
