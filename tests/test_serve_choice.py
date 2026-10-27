"""Python or Docker is a user choice when both packaging files exist."""

from __future__ import annotations

import json
from pathlib import Path

from zeus_dev_helper_mcp.beer import write_beer_sample
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.serve_choice import annotate_serve_choice
from zeus_dev_helper_mcp.travel import travel_golden_path
from zeus_dev_helper_mcp.website_green import website_green


def _cfg(tmp_path: Path) -> HelperConfig:
    return HelperConfig(
        zeus_url="",
        default_bucket="beer-sample",
        default_scope="_default",
        state_dir=tmp_path / "state",
    )


def _compose(root: Path, published: str = "8090:8090") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
    (root / "docker-compose.yml").write_text(
        "services:\n"
        "  app:\n"
        "    ports:\n"
        f'      - "{published}"\n'
        "    environment:\n"
        '      HOST: "0.0.0.0"\n'
        '      ZEUS_URL: "http://host.docker.internal:8080"\n'
        "    env_file:\n"
        "      - .env\n"
        "    volumes:\n"
        "      - ./data:/app/data\n",
        encoding="utf-8",
    )


def test_missing_compose_keeps_the_python_command(tmp_path: Path) -> None:
    root = tmp_path / "app"
    root.mkdir()
    (root / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
    result = {
        "ok": True,
        "run": "python main.py",
        "next_action": "Start with python main.py.",
    }
    out = annotate_serve_choice(result, root, cfg=_cfg(tmp_path))
    assert out.get("serve_choice_required") is None
    assert out["run"] == "python main.py"
    assert "python main.py" in out["next_action"]


def test_written_beer_app_asks_before_starting(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    out = write_beer_sample(cfg, tmp_path / "demo_beer_sample")
    assert out["ok"] is True
    assert out["serve_choice_required"] is True
    assert out["run"] == ""
    action = out["next_action"]
    assert "Ask the user whether to serve" in action
    assert "python main.py" not in action
    assert "docker compose up --build" not in action
    assert "Do not clone demo_travel_sample." in action
    options = {item["id"]: item for item in out["serve_options"]}
    assert "python main.py" in options["python"]["run"]
    assert "docker compose up --build" in options["docker"]["run"]
    assert "host.docker.internal:8080" in options["docker"]["notes"]
    assert "The helper does not run Docker." in options["docker"]["notes"]
    assert options["python"]["url"] == "http://127.0.0.1:8090/"
    assert options["docker"]["url"] == "http://127.0.0.1:8090/"


def test_serve_with_docker_records_one_command(tmp_path: Path) -> None:
    import socket

    cfg = _cfg(tmp_path)
    root = tmp_path / "demo_beer_sample"
    assert write_beer_sample(cfg, root)["ok"] is True
    # A live app on 8090 is already_serving and returns before the choice.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        closed = sock.getsockname()[1]
    env_path = root / ".env"
    lines = [
        line
        for line in env_path.read_text(encoding="utf-8").splitlines()
        if not line.startswith("PORT=")
    ]
    lines.append(f"PORT={closed}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    chosen = write_beer_sample(cfg, root, serve_with="docker")
    assert chosen["ok"] is True
    assert chosen["serve_choice_required"] is False
    assert chosen["serve_with"] == "docker"
    assert chosen["run"].endswith("docker compose up --build")
    assert "The user chose Docker." in chosen["next_action"]
    assert "python main.py" not in chosen["next_action"]
    saved = json.loads(
        (cfg.state_dir / "serve_choice.json").read_text(encoding="utf-8")
    )
    assert saved["choices"][str(root.resolve())] == "docker"
    blob = json.dumps(chosen)
    assert "password" not in blob.lower() or "ZEUS_PASSWORD" in blob


def test_already_serving_does_not_ask(tmp_path: Path) -> None:
    root = tmp_path / "app"
    _compose(root)
    out = annotate_serve_choice(
        {
            "ok": True,
            "already_serving": True,
            "run": "http://127.0.0.1:8090/",
            "next_action": "Leave the process running.",
        },
        root,
        cfg=_cfg(tmp_path),
    )
    assert "serve_options" not in out
    assert out["next_action"] == "Leave the process running."


def test_travel_with_both_files_asks(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_TRAVEL_SAMPLE_DIR", str(tmp_path / "unused"))
    root = tmp_path / "demo_travel_sample"
    root.mkdir()
    (root / "README.md").write_text(
        "### Docker (recommended)\n\ndocker compose up --build\n",
        encoding="utf-8",
    )
    (root / "requirements.txt").write_text("flask\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        "[project]\nname='travel'\n[project.scripts]\n"
        'travel-planner = "travel_planner.__main__:main"\n',
        encoding="utf-8",
    )
    _compose(root, "5050:5000")
    cfg = _cfg(tmp_path)
    out = travel_golden_path(cfg, sample_dir=str(root))
    assert out["ok"] is True
    assert out["serve_choice_required"] is True
    assert out["run"] == ""
    assert "Ask the user whether to serve" in out["next_action"]
    assert "docker compose up --build" not in out["next_action"]
    assert "Choose Python or Docker" in out["docker"]["next_action"]
    options = {item["id"]: item for item in out["serve_options"]}
    assert "python -m travel_planner" in options["python"]["run"]
    assert options["python"]["url"] == "http://127.0.0.1:5000/"
    assert options["docker"]["url"] == "http://127.0.0.1:5050/"
    phase5 = next(item for item in out["helper_phases"] if item["phase"] == "5")
    assert "Ask the user" in phase5["action"]
    assert "docker compose up --build" in phase5["action"]


def test_travel_compose_without_dockerfile_stays_on_docker_docs(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DEMO_TRAVEL_SAMPLE_DIR", str(tmp_path / "unused"))
    root = tmp_path / "demo_travel_sample"
    root.mkdir()
    (root / "README.md").write_text(
        "## Quick Start\n\n### Docker (recommended)\n\ndocker compose up --build\n",
        encoding="utf-8",
    )
    (root / "requirements.txt").write_text("flask\n", encoding="utf-8")
    (root / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    out = travel_golden_path(_cfg(tmp_path), sample_dir=str(root))
    assert out.get("serve_choice_required") is None
    assert "docker compose up --build" in out["next_action"]


def _beerish(tmp_path: Path) -> Path:
    root = tmp_path / "demo_beer_sample"
    _compose(root)
    (root / "main.py").write_text("print('beer')\n", encoding="utf-8")
    (root / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    (root / ".env").write_text("PORT=8090\n", encoding="utf-8")
    return root


def test_website_green_asks_and_does_not_start(tmp_path: Path, monkeypatch) -> None:
    root = _beerish(tmp_path)

    def fail_install(_root: Path) -> dict[str, object]:
        raise AssertionError("pip ran before the user chose")

    def fail_start(_root: Path, _port: int) -> dict[str, object]:
        raise AssertionError("python started before the user chose")

    monkeypatch.setattr(
        "zeus_dev_helper_mcp.website_green._probe_health",
        lambda *_args, **_kwargs: "down",
    )
    monkeypatch.setattr("zeus_dev_helper_mcp.website_green.install_app", fail_install)
    monkeypatch.setattr("zeus_dev_helper_mcp.website_green.start_app", fail_start)
    out = website_green(_cfg(tmp_path), target_dir=str(root))
    assert out["ok"] is False
    assert out["failure_class"] == "serve_choice_required"
    assert out["run"] == ""
    assert "Ask the user whether to serve" in out["next_action"]
    assert out["recommended_tools"] == []


def test_website_green_docker_does_not_start_python(
    tmp_path: Path, monkeypatch
) -> None:
    root = _beerish(tmp_path)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.website_green._probe_health",
        lambda *_args, **_kwargs: "down",
    )
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.website_green.start_app",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("python start")),
    )
    out = website_green(_cfg(tmp_path), target_dir=str(root), serve_with="docker")
    assert out["failure_class"] == "docker_not_started"
    assert "docker compose up --build" in out["next_action"]
    assert "The helper does not run Docker." in out["next_action"]
    assert out["serve_with"] == "docker"


def test_website_green_python_starts_after_the_choice(
    tmp_path: Path, monkeypatch
) -> None:
    root = _beerish(tmp_path)
    started = {"yes": False}

    def install(_root: Path) -> dict[str, bool]:
        return {"ok": True, "installed": True}

    def start(_root: Path, port: int) -> dict[str, object]:
        assert port == 8090
        started["yes"] = True
        return {"ok": True, "started": True, "pid": 4}

    def probe(_base: str, yelp: bool = False) -> str:
        del yelp
        return "up" if started["yes"] else "down"

    def get_json(url: str) -> tuple[int, dict[str, object], str]:
        if url.endswith("/api/config"):
            return 200, {"pour_enabled": False, "bucket": "beer-sample"}, ""
        if "offset=" in url:
            return 200, {"items": [], "cards": [], "entity": "Beer"}, ""
        if "/api/beers" in url:
            return (
                200,
                {
                    "items": [{"name": "Friar's Porter"}],
                    "cards": [{"name": "Friar's Porter"}],
                    "entity": "Beer",
                },
                "",
            )
        return 404, {}, ""

    monkeypatch.setattr("zeus_dev_helper_mcp.website_green.install_app", install)
    monkeypatch.setattr("zeus_dev_helper_mcp.website_green.start_app", start)
    monkeypatch.setattr("zeus_dev_helper_mcp.website_green._probe_health", probe)
    monkeypatch.setattr("zeus_dev_helper_mcp.website_green._get_json", get_json)
    out = website_green(_cfg(tmp_path), target_dir=str(root), serve_with="python")
    assert started["yes"] is True
    assert out["ok"] is True
    assert out["list_count"] == 1


def test_stored_docker_choice_skips_python_on_the_next_check(
    tmp_path: Path, monkeypatch
) -> None:
    root = _beerish(tmp_path)
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.website_green._probe_health",
        lambda *_args, **_kwargs: "down",
    )
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.website_green.start_app",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("python start")),
    )
    first = website_green(cfg, target_dir=str(root), serve_with="docker")
    assert first["failure_class"] == "docker_not_started"
    second = website_green(cfg, target_dir=str(root))
    assert second["failure_class"] == "docker_not_started"
    assert "python main.py" not in second["next_action"]


def test_listening_app_is_checked_without_asking(tmp_path: Path, monkeypatch) -> None:
    root = _beerish(tmp_path)

    def fail_start(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("started a second process")

    def get_json(url: str) -> tuple[int, dict[str, object], str]:
        if url.endswith("/api/config"):
            return 200, {"pour_enabled": False, "bucket": "beer-sample"}, ""
        if "offset=" in url:
            return 200, {"items": [], "cards": []}, ""
        if "/api/beers" in url:
            return 200, {"cards": [{"name": "Friar's Porter"}], "entity": "Beer"}, ""
        return 404, {}, ""

    monkeypatch.setattr(
        "zeus_dev_helper_mcp.website_green._probe_health",
        lambda *_args, **_kwargs: "up",
    )
    monkeypatch.setattr("zeus_dev_helper_mcp.website_green.start_app", fail_start)
    monkeypatch.setattr("zeus_dev_helper_mcp.website_green._get_json", get_json)
    out = website_green(_cfg(tmp_path), target_dir=str(root))
    assert out["ok"] is True
    assert "Ask the user whether to serve" not in out["next_action"]


def test_bad_serve_with_does_not_start(tmp_path: Path, monkeypatch) -> None:
    root = _beerish(tmp_path)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.website_green._probe_health",
        lambda *_args, **_kwargs: "down",
    )
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.website_green.start_app",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("python start")),
    )
    out = website_green(_cfg(tmp_path), target_dir=str(root), serve_with="kubernetes")
    assert out["failure_class"] == "serve_choice_unavailable"
    assert "python or docker" in out["next_action"]
