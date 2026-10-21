"""ZDM-38: smoke_test_agent pins client_floor from the stamped catalog."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from zeus_dev_helper_mcp.config import HelperConfig

BASE_61 = {
    "_lineage": {"base_id": "base-6.1"},
    "messages": [{"role": "system", "content": "x"}],
    "contract": {"hash": "md5:deadbeef"},
}


def _write_catalog(root: Path, *, scope_dir: bool = False) -> None:
    dest = root / "beer-sample__default" if scope_dir else root
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "chat_request_analytics_v2.json").write_text(
        json.dumps(BASE_61),
        encoding="utf-8",
    )


def _cfg(tmp_path: Path, catalog: Path | None) -> HelperConfig:
    return HelperConfig(
        zeus_url="http://127.0.0.1:8080",
        default_bucket="beer-sample",
        default_scope="_default",
        default_mode="analytics",
        chat_request_dir=catalog,
        state_dir=tmp_path / "state",
    )


def test_default_floor_rejects_base_61(tmp_path: Path) -> None:
    pytest.importorskip("zeus_client")
    from zeus_client.config.models import DataTarget, RuntimeConfig
    from zeus_client.domain.errors import CatalogError, ErrorCode
    from zeus_client.runtime import ZeusRuntime

    _write_catalog(tmp_path)

    async def _load() -> None:
        cfg = RuntimeConfig(
            chat_requests_dir=str(tmp_path),
            target=DataTarget(bucket="beer-sample", scope="_default"),
            client_floor="client-floor-5",
        )
        async with ZeusRuntime(cfg) as rt:
            await rt.catalog.load("analytics")

    with pytest.raises(CatalogError) as ei:
        asyncio.run(_load())
    assert ei.value.code == ErrorCode.PRECONDITION_FAILED
    assert ei.value.code == "000004"


def test_pinned_floor_loads_base_61_without_llm_or_zeus(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("zeus_client")
    from zeus_client.config.loader import config_from_mapping
    from zeus_client.runtime import ZeusRuntime

    from zeus_dev_helper_mcp.scaffold import runtime_config_dict
    from zeus_dev_helper_mcp.smoke import (
        apply_smoke_client_floor,
        pin_runtime_client_floor,
    )

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    catalog = tmp_path / "catalog"
    _write_catalog(catalog)
    cfg = _cfg(tmp_path, catalog)
    mapping = runtime_config_dict(cfg)
    assert "client_floor" not in mapping
    floor = apply_smoke_client_floor(mapping, cfg)
    assert floor == "client-floor-6.1"
    rt_cfg = config_from_mapping(mapping)

    async def _load():
        async with ZeusRuntime(rt_cfg) as rt:
            pinned = pin_runtime_client_floor(rt)
            loaded = await rt.catalog.load(mode=rt.config.settings.mode)
            return pinned, rt.config.client_floor, loaded

    pinned, seen, loaded = asyncio.run(_load())
    assert pinned == "client-floor-6.1"
    assert seen == "client-floor-6.1"
    assert loaded.base_id == "base-6.1"
    assert loaded.body["_lineage"]["base_id"] == "base-6.1"


def test_smoke_floor_matches_beer_config(tmp_path: Path) -> None:
    pytest.importorskip("zeus_client")
    from zeus_dev_helper_mcp.beer import write_beer_config
    from zeus_dev_helper_mcp.smoke import client_floor_for_catalog

    floor = client_floor_for_catalog({"_lineage": {"base_id": "base-6.1"}})
    written = write_beer_config(_cfg(tmp_path, None), tmp_path / "beer")
    payload = json.loads(Path(written["path"]).read_text(encoding="utf-8"))
    assert payload["client_floor"] == floor == "client-floor-6.1"


def test_smoke_pins_floor_before_turn_and_after_sync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("zeus_client")
    from zeus_client.api.agent import AgentAPI
    from zeus_client.api.catalog import CatalogAPI

    from zeus_dev_helper_mcp.smoke import smoke_test_agent

    monkeypatch.setenv("LLM_API_KEY", "test-not-sent")
    seen: dict[str, str | None] = {}

    async def stop_turn(self, message, **kwargs):
        seen["floor"] = self._rt.config.client_floor
        body = kwargs.get("chat_request") or {}
        lineage = body.get("_lineage") if isinstance(body, dict) else None
        seen["base_id"] = lineage.get("base_id") if isinstance(lineage, dict) else None
        raise RuntimeError("stop-before-turn")

    monkeypatch.setattr(AgentAPI, "run_turn", stop_turn)

    async def fail_sync(self, *args, **kwargs):
        raise AssertionError("sync should not run when the stamp is already on disk")

    monkeypatch.setattr(CatalogAPI, "sync", fail_sync)
    catalog = tmp_path / "catalog"
    _write_catalog(catalog)
    out = smoke_test_agent(_cfg(tmp_path, catalog), update_checklist=False)
    assert seen["floor"] == "client-floor-6.1"
    assert seen["base_id"] == "base-6.1"
    assert "stop-before-turn" in (out.get("error") or "")
    assert out.get("failure_class") != "empty_tool_catalog"
    blob = json.dumps(out)
    assert "test-not-sent" not in blob
    assert "000004" not in blob

    seen.clear()

    async def write_on_sync(self, *args, **kwargs):
        _write_catalog(Path(self._store().root), scope_dir=True)
        return SimpleNamespace(
            synced=[{"path": "beer-sample__default/chat_request_analytics_v2.json"}]
        )

    monkeypatch.setattr(CatalogAPI, "sync", write_on_sync)
    empty = tmp_path / "empty"
    empty.mkdir()
    out_after_sync = smoke_test_agent(_cfg(tmp_path, empty), update_checklist=False)
    assert seen["floor"] == "client-floor-6.1"
    assert seen["base_id"] == "base-6.1"
    assert out_after_sync.get("failure_class") != "empty_tool_catalog"
    assert "000004" not in json.dumps(out_after_sync)
    assert "test-not-sent" not in json.dumps(out_after_sync)
