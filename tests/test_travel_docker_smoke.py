"""Docker-aware travel sample guidance for smoke_test_agent."""

from __future__ import annotations

import sys
from pathlib import Path

from zeus_dev_helper_mcp.checklist import load_checklist
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.smoke import smoke_test_agent
from zeus_dev_helper_mcp.travel import (
    detect_docker_install,
    resolve_travel_docker_guidance,
    save_travel_sample_dir,
    travel_golden_path,
    validate_travel_layout,
)


def _cfg(tmp_path: Path) -> HelperConfig:
    return HelperConfig(
        zeus_url="http://localhost:8080",
        default_bucket="travel-sample",
        default_scope="_default",
        state_dir=tmp_path / "state",
    )


def _write_travel_pythonish(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "requirements.txt").write_text("httpx\n", encoding="utf-8")


def test_detect_docker_install_compose_and_readme(tmp_path: Path) -> None:
    root = tmp_path / "demo_travel_sample"
    _write_travel_pythonish(root)
    (root / "README.md").write_text(
        "# Demo\n\n### Docker (recommended)\n\n```bash\ndocker compose up --build\n```\n"
        "Open http://localhost:5050\n",
        encoding="utf-8",
    )
    (root / "docker-compose.yml").write_text(
        "services:\n  app:\n    ports:\n      - \"5050:5000\"\n",
        encoding="utf-8",
    )
    (root / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")

    out = detect_docker_install(root)
    assert out["ok"] is True
    assert out["has_compose"] is True
    assert out["has_dockerfile"] is True
    assert out["readme_signals"] is True
    assert out["recommended"] is True
    assert out["host_port"] == 5050
    assert "docker compose up --build" in out["next_action"]


def test_detect_docker_install_readme_only(tmp_path: Path) -> None:
    root = tmp_path / "demo_travel_sample"
    _write_travel_pythonish(root)
    (root / "README.md").write_text(
        "Run with docker-compose up after copying config.\n",
        encoding="utf-8",
    )
    out = detect_docker_install(root)
    assert out["ok"] is True
    assert out["readme_signals"] is True
    assert out["has_compose"] is False


def test_detect_docker_install_compose_only(tmp_path: Path) -> None:
    root = tmp_path / "demo_travel_sample"
    _write_travel_pythonish(root)
    (root / "README.md").write_text("# no container docs\n", encoding="utf-8")
    (root / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    out = detect_docker_install(root)
    assert out["ok"] is True
    assert out["has_compose"] is True
    assert out["readme_signals"] is False


def test_detect_docker_install_neither(tmp_path: Path) -> None:
    root = tmp_path / "demo_travel_sample"
    _write_travel_pythonish(root)
    (root / "README.md").write_text("# plain pip install\n", encoding="utf-8")
    out = detect_docker_install(root)
    assert out["ok"] is False
    assert out["next_action"] == ""


def test_travel_golden_path_phase5_mentions_docker(tmp_path: Path) -> None:
    root = tmp_path / "demo_travel_sample"
    _write_travel_pythonish(root)
    (root / "README.md").write_text(
        "## Quick Start\n\n### Docker (recommended)\n\ndocker compose up --build\n",
        encoding="utf-8",
    )
    (root / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    cfg = _cfg(tmp_path)
    load_checklist(cfg)
    out = travel_golden_path(cfg, sample_dir=str(root))
    assert out["docker"]["ok"] is True
    phase5 = next(p for p in out["helper_phases"] if p["phase"] == "5")
    assert "docker compose" in phase5["action"]
    assert (cfg.state_dir / "travel_sample.json").is_file()


def test_resolve_uses_persisted_dir(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "travel-sample"
    _write_travel_pythonish(root)
    (root / "README.md").write_text("Docker (recommended)\ndocker compose up\n", encoding="utf-8")
    (root / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
    cfg = _cfg(tmp_path)
    save_travel_sample_dir(cfg, root)
    monkeypatch.delenv("DEMO_TRAVEL_SAMPLE_DIR", raising=False)
    guided = resolve_travel_docker_guidance(cfg)
    assert guided is not None
    assert guided["ok"] is True
    assert guided["local_dir"] == str(root.resolve())


def _block_zeus_client(monkeypatch):
    """Force ImportError for zeus_client whether or not it is installed."""

    class _Block:
        def find_spec(self, fullname, path=None, target=None):
            if fullname == "zeus_client" or fullname.startswith("zeus_client."):
                raise ModuleNotFoundError(fullname)

    for key in list(sys.modules):
        if key == "zeus_client" or key.startswith("zeus_client."):
            monkeypatch.delitem(sys.modules, key, raising=False)

    blocker = _Block()
    meta = list(sys.meta_path)
    meta.insert(0, blocker)
    monkeypatch.setattr(sys, "meta_path", meta)
    return blocker


def test_smoke_test_agent_import_error_prefers_docker(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "demo_travel_sample"
    _write_travel_pythonish(root)
    (root / "README.md").write_text(
        "### Docker (recommended)\n\ndocker compose up --build\nOpen http://localhost:5050\n",
        encoding="utf-8",
    )
    (root / "docker-compose.yml").write_text(
        'services:\n  travel-planner:\n    ports:\n      - "5050:5000"\n',
        encoding="utf-8",
    )
    cfg = _cfg(tmp_path)
    monkeypatch.setenv("DEMO_TRAVEL_SAMPLE_DIR", str(root))
    _block_zeus_client(monkeypatch)
    out = smoke_test_agent(cfg)

    assert out["ok"] is False
    assert out["install_path"] == "docker"
    assert out["sample"] == "travel"
    assert "docker compose up --build" in out["next_action"]
    assert out["docker"]["has_compose"] is True


def test_smoke_test_agent_import_error_falls_back_to_pip(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "demo_travel_sample"
    _write_travel_pythonish(root)
    (root / "README.md").write_text("# no docker here\npip install -e .\n", encoding="utf-8")
    cfg = _cfg(tmp_path)
    monkeypatch.setenv("DEMO_TRAVEL_SAMPLE_DIR", str(root))
    _block_zeus_client(monkeypatch)
    out = smoke_test_agent(cfg)

    assert out["ok"] is False
    assert out.get("install_path") == "pip"
    assert "kotenai-zeus-client" in out["next_action"]
    assert "docker compose" not in out["next_action"]


def test_validate_layout_still_soft_ok_without_makefile(tmp_path: Path) -> None:
    root = tmp_path / "demo_travel_sample"
    _write_travel_pythonish(root)
    (root / "README.md").write_text("# travel\n", encoding="utf-8")
    layout = validate_travel_layout(root)
    assert layout["ok"] is True
    assert "Makefile" in layout["missing"]
