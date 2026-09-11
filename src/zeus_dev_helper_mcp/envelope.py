"""Shared tool result envelope + execution-failure mapping (ZDH-34).

MCP 2.x `ToolError` is the SDK equivalent of `CallToolResult(isError=true)`:
the protocol handler catches it and returns `isError: true` with the message
in `content`. Tools that complete and report a domain status (lint findings,
blocked multi-agent start) keep `ok=false` without raising.
"""

from __future__ import annotations

import json
from typing import Any

from zeus_dev_helper_mcp.mcp_compat import ToolError

ENVELOPE_KEYS = ("ok", "failure_class", "next_action", "recommended_tools", "docs")

# Tools whose unsuccessful result is an execution failure the model should correct.
EXECUTION_FAIL_TOOLS = frozenset(
    {
        "readiness_check",
        "bind_contract",
        "list_catalog_modes",
        "fetch_chat_request",
        "scaffold_app",
        "smoke_test_zeus",
        "smoke_test_agent",
    }
)


def as_envelope(data: dict[str, Any]) -> dict[str, Any]:
    """Ensure the shared 0.7 envelope keys exist without dropping domain fields."""
    out = dict(data)
    if "ok" not in out:
        if out.get("error") or out.get("overall") == "fail" or out.get("blocked"):
            out["ok"] = False
        elif out.get("overall") == "pass":
            out["ok"] = True
        else:
            out["ok"] = True
    if "failure_class" not in out:
        out["failure_class"] = out.get("primary_failure_class")
    out.setdefault("next_action", None)
    if not isinstance(out.get("recommended_tools"), list):
        out["recommended_tools"] = list(out.get("recommended_tools") or [])
    if "docs" not in out:
        out["docs"] = {}
    return out


def is_execution_failure(tool_name: str, payload: dict[str, Any]) -> bool:
    if tool_name not in EXECUTION_FAIL_TOOLS:
        return False
    if payload.get("ok") is False:
        return True
    if payload.get("error") and payload.get("ok") is not True:
        return True
    return tool_name == "readiness_check" and payload.get("overall") == "fail"


def raise_tool_error(payload: dict[str, Any]) -> None:
    """Raise so the MCP handler sets isError (or the documented SDK equivalent)."""
    body = as_envelope(payload)
    message = json.dumps(body, indent=2, default=str)
    if ToolError is not None:
        raise ToolError(message)
    raise RuntimeError(message)
