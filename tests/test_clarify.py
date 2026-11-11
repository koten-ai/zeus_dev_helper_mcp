"""URL and auth clarification decisions."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

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
    from mcp.server import elicitation
    from mcp.server.mcpserver import resolve

    from zeus_dev_helper_mcp import clarify
    from zeus_dev_helper_mcp.first_create import _connection_form, _llm_form

    render = elicitation.render_elicitation_schema
    assert render is resolve.render_elicitation_schema
    assert render is clarify.render_elicitation_schema
    connection = render(
        _connection_form("http://zeus-dev.local:8080", "pour-user", True)
    )
    assert set(connection) <= {"$schema", "type", "properties", "required"}
    assert "title" not in connection
    assert connection["properties"]["zeus_url"]["title"]
    assert set(connection["properties"]) == {
        "zeus_url",
        "zeus_username",
        "password_in_env",
    }
    assert connection["properties"]["zeus_url"]["default"] == "http://zeus-dev.local:8080"
    assert connection["properties"]["zeus_username"]["default"] == "pour-user"
    llm = render(_llm_form("grok", "grok-custom-model", False))
    assert set(llm) <= {"$schema", "type", "properties", "required"}
    assert "title" not in llm
    assert set(llm["properties"]) == {"llm_provider", "llm_model", "llm_key_in_env"}
    assert llm["properties"]["llm_model"]["default"] == "grok-custom-model"
    assert llm["properties"]["llm_provider"]["default"] == "grok"
    assert "zeus_password" not in connection["properties"]
    assert "llm_api_key" not in llm["properties"]
    assert "token" not in connection["properties"]
    assert "ZEUS_PASSWORD" in connection["properties"]["password_in_env"]["description"]
    assert "LLM_API_KEY" in llm["properties"]["llm_key_in_env"]["description"]
    from zeus_dev_helper_mcp.first_create import _couchbase_form

    couchbase = render(
        _couchbase_form("http://localhost:8093", "Administrator", False)
    )
    assert set(couchbase) <= {"$schema", "type", "properties", "required"}
    assert "title" not in couchbase
    assert set(couchbase["properties"]) == {
        "couchbase_query_url",
        "couchbase_username",
        "couchbase_password_in_env",
    }
    assert couchbase["properties"]["couchbase_query_url"]["type"] == "string"
    assert couchbase["properties"]["couchbase_username"]["type"] == "string"
    assert couchbase["properties"]["couchbase_password_in_env"]["type"] == "boolean"
    assert "couchbase_password" not in couchbase["properties"]
    assert "password" not in couchbase["properties"]
    described = couchbase["properties"]["couchbase_password_in_env"]["description"]
    assert "COUCHBASE_PASSWORD" in described
    assert "Do not type the password into this form" in described
    assert "couchbase_query_url" not in connection["properties"]
    assert "server" not in connection["properties"]
    assert "server" not in llm["properties"]
    assert "server" not in couchbase["properties"]
    from zeus_dev_helper_mcp.first_create import _server_form

    server = render(_server_form())
    assert set(server) <= {"$schema", "type", "properties", "required"}
    assert "title" not in server
    assert set(server["properties"]) == {"server"}
    field = server["properties"]["server"]
    assert field["default"] == "docker"
    assert field["enum"][0] == "docker"
    assert field["enum"] == ["docker", "python"]
    described = field["description"]
    assert "one option" in described
    assert "python -m local_guide" in described
    assert "npm run dev" in described
    assert "port 5000" in described
    assert "port 5173" in described


def test_beer_and_travel_creates_omit_the_server_field(tmp_path, monkeypatch) -> None:
    import asyncio
    import json

    from mcp.server.connection import Connection
    from mcp.server.context import ServerRequestContext
    from mcp.server.mcpserver import Context
    from mcp_types import ElicitResult, InputRequiredResult, InputResponseRequestParams

    from zeus_dev_helper_mcp.server import create_mcp_server

    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("ZEUS_URL", raising=False)
    for name in (
        "ZEUS_USERNAME",
        "ZEUS_USER",
        "ZEUS_PASSWORD",
        "ZEUS_BEARER_TOKEN",
        "ZEUS_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)

    def elicit_ctx(server: object, params: object = None) -> Context:
        connection = Connection.from_envelope(
            "2026-07-28",
            {"name": "test", "version": "0"},
            {"elicitation": {"form": {}}},
        )

        class _Session:
            client_capabilities = connection.client_capabilities

        request = ServerRequestContext(
            session=_Session(),
            lifespan_context={},
            protocol_version="2026-07-28",
            method="tools/call",
            request_id="1",
        )
        return Context(request_context=request, mcp_server=server, input_params=params)

    server = create_mcp_server(["core"])
    accept = ElicitResult(
        action="accept",
        content={
            "zeus_url": "http://192.168.0.219:8080",
            "zeus_username": "edited-user",
            "password_in_env": True,
        },
    )
    for sample, dirname in (("beer", "demo_beer_sample"), ("travel", "demo_travel_sample")):
        root = tmp_path / dirname
        root.mkdir()
        (root / "README.md").write_text(f"# {sample}\n", encoding="utf-8")
        args = {"sample": sample, "sample_dir": str(root)}
        first = asyncio.run(
            server.call_tool("use_sample", args, context=elicit_ctx(server))
        )
        assert isinstance(first, InputRequiredResult)
        conn_key = next(iter(first.input_requests or {}))
        first_schema = first.input_requests[conn_key].params.requested_schema
        assert "server" not in first_schema["properties"]
        assert "docker" not in json.dumps(first_schema)
        second = asyncio.run(
            server.call_tool(
                "use_sample",
                args,
                context=elicit_ctx(
                    server,
                    InputResponseRequestParams(
                        input_responses={conn_key: accept},
                        request_state=first.request_state,
                    ),
                ),
            )
        )
        assert isinstance(second, InputRequiredResult)
        _key, request = next(iter((second.input_requests or {}).items()))
        schema = request.params.requested_schema
        assert set(schema["properties"]) == {
            "llm_provider",
            "llm_model",
            "llm_key_in_env",
        }
        assert "server" not in schema["properties"]
        assert "title" not in schema
        assert "docker" not in json.dumps(schema)


def test_gate_copies_couchbase_strings_and_not_a_password(monkeypatch) -> None:
    import dataclasses
    import os

    from zeus_dev_helper_mcp.clarify import (
        Clarification,
        Gate,
        interpret_gate,
        persist_gate,
        query_url_has_userinfo,
    )

    assert query_url_has_userinfo("http://user:secret@localhost:8093") is True
    assert query_url_has_userinfo("http://localhost:8093") is False
    info = Clarification(
        confirmed=True,
        first_create=True,
        cards_accepted=True,
        zeus_url="http://192.168.0.219:8080",
        zeus_username="edited-user",
        llm_base_url="https://api.x.ai/v1",
        couchbase_query_url="http://127.0.0.1:8093",
        couchbase_username="cb-admin",
        couchbase_password_in_env=False,
        server="docker",
    )
    gate = interpret_gate(info)
    assert gate.couchbase_query_url == "http://127.0.0.1:8093"
    assert gate.couchbase_username == "cb-admin"
    assert gate.couchbase_password_in_env is False
    assert gate.server == "docker"
    assert gate.llm_base_url == "https://api.x.ai/v1"
    assert gate.zeus_username == "edited-user"
    names = {field.name for field in dataclasses.fields(Gate)}
    assert "couchbase_password" not in names
    assert "password" not in names
    for name in (
        "COUCHBASE_QUERY_URL",
        "COUCHBASE_USERNAME",
        "COUCHBASE_PASSWORD",
        "ZEUS_USERNAME",
        "LLM_BASE_URL",
        "LLM_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    before = set(os.environ)
    persist_gate(gate)
    added = set(os.environ) - before
    assert not any("SERVER" in name for name in added)
    assert os.environ["COUCHBASE_QUERY_URL"] == "http://127.0.0.1:8093"
    assert os.environ["COUCHBASE_USERNAME"] == "cb-admin"
    assert "COUCHBASE_PASSWORD" not in os.environ
    persist_gate(
        Gate(
            proceed=True,
            cards_accepted=True,
            couchbase_query_url="http://user:secret@localhost:8093",
            couchbase_username="cb-admin",
        )
    )
    assert os.environ["COUCHBASE_QUERY_URL"] == "http://127.0.0.1:8093"
    assert "secret" not in os.environ["COUCHBASE_QUERY_URL"]


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


def test_beer_destination_skips_a_recorded_dir_that_is_not_serving(tmp_path: Path) -> None:
    from zeus_dev_helper_mcp.beer import (
        beer_destination,
        looks_like_beer_sample,
        save_beer_sample_dir,
    )

    cfg = HelperConfig(state_dir=tmp_path / "state")
    recorded = tmp_path / "recorded"
    (recorded / "static").mkdir(parents=True)
    (recorded / "main.py").write_text("print('old')\n", encoding="utf-8")
    (recorded / "README.md").write_text("readme\n", encoding="utf-8")
    (recorded / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    (recorded / "static" / "index.html").write_text("<html></html>\n", encoding="utf-8")
    assert looks_like_beer_sample(recorded)
    save_beer_sample_dir(cfg, recorded)
    parent = tmp_path / "parent"
    parent.mkdir()
    target = beer_destination(cfg, parent_dir=str(parent))
    assert target.serving_verdict is None
    assert target.root == (parent / "demo_beer_sample").resolve()
    assert target.root != recorded.resolve()


def test_beer_destination_moves_off_a_foreign_directory(tmp_path: Path) -> None:
    from zeus_dev_helper_mcp.beer import beer_destination

    cfg = HelperConfig(state_dir=tmp_path / "state")
    parent = tmp_path / "parent"
    foreign = parent / "demo_beer_sample"
    foreign.mkdir(parents=True)
    (foreign / "notes.txt").write_text("not beer\n", encoding="utf-8")
    target = beer_destination(cfg, parent_dir=str(parent))
    assert target.root == (parent / "demo_beer_sample-2").resolve()
    assert target.relocated_from == str(foreign.resolve())
    assert target.foreign_blocked is False


def test_travel_destination_uses_parent_until_the_port_is_serving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zeus_dev_helper_mcp.travel import travel_destination

    checkout = tmp_path / "already"
    checkout.mkdir()
    (checkout / "README.md").write_text("# travel\n", encoding="utf-8")
    (checkout / "requirements.txt").write_text("x\n", encoding="utf-8")
    (checkout / "src" / "travel_planner").mkdir(parents=True)
    monkeypatch.setenv("DEMO_TRAVEL_SAMPLE_DIR", str(checkout))
    parent = tmp_path / "parent"
    parent.mkdir()
    cfg = HelperConfig(state_dir=tmp_path / "state")

    def closed(port: int, *, timeout: float = 0.6) -> dict[str, object]:
        del timeout
        return {
            "url": f"http://127.0.0.1:{port}/",
            "reachable": False,
            "health_ok": False,
        }

    monkeypatch.setattr("zeus_dev_helper_mcp.travel.probe_travel_port", closed)
    found = travel_destination(cfg, parent_dir=str(parent))
    assert found.serving_verdict is None
    assert found.root == (parent / "demo_travel_sample").resolve()
    assert found.root != checkout.resolve()

    def live(port: int, *, timeout: float = 0.6) -> dict[str, object]:
        del timeout
        return {
            "url": f"http://127.0.0.1:{port}/",
            "reachable": True,
            "health_ok": True,
        }

    monkeypatch.setattr("zeus_dev_helper_mcp.travel.probe_travel_port", live)
    serving = travel_destination(cfg, parent_dir=str(parent))
    assert serving.serving_verdict is not None
    assert serving.serving_verdict["already_serving"] is True
    assert serving.root == checkout.resolve()


def test_yelp_destination_stays_inside_parent_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zeus_dev_helper_mcp.yelp import yelp_destination

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("DEMO_YELP_SAMPLE_DIR", str(elsewhere))
    parent = tmp_path / "work"
    parent.mkdir()
    cfg = HelperConfig(state_dir=tmp_path / "state")
    dest = yelp_destination(cfg, parent_dir=str(parent))
    assert dest == (parent / "demo_yelp").resolve()


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
