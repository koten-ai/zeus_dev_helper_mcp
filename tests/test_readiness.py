"""Readiness unit tests (no live Zeus required)."""

from __future__ import annotations

from pathlib import Path

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.readiness import _looks_like_hub, run_readiness_check


def test_looks_like_hub() -> None:
    assert _looks_like_hub("http://localhost:9091")
    assert _looks_like_hub("http://host:9091/hub")
    assert not _looks_like_hub("http://localhost:8080")


def test_readiness_missing_url(tmp_path: Path) -> None:
    cfg = HelperConfig(zeus_url="", state_dir=tmp_path)
    out = run_readiness_check(cfg, update_checklist=False)
    assert out["overall"] == "fail"
    assert out["gates"][0]["id"] == "url_configured"
    assert out["gates"][0]["status"] == "fail"


def test_readiness_hub_port(tmp_path: Path) -> None:
    cfg = HelperConfig(zeus_url="http://127.0.0.1:9091", state_dir=tmp_path)
    out = run_readiness_check(cfg, update_checklist=False)
    ports = {g["id"]: g for g in out["gates"]}
    assert ports["public_port"]["status"] == "fail"
    assert ports["public_port"]["failure_class"] == "wrong_port_hub_vs_public"


def test_readiness_unreachable(tmp_path: Path) -> None:
    # High port unlikely to be Zeus
    cfg = HelperConfig(
        zeus_url="http://127.0.0.1:59999",
        state_dir=tmp_path,
        chat_request_dir=None,
    )
    out = run_readiness_check(cfg, update_checklist=False)
    assert out["overall"] == "fail"
    health = next(g for g in out["gates"] if g["id"] == "healthz")
    assert health["status"] == "fail"
    assert health.get("failure_class") == "network_timeout"
