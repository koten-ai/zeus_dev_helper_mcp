"""Catalog fetch against local zeus_chat_request checkout."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from zeus_dev_helper_mcp.catalog import CatalogError, fetch_chat_request, list_modes
from zeus_dev_helper_mcp.config import HelperConfig

# tests/ → package root → parent folder with sibling repos
SIBLING = Path(__file__).resolve().parents[1].parent / "zeus_chat_request"


@pytest.fixture
def local_cfg(tmp_path: Path) -> HelperConfig:
    if not (SIBLING / "manifest.json").is_file():
        pytest.skip("zeus_chat_request not checked out as sibling")
    return HelperConfig(
        chat_request_dir=SIBLING,
        state_dir=tmp_path / "state",
    )


def test_list_modes(local_cfg: HelperConfig) -> None:
    out = list_modes(local_cfg)
    assert out["profile"] == "v2_min"
    modes = {m["mode"] for m in out["modes"]}
    assert "analytics" in modes
    assert "TEMPLATE ONLY" in out["warning"]


def test_fetch_summary(local_cfg: HelperConfig) -> None:
    out = fetch_chat_request(local_cfg, "analytics", detail="summary")
    assert out["mode"] == "analytics"
    assert out["verb_count"] >= 1
    assert "chat_request" not in out
    assert "TEMPLATE ONLY" in out["warning"]


def test_fetch_full(local_cfg: HelperConfig) -> None:
    out = fetch_chat_request(local_cfg, "analytics", detail="full")
    assert out["chat_request"]["_format"] == "zeus.chat_request.v2"
    assert isinstance(out["chat_request"].get("verbs"), list)


def test_unknown_mode(local_cfg: HelperConfig) -> None:
    with pytest.raises(CatalogError):
        fetch_chat_request(local_cfg, "nope-mode")
