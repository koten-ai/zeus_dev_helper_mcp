"""Tests for ZDH-10/11/12/13: travel, multi handoff, data-plane, glossary."""

from __future__ import annotations

from pathlib import Path

from zeus_dev_helper_mcp.checklist import load_checklist, save_checklist, set_item_status
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.explain import TOPICS, explain_topic
from zeus_dev_helper_mcp.handoff import (
    emit_mcp_config,
    handoff_to_multi,
    metrics_summary,
    recommend_data_plane_mcp,
    record_metric,
)
from zeus_dev_helper_mcp.scaffold import use_sample
from zeus_dev_helper_mcp.travel import travel_golden_path, validate_travel_layout
from zeus_dev_helper_mcp.walkthrough import enriched_next_step


def _cfg(tmp_path: Path) -> HelperConfig:
    return HelperConfig(
        zeus_url="http://localhost:8080",
        default_bucket="travel-sample",
        default_scope="inventory",
        state_dir=tmp_path / "state",
    )


def test_explain_has_min_topics() -> None:
    # ZDH-13: curated snapshot of koten_docs glossary (≥12 topics)
    assert len(TOPICS) >= 12
    for key in (
        "zeus",
        "zeus_client",
        "contract",
        "contract_hash",
        "middleman",
        "scope",
        "hub",
        "public_api",
        "chat_request",
        "single_agent",
        "multi_agent",
        "session",
    ):
        assert key in TOPICS


def test_explain_found_and_alias(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    out = explain_topic(cfg, "contract_hash")
    assert out["found"] is True
    assert "hash" in out["summary"].lower() or "fingerprint" in out["summary"].lower()
    assert "doc_url" in out

    alias = explain_topic(cfg, "middle-man")
    assert alias["found"] is True
    assert alias["topic"] == "middleman"

    miss = explain_topic(cfg, "not_a_real_topic_xyz")
    assert miss["found"] is False
    assert "known_topics" in miss


def test_travel_layout_soft(tmp_path: Path) -> None:
    root = tmp_path / "demo_travel_sample"
    root.mkdir()
    (root / "README.md").write_text("# travel\n")
    (root / "requirements.txt").write_text("httpx\n")
    layout = validate_travel_layout(root)
    assert layout["ok"] is True

    cfg = _cfg(tmp_path)
    # ensure checklist exists
    load_checklist(cfg)
    out = travel_golden_path(cfg, sample_dir=str(root))
    assert out["ok"] is True
    assert out["local_dir"] == str(root)
    assert out["layout"]["ok"] is True
    assert "sample_readme_snippet" in out
    assert "Developer Helper MCP" in out["sample_readme_snippet"]


def test_use_sample_includes_golden_path(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    load_checklist(cfg)
    out = use_sample(cfg, "travel")
    assert out["ok"] is True
    assert "golden_path" in out
    assert out["sample"]["name"] == "demo_travel_sample"


def test_handoff_blocks_until_green(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    load_checklist(cfg)
    blocked = handoff_to_multi(cfg, force=False)
    assert blocked["blocked"] is True
    assert blocked["ok"] is False

    forced = handoff_to_multi(cfg, force=True)
    assert forced["ok"] is True
    assert forced.get("forced") is True
    assert "three_tier" in forced["concept"]


def test_handoff_opens_after_smokes(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    load_checklist(cfg)
    set_item_status(cfg, "5.1", "done", evidence="test")
    set_item_status(cfg, "5.2", "done", evidence="test")
    out = handoff_to_multi(cfg, force=False)
    assert out["ok"] is True
    assert out["blocked"] is False


def test_data_plane_emit_scope_bound(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    rec = recommend_data_plane_mcp(cfg)
    assert rec["helper_role"].startswith("onboarding")
    assert "use_data_plane_for" in rec["boundary"]

    frag = emit_mcp_config(cfg, server_name="dp-test", read_only=True)
    assert frag["read_only"] is True
    assert "travel-sample/inventory" in frag["scope_allowlist"]
    servers = frag["claude_desktop_fragment"]["mcpServers"]["dp-test"]
    assert servers["env"]["DATA_PLANE_READ_ONLY"] == "true"
    assert "PLACEHOLDER" in frag["note"]


def test_metrics_time_to_green(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    empty = metrics_summary(cfg)
    assert empty["events"] == 0

    record_metric(cfg, "start_project")
    record_metric(cfg, "smoke_test_zeus_ok")
    record_metric(cfg, "smoke_test_agent_ok")
    summary = metrics_summary(cfg)
    assert summary["start_project_count"] == 1
    assert summary["smoke_agent_ok_count"] == 1
    assert summary["time_to_green_seconds"] is not None


def test_next_step_post_green_hints(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    data = load_checklist(cfg)
    # mark everything done for cleaner complete path
    for phase in data.get("phases") or []:
        for item in phase.get("items") or []:
            item["status"] = "done"
    save_checklist(cfg, data)
    nxt = enriched_next_step(cfg)
    assert "post_green" in nxt
    tools = nxt.get("recommended_tools") or []
    assert "recommend_data_plane_mcp" in tools or "handoff_to_multi" in (
        nxt["post_green"].get("suggested_tools") or []
    )
