"""Standalone Docker rewrite for UI travel clones outside the monorepo."""

from __future__ import annotations

from pathlib import Path

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.travel import (
    ensure_travel_sample,
    monorepo_docker_layout_usable,
    needs_standalone_docker_setup,
    prepare_standalone_docker,
)


def _cfg(tmp_path: Path) -> HelperConfig:
    return HelperConfig(state_dir=tmp_path / "state")


def _write_monorepo_travel_packaging(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text(
        "# Demo\n\n### Docker (recommended)\n\ndocker compose up --build\n",
        encoding="utf-8",
    )
    (root / "requirements.txt").write_text("flask==3.1.0\nhttpx==0.28.1\n", encoding="utf-8")
    (root / "LICENSE").write_text("BSD\n", encoding="utf-8")
    (root / "config.example.json").write_text("{}\n", encoding="utf-8")
    (root / "src" / "travel_planner").mkdir(parents=True)
    (root / "src" / "travel_planner" / "__init__.py").write_text("", encoding="utf-8")
    (root / "data" / "chat_requests").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        "[project]\n"
        "name = \"travel-planner\"\n"
        "version = \"0.1.0\"\n"
        "dependencies = [\n"
        '    "flask==3.1.0",\n'
        '    "kotenai-zeus-client @ file:../zeus_client_python",\n'
        "]\n",
        encoding="utf-8",
    )
    (root / "Dockerfile").write_text(
        "FROM python:3.12-slim\n"
        "WORKDIR /app\n"
        "COPY demo_travel_sample/pyproject.toml demo_travel_sample/requirements.txt ./\n"
        "COPY zeus_client_python /opt/zeus_client_python\n"
        "COPY demo_travel_sample/src ./src\n"
        "RUN pip install -e /opt/zeus_client_python && pip install -e .\n",
        encoding="utf-8",
    )
    (root / "docker-compose.yml").write_text(
        "services:\n"
        "  travel-planner:\n"
        "    build:\n"
        "      context: ..\n"
        "      dockerfile: demo_travel_sample/Dockerfile\n"
        "    container_name: travel-planner\n"
        "    ports:\n"
        '      - "5050:5000"\n'
        "    volumes:\n"
        "      - ../zeus_client_python:/opt/zeus_client_python\n",
        encoding="utf-8",
    )
    (root / ".dockerignore").write_text(
        "__pycache__\n.git\ndata\nconfig.json\n",
        encoding="utf-8",
    )


def test_needs_standalone_when_monorepo_sibling_missing(tmp_path: Path) -> None:
    root = tmp_path / "apps" / "my-first-zeus-app"
    _write_monorepo_travel_packaging(root)
    assert monorepo_docker_layout_usable(root) is False
    assert needs_standalone_docker_setup(root) is True


def test_skips_when_monorepo_siblings_present(tmp_path: Path) -> None:
    mono = tmp_path / "koten-ai"
    root = mono / "demo_travel_sample"
    _write_monorepo_travel_packaging(root)
    (mono / "zeus_client_python").mkdir()
    (mono / "zeus_client_python" / "pyproject.toml").write_text("[project]\nname='c'\n", encoding="utf-8")
    assert monorepo_docker_layout_usable(root) is True
    assert needs_standalone_docker_setup(root) is False
    out = prepare_standalone_docker(root)
    assert out["ok"] is True
    assert out["prepared"] is False
    assert out["skipped"] == "monorepo_layout"
    # Upstream packaging left intact
    assert "demo_travel_sample/" in (root / "Dockerfile").read_text(encoding="utf-8")


def test_prepare_rewrites_standalone_packaging(tmp_path: Path) -> None:
    root = tmp_path / "ws" / "BootUI"
    _write_monorepo_travel_packaging(root)
    out = prepare_standalone_docker(root)
    assert out["ok"] is True
    assert out["prepared"] is True
    assert "Dockerfile" in out["files_written"]
    assert "docker-compose.yml" in out["files_written"]
    assert "pyproject.toml" in out["files_written"]
    assert ".dockerignore" in out["files_written"]

    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    assert "demo_travel_sample/" not in dockerfile
    assert "COPY pyproject.toml" in dockerfile
    assert "zeus_client_python" not in dockerfile

    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    assert "context: ." in compose
    assert "dockerfile: Dockerfile" in compose
    assert "demo_travel_sample/Dockerfile" not in compose
    assert "container_name: BootUI" in compose
    assert "host.docker.internal:8080" in compose

    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert "file:../zeus_client_python" not in pyproject
    assert "kotenai-zeus-client>=2.3.0" in pyproject

    dockerignore = (root / ".dockerignore").read_text(encoding="utf-8")
    assert "\ndata\n" not in f"\n{dockerignore}\n"
    assert "data/chats.jsonl" in dockerignore

    # Idempotent second call
    again = prepare_standalone_docker(root)
    assert again["prepared"] is False
    assert again["skipped"] == "already_standalone"


def test_ensure_travel_sample_prepares_docker(tmp_path: Path, monkeypatch) -> None:
    parent = tmp_path / "demos"
    parent.mkdir()
    root = parent / "ui-app"

    def fake_clone(*, dest, **_kwargs):
        dest_p = Path(dest)
        _write_monorepo_travel_packaging(dest_p)
        return {"ok": True, "cloned": True, "dest": str(dest_p)}

    monkeypatch.delenv("DEMO_TRAVEL_SAMPLE_DIR", raising=False)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.travel._find_travel_dir",
        lambda explicit="", cfg=None: None,
    )
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.travel.clone_travel_sample",
        fake_clone,
    )
    cfg = _cfg(tmp_path)
    out = ensure_travel_sample(cfg, project_name="ui-app", parent_dir=str(parent))
    assert out["ok"] is True
    assert out["cloned"] is True
    setup = out.get("docker_setup") or {}
    assert setup.get("prepared") is True
    assert "docker compose" in (out.get("next_action") or "").lower()
    assert "context: ." in (root / "docker-compose.yml").read_text(encoding="utf-8")
