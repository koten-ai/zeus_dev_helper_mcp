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
    assert "inputs" not in out
    assert out["job"]["hard_stop"] == "one_scope"
    assert out["job"]["hint"] is False
    assert out["job"]["write"] is False
    joined = " ".join(out["do_not"]).lower()
    assert "pipeline" in joined
    assert "direct" in joined


def _rows(out: dict) -> dict:
    assert "surface" not in out
    assert "trace_class" not in out
    return {row["input"]: row for row in out["inputs"]}


def test_nl_question_names_each_input() -> None:
    out = recommend_surface(HelperConfig(), intent="nl_question")
    assert out["ok"] is True
    assert out["page"] == "catalog"
    rows = _rows(out)
    assert set(rows) == {"list", "chips", "typeahead", "paging", "detail", "question"}
    for name in ("list", "chips", "typeahead", "paging", "detail"):
        assert rows[name]["mode"] == "direct"
        assert rows[name]["llm"] is False
        assert rows[name]["enabled"] is True
        assert rows[name]["chat_request"] is None
    question = rows["question"]
    assert question["mode"] == "one_chat"
    assert question["surface"] == "rt.agent.run_turn"
    assert question["trace_class"] == "agent"
    assert question["chat_request"] == "omit"
    assert question["max_rounds"] == 4
    assert question["enabled"] is True
    assert question["llm"] is True
    assert out["job"]["hard_stop"] == "one_scope"
    assert out["job"]["write"] is False
    assert "smoke_test_agent" not in (out.get("recommended_tools") or [])
    assert "run_turn" in (out.get("next_action") or "")


def test_nl_question_no_llm_keeps_direct_inputs() -> None:
    out = recommend_surface(HelperConfig(), intent="nl_question", needs_llm=False)
    assert out["ok"] is True
    rows = _rows(out)
    assert rows["list"]["enabled"] is True
    assert rows["detail"]["enabled"] is True
    assert rows["question"]["enabled"] is False
    assert rows["question"]["max_rounds"] == 4
    assert "run_turn" not in (out.get("next_action") or "")
    assert "smoke_test_agent" not in (out.get("recommended_tools") or [])
    assert any("stays off" in note for note in out["notes"])


def test_nl_question_with_llm_keeps_the_pair() -> None:
    out = recommend_surface(HelperConfig(), intent="nl_question", needs_llm=True)
    rows = _rows(out)
    assert rows["question"]["enabled"] is True
    assert rows["question"]["surface"] == "rt.agent.run_turn"
    assert rows["list"]["mode"] == "direct"
    assert "run_turn" in (out.get("next_action") or "")


def test_copilot_question_uses_eight_rounds() -> None:
    out = recommend_surface(HelperConfig(), intent="nl_question", page="copilot")
    rows = _rows(out)
    assert out["page"] == "copilot"
    assert rows["question"]["max_rounds"] == 8


def test_two_urls_are_a_job_hint() -> None:
    out = recommend_surface(HelperConfig(), intent="nl_question", url_count=2)
    assert out["job"]["hint"] is True
    assert out["job"]["write"] is False
    assert out["job"]["hard_stop"] is None
    assert out["job"]["wall_ms"] == 120000
    assert out["job"]["reason"] == "multi_url"
    assert "wait for a yes" in (out.get("next_action") or "")


def test_long_report_uses_the_longer_wall() -> None:
    short = recommend_surface(HelperConfig(), intent="nl_question", report_wait_s=20)
    two_minutes = recommend_surface(HelperConfig(), intent="nl_question", report_wait_s=120)
    five_minutes = recommend_surface(HelperConfig(), intent="nl_question", report_wait_s=300)
    assert short["job"]["hint"] is True
    assert short["job"]["wall_ms"] == 120000
    assert two_minutes["job"]["hint"] is True
    assert two_minutes["job"]["wall_ms"] == 120000
    assert five_minutes["job"]["hint"] is True
    assert five_minutes["job"]["wall_ms"] == 300000
    assert five_minutes["job"]["write"] is False


def test_two_source_types_stay_one_chat() -> None:
    out = recommend_surface(HelperConfig(), intent="nl_question", source_type_count=2)
    assert out["job"]["hint"] is False
    assert out["job"]["hard_stop"] == "two_source_types"
    assert out["job"]["write"] is False


def test_analytics_mode_does_not_promote_a_job() -> None:
    out = recommend_surface(
        HelperConfig(),
        intent="nl_question",
        settings_mode="analytics",
    )
    assert out["job"]["hint"] is False
    assert out["job"]["hard_stop"] == "one_scope"
    assert out["job"]["settings_mode"] == "analytics"


def test_page_interaction_is_a_hard_stop() -> None:
    out = recommend_surface(HelperConfig(), intent="nl_question", page_interaction=True)
    assert out["job"]["hard_stop"] == "page_interaction"
    assert out["job"]["hint"] is False
    assert out["job"]["write"] is False
    long = recommend_surface(
        HelperConfig(),
        intent="nl_question",
        page_interaction=True,
        report_wait_s=300,
        url_count=2,
    )
    assert long["job"]["hard_stop"] == "page_interaction"
    assert long["job"]["hint"] is False
    assert long["job"]["write"] is False


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
        ("demo_beer_sample", "Direct"),
        ("beer_direct", "Direct"),
    ):
        out = explain_topic(cfg, topic)
        assert out["found"] is True, topic
        assert expect.lower() in out["summary"].lower() or expect in out["summary"]
