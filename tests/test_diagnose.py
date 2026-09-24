import ast
from pathlib import Path

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.diagnose import diagnose_error


def test_diagnose_409() -> None:
    out = diagnose_error(HelperConfig(), status="409", message="contract drift")
    assert out["failure_class"] == "hash_drift"
    assert out["doc_anchor"] == "err-409-drift"


def test_diagnose_wrong_port() -> None:
    out = diagnose_error(HelperConfig(), zeus_url="http://localhost:9091")
    assert out["failure_class"] == "wrong_port_hub_vs_public"


def test_diagnose_401() -> None:
    out = diagnose_error(HelperConfig(), status="401", body="unauthorized")
    assert out["failure_class"] == "auth_failed"


def test_diagnose_invalid_req_id() -> None:
    out = diagnose_error(
        HelperConfig(),
        status="400",
        body='{"error":"invalid_req_id","error_class":"invalid_req_id"}',
        error_class="invalid_req_id",
    )
    assert out["failure_class"] == "invalid_req_id"
    assert "detective" not in out


def test_diagnose_base1_composite() -> None:
    out = diagnose_error(HelperConfig(), status="400", message="X-Zeus-Req-Id rejected: base:1")
    assert out["failure_class"] == "composite_req_id"


def test_diagnose_060010_pipeline() -> None:
    out = diagnose_error(HelperConfig(), error_code="060010", message="pipeline")
    assert out["failure_class"] == "pipeline_not_on_direct"
    assert out["matched_via"] == "error_code"


def test_diagnose_030005_invent_hash() -> None:
    out = diagnose_error(HelperConfig(), error_code="CONTRACT_HASH_INVENT_FORBIDDEN")
    assert out["failure_class"] == "contract_hash_invent_forbidden"


def test_diagnose_v1_session_404() -> None:
    out = diagnose_error(HelperConfig(), status="404", message="GET /v1/session/abc")
    assert out["failure_class"] == "v1_session_removed"


def test_diagnose_detective_urls_only() -> None:
    out = diagnose_error(
        HelperConfig(zeus_url="http://localhost:8080"),
        status="500",
        req_id="req-abc",
        chat_id="chat-1",
        message="dispatch failed",
    )
    det = out.get("detective") or {}
    assert det["req"].endswith("/hub/debug/req/req-abc")
    assert "chat_id=chat-1" in det["chat"]
    assert "9091" in det["req"]
    assert "scrape" in (out.get("detective_note") or "").lower()


def test_diagnose_session_force_closed() -> None:
    out = diagnose_error(
        HelperConfig(),
        status="429",
        message="session exceeded per-session round budget; re-authenticate to continue. session_force_closed",
    )
    assert out["failure_class"] == "session_force_closed"
    assert out["doc_anchor"] == "err-session-force-closed"
    assert "sid=dev" in out["next_action"] or "unique sid" in out["next_action"].lower()


def test_diagnose_empty_find_get_node_ids_required() -> None:
    out = diagnose_error(
        HelperConfig(),
        status="400",
        message="STEP_FAILED: node_ids required",
        body='{"error":"STEP_FAILED","message":"node_ids required"}',
    )
    assert out["failure_class"] == "empty_find_get"
    assert out["doc_anchor"] == "err-empty-find-get"
    assert "never get" in out["next_action"].lower()
    assert "bad plan" in out["next_action"].lower() or "not empty zeus" in out["next_action"].lower()


def test_diagnose_sentence_as_query_points_at_nl_plan() -> None:
    out = diagnose_error(
        HelperConfig(),
        message="0 rows on a sentence: find.query=What beers are made from fruit?",
        body="sentence as query / NL sentence stuffed into find",
    )
    assert out["failure_class"] == "empty_find_get"
    assert "where.style" in out["next_action"] or "Fruit Beer" in out["next_action"]
    assert "plan" in out["next_action"].lower() or "token" in out["next_action"].lower()
    assert "empty zeus" in out["next_action"].lower() or "bad plan" in out["next_action"].lower()


def test_diagnose_fts_doc_key_only() -> None:
    out = diagnose_error(
        HelperConfig(),
        message="FTS hits with empty node_ids and doc_key only",
        body='{"items":[{"node":{"doc_key":"beer:1"}}],"node_ids":[]}',
    )
    assert out["failure_class"] == "fts_doc_key_only"
    assert out["doc_anchor"] == "err-fts-doc-key-only"
    assert "doc_key" in out["next_action"]


def test_diagnose_does_not_import_zeus_client() -> None:
    src = Path("src/zeus_dev_helper_mcp/diagnose.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(not a.name.startswith("zeus_client") for a in node.names)
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("zeus_client")
