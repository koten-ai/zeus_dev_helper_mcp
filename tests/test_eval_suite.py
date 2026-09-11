"""ZDH-40: prompt corpus + first-green trace checks (no cluster, no payloads)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.eval_suite import (
    EVAL_TOOLS,
    check_trace,
    evaluate_corpus,
    load_prompt_cases,
)
from zeus_dev_helper_mcp.handoff import metrics_summary, record_metric
from zeus_dev_helper_mcp.server import create_mcp_server


def test_eval_corpus_has_twenty_prompts() -> None:
    cases = load_prompt_cases()
    assert len(cases) >= 20
    assert {c["expected_tool"] for c in cases} == set(EVAL_TOOLS)
    report = evaluate_corpus()
    assert report["ok"] is True, report["failed"]


def test_trace_requires_coach_before_scaffold() -> None:
    bad = check_trace(["set_prereq", "scaffold_app", "smoke_test_agent"])
    assert bad["ok"] is False
    assert any("scaffold_app" in i for i in bad["issues"])
    good = check_trace(["doctor", "start_project", "next_step", "scaffold_app"])
    assert good["ok"] is True
    also = check_trace(["next_step", "scaffold_app"])
    assert also["ok"] is True


def test_metrics_records_tool_ids_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    cfg = HelperConfig(state_dir=tmp_path / "state")
    record_metric(cfg, "tool_call", tool="doctor")
    record_metric(cfg, "tool_call", tool="next_step")
    record_metric(cfg, "tool_call", tool="scaffold_app")
    summary = metrics_summary(cfg)
    assert summary["tool_calls"] == ["doctor", "next_step", "scaffold_app"]
    assert summary["sequence"]["ok"] is True
    blob = str(summary)
    assert "password" not in blob.lower()
    assert "prompt" not in (summary.get("note") or "").lower() or "no payloads" in summary["note"]


def test_mcp_wrap_records_tool_name(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("ZEUS_URL", raising=False)
    server = create_mcp_server(["core"])
    asyncio.run(server.call_tool("doctor", {}))
    summary = metrics_summary(HelperConfig(state_dir=tmp_path / "state"))
    assert "doctor" in summary["tool_calls"]
    raw = (tmp_path / "state" / "metrics.jsonl").read_text()
    assert "ZEUS_PASSWORD" not in raw
    assert "tool_call" in raw
