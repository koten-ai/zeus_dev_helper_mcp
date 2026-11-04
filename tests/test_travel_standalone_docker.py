"""Travel create leaves the checkout's Docker files and client pin alone."""

from __future__ import annotations

from pathlib import Path

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.travel import ensure_travel_sample


def _cfg(tmp_path: Path) -> HelperConfig:
    return HelperConfig(state_dir=tmp_path / "state")


def _write_monorepo_travel_packaging(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text(
        "# Demo\n\n### Docker (recommended)\n\ndocker compose up --build\n",
        encoding="utf-8",
    )
    (root / "requirements.txt").write_text(
        "flask==3.1.0\nhttpx==0.28.1\n",
        encoding="utf-8",
    )
    (root / "LICENSE").write_text("BSD\n", encoding="utf-8")
    (root / "config.example.json").write_text("{}\n", encoding="utf-8")
    (root / "src" / "travel_planner").mkdir(parents=True)
    (root / "src" / "travel_planner" / "__init__.py").write_text("", encoding="utf-8")
    (root / "data" / "chat_requests").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        "[project]\n"
        'name = "travel-planner"\n'
        'version = "0.1.0"\n'
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


def test_ensure_travel_sample_leaves_docker_files(tmp_path: Path, monkeypatch) -> None:
    parent = tmp_path / "demos"
    parent.mkdir()
    root = parent / "ui-app"

    def fake_clone(*, dest, **_kwargs):
        dest_p = Path(dest)
        _write_monorepo_travel_packaging(dest_p)
        return {"ok": True, "cloned": True, "dest": str(dest_p)}

    monkeypatch.delenv("DEMO_TRAVEL_SAMPLE_DIR", raising=False)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.travel.clone_travel_sample",
        fake_clone,
    )
    cfg = _cfg(tmp_path)
    out = ensure_travel_sample(cfg, project_name="ui-app", parent_dir=str(parent))
    assert out["ok"] is True
    assert out["cloned"] is True
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert "demo_travel_sample/" in dockerfile
    assert "context: .." in (root / "docker-compose.yml").read_text(encoding="utf-8")
    assert "file:../zeus_client_python" in pyproject
    blob = __import__("json").dumps(out)
    assert ">=2.4.0,<2.5" not in blob
    assert "llm_provider.api_key" not in blob
    assert out.get("docker_setup") in (None, {})
