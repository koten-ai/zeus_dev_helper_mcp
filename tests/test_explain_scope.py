"""ZDM-14: live stamp summary and the generic catalog page."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.explain_scope import (
    STAMP_NOTE,
    parse_mini_schema,
    render_catalog_page,
    summarize_entities,
)
from zeus_dev_helper_mcp.explain_scope import (
    explain_scope as explain_scope_impl,
)
from zeus_dev_helper_mcp.scaffold import use_sample
from zeus_dev_helper_mcp.toolsets import (
    CORE_CAP,
    DEFAULT_CORE_TOOLS,
    default_core_count,
)

SECRET = "SECRET_PROMPT_MARKER"
INVENTED = "InventedEntity"

_BRIEF = f"""You are a catalog helper. {SECRET} stays in the prompt.

## MINI-SCHEMA
### Order (fields: 3)
  - title display [display]
  - notes text_fts [fts]
  - customer_id entity_fk [gsi] fk_to=Customer
### Customer (fields: 2)
  - title display [none]
  - city text_fts [fts] ex: {SECRET}
### Widget (fields: 2)
  - link_id entity_fk [gsi] via=Other
  - status display [none] -- note here
## LATER
ignore this
"""


class _StampHandler(BaseHTTPRequestHandler):
    status = 200
    body = b"{}"
    req_id = "req-stamp-1"

    def do_GET(self) -> None:
        body = type(self).body
        self.send_response(type(self).status)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Zeus-Req-Id", type(self).req_id)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def _stamp_doc(content: str, *, system_prompt: str = "") -> bytes:
    doc: dict[str, object] = {
        "messages": [{"role": "system", "content": content}],
        "verbs": [{"name": "find"}],
    }
    if system_prompt:
        doc["instructions"] = {"system_prompt": system_prompt}
    return json.dumps(doc).encode()


@pytest.fixture
def stamp_server(monkeypatch: pytest.MonkeyPatch) -> str:
    _StampHandler.status = 200
    _StampHandler.body = _stamp_doc(_BRIEF)
    _StampHandler.req_id = "req-stamp-1"
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StampHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])
    monkeypatch.delenv("ZEUS_PASSWORD", raising=False)
    monkeypatch.delenv("ZEUS_USERNAME", raising=False)
    monkeypatch.delenv("ZEUS_USER", raising=False)
    monkeypatch.delenv("ZEUS_BEARER_TOKEN", raising=False)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


def _cfg(tmp_path: Path, url: str, *, bucket: str = "orders") -> HelperConfig:
    return HelperConfig(
        zeus_url=url,
        default_bucket=bucket,
        default_scope="_default",
        default_mode="analytics",
        state_dir=tmp_path / "state",
    )


def _summary() -> dict[str, object]:
    parsed = parse_mini_schema(_BRIEF)
    rows = summarize_entities(parsed)
    return {
        "ok": True,
        "bucket": "orders",
        "scope": "_default",
        "zeus_url": "http://lab.example:8080",
        "entity_types": [row["name"] for row in rows],
        "entities": rows,
        "verbs": {"list": "find", "detail": "get", "search": "search"},
        "req_id": "req-stamp-1",
        "failure_class": None,
    }


def test_parser_keeps_display_text_and_fk_names() -> None:
    parsed = parse_mini_schema(_BRIEF)
    rows = {row["name"]: row for row in summarize_entities(parsed)}
    assert rows["Order"]["display_fields"] == ["title"]
    assert rows["Order"]["text_search_fields"] == ["notes"]
    assert rows["Order"]["fk_fields"] == ["customer_id"]
    assert rows["Customer"]["display_fields"] == ["title"]
    assert rows["Customer"]["text_search_fields"] == ["city"]
    assert rows["Widget"]["fk_fields"] == ["link_id"]
    assert rows["Widget"]["display_fields"] == ["status"]
    blob = json.dumps(rows)
    assert SECRET not in blob
    assert "note here" not in blob


def test_rendered_page_uses_display_fields_only() -> None:
    page = render_catalog_page(_summary())
    assert 'data-catalog="generic"' in page
    assert 'data-entity="Order"' in page
    assert 'data-entity="Customer"' in page
    assert 'data-field="title"' in page
    assert "list find · detail get · search search" in page
    assert "ABV" not in page
    assert "on tap" not in page
    assert SECRET not in page


def test_explain_scope_omits_prompt_and_secrets(
    tmp_path: Path,
    stamp_server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ZEUS_USERNAME", "alice")
    monkeypatch.setenv("ZEUS_PASSWORD", "p@ss-word")
    cfg = _cfg(tmp_path, stamp_server.replace("http://", "http://user:s3cret@", 1))
    cfg.zeus_auth_mode = "basic"
    out = explain_scope_impl(cfg)
    blob = json.dumps(out)
    assert out["ok"] is True
    assert out["failure_class"] is None
    assert out["entity_types"] == ["Order", "Customer", "Widget"]
    assert out["verbs"] == {"list": "find", "detail": "get", "search": "search"}
    assert out["req_id"] == "req-stamp-1"
    assert out["zeus_url"] == stamp_server
    assert out["note"] == STAMP_NOTE
    assert out["result_shapes"]["contract"] == "live V2"
    assert "template only" in out["note"]
    assert SECRET not in blob
    assert "s3cret" not in blob
    assert "p@ss-word" not in blob
    assert "alice" not in blob


def test_explain_scope_falls_back_to_system_prompt(
    tmp_path: Path,
    stamp_server: str,
) -> None:
    _StampHandler.body = _stamp_doc("no schema in the message", system_prompt=_BRIEF)
    out = explain_scope_impl(_cfg(tmp_path, stamp_server))
    assert out["ok"] is True
    assert out["entity_types"][0] == "Order"


def test_stamp_http_500_invents_no_entities(tmp_path: Path, stamp_server: str) -> None:
    _StampHandler.status = 500
    _StampHandler.body = _stamp_doc(
        f"### {INVENTED} (fields: 1)\n  - name display [display]"
    )
    out = explain_scope_impl(_cfg(tmp_path, stamp_server))
    blob = json.dumps(out)
    assert out["ok"] is False
    assert out["failure_class"] == "stamp_fetch_failed"
    assert out["entity_types"] == []
    assert out["entities"] == []
    assert INVENTED not in blob
    assert out["result_shapes"]["search"]


def test_stamp_401_is_auth_failed(tmp_path: Path, stamp_server: str) -> None:
    _StampHandler.status = 401
    _StampHandler.body = _stamp_doc(
        f"### {INVENTED} (fields: 1)\n  - name display [display]"
    )
    out = explain_scope_impl(_cfg(tmp_path, stamp_server))
    assert out["failure_class"] == "auth_failed"
    assert out["entity_types"] == []
    assert out["req_id"] == "req-stamp-1"
    assert INVENTED not in json.dumps(out)


def test_missing_url_and_hub_do_not_invent_entities(tmp_path: Path) -> None:
    missing = explain_scope_impl(_cfg(tmp_path, ""))
    assert missing["failure_class"] == "zeus_url_missing"
    assert missing["entity_types"] == []
    hub = explain_scope_impl(_cfg(tmp_path, "http://127.0.0.1:9091"))
    assert hub["failure_class"] == "wrong_port_hub_vs_public"
    assert hub["entity_types"] == []


def test_closed_port_hides_url_userinfo(tmp_path: Path) -> None:
    out = explain_scope_impl(_cfg(tmp_path, "http://user:s3cret@127.0.0.1:1"))
    assert out["failure_class"] == "stamp_fetch_failed"
    assert out["entity_types"] == []
    assert "s3cret" not in json.dumps(out)


def test_missing_mini_schema(tmp_path: Path, stamp_server: str) -> None:
    _StampHandler.body = _stamp_doc(f"plain prompt {SECRET}")
    out = explain_scope_impl(_cfg(tmp_path, stamp_server))
    assert out["failure_class"] == "missing_mini_schema"
    assert out["entity_types"] == []
    assert SECRET not in json.dumps(out)


def test_use_sample_catalog_writes_generic_page(
    tmp_path: Path,
    stamp_server: str,
) -> None:
    out = use_sample(
        _cfg(tmp_path, stamp_server),
        sample="catalog",
        parent_dir=str(tmp_path),
    )
    assert out["ok"] is True
    assert out["catalog_kind"] == "generic"
    assert out["written"] is True
    root = Path(out["local_dir"])
    assert root.name == "demo_catalog_sample"
    page = (root / "static" / "index.html").read_text(encoding="utf-8")
    assert "Order" in page and "Customer" in page
    assert 'data-field="title"' in page
    assert "ABV" not in page
    assert "on tap" not in page
    assert SECRET not in page
    main = (root / "main.py").read_text(encoding="utf-8")
    compile(main, str(root / "main.py"), "exec")
    assert '"sample": "catalog"' in main
    assert "8091" in out["run"]
    meta = json.loads((root / "sample_meta.json").read_text(encoding="utf-8"))
    assert meta["sample"] == "catalog"
    assert meta["entity_types"] == ["Order", "Customer", "Widget"]
    assert SECRET not in json.dumps(out)
    assert out["result_shapes"]["contract"] == "live V2"


def test_use_sample_generic_alias_matches_catalog(
    tmp_path: Path,
    stamp_server: str,
) -> None:
    out = use_sample(
        _cfg(tmp_path, stamp_server),
        sample="generic",
        project_name="orders-ui",
        parent_dir=str(tmp_path),
    )
    assert out["ok"] is True
    assert Path(out["local_dir"]).name == "orders-ui"
    assert "Order" in (Path(out["local_dir"]) / "static" / "index.html").read_text(
        encoding="utf-8"
    )


def test_failed_stamp_does_not_write(tmp_path: Path, stamp_server: str) -> None:
    _StampHandler.status = 500
    _StampHandler.body = _stamp_doc(
        f"### {INVENTED} (fields: 1)\n  - name display [display]"
    )
    out = use_sample(
        _cfg(tmp_path, stamp_server),
        sample="catalog",
        parent_dir=str(tmp_path),
    )
    assert out["ok"] is False
    assert out["written"] is False
    assert out["failure_class"] == "stamp_fetch_failed"
    assert out["entity_types"] == []
    assert not (tmp_path / "demo_catalog_sample").exists()
    assert INVENTED not in json.dumps(out)


def test_foreign_catalog_dir_is_left_alone(tmp_path: Path, stamp_server: str) -> None:
    taken = tmp_path / "taken"
    taken.mkdir()
    (taken / "keep.txt").write_text("leave me", encoding="utf-8")
    out = use_sample(
        _cfg(tmp_path, stamp_server),
        sample="catalog",
        sample_dir=str(taken),
    )
    assert out["failure_class"] == "foreign_sample_dir"
    assert out["written"] is False
    assert (taken / "keep.txt").read_text(encoding="utf-8") == "leave me"
    assert not (taken / "main.py").exists()


def test_beer_bucket_catalog_sample_writes_beer_page(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, "http://lab.example:8080", bucket="beer-sample")
    out = use_sample(cfg, sample="catalog", parent_dir=str(tmp_path))
    assert out["ok"] is True
    assert out["catalog_kind"] == "beer"
    page = (Path(out["local_dir"]) / "static" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "What's on tap." in page
    assert not (tmp_path / "demo_catalog_sample").exists()


def test_beer_entities_write_the_beer_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _beer_stamp(cfg: HelperConfig) -> dict[str, object]:
        return {
            "ok": True,
            "entity_types": ["Beer", "Brewery"],
            "entities": [],
            "req_id": "req-beer-entities",
            "zeus_url": cfg.zeus_url,
            "failure_class": None,
            "note": STAMP_NOTE,
        }

    monkeypatch.setattr("zeus_dev_helper_mcp.explain_scope.explain_scope", _beer_stamp)
    out = use_sample(
        _cfg(tmp_path, "http://lab.example:8080", bucket="orders"),
        sample="catalog",
        parent_dir=str(tmp_path),
    )
    assert out["catalog_kind"] == "beer"
    assert out["explain_scope"]["entity_types"] == ["Beer", "Brewery"]
    assert out["explain_scope"]["req_id"] == "req-beer-entities"
    page = (Path(out["local_dir"]) / "static" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "What's on tap." in page


def test_sample_beer_stays_on_the_beer_writer(tmp_path: Path) -> None:
    out = use_sample(
        _cfg(tmp_path, "http://lab.example:8080", bucket="orders"),
        sample="beer",
        parent_dir=str(tmp_path),
    )
    assert out["ok"] is True
    assert "catalog_kind" not in out
    page = (Path(out["local_dir"]) / "static" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "What's on tap." in page
    assert not (tmp_path / "demo_catalog_sample").exists()


def test_explain_scope_is_a_core_tool() -> None:
    assert "explain_scope" in DEFAULT_CORE_TOOLS
    assert default_core_count() <= CORE_CAP
