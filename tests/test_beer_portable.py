"""ZDM-44: a helper-written beer app has the same run layout as the published sample."""

from __future__ import annotations

import json
import py_compile
from pathlib import Path

import pytest

from zeus_dev_helper_mcp.beer import write_beer_sample
from zeus_dev_helper_mcp.config import HelperConfig

_PASSWORD = "zdm44-password-sentinel"


def test_written_tree_is_a_portable_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZEUS_USERNAME", "lab-user")
    monkeypatch.setenv("ZEUS_PASSWORD", _PASSWORD)
    cfg = HelperConfig(
        zeus_url="http://lab.example:8080",
        zeus_auth_mode="basic",
        default_bucket="beer-sample",
        default_scope="_default",
        state_dir=tmp_path / "state",
    )
    out = write_beer_sample(cfg, tmp_path / "demo_beer_sample")
    assert out["ok"] is True
    root = Path(out["local_dir"])
    py_compile.compile(root / "main.py", doraise=True)

    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    ignore = (root / ".dockerignore").read_text(encoding="utf-8")
    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    example = (root / ".env.example").read_text(encoding="utf-8")
    main = (root / "main.py").read_text(encoding="utf-8")
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))

    assert "COPY .env" not in dockerfile
    assert "COPY data" not in dockerfile
    assert "8090:8090" in compose
    assert "http://host.docker.internal:8080" in compose
    assert "./data:/app/data" in compose
    url_lines = [
        line
        for line in compose.splitlines()
        if "ZEUS_URL" in line and not line.strip().startswith("#")
    ]
    assert url_lines
    assert all(":8080" in line and ":9091" not in line for line in url_lines)
    assert ".env" in ignore.splitlines()
    assert "data" in ignore.splitlines()
    assert "data/" in gitignore.splitlines()
    assert "HOST=127.0.0.1" in example
    assert "ZEUS_USERNAME=tester_beer" in example
    assert "ZEUS_PASSWORD=" in example
    assert "ZEUS_URL=http://lab.example:8080" in example
    assert "LLM_MODEL=grok-4-1-fast-non-reasoning" in example
    assert config["zeus"]["url"] == "http://localhost:8080"
    assert "username" not in config["zeus"]
    assert config["zeus"]["password_env"] == "ZEUS_PASSWORD"
    assert _PASSWORD not in (root / "config.json").read_text(encoding="utf-8")
    assert _PASSWORD not in json.dumps(out)
    assert config["chat_requests_dir"] == "data/chat_requests"
    assert config["llm"]["model"] == "LLM_MODEL"
    assert config["llm"]["base_url"] == "LLM_BASE_URL"
    catalog = (
        root
        / "data"
        / "chat_requests"
        / "beer-sample__default"
        / "chat_request_analytics_v2.json"
    )
    assert catalog.is_file()
    assert not (root / "data" / "chat_requests" / "chat_request_analytics_v2.json").exists()
    search = main.split("async def _run_search", 1)[1]
    assert "await rt.catalog.sync()" in main
    assert "await rt.catalog.load_for_turn(cfg.settings.mode, target=cfg.target)" in search
    call = search.split("await rt.catalog.load_for_turn", 1)[1]
    assert "base_id" not in call.split("run_turn", 1)[0]
    assert "docker compose up --build" in (root / "README.md").read_text(encoding="utf-8")
