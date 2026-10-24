"""ZDM-43: checklist 4.2 uses the live bootstrap stamp, not a Hub stop."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

from zeus_dev_helper_mcp.beer import save_beer_sample_dir
from zeus_dev_helper_mcp.checklist import (
    load_checklist,
    save_checklist,
    set_item_status,
)
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.contract import bind_contract
from zeus_dev_helper_mcp.explain_scope import explain_scope
from zeus_dev_helper_mcp.walkthrough import enriched_next_step

SECRET = "SECRET_PROMPT_MARKER"
HASH = "md5:5aacbf1d0123456789abcdef01234567"
CONTRACT_ID = "analytics_base5_2"
_SCHEMA = """## SCOPE BRIEF
Beer catalog.

## MINI-SCHEMA
### Beer (fields: 2)
  - name display [display]
  - style text_fts [fts]
## LATER
"""
_TRIMMED = (
    "You are a catalog helper. MINI-SCHEMA is injected at call time. "
    f"{SECRET} stays in this prefix."
)


class _Handler(BaseHTTPRequestHandler):
    bodies: ClassVar[dict[str, bytes]] = {}
    status = 200

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        body = type(self).bodies.get(path, b"{}")
        self.send_response(type(self).status)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Zeus-Req-Id", "req-live-1")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def _chat(content: str, *, contract_hash: str = HASH) -> dict[str, object]:
    return {
        "_format": "zeus.chat_request.v2",
        "messages": [{"role": "system", "content": content}],
        "contract": {"id": CONTRACT_ID, "hash": contract_hash},
        "verbs": [{"name": "find"}],
    }


def _bootstrap(content: str, *, contract_hash: str = HASH) -> bytes:
    return json.dumps({"chat_request": _chat(content, contract_hash=contract_hash)}).encode()


@pytest.fixture
def live_server() -> str:
    _Handler.status = 200
    _Handler.bodies = {
        "/v1/ai/chat_request.json": json.dumps(_chat(_TRIMMED, contract_hash=HASH)).encode(),
        "/v1/ai/bootstrap/scope/beer-sample/_default": _bootstrap(
            _SCHEMA + f"\nfield example {SECRET}\n"
        ),
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


def _cfg(tmp_path: Path, url: str) -> HelperConfig:
    return HelperConfig(
        zeus_url=url,
        default_bucket="beer-sample",
        default_scope="_default",
        default_mode="analytics",
        state_dir=tmp_path / "state",
    )


def _bind_project(cfg: HelperConfig) -> None:
    data = load_checklist(cfg)
    data["meta"] = {"goal": "single-agent", "sample": "beer"}
    save_checklist(cfg, data)


def _app(tmp_path: Path, *, contract_hash: str = "") -> Path:
    root = tmp_path / "beer-explorer"
    root.mkdir()
    (root / "main.py").write_text("print('beer')\n", encoding="utf-8")
    zeus: dict[str, object] = {}
    if contract_hash:
        zeus["scope_contracts"] = {
            "beer-sample/_default": {
                "analytics": {
                    "contract_id": CONTRACT_ID,
                    "contract_hash": contract_hash,
                }
            }
        }
    payload = {
        "target": {"bucket": "beer-sample", "scope": "_default"},
        "settings": {"mode": "analytics"},
        "zeus": zeus,
    }
    (root / "config.json").write_text(json.dumps(payload), encoding="utf-8")
    return root


def _open_4_2(cfg: HelperConfig) -> None:
    for item_id in (
        "0.1",
        "0.2",
        "1.1",
        "1.2",
        "2.1",
        "2.2",
        "2.3",
        "3.1",
        "3.2",
        "4.1",
    ):
        set_item_status(cfg, item_id, "done", evidence="test")


def _item(cfg: HelperConfig, item_id: str) -> dict:
    data = load_checklist(cfg)
    for phase in data["phases"]:
        for item in phase["items"]:
            if item["id"] == item_id:
                return item
    raise AssertionError(item_id)


def test_explain_scope_uses_bootstrap_when_chat_request_is_trimmed(
    tmp_path: Path, live_server: str
) -> None:
    out = explain_scope(_cfg(tmp_path, live_server))
    blob = json.dumps(out)
    assert out["ok"] is True
    assert out["failure_class"] is None
    assert out["schema_source"] == "bootstrap.chat_request"
    assert out["entity_types"] == ["Beer"]
    assert SECRET not in blob
    assert "Hub" not in out["next_action"]


def test_missing_mini_schema_when_bootstrap_also_has_no_heading(
    tmp_path: Path, live_server: str
) -> None:
    _Handler.bodies["/v1/ai/bootstrap/scope/beer-sample/_default"] = _bootstrap(
        f"plain bootstrap {SECRET}"
    )
    out = explain_scope(_cfg(tmp_path, live_server))
    assert out["ok"] is False
    assert out["failure_class"] == "missing_mini_schema"
    assert out["entity_types"] == []
    assert SECRET not in json.dumps(out)


def test_bind_contract_without_path_copies_the_live_hash(
    tmp_path: Path, live_server: str
) -> None:
    cfg = _cfg(tmp_path, live_server)
    app = _app(tmp_path)
    _bind_project(cfg)
    save_beer_sample_dir(cfg, app)
    out = bind_contract(cfg)
    blob = json.dumps(out)
    assert out["ok"] is True
    assert out["pin_source"] == "bootstrap.chat_request.contract"
    assert out["contract_id"] == CONTRACT_ID
    assert out["contract_hash"] == HASH
    pin = out["scope_contracts"]["beer-sample/_default"]["analytics"]
    assert pin["contract_id"] == CONTRACT_ID
    assert pin["contract_hash"] == HASH
    assert out["config_path"] == str(app / "config.json")
    assert "did not compute" in out["note"].lower()
    assert SECRET not in blob
    assert _SCHEMA not in blob
    assert "Workbench" not in out["next_action"]


def test_bind_contract_refuses_a_directory_pointer(tmp_path: Path) -> None:
    pointer = {"chat_request_dir": str(tmp_path / "zeus_chat_request")}
    path = tmp_path / "chat_request.json"
    path.write_text(json.dumps(pointer), encoding="utf-8")
    cfg = _cfg(tmp_path, "")
    from_path = bind_contract(cfg, path=str(path))
    from_text = bind_contract(cfg, json_text=json.dumps(pointer))
    for out in (from_path, from_text):
        assert out["ok"] is False
        assert out["failure_class"] == "contract_required"
        assert out["input_kind"] == "chat_request_dir_pointer"
        assert "Stamp on Hub" not in out["next_action"]
        assert "Workbench" not in out["next_action"]
        assert "bootstrap chat_request.contract" in out["next_action"]
        assert "contract_hash" not in out


def test_bind_contract_still_refuses_placeholder_on_the_live_document(
    tmp_path: Path, live_server: str
) -> None:
    _Handler.bodies["/v1/ai/bootstrap/scope/beer-sample/_default"] = _bootstrap(
        _SCHEMA, contract_hash="md5:TO_BE_FILLED"
    )
    out = bind_contract(_cfg(tmp_path, live_server))
    blob = json.dumps(out)
    assert out["ok"] is False
    assert out["failure_class"] == "contract_hash_invent_forbidden"
    assert "Stamp on Hub" in out["next_action"]
    assert "compute_local" in out["next_action"]
    assert SECRET not in blob
    assert HASH not in blob
    assert _SCHEMA not in blob


def test_bind_contract_still_refuses_compute_local_on_the_live_document(
    tmp_path: Path, live_server: str
) -> None:
    _Handler.bodies["/v1/ai/bootstrap/scope/beer-sample/_default"] = _bootstrap(
        _SCHEMA, contract_hash="compute_local"
    )
    out = bind_contract(_cfg(tmp_path, live_server))
    assert out["ok"] is False
    assert out["failure_class"] == "contract_hash_invent_forbidden"
    assert "compute_local" in out["next_action"]
    assert SECRET not in json.dumps(out)


def test_bind_contract_unwraps_a_bootstrap_envelope(tmp_path: Path) -> None:
    envelope = {"chat_request": _chat(_SCHEMA), "scope_url": "http://127.0.0.1:8080"}
    out = bind_contract(
        _cfg(tmp_path, ""),
        json_text=json.dumps(envelope),
    )
    assert out["ok"] is True
    assert out["contract_hash"] == HASH
    assert SECRET not in json.dumps(out)
    assert _SCHEMA not in json.dumps(out)


def test_next_step_names_the_live_pin_source(tmp_path: Path, live_server: str) -> None:
    cfg = _cfg(tmp_path, live_server)
    app = _app(tmp_path)
    _bind_project(cfg)
    save_beer_sample_dir(cfg, app)
    _open_4_2(cfg)
    out = enriched_next_step(cfg)
    blob = json.dumps(out)
    assert out["item"]["id"] == "4.2"
    assert out["pin_source"] == "bootstrap.chat_request.contract"
    assert out["config_path"] == str(app / "config.json")
    assert str(app / "config.json") in out["note"]
    assert "bootstrap chat_request.contract" in out["note"]
    assert "Administrator" not in out["ops_note"]
    assert "Workbench" not in out["ops_note"]
    assert "No Hub stamp" in out["ops_note"]
    assert out.get("pour_enabled") is not True
    assert SECRET not in blob
    assert HASH not in blob
    assert not (cfg.state_dir / "website_green.json").exists()


def test_next_step_admin_note_when_the_live_hash_is_missing(
    tmp_path: Path, live_server: str
) -> None:
    _Handler.bodies["/v1/ai/bootstrap/scope/beer-sample/_default"] = _bootstrap(
        _SCHEMA, contract_hash="md5:TO_BE_FILLED"
    )
    cfg = _cfg(tmp_path, live_server)
    app = _app(tmp_path)
    _bind_project(cfg)
    save_beer_sample_dir(cfg, app)
    _open_4_2(cfg)
    out = enriched_next_step(cfg)
    assert out["item"]["id"] == "4.2"
    assert "Administrator" in out["ops_note"]
    assert str(app / "config.json") in out["note"]
    assert "bootstrap chat_request.contract" in out["note"]
    assert SECRET not in json.dumps(out)
    assert HASH not in json.dumps(out)


def test_next_step_marks_4_2_done_after_the_pin(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, "")
    app = _app(tmp_path, contract_hash=HASH)
    _bind_project(cfg)
    save_beer_sample_dir(cfg, app)
    out = enriched_next_step(cfg)
    pin = _item(cfg, "4.2")
    assert pin["status"] == "done"
    assert pin["evidence"] == "scope_contracts pinned"
    assert out.get("pour_enabled") is not True
    assert HASH not in json.dumps(pin)
    assert not (cfg.state_dir / "website_green.json").exists()


def test_done_4_1_stays_when_the_catalog_directory_is_removed(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, "")
    app = _app(tmp_path)
    catalog = app / "data" / "chat_requests" / "beer-sample__default"
    catalog.mkdir(parents=True)
    (catalog / "chat_request_analytics_v2.json").write_text("{}\n", encoding="utf-8")
    (app / "config.json").write_text(
        json.dumps(
            {
                "chat_requests_dir": "data/chat_requests",
                "target": {"bucket": "beer-sample", "scope": "_default"},
                "settings": {"mode": "analytics"},
                "zeus": {},
            }
        ),
        encoding="utf-8",
    )
    _bind_project(cfg)
    save_beer_sample_dir(cfg, app)
    set_item_status(cfg, "4.1", "done", evidence="scope catalog on disk")
    for path in sorted(catalog.rglob("*"), reverse=True):
        path.unlink()
    catalog.rmdir()
    enriched_next_step(cfg)
    row = _item(cfg, "4.1")
    assert row["status"] == "done"
    assert row["evidence"] == "scope catalog on disk"
    assert _item(cfg, "4.2")["status"] == "todo"
