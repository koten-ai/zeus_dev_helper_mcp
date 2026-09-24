"""URL and auth clarification decisions. No MCP session."""

from __future__ import annotations

import httpx

from zeus_dev_helper_mcp.clarify import (
    auth_form_schema,
    credentials_for,
    probe_auth_required,
    url_decision,
    valid_public_url,
)
from zeus_dev_helper_mcp.config import HelperConfig


def test_empty_url_asks_even_when_host_env_is_set(monkeypatch) -> None:
    monkeypatch.setenv("ZEUS_URL", "http://zeus-dev.local:8080")
    assert url_decision("", "") == "ask"


def test_stored_zeus_url_is_reused() -> None:
    assert url_decision("", "http://192.168.0.219:8080") == "use"


def test_explicit_argument_is_used_and_hub_port_is_rejected() -> None:
    assert url_decision("http://192.168.0.219:8080", "") == "use"
    assert url_decision("http://hub.example:9091", "") == "reject"
    assert url_decision("http://user:secret@host:8080", "") == "reject"
    assert valid_public_url("http://192.168.0.219:8080") is True
    assert valid_public_url("not-a-url") is False


def test_auth_schema_has_no_secret_fields() -> None:
    schema = auth_form_schema()
    assert set(schema["properties"]) == {"auth_mode", "credentials_ready"}
    assert "password" not in schema["properties"]
    assert "username" not in schema["properties"]
    assert "token" not in schema["properties"]


def test_basic_without_env_does_not_set_password(monkeypatch) -> None:
    for name in (
        "ZEUS_USERNAME",
        "ZEUS_USER",
        "ZEUS_PASSWORD",
        "ZEUS_BEARER_TOKEN",
        "ZEUS_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    got = credentials_for("basic")
    assert got["ok"] is False
    assert "has_password" not in got
    assert got.get("has_password") is not True


def test_probe_tri_state(monkeypatch) -> None:
    seen: dict[str, str] = {}

    def fake_get(url: str, **kwargs: object) -> object:
        seen["url"] = url
        code = seen.get("code")
        if code == "err":
            raise httpx.ConnectError("down")

        class Response:
            status_code = int(code)  # type: ignore[arg-type]

        return Response()

    monkeypatch.setattr("zeus_dev_helper_mcp.clarify.httpx.get", fake_get)
    seen["code"] = "401"
    assert (
        probe_auth_required("http://h:8080", "beer-sample", "_default")
        == "unauthorized"
    )
    assert seen["url"].endswith("/v1/ai/bootstrap/scope/beer-sample/_default")
    assert "auth/session" not in seen["url"]
    seen["code"] = "403"
    assert (
        probe_auth_required("http://h:8080", "beer-sample", "_default")
        == "unauthorized"
    )
    seen["code"] = "200"
    assert probe_auth_required("http://h:8080", "beer-sample", "_default") == "open"
    seen["code"] = "404"
    assert probe_auth_required("http://h:8080", "beer-sample", "_default") == "open"
    seen["code"] = "err"
    assert (
        probe_auth_required("http://h:8080", "beer-sample", "_default") == "unreachable"
    )


def test_doctor_url_confirmed_follows_stored_prereq(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ZEUS_URL", "http://zeus-dev.local:8080")
    from zeus_dev_helper_mcp.server import _url_routing_view

    view = _url_routing_view(HelperConfig(state_dir=tmp_path))
    assert view["zeus_url_confirmed"] is False
    assert view["env_zeus_url"] == "http://zeus-dev.local:8080"
    (tmp_path / "prereqs.json").write_text(
        '{"zeus_url": "http://192.168.0.219:8080"}\n', encoding="utf-8"
    )
    view = _url_routing_view(HelperConfig(state_dir=tmp_path))
    assert view["zeus_url_confirmed"] is True
    assert view["stored_zeus_url"] == "http://192.168.0.219:8080"
