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


def test_connection_schema_has_no_secret_fields() -> None:
    from mcp.server.elicitation import render_elicitation_schema

    from zeus_dev_helper_mcp.clarify import _connection_form, _llm_form

    connection = render_elicitation_schema(
        _connection_form("http://zeus-dev.local:8080", "pour-user", True)
    )
    assert set(connection["properties"]) == {
        "zeus_url",
        "zeus_username",
        "password_in_env",
    }
    assert connection["properties"]["zeus_url"]["default"] == "http://zeus-dev.local:8080"
    assert connection["properties"]["zeus_username"]["default"] == "pour-user"
    llm = render_elicitation_schema(_llm_form("grok", "grok-custom-model", False))
    assert set(llm["properties"]) == {"llm_provider", "llm_model", "llm_key_in_env"}
    assert llm["properties"]["llm_model"]["default"] == "grok-custom-model"
    assert llm["properties"]["llm_provider"]["default"] == "grok"
    assert "zeus_password" not in connection["properties"]
    assert "llm_api_key" not in llm["properties"]
    assert "token" not in connection["properties"]
    assert "ZEUS_PASSWORD" in connection["properties"]["password_in_env"]["description"]
    assert "LLM_API_KEY" in llm["properties"]["llm_key_in_env"]["description"]


def test_overlay_keeps_password_and_api_key(tmp_path) -> None:
    from zeus_dev_helper_mcp.app_env import overlay_nonsecret_env

    root = tmp_path / "app"
    root.mkdir()
    env = root / ".env"
    env.write_text(
        "ZEUS_USERNAME=old-user\n"
        "ZEUS_PASSWORD=keep-password\n"
        'LLM_API_KEY="keep-llm-key"\n'
        "LLM_MODEL=old-model\n",
        encoding="utf-8",
    )
    overlay_nonsecret_env(
        root,
        {
            "ZEUS_URL": "http://192.168.0.219:8080",
            "ZEUS_USERNAME": "edited-user",
            "LLM_BASE_URL": "https://api.x.ai/v1",
            "LLM_MODEL": "grok-custom-model",
            "ZEUS_PASSWORD": "should-not-stick",
            "LLM_API_KEY": "should-not-stick",
        },
    )
    text = env.read_text(encoding="utf-8")
    assert "ZEUS_PASSWORD=keep-password" in text
    assert 'LLM_API_KEY="keep-llm-key"' in text
    assert "should-not-stick" not in text
    assert "ZEUS_URL=http://192.168.0.219:8080" in text
    assert "ZEUS_USERNAME=edited-user" in text
    assert "LLM_MODEL=grok-custom-model" in text


def test_provider_match_and_other_keeps_base_url() -> None:
    from zeus_dev_helper_mcp.env_questions import (
        llm_base_and_model,
        provider_for_base_url,
    )

    assert provider_for_base_url("https://api.x.ai/v1") == "grok"
    assert provider_for_base_url("https://example.test/v1") == "other"
    assert provider_for_base_url("") == "grok"
    base, model = llm_base_and_model("openai", "", "https://api.x.ai/v1")
    assert base == "https://api.openai.com/v1"
    assert model
    kept, kept_model = llm_base_and_model(
        "other", "custom-model", "https://example.test/v1"
    )
    assert kept == "https://example.test/v1"
    assert kept_model == "custom-model"


def test_first_create_is_a_missing_log_file(tmp_path, monkeypatch) -> None:
    from zeus_dev_helper_mcp.config import HelperConfig
    from zeus_dev_helper_mcp.sample_log import (
        first_create_pending,
        seal_creation_marker,
    )

    cfg = HelperConfig(state_dir=tmp_path)
    assert first_create_pending(cfg, "beer") is True
    assert first_create_pending(cfg, "api") is False
    assert first_create_pending(cfg, "api", api=True) is True
    seal_creation_marker(cfg, "beer")
    assert first_create_pending(cfg, "beer") is False
    assert (tmp_path / "beer-sample-build.md").is_file()
    monkeypatch.delenv("ZEUS_URL", raising=False)


def test_beer_needs_the_llm_card_and_travel_opt_out_does_not(tmp_path, monkeypatch) -> None:
    from zeus_dev_helper_mcp.clarify import create_needs_llm_card
    from zeus_dev_helper_mcp.config import reload_config
    from zeus_dev_helper_mcp.prereqs import save_prereqs

    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path))
    assert create_needs_llm_card("beer") is True
    assert create_needs_llm_card("api") is True
    save_prereqs(reload_config(), {"has_llm_key": False})
    assert create_needs_llm_card("travel") is False
    assert create_needs_llm_card("beer") is True


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
