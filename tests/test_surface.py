from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.explain import explain_topic
from zeus_dev_helper_mcp.surface import INTENTS, recommend_surface


def test_typeahead_is_direct_interactive() -> None:
    out = recommend_surface(HelperConfig(), intent="typeahead")
    assert out["ok"] is True
    assert out["surface"] == "rt.data.search"
    assert out["trace_class"] == "direct.interactive"
    assert any("pipeline" in x.lower() for x in out["do_not"])


def test_multi_step_not_direct_pipeline() -> None:
    out = recommend_surface(HelperConfig(), intent="multi_step")
    assert out["ok"] is True
    assert out["surface"] == "agent-for-pipeline"
    assert out["trace_class"] == "agent"
    assert out["surface"] != "rt.data.verb"
    joined = " ".join(out["do_not"]).lower()
    assert "pipeline" in joined
    assert "direct" in joined


def test_nl_question_run_turn() -> None:
    out = recommend_surface(HelperConfig(), intent="nl_question")
    assert out["surface"] == "rt.agent.run_turn"
    assert out["trace_class"] == "agent"


def test_nl_question_no_llm_is_direct_not_travel() -> None:
    out = recommend_surface(HelperConfig(), intent="nl_question", needs_llm=False)
    assert out["ok"] is True
    assert out["surface"] == "rt.data.verb"
    assert out["trace_class"] == "direct.read"
    blob = " ".join(out.get("notes") or []).lower()
    assert "beer" in blob or "direct" in blob
    assert "travel" in blob
    assert "run_turn" in blob and "do not copy" in blob
    assert "use_sample" in (out.get("next_action") or "")
    assert "smoke_test_agent" not in (out.get("recommended_tools") or [])


def test_single_verb_direct_read() -> None:
    out = recommend_surface(HelperConfig(), intent="single_verb")
    assert out["surface"] == "rt.data.verb"
    assert out["trace_class"] == "direct.read"


def test_unknown_intent() -> None:
    out = recommend_surface(HelperConfig(), intent="telepathy")
    assert out["ok"] is False
    assert out["known_intents"] == list(INTENTS)


def test_high_qps_warns_off_agent() -> None:
    out = recommend_surface(HelperConfig(), intent="typeahead", qps=50)
    assert any("qps=" in n for n in out["notes"])


def test_explain_new_topics() -> None:
    cfg = HelperConfig()
    for topic, expect in (
        ("zeus_runtime", "ZeusRuntime"),
        ("turn_result", "TurnResult"),
        ("cheap_path", "ai_process_result"),
        ("semantic_cache", "0.7.6"),
        ("req_id_policy", "UUID"),
        ("trace_class", "direct.interactive"),
        ("direct", "pipeline"),
        ("typeahead", "rt.data.search"),
        ("pipeline", "Direct"),
        ("demo_travel_sample", "agent-plane"),
        ("travelplan", "agent-plane"),
        ("demo_beer_sample", "data-plane"),
        ("beer_direct", "data-plane"),
    ):
        out = explain_topic(cfg, topic)
        assert out["found"] is True, topic
        assert expect.lower() in out["summary"].lower() or expect in out["summary"]
