import json
from pathlib import Path

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.contract import (
    bind_contract,
    catalog_diff,
    explain_hash_boundary,
    extract_stamped_hash,
    lint_chat_request,
)
from zeus_dev_helper_mcp.walkthrough import TOOL_HINTS

STAMPED = {
    "_format": "zeus.chat_request.v2",
    "verbs": [{"name": "find"}],
    "contract": {"id": "analytics_base", "hash": "md5:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
}

PLACEHOLDER = {
    "_format": "zeus.chat_request.v2",
    "verbs": [{"name": "find"}],
    "contract": {"hash": "md5:TO_BE_FILLED"},
}


def test_extract_skips_placeholder() -> None:
    assert extract_stamped_hash(PLACEHOLDER) == ""
    assert extract_stamped_hash(STAMPED).startswith("md5:aaaa")
    assert extract_stamped_hash({"contract": {"hash": "compute_local"}}) == ""


def test_lint_placeholder_and_missing_verbs() -> None:
    cfg = HelperConfig()
    bad = lint_chat_request(cfg, json_text=json.dumps(PLACEHOLDER))
    assert bad["ok"] is False
    classes = {i.get("failure_class") for i in bad["issues"]}
    assert "contract_hash_invent_forbidden" in classes

    empty = lint_chat_request(cfg, json_text=json.dumps({"_format": "nope"}))
    assert empty["ok"] is False
    fields = {i["field"] for i in empty["issues"]}
    assert "verbs" in fields
    assert "_format" in fields


def test_lint_stamped_ok() -> None:
    out = lint_chat_request(HelperConfig(), json_text=json.dumps(STAMPED))
    assert out["ok"] is True
    assert out["has_stamped_hash"] is True
    assert out["verb_count"] == 1


def test_bind_refuses_empty_and_placeholder() -> None:
    cfg = HelperConfig()
    empty = bind_contract(cfg, json_text="{}")
    assert empty["ok"] is False
    assert empty["failure_class"] == "contract_hash_invent_forbidden"
    ph = bind_contract(cfg, json_text=json.dumps(PLACEHOLDER))
    assert ph["ok"] is False


def test_bind_snippet_from_stamp() -> None:
    cfg = HelperConfig(default_bucket="beer-sample", default_scope="_default", default_mode="analytics")
    out = bind_contract(cfg, json_text=json.dumps(STAMPED))
    assert out["ok"] is True
    assert out["contract_hash"].startswith("md5:aaaa")
    pin = out["scope_contracts"]["beer-sample/_default"]["analytics"]
    assert pin["contract_hash"] == out["contract_hash"]
    assert "compute" not in json.dumps(out).lower() or "did not compute" in out["note"].lower()


def test_bind_from_path(tmp_path: Path) -> None:
    p = tmp_path / "cr.json"
    p.write_text(json.dumps(STAMPED), encoding="utf-8")
    out = bind_contract(HelperConfig(), path=str(p), bucket="b", scope="s", mode="analytics")
    assert out["ok"] is True
    assert "b/s" in out["scope_contracts"]


def test_explain_hash_boundary() -> None:
    out = explain_hash_boundary(HelperConfig())
    assert out["ok"] is True
    blob = json.dumps(out).lower()
    assert "mini-schema" in blob
    assert "excluded" in blob
    assert "guidance" in blob


def test_catalog_diff_disk_vs_bound(tmp_path: Path) -> None:
    p = tmp_path / "cr.json"
    p.write_text(json.dumps(STAMPED), encoding="utf-8")
    out = catalog_diff(
        HelperConfig(zeus_url=""),
        path=str(p),
        bound_hash=STAMPED["contract"]["hash"],
    )
    assert out["ok"] is True
    assert out["disk"]["verb_count"] == 1
    assert out["compare"].get("disk_vs_bound") is True
    assert "chat_request" not in (out.get("disk") or {})
    assert out.get("live") is None


def test_tool_hints_42_bind() -> None:
    assert "bind_contract" in TOOL_HINTS["4.2"]
    assert "catalog_diff" in TOOL_HINTS["4.2"]
