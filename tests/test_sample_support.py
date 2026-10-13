"""ZDM-25: append-only support journal and the read-only paste."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from zeus_dev_helper_mcp import __version__
from zeus_dev_helper_mcp import sample_support as journal
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.error_log import EVENT
from zeus_dev_helper_mcp.server import _wrap_tool, sample_support_pack
from zeus_dev_helper_mcp.toolsets import (
    CORE_CAP,
    DEFAULT_CORE_TOOLS,
    TOOL_META_BY_NAME,
    default_core_count,
)

NOW = datetime(2026, 10, 13, 15, 4, 5, tzinfo=UTC)
_STAMP = "2026-10-13T15:04:05Z"
_SESSION = "11111111-1111-1111-1111-111111111111"
_CATALOG = "UNIQUE_CATALOG_DOCUMENT_BODY"
_PROMPT = "UNIQUE_PROMPT_BODY"
_SECRET = "sk-live-abcdefghijklmnopqrstuvwxyz"
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


@pytest.fixture(autouse=True)
def _quiet_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "DEMO_BEER_SAMPLE_DIR",
        "DEMO_TRAVEL_SAMPLE_DIR",
        "DEMO_YELP_SAMPLE_DIR",
        "LLM_API_KEY",
        "XAI_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


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
) -> None:
    journal.observe_sample_support(
        cfg,
        tool,
        args or {},
        result,
        exc=exc,
        now=now,
    )


def _project(cfg: HelperConfig, sample: str) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {"goal": "single-agent", "sample": sample},
        "phases": [
            {
                "id": "0_intent",
                "items": [{"id": "0.1", "title": "Choose", "status": "todo"}],
            },
            {
                "id": "1_prereqs",
                "items": [
                    {
                        "id": "1.2",
                        "title": "ZEUS_URL and LLM key available",
                        "status": "todo",
                        "evidence": f"session_id={_SESSION} password=s3cret",
                    }
                ],
            },
            {
                "id": "2_platform",
                "items": [{"id": "2.1", "title": "Reachable", "status": "done"}],
            },
            {
                "id": "5_green",
                "items": [
                    {
                        "id": "5.1",
                        "title": "smoke_test_zeus",
                        "status": "blocked",
                        "evidence": "auth_failed",
                    }
                ],
            },
            {
                "id": "6_customize",
                "items": [{"id": "6.1", "title": "Hooks", "status": "todo"}],
            },
            {
                "id": "7_prodish",
                "items": [{"id": "7.1", "title": "Prod", "status": "blocked"}],
            },
        ],
    }
    (cfg.state_dir / "checklist.json").write_text(json.dumps(payload), encoding="utf-8")


def _seal(cfg: HelperConfig, kind: str, body: str = "SECRET_BUILD_BODY\n") -> Path:
    path = cfg.state_dir / _BUILD[kind]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _text(cfg: HelperConfig, kind: str) -> str:
    return (cfg.state_dir / _SUPPORT[kind]).read_text(encoding="utf-8")


def _sections(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("## ")]


def _red(failure: str = "auth_failed", message: str = "fix login") -> dict[str, Any]:
    return {
        "ok": False,
        "failure_class": failure,
        "next_action": message,
        "catalog": _CATALOG,
        "prompt": _PROMPT,
        "body": "UNIQUE_BODY",
        "session_id": _SESSION,
    }


def test_failed_use_sample_is_on_disk_after_the_process_exits(tmp_path: Path) -> None:
    state = tmp_path / "state"
    src = Path(__file__).resolve().parents[1] / "src"
    code = (
        "import os\n"
        "from zeus_dev_helper_mcp.server import _wrap_tool\n"
        "def use_sample(sample: str = 'travel') -> dict:\n"
        "    raise RuntimeError(\n"
        "        'password=s3cret bearer abcdefghijklmnop "
        f"session_id={_SESSION}'\n"
        "    )\n"
        "try:\n"
        "    _wrap_tool(use_sample)(sample='beer')\n"
        "except RuntimeError:\n"
        "    os._exit(3)\n"
        "os._exit(0)\n"
    )
    env = os.environ.copy()
    env["ZEUS_DEV_HELPER_STATE_DIR"] = str(state)
    env["PYTHONPATH"] = str(src) + os.pathsep + env.get("PYTHONPATH", "")
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 3, completed.stderr
    text = (state / "beer-sample-support.md").read_text(encoding="utf-8")
    assert "failure_class: exception" in text
    assert "s3cret" not in text
    assert "abcdefghijklmnop" not in text
    assert _SESSION not in text
    assert "[REDACTED]" in text
    assert not (state / "beer-sample-build.md").exists()


def test_use_sample_failure_journals_before_the_creation_log_seals(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _call(
        cfg,
        "use_sample",
        {"sample": "beer", "question": _PROMPT},
        _red("login_not_in_process", f"bearer {_SECRET} password=s3cret"),
    )
    text = _text(cfg, "beer")
    assert "## 1. use_sample" in text
    assert f"- Helper version: {__version__}" in text
    assert f"- UTC timestamp: {_STAMP}" in text
    assert "failure_class: login_not_in_process" in text
    assert _SECRET not in text
    assert "s3cret" not in text
    assert _PROMPT not in text
    assert _CATALOG not in text
    assert _SESSION not in text
    assert not (cfg.state_dir / _BUILD["beer"]).exists()


def test_three_samples_and_yelp_aliases_get_their_own_files(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _call(cfg, "use_sample", {"sample": "beer"}, _red())
    _call(cfg, "use_sample", {"sample": "travel"}, _red())
    for alias in ("demo_yelp", "yelp-demo", "demo-yelp", "yelp_demo", "yelpdemo"):
        _call(cfg, "use_sample", {"sample": alias}, _red(message=alias))
    assert (cfg.state_dir / _SUPPORT["beer"]).is_file()
    assert (cfg.state_dir / _SUPPORT["travel"]).is_file()
    yelp = _text(cfg, "yelp-demo")
    assert _sections(yelp) == [f"## {index}. use_sample" for index in range(1, 6)]
    assert "demo-yelp" in yelp
    names = sorted(path.name for path in cfg.state_dir.glob("*.md"))
    assert names == [
        "beer-sample-support.md",
        "travel-sample-support.md",
        "yelp-demo-support.md",
    ]


def test_api_bare_yelp_scaffold_and_diagnose_stay_out(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _seal(cfg, "beer")
    _project(cfg, "beer")
    _call(cfg, "use_sample", {"sample": "api"}, _red())
    _call(cfg, "use_sample", {"sample": "yelp"}, _red())
    _call(cfg, "use_sample", {"sample": "catalog"}, _red())
    _call(cfg, "scaffold_app", {"app_kind": "api"}, _red())
    _call(cfg, "diagnose_error", {"symptom": "401"}, _red())
    _call(cfg, "diagnose_error", {}, None, exc=RuntimeError("boom"))
    assert list(cfg.state_dir.glob("*-support.md")) == []


def test_green_results_and_a_gate_before_seal_add_nothing(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _project(cfg, "beer")
    _call(cfg, "use_sample", {"sample": "beer"}, {"ok": True, "written": True})
    _call(cfg, "readiness_check", {}, _red())
    _call(cfg, "readiness_check", {}, {"ok": True, "failure_class": "ignored"})
    assert list(cfg.state_dir.glob("*-support.md")) == []


def test_red_gates_after_seal_append_and_leave_the_build_file(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _project(cfg, "demo_yelp")
    build = _seal(cfg, "yelp-demo", "SEALED\n")
    before = build.read_bytes()
    gates = (
        ("readiness_check", {"ok": False, "primary_failure_class": "auth_failed", "next_action": "login"}),
        ("validate_env", {
            "ok": False,
            "issues": [
                {"level": "warn", "failure_class": "catalog_down", "message": "templates"},
                {"level": "error", "failure_class": "llm_key_missing", "message": "No LLM key"},
            ],
        }),
        ("load_process_login", _red("login_not_in_process", "mode 600")),
        ("verify_local_setup", _red("llm_key_missing", "set the app key")),
        ("smoke_test_zeus", _red("zeus_unreachable", "down")),
        ("smoke_test_agent", _red("llm_key_missing", "set the process key")),
        ("website_green", {"overall": "fail", "failure_class": "health_timeout", "error": "page down"}),
    )
    for tool, result in gates:
        _call(cfg, tool, {}, result)
    text = _text(cfg, "yelp-demo")
    assert _sections(text) == [f"## {index}. {name}" for index, (name, _) in enumerate(gates, start=1)]
    assert "failure_class: llm_key_missing" in text
    assert "failure_class: health_timeout" in text
    assert "templates" not in text
    assert build.read_bytes() == before
    assert not (cfg.state_dir / _SUPPORT["beer"]).exists()


def test_gate_without_a_project_sample_or_a_sealed_log_adds_nothing(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _call(cfg, "readiness_check", {}, _red())
    _seal(cfg, "travel")
    _call(cfg, "website_green", {}, _red())
    assert list(cfg.state_dir.glob("*-support.md")) == []


def test_blank_use_sample_argument_follows_the_travel_default(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _call(cfg, "use_sample", {}, _red())
    _call(cfg, "use_sample", {"sample": "  "}, _red())
    assert _sections(_text(cfg, "travel")) == ["## 1. use_sample", "## 2. use_sample"]


def test_section_cap_keeps_the_newest_forty(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    for index in range(journal.SECTION_CAP + 1):
        _call(cfg, "use_sample", {"sample": "beer"}, _red(message=f"mark-{index}"))
    text = _text(cfg, "beer")
    assert len(_sections(text)) == journal.SECTION_CAP
    assert "mark-0" not in text
    assert f"mark-{journal.SECTION_CAP}" in text
    assert "mark-1" in text
    assert text.startswith("# beer-sample support\n")


def test_message_cap_matches_the_stderr_redaction_limit(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    marker = "TAIL_SECRET_MARKER"
    _call(
        cfg,
        "use_sample",
        {"sample": "travel"},
        _red(message=("n" * (journal.MESSAGE_CAP + 50)) + marker),
    )
    text = _text(cfg, "travel")
    message = next(line for line in text.splitlines() if line.startswith("- message:"))
    assert marker not in text
    assert len(message.removeprefix("- message: ")) == journal.MESSAGE_CAP


def test_naive_timestamp_is_utc_and_a_raised_gate_uses_exception(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    _seal(cfg, "beer")
    _project(cfg, "beer")
    _call(
        cfg,
        "readiness_check",
        {},
        None,
        exc=RuntimeError(f"session_id={_SESSION} exploded"),
        now=datetime(2026, 10, 13, 1, 2, 3),  # noqa: DTZ001 — naive input is treated as UTC
    )
    text = _text(cfg, "beer")
    assert "- UTC timestamp: 2026-10-13T01:02:03Z" in text
    assert "failure_class: exception" in text
    assert _SESSION not in text
    assert "exploded" in text


def test_foreign_file_symlink_and_directory_are_left_alone(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.state_dir.mkdir(parents=True)
    foreign = cfg.state_dir / _SUPPORT["beer"]
    foreign.write_text("keep me\n", encoding="utf-8")
    _call(cfg, "use_sample", {"sample": "beer"}, _red())
    assert foreign.read_text(encoding="utf-8") == "keep me\n"

    outside = tmp_path / "outside.md"
    outside.write_text("outside\n", encoding="utf-8")
    link = cfg.state_dir / _SUPPORT["travel"]
    link.symlink_to(outside)
    _call(cfg, "use_sample", {"sample": "travel"}, _red())
    assert link.is_symlink()
    assert outside.read_text(encoding="utf-8") == "outside\n"

    blocked = cfg.state_dir / _SUPPORT["yelp-demo"]
    blocked.mkdir()
    _call(cfg, "use_sample", {"sample": "demo_yelp"}, _red())
    assert blocked.is_dir()


def test_a_journal_write_failure_does_not_raise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _cfg(tmp_path)

    def _boom(*args: Any, **kwargs: Any) -> bool:
        raise OSError("disk")

    monkeypatch.setattr(journal, "_write_text", _boom)
    _call(cfg, "use_sample", {"sample": "beer"}, _red())
    assert not (cfg.state_dir / _SUPPORT["beer"]).exists()


def test_wrapper_red_readiness_keeps_stderr_and_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    cfg = _cfg(tmp_path)
    _project(cfg, "beer")
    build = _seal(cfg, "beer")
    before = build.read_bytes()

    def readiness_check() -> dict[str, Any]:
        return {
            "ok": False,
            "primary_failure_class": "auth_failed",
            "next_action": "fix login",
            "session_id": _SESSION,
            "catalog": _CATALOG,
        }

    out = _wrap_tool(readiness_check)()
    assert out["ok"] is False
    assert EVENT not in capsys.readouterr().err
    text = _text(cfg, "beer")
    assert "failure_class: auth_failed" in text
    assert "fix login" in text
    assert _SESSION not in text
    assert _CATALOG not in text
    assert build.read_bytes() == before
    rows = [
        json.loads(line)
        for line in (cfg.state_dir / "metrics.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [row["tool"] for row in rows] == ["readiness_check"]
    assert all(set(row) == {"ts", "event", "tool"} for row in rows)


def test_wrapper_smoke_still_logs_stderr_and_journals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    cfg = _cfg(tmp_path)
    _project(cfg, "travel")
    build = _seal(cfg, "travel")
    before = build.read_bytes()

    def smoke_test_zeus() -> dict[str, Any]:
        return {"ok": False, "failure_class": "zeus_unreachable", "error": "down", "session_id": _SESSION}

    with pytest.raises(Exception, match="zeus_unreachable"):
        _wrap_tool(smoke_test_zeus)()
    assert EVENT in capsys.readouterr().err
    assert "failure_class: zeus_unreachable" in _text(cfg, "travel")
    assert _SESSION not in _text(cfg, "travel")
    assert build.read_bytes() == before


def test_wrapper_ignores_a_journal_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))

    def readiness_check() -> dict[str, Any]:
        return {"ok": False, "failure_class": "auth_failed"}

    def _boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("journal")

    monkeypatch.setattr("zeus_dev_helper_mcp.server.observe_sample_support", _boom)
    assert _wrap_tool(readiness_check)()["ok"] is False


def test_support_pack_is_a_read_only_core_tool() -> None:
    assert "sample_support_pack" in DEFAULT_CORE_TOOLS
    assert default_core_count() == 16
    assert default_core_count() <= CORE_CAP
    meta = TOOL_META_BY_NAME["sample_support_pack"]
    assert meta.read_only is True
    assert meta.destructive is False
    assert meta.open_world is False
    source = Path(journal.__file__).read_text(encoding="utf-8")
    assert "httpx" not in source
    assert "urlopen" not in source


def test_support_pack_refuses_samples_outside_the_journal(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    for sample in ("", "api", "yelp", "catalog"):
        out = journal.sample_support_pack(cfg, sample)
        assert out["ok"] is False
        assert out["failure_class"] == "sample_not_supported"
        assert out["markdown"] == ""
    assert not cfg.state_dir.exists()


def test_support_pack_paste_has_the_gate_facts_and_no_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _cfg(tmp_path)
    app = tmp_path / "demo_beer_sample"
    app.mkdir()
    (app / "config.json").write_text(
        json.dumps({"llm": {"api_key_env": "LLM_API_KEY"}}),
        encoding="utf-8",
    )
    (app / ".env").write_text("LLM_API_KEY=app-secret-value\n", encoding="utf-8")
    monkeypatch.setenv("DEMO_BEER_SAMPLE_DIR", str(app))
    monkeypatch.setenv("LLM_API_KEY", "process-secret-value")
    _project(cfg, "beer")
    build = _seal(cfg, "beer", "SECRET_BUILD_BODY\n")
    (cfg.state_dir / "prereqs.json").write_text(
        json.dumps(
            {
                "zeus_url": "http://user:s3cret@192.168.0.219:8080/v1",
                "auth_mode": "basic",
                "bucket": "beer-sample",
                "scope": "_default",
                "has_llm_key": True,
                "has_bearer": False,
                "has_password": True,
                "password": "hunter2",
            }
        ),
        encoding="utf-8",
    )
    (cfg.state_dir / "website_green.json").write_text(
        json.dumps({"ok": False, "failure_class": "health_timeout", "session_id": _SESSION}),
        encoding="utf-8",
    )
    (cfg.state_dir / "last_smoke_agent.json").write_text(
        json.dumps({"session_id": _SESSION, "prompt": _PROMPT}),
        encoding="utf-8",
    )
    metrics = [{"event": "start_project", "secret": "hunter2"}]
    metrics.append({"event": "not-json"})
    metrics.extend(
        {"ts": index, "event": "tool_call", "tool": "readiness_check", "password": "hunter2"}
        for index in range(journal.METRIC_TAIL + 1)
    )
    metrics.append({"event": "tool_call", "tool": "password=hunter2"})
    (cfg.state_dir / "metrics.jsonl").write_text(
        "\n".join(json.dumps(row) if isinstance(row, dict) else str(row) for row in metrics) + "\n",
        encoding="utf-8",
    )
    for index in range(10):
        _call(cfg, "use_sample", {"sample": "beer"}, _red(message=f"mark-{index}"))

    before = {path.name: path.read_bytes() for path in cfg.state_dir.iterdir()}
    out = journal.sample_support_pack(cfg, "beer-sample")
    after = {path.name: path.read_bytes() for path in cfg.state_dir.iterdir()}
    assert before == after
    text = out["markdown"]
    assert out["ok"] is True
    assert out["sample"] == "beer"
    assert "- sample: beer" in text
    assert f"- bound directory: {app}" in text
    assert "- directory on disk: yes" in text
    assert f"- Helper version: {__version__}" in text
    assert f"- creation log: {build}" in text
    assert "SECRET_BUILD_BODY" not in text
    assert "- origin: http://192.168.0.219:8080" in text
    assert "- auth_mode: basic" in text
    assert "- bucket: beer-sample" in text
    assert "- scope: _default" in text
    assert "- has_llm_key: true" in text
    assert "- has_bearer: false" in text
    assert "- has_username: absent" in text
    assert "- has_password: true" in text
    assert "- 1.2 todo: ZEUS_URL and LLM key available" in text
    assert "evidence: session_id=[REDACTED] password=[REDACTED]" in text
    assert "- 5.1 blocked: smoke_test_zeus evidence: auth_failed" in text
    assert "- 0.1 " not in text
    assert "- 2.1 " not in text
    assert "- 6.1 " not in text
    assert "- 7.1 " not in text
    assert "- website_green class: health_timeout" in text
    assert "- last_smoke_agent.json: present" in text
    assert "- process LLM key: present" in text
    assert "- app .env key: present" in text
    assert "- llm.api_key_env: LLM_API_KEY" in text
    assert "API port" not in text
    assert "- readiness_check" in text
    assert "start_project" not in text
    assert "mark-0" not in text
    assert "mark-1" not in text
    assert "mark-2" in text
    assert "mark-9" in text
    assert "## 9. use_sample" in text
    for secret in ("s3cret", "hunter2", "app-secret-value", "process-secret-value", _SESSION, _PROMPT):
        assert secret not in text


def test_support_pack_reports_a_missing_log_and_a_secret_api_key_env(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    app = tmp_path / "demo_yelp"
    app.mkdir()
    (app / "config.json").write_text(
        json.dumps({"llm_provider": {"api_key_env": _SECRET}}),
        encoding="utf-8",
    )
    monkeypatch_dir = app
    os.environ["DEMO_YELP_SAMPLE_DIR"] = str(monkeypatch_dir)
    try:
        out = journal.sample_support_pack(cfg, "yelp-demo")
    finally:
        os.environ.pop("DEMO_YELP_SAMPLE_DIR", None)
    text = out["markdown"]
    assert out["sample"] == "yelp-demo"
    assert "- creation log: never sealed" in text
    assert "yelp-demo-build.md" not in text
    assert "- directory on disk: yes" in text
    assert "- process LLM key: absent" in text
    assert "- app .env key: absent" in text
    assert "- llm.api_key_env: not a variable name" in text
    assert "- API port: 5000" in text
    assert "- frontend port: 5173" in text
    assert "- last_smoke_agent.json: absent" in text
    assert "- website_green class: none" in text
    assert "- (none)" in text
    assert _SECRET not in text
    assert not cfg.state_dir.exists()


def test_support_pack_omits_a_hub_origin_and_an_unsealed_symlink(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg.state_dir.mkdir()
    (cfg.state_dir / "prereqs.json").write_text(
        json.dumps({"zeus_url": "http://user:s3cret@zeus.internal:9091", "has_llm_key": "yes"}),
        encoding="utf-8",
    )
    outside = tmp_path / "build.md"
    outside.write_text("SECRET_BUILD_BODY\n", encoding="utf-8")
    (cfg.state_dir / _BUILD["travel"]).symlink_to(outside)
    text = journal.sample_support_pack(cfg, "travel")["markdown"]
    assert "- origin: omitted" in text
    assert "- has_llm_key: absent" in text
    assert "- creation log: never sealed" in text
    assert "- bound directory: (none)" in text
    assert "- directory on disk: no" in text
    assert "s3cret" not in text
    assert "SECRET_BUILD_BODY" not in text
    assert ":9091" not in text


def test_wrapper_support_pack_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    (state / "note.txt").write_text("keep\n", encoding="utf-8")
    before = {path.name: path.read_bytes() for path in state.iterdir()}
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(state))
    out = _wrap_tool(sample_support_pack)(sample="travel")
    after = {path.name: path.read_bytes() for path in state.iterdir()}
    assert out["ok"] is True
    assert "never sealed" in out["markdown"]
    assert before == after
    assert not (state / "metrics.jsonl").exists()


def test_bound_directory_that_is_not_on_disk_stays_in_the_paste(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _cfg(tmp_path)
    missing = tmp_path / "gone"
    monkeypatch.setenv("DEMO_TRAVEL_SAMPLE_DIR", str(missing))
    text = journal.sample_support_pack(cfg, "travel")["markdown"]
    assert f"- bound directory: {missing}" in text
    assert "- directory on disk: no" in text
    assert "- app .env key: absent" in text
    assert "- llm.api_key_env: (none)" in text


def test_unreadable_state_files_do_not_break_the_paste(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _cfg(tmp_path)
    cfg.state_dir.mkdir()
    for name in ("prereqs.json", "checklist.json", "website_green.json", "metrics.jsonl"):
        (cfg.state_dir / name).write_text("{", encoding="utf-8")
    (cfg.state_dir / "checklist.json").write_text("[]", encoding="utf-8")

    def _boom(self: Path, *args: Any, **kwargs: Any) -> str:
        raise OSError("read")

    monkeypatch.setattr(Path, "read_text", _boom)
    text = journal.sample_support_pack(cfg, "beer")["markdown"]
    assert "- origin: omitted" in text
    assert "- website_green class: none" in text
    assert "## Recent tools" in text
    assert "- (none)" in text
