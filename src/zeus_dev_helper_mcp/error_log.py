"""One stderr line when a Helper MCP tool fails (ZDM-11).

stdout is the MCP JSON-RPC stream. This module writes the Zeus Client
family text shape to stderr only and does not call ``logging.basicConfig``.
"""

from __future__ import annotations

import logging
import re
import sys
import traceback
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

EVENT = "zeus_dev_helper.tool.failed"
LOGGER_NAME = "zeus_dev_helper"
MESSAGE_CAP = 2048
_HANDLER_MARK = "_zeus_dev_helper_stderr"
_PACKAGE = "zeus_dev_helper_mcp"
_LOGGER_FILE = f"{_PACKAGE}/error_log.py"
_WRAPPER_NAMES = frozenset({"_wrap_tool", "wrapped"})
_REPO_DIRS = frozenset(
    {"src", "tests", "docs", "guides", "scripts", ".git", ".github"}
)

# Hard-denied even if a future redact switch is off.
_SECRET_KEYS = (
    "refresh_token",
    "private_key",
    "api_key",
    "authorization",
    "password",
    "passwd",
    "secret",
    "token",
    "cookie",
)

_FIELD_ORDER = (
    "error.message",
    "error.type",
    "source.file",
    "source.line",
    "result",
    "tool",
    "req_id",
    "session.id",
    "http.status_code",
    "zeus.url",
    "verb",
)


def package_source(path: str) -> str:
    """Package-relative path (``zeus_dev_helper_mcp/<module>.py``) or ``''``.

    Keeps the import package, not the repo directory of the same name.
    Drops a leading ``src/``. Rejects absolute leftovers and ``..``.
    """
    norm = str(path or "").replace("\\", "/")
    parts = [part for part in norm.split("/") if part not in ("", ".")]
    candidates = [index for index, part in enumerate(parts) if part == _PACKAGE]
    for index in reversed(candidates):
        rel_parts = parts[index:]
        if any(part == ".." for part in rel_parts):
            continue
        if len(rel_parts) < 2:
            continue
        nxt = rel_parts[1]
        if nxt in _REPO_DIRS:
            continue
        if not (nxt.endswith(".py") or nxt.isidentifier()):
            continue
        rel = "/".join(rel_parts).removeprefix("src/")
        folded = f"/{rel.lower()}/"
        if (
            not rel.startswith(f"{_PACKAGE}/")
            or rel.startswith("/")
            or ".." in rel.split("/")
            or "src/zeus_dev_helper_mcp" in rel
            or "/home/" in folded
            or "/users/" in folded
        ):
            continue
        return rel
    return ""


def public_origin(url: str) -> str | None:
    """Public API origin with userinfo removed. Hub ``:9091`` is omitted."""
    raw = str(url or "").strip()
    if not raw:
        return None
    parts = urlsplit(raw)
    host = parts.hostname
    if not parts.scheme or not host:
        return None
    if parts.port == 9091 or "/hub" in raw.lower():
        return None
    host_text = f"[{host}]" if ":" in host else host
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{host_text}{port}"


def scrub_text(text: str) -> str:
    """Replace bearer tokens and secret assignments with ``[REDACTED]``."""
    cleaned = str(text)
    cleaned = re.sub(
        r"(?i)\b(?:authorization\s*:\s*)?(?:bearer|basic)\s+\S+",
        "[REDACTED]",
        cleaned,
    )
    cleaned = re.sub(
        r"(?i)\b(?:sk-[a-z0-9\-_]{8,}|xai-[a-z0-9\-_]{8,})\b",
        "[REDACTED]",
        cleaned,
    )
    keys = "|".join(_SECRET_KEYS)
    cleaned = re.sub(
        rf"(?i)(?:^|[^A-Za-z0-9])(?:{keys})\s*[:=]\s*\S+",
        lambda match: _redact_assignment(match.group(0)),
        cleaned,
    )
    cleaned = re.sub(
        r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s@]+@",
        r"\1",
        cleaned,
    )
    return cleaned


def format_failure_line(
    *,
    tool: str,
    message: str,
    error_type: str | None = None,
    source_file: str | None = None,
    source_line: int | None = None,
    req_id: str | None = None,
    session_id: str | None = None,
    status_code: int | None = None,
    zeus_url: str | None = None,
    verb: str | None = None,
    now: datetime | None = None,
) -> str:
    """Render one physical family line. ``error.code`` is never included."""
    fields: dict[str, Any] = {
        "error.message": message,
        "result": "error",
        "tool": tool,
    }
    if error_type:
        fields["error.type"] = error_type
    rel = package_source(source_file or "")
    if rel:
        fields["source.file"] = rel
        if isinstance(source_line, int) and not isinstance(source_line, bool) and source_line > 0:
            fields["source.line"] = source_line
    if req_id:
        fields["req_id"] = req_id
    if session_id:
        fields["session.id"] = session_id
    if isinstance(status_code, int) and not isinstance(status_code, bool):
        fields["http.status_code"] = status_code
    origin = public_origin(zeus_url or "")
    if origin:
        fields["zeus.url"] = origin
    if verb:
        fields["verb"] = verb
    return _render(fields, now=now)


def log_tool_failure(fn: Callable[..., Any], payload: Mapping[str, Any]) -> None:
    """Log one line for an execution-failure payload. Never raises."""
    try:
        code = getattr(fn, "__code__", None)
        filename = getattr(code, "co_filename", "") if code is not None else ""
        lineno = getattr(code, "co_firstlineno", 0) if code is not None else 0
        emit_line(
            format_failure_line(
                tool=getattr(fn, "__name__", "") or "",
                message=_message_from_payload(payload),
                error_type=_text(payload.get("failure_class")),
                source_file=filename,
                source_line=lineno if isinstance(lineno, int) else None,
                req_id=_req_id(payload),
                session_id=_session_id(payload),
                status_code=_status_code(payload),
                zeus_url=_text(payload.get("zeus_url") or payload.get("zeus.url")),
                verb=_text(payload.get("verb")),
            )
        )
    except Exception:  # noqa: BLE001 — a log failure must not hide the tool error
        return


def log_tool_exception(fn: Callable[..., Any], exc: BaseException) -> None:
    """Log one line for an uncaught tool exception, then let the caller re-raise."""
    try:
        source_file, source_line = _source_from_exception(exc)
        emit_line(
            format_failure_line(
                tool=getattr(fn, "__name__", "") or "",
                message=_text(str(exc)) or exc.__class__.__name__,
                error_type="exception",
                source_file=source_file,
                source_line=source_line,
            )
        )
    except Exception:  # noqa: BLE001 — a log failure must not hide the tool error
        return


def emit_line(line: str) -> None:
    """Write one family line to stderr through the Helper logger."""
    text = " ".join(str(line).split())
    if not text:
        return
    log = _logger()
    log.log(logging.ERROR, "%s", text)


def _logger() -> logging.Logger:
    log = logging.getLogger(LOGGER_NAME)
    log.propagate = False
    log.setLevel(logging.ERROR)
    handler = next(
        (item for item in log.handlers if getattr(item, _HANDLER_MARK, False)),
        None,
    )
    if handler is None:
        handler = logging.StreamHandler(sys.stderr)
        setattr(handler, _HANDLER_MARK, True)
        handler.setLevel(logging.ERROR)
        handler.setFormatter(logging.Formatter("%(message)s"))
    handler.stream = sys.stderr
    log.handlers = [handler]
    return log


def _render(fields: Mapping[str, Any], *, now: datetime | None) -> str:
    parts = [_timestamp(now), "[error]", EVENT]
    for key in _FIELD_ORDER:
        if key not in fields:
            continue
        rendered = _format_attr(key, fields[key])
        if rendered:
            parts.append(rendered)
    return " ".join(parts)


def _format_attr(key: str, value: Any) -> str | None:
    if key in {"source.line", "http.status_code"}:
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        if key == "source.line" and value <= 0:
            return None
        return f"{key}={value}"
    if value is None:
        return None
    text = scrub_text(str(value).replace("\r", " ").replace("\n", " ").strip())
    if key == "error.message":
        text = (text or "tool failed")[:MESSAGE_CAP]
    elif text == "":
        return None
    if key == "error.message" or _needs_quotes(text):
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'{key}="{escaped}"'
    return f"{key}={text}"


def _needs_quotes(text: str) -> bool:
    return any(char.isspace() or char in '="\\' for char in text)


def _timestamp(now: datetime | None) -> str:
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    else:
        moment = moment.astimezone(UTC)
    millis = moment.microsecond // 1000
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{millis:03d}Z"


def _message_from_payload(payload: Mapping[str, Any]) -> str:
    for key in ("error", "message"):
        text = _text(payload.get(key))
        if text:
            return text
    return "tool failed"


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _req_id(payload: Mapping[str, Any]) -> str | None:
    found = _text(payload.get("req_id"))
    if found:
        return found
    steps = payload.get("steps")
    if not isinstance(steps, list):
        return None
    last = None
    for step in steps:
        if isinstance(step, dict):
            text = _text(step.get("req_id"))
            if text:
                last = text
    return last


def _session_id(payload: Mapping[str, Any]) -> str | None:
    for key in ("session_id", "session.id"):
        text = _text(payload.get(key))
        if text:
            return text
    session = payload.get("session")
    if isinstance(session, dict):
        for key in ("id", "session_id"):
            text = _text(session.get(key))
            if text:
                return text
    return None


def _status_code(payload: Mapping[str, Any]) -> int | None:
    for key in ("status_code", "http_status", "http.status_code"):
        code = _int_code(payload.get(key))
        if code is not None:
            return code
    steps = payload.get("steps")
    if isinstance(steps, list):
        last = None
        for step in steps:
            if isinstance(step, dict):
                code = _int_code(step.get("status"))
                if code is None:
                    code = _int_code(step.get("status_code"))
                if code is not None:
                    last = code
        if last is not None:
            return last
    gates = payload.get("gates")
    if isinstance(gates, list):
        for gate in gates:
            if not isinstance(gate, dict) or gate.get("status") != "fail":
                continue
            evidence = gate.get("evidence")
            if isinstance(evidence, dict):
                code = _int_code(evidence.get("status"))
                if code is not None:
                    return code
    return None


def _int_code(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _source_from_exception(exc: BaseException) -> tuple[str | None, int | None]:
    frames = traceback.extract_tb(exc.__traceback__)
    if not frames:
        return None, None
    raise_site = frames[-1]
    chosen: traceback.FrameSummary | None = None
    for frame in frames:
        rel = package_source(frame.filename)
        if not rel or rel == _LOGGER_FILE:
            continue
        if (
            rel == f"{_PACKAGE}/server.py"
            and frame.name in _WRAPPER_NAMES
            and frame is not raise_site
        ):
            continue
        chosen = frame
    if chosen is None:
        return None, None
    rel = package_source(chosen.filename)
    line = chosen.lineno if isinstance(chosen.lineno, int) and chosen.lineno > 0 else None
    return rel or None, line


def _redact_assignment(token: str) -> str:
    match = re.match(r"(?i)^([^A-Za-z0-9]*)([A-Za-z0-9_]+)\s*[:=]", token)
    if not match:
        return "[REDACTED]"
    return f"{match.group(1)}{match.group(2)}=[REDACTED]"
