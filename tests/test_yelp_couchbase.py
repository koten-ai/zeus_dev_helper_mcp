"""Yelp Couchbase .env merge. The password value is never an argument."""

from __future__ import annotations

import asyncio
import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from zeus_dev_helper_mcp.clarify import Gate
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.process_login import _LOGIN_KEYS, load_process_login
from zeus_dev_helper_mcp.yelp import apply_couchbase_env

SECRET = "cb-secret-sentinel"


def _presence(*, password: bool) -> dict[str, bool]:
    return {
        "ZEUS_PASSWORD": False,
        "ZEUS_BEARER_TOKEN": False,
        "LLM_API_KEY": False,
        "COUCHBASE_PASSWORD": password,
    }


def _quiet_process(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    for name in (
        "ZEUS_URL",
        "ZEUS_USERNAME",
        "ZEUS_USER",
        "ZEUS_PASSWORD",
        "ZEUS_BEARER_TOKEN",
        "ZEUS_TOKEN",
        "ZEUS_AUTH_MODE",
        "LLM_API_KEY",
        "XAI_API_KEY",
        "OPENAI_API_KEY",
        "LLM_BASE_URL",
        "LLM_MODEL",
        "COUCHBASE_QUERY_URL",
        "COUCHBASE_USERNAME",
        "COUCHBASE_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_login_keys_do_not_include_the_couchbase_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert "COUCHBASE_PASSWORD" not in _LOGIN_KEYS
    monkeypatch.delenv("COUCHBASE_PASSWORD", raising=False)
    monkeypatch.delenv("ZEUS_USERNAME", raising=False)
    monkeypatch.delenv("ZEUS_PASSWORD", raising=False)
    path = tmp_path / "login.env"
    path.write_text(
        f"ZEUS_USERNAME=tap-user\nZEUS_PASSWORD=zeus-only\nCOUCHBASE_PASSWORD={SECRET}\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)
    out = load_process_login(str(path))
    assert out["ok"] is True
    assert "COUCHBASE_PASSWORD" not in out["loaded"]
    assert os.environ.get("COUCHBASE_PASSWORD") in (None, "")
    assert SECRET not in json.dumps(out)


def _apply(root: Path, url: str, username: str, *, password_in_env: bool) -> dict:
    return apply_couchbase_env(
        {"ok": True, "sample": "demo_yelp", "local_dir": str(root)},
        Gate(
            proceed=True,
            cards_accepted=True,
            couchbase_query_url=url,
            couchbase_username=username,
            couchbase_password_in_env=password_in_env,
        ),
    )


def test_write_creates_env_from_example_without_a_password_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _quiet_process(monkeypatch, tmp_path)
    root = tmp_path / "demo_yelp"
    root.mkdir()
    (root / ".env.example").write_text(
        "COUCHBASE_QUERY_URL=http://old.example:8093\nOTHER=kept\n",
        encoding="utf-8",
    )
    report = _apply(root, "http://localhost:8093", "Administrator", password_in_env=False)
    env = root / ".env"
    text = env.read_text(encoding="utf-8")
    assert _mode(env) == 0o600
    assert "COUCHBASE_QUERY_URL=http://localhost:8093\n" in text
    assert "COUCHBASE_USERNAME=Administrator\n" in text
    assert "COUCHBASE_PASSWORD=\n" in text
    assert "OTHER=kept" in text
    assert SECRET not in text
    assert report["env_change"] is False
    assert report["settings_written"] == ["COUCHBASE_QUERY_URL", "COUCHBASE_USERNAME"]
    assert report["secret_presence"] == _presence(password=False)
    assert ".env" in (root / ".gitignore").read_text(encoding="utf-8")
    assert SECRET not in json.dumps(report)


def test_write_keeps_an_existing_password_line(tmp_path: Path) -> None:
    root = tmp_path / "demo_yelp"
    root.mkdir()
    env = root / ".env"
    env.write_text(
        "export COUCHBASE_QUERY_URL=http://old.example:8093\n"
        "COUCHBASE_USERNAME=old-user\n"
        f'export COUCHBASE_PASSWORD="{SECRET}"\n',
        encoding="utf-8",
    )
    report = _apply(root, "http://127.0.0.1:8093", "cb-admin", password_in_env=True)
    text = env.read_text(encoding="utf-8")
    assert f'export COUCHBASE_PASSWORD="{SECRET}"' in text
    assert "export COUCHBASE_QUERY_URL=http://127.0.0.1:8093" in text
    assert "COUCHBASE_USERNAME=cb-admin" in text
    assert _mode(env) == 0o600
    assert report["env_change"] is True
    assert report["settings_written"] == ["COUCHBASE_QUERY_URL", "COUCHBASE_USERNAME"]
    assert report["secret_presence"] == _presence(password=True)
    assert "COUCHBASE_PASSWORD" not in report["settings_written"]
    assert SECRET not in json.dumps(report)


def test_apply_writes_strings_and_skips_userinfo_and_other_samples(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _quiet_process(monkeypatch, tmp_path)
    root = tmp_path / "demo_yelp"
    root.mkdir()
    (root / "README.md").write_text("# yelp\n", encoding="utf-8")
    payload = {
        "ok": True,
        "sample": {"sample": "demo_yelp", "name": "demo_yelp"},
        "local_dir": str(root),
        "next_action": "start",
    }
    skipped = apply_couchbase_env(
        dict(payload),
        Gate(
            proceed=True,
            cards_accepted=True,
            couchbase_query_url=f"http://user:{SECRET}@127.0.0.1:8093",
            couchbase_username="Administrator",
            couchbase_password_in_env=False,
        ),
    )
    assert not (root / ".env").exists()
    assert "settings_written" not in skipped
    assert SECRET not in json.dumps(skipped)

    written = apply_couchbase_env(
        dict(payload),
        Gate(
            proceed=True,
            cards_accepted=True,
            couchbase_query_url="http://127.0.0.1:8093",
            couchbase_username="cb-admin",
            couchbase_password_in_env=False,
        ),
    )
    text = (root / ".env").read_text(encoding="utf-8")
    assert "COUCHBASE_QUERY_URL=http://127.0.0.1:8093" in text
    assert "COUCHBASE_USERNAME=cb-admin" in text
    assert "COUCHBASE_PASSWORD=\n" in text
    assert SECRET not in text
    assert written["settings_written"] == ["COUCHBASE_QUERY_URL", "COUCHBASE_USERNAME"]
    assert written["secret_presence"] == _presence(password=False)
    assert "Fill COUCHBASE_PASSWORD" in written["next_action"]
    assert str(root / ".env") in written["next_action"]
    assert "python -m local_guide" in written["next_action"]
    assert "Do not type the password into the form" in written["next_action"]
    assert SECRET not in json.dumps(written)

    beer = {"ok": True, "sample": "beer", "local_dir": str(root), "next_action": "pour"}
    before = (root / ".env").read_text(encoding="utf-8")
    assert apply_couchbase_env(beer, Gate(proceed=True, cards_accepted=True)) == beer
    assert (root / ".env").read_text(encoding="utf-8") == before

    quiet = apply_couchbase_env(
        dict(payload),
        Gate(proceed=True, cards_accepted=False, couchbase_password_in_env=False),
    )
    assert "settings_written" not in quiet


def test_config_json_does_not_receive_the_couchbase_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zeus_dev_helper_mcp.yelp_config import write_yelp_config

    monkeypatch.delenv("ZEUS_PASSWORD", raising=False)
    monkeypatch.setenv("ZEUS_PASSWORD", "zeus-only-sentinel")
    root = tmp_path / "demo_yelp"
    root.mkdir()
    (root / ".env").write_text(f"COUCHBASE_PASSWORD={SECRET}\n", encoding="utf-8")
    cfg = HelperConfig(
        state_dir=tmp_path / "state",
        zeus_url="http://zeus-dev.local:8080",
        default_bucket="yelp-demo",
        default_scope="_default",
        zeus_auth_mode="none",
    )
    assert write_yelp_config(cfg, root)["created"] is True
    text = (root / "config.json").read_text(encoding="utf-8")
    assert SECRET not in text
    assert "COUCHBASE" not in text
    assert "zeus-only-sentinel" in text


def _run(coro):
    return asyncio.run(coro)


def _structured(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structured_content", None) or getattr(
        result, "structuredContent", None
    )
    if structured is None and hasattr(result, "model_dump"):
        dumped = result.model_dump(by_alias=True)
        structured = dumped.get("structuredContent") or dumped.get("structured_content")
    assert isinstance(structured, dict)
    return structured


def _elicit_ctx(server: Any, *, form: bool, params: Any = None) -> Any:
    from mcp.server.connection import Connection
    from mcp.server.context import ServerRequestContext
    from mcp.server.mcpserver import Context

    caps: dict[str, Any] = {"elicitation": {"form": {}}} if form else {}
    connection = Connection.from_envelope(
        "2026-07-28", {"name": "test", "version": "0"}, caps
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


def _isolate_prereqs(tmp_path, monkeypatch) -> None:
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


def _accept(content: dict[str, Any]) -> Any:
    from mcp_types import ElicitResult

    return ElicitResult(action="accept", content=content)


_CONN = {
    "zeus_url": "http://192.168.0.219:8080",
    "zeus_username": "edited-user",
    "password_in_env": True,
}


def _prepare_yelp_tree(tmp_path, monkeypatch, *, env_text: str | None) -> Any:
    _isolate_prereqs(tmp_path, monkeypatch)
    monkeypatch.setenv("ZEUS_DEV_HELPER_SKIP_YELP_IMAGES", "1")
    monkeypatch.delenv("DEMO_YELP_SAMPLE_DIR", raising=False)
    monkeypatch.delenv("ZEUS_AUTH_MODE", raising=False)
    for name in ("COUCHBASE_QUERY_URL", "COUCHBASE_USERNAME", "COUCHBASE_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.clarify.probe_auth_required",
        lambda *args, **kwargs: "open",
    )
    root = tmp_path / "demo_yelp"
    root.mkdir()
    (root / "README.md").write_text("# yelp\n", encoding="utf-8")
    (root / "frontend").mkdir()
    (root / "frontend" / "package.json").write_text("{}\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        "[project]\nname='local-guide'\n", encoding="utf-8"
    )
    if env_text is not None:
        env = root / ".env"
        env.write_text(env_text, encoding="utf-8")
        env.chmod(0o600)
    return root


def _yelp_call(server: Any, args: dict[str, Any], params: Any = None) -> Any:
    return _run(
        server.call_tool(
            "use_sample", args, context=_elicit_ctx(server, form=True, params=params)
        )
    )


def _respond(server: Any, args: dict[str, Any], state: Any, responses: dict) -> Any:
    from mcp_types import InputResponseRequestParams

    return _yelp_call(
        server,
        args,
        InputResponseRequestParams(input_responses=responses, request_state=state),
    )


def _pending(result: Any) -> tuple[str, Any]:
    from mcp_types import InputRequiredResult

    assert isinstance(result, InputRequiredResult)
    key = next(iter(result.input_requests or {}))
    return key, result.input_requests[key]


def test_travel_connection_schema_has_no_couchbase_fields(tmp_path, monkeypatch) -> None:
    from zeus_dev_helper_mcp.server import create_mcp_server

    root = tmp_path / "demo_travel_sample"
    root.mkdir()
    (root / "README.md").write_text("# travel\n", encoding="utf-8")
    _isolate_prereqs(tmp_path, monkeypatch)
    server = create_mcp_server(["core"])
    first = _yelp_call(server, {"sample": "travel", "sample_dir": str(root)})
    _key, request = _pending(first)
    assert set(request.params.requested_schema["properties"]) == {
        "zeus_url",
        "zeus_username",
        "password_in_env",
    }
    assert "couchbase" not in json.dumps(request.params.requested_schema)


def test_yelp_create_asks_connection_then_couchbase_then_llm(tmp_path, monkeypatch) -> None:
    from zeus_dev_helper_mcp.server import create_mcp_server
    from zeus_dev_helper_mcp.yelp import apply_couchbase_env as real_apply

    root = _prepare_yelp_tree(
        tmp_path,
        monkeypatch,
        env_text=(
            "ZEUS_USERNAME=pour-user\n"
            "COUCHBASE_QUERY_URL=http://cb.example:8093\n"
            "COUCHBASE_USERNAME=from-file\n"
            f'export COUCHBASE_PASSWORD="{SECRET}"\n'
        ),
    )
    seen: dict[str, Any] = {}

    def _spy(payload: dict[str, Any], gate: Any) -> dict[str, Any]:
        seen["url"] = gate.couchbase_query_url
        seen["user"] = gate.couchbase_username
        seen["flag"] = gate.couchbase_password_in_env
        assert SECRET not in repr(gate)
        return real_apply(payload, gate)

    monkeypatch.setattr("zeus_dev_helper_mcp.yelp.apply_couchbase_env", _spy)
    server = create_mcp_server(["core"])
    args = {"sample": "demo_yelp", "sample_dir": str(root)}
    first = _yelp_call(server, args)
    conn_key, conn = _pending(first)
    assert set(conn.params.requested_schema["properties"]) == {
        "zeus_url",
        "zeus_username",
        "password_in_env",
    }
    assert "couchbase" not in json.dumps(conn.params.requested_schema)
    second = _respond(server, args, first.request_state, {conn_key: _accept(_CONN)})
    cb_key, card = _pending(second)
    schema = card.params.requested_schema
    assert set(schema) <= {"$schema", "type", "properties", "required"}
    props = schema["properties"]
    assert set(props) == {
        "couchbase_query_url",
        "couchbase_username",
        "couchbase_password_in_env",
    }
    assert props["couchbase_query_url"]["type"] == "string"
    assert props["couchbase_username"]["type"] == "string"
    assert props["couchbase_password_in_env"]["type"] == "boolean"
    assert "password" not in props
    assert props["couchbase_query_url"]["default"] == "http://cb.example:8093"
    assert props["couchbase_username"]["default"] == "from-file"
    assert props["couchbase_password_in_env"]["default"] is True
    assert "COUCHBASE_PASSWORD" in props["couchbase_password_in_env"]["description"]
    assert "Do not type the password" in card.params.message
    assert SECRET not in card.params.message
    third = _respond(
        server,
        args,
        second.request_state,
        {
            conn_key: _accept(_CONN),
            cb_key: _accept(
                {
                    "couchbase_query_url": "http://127.0.0.1:8093",
                    "couchbase_username": "cb-admin",
                    "couchbase_password_in_env": False,
                }
            ),
        },
    )
    llm_key, llm = _pending(third)
    assert set(llm.params.requested_schema["properties"]) == {
        "llm_provider",
        "llm_model",
        "llm_key_in_env",
    }
    llm_props = llm.params.requested_schema["properties"]
    result = _respond(
        server,
        args,
        third.request_state,
        {
            conn_key: _accept(_CONN),
            cb_key: _accept(
                {
                    "couchbase_query_url": "http://127.0.0.1:8093",
                    "couchbase_username": "cb-admin",
                    "couchbase_password_in_env": False,
                }
            ),
            llm_key: _accept(
                {
                    "llm_provider": llm_props["llm_provider"]["default"],
                    "llm_model": llm_props["llm_model"]["default"],
                    "llm_key_in_env": llm_props["llm_key_in_env"]["default"],
                }
            ),
        },
    )
    body = _structured(result)
    assert body["ok"] is True
    assert seen["url"] == "http://127.0.0.1:8093"
    assert seen["user"] == "cb-admin"
    assert seen["flag"] is False
    env_text = (root / ".env").read_text(encoding="utf-8")
    assert "COUCHBASE_QUERY_URL=http://127.0.0.1:8093" in env_text
    assert "COUCHBASE_USERNAME=cb-admin" in env_text
    assert f'export COUCHBASE_PASSWORD="{SECRET}"' in env_text
    assert body["settings_written"] == ["COUCHBASE_QUERY_URL", "COUCHBASE_USERNAME"]
    assert body["secret_presence"] == _presence(password=True)
    assert "Fill COUCHBASE_PASSWORD" in body["next_action"]
    assert "python -m local_guide" in body["next_action"]
    blob = json.dumps(body)
    assert SECRET not in blob
    config = (root / "config.json").read_text(encoding="utf-8")
    assert SECRET not in config
    assert "COUCHBASE" not in config
    state_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "state").rglob("*")
        if path.is_file()
    )
    assert SECRET not in state_text
    assert (tmp_path / "state" / "yelp-demo-build.md").is_file()


def test_yelp_couchbase_decline_and_userinfo_write_nothing(tmp_path, monkeypatch) -> None:
    from mcp_types import ElicitResult

    from zeus_dev_helper_mcp.server import create_mcp_server

    root = _prepare_yelp_tree(
        tmp_path,
        monkeypatch,
        env_text="KEEP=yes\n",
    )
    before = (root / ".env").read_text(encoding="utf-8")
    server = create_mcp_server(["core"])
    args = {"sample": "yelp-demo", "sample_dir": str(root)}
    first = _yelp_call(server, args)
    conn_key, _conn = _pending(first)
    second = _respond(server, args, first.request_state, {conn_key: _accept(_CONN)})
    cb_key, _card = _pending(second)
    declined = _respond(
        server,
        args,
        second.request_state,
        {conn_key: _accept(_CONN), cb_key: ElicitResult(action="decline")},
    )
    body = _structured(declined)
    assert body["ok"] is False
    assert body["written"] is False
    assert (root / ".env").read_text(encoding="utf-8") == before
    assert not (tmp_path / "state" / "yelp-demo-build.md").exists()

    bad = f"http://user:{SECRET}@127.0.0.1:8093"
    again = _yelp_call(server, args)
    conn_key, _conn = _pending(again)
    asked = _respond(server, args, again.request_state, {conn_key: _accept(_CONN)})
    cb_key, _card = _pending(asked)
    retry = _respond(
        server,
        args,
        asked.request_state,
        {
            conn_key: _accept(_CONN),
            cb_key: _accept(
                {
                    "couchbase_query_url": bad,
                    "couchbase_username": "Administrator",
                    "couchbase_password_in_env": False,
                }
            ),
        },
    )
    retry_key, retry_card = _pending(retry)
    assert "must not include a username or password" in retry_card.params.message
    assert bad not in retry_card.params.message
    assert SECRET not in retry_card.params.message
    stopped = _respond(
        server,
        args,
        retry.request_state,
        {
            conn_key: _accept(_CONN),
            retry_key: _accept(
                {
                    "couchbase_query_url": bad,
                    "couchbase_username": "Administrator",
                    "couchbase_password_in_env": False,
                }
            ),
        },
    )
    stopped_body = _structured(stopped)
    assert stopped_body["ok"] is False
    assert stopped_body["written"] is False
    assert bad not in json.dumps(stopped_body)
    assert SECRET not in json.dumps(stopped_body)
    assert (root / ".env").read_text(encoding="utf-8") == before
    state_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "state").rglob("*")
        if path.is_file()
    )
    assert SECRET not in state_text


def test_sealed_or_formless_yelp_skips_the_card_and_asks_text(
    tmp_path, monkeypatch
) -> None:
    from mcp_types import InputRequiredResult

    from zeus_dev_helper_mcp.config import reload_config
    from zeus_dev_helper_mcp.prereqs import save_prereqs
    from zeus_dev_helper_mcp.server import create_mcp_server

    root = _prepare_yelp_tree(tmp_path, monkeypatch, env_text=None)
    save_prereqs(reload_config(), {"zeus_url": "http://zeus-dev.local:8080"})
    (tmp_path / "state" / "yelp-demo-build.md").write_text(
        "# yelp-demo\n\nsealed\n", encoding="utf-8"
    )
    server = create_mcp_server(["core"])
    args = {"sample": "demo_yelp", "sample_dir": str(root)}
    sealed = _yelp_call(server, args)
    assert not isinstance(sealed, InputRequiredResult)
    body = _structured(sealed)
    envs = [row["env"] for row in body["ask_user"] if row.get("env")]
    assert "COUCHBASE_QUERY_URL" in envs
    assert "COUCHBASE_USERNAME" in envs
    assert "COUCHBASE_PASSWORD" not in envs
    assert "Write COUCHBASE_PASSWORD in the app .env" in body["next_action"]
    assert not (root / ".env").exists()

    (tmp_path / "plain").mkdir()
    plain = _prepare_yelp_tree(tmp_path / "plain", monkeypatch, env_text=None)
    server = create_mcp_server(["core"])
    result = _run(
        server.call_tool(
            "use_sample",
            {"sample": "yelpdemo", "sample_dir": str(plain)},
            context=_elicit_ctx(server, form=False),
        )
    )
    assert not isinstance(result, InputRequiredResult)
    asked = _structured(result)
    envs = [row["env"] for row in asked["ask_user"] if row.get("env")]
    assert envs[0] == "ZEUS_AUTH_MODE"
    assert "COUCHBASE_QUERY_URL" in envs
    assert "COUCHBASE_USERNAME" in envs
    assert envs[-1] == "LLM_API_KEY"
    assert "COUCHBASE_PASSWORD" not in envs
    assert "Write COUCHBASE_PASSWORD in the app .env" in asked["next_action"]
    assert not (plain / ".env").exists()
