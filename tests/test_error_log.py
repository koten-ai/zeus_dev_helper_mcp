"""ZDM-11: one family-shaped stderr line per Helper tool failure."""

from __future__ import annotations

import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from zeus_dev_helper_mcp import readiness
from zeus_dev_helper_mcp.error_log import (
    EVENT,
    format_failure_line,
    package_source,
    scrub_text,
)
from zeus_dev_helper_mcp.mcp_compat import ToolError
from zeus_dev_helper_mcp.server import _wrap_tool

_LINE_RE = (
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z "
    r"\[error\] zeus_dev_helper\.tool\.failed "
)
_EXAMPLE = (
    "2026-09-23T18:04:11.234Z [error] zeus_dev_helper.tool.failed "
    'error.message="public API health check failed" '
    "error.type=network_timeout "
    "source.file=zeus_dev_helper_mcp/readiness.py "
    "source.line=118 result=error tool=readiness_check "
    "req_id=7f3ac2e1-4b0a-4c2e-9a11-0c5d8e2f6a10 "
    "session.id=dev http.status_code=0 "
    "zeus.url=http://192.168.0.219:8080"
)


@pytest.fixture
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))


def _compile_tool(name: str, body: str, filename: str) -> Any:
    source = f"def {name}():\n    {body}\n"
    namespace: dict[str, Any] = {}
    exec(compile(source, filename, "exec"), namespace)  # noqa: S102
    return namespace[name]


def _failure_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if EVENT in line]


def test_rendered_line_matches_family_example() -> None:
    line = format_failure_line(
        tool="readiness_check",
        message="public API health check failed",
        error_type="network_timeout",
        source_file="zeus_dev_helper_mcp/readiness.py",
        source_line=118,
        req_id="7f3ac2e1-4b0a-4c2e-9a11-0c5d8e2f6a10",
        session_id="dev",
        status_code=0,
        zeus_url="http://user:secret@192.168.0.219:8080/v1/beer",
        now=datetime(2026, 9, 23, 18, 4, 11, 234000, tzinfo=UTC),
    )
    assert line == _EXAMPLE
    assert re.match(_LINE_RE, line)
    assert "source.file=zeus_dev_helper_mcp/" in line
    assert "source.line=118" in line
    assert "error.code" not in line
    assert "/home/" not in line
    assert "/Users/" not in line
    assert "src/zeus_dev_helper_mcp" not in line
    assert "user:secret" not in line
    assert "\n" not in line


def test_package_source_keeps_import_package() -> None:
    absolute = (
        "/home/michael/koten-ai/zeus_dev_helper_mcp/src/"
        "zeus_dev_helper_mcp/readiness.py"
    )
    windows = r"C:\Users\me\src\zeus_dev_helper_mcp\readiness.py"
    assert package_source(absolute) == "zeus_dev_helper_mcp/readiness.py"
    assert package_source(windows) == "zeus_dev_helper_mcp/readiness.py"
    assert package_source("src/zeus_dev_helper_mcp/server.py") == (
        "zeus_dev_helper_mcp/server.py"
    )
    assert package_source("/home/michael/secret.py") == ""
    assert package_source("zeus_dev_helper_mcp/foo/../server.py") == ""
    assert package_source(
        "/home/michael/koten-ai/zeus_dev_helper_mcp/tests/test_error_log.py"
    ) == ""
    live = package_source(readiness.__file__)
    assert live == "zeus_dev_helper_mcp/readiness.py"
    assert not live.startswith("/")
    assert "src/zeus_dev_helper_mcp" not in live


def test_bearer_token_is_redacted() -> None:
    line = format_failure_line(
        tool="readiness_check",
        message="Authorization: Bearer super-secret-value",
        error_type="exception",
        source_file="zeus_dev_helper_mcp/readiness.py",
        source_line=12,
    )
    assert 'error.message="[REDACTED]"' in line
    assert "super-secret-value" not in line
    assert "Bearer" not in line
    assert scrub_text("bad password=hunter2 now") == "bad password=[REDACTED] now"


def test_newlines_stay_on_one_physical_line() -> None:
    line = format_failure_line(
        tool="smoke_test_zeus",
        message="public API\nhealth check failed",
        error_type="network_timeout",
        source_file="zeus_dev_helper_mcp/smoke.py",
        source_line=4,
    )
    assert "\n" not in line
    assert 'error.message="public API health check failed"' in line


def test_hub_url_and_missing_source_are_omitted() -> None:
    line = format_failure_line(
        tool="readiness_check",
        message="hub",
        zeus_url="http://127.0.0.1:9091",
        source_file="/tmp/not_a_package.py",
        source_line=0,
    )
    assert "zeus.url" not in line
    assert ":9091" not in line
    assert "source.file=" not in line
    assert "source.line=" not in line
    assert "error.code" not in line


def test_writer_does_not_write_the_line_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    from zeus_dev_helper_mcp.error_log import emit_line

    root = logging.getLogger()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    previous = root.level
    root.setLevel(logging.ERROR)
    root.addHandler(handler)
    try:
        line = format_failure_line(
            tool="readiness_check",
            message="Authorization: Bearer super-secret-value",
            error_type="network_timeout",
            source_file=readiness.__file__,
            source_line=118,
        )
        emit_line(line)
        captured = capsys.readouterr()
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)
    assert EVENT in captured.err
    assert EVENT not in captured.out
    assert "super-secret-value" not in captured.err
    source = Path(readiness.__file__).with_name("error_log.py").read_text()
    assert "basicConfig(" not in source


def test_wrap_tool_execution_failure_logs_stub_module_then_raises(
    capsys: pytest.CaptureFixture[str],
    isolated_state: None,
) -> None:
    fn = _compile_tool(
        "readiness_check",
        "return {'ok': False, 'failure_class': 'network_timeout'}",
        readiness.__file__,
    )
    wrapped = _wrap_tool(fn)
    expected = ToolError if ToolError is not None else RuntimeError
    with pytest.raises(expected):
        wrapped()
    captured = capsys.readouterr()
    lines = _failure_lines(captured.err)
    assert len(lines) == 1
    line = lines[0]
    assert re.match(_LINE_RE, line)
    assert f"source.file={package_source(fn.__code__.co_filename)}" in line
    assert "source.file=zeus_dev_helper_mcp/readiness.py" in line
    assert "source.file=zeus_dev_helper_mcp/server.py" not in line
    assert "source.line=" in line
    assert "source.line=0" not in line
    assert "error.type=network_timeout" in line
    assert "tool=readiness_check" in line
    assert "result=error" in line
    assert "error.code" not in line
    assert "/home/" not in line
    assert "/Users/" not in line
    assert "src/zeus_dev_helper_mcp" not in line
    assert EVENT not in captured.out


def test_exception_source_is_the_tool_module_not_server(
    capsys: pytest.CaptureFixture[str],
    isolated_state: None,
) -> None:
    fn = _compile_tool(
        "explode_probe",
        "raise RuntimeError('probe failed')",
        readiness.__file__,
    )
    wrapped = _wrap_tool(fn)
    with pytest.raises(RuntimeError, match="probe failed"):
        wrapped()
    captured = capsys.readouterr()
    lines = _failure_lines(captured.err)
    assert len(lines) == 1
    line = lines[0]
    assert "source.file=zeus_dev_helper_mcp/readiness.py" in line
    assert "source.file=zeus_dev_helper_mcp/server.py" not in line
    assert "source.line=2" in line
    assert "error.type=exception" in line
    assert "tool=explode_probe" in line
    assert EVENT not in captured.out


def test_exception_outside_package_does_not_blame_server(
    capsys: pytest.CaptureFixture[str],
    isolated_state: None,
) -> None:
    fn = _compile_tool(
        "explode_outside",
        "raise RuntimeError('outside')",
        "/tmp/not_in_helper_package.py",
    )
    wrapped = _wrap_tool(fn)
    with pytest.raises(RuntimeError, match="outside"):
        wrapped()
    lines = _failure_lines(capsys.readouterr().err)
    assert len(lines) == 1
    assert "source.file=" not in lines[0]
    assert "server.py" not in lines[0]
    assert "error.type=exception" in lines[0]


def test_domain_ok_false_is_not_an_error_line(
    capsys: pytest.CaptureFixture[str],
    isolated_state: None,
) -> None:
    fn = _compile_tool(
        "diagnose_error",
        "return {'ok': False, 'failure_class': 'empty_find_get', 'message': 'no rows'}",
        readiness.__file__,
    )
    out = _wrap_tool(fn)()
    assert out["ok"] is False
    assert out["message"] == "no rows"
    assert _failure_lines(capsys.readouterr().err) == []
