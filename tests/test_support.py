import json
from pathlib import Path

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.support import (
    SMOKE_ARTIFACT,
    detective_links,
    explain_req_id_policy,
    support_pack_from_turn,
)
from zeus_dev_helper_mcp.walkthrough import TOOL_HINTS


def test_explain_req_id_policy() -> None:
    out = explain_req_id_policy(HelperConfig())
    blob = json.dumps(out).lower()
    assert out["ok"] is True
    assert "uuid" in blob
    assert "base:1" in blob
    assert "/v2/session" in blob and "turn" in blob


def test_detective_links_templates_only() -> None:
    out = detective_links(
        HelperConfig(zeus_url="http://localhost:8080"),
        req_id="req-1",
        chat_id="chat-9",
    )
    assert out["ok"] is True
    assert out["links"]["req"].endswith("/hub/debug/req/req-1")
    assert "9091" in out["links"]["req"]
    assert "chat_id=chat-9" in out["links"]["chat"]
    assert "scrape" in out["note"].lower()


def test_support_pack_redacts_and_no_bodies(tmp_path: Path) -> None:
    debug = {
        "chat_id": "c1",
        "turn_id": "t1",
        "session_id": "s1",
        "req_ids": ["req-aaa"],
        "password": "hunter2",
        "prompt": "secret user prompt",
        "hops": [
            {
                "name": "find",
                "status": 200,
                "req_id": "req-aaa",
                "body": {"where": {"x": 1}},
                "snippet": "DOCUMENT SAMPLE xyz",
            }
        ],
    }
    out = support_pack_from_turn(
        HelperConfig(state_dir=tmp_path, zeus_url="http://localhost:8080"),
        debug_json=json.dumps(debug),
    )
    assert out["ok"] is True
    md = out["markdown"]
    assert "hunter2" not in md
    assert "secret user prompt" not in md
    assert "DOCUMENT SAMPLE" not in md
    assert "req-aaa" in md
    assert "find" in md
    assert out["detective"]["req"].endswith("/hub/debug/req/req-aaa")
    assert "body" not in (out["ids"]["hops"][0] or {})


def test_support_pack_from_smoke_artifact(tmp_path: Path) -> None:
    art = tmp_path / SMOKE_ARTIFACT
    art.write_text(
        json.dumps({"session_id": "sess-9", "req_ids": ["r2"], "hops": [{"name": "describe", "status": 200}]}),
        encoding="utf-8",
    )
    out = support_pack_from_turn(HelperConfig(state_dir=tmp_path))
    assert out["ok"] is True
    assert out["ids"]["session_id"] == "sess-9"
    assert "describe" in out["markdown"]


def test_tool_hints_71_support() -> None:
    assert "support_pack_from_turn" in TOOL_HINTS["7.1"]
    assert "detective_links" in TOOL_HINTS["7.1"]
