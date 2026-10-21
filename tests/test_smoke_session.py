"""ZDM-37: smoke mints a scope session and does not spend the shared dev session."""

from __future__ import annotations

import json
from pathlib import Path

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.readiness import take_scope_session
from zeus_dev_helper_mcp.smoke import smoke_test_agent, smoke_test_zeus

_SID = "sess_zdm37_do_not_leak"
_PASSWORD = "pw-zdm37-do-not-leak"
_REQ = "req-zdm37"


def _cfg(tmp_path: Path, **kwargs) -> HelperConfig:
    data = {
        "zeus_url": "http://lab.example:8080",
        "zeus_auth_mode": "basic",
        "default_bucket": "beer-sample",
        "default_scope": "_default",
        "state_dir": tmp_path / "state",
    }
    data.update(kwargs)
    return HelperConfig(**data)


def _ready(**kwargs) -> dict:
    out = {
        "overall": "pass",
        "authenticated_bucket": "beer-sample",
        "prereq_bucket": "beer-sample",
        "request_buckets": ["beer-sample"],
        "primary_failure_class": None,
        "next_action": "ready",
    }
    out.update(kwargs)
    return out


class _Resp:
    def __init__(self, status: int, body: dict, headers: dict | None = None) -> None:
        self.status_code = status
        self._body = body
        self.text = json.dumps(body)
        self.headers = headers or {}

    def json(self) -> dict:
        return self._body


def test_take_scope_session_hides_the_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ZEUS_USERNAME", "tap")
    monkeypatch.setenv("ZEUS_PASSWORD", _PASSWORD)

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def post(self, url, **kwargs):
            assert kwargs["auth"] == ("tap", _PASSWORD)
            return _Resp(200, {"session_id": _SID, "expires_in": 1800})

        def close(self) -> None:
            return None

    monkeypatch.setattr("zeus_dev_helper_mcp.readiness.httpx.Client", _Client)
    public, sid = take_scope_session(_cfg(tmp_path))
    assert public["ok"] is True
    assert public["has_session_id"] is True
    assert sid == _SID
    blob = json.dumps(public)
    assert _SID not in blob
    assert _PASSWORD not in blob


def test_basic_describe_sends_only_the_session(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ZEUS_USERNAME", "tap")
    monkeypatch.setenv("ZEUS_PASSWORD", _PASSWORD)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.smoke.run_readiness_check",
        lambda *args, **kwargs: _ready(),
    )
    posts: list[tuple[str, dict]] = []

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            assert "Authorization" not in (kwargs.get("headers") or {})

        def __enter__(self):
            return self

        def __exit__(self, *args) -> bool:
            return False

        def post(self, url, **kwargs):
            posts.append((url, kwargs))
            if url.endswith("/auth/session"):
                return _Resp(200, {"session_id": _SID})
            return _Resp(200, {"ok": True}, {"X-Zeus-Req-Id": _REQ})

    monkeypatch.setattr("zeus_dev_helper_mcp.smoke.httpx.Client", _Client)
    out = smoke_test_zeus(_cfg(tmp_path), update_checklist=False)
    assert out["ok"] is True
    assert out["req_id"] == _REQ
    describe = [item for item in posts if item[0].endswith("/describe")]
    mint = [item for item in posts if item[0].endswith("/auth/session")]
    assert len(mint) == 1
    assert len(describe) == 1
    headers = describe[0][1]["headers"]
    assert headers["X-Zeus-Session"] == _SID
    assert "Authorization" not in headers
    assert describe[0][1]["auth"] is None
    blob = json.dumps(out)
    assert _SID not in blob
    assert _PASSWORD not in blob


def test_login_stop_does_not_describe(tmp_path: Path, monkeypatch) -> None:
    def _boom(*args, **kwargs):
        raise AssertionError("anonymous describe must not be sent")

    monkeypatch.setattr("zeus_dev_helper_mcp.smoke.httpx.Client", _boom)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.smoke.run_readiness_check",
        lambda *args, **kwargs: _ready(
            overall="fail",
            primary_failure_class="login_not_in_process",
            next_action="call load_process_login",
        ),
    )
    out = smoke_test_zeus(_cfg(tmp_path), update_checklist=False)
    assert out["ok"] is False
    assert out["failure_class"] == "login_not_in_process"
    assert out["next_action"] == "call load_process_login"
    assert all(step["name"] != "describe" for step in out["steps"])


def test_auth_failed_stop_does_not_describe(tmp_path: Path, monkeypatch) -> None:
    def _boom(*args, **kwargs):
        raise AssertionError("anonymous describe must not be sent")

    monkeypatch.setattr("zeus_dev_helper_mcp.smoke.httpx.Client", _boom)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.smoke.run_readiness_check",
        lambda *args, **kwargs: _ready(
            overall="fail",
            primary_failure_class="auth_failed",
            next_action="Do not try another password.",
        ),
    )
    out = smoke_test_zeus(_cfg(tmp_path), update_checklist=False)
    assert out["failure_class"] == "auth_failed"
    assert "password" in out["next_action"]


def test_agent_stops_when_login_is_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "llm-secret")
    monkeypatch.delenv("ZEUS_USERNAME", raising=False)
    monkeypatch.delenv("ZEUS_PASSWORD", raising=False)

    def _boom(*args, **kwargs):
        raise AssertionError("turn must not start")

    monkeypatch.setattr("zeus_client.ZeusRuntime", _boom)
    out = smoke_test_agent(_cfg(tmp_path), update_checklist=False)
    assert out["ok"] is False
    assert out["failure_class"] == "login_not_in_process"
    blob = json.dumps(out)
    assert "llm-secret" not in blob
    assert _PASSWORD not in blob


def test_agent_runtime_uses_the_minted_session(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "llm-secret")
    monkeypatch.setenv("ZEUS_USERNAME", "tap")
    monkeypatch.setenv("ZEUS_PASSWORD", _PASSWORD)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.smoke.take_scope_session",
        lambda *args, **kwargs: (
            {"ok": True, "has_session_id": True, "status": 200, "failure_class": None},
            _SID,
        ),
    )
    seen: dict = {}

    class _Runtime:
        def __init__(self, rt_cfg, **kwargs) -> None:
            seen["auth_mode"] = rt_cfg.zeus.auth_mode
            seen["token_env"] = rt_cfg.zeus.token_env
            seen["password_env"] = rt_cfg.zeus.password_env
            seen["username"] = rt_cfg.zeus.username
            seen["sid"] = kwargs["secrets"].get(rt_cfg.zeus.token_env)
            raise RuntimeError("stop before turn")

    monkeypatch.setattr("zeus_client.ZeusRuntime", _Runtime)
    out = smoke_test_agent(_cfg(tmp_path), update_checklist=False)
    assert seen["auth_mode"] == "session"
    assert seen["token_env"] == "ZEUS_SMOKE_SESSION"
    assert not seen["password_env"]
    assert not seen["username"]
    assert seen["sid"] == _SID
    blob = json.dumps(out)
    assert _SID not in blob
    assert _PASSWORD not in blob
    assert "llm-secret" not in blob
