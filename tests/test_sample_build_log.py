"""ZDM-24: one write-once Markdown file for the first sample creation."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from zeus_dev_helper_mcp import __version__
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.sample_log import (
    bound_sample_dirs,
    observe_sample_build,
    public_arguments,
    reset_memory,
    sample_kind,
)
from zeus_dev_helper_mcp.server import _wrap_tool

NOW = datetime(2026, 10, 12, 18, 4, 5, tzinfo=UTC)
_STAMP = "2026-10-12T18:04:05Z"
_HASH = "AbCdEf1234567890dead"
_CATALOG = "UNIQUE_CATALOG_DOCUMENT_BODY"
_SECRET = "sk-live-abcdefghijklmnopqrstuvwxyz"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_memory()
    for name in (
        "DEMO_BEER_SAMPLE_DIR",
        "DEMO_TRAVEL_SAMPLE_DIR",
        "DEMO_YELP_SAMPLE_DIR",
    ):
        monkeypatch.delenv(name, raising=False)


def _cfg(tmp_path: Path) -> HelperConfig:
    return HelperConfig(state_dir=tmp_path / "state")


def _call(
    cfg: HelperConfig,
    tool: str,
    args: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    **kwargs: Any,
) -> None:
    observe_sample_build(
        cfg,
        tool,
        args or {},
        result or {"ok": True},
        now=kwargs.pop("now", NOW),
        **kwargs,
    )


def _beer(cfg: HelperConfig, **result: Any) -> None:
    payload = {
        "ok": True,
        "written": True,
        "local_dir": "/work/demos/demo_beer_sample",
    }
    payload.update(result)
    _call(cfg, "doctor", {"detail": "health"})
    _call(
        cfg,
        "set_prereq",
        {
            "zeus_url": "http://192.168.0.219:8080",
            "bucket": "beer-sample",
            "scope": "_default",
            "auth_mode": "basic",
            "has_password": True,
            "password": "s3cret-password",
            "api_key": _SECRET,
            "prompt": _CATALOG,
            "chat_request": {"body": _CATALOG, "hash": _HASH},
        },
    )
    _call(cfg, "start_project", {"goal": "single-agent", "sample": "beer"})
    _call(cfg, "next_step")
    _call(cfg, "readiness_check", {"update_checklist": True})
    _call(cfg, "recommend_surface", {"intent": "website", "needs_llm": False, "qps": 1.5})
    _call(cfg, "load_process_login", {"env_file": "/work/demo.env"})
    _call(cfg, "validate_env")
    _call(
        cfg,
        "use_sample",
        {
            "sample": "beer",
            "parent_dir": "/work/demos",
            "project_name": "demo_beer_sample",
            "target_dir": "/work/demos/demo_beer_sample",
        },
        payload,
    )


def _text(cfg: HelperConfig, name: str) -> str:
    return (cfg.state_dir / name).read_text(encoding="utf-8")


def _files(cfg: HelperConfig) -> list[str]:
    root = cfg.state_dir
    if not root.is_dir():
        return []
    return sorted(path.name for path in root.glob("*.md"))


def _sections(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("## ")]


def _fences(text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    parts = text.split("```json\n")
    for part in parts[1:]:
        body = part.split("```", 1)[0]
        blocks.append(json.loads(body))
    return blocks


def test_sample_kind_maps_the_three_samples() -> None:
    assert sample_kind("") is None
    assert sample_kind("api") is None
    assert sample_kind("rest") is None
    assert sample_kind("api_only") is None
    assert sample_kind("api-only") is None
    assert sample_kind("yelp") is None
    assert sample_kind("multi") is None
    assert sample_kind("catalog") is None
    assert sample_kind("travel") == "travel"
    assert sample_kind("ui") == "travel"
    assert sample_kind("demo_travel_sample") == "travel"
    assert sample_kind("beer") == "beer"
    assert sample_kind("beer-sample") == "beer"
    assert sample_kind("demo_yelp") == "yelp-demo"
    assert sample_kind("yelp-demo") == "yelp-demo"
    assert sample_kind("demo-yelp") == "yelp-demo"
    assert sample_kind("yelp_demo") == "yelp-demo"
    assert sample_kind("yelpdemo") == "yelp-demo"


def test_first_beer_creation_writes_one_replayable_file(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _beer(
        cfg,
        contract_hash=_HASH,
        app_config={"password": "s3cret-password"},
        chat_request={"body": _CATALOG, "hash": "ffffffffffffffff"},
    )
    assert _files(cfg) == ["beer-sample-build.md"]
    text = _text(cfg, "beer-sample-build.md")
    assert text.startswith("# beer-sample\n")
    assert _sections(text) == [
        "## 1. doctor",
        "## 2. set_prereq",
        "## 3. start_project",
        "## 4. next_step",
        "## 5. readiness_check",
        "## 6. recommend_surface",
        "## 7. load_process_login",
        "## 8. validate_env",
        "## 9. use_sample",
    ]
    assert f"- Helper version: {__version__}" in text
    assert f"- UTC timestamp: {_STAMP}" in text
    assert "- Tool: `use_sample`" in text
    assert "- ok: true" in text
    assert "- path: /work/demos/demo_beer_sample" in text
    assert "- stamp: AbCdEf123456" in text
    assert _HASH not in text
    assert "ffffffffffffffff" not in text
    fences = _fences(text)
    assert fences[-1] == {
        "parent_dir": "/work/demos",
        "project_name": "demo_beer_sample",
        "sample": "beer",
        "target_dir": "/work/demos/demo_beer_sample",
    }
    assert fences[1]["zeus_url"] == "http://192.168.0.219:8080"
    assert fences[1]["bucket"] == "beer-sample"
    assert fences[1]["scope"] == "_default"
    assert fences[1]["auth_mode"] == "basic"
    assert fences[1]["has_password"] is True
    assert fences[5] == {"intent": "website", "needs_llm": False, "qps": 1.5}
    assert "s3cret-password" not in text
    assert _SECRET not in text
    assert _CATALOG not in text
    assert "cloned:" not in text


def test_existing_file_is_left_unchanged(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _beer(cfg)
    original = _text(cfg, "beer-sample-build.md")
    _call(cfg, "next_step")
    _call(cfg, "smoke_test_zeus")
    _call(cfg, "smoke_test_agent")
    _call(cfg, "website_green")
    _call(cfg, "diagnose_error")
    _call(cfg, "bind_contract")
    _call(cfg, "verify_local_setup")
    _call(cfg, "scaffold_app", {"app_kind": "api", "target_dir": "/tmp/api"})
    _beer(cfg, local_dir="/work/other")
    assert _text(cfg, "beer-sample-build.md") == original
    assert _files(cfg) == ["beer-sample-build.md"]


def test_later_session_does_not_rewrite(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _beer(cfg)
    original = _text(cfg, "beer-sample-build.md")
    reset_memory()
    _call(cfg, "doctor", {"detail": "health"})
    _call(cfg, "next_step")
    _call(
        cfg,
        "use_sample",
        {"sample": "beer"},
        {"ok": True, "written": True, "local_dir": "/work/other"},
    )
    assert _text(cfg, "beer-sample-build.md") == original


def test_noop_and_upgrade_do_not_create_a_file(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _call(cfg, "start_project", {"sample": "beer"})
    for result in (
        {"ok": True, "written": False, "local_dir": "/work/demo_beer_sample"},
        {"ok": True, "already_serving": True, "written": False, "local_dir": "/work/x"},
        {"ok": True, "written": True, "upgraded": True, "local_dir": "/work/x"},
        {"ok": True, "written": True, "page_only": True, "local_dir": "/work/x"},
    ):
        _call(cfg, "use_sample", {"sample": "beer"}, result)
    assert _files(cfg) == []


def test_failed_use_sample_is_kept_until_the_create(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _call(cfg, "doctor", {"detail": "health"})
    _call(
        cfg,
        "use_sample",
        {"sample": "beer", "parent_dir": "/work"},
        {
            "ok": False,
            "failure_class": "login_not_in_process",
            "local_dir": "/work/demo_beer_sample",
        },
    )
    assert _files(cfg) == []
    _call(
        cfg,
        "use_sample",
        {"sample": "beer", "parent_dir": "/work"},
        {"ok": True, "written": True, "local_dir": "/work/demo_beer_sample"},
    )
    text = _text(cfg, "beer-sample-build.md")
    assert _sections(text)[-1] == "## 3. use_sample"
    assert "- ok: false" in text
    assert "- failure_class: login_not_in_process" in text
    assert text.count("- ok: true") == 2
    assert "\n- path: /work/demo_beer_sample\n" in text


def test_travel_clone_and_new_bind(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _call(cfg, "start_project", {"sample": "travel"})
    _call(
        cfg,
        "use_sample",
        {"sample": "demo_travel_sample", "parent_dir": "/work"},
        {
            "ok": True,
            "cloned": True,
            "local_dir": "/work/demo_travel_sample",
            "env": {"DEMO_TRAVEL_SAMPLE_DIR": "/work/demo_travel_sample"},
        },
        bound_before={},
    )
    text = _text(cfg, "travel-sample-build.md")
    assert _sections(text) == ["## 1. start_project", "## 2. use_sample"]
    assert "- cloned: true" in text
    assert "- path: /work/demo_travel_sample" in text
    assert _files(cfg) == ["travel-sample-build.md"]

    other = HelperConfig(state_dir=tmp_path / "bind")
    _call(other, "doctor", {"detail": "health"})
    _call(
        other,
        "use_sample",
        {"sample": "ui"},
        {"ok": True, "cloned": False, "local_dir": "/work/demo_travel_sample"},
        bound_before={},
    )
    bound = _text(other, "travel-sample-build.md")
    assert _sections(bound) == ["## 1. doctor", "## 2. use_sample"]
    assert "- cloned: false" in bound


def test_already_bound_travel_and_missing_clone_flag_are_noops(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    same = "/work/demo_travel_sample"
    _call(
        cfg,
        "use_sample",
        {"sample": "travel"},
        {"ok": True, "cloned": False, "local_dir": same},
        bound_before={"travel": same},
    )
    _call(
        cfg,
        "use_sample",
        {"sample": "travel"},
        {"ok": True, "local_dir": same},
        bound_before=None,
    )
    _call(
        cfg,
        "use_sample",
        {"sample": "travel"},
        {"ok": True, "cloned": False, "local_dir": "/work/other"},
        bound_before=None,
    )
    assert _files(cfg) == []

    created = HelperConfig(state_dir=tmp_path / "moved")
    _call(
        created,
        "use_sample",
        {"sample": "travel"},
        {"ok": True, "cloned": False, "local_dir": "/work/other"},
        bound_before={"travel": "/work/demo_travel_sample"},
    )
    assert _files(created) == ["travel-sample-build.md"]


@pytest.mark.parametrize(
    "alias",
    ["demo_yelp", "yelp-demo", "demo-yelp", "yelp_demo", "yelpdemo"],
)
def test_yelp_aliases_share_one_file(tmp_path: Path, alias: str) -> None:
    cfg = _cfg(tmp_path)
    _call(cfg, "start_project", {"sample": alias})
    _call(
        cfg,
        "use_sample",
        {"sample": alias, "parent_dir": "/work", "project_name": "demo_yelp"},
        {"ok": True, "cloned": True, "local_dir": "/work/demo_yelp"},
    )
    assert _files(cfg) == ["yelp-demo-build.md"]
    text = _text(cfg, "yelp-demo-build.md")
    assert text.startswith("# yelp-demo\n")
    assert _sections(text)[-1] == "## 2. use_sample"
    assert _fences(text)[-1]["sample"] == alias


def test_api_scaffold_and_bare_yelp_add_nothing(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _call(cfg, "doctor", {"detail": "health"})
    _call(cfg, "start_project", {"sample": "api", "goal": "single-agent"})
    _call(cfg, "scaffold_app", {"app_kind": "api", "coding_language": "python", "target_dir": "/tmp/api"})
    _call(cfg, "scaffold_app", {"app_kind": "cli", "target_dir": "/tmp/cli"})
    _call(
        cfg,
        "use_sample",
        {"sample": "yelp"},
        {"ok": True, "cloned": True, "local_dir": "/tmp/yelp"},
    )
    _call(
        cfg,
        "use_sample",
        {"sample": "api"},
        {"ok": False, "failure_class": "use_scaffold"},
    )
    assert _files(cfg) == []


def test_second_sample_keeps_its_own_calls(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _call(cfg, "doctor", {"detail": "health"})
    _call(cfg, "start_project", {"sample": "beer"})
    _call(cfg, "start_project", {"sample": "travel"})
    _call(
        cfg,
        "use_sample",
        {"sample": "travel"},
        {"ok": True, "cloned": True, "local_dir": "/work/demo_travel_sample"},
    )
    travel = _text(cfg, "travel-sample-build.md")
    assert "start_project" in travel
    assert _fences(travel)[1]["sample"] == "travel"
    assert "beer" not in travel
    _call(
        cfg,
        "use_sample",
        {"sample": "beer"},
        {"ok": True, "written": True, "local_dir": "/work/demo_beer_sample"},
    )
    beer = _text(cfg, "beer-sample-build.md")
    assert _fences(beer)[0]["detail"] == "health"
    assert _fences(beer)[1]["sample"] == "beer"
    assert "travel" not in beer


def test_blank_sample_follows_the_travel_default(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _call(
        cfg,
        "use_sample",
        {"sample": "   "},
        {"ok": True, "cloned": True, "local_dir": "/work/demo_travel_sample"},
    )
    assert _files(cfg) == ["travel-sample-build.md"]
    omitted = HelperConfig(state_dir=tmp_path / "omit")
    _call(
        omitted,
        "use_sample",
        {},
        {"ok": True, "cloned": True, "local_dir": "/work/demo_travel_sample"},
    )
    assert _files(omitted) == ["travel-sample-build.md"]


def test_secrets_and_stamp_walk_stay_out_of_the_file(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    nested = {"contract_hash": _HASH}
    for _ in range(6):
        nested = {"child": nested}
    _call(
        cfg,
        "set_prereq",
        {
            "zeus_url": "http://user:s3cret@192.168.0.219:8080/v1?mode=analytics",
            "leaked": f"http://user:s3cret@10.0.0.1:8080/?k={_SECRET}",
            "detail": _SECRET,
            "note": "http://user:s3cret@[2001:db8::1]:8080/v1",
            "dropped": "   ",
            "evidence": "do not keep",
            "items": ["catalog"],
            "count": 2,
        },
    )
    _call(
        cfg,
        "readiness_check",
        {},
        {
            "ok": True,
            "primary_failure_class": "auth_failed\nline",
            "local_dir": f"/tmp/{_SECRET}",
            "checks": [{"contract_hash": "abc"}],
            "nested": nested,
            1: {"contract_hash": _HASH},
        },
    )
    _call(
        cfg,
        "use_sample",
        {"sample": "beer"},
        {
            "ok": True,
            "written": True,
            "password": "s3cret-password",
            "hash": None,
            "env": {"DEMO_BEER_SAMPLE_DIR": "/work/demo_beer_sample"},
            "checks": [{}, {"contract_hash": "1234abcd5678ffff"}],
        },
    )
    text = _text(cfg, "beer-sample-build.md")
    assert "s3cret" not in text
    assert _SECRET not in text
    assert "http://192.168.0.219:8080/v1?mode=analytics" in text
    assert "http://[2001:db8::1]:8080/v1" in text
    assert "items" not in text
    assert '"count": 2' in text
    assert "- failure_class: auth_failed line" in text
    assert "- stamp: 1234abcd5678" in text
    assert "1234abcd5678ffff" not in text
    assert "AbCdEf123456" not in text
    assert "/tmp/" not in text


def test_stamp_on_the_twentieth_list_item_only(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    checks = [{} for _ in range(19)]
    checks.append({"hash": "abcdef1234567890"})
    _call(
        cfg,
        "use_sample",
        {"sample": "travel"},
        {"ok": True, "cloned": True, "local_dir": "/work/t", "checks": checks},
    )
    assert "- stamp: abcdef123456" in _text(cfg, "travel-sample-build.md")

    missed = HelperConfig(state_dir=tmp_path / "missed")
    late = [{} for _ in range(20)]
    late.append({"hash": "abcdef1234567890"})
    _call(
        missed,
        "use_sample",
        {"sample": "travel"},
        {"ok": True, "cloned": True, "local_dir": "/work/t", "checks": late},
    )
    assert "- stamp:" not in _text(missed, "travel-sample-build.md")


def test_naive_timestamp_is_utc(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _call(
        cfg,
        "use_sample",
        {"sample": "beer"},
        {"ok": True, "written": True, "local_dir": "/work/demo_beer_sample"},
        now=datetime(2026, 10, 12, 18, 4, 5),  # noqa: DTZ001 — naive input is treated as UTC
    )
    assert "- UTC timestamp: 2026-10-12T18:04:05Z" in _text(cfg, "beer-sample-build.md")


def test_bound_sample_dirs_read_env_then_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _cfg(tmp_path)
    cfg.state_dir.mkdir()
    (cfg.state_dir / "beer_sample.json").write_text("{", encoding="utf-8")
    (cfg.state_dir / "travel_sample.json").write_text("[]", encoding="utf-8")
    (cfg.state_dir / "yelp_sample.json").write_text(
        json.dumps({"yelp_sample_dir": "/work/demo_yelp"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DEMO_BEER_SAMPLE_DIR", "/env/beer")
    monkeypatch.setenv("DEMO_TRAVEL_SAMPLE_DIR", "/env/travel")
    assert bound_sample_dirs(cfg) == {
        "beer": "/env/beer",
        "travel": "/env/travel",
        "yelp-demo": "/work/demo_yelp",
    }
    monkeypatch.delenv("DEMO_BEER_SAMPLE_DIR")
    (cfg.state_dir / "beer_sample.json").write_text(
        json.dumps({"beer_sample_dir": ""}),
        encoding="utf-8",
    )
    found = bound_sample_dirs(cfg)
    assert "beer" not in found
    assert found["travel"] == "/env/travel"


def test_file_created_mid_run_is_left_unchanged(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _call(cfg, "doctor", {"detail": "health"})
    _call(cfg, "start_project", {"sample": "beer"})
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    path = cfg.state_dir / "beer-sample-build.md"
    path.write_text("keep\n", encoding="utf-8")
    _call(cfg, "next_step")
    _call(
        cfg,
        "use_sample",
        {"sample": "beer"},
        {"ok": True, "written": True, "local_dir": "/work/demo_beer_sample"},
    )
    assert path.read_text(encoding="utf-8") == "keep\n"


def test_bound_sample_dirs_skip_bad_state_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _cfg(tmp_path)
    cfg.state_dir.mkdir()
    (cfg.state_dir / "beer_sample.json").write_text("{", encoding="utf-8")
    (cfg.state_dir / "travel_sample.json").write_text("[]", encoding="utf-8")
    (cfg.state_dir / "yelp_sample.json").write_text(
        json.dumps({"yelp_sample_dir": "  "}),
        encoding="utf-8",
    )
    assert bound_sample_dirs(cfg) == {}

    good = cfg.state_dir / "beer_sample.json"
    good.write_text(json.dumps({"beer_sample_dir": "/work/beer"}), encoding="utf-8")

    def _boom(self: Path, *args: Any, **kwargs: Any) -> str:
        raise OSError("read")

    monkeypatch.setattr(Path, "read_text", _boom)
    assert bound_sample_dirs(cfg) == {}


def test_bound_sample_dirs_ignore_unreadable_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _cfg(tmp_path)
    cfg.state_dir.mkdir()
    path = cfg.state_dir / "beer_sample.json"
    path.mkdir()
    monkeypatch.delenv("DEMO_BEER_SAMPLE_DIR", raising=False)
    assert "beer" not in bound_sample_dirs(cfg)


def test_public_arguments_drop_the_gate_and_fall_back() -> None:
    def use_sample(sample: str = "travel", clarification: Any = None) -> dict[str, Any]:
        return {"ok": True}

    assert public_arguments(use_sample, (), {"sample": "beer", "clarification": object()}) == {
        "sample": "beer"
    }

    def doctor() -> dict[str, Any]:
        return {"ok": True}

    assert public_arguments(doctor, ("extra",), {"password": "nope"}) == {"password": "nope"}


def test_symlink_and_directory_are_not_overwritten(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.state_dir.mkdir()
    target = tmp_path / "other.md"
    target.write_text("keep\n", encoding="utf-8")
    link = cfg.state_dir / "beer-sample-build.md"
    link.symlink_to(target)
    _call(
        cfg,
        "use_sample",
        {"sample": "beer"},
        {"ok": True, "written": True, "local_dir": "/work/demo_beer_sample"},
    )
    assert target.read_text(encoding="utf-8") == "keep\n"
    assert link.is_symlink()

    dangling = HelperConfig(state_dir=tmp_path / "dangling")
    dangling.state_dir.mkdir()
    (dangling.state_dir / "beer-sample-build.md").symlink_to(tmp_path / "missing.md")
    _call(
        dangling,
        "use_sample",
        {"sample": "beer"},
        {"ok": True, "written": True, "local_dir": "/work/demo_beer_sample"},
    )
    assert (dangling.state_dir / "beer-sample-build.md").is_symlink()
    assert not (tmp_path / "missing.md").exists()

    blocked = HelperConfig(state_dir=tmp_path / "blocked")
    blocked.state_dir.mkdir()
    (blocked.state_dir / "travel-sample-build.md").mkdir()
    _call(
        blocked,
        "use_sample",
        {"sample": "travel"},
        {"ok": True, "cloned": True, "local_dir": "/work/demo_travel_sample"},
    )
    assert (blocked.state_dir / "travel-sample-build.md").is_dir()


def test_write_errors_do_not_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zeus_dev_helper_mcp import sample_log

    cfg = _cfg(tmp_path)

    def _mkdir(self: Path, *args: Any, **kwargs: Any) -> None:
        raise OSError("mkdir")

    monkeypatch.setattr(Path, "mkdir", _mkdir)
    _call(
        cfg,
        "use_sample",
        {"sample": "beer"},
        {"ok": True, "written": True, "local_dir": "/work/demo_beer_sample"},
    )
    assert _files(cfg) == []

    monkeypatch.undo()
    reset_memory()

    def _open(*args: Any, **kwargs: Any) -> int:
        raise OSError("open")

    monkeypatch.setattr(sample_log.os, "open", _open)
    _call(
        cfg,
        "use_sample",
        {"sample": "beer"},
        {"ok": True, "written": True, "local_dir": "/work/demo_beer_sample"},
    )
    assert _files(cfg) == []

    monkeypatch.undo()
    reset_memory()

    real_open = os.open
    real_fdopen = os.fdopen

    def _fdopen(fd: int, *args: Any, **kwargs: Any) -> Any:
        os.close(fd)
        raise OSError("write")

    monkeypatch.setattr(sample_log.os, "open", real_open)
    monkeypatch.setattr(sample_log.os, "fdopen", _fdopen)
    _call(
        cfg,
        "use_sample",
        {"sample": "beer"},
        {"ok": True, "written": True, "local_dir": "/work/demo_beer_sample"},
    )
    assert not (cfg.state_dir / "beer-sample-build.md").exists()
    monkeypatch.setattr(sample_log.os, "fdopen", real_fdopen)


def test_same_path_falls_back_when_resolve_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from zeus_dev_helper_mcp import sample_log

    def _boom(self: Path, *args: Any, **kwargs: Any) -> Path:
        raise OSError("resolve")

    monkeypatch.setattr(Path, "resolve", _boom)
    assert sample_log._same_path("/work/a", "/work/a") is True
    assert sample_log._same_path("/work/a", "/work/b") is False


def test_wrapper_records_the_run_and_leaves_metrics_as_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))

    def doctor(detail: str = "health") -> dict[str, Any]:
        return {"ok": True}

    def set_prereq(zeus_url: str = "", password: str = "") -> dict[str, Any]:
        return {"ok": True}

    def use_sample(sample: str = "travel", parent_dir: str = "") -> dict[str, Any]:
        return {"ok": True, "written": True, "local_dir": str(tmp_path / "demo_beer_sample")}

    assert _wrap_tool(doctor)(detail="health")["ok"] is True
    _wrap_tool(set_prereq)(zeus_url="http://user:s3cret@192.168.0.219:8080", password="s3cret")
    created = _wrap_tool(use_sample)(sample="beer", parent_dir=str(tmp_path))
    assert created["written"] is True
    text = (tmp_path / "state" / "beer-sample-build.md").read_text(encoding="utf-8")
    assert _sections(text) == ["## 1. doctor", "## 2. set_prereq", "## 3. use_sample"]
    assert "s3cret" not in text
    assert "http://192.168.0.219:8080" in text
    rows = [
        json.loads(line)
        for line in (tmp_path / "state" / "metrics.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [row["tool"] for row in rows] == ["doctor", "set_prereq", "use_sample"]
    assert all(set(row) == {"ts", "event", "tool"} for row in rows)
    assert all(row["event"] == "tool_call" for row in rows)


def test_wrapper_ignores_a_log_failure_and_still_raises_tool_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))

    def doctor(detail: str = "health") -> dict[str, Any]:
        return {"status": "up"}

    def explode(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("log failed")

    monkeypatch.setattr(
        "zeus_dev_helper_mcp.server.observe_sample_build",
        explode,
    )
    assert _wrap_tool(doctor)()["ok"] is True

    def smoke_test_zeus() -> dict[str, Any]:
        return {"ok": False, "failure_class": "zeus_unreachable"}

    with pytest.raises(Exception, match="zeus_unreachable"):
        _wrap_tool(smoke_test_zeus)()
    err = capsys.readouterr().err
    assert "zeus_dev_helper.tool.failed" in err
    assert _files(HelperConfig(state_dir=tmp_path / "state")) == []


def test_wrapper_returns_non_dict_and_reraises_tool_exceptions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))

    def doctor() -> str:
        return "ok"

    assert _wrap_tool(doctor)() == "ok"

    def use_sample(sample: str = "travel") -> dict[str, Any]:
        raise RuntimeError("clone failed")

    with pytest.raises(RuntimeError, match="clone failed"):
        _wrap_tool(use_sample)(sample="beer")
    assert _files(HelperConfig(state_dir=tmp_path / "state")) == []
