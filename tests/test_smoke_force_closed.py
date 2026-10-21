"""ZDM-36: describe HTTP 429 session_force_closed is not dispatch_failed."""

from __future__ import annotations

import json
from pathlib import Path

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.diagnose import _NEXT as _DIAGNOSE_NEXT
from zeus_dev_helper_mcp.smoke import smoke_test_zeus

_BODY = {
    "error": "session_force_closed",
    "message": "session exceeded per-session round budget; re-authenticate to continue",
}
_REQ = "6572e0a0-63db-4135-943d-66371d2f213e"


def _cfg(tmp_path: Path) -> HelperConfig:
    return HelperConfig(
        zeus_url="http://lab.example:8080",
        default_bucket="beer-sample",
        default_scope="_default",
        state_dir=tmp_path / "state",
    )


def _ready() -> dict:
    return {
        "overall": "pass",
        "authenticated_bucket": "beer-sample",
        "prereq_bucket": "beer-sample",
        "request_buckets": ["beer-sample"],
        "primary_failure_class": None,
        "next_action": "ready",
    }


class _Resp:
    def __init__(self, status: int, body: dict) -> None:
        self.status_code = status
        self.text = json.dumps(body)
        self.headers = {"X-Zeus-Req-Id": _REQ}

    def json(self) -> dict:
        return json.loads(self.text)


def _install(monkeypatch, status: int, body: dict) -> None:
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.smoke.run_readiness_check",
        lambda *args, **kwargs: _ready(),
    )

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> bool:
            return False

        def post(self, url, **kwargs):
            assert "/v2/beer-sample/_default/describe" in url
            return _Resp(status, body)

    monkeypatch.setattr("zeus_dev_helper_mcp.smoke.httpx.Client", _Client)


def test_describe_429_session_force_closed(tmp_path: Path, monkeypatch) -> None:
    _install(monkeypatch, 429, _BODY)
    out = smoke_test_zeus(_cfg(tmp_path), update_checklist=False)
    assert out["ok"] is False
    assert out["failure_class"] == "session_force_closed"
    assert out["next_action"] == _DIAGNOSE_NEXT["session_force_closed"]
    assert "Stop probing" in out["next_action"]
    assert out["req_id"] == _REQ
    step = next(item for item in out["steps"] if item["name"] == "describe")
    assert step["failure_class"] == "session_force_closed"
    assert step["status"] == 429


def test_describe_401_stays_auth_failed(tmp_path: Path, monkeypatch) -> None:
    _install(monkeypatch, 401, {"error": "unauthenticated"})
    out = smoke_test_zeus(_cfg(tmp_path), update_checklist=False)
    assert out["failure_class"] == "auth_failed"


def test_describe_404_stays_scope_not_enabled(tmp_path: Path, monkeypatch) -> None:
    _install(monkeypatch, 404, {"error": "not_found"})
    out = smoke_test_zeus(_cfg(tmp_path), update_checklist=False)
    assert out["failure_class"] == "scope_not_enabled"


def test_describe_429_other_error_stays_dispatch_failed(tmp_path: Path, monkeypatch) -> None:
    _install(monkeypatch, 429, {"error": "explain_cap_exhausted"})
    out = smoke_test_zeus(_cfg(tmp_path), update_checklist=False)
    assert out["failure_class"] == "dispatch_failed"
    assert "Fix describe failure" in out["next_action"]
