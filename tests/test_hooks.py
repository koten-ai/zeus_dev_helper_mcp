from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.explain import explain_topic
from zeus_dev_helper_mcp.hooks import suggest_hooks
from zeus_dev_helper_mcp.walkthrough import TOOL_HINTS


def test_suggest_hooks_all_recipes() -> None:
    out = suggest_hooks(HelperConfig())
    assert out["ok"] is True
    assert out["executed"] is False
    ids = {r["id"] for r in out["recipes"]}
    assert ids == {
        "tenant_pin",
        "deny_pipeline_direct",
        "output_schema_allowlist",
        "never_promote_ocr",
    }
    blob = " ".join(r["snippet"] for r in out["recipes"])
    assert "before_zeus" in blob
    assert "pipeline" in blob
    assert "output_schema" in blob
    assert "OCR" in blob
    assert "system" in blob.lower()


def test_suggest_hooks_filter() -> None:
    out = suggest_hooks(HelperConfig(), recipe="ocr")
    assert len(out["recipes"]) == 1
    assert out["recipes"][0]["id"] == "never_promote_ocr"


def test_suggest_hooks_unknown() -> None:
    out = suggest_hooks(HelperConfig(), recipe="telepathy")
    assert out["ok"] is False
    assert out["executed"] is False


def test_checklist_hints_hooks() -> None:
    assert "suggest_hooks" in TOOL_HINTS["6.1"]
    assert "suggest_hooks" in TOOL_HINTS["7.1"]


def test_explain_hooks_topic() -> None:
    out = explain_topic(HelperConfig(), "agent_hooks")
    assert out["found"] is True
