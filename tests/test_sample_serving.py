"""ZDM-22: a live catalog is already serving, or the recorded directory is gone."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from zeus_dev_helper_mcp.beer import write_beer_sample
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.scaffold import use_sample


class _CatalogHandler(BaseHTTPRequestHandler):
    health = b'{"status":"ok","sample":"beer"}'
    config = b"{}"

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            body = type(self).health
            code = 200
        elif path == "/api/config":
            body = type(self).config
            code = 200
        else:
            body = b""
            code = 404
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        return


@pytest.fixture
def catalog_server() -> tuple[str, ThreadingHTTPServer]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _CatalogHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = str(server.server_address[1])
    try:
        yield port, server
    finally:
        server.shutdown()
        server.server_close()


def _cfg(tmp_path: Path) -> HelperConfig:
    return HelperConfig(
        zeus_url="http://lab.example:8080",
        default_bucket="beer-sample",
        default_scope="_default",
        state_dir=tmp_path / "state",
    )


def _pin_port(root: Path, port: str) -> None:
    path = root / ".env"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    lines = [line for line in text.splitlines() if not line.startswith("PORT=")]
    lines.append(f"PORT={port}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _set_live(config: dict[str, object], health: dict[str, object] | None = None) -> None:
    _CatalogHandler.config = json.dumps(config).encode()
    _CatalogHandler.health = json.dumps(health or {"status": "ok", "sample": "beer"}).encode()


def test_already_serving_skips_install_instructions(
    tmp_path: Path,
    catalog_server: tuple[str, ThreadingHTTPServer],
) -> None:
    port, _server = catalog_server
    _set_live(
        {
            "zeus_url": "http://192.168.0.219:8080",
            "zeus_version": "0.9.0",
            "bucket": "beer-sample",
        }
    )
    cfg = _cfg(tmp_path)
    root = tmp_path / "demo_beer_sample"
    first = write_beer_sample(cfg, root)
    assert first["ok"] is True
    _pin_port(root, port)
    main_before = (root / "main.py").read_text(encoding="utf-8")
    out = use_sample(cfg, sample="beer", sample_dir=str(root))
    assert out["ok"] is True
    assert out["already_serving"] is True
    assert out["written"] is False
    assert out["url"] == f"http://127.0.0.1:{port}/"
    assert out["zeus_url"] == "http://192.168.0.219:8080"
    assert out["version"] == "0.9.0"
    run = str(out.get("run") or "")
    action = str(out.get("next_action") or "")
    assert "pip install" not in run
    assert "cp .env.example .env" not in run
    assert "pip install" not in action
    assert "cp .env.example .env" not in action
    assert (root / "main.py").read_text(encoding="utf-8") == main_before


def test_open_port_with_other_bucket_is_port_in_use(
    tmp_path: Path,
    catalog_server: tuple[str, ThreadingHTTPServer],
) -> None:
    port, _server = catalog_server
    _set_live(
        {
            "zeus_url": "http://192.168.0.219:8080",
            "zeus_version": "0.9.0",
            "bucket": "yelp-data",
        }
    )
    cfg = _cfg(tmp_path)
    root = tmp_path / "demo_beer_sample"
    assert write_beer_sample(cfg, root)["ok"] is True
    _pin_port(root, port)
    marker = root / "main.py"
    before = marker.read_text(encoding="utf-8")
    out = use_sample(cfg, sample="beer", sample_dir=str(root))
    assert out["ok"] is False
    assert out["failure_class"] == "port_in_use"
    assert out["written"] is False
    assert out.get("already_serving") is False
    blob = json.dumps(out)
    assert "pip install" not in blob
    assert "cp .env.example .env" not in blob
    assert "Do not start another process" in out["next_action"]
    assert marker.read_text(encoding="utf-8") == before
    assert not (tmp_path / "demo_beer_sample-2").exists()


def test_closed_port_does_not_claim_already_serving(tmp_path: Path) -> None:
    import socket

    cfg = _cfg(tmp_path)
    root = tmp_path / "demo_beer_sample"
    assert write_beer_sample(cfg, root)["ok"] is True
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        closed = str(sock.getsockname()[1])
    _pin_port(root, closed)
    out = use_sample(cfg, sample="beer", sample_dir=str(root))
    assert out["ok"] is True
    assert out.get("already_serving") is not True
    assert out.get("failure_class") != "port_in_use"


def test_missing_env_dir_is_sample_dir_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "gone"
    monkeypatch.setenv("DEMO_BEER_SAMPLE_DIR", str(missing))
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.server.list_modes",
        lambda _cfg: {"modes": []},
    )
    from zeus_dev_helper_mcp.server import doctor
    from zeus_dev_helper_mcp.walkthrough import enriched_next_step

    health = doctor("health")
    assert health["ok"] is False
    assert health["failure_class"] == "sample_dir_missing"
    assert health["sample_dir"] == str(missing)
    assert health["recommended_tools"] == ["use_sample"]
    nxt = enriched_next_step(_cfg(tmp_path))
    assert nxt["failure_class"] == "sample_dir_missing"
    assert nxt["recommended_tools"] == ["use_sample"]


def test_missing_state_file_is_sample_dir_missing(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    missing = tmp_path / "not-a-dir"
    missing.write_text("file\n", encoding="utf-8")
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / "beer_sample.json").write_text(
        json.dumps({"beer_sample_dir": str(missing)}) + "\n",
        encoding="utf-8",
    )
    from zeus_dev_helper_mcp.walkthrough import enriched_next_step

    nxt = enriched_next_step(cfg)
    assert nxt["failure_class"] == "sample_dir_missing"
    assert nxt["sample_dir"] == str(missing)
    assert nxt["recommended_tools"] == ["use_sample"]


def test_missing_pointer_does_not_pick_a_sibling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    missing = tmp_path / "recorded-gone"
    monkeypatch.setenv("DEMO_BEER_SAMPLE_DIR", str(missing))
    cfg = _cfg(tmp_path)
    out = use_sample(
        cfg,
        sample="beer",
        parent_dir=str(tmp_path),
    )
    assert out["ok"] is True
    assert out.get("failure_class") != "sample_dir_missing"
    assert Path(out["local_dir"]).name == "demo_beer_sample"
    assert not (tmp_path / "demo_beer_sample-2").exists()


def test_serving_recorded_dir_does_not_relocate(
    tmp_path: Path,
    catalog_server: tuple[str, ThreadingHTTPServer],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port, _server = catalog_server
    _set_live({"zeus_url": "http://lab.example:8080", "zeus_version": "0.9.0", "bucket": "beer-sample"})
    cfg = _cfg(tmp_path)
    recorded = tmp_path / "serving"
    assert write_beer_sample(cfg, recorded)["ok"] is True
    _pin_port(recorded, port)
    monkeypatch.setenv("DEMO_BEER_SAMPLE_DIR", str(recorded))
    foreign = tmp_path / "demo_beer_sample"
    foreign.mkdir()
    (foreign / "app.py").write_text("flask\n", encoding="utf-8")
    out = use_sample(cfg, sample="beer", parent_dir=str(tmp_path))
    assert out["ok"] is True
    assert out["already_serving"] is True
    assert Path(out["local_dir"]) == recorded.resolve()
    assert not (tmp_path / "demo_beer_sample-2").exists()
    assert (foreign / "app.py").read_text(encoding="utf-8") == "flask\n"
