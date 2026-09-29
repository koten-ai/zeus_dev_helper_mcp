"""ZDM-20: website_green checks the running catalog page."""

from __future__ import annotations

import inspect
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.smoke import smoke_test_zeus
from zeus_dev_helper_mcp.website_green import website_green


class _AppHandler(BaseHTTPRequestHandler):
    health_code: ClassVar[int] = 200
    health: ClassVar[dict[str, object]] = {"status": "ok", "sample": "beer"}
    config: ClassVar[dict[str, object]] = {
        "pour_enabled": False,
        "bucket": "beer-sample",
    }
    beers: ClassVar[dict[str, object]] = {
        "items": [{"id": "friar", "name": "Friar's Porter"}],
        "cards": [{"id": "friar", "name": "Friar's Porter"}],
        "range_label": "1–1 shown",
        "entity": "Beer",
        "req_ids": ["req-list"],
        "session_id": "sid-secret",
    }
    page2: ClassVar[dict[str, object]] = {
        "items": [],
        "cards": [],
        "entity": "Beer",
        "req_ids": ["req-page2"],
    }
    search: ClassVar[dict[str, object]] = {
        "items": [],
        "cards": [],
        "req_ids": ["req-search"],
    }
    beers_status: ClassVar[int] = 200
    paths: ClassVar[list[str]] = []

    def do_GET(self) -> None:
        type(self).paths.append(self.path)
        path = self.path.split("?", 1)[0]
        query = self.path.split("?", 1)[1] if "?" in self.path else ""
        if path == "/healthz":
            self._send(type(self).health_code, type(self).health)
            return
        if path == "/api/config":
            self._send(200, type(self).config)
            return
        if path in {"/api/beers", "/api/breweries"}:
            body = type(self).page2 if "offset=" in query else type(self).beers
            self._send(type(self).beers_status, body)
            return
        if path == "/api/search":
            self._send(200, type(self).search)
            return
        if path.endswith("/describe"):
            self._send(200, {"ok": True, "entity_types": ["Beer"]})
            return
        self._send(404, {})

    def _send(self, code: int, body: dict[str, object]) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt: str, *args: object) -> None:
        return


@pytest.fixture
def app_server() -> tuple[str, Path]:
    _AppHandler.health_code = 200
    _AppHandler.health = {"status": "ok", "sample": "beer"}
    _AppHandler.config = {"pour_enabled": False, "bucket": "beer-sample"}
    _AppHandler.beers = {
        "items": [{"id": "friar", "name": "Friar's Porter"}],
        "cards": [{"id": "friar", "name": "Friar's Porter"}],
        "range_label": "1–1 shown",
        "entity": "Beer",
        "req_ids": ["req-list"],
        "session_id": "sid-secret",
    }
    _AppHandler.page2 = {
        "items": [],
        "cards": [],
        "entity": "Beer",
        "req_ids": ["req-page2"],
    }
    _AppHandler.search = {"items": [], "cards": [], "req_ids": ["req-search"]}
    _AppHandler.beers_status = 200
    _AppHandler.paths = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _AppHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])
    try:
        yield f"http://127.0.0.1:{port}", Path()
    finally:
        server.shutdown()
        server.server_close()


def _cfg(tmp_path: Path, *, auth: str = "none") -> HelperConfig:
    return HelperConfig(
        zeus_url="http://lab.example:8080",
        zeus_auth_mode=auth,
        default_bucket="beer-sample",
        default_scope="_default",
        state_dir=tmp_path / "state",
    )


def _tree(tmp_path: Path, port: str, *, api: bool = False) -> Path:
    root = tmp_path / "app"
    root.mkdir()
    (root / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    if api:
        source = "from fastapi import FastAPI\napp = FastAPI()\n@app.post('/turn')\ndef turn():\n    return {}\n"
    else:
        source = "from fastapi import FastAPI\napp = FastAPI()\n"
    (root / "main.py").write_text(source, encoding="utf-8")
    (root / ".env").write_text(
        f"PORT={port}\nZEUS_PASSWORD=local-secret\n", encoding="utf-8"
    )
    return root


def _scope(entity_types: list[str]) -> dict[str, object]:
    return {"ok": True, "entity_types": entity_types, "req_id": "req-scope"}


def test_describe_200_and_empty_list_fails(
    tmp_path: Path,
    app_server: tuple[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, _unused = app_server
    _AppHandler.beers = {
        "items": [],
        "cards": [],
        "range_label": "0 shown",
        "entity": "Beer",
        "req_ids": ["req-list"],
        "password": "local-secret",
    }
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.explain_scope.explain_scope",
        lambda cfg: (_ for _ in ()).throw(AssertionError("explain on an empty list")),
    )
    out = website_green(
        _cfg(tmp_path), target_dir=str(_tree(tmp_path, base.rsplit(":", 1)[1]))
    )
    blob = json.dumps(out)
    assert out["ok"] is False
    assert out["failure_class"] == "list_empty"
    assert out["describe_checked"] is False
    assert out["list_count"] == 0
    assert "smoke_test_agent" not in out["recommended_tools"]
    assert not any("describe" in path for path in _AppHandler.paths)
    assert "local-secret" not in blob
    assert "sid-secret" not in blob


def test_of_zero_label_fails(tmp_path: Path, app_server: tuple[str, Path]) -> None:
    base, _unused = app_server
    _AppHandler.beers = {
        "items": [{"id": "friar", "name": "Friar's Porter"}],
        "cards": [{"id": "friar", "name": "Friar's Porter"}],
        "range_label": "1–1 of 0",
        "entity": "Beer",
    }
    out = website_green(
        _cfg(tmp_path), target_dir=str(_tree(tmp_path, base.rsplit(":", 1)[1]))
    )
    assert out["failure_class"] == "total_null_rendered_as_zero"
    assert out["ok"] is False


def test_repeated_page_ids_fail(tmp_path: Path, app_server: tuple[str, Path]) -> None:
    base, _unused = app_server
    page = {
        "items": [
            {"id": "friar", "name": "Friar's Porter"},
            {"id": "cains", "name": "Cain's IPA"},
        ],
        "cards": [
            {"id": "friar", "name": "Friar's Porter"},
            {"id": "cains", "name": "Cain's IPA"},
        ],
        "range_label": "1–2 shown",
        "entity": "Beer",
        "req_ids": ["req-list"],
    }
    _AppHandler.beers = page
    _AppHandler.page2 = page
    out = website_green(
        _cfg(tmp_path), target_dir=str(_tree(tmp_path, base.rsplit(":", 1)[1]))
    )
    assert out["failure_class"] == "find_offset_ignored"
    assert out["list_count"] == 2


def test_named_list_card_passes_without_search(
    tmp_path: Path,
    app_server: tuple[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, _unused = app_server
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.explain_scope.explain_scope",
        lambda cfg: _scope(["Beer", "Brewery"]),
    )
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.website_green.install_app",
        lambda root: (_ for _ in ()).throw(AssertionError("already up")),
    )
    out = website_green(
        _cfg(tmp_path), target_dir=str(_tree(tmp_path, base.rsplit(":", 1)[1]))
    )
    assert out["ok"] is True
    assert out["list_count"] == 1
    assert out["search_card_count"] == 0
    assert out["search_skipped"] is True
    assert out["pour_enabled"] is False
    assert out["url"] == base
    assert out["req_ids"] == ["req-list", "req-page2", "req-scope"]
    assert "smoke_test_agent" not in out["recommended_tools"]
    assert not any(path.startswith("/api/search") for path in _AppHandler.paths)
    assert "local-secret" not in json.dumps(out)
    assert "Do not call smoke_test_agent." in out["next_action"]


def test_search_named_card_and_diagnosed_empty(
    tmp_path: Path,
    app_server: tuple[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, _unused = app_server
    root = _tree(tmp_path, base.rsplit(":", 1)[1])
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.explain_scope.explain_scope",
        lambda cfg: _scope(["Beer"]),
    )
    _AppHandler.config = {"pour_enabled": True, "bucket": "beer-sample"}
    _AppHandler.search = {
        "items": [{"id": "friar", "name": "Friar's Porter"}],
        "cards": [{"id": "friar", "name": "Friar's Porter"}],
        "req_ids": ["req-search"],
    }
    named = website_green(_cfg(tmp_path), target_dir=str(root))
    assert named["ok"] is True
    assert named["search_card_count"] == 1
    assert named["search_skipped"] is False
    assert "req-search" in named["req_ids"]

    _AppHandler.paths = []
    _AppHandler.search = {
        "items": [],
        "cards": [],
        "empty_state": "fts_doc_key_only",
        "req_ids": ["req-empty"],
    }
    diagnosed = website_green(_cfg(tmp_path), target_dir=str(root))
    assert diagnosed["ok"] is True
    assert diagnosed["search_class"] == "fts_doc_key_only"
    assert diagnosed["search_card_count"] == 0

    _AppHandler.search = {"items": [], "cards": [], "req_ids": ["req-bare"]}
    bare = website_green(_cfg(tmp_path), target_dir=str(root))
    assert bare["ok"] is False
    assert bare["failure_class"] == "search_empty"
    assert "smoke_test_agent" not in bare["recommended_tools"]


def test_entity_outside_the_live_scope_fails(
    tmp_path: Path,
    app_server: tuple[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, _unused = app_server
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.explain_scope.explain_scope",
        lambda cfg: _scope(["Order", "Customer"]),
    )
    out = website_green(
        _cfg(tmp_path), target_dir=str(_tree(tmp_path, base.rsplit(":", 1)[1]))
    )
    assert out["failure_class"] == "entity_not_in_scope"
    assert out["list_count"] == 1


def test_closed_port_installs_and_starts(
    tmp_path: Path,
    app_server: tuple[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, _unused = app_server
    calls = {"install": 0, "start": 0}
    state = {"down": True}

    def health(_base: str) -> str:
        return "down" if state["down"] else "up"

    def install(root: Path) -> dict[str, object]:
        calls["install"] += 1
        assert (root / "requirements.txt").is_file()
        return {"ok": True, "installed": True}

    def start(root: Path, port: int) -> dict[str, object]:
        calls["start"] += 1
        state["down"] = False
        return {"ok": True, "started": True, "pid": 1}

    monkeypatch.setattr("zeus_dev_helper_mcp.website_green._health", health)
    monkeypatch.setattr("zeus_dev_helper_mcp.website_green.install_app", install)
    monkeypatch.setattr("zeus_dev_helper_mcp.website_green.start_app", start)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.explain_scope.explain_scope",
        lambda cfg: _scope(["Beer"]),
    )
    out = website_green(
        _cfg(tmp_path), target_dir=str(_tree(tmp_path, base.rsplit(":", 1)[1]))
    )
    assert calls == {"install": 1, "start": 1}
    assert out["ok"] is True
    assert out["list_count"] == 1


def test_mint_failure_does_not_probe_the_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ZEUS_PASSWORD", "local-secret")

    def mint(cfg: HelperConfig, client: object = None) -> dict[str, object]:
        return {
            "ok": False,
            "failure_class": "auth_failed",
            "stopped": True,
            "next_action": "Fix the login. A describe 200 is not a login.",
            "detail": "POST /v1/beer-sample/_default/auth/session → HTTP 401",
        }

    def probed(*_args: object, **_kwargs: object) -> tuple[int, dict[str, object], str]:
        raise AssertionError("page probe after a failed mint")

    monkeypatch.setattr("zeus_dev_helper_mcp.readiness.mint_scope_session", mint)
    monkeypatch.setattr("zeus_dev_helper_mcp.website_green._get_json", probed)
    out = website_green(_cfg(tmp_path, auth="basic"), target_dir=str(tmp_path))
    blob = json.dumps(out)
    assert out["ok"] is False
    assert out["failure_class"] == "auth_failed"
    assert out["describe_checked"] is False
    assert "local-secret" not in blob
    assert "session_id" not in blob


def test_api_app_health_has_no_catalog_list(
    tmp_path: Path,
    app_server: tuple[str, Path],
) -> None:
    base, _unused = app_server
    _AppHandler.beers_status = 404
    out = website_green(
        _cfg(tmp_path),
        target_dir=str(_tree(tmp_path, base.rsplit(":", 1)[1], api=True)),
    )
    assert out["ok"] is True
    assert out["list_count"] == 0
    assert out["search_skipped"] is True
    assert not any("describe" in path for path in _AppHandler.paths)


def test_missing_directory(tmp_path: Path) -> None:
    out = website_green(_cfg(tmp_path), target_dir=str(tmp_path / "missing"))
    assert out["failure_class"] == "sample_dir_missing"


def test_smoke_test_zeus_still_owns_describe() -> None:
    text = inspect.getsource(smoke_test_zeus)
    page = inspect.getsource(website_green)
    assert "describe" in text
    assert "smoke_test_agent(" not in page
