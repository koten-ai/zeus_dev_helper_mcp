"""Published docs URL mapping (ZDM-10). Offline — no network."""

from __future__ import annotations

import pytest

from zeus_dev_helper_mcp.docs_links import DEFAULT_DOCS_BASE, ZEUS_CLIENT_HUB, docs_url


def test_docs_url_maps_zeus_client_hub_and_pages() -> None:
    assert docs_url("zeus-client") == f"{DEFAULT_DOCS_BASE}/zeus-client"
    assert ZEUS_CLIENT_HUB == f"{DEFAULT_DOCS_BASE}/zeus-client"
    assert docs_url("zeus-client/for-ai-agents.md") == (
        f"{DEFAULT_DOCS_BASE}/zeus-client/for-ai-agents"
    )
    assert docs_url("zeus-client/dev-helper-mcp.md") == (
        f"{DEFAULT_DOCS_BASE}/zeus-client/dev-helper-mcp"
    )
    assert docs_url("zeus-client/errors.md") == f"{DEFAULT_DOCS_BASE}/zeus-client/errors"
    assert docs_url("zeus-client/start.md") == f"{DEFAULT_DOCS_BASE}/zeus-client/start"
    assert docs_url("zeus-client/using-zeus-client.md") == (
        f"{DEFAULT_DOCS_BASE}/zeus-client/using-zeus-client"
    )
    assert docs_url("zeus-client/errors.md#err-409-drift") == (
        f"{DEFAULT_DOCS_BASE}/zeus-client/errors#err-409-drift"
    )


def test_docs_url_yaml_stays_on_github_source() -> None:
    url = docs_url("agent-index.yaml")
    assert url.startswith("https://github.com/koten-ai/koten_docs/blob/")
    assert url.endswith("/agent-index.yaml")
    assert "docs.koten.ai" not in url


def test_docs_url_honors_base_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KOTEN_DOCS_BASE_URL", "https://docs.example.test")
    assert docs_url("zeus-client/for-ai-agents.md") == (
        "https://docs.example.test/zeus-client/for-ai-agents"
    )
