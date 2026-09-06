from zeus_dev_helper_mcp.cache import interpret_memory_status, semantic_cache_status
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.explain import explain_topic
from zeus_dev_helper_mcp.scaffold import write_env_example


def test_interpret_404_too_old_or_off() -> None:
    out = interpret_memory_status(404)
    assert out["available"] is False
    assert "too old" in out["detail"] or "flag off" in out["detail"]


def test_interpret_200() -> None:
    out = interpret_memory_status(200, {"enabled": False, "embedder": True})
    assert out["available"] is True
    assert out["engine_enabled"] is False


def test_semantic_cache_no_url_stays_off() -> None:
    out = semantic_cache_status(HelperConfig(zeus_url=""))
    assert out["recommended_enabled"] is False
    assert out["recommendation"]["client_enabled"] is False
    assert out["probe"]["probe"] == "skip"


def test_semantic_cache_rejects_hub() -> None:
    out = semantic_cache_status(HelperConfig(zeus_url="http://localhost:9091"))
    assert out["ok"] is False
    assert out["recommended_enabled"] is False
    assert out["failure_class"] == "wrong_port_hub_vs_public"


def test_explain_semantic_cache() -> None:
    out = explain_topic(HelperConfig(), "semantic_cache")
    assert out["found"] is True
    s = out["summary"].lower()
    assert "0.7.6" in s
    assert "false" in s or "off" in s
    assert "direct" in s


def test_env_example_leaves_cache_off(tmp_path) -> None:
    out = write_env_example(HelperConfig(state_dir=tmp_path / "state"), tmp_path)
    text = (tmp_path / ".env.example").read_text()
    assert "semantic_cache" in text
    assert "false" in text
    assert out["ok"] is True
