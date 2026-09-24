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


def test_readiness_check_missing_url_is_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("ZEUS_URL", raising=False)
    server = create_mcp_server(["core"])
    with pytest.raises(Exception) as ei:
        _run(server.call_tool("readiness_check", {"update_checklist": False}))
    assert "overall" in str(ei.value) or "ZEUS_URL" in str(ei.value)


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
    assert set(request.params.requested_schema["properties"]) == {"zeus_url"}
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


def test_auth_form_blocks_use_sample_until_env_has_credentials(
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

    def _forbid_write(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("use_sample_impl called")

    monkeypatch.setattr("zeus_dev_helper_mcp.server.use_sample_impl", _forbid_write)
    server = create_mcp_server(["core"])
    args = {
        "sample": "beer",
        "parent_dir": str(tmp_path),
        "project_name": "demo_beer_sample",
    }
    first = _run(
        server.call_tool("use_sample", args, context=_elicit_ctx(server, form=True))
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
            "use_sample",
            args,
            context=_elicit_ctx(server, form=True, params=url_answer),
        )
    )
    assert isinstance(second, InputRequiredResult)
    auth_key = next(iter(second.input_requests or {}))
    auth_request = second.input_requests[auth_key]
    props = auth_request.params.requested_schema["properties"]
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
            "use_sample", args, context=_elicit_ctx(server, form=True, params=ready)
        )
    )
    body = _structured(result)
    assert body["ok"] is False
    assert body["written"] is False
    stored = load_prereqs(reload_config())
    assert stored.get("has_password") is not True
    assert not (tmp_path / "demo_beer_sample").exists()
