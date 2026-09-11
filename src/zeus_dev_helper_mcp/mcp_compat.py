"""mcp 1.x / 2.x import and registration helpers (ZDH-34 / ZDH-37)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ModuleNotFoundError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP  # type: ignore[no-redef]


def _load_symbol(paths: tuple[str, ...], name: str) -> Any | None:
    for path in paths:
        try:
            module = __import__(path, fromlist=[name])
        except ImportError:
            continue
        obj = getattr(module, name, None)
        if obj is not None:
            return obj
    return None


ToolAnnotations = _load_symbol(("mcp_types", "mcp.types"), "ToolAnnotations")
ToolError = _load_symbol(
    (
        "mcp.server.mcpserver.exceptions",
        "mcp.server.fastmcp.exceptions",
    ),
    "ToolError",
)


def make_fastmcp(*, name: str, instructions: str, version: str = "") -> Any:
    try:
        return FastMCP(name, instructions=instructions, version=version)
    except TypeError:
        return FastMCP(name, instructions=instructions)


def make_tool_annotations(
    *,
    read_only: bool,
    destructive: bool,
    idempotent: bool,
    open_world: bool,
    title: str | None = None,
) -> Any:
    payload: dict[str, Any] = {
        "readOnlyHint": read_only,
        "destructiveHint": destructive,
        "idempotentHint": idempotent,
        "openWorldHint": open_world,
    }
    if title:
        payload["title"] = title
    if ToolAnnotations is None:
        return payload
    try:
        return ToolAnnotations(**payload)
    except TypeError:
        return payload


def register_tool(mcp: Any, fn: Callable[..., Any], *, annotations: Any = None) -> None:
    kwargs: dict[str, Any] = {}
    if annotations is not None:
        kwargs["annotations"] = annotations
    try:
        mcp.tool(**kwargs)(fn)
    except TypeError:
        kwargs.pop("annotations", None)
        mcp.tool(**kwargs)(fn)


def register_resource(
    mcp: Any,
    uri: str,
    fn: Callable[..., Any],
    *,
    name: str | None = None,
    description: str | None = None,
    mime_type: str = "application/json",
) -> None:
    kwargs: dict[str, Any] = {"mime_type": mime_type}
    if name:
        kwargs["name"] = name
    if description:
        kwargs["description"] = description
    try:
        mcp.resource(uri, **kwargs)(fn)
    except TypeError:
        kwargs.pop("mime_type", None)
        mcp.resource(uri, **kwargs)(fn)


def register_prompt(
    mcp: Any,
    fn: Callable[..., Any],
    *,
    name: str | None = None,
    description: str | None = None,
) -> None:
    kwargs: dict[str, Any] = {}
    if name:
        kwargs["name"] = name
    if description:
        kwargs["description"] = description
    try:
        mcp.prompt(**kwargs)(fn)
    except TypeError:
        mcp.prompt()(fn)
