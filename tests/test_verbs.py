from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.verbs import explain_verb, lint_verb_args, suggest_verb_call


def test_explain_find_return_demux() -> None:
    out = explain_verb(HelperConfig(), name="find")
    assert out["ok"] is True
    assert out["path_class"] == "collection"
    assert "return" in (out.get("demux") or "").lower()
    assert "find_nodes" in (out.get("demux") or "")


def test_explain_pipeline_not_on_direct() -> None:
    out = explain_verb(HelperConfig(), name="pipeline")
    assert out["ok"] is True
    assert out["direct_ok"] is False
    assert out.get("not_on_direct") is True


def test_lint_accepts_json_string_body() -> None:
    out = lint_verb_args(
        HelperConfig(),
        verb="find",
        body='{"where": {"abv": {"$gt": 5}}}',
        use_live_schema=False,
    )
    assert out["posted"] is False
    assert any(i["code"] == "where_not_equality" for i in out["issues"])


def test_lint_find_where_gt() -> None:
    out = lint_verb_args(
        HelperConfig(),
        verb="find",
        body={"entity_type": "Beer", "where": {"abv": {"$gt": 5}}, "return": "ids"},
        use_live_schema=False,
    )
    assert out["posted"] is False
    codes = {i["code"] for i in out["issues"]}
    assert "where_not_equality" in codes
    assert out["ok"] is False


def test_lint_unknown_where_field_with_schema() -> None:
    out = lint_verb_args(
        HelperConfig(),
        verb="find",
        body={"where": {"no_such_field": "x"}, "return": "ids"},
        mini_schema=["name", "style", "abv"],
        use_live_schema=False,
    )
    codes = {i["code"] for i in out["issues"]}
    assert "where_key_not_in_schema" in codes
    assert any(i.get("failure_class") == "where_not_in_mini_schema" for i in out["issues"])


def test_lint_known_equality_where_ok() -> None:
    out = lint_verb_args(
        HelperConfig(),
        verb="find",
        body={"where": {"style": "IPA"}, "return": "ids"},
        mini_schema=["name", "style", "abv"],
        use_live_schema=False,
    )
    assert out["ok"] is True
    assert out["issues"] == []


def test_lint_pipeline_on_direct() -> None:
    out = lint_verb_args(
        HelperConfig(),
        verb="pipeline",
        body={"steps": [{"verb": "find", "params": {}}]},
        use_live_schema=False,
    )
    assert any(i["failure_class"] == "pipeline_not_on_direct" for i in out["issues"])


def test_lint_fts_biz_key() -> None:
    out = lint_verb_args(
        HelperConfig(),
        verb="get",
        body={"ids": ["biz:abc123"]},
        use_live_schema=False,
    )
    assert any(i["failure_class"] == "fts_key_used_as_node_id" for i in out["issues"])


def test_suggest_does_not_post() -> None:
    out = suggest_verb_call(
        HelperConfig(),
        goal="find beers",
        mini_schema=["abv", "name", "Beer"],
        use_live_schema=False,
    )
    assert out["posted"] is False
    assert out["verb"] == "find"
    assert isinstance(out.get("body"), dict)
    where = (out["body"] or {}).get("where") or {}
    assert all(not isinstance(v, dict) for v in where.values())


def test_suggest_pipeline_goal_no_direct_body() -> None:
    out = suggest_verb_call(
        HelperConfig(),
        goal="run a pipeline then find",
        use_live_schema=False,
    )
    assert out["posted"] is False
    assert out["verb"] is None
    assert out["surface"] == "agent-for-pipeline"
    assert out["body"] is None


def test_lint_skips_live_when_no_url() -> None:
    out = lint_verb_args(
        HelperConfig(zeus_url=""),
        verb="find",
        body={"where": {"abv": 5}},
        use_live_schema=True,
    )
    assert out["schema_source"] in ("none", "skipped:no_live_target")
    assert out["posted"] is False
