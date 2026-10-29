"""ZDM-46: a helper-written catalog page is One chat paired with Direct."""

from __future__ import annotations

import json
from pathlib import Path

from zeus_dev_helper_mcp.beer import write_beer_config, write_beer_sample
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.scaffold import runtime_config_dict


def test_written_beer_config_uses_four_rounds_and_no_jobs(tmp_path: Path) -> None:
    cfg = HelperConfig(
        zeus_url="http://127.0.0.1:8080",
        default_bucket="beer-sample",
        default_scope="_default",
        state_dir=tmp_path / "state",
    )
    out = write_beer_sample(cfg, tmp_path / "demo_beer_sample")
    assert out["ok"] is True
    assert out["llm_required"] is False
    assert out["lists_llm_required"] is False
    assert out["question_llm_required"] is True
    root = Path(out["local_dir"])
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    assert config["settings"]["max_rounds"] == 4
    assert config["settings"]["mode"] == "analytics"
    assert config["settings"]["durable_sessions"] is False
    assert config["settings"]["ai_process_result"] is False
    assert "jobs" not in config
    assert "roles" not in config["llm"]
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "run with no LLM key" in readme
    assert "stays off until" in readme
    assert "`max_rounds` 4" in readme
    main = (root / "main.py").read_text(encoding="utf-8")
    assert '"llm_required": False' in main
    assert "rt.agent.run_turn" in main or "agent.run_turn" in main

    again = write_beer_config(cfg, root)
    assert again["ok"] is True
    pinned = json.loads(Path(again["path"]).read_text(encoding="utf-8"))
    assert pinned["settings"]["max_rounds"] == 4
    assert "jobs" not in pinned


def test_copilot_scaffold_stays_at_eight_rounds() -> None:
    cfg = HelperConfig(default_bucket="travel-sample", default_scope="_default")
    config = runtime_config_dict(cfg)
    assert config["settings"]["max_rounds"] == 8
    assert "jobs" not in config
    assert "roles" not in config["llm"]
