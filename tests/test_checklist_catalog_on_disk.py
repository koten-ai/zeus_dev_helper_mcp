"""ZDM-40: checklist 4.1 and 4.2 follow the bound app on disk."""

from __future__ import annotations

import json
from pathlib import Path

from zeus_dev_helper_mcp.beer import save_beer_sample_dir
from zeus_dev_helper_mcp.checklist import (
    load_checklist,
    save_checklist,
    set_item_status,
)
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.sample_support import sample_support_pack
from zeus_dev_helper_mcp.scaffold import verify_local_setup
from zeus_dev_helper_mcp.walkthrough import enriched_next_step

_HASH = "md5:abc123dead"
_PLACEHOLDER = "TO_BE_FILLED_BY_HUB"


def _cfg(tmp_path: Path) -> HelperConfig:
    return HelperConfig(
        default_bucket="beer-sample",
        default_scope="_default",
        default_mode="analytics",
        state_dir=tmp_path / "state",
    )


def _item(cfg: HelperConfig, item_id: str) -> dict:
    data = load_checklist(cfg)
    for phase in data["phases"]:
        for item in phase["items"]:
            if item["id"] == item_id:
                return item
    raise AssertionError(item_id)


def _bind_project(cfg: HelperConfig, sample: str = "beer") -> None:
    data = load_checklist(cfg)
    data["meta"] = {"goal": "single-agent", "sample": sample}
    save_checklist(cfg, data)


def _app(
    tmp_path: Path,
    *,
    catalog: bool = True,
    contract_hash: str = _HASH,
    mode: str = "ZEUS_MODE",
    flat: bool = False,
) -> Path:
    root = tmp_path / "demo_beer_sample"
    (root / "data" / "chat_requests").mkdir(parents=True)
    (root / "main.py").write_text("print('beer')\n", encoding="utf-8")
    if catalog and flat:
        dest = root / "data" / "chat_requests" / "chat_request_analytics_v2.json"
        dest.write_text("{}\n", encoding="utf-8")
    elif catalog:
        dest_dir = root / "data" / "chat_requests" / "beer-sample__default"
        dest_dir.mkdir()
        (dest_dir / "chat_request_analytics_v2.json").write_text("{}\n", encoding="utf-8")
    zeus: dict = {}
    if contract_hash:
        zeus["scope_contracts"] = {
            "beer-sample/_default": {
                "analytics": {"contract_id": "analytics_base", "contract_hash": contract_hash}
            }
        }
    payload = {
        "chat_requests_dir": "data/chat_requests",
        "target": {"bucket": "beer-sample", "scope": "_default"},
        "settings": {"mode": mode},
        "zeus": zeus,
    }
    (root / "config.json").write_text(json.dumps(payload), encoding="utf-8")
    return root


def test_next_step_marks_scope_catalog_and_pin(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    app = _app(tmp_path)
    _bind_project(cfg)
    save_beer_sample_dir(cfg, app)
    nxt = enriched_next_step(cfg)
    catalog = _item(cfg, "4.1")
    pin = _item(cfg, "4.2")
    assert catalog["status"] == "done"
    assert catalog["evidence"] == "scope catalog on disk"
    assert pin["status"] == "done"
    assert pin["evidence"] == "scope_contracts pinned"
    assert nxt["item"]["id"] == "0.1"
    assert _HASH not in json.dumps(catalog)
    assert _HASH not in json.dumps(pin)


def test_placeholder_hash_leaves_4_2_open(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    app = _app(tmp_path, contract_hash=_PLACEHOLDER)
    _bind_project(cfg)
    save_beer_sample_dir(cfg, app)
    enriched_next_step(cfg)
    assert _item(cfg, "4.1")["status"] == "done"
    assert _item(cfg, "4.2")["status"] == "todo"


def test_local_hash_and_missing_catalog_stay_open(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    app = _app(tmp_path, catalog=False, contract_hash="compute_local")
    _bind_project(cfg)
    save_beer_sample_dir(cfg, app)
    enriched_next_step(cfg)
    assert _item(cfg, "4.1")["status"] == "todo"
    assert _item(cfg, "4.2")["status"] == "todo"


def test_done_evidence_stays(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    app = _app(tmp_path)
    _bind_project(cfg)
    save_beer_sample_dir(cfg, app)
    set_item_status(cfg, "4.1", "done", evidence="test")
    set_item_status(cfg, "4.2", "blocked", evidence="old")
    enriched_next_step(cfg)
    assert _item(cfg, "4.1")["evidence"] == "test"
    assert _item(cfg, "4.2")["status"] == "done"
    assert _item(cfg, "4.2")["evidence"] == "scope_contracts pinned"


def test_other_sample_does_not_read_the_beer_tree(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    app = _app(tmp_path)
    _bind_project(cfg, "travel")
    save_beer_sample_dir(cfg, app)
    enriched_next_step(cfg)
    assert _item(cfg, "4.1")["status"] == "todo"
    assert _item(cfg, "4.2")["status"] == "todo"


def test_support_pack_omits_satisfied_rows_without_writing(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    app = _app(tmp_path)
    _bind_project(cfg)
    save_beer_sample_dir(cfg, app)
    set_item_status(cfg, "5.1", "blocked", evidence="status=429")
    checklist = cfg.state_dir / "checklist.json"
    before = {path.name: path.read_bytes() for path in cfg.state_dir.iterdir()}
    out = sample_support_pack(cfg, "beer")
    after = {path.name: path.read_bytes() for path in cfg.state_dir.iterdir()}
    assert before == after
    text = out["markdown"]
    assert "- 4.1 " not in text
    assert "- 4.2 " not in text
    assert "- 5.1 blocked: smoke_test_zeus" in text
    assert _HASH not in text
    assert checklist.read_bytes() == before["checklist.json"]

    bare = _cfg(tmp_path / "bare")
    _bind_project(bare)
    set_item_status(bare, "4.1", "todo")
    set_item_status(bare, "4.2", "todo")
    empty = sample_support_pack(bare, "beer")["markdown"]
    assert "- 4.1 todo:" in empty
    assert "- 4.2 todo:" in empty


def test_verify_local_setup_sees_a_flat_catalog(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    app = _app(tmp_path, flat=True, mode="analytics")
    _bind_project(cfg)
    verify_local_setup(cfg, target_dir=str(app))
    assert _item(cfg, "4.1")["status"] == "done"
    assert _item(cfg, "4.2")["evidence"] == "scope_contracts pinned"


def test_template_checkout_is_not_the_app_catalog(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    app = _app(tmp_path, catalog=False, contract_hash="")
    template = tmp_path / "zeus_chat_request"
    (template / "v2").mkdir(parents=True)
    (template / "catalog-index.json").write_text("{}\n", encoding="utf-8")
    scope = template / "beer-sample__default"
    scope.mkdir()
    (scope / "chat_request_analytics_v2.json").write_text("{}\n", encoding="utf-8")
    config = json.loads((app / "config.json").read_text(encoding="utf-8"))
    config["chat_requests_dir"] = str(template)
    (app / "config.json").write_text(json.dumps(config), encoding="utf-8")
    _bind_project(cfg)
    save_beer_sample_dir(cfg, app)
    enriched_next_step(cfg)
    assert _item(cfg, "4.1")["status"] == "todo"
    assert _item(cfg, "4.2")["status"] == "todo"
