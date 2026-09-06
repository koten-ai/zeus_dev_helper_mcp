from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.verbs import describe_scope, schema_from_describe
from zeus_dev_helper_mcp.walkthrough import TOOL_HINTS


def test_schema_from_describe_names_only() -> None:
    payload = {
        "result": {
            "entity_types": [
                {"name": "Beer", "fields": ["abv", "ibu", {"name": "style"}]},
                {"name": "Brewery", "properties": ["city", "country"]},
            ],
            "items": [{"id": "n_1", "body": {"secret": "NOPE"}}],
            "documents": [{"text": "full document sample"}],
        }
    }
    schema = schema_from_describe(payload)
    names = {t["name"] for t in schema["entity_types"]}
    assert names == {"Beer", "Brewery"}
    assert "abv" in schema["field_names"]
    assert "city" in schema["field_names"]
    assert schema["includes_samples"] is False
    blob = str(schema)
    assert "NOPE" not in blob
    assert "full document sample" not in blob


def test_describe_scope_rejects_hub() -> None:
    out = describe_scope(
        HelperConfig(zeus_url="http://localhost:9091", default_bucket="b", default_scope="s")
    )
    assert out["ok"] is False
    assert out["failure_class"] == "wrong_port_hub_vs_public"


def test_describe_scope_needs_url() -> None:
    out = describe_scope(HelperConfig(zeus_url=""))
    assert out["ok"] is False


def test_tool_hints_51_describe() -> None:
    assert "describe_scope" in TOOL_HINTS["5.1"]
