"""ZDM-3: set_prereq URL/bucket/scope must win over MCP host ZEUS_* env."""

from __future__ import annotations

from pathlib import Path

from zeus_dev_helper_mcp.config import load_config, reload_config
from zeus_dev_helper_mcp.prereqs import save_prereqs
from zeus_dev_helper_mcp.server import set_prereq


def test_persisted_zeus_url_wins_over_localhost_env(tmp_path: Path, monkeypatch) -> None:
    """Lab case: MCP host ZEUS_URL=localhost must not shadow set_prereq remote URL."""
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(state))
    monkeypatch.setenv("ZEUS_URL", "http://localhost:8080")
    monkeypatch.setenv("ZEUS_BUCKET", "travel-sample")
    monkeypatch.setenv("ZEUS_SCOPE", "_default")

    cfg = reload_config()
    save_prereqs(
        cfg,
        {
            "zeus_url": "http://192.168.0.219:8080",
            "bucket": "beer-sample",
            "scope": "_default",
            "has_llm_key": False,
        },
    )
    cfg = reload_config()
    assert cfg.zeus_url == "http://192.168.0.219:8080"
    assert cfg.default_bucket == "beer-sample"
    assert cfg.default_scope == "_default"
    # Host env is still localhost — precedence must ignore it when prereq is set.
    import os

    assert os.environ.get("ZEUS_URL") == "http://localhost:8080"
    assert load_config().zeus_url == "http://192.168.0.219:8080"


def test_set_prereq_effective_config_ignores_host_zeus_url(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(state))
    monkeypatch.setenv("ZEUS_URL", "http://localhost:8080")
    reload_config()

    out = set_prereq(
        zeus_url="http://192.168.0.219:8080",
        bucket="beer-sample",
        scope="_default",
        has_llm_key=False,
    )
    assert out["saved"] is True
    eff = out["effective_config"]
    assert eff["zeus_url"] == "http://192.168.0.219:8080"
    assert eff["default_bucket"] == "beer-sample"
    # Process env mirrored so direct ZEUS_* readers see the lab URL too.
    import os

    assert os.environ.get("ZEUS_URL") == "http://192.168.0.219:8080"
    assert reload_config().zeus_url == "http://192.168.0.219:8080"


def test_env_used_when_no_prereq_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "empty-state"))
    monkeypatch.setenv("ZEUS_URL", "http://localhost:8080")
    monkeypatch.delenv("ZEUS_BUCKET", raising=False)
    cfg = reload_config()
    assert cfg.zeus_url == "http://localhost:8080"
    assert cfg.default_bucket == ""
