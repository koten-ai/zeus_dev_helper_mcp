"""Regression: server module must import on mcp 1.x (FastMCP) and 2.x (MCPServer)."""

from zeus_dev_helper_mcp.server import main, mcp


def test_server_module_imports() -> None:
    assert callable(main)
    assert mcp is not None
    name = getattr(mcp, "name", None)
    if name is not None:
        assert name == "zeus-dev-helper"
