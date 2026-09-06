from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.explain import explain_topic
from zeus_dev_helper_mcp.motion import MOTIONS, recommend_motion
from zeus_dev_helper_mcp.walkthrough import TOOL_HINTS


def test_thirteen_motions() -> None:
    assert len(MOTIONS) == 13


def test_recommend_funnel() -> None:
    out = recommend_motion(HelperConfig(), user_job="book a hotel in April")
    assert out["ok"] is True
    assert out["motion"] == "funnel"
    assert out["chat_request"] is None
    assert "find" in out["typical_verbs"]
    assert "pipeline" not in (out.get("typical_verbs") or []) or "do_not" in out


def test_recommend_verify() -> None:
    out = recommend_motion(HelperConfig(), user_job="Is this claim true and allowed?")
    assert out["motion"] == "verify"


def test_recommend_explore_default() -> None:
    out = recommend_motion(HelperConfig(), user_job="help me investigate this revenue drop")
    assert out["motion"] == "explore"
    assert out["chat_request"] is None


def test_explain_motion_lists_thirteen() -> None:
    out = explain_topic(HelperConfig(), "motion")
    assert out["found"] is True
    s = out["summary"]
    for name in ("Funnel", "Explore", "Verify", "Custom"):
        assert name in s
    assert "mode" in s.lower()
    funnel = explain_topic(HelperConfig(), "funnel")
    assert funnel["found"] is True
    assert funnel["topic"] == "funnel"


def test_tool_hints_01_motion() -> None:
    assert "recommend_motion" in TOOL_HINTS["0.1"]
