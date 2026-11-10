"""ZDM-58: a red gate appends wish items and names the file."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from zeus_dev_helper_mcp import __version__
from zeus_dev_helper_mcp import sample_support as journal
from zeus_dev_helper_mcp import sample_wish as wish
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.error_log import MESSAGE_CAP
from zeus_dev_helper_mcp.server import _wrap_tool

NOW = datetime(2026, 11, 6, tzinfo=UTC)
_STAMP = "2026-11-06T00:00:00Z"
_SESSION = "11111111-1111-1111-1111-111111111111"
_SECRET = "sk-live-abcdefghijklmnopqrstuvwxyz"
_XAI = "xai-abcdefghijklmnopqrstuvwxyz"
_BUILD = {
    "beer": "beer-sample-build.md",
    "travel": "travel-sample-build.md",
    "yelp-demo": "yelp-demo-build.md",
}
_SUPPORT = {
    "beer": "beer-sample-support.md",
    "travel": "travel-sample-support.md",
    "yelp-demo": "yelp-demo-support.md",
}
_WISH = {
    "beer": "beer-sample-wish.md",
    "travel": "travel-sample-wish.md",
    "yelp-demo": "yelp-demo-wish.md",
}
_CATALOG_PATH = (
    "data/chat_requests/beer-sample__default/chat_request_analytics_v2.json"
)


def _cfg(tmp_path: Path) -> HelperConfig:
    return HelperConfig(state_dir=tmp_path / "state")


def _call(
    cfg: HelperConfig,
    tool: str,
    args: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    *,
    exc: BaseException | None = None,
    now: datetime | None = NOW,
) -> str | None:
    return wish.observe_sample_wish(
        cfg,
        tool,
        args or {},
        result,
        exc=exc,
        now=now,
    )


def _project(cfg: HelperConfig, sample: str) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    payload = {"meta": {"goal": "single-agent", "sample": sample}, "phases": []}
    (cfg.state_dir / "checklist.json").write_text(json.dumps(payload), encoding="utf-8")


def _seal(cfg: HelperConfig, kind: str, body: str = "SEALED\n") -> Path:
    path = cfg.state_dir / _BUILD[kind]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _text(cfg: HelperConfig, kind: str) -> str:
    return (cfg.state_dir / _WISH[kind]).read_text(encoding="utf-8")


def _sections(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("## ")]


def _items(text: str) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = None
            continue
        if line.startswith("  - what:"):
            current = {"what": line.split(": ", 1)[1]}
            found.append(current)
            continue
        if current is not None and line.startswith("    ") and ": " in line:
            key, value = line.strip().split(": ", 1)
            current[key] = value
    return found


def _red(failure: str = "auth_failed", message: str = "fix login") -> dict[str, Any]:
    return {"ok": False, "failure_class": failure, "next_action": message}


def test_support_section_pattern_stays_the_message_shape() -> None:
    pattern = journal._SECTION.pattern
    assert "- message:" in pattern
    assert "wish_i_knew" not in pattern
    source = Path(wish.__file__).read_text(encoding="utf-8")
    assert "httpx" not in source
    assert "urlopen" not in source


def test_red_use_sample_without_a_creation_log_writes_the_wish_file(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    written = _call(cfg, "use_sample", {"sample": "beer"}, _red("login_not_in_process"))
    assert written == str(cfg.state_dir / _WISH["beer"])
    text = _text(cfg, "beer")
    assert text.startswith("# beer-sample wish\n")
    assert wish._INTRO in text
    assert "## 1. use_sample" in text
    assert f"- Helper version: {__version__}" in text
    assert f"- UTC timestamp: {_STAMP}" in text
    assert "failure_class: login_not_in_process" in text
    assert not (cfg.state_dir / _BUILD["beer"]).exists()
    assert not (cfg.state_dir / _SUPPORT["beer"]).exists()


def test_readiness_before_a_regular_creation_log_writes_nothing(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _project(cfg, "beer")
    _call(cfg, "readiness_check", {}, _red())
    _call(cfg, "smoke_test_zeus", {}, _red())
    _call(cfg, "website_green", {}, _red())
    outside = tmp_path / "build.md"
    outside.write_text("SEALED\n", encoding="utf-8")
    (cfg.state_dir / _BUILD["beer"]).symlink_to(outside)
    _call(cfg, "validate_env", {}, _red())
    _call(cfg, "load_process_login", {}, _red())
    _call(cfg, "verify_local_setup", {}, _red())
    _call(cfg, "smoke_test_agent", {}, _red())
    assert list(cfg.state_dir.glob("*-wish.md")) == []
    assert outside.read_text(encoding="utf-8") == "SEALED\n"


def test_diagnose_api_scaffold_and_bare_yelp_write_nothing(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _project(cfg, "beer")
    _seal(cfg, "beer")
    _call(cfg, "use_sample", {"sample": "api"}, _red())
    _call(cfg, "use_sample", {"sample": "yelp"}, _red())
    _call(cfg, "scaffold_app", {"app_kind": "api"}, _red())
    _call(cfg, "diagnose_error", {"symptom": "401"}, _red())
    _call(cfg, "diagnose_error", {}, None, exc=RuntimeError("boom"))
    assert list(cfg.state_dir.glob("*-wish.md")) == []


def test_yelp_aliases_and_the_three_samples_get_their_own_files(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _call(cfg, "use_sample", {"sample": "beer"}, _red())
    _call(cfg, "use_sample", {"sample": "travel"}, _red())
    for alias in ("demo_yelp", "yelp-demo", "demo-yelp", "yelp_demo", "yelpdemo"):
        _call(cfg, "use_sample", {"sample": alias}, _red(message=alias))
    yelp = _text(cfg, "yelp-demo")
    assert _sections(yelp) == [f"## {index}. use_sample" for index in range(1, 6)]
    names = sorted(path.name for path in cfg.state_dir.glob("*.md"))
    assert names == [
        "beer-sample-wish.md",
        "travel-sample-wish.md",
        "yelp-demo-wish.md",
    ]


def test_auth_default_bucket_writes_one_bucket_item(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _project(cfg, "beer")
    _seal(cfg, "beer")
    _call(
        cfg,
        "readiness_check",
        {},
        {
            "ok": False,
            "failure_class": "auth_default_bucket",
            "next_action": "A probe touched a bucket other than the set_prereq bucket.",
            "foreign_buckets": ["default"],
            "prereq_bucket": "beer-sample",
            "request_buckets": ["default", "beer-sample"],
            "gates": [{"failure_class": "auth_default_bucket", "status": "fail"}],
        },
    )
    text = _text(cfg, "beer")
    assert text == (
        "# beer-sample wish\n"
        "\n"
        f"{wish._INTRO}\n"
        "\n"
        "## 1. readiness_check\n"
        "\n"
        f"- Helper version: {__version__}\n"
        f"- UTC timestamp: {_STAMP}\n"
        "- Tool: `readiness_check`\n"
        "- failure_class: auth_default_bucket\n"
        "- wish_i_knew:\n"
        "  - what: bucket on the hop is not the stored prereq bucket\n"
        "    kind: bucket\n"
        "    why: login was sent to the wrong bucket\n"
        "    severity: high\n"
    )
    assert _items(text) == [
        {
            "what": "bucket on the hop is not the stored prereq bucket",
            "kind": "bucket",
            "why": "login was sent to the wrong bucket",
            "severity": "high",
        }
    ]


def test_missing_config_file_names_that_file(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _call(
        cfg,
        "use_sample",
        {"sample": "travel"},
        {
            "ok": False,
            "issues": [
                {"field": "path", "level": "error", "message": "not a file: config.json"}
            ],
        },
    )
    items = _items(_text(cfg, "travel"))
    assert items == [
        {"what": "missing required file config.json", "kind": "file"}
    ]


def test_missing_zeus_url_is_an_env_item_and_secret_names_are_skipped(
    tmp_path: Path,
) -> None:
    cfg = _cfg(tmp_path)
    _call(
        cfg,
        "use_sample",
        {"sample": "beer"},
        {
            "ok": False,
            "missing_app_settings": ["ZEUS_URL", "ZEUS_PASSWORD", "LLM_API_KEY"],
            "missing_process_settings": [
                "ZEUS_URL",
                "ZEUS_BEARER_TOKEN",
                "XAI_API_KEY",
                "OPENAI_API_KEY",
            ],
            "app_env": {"missing_app_settings": ["ZEUS_URL", "ZEUS_PASSWORD"]},
        },
    )
    text = _text(cfg, "beer")
    assert _items(text) == [{"what": "ZEUS_URL", "kind": "env"}]
    for name in (
        "ZEUS_PASSWORD",
        "ZEUS_BEARER_TOKEN",
        "LLM_API_KEY",
        "XAI_API_KEY",
        "OPENAI_API_KEY",
    ):
        assert name not in text


def test_catalog_gaps_are_catalog_items_not_files(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _call(
        cfg,
        "use_sample",
        {"sample": "beer"},
        {
            "ok": False,
            "failure_class": "empty_tool_catalog",
            "gates": [{"failure_class": "stamp_fetch_failed"}],
            "issues": [{"level": "error", "message": f"not a file: {_CATALOG_PATH}"}],
        },
    )
    items = _items(_text(cfg, "beer"))
    assert items == [
        {"what": "live tool catalog is empty", "kind": "catalog"},
        {"what": "live stamp could not be fetched", "kind": "catalog"},
        {"what": f"missing catalog path {_CATALOG_PATH}", "kind": "catalog"},
    ]


def test_a_fourth_gap_is_dropped(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _project(cfg, "beer")
    _seal(cfg, "beer")
    _call(
        cfg,
        "website_green",
        {},
        {
            "ok": False,
            "failure_class": "auth_default_bucket",
            "issues": [{"level": "error", "message": "not a file: config.json"}],
            "missing_app_settings": ["ZEUS_URL"],
            "gates": [{"failure_class": "empty_tool_catalog"}],
        },
    )
    items = _items(_text(cfg, "beer"))
    assert items == [
        {"what": "missing required file config.json", "kind": "file"},
        {
            "what": "bucket on the hop is not the stored prereq bucket",
            "kind": "bucket",
            "why": "login was sent to the wrong bucket",
            "severity": "high",
        },
        {"what": "ZEUS_URL", "kind": "env"},
    ]
    assert "live tool catalog is empty" not in _text(cfg, "beer")


def test_secrets_and_session_ids_are_redacted(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _call(
        cfg,
        "use_sample",
        {"sample": "travel"},
        _red(
            "auth_failed",
            (
                f"password=s3cret bearer {_SECRET} {_XAI} "
                f"ZEUS_BEARER_TOKEN=tok_live_value LLM_API_KEY=app-secret-value "
                f"session_id={_SESSION} fix login"
            ),
        ),
    )
    text = _text(cfg, "travel")
    assert "s3cret" not in text
    assert _SECRET not in text
    assert _XAI not in text
    assert "tok_live_value" not in text
    assert "app-secret-value" not in text
    assert _SESSION not in text
    assert "[REDACTED]" in text
    assert "fix login" in text


def test_what_line_uses_the_stderr_message_cap(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    marker = "TAIL_SECRET_MARKER"
    _call(
        cfg,
        "use_sample",
        {"sample": "beer"},
        _red("auth_failed", ("n" * (MESSAGE_CAP + 50)) + marker),
    )
    text = _text(cfg, "beer")
    what = next(line for line in text.splitlines() if line.startswith("  - what:"))
    assert marker not in text
    assert len(what.removeprefix("  - what: ")) == MESSAGE_CAP


def test_section_41_drops_the_oldest(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    for index in range(wish.SECTION_CAP + 1):
        _call(cfg, "use_sample", {"sample": "beer"}, _red(message=f"mark-{index}"))
    text = _text(cfg, "beer")
    assert len(_sections(text)) == wish.SECTION_CAP
    assert "mark-0" not in text
    assert "mark-1" in text
    assert f"mark-{wish.SECTION_CAP}" in text
    assert text.startswith("# beer-sample wish\n")


def test_green_result_leaves_the_file_unchanged(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _call(cfg, "use_sample", {"sample": "beer"}, _red(message="keep"))
    path = cfg.state_dir / _WISH["beer"]
    before = path.read_bytes()
    assert _call(cfg, "use_sample", {"sample": "beer"}, {"ok": True, "written": True}) is None
    _project(cfg, "beer")
    _seal(cfg, "beer")
    assert _call(cfg, "readiness_check", {}, {"ok": True, "failure_class": "ignored"}) is None
    assert _call(cfg, "website_green", {}, {"overall": "pass"}) is None
    assert path.read_bytes() == before


def test_append_leaves_build_and_support_byte_identical(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _project(cfg, "travel")
    build = _seal(cfg, "travel", "SECRET_BUILD_BODY\n")
    support = cfg.state_dir / _SUPPORT["travel"]
    support.write_text("# travel-sample support\n\nkeep\n", encoding="utf-8")
    before_build = build.read_bytes()
    before_support = support.read_bytes()
    _call(cfg, "smoke_test_zeus", {}, _red("zeus_unreachable", "down"))
    _call(cfg, "smoke_test_agent", {}, _red("llm_key_missing", "set the key"))
    _call(cfg, "website_green", {}, {"overall": "fail", "failure_class": "health_timeout"})
    assert build.read_bytes() == before_build
    assert support.read_bytes() == before_support
    assert [item["what"] for item in _items(_text(cfg, "travel"))] == [
        "down",
        "set the key",
        "health_timeout",
    ]


def test_foreign_heading_directory_and_write_failure_leave_the_tool_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _cfg(tmp_path)
    cfg.state_dir.mkdir(parents=True)
    foreign = cfg.state_dir / _WISH["beer"]
    foreign.write_text("keep me\n", encoding="utf-8")
    assert _call(cfg, "use_sample", {"sample": "beer"}, _red()) is None
    assert foreign.read_text(encoding="utf-8") == "keep me\n"

    blocked = cfg.state_dir / _WISH["travel"]
    blocked.mkdir()
    assert _call(cfg, "use_sample", {"sample": "travel"}, _red()) is None
    assert blocked.is_dir()
    assert not any(blocked.iterdir())

    def _boom(*args: Any, **kwargs: Any) -> bool:
        raise OSError("disk")

    monkeypatch.setattr(wish, "write_state_text", _boom)
    assert _call(cfg, "use_sample", {"sample": "demo_yelp"}, _red()) is None
    assert not (cfg.state_dir / _WISH["yelp-demo"]).exists()


def test_red_readiness_payload_names_the_file_and_not_the_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(state))
    cfg = _cfg(tmp_path)
    _project(cfg, "beer")
    _seal(cfg, "beer")

    def readiness_check() -> dict[str, Any]:
        return {
            "ok": False,
            "failure_class": "auth_failed",
            "next_action": "fix login",
        }

    out = _wrap_tool(readiness_check)()
    assert out["ok"] is False
    assert out["failure_class"] == "auth_failed"
    assert out["next_action"] == "fix login"
    assert out["wish_file"] == str(state / _WISH["beer"])
    assert "wish_i_knew" not in out
    assert "fix login" in _text(cfg, "beer")


def test_green_payload_gains_neither_wish_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(state))
    cfg = _cfg(tmp_path)
    _project(cfg, "beer")
    _seal(cfg, "beer")

    def readiness_check() -> dict[str, Any]:
        return {"ok": True, "next_action": "continue"}

    out = _wrap_tool(readiness_check)()
    assert out["ok"] is True
    assert "wish_file" not in out
    assert "wish_i_knew" not in out
    assert not (state / _WISH["beer"]).exists()


def test_symlink_wish_path_is_left_in_place_and_the_tool_returns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(state))
    cfg = _cfg(tmp_path)
    _project(cfg, "beer")
    _seal(cfg, "beer")
    outside = tmp_path / "outside.md"
    outside.write_text("outside\n", encoding="utf-8")
    link = state / _WISH["beer"]
    link.symlink_to(outside)

    def readiness_check() -> dict[str, Any]:
        return {"ok": False, "failure_class": "auth_failed", "next_action": "fix login"}

    out = _wrap_tool(readiness_check)()
    assert out["ok"] is False
    assert out["failure_class"] == "auth_failed"
    assert "wish_file" not in out
    assert "wish_i_knew" not in out
    assert link.is_symlink()
    assert outside.read_text(encoding="utf-8") == "outside\n"


def test_wrapper_wish_failure_still_returns_the_tool_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))

    def readiness_check() -> dict[str, Any]:
        return {"ok": False, "failure_class": "auth_failed", "next_action": "fix login"}

    def _boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("wish disk")

    monkeypatch.setattr("zeus_dev_helper_mcp.server.observe_sample_wish", _boom)
    out = _wrap_tool(readiness_check)()
    assert out["ok"] is False
    assert out["next_action"] == "fix login"
    assert "wish_file" not in out


def test_smoke_execution_failure_includes_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(state))
    cfg = _cfg(tmp_path)
    _project(cfg, "travel")
    _seal(cfg, "travel")

    def smoke_test_zeus() -> dict[str, Any]:
        return {"ok": False, "failure_class": "zeus_unreachable", "next_action": "retry"}

    with pytest.raises(Exception, match="zeus_unreachable") as caught:
        _wrap_tool(smoke_test_zeus)()
    message = str(caught.value)
    assert str(state / _WISH["travel"]) in message
    assert "wish_i_knew" not in message
    assert "retry" in _text(cfg, "travel")


def test_raised_use_sample_appends_and_is_reraised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(state))

    def use_sample(sample: str = "travel") -> dict[str, Any]:
        raise RuntimeError("clone failed")

    with pytest.raises(RuntimeError, match="^clone failed$"):
        _wrap_tool(use_sample)(sample="beer")
    text = (state / _WISH["beer"]).read_text(encoding="utf-8")
    assert "failure_class: exception" in text
    assert "clone failed" in text
    assert not (state / _BUILD["beer"]).exists()


def test_wrapper_scaffold_and_diagnose_write_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(state))
    cfg = _cfg(tmp_path)
    _project(cfg, "beer")
    _seal(cfg, "beer")

    def scaffold_app(target_dir: str = "") -> dict[str, Any]:
        return {"ok": False, "failure_class": "refused"}

    def diagnose_error(symptom: str = "") -> dict[str, Any]:
        return {"ok": False, "failure_class": "auth_failed", "next_action": "inspect"}

    def use_sample(sample: str = "travel") -> dict[str, Any]:
        return {"ok": False, "failure_class": "refused", "next_action": "no"}

    with pytest.raises(Exception, match="refused"):
        _wrap_tool(scaffold_app)(target_dir=str(tmp_path))
    diagnosed = _wrap_tool(diagnose_error)(symptom="401")
    assert diagnosed["ok"] is False
    assert "wish_file" not in diagnosed
    for sample in ("api", "yelp"):
        out = _wrap_tool(use_sample)(sample=sample)
        assert out["ok"] is False
        assert "wish_file" not in out
    assert list(state.glob("*-wish.md")) == []


def test_support_pack_includes_the_last_eight_wish_sections_and_writes_nothing(
    tmp_path: Path,
) -> None:
    cfg = _cfg(tmp_path)
    _project(cfg, "beer")
    _seal(cfg, "beer", "SECRET_BUILD_BODY\n")
    (cfg.state_dir / _SUPPORT["beer"]).write_text(
        "# beer-sample support\n\nkeep\n",
        encoding="utf-8",
    )
    for index in range(10):
        _call(cfg, "use_sample", {"sample": "beer"}, _red(message=f"mark-{index}"))
    before = {path.name: path.read_bytes() for path in cfg.state_dir.iterdir()}
    out = journal.sample_support_pack(cfg, "beer")
    after = {path.name: path.read_bytes() for path in cfg.state_dir.iterdir()}
    assert before == after
    text = out["markdown"]
    assert out["ok"] is True
    assert text.index("## Support journal") < text.index("## Wish journal")
    wish_block = text.split("## Wish journal", 1)[1]
    assert "mark-0" not in wish_block
    assert "mark-1" not in wish_block
    assert "mark-2" in wish_block
    assert "mark-9" in wish_block
    assert "## 10. use_sample" in wish_block
    assert "## 2. use_sample" not in wish_block
    assert "SECRET_BUILD_BODY" not in text
    for sample in ("api", "yelp", ""):
        refused = journal.sample_support_pack(cfg, sample)
        assert refused["ok"] is False
        assert refused["failure_class"] == "sample_not_supported"
        assert refused["markdown"] == ""
    assert {path.name: path.read_bytes() for path in cfg.state_dir.iterdir()} == before


def test_red_gates_after_the_creation_log_append_one_section(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _project(cfg, "yelp-demo")
    build = _seal(cfg, "yelp-demo", "SEALED\n")
    before = build.read_bytes()
    gates = (
        "readiness_check",
        "validate_env",
        "load_process_login",
        "verify_local_setup",
        "smoke_test_zeus",
        "smoke_test_agent",
        "website_green",
    )
    for name in gates:
        _call(cfg, name, {}, _red(message=name))
    assert _sections(_text(cfg, "yelp-demo")) == [
        f"## {index}. {name}" for index, name in enumerate(gates, start=1)
    ]
    assert build.read_bytes() == before
    assert not (cfg.state_dir / _WISH["beer"]).exists()
