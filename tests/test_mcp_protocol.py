"""Protocol tests for Helper 0.7: toolsets, annotations, resources, prompts, isError."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from zeus_dev_helper_mcp.envelope import (
    EXECUTION_FAIL_TOOLS,
    as_envelope,
    is_execution_failure,
)
from zeus_dev_helper_mcp.mcp_compat import ToolError
from zeus_dev_helper_mcp.server import create_mcp_server, mcp
from zeus_dev_helper_mcp.toolsets import (
    CORE_CAP,
    DEFAULT_CORE_TOOLS,
    default_core_count,
    parse_toolsets,
)


def _run(coro):
    return asyncio.run(coro)


def _tool_names(server) -> list[str]:
    tools = _run(server.list_tools())
    return sorted(t.name for t in tools)


def _ann(tool: Any) -> dict[str, Any]:
    raw = getattr(tool, "annotations", None)
    if raw is None:
        return {}
    if hasattr(raw, "model_dump"):
        return raw.model_dump(by_alias=True, exclude_none=False)
    if isinstance(raw, dict):
        return raw
    return {
        "readOnlyHint": getattr(raw, "readOnlyHint", None),
        "destructiveHint": getattr(raw, "destructiveHint", None),
        "idempotentHint": getattr(raw, "idempotentHint", None),
        "openWorldHint": getattr(raw, "openWorldHint", None),
    }


def test_default_core_count_within_cap() -> None:
    assert default_core_count() <= CORE_CAP
    assert default_core_count() == len(DEFAULT_CORE_TOOLS)
    names = _tool_names(create_mcp_server(["core"]))
    assert len(names) <= CORE_CAP
    assert set(names) == DEFAULT_CORE_TOOLS
    assert "explain_hash_boundary" not in names
    assert "detective_links" not in names
    assert "semantic_cache_status" not in names
    assert "get_checklist" not in names
    assert "suggest_demo_prompts" not in names
    assert "validate_env" not in names
    assert "lint_app" not in names


def test_module_server_uses_core_by_default() -> None:
    assert getattr(mcp, "name", None) in ("zeus-dev-helper", None)
    names = set(_tool_names(create_mcp_server(["core"])))
    assert names == DEFAULT_CORE_TOOLS


def test_stub_removed() -> None:
    import zeus_dev_helper_mcp.server as server_mod

    assert not hasattr(server_mod, "_stub")


def test_all_toolset_registers_hidden_tools() -> None:
    names = set(_tool_names(create_mcp_server(["all"])))
    assert "lint_app_code" in names
    assert "lint_app" in names
    assert "validate_env" in names
    assert "explain_verb" in names
    assert "travel_golden_path" in names
    assert "support_pack_from_turn" in names
    assert "handoff_to_multi" in names
    assert DEFAULT_CORE_TOOLS <= names
    assert len(names) >= 40


def test_every_default_tool_has_annotations() -> None:
    for tool in _run(create_mcp_server(["core"]).list_tools()):
        anns = _ann(tool)
        assert anns.get("readOnlyHint") is not None, tool.name
        # Non-readonly tools must not inherit the spec default destructive=true.
        if anns.get("readOnlyHint") is False:
            assert anns.get("destructiveHint") is not None, tool.name
        assert anns.get("openWorldHint") is not None, tool.name


def test_destructive_and_open_world_hints() -> None:
    by_name = {t.name: _ann(t) for t in _run(create_mcp_server(["core"]).list_tools())}
    assert by_name["start_project"]["destructiveHint"] is True
    assert by_name["scaffold_app"]["destructiveHint"] is True
    assert by_name["doctor"]["readOnlyHint"] is True
    assert by_name["next_step"]["readOnlyHint"] is True
    assert by_name["recommend_surface"]["readOnlyHint"] is True
    assert by_name["readiness_check"]["openWorldHint"] is True
    assert by_name["smoke_test_zeus"]["openWorldHint"] is True
    assert by_name["explain_scope"]["readOnlyHint"] is True
    assert by_name["explain_scope"]["openWorldHint"] is True
    assert by_name["website_green"]["readOnlyHint"] is False
    assert by_name["website_green"]["destructiveHint"] is False
    assert by_name["website_green"]["openWorldHint"] is True
    assert by_name["doctor"]["openWorldHint"] is False


def _resource_uris(server) -> set[str]:
    resources = _run(server.list_resources())
    uris = {str(getattr(r, "uri", r)) for r in resources}
    templates = _run(server.list_resource_templates())
    uris |= {
        str(getattr(t, "uriTemplate", getattr(t, "uri_template", t))) for t in templates
    }
    return uris


def test_resources_list_and_read(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    server = create_mcp_server(["core"])
    uris = _resource_uris(server)
    assert any("checklist" in u for u in uris)
    assert any("glossary" in u for u in uris)
    assert any("hash-boundary" in u for u in uris)
    assert any("req-id" in u for u in uris)
    assert any("catalog/modes" in u for u in uris)
    assert any("verbs" in u for u in uris)

    chunks = list(_run(server.read_resource("zeus-helper://checklist")))
    text = chunks[0].content if chunks else ""
    data = json.loads(text)
    assert "phases" in data

    page = list(_run(server.read_resource("zeus-helper://glossary/contract_hash")))
    topic = json.loads(page[0].content)
    assert topic.get("found") is True
    assert (
        "hash" in (topic.get("summary") or "").lower()
        or "fingerprint" in (topic.get("summary") or "").lower()
    )

    policy = list(_run(server.read_resource("zeus-helper://policy/hash-boundary")))
    body = json.loads(policy[0].content)
    assert body.get("ok") is True
    assert "do_not" in body

    req = list(_run(server.read_resource("zeus-helper://policy/req-id")))
    req_body = json.loads(req[0].content)
    assert req_body.get("ok") is True

    verb = list(_run(server.read_resource("zeus-helper://verbs/find")))
    verb_body = json.loads(verb[0].content)
    assert verb_body.get("ok") is True
    assert verb_body.get("name") == "find"


def test_prompts_list_and_get() -> None:
    server = create_mcp_server(["core"])
    prompts = {p.name for p in _run(server.list_prompts())}
    assert prompts >= {"first_green", "smoke_question", "support_pack"}
    assert "integrate_existing" not in prompts
    got = _run(server.get_prompt("first_green", {}))
    messages = getattr(got, "messages", None) or []
    text = json.dumps(got.model_dump() if hasattr(got, "model_dump") else str(got))
    assert "8080" in text or (messages and "8080" in str(messages))
    blob = text + str(messages)
    assert "beer-sample" in blob or "Application-user" in blob
    assert "use_sample(sample=beer)" in blob or "Direct/beer" in blob
    assert "set_prereq" in blob
    assert "Zeus source tree" in blob or "grep" in blob.lower()
    assert "has_llm_key=false" in blob or "has_llm_key" in blob
    assert "docs.koten.ai/zeus-client" in blob
    assert "placeholder while wiring" not in blob.lower()
    smoke = _run(
        server.get_prompt("smoke_question", {"question": "What entities exist?"})
    )
    smoke_text = json.dumps(
        smoke.model_dump() if hasattr(smoke, "model_dump") else str(smoke)
    )
    assert "entities" in smoke_text.lower() or "smoke_test_agent" in smoke_text


def test_bind_contract_execution_failure_is_error() -> None:
    server = create_mcp_server(["core"])
    with pytest.raises(Exception) as ei:
        _run(server.call_tool("bind_contract", {"json_text": "{}"}))
    err = ei.value
    message = str(err)
    assert "contract_hash_invent_forbidden" in message
    if ToolError is not None:
        assert isinstance(err, ToolError)


def test_readiness_check_missing_url_is_a_report(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("ZEUS_URL", raising=False)
    server = create_mcp_server(["core"])
    result = _run(server.call_tool("readiness_check", {"update_checklist": False}))
    structured = getattr(result, "structured_content", None) or getattr(
        result, "structuredContent", None
    )
    if structured is None and hasattr(result, "model_dump"):
        dumped = result.model_dump(by_alias=True)
        structured = dumped.get("structuredContent") or dumped.get("structured_content")
    assert isinstance(structured, dict)
    assert structured["ok"] is False
    assert structured.get("overall") == "fail" or structured.get("failure_class")
    assert getattr(result, "is_error", False) is False
    captured = capsys.readouterr()
    assert "zeus_dev_helper.tool.failed" not in captured.err
    assert "readiness_check" not in EXECUTION_FAIL_TOOLS


def test_envelope_keys_on_doctor() -> None:
    server = create_mcp_server(["core"])
    result = _run(server.call_tool("doctor", {}))
    structured = getattr(result, "structured_content", None) or getattr(
        result, "structuredContent", None
    )
    if structured is None and hasattr(result, "model_dump"):
        dumped = result.model_dump(by_alias=True)
        structured = dumped.get("structuredContent") or dumped.get("structured_content")
    assert isinstance(structured, dict)
    for key in ("ok", "failure_class", "next_action", "recommended_tools", "docs"):
        assert key in structured
    assert structured["ok"] is True
    assert getattr(result, "is_error", False) is False


def test_parse_toolsets_always_includes_core(monkeypatch) -> None:
    monkeypatch.delenv("ZEUS_DEV_HELPER_TOOLSETS", raising=False)
    assert parse_toolsets() == frozenset({"core"})
    assert "core" in parse_toolsets("lint")
    assert parse_toolsets("all") >= frozenset(
        {"core", "lint", "catalog", "travel", "support", "handoff"}
    )


def test_next_step_includes_resource_links(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    from zeus_dev_helper_mcp.config import HelperConfig
    from zeus_dev_helper_mcp.walkthrough import enriched_next_step

    out = enriched_next_step(HelperConfig(state_dir=tmp_path / "state"))
    uris = {link["uri"] for link in out.get("resource_links") or []}
    assert "zeus-helper://checklist" in uris
    assert all(link.get("type") == "resource_link" for link in out["resource_links"])


def test_doctor_detail_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("ZEUS_URL", raising=False)
    from zeus_dev_helper_mcp.server import doctor

    health = doctor("health")
    assert health["ok"] is True
    assert health["detail"] == "health"
    env = doctor("env")
    assert env["detail"] == "env"
    assert "issues" in env
    unknown = doctor("nope")
    assert unknown["ok"] is False
    assert "health" in unknown["known_details"]


def test_execution_failure_helper() -> None:
    assert "bind_contract" in EXECUTION_FAIL_TOOLS
    payload = as_envelope(
        {"ok": False, "failure_class": "contract_hash_invent_forbidden"}
    )
    assert is_execution_failure("bind_contract", payload)
    assert not is_execution_failure("diagnose_error", payload)


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


def test_start_project_schema_hides_clarification_and_secrets() -> None:
    tools = _run(create_mcp_server(["core"]).list_tools())
    tool = next(item for item in tools if item.name == "start_project")
    props = set((tool.input_schema or {}).get("properties") or {})
    assert "clarification" not in props
    assert "password" not in props
    assert "username" not in props
    assert "token" not in props
    blob = json.dumps(tool.input_schema).lower()
    assert "password" not in blob
    assert "zeus_username" not in blob


def test_start_project_asks_for_zeus_url(tmp_path, monkeypatch) -> None:
    from mcp_types import InputRequiredResult

    _isolate_prereqs(tmp_path, monkeypatch)
    server = create_mcp_server(["core"])
    result = _run(
        server.call_tool(
            "start_project", {"sample": "beer"}, context=_elicit_ctx(server, form=True)
        )
    )
    assert isinstance(result, InputRequiredResult)
    request = next(iter((result.input_requests or {}).values()))
    message = request.params.message
    assert "Zeus URL" in message
    assert "8080" in message
    schema = request.params.requested_schema
    assert set(schema["properties"]) == {"zeus_url"}
    assert set(schema) <= {"$schema", "type", "properties", "required"}
    assert "title" not in schema
    assert not (tmp_path / "demo_beer_sample").exists()
    from zeus_dev_helper_mcp.config import reload_config
    from zeus_dev_helper_mcp.prereqs import load_prereqs

    assert "zeus_url" not in load_prereqs(reload_config())


def test_accepted_url_is_stored_and_not_asked_again(tmp_path, monkeypatch) -> None:
    from mcp_types import ElicitResult, InputRequiredResult, InputResponseRequestParams

    from zeus_dev_helper_mcp.config import reload_config
    from zeus_dev_helper_mcp.prereqs import load_prereqs

    _isolate_prereqs(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.clarify.probe_auth_required",
        lambda *args, **kwargs: "open",
    )
    server = create_mcp_server(["core"])
    first = _run(
        server.call_tool(
            "start_project", {"sample": "beer"}, context=_elicit_ctx(server, form=True)
        )
    )
    assert isinstance(first, InputRequiredResult)
    key = next(iter(first.input_requests or {}))
    accepted = InputResponseRequestParams(
        input_responses={
            key: ElicitResult(
                action="accept", content={"zeus_url": "http://192.168.0.219:8080"}
            )
        },
        request_state=first.request_state,
    )
    second = _run(
        server.call_tool(
            "start_project",
            {"sample": "beer"},
            context=_elicit_ctx(server, form=True, params=accepted),
        )
    )
    assert not isinstance(second, InputRequiredResult)
    body = _structured(second)
    assert body["started"] is True
    assert load_prereqs(reload_config()).get("zeus_url") == "http://192.168.0.219:8080"
    third = _run(
        server.call_tool(
            "start_project", {"sample": "beer"}, context=_elicit_ctx(server, form=True)
        )
    )
    assert not isinstance(third, InputRequiredResult)
    assert _structured(third)["started"] is True


def test_declined_url_does_not_start(tmp_path, monkeypatch) -> None:
    from mcp_types import ElicitResult, InputRequiredResult, InputResponseRequestParams

    from zeus_dev_helper_mcp.config import reload_config
    from zeus_dev_helper_mcp.prereqs import load_prereqs

    _isolate_prereqs(tmp_path, monkeypatch)
    server = create_mcp_server(["core"])
    first = _run(
        server.call_tool(
            "start_project", {"sample": "beer"}, context=_elicit_ctx(server, form=True)
        )
    )
    assert isinstance(first, InputRequiredResult)
    key = next(iter(first.input_requests or {}))
    declined = InputResponseRequestParams(
        input_responses={key: ElicitResult(action="decline")},
        request_state=first.request_state,
    )
    result = _run(
        server.call_tool(
            "start_project",
            {"sample": "beer"},
            context=_elicit_ctx(server, form=True, params=declined),
        )
    )
    body = _structured(result)
    assert body["ok"] is False
    assert body["started"] is False
    assert getattr(result, "is_error", False) is False
    assert "zeus_url" not in load_prereqs(reload_config())
    assert not (tmp_path / "demo_beer_sample").exists()


def test_missing_elicitation_capability_returns_coach_text(
    tmp_path, monkeypatch
) -> None:
    _isolate_prereqs(tmp_path, monkeypatch)
    server = create_mcp_server(["core"])
    result = _run(
        server.call_tool(
            "start_project", {"sample": "beer"}, context=_elicit_ctx(server, form=False)
        )
    )
    body = _structured(result)
    assert body["ok"] is False
    assert body["started"] is False
    assert "8080" in (body.get("next_action") or "")
    assert getattr(result, "is_error", False) is False


def test_auth_form_blocks_start_project_until_env_has_credentials(
    tmp_path, monkeypatch
) -> None:
    from mcp_types import ElicitResult, InputRequiredResult, InputResponseRequestParams

    from zeus_dev_helper_mcp.config import reload_config
    from zeus_dev_helper_mcp.prereqs import load_prereqs

    _isolate_prereqs(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.clarify.probe_auth_required",
        lambda *args, **kwargs: "unauthorized",
    )
    server = create_mcp_server(["core"])
    args = {"sample": "beer"}
    first = _run(
        server.call_tool("start_project", args, context=_elicit_ctx(server, form=True))
    )
    assert isinstance(first, InputRequiredResult)
    url_key = next(iter(first.input_requests or {}))
    url_answer = InputResponseRequestParams(
        input_responses={
            url_key: ElicitResult(
                action="accept", content={"zeus_url": "http://192.168.0.219:8080"}
            )
        },
        request_state=first.request_state,
    )
    second = _run(
        server.call_tool(
            "start_project",
            args,
            context=_elicit_ctx(server, form=True, params=url_answer),
        )
    )
    assert isinstance(second, InputRequiredResult)
    auth_key = next(iter(second.input_requests or {}))
    auth_request = second.input_requests[auth_key]
    auth_schema = auth_request.params.requested_schema
    assert set(auth_schema) <= {"$schema", "type", "properties", "required"}
    assert "title" not in auth_schema
    props = auth_schema["properties"]
    assert set(props) == {"auth_mode", "credentials_ready"}
    assert "password" not in props
    assert "username" not in props
    assert "token" not in props
    ready = InputResponseRequestParams(
        input_responses={
            url_key: ElicitResult(
                action="accept", content={"zeus_url": "http://192.168.0.219:8080"}
            ),
            auth_key: ElicitResult(
                action="accept",
                content={"auth_mode": "basic", "credentials_ready": True},
            ),
        },
        request_state=second.request_state,
    )
    result = _run(
        server.call_tool(
            "start_project", args, context=_elicit_ctx(server, form=True, params=ready)
        )
    )
    body = _structured(result)
    assert body["ok"] is False
    assert body["started"] is False
    stored = load_prereqs(reload_config())
    assert stored.get("has_password") is not True
    assert not (tmp_path / "demo_beer_sample").exists()


def _closed_port() -> str:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return str(sock.getsockname()[1])


def _env_values(path: Any) -> dict[str, str]:
    from zeus_dev_helper_mcp.llm_key import _dotenv_values

    return _dotenv_values(path)


def _prepare_beer_tree(tmp_path: Any, monkeypatch: Any) -> Any:
    """Existing beer checkout with a username, password, and model. No creation log."""
    from zeus_dev_helper_mcp.beer import write_beer_sample
    from zeus_dev_helper_mcp.config import HelperConfig, reload_config
    from zeus_dev_helper_mcp.prereqs import save_prereqs

    _isolate_prereqs(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.clarify.probe_auth_required",
        lambda *args, **kwargs: "open",
    )
    state = tmp_path / "state"
    cfg = HelperConfig(
        state_dir=state,
        zeus_url="http://zeus-dev.local:8080",
        default_bucket="beer-sample",
        default_scope="_default",
    )
    root = tmp_path / "demo_beer_sample"
    assert write_beer_sample(cfg, root)["ok"] is True
    env = root / ".env"
    env.write_text(
        "\n".join(
            [
                "ZEUS_USERNAME=pour-user",
                "ZEUS_PASSWORD=keep-password",
                "LLM_API_KEY=keep-llm-key",
                "LLM_BASE_URL=https://api.x.ai/v1",
                "LLM_MODEL=grok-custom-model",
                f"PORT={_closed_port()}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    env.chmod(0o600)
    save_prereqs(reload_config(), {"zeus_url": "http://zeus-dev.local:8080"})
    return root


def _accept(content: dict[str, Any]) -> Any:
    from mcp_types import ElicitResult

    return ElicitResult(action="accept", content=content)


def test_first_beer_create_asks_connection_then_llm(tmp_path, monkeypatch) -> None:
    from mcp_types import InputRequiredResult, InputResponseRequestParams

    from zeus_dev_helper_mcp.server import use_sample_impl

    root = _prepare_beer_tree(tmp_path, monkeypatch)
    calls = {"n": 0}
    real = use_sample_impl

    def _count(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr("zeus_dev_helper_mcp.server.use_sample_impl", _count)
    server = create_mcp_server(["core"])
    args = {"sample": "beer", "sample_dir": str(root)}
    first = _run(
        server.call_tool("use_sample", args, context=_elicit_ctx(server, form=True))
    )
    assert isinstance(first, InputRequiredResult)
    assert calls["n"] == 0
    conn_key = next(iter(first.input_requests or {}))
    request = first.input_requests[conn_key]
    schema = request.params.requested_schema
    assert set(schema) <= {"$schema", "type", "properties", "required"}
    assert "title" not in schema
    props = schema["properties"]
    assert set(props) == {"zeus_url", "zeus_username", "password_in_env"}
    assert "zeus_password" not in props
    assert "llm_api_key" not in props
    assert "token" not in props
    assert "password" not in props
    assert props["zeus_url"]["default"] == "http://zeus-dev.local:8080"
    assert props["zeus_username"]["default"] == "pour-user"
    assert props["password_in_env"]["default"] is True
    assert str(root / ".env") in request.params.message
    assert "ZEUS_PASSWORD" in request.params.message
    conn = InputResponseRequestParams(
        input_responses={
            conn_key: _accept(
                {
                    "zeus_url": "http://192.168.0.219:8080",
                    "zeus_username": "edited-user",
                    "password_in_env": True,
                }
            )
        },
        request_state=first.request_state,
    )
    second = _run(
        server.call_tool(
            "use_sample", args, context=_elicit_ctx(server, form=True, params=conn)
        )
    )
    assert isinstance(second, InputRequiredResult)
    assert calls["n"] == 0
    llm_key = next(iter(second.input_requests or {}))
    llm_schema = second.input_requests[llm_key].params.requested_schema
    assert set(llm_schema) <= {"$schema", "type", "properties", "required"}
    assert "title" not in llm_schema
    llm_props = llm_schema["properties"]
    assert set(llm_props) == {"llm_provider", "llm_model", "llm_key_in_env"}
    assert llm_props["llm_model"]["default"] == "grok-custom-model"
    assert llm_props["llm_provider"]["default"] == "grok"
    assert llm_props["llm_key_in_env"]["default"] is True
    assert "LLM_API_KEY" in second.input_requests[llm_key].params.message
    kept = _env_values(root / ".env")
    assert kept["ZEUS_PASSWORD"] == "keep-password"
    assert kept["LLM_API_KEY"] == "keep-llm-key"
    assert "ZEUS_URL" not in kept
    ready = InputResponseRequestParams(
        input_responses={
            conn_key: _accept(
                {
                    "zeus_url": "http://192.168.0.219:8080",
                    "zeus_username": "edited-user",
                    "password_in_env": True,
                }
            ),
            llm_key: _accept(
                {
                    "llm_provider": "grok",
                    "llm_model": "grok-custom-model",
                    "llm_key_in_env": True,
                }
            ),
        },
        request_state=second.request_state,
    )
    result = _run(
        server.call_tool(
            "use_sample", args, context=_elicit_ctx(server, form=True, params=ready)
        )
    )
    assert not isinstance(result, InputRequiredResult)
    body = _structured(result)
    assert body["ok"] is True
    assert calls["n"] == 1
    assert "ask_user" not in body
    written = _env_values(root / ".env")
    assert written["ZEUS_URL"] == "http://192.168.0.219:8080"
    assert written["ZEUS_USERNAME"] == "edited-user"
    assert written["ZEUS_PASSWORD"] == "keep-password"
    assert written["LLM_API_KEY"] == "keep-llm-key"
    assert written["LLM_MODEL"] == "grok-custom-model"
    assert written["LLM_BASE_URL"] == "https://api.x.ai/v1"
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    assert config["llm"]["api_key_env"] == "LLM_API_KEY"
    assert (tmp_path / "state" / "beer-sample-build.md").is_file()
    again = _run(
        server.call_tool("use_sample", args, context=_elicit_ctx(server, form=True))
    )
    assert not isinstance(again, InputRequiredResult)


def test_sealed_beer_log_does_not_open_setup_cards(tmp_path, monkeypatch) -> None:
    from mcp_types import InputRequiredResult

    root = _prepare_beer_tree(tmp_path, monkeypatch)
    (tmp_path / "state" / "beer-sample-build.md").write_text(
        "# beer-sample\n\nsealed\n", encoding="utf-8"
    )

    def _impl(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"ok": True, "written": False, "local_dir": str(root)}

    monkeypatch.setattr("zeus_dev_helper_mcp.server.use_sample_impl", _impl)
    server = create_mcp_server(["core"])
    result = _run(
        server.call_tool(
            "use_sample",
            {"sample": "beer", "sample_dir": str(root)},
            context=_elicit_ctx(server, form=True),
        )
    )
    assert not isinstance(result, InputRequiredResult)
    body = _structured(result)
    assert body["ok"] is True


def test_beer_create_without_elicitation_keeps_ask_user(tmp_path, monkeypatch) -> None:
    root = _prepare_beer_tree(tmp_path, monkeypatch)
    server = create_mcp_server(["core"])
    result = _run(
        server.call_tool(
            "use_sample",
            {"sample": "beer", "sample_dir": str(root)},
            context=_elicit_ctx(server, form=False),
        )
    )
    body = _structured(result)
    assert body["ok"] is True
    assert isinstance(body.get("ask_user"), list)
    assert body.get("sample_build_form") is True
    assert "ask_user" in (body.get("next_action") or "")
    blob = json.dumps(body)
    assert "keep-password" not in blob
    assert "keep-llm-key" not in blob


def test_api_scaffold_asks_the_same_connection_card(tmp_path, monkeypatch) -> None:
    from mcp_types import InputRequiredResult

    _isolate_prereqs(tmp_path, monkeypatch)
    server = create_mcp_server(["core"])
    target = tmp_path / "zeus_first_api"
    first = _run(
        server.call_tool(
            "scaffold_app",
            {"target_dir": str(target), "app_kind": "api"},
            context=_elicit_ctx(server, form=True),
        )
    )
    assert isinstance(first, InputRequiredResult)
    request = next(iter((first.input_requests or {}).values()))
    assert set(request.params.requested_schema["properties"]) == {
        "zeus_url",
        "zeus_username",
        "password_in_env",
    }
    assert not target.exists()
    cli = _run(
        server.call_tool(
            "scaffold_app",
            {"target_dir": str(tmp_path / "cli-app"), "app_kind": "cli"},
            context=_elicit_ctx(server, form=True),
        )
    )
    assert isinstance(cli, InputRequiredResult)
    cli_request = next(iter((cli.input_requests or {}).values()))
    assert set(cli_request.params.requested_schema["properties"]) == {"zeus_url"}


def test_declined_connection_card_does_not_create(tmp_path, monkeypatch) -> None:
    from mcp_types import ElicitResult, InputRequiredResult, InputResponseRequestParams

    root = _prepare_beer_tree(tmp_path, monkeypatch)
    before = (root / ".env").read_text(encoding="utf-8")

    def _forbid(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("use_sample_impl called")

    monkeypatch.setattr("zeus_dev_helper_mcp.server.use_sample_impl", _forbid)
    server = create_mcp_server(["core"])
    args = {"sample": "beer", "sample_dir": str(root)}
    first = _run(
        server.call_tool("use_sample", args, context=_elicit_ctx(server, form=True))
    )
    assert isinstance(first, InputRequiredResult)
    key = next(iter(first.input_requests or {}))
    declined = InputResponseRequestParams(
        input_responses={key: ElicitResult(action="decline")},
        request_state=first.request_state,
    )
    result = _run(
        server.call_tool(
            "use_sample", args, context=_elicit_ctx(server, form=True, params=declined)
        )
    )
    body = _structured(result)
    assert body["ok"] is False
    assert body["written"] is False
    assert (root / ".env").read_text(encoding="utf-8") == before
    assert not (tmp_path / "state" / "beer-sample-build.md").exists()


_CB_SECRET = "cb-secret-sentinel"
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
    from zeus_dev_helper_mcp.yelp import apply_couchbase_env

    root = _prepare_yelp_tree(
        tmp_path,
        monkeypatch,
        env_text=(
            "ZEUS_USERNAME=pour-user\n"
            "COUCHBASE_QUERY_URL=http://cb.example:8093\n"
            "COUCHBASE_USERNAME=from-file\n"
            f'export COUCHBASE_PASSWORD="{_CB_SECRET}"\n'
        ),
    )
    seen: dict[str, Any] = {}
    real = apply_couchbase_env

    def _spy(payload: dict[str, Any], gate: Any) -> dict[str, Any]:
        seen["url"] = gate.couchbase_query_url
        seen["user"] = gate.couchbase_username
        seen["flag"] = gate.couchbase_password_in_env
        assert _CB_SECRET not in repr(gate)
        return real(payload, gate)

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
    assert _CB_SECRET not in card.params.message
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
    assert f'export COUCHBASE_PASSWORD="{_CB_SECRET}"' in env_text
    assert body["settings_written"] == ["COUCHBASE_QUERY_URL", "COUCHBASE_USERNAME"]
    assert body["secret_presence"] == {"COUCHBASE_PASSWORD": True}
    assert "Fill COUCHBASE_PASSWORD" in body["next_action"]
    assert "python -m local_guide" in body["next_action"]
    blob = json.dumps(body)
    assert _CB_SECRET not in blob
    config = (root / "config.json").read_text(encoding="utf-8")
    assert _CB_SECRET not in config
    assert "COUCHBASE" not in config
    state_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "state").rglob("*")
        if path.is_file()
    )
    assert _CB_SECRET not in state_text
    assert (tmp_path / "state" / "yelp-demo-build.md").is_file()


def test_yelp_couchbase_decline_and_userinfo_write_nothing(tmp_path, monkeypatch) -> None:
    from mcp_types import ElicitResult

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

    bad = f"http://user:{_CB_SECRET}@127.0.0.1:8093"
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
    assert _CB_SECRET not in retry_card.params.message
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
    assert _CB_SECRET not in json.dumps(stopped_body)
    assert (root / ".env").read_text(encoding="utf-8") == before
    state_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "state").rglob("*")
        if path.is_file()
    )
    assert _CB_SECRET not in state_text


def test_sealed_or_formless_yelp_skips_the_card_and_asks_text(
    tmp_path, monkeypatch
) -> None:
    from mcp_types import InputRequiredResult

    from zeus_dev_helper_mcp.config import reload_config
    from zeus_dev_helper_mcp.prereqs import save_prereqs

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

