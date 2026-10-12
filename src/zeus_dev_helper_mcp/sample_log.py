"""Write-once Markdown transcript of the first sample creation (ZDM-24).

One file per sample under the Helper state directory. The file lists the
coach calls that led to ``use_sample``, in order, and stops when that call
writes or binds the sample. A file that already exists is left unchanged.
"""

from __future__ import annotations

import inspect
import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from zeus_dev_helper_mcp import __version__
from zeus_dev_helper_mcp.config import HelperConfig

_FILES = {
    "beer": "beer-sample-build.md",
    "travel": "travel-sample-build.md",
    "yelp-demo": "yelp-demo-build.md",
}
_TITLES = {
    "beer": "beer-sample",
    "travel": "travel-sample",
    "yelp-demo": "yelp-demo",
}
_TRAVEL_NAMES = frozenset(
    {"travel", "demo_travel", "travel_sample", "demo_travel_sample", "ui"}
)
_API_NAMES = frozenset({"api", "rest", "api_only", "api-only"})
_BARE_YELP = frozenset({"yelp", "multi"})
_COACH_TOOLS = frozenset(
    {
        "doctor",
        "set_prereq",
        "start_project",
        "next_step",
        "readiness_check",
        "recommend_surface",
        "load_process_login",
        "validate_env",
        "use_sample",
    }
)
_SAMPLE_TOOLS = frozenset({"start_project", "use_sample"})
_BOOL_FLAGS = frozenset(
    {"has_llm_key", "has_bearer", "has_username", "has_password"}
)
_DROP_KEYS = frozenset(
    {
        "clarification",
        "gate_outcome",
        "body",
        "chat_request",
        "catalog",
        "prompt",
        "messages",
        "evidence",
        "reason",
        "mini_schema",
    }
)
_SECRET_KEY = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|authorization|bearer|cookie)",
    re.IGNORECASE,
)
_SECRET_VALUE = re.compile(
    r"(?i)(?:\bbearer\s+\S+|\bsk-[a-z0-9_-]{8,}\b|\bxai-[a-z0-9_-]{8,}\b)"
)
_HASH_KEY = re.compile(r"(?i)^(contract_hash|stamp_hash|_hash|hash)$")
_SKIP_WALK = re.compile(
    r"(?i)password|passwd|secret|token|api[_-]?key|authorization|bearer|"
    r"cookie|prompt|messages|body|chat_request|catalog|mini_schema|description"
)
_HASH_VALUE = re.compile(r"^[0-9a-fA-F]{8,}$")
_STAMP_PREFIX = 12
_STATE_FILES = {
    "beer": ("DEMO_BEER_SAMPLE_DIR", "beer_sample.json", "beer_sample_dir"),
    "travel": ("DEMO_TRAVEL_SAMPLE_DIR", "travel_sample.json", "travel_sample_dir"),
    "yelp-demo": ("DEMO_YELP_SAMPLE_DIR", "yelp_sample.json", "yelp_sample_dir"),
}


@dataclass
class _Call:
    tool: str
    args: dict[str, Any]
    summary: dict[str, Any]
    at: datetime
    version: str


@dataclass
class _Buffer:
    prelude_open: bool = True
    active: str | None = None
    prelude: list[_Call] = field(default_factory=list)
    runs: dict[str, list[_Call]] = field(default_factory=dict)


_BUFFERS: dict[str, _Buffer] = {}


def reset_memory() -> None:
    """Drop in-process transcripts. The Markdown files are left as they are."""
    _BUFFERS.clear()


def sample_kind(name: str) -> str | None:
    """Map a sample argument to beer, travel, or yelp-demo.

    ``sample=api`` and bare ``sample=yelp`` are outside this log.
    """
    text = (name or "").strip().lower()
    if not text or text in _API_NAMES or text in _BARE_YELP:
        return None
    if text in _TRAVEL_NAMES:
        return "travel"
    from zeus_dev_helper_mcp.yelp import is_yelp_demo_sample

    if is_yelp_demo_sample(text):
        return "yelp-demo"
    from zeus_dev_helper_mcp.beer import is_beer_sample

    if is_beer_sample(text):
        return "beer"
    return None


def bound_sample_dirs(cfg: HelperConfig) -> dict[str, str]:
    """Recorded sample directory for each sample, before ``use_sample`` runs."""
    found: dict[str, str] = {}
    for kind, (env_name, filename, field_name) in _STATE_FILES.items():
        raw = (os.environ.get(env_name) or "").strip()
        if not raw:
            raw = _json_field(cfg.state_dir / filename, field_name)
        if raw:
            found[kind] = raw
    return found


def public_arguments(
    fn: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    """Arguments the tool was called with, excluding the elicitation gate."""
    try:
        bound = inspect.signature(fn).bind_partial(*args, **kwargs)
    except TypeError:
        bound_args = dict(kwargs)
    else:
        bound_args = dict(bound.arguments)
    return {key: value for key, value in bound_args.items() if key not in _DROP_KEYS}


def observe_sample_build(
    cfg: HelperConfig,
    tool: str,
    args: Mapping[str, Any] | None,
    result: Mapping[str, Any] | None,
    *,
    bound_before: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> None:
    """Record one coach call. Write the sample file when ``use_sample`` creates it."""
    if tool not in _COACH_TOOLS:
        return
    payload = dict(result or {})
    safe_args = _safe_args(dict(args or {}))
    call = _Call(
        tool=tool,
        args=safe_args,
        summary=_summary(payload),
        at=_as_utc(now),
        version=__version__,
    )
    buf = _buffer(cfg)
    _close_if_file_exists(cfg, buf)
    if tool not in _SAMPLE_TOOLS:
        _record_generic(buf, call)
        return
    kind = _named_sample(safe_args)
    if kind is None or _log_path(cfg, kind).exists():
        return
    if tool == "use_sample" and _is_noop(kind, payload, bound_before):
        return
    buf.prelude_open = False
    buf.active = kind
    buf.runs.setdefault(kind, []).append(call)
    if tool == "use_sample" and _is_creation(kind, payload, bound_before):
        _seal(cfg, buf, kind)


def _named_sample(args: Mapping[str, Any]) -> str | None:
    if "sample" not in args:
        return "travel"
    return sample_kind(str(args.get("sample") or ""))


def _record_generic(buf: _Buffer, call: _Call) -> None:
    if buf.active:
        buf.runs.setdefault(buf.active, []).append(call)
        return
    if buf.prelude_open:
        buf.prelude.append(call)


def _close_if_file_exists(cfg: HelperConfig, buf: _Buffer) -> None:
    if buf.active and _log_path(cfg, buf.active).exists():
        _forget(buf, buf.active)


def _is_noop(
    kind: str,
    result: Mapping[str, Any],
    bound_before: Mapping[str, str] | None,
) -> bool:
    if result.get("ok") is not True:
        return False
    return not _is_creation(kind, result, bound_before)


def _is_creation(
    kind: str,
    result: Mapping[str, Any],
    bound_before: Mapping[str, str] | None,
) -> bool:
    if result.get("ok") is not True:
        return False
    if kind == "beer":
        if result.get("already_serving") or result.get("upgraded") or result.get("page_only"):
            return False
        return result.get("written") is True
    if result.get("cloned") is True:
        return True
    if result.get("cloned") is not False:
        return False
    local = _path_of(result)
    if not local or bound_before is None:
        return False
    previous = str(bound_before.get(kind) or "").strip()
    if not previous:
        return True
    return not _same_path(previous, local)


def _seal(cfg: HelperConfig, buf: _Buffer, kind: str) -> None:
    path = _log_path(cfg, kind)
    text = _render(kind, list(buf.prelude) + list(buf.runs.get(kind, [])))
    _write_once(path, text)
    if path.is_file():
        _forget(buf, kind)


def _forget(buf: _Buffer, kind: str) -> None:
    buf.runs.pop(kind, None)
    if buf.active == kind:
        buf.active = next(iter(buf.runs), None)
        if buf.active is None:
            buf.prelude.clear()
            buf.prelude_open = False


def _buffer(cfg: HelperConfig) -> _Buffer:
    key = str(cfg.state_dir.expanduser().resolve())
    buf = _BUFFERS.get(key)
    if buf is None:
        buf = _Buffer()
        _BUFFERS[key] = buf
    return buf


def _log_path(cfg: HelperConfig, kind: str) -> Path:
    return cfg.state_dir.expanduser() / _FILES[kind]


def _write_once(path: Path, text: str) -> bool:
    """Create ``path`` only when it is absent. An existing file is not opened."""
    if path.exists() or path.is_symlink():
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o644)
    except OSError:
        return False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
    except OSError:
        path.unlink(missing_ok=True)
        return False
    return True


def _render(kind: str, calls: list[_Call]) -> str:
    lines = [
        f"# {_TITLES[kind]}",
        "",
        (
            "Replay these tool calls in order. "
            "The last call is the use_sample that wrote or bound the sample."
        ),
        "",
    ]
    for index, call in enumerate(calls, start=1):
        lines.append(f"## {index}. {call.tool}")
        lines.append("")
        lines.append(f"- Helper version: {call.version}")
        lines.append(f"- UTC timestamp: {_stamp(call.at)}")
        lines.append(f"- Tool: `{call.tool}`")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(call.args, indent=2, sort_keys=True))
        lines.append("```")
        lines.append("")
        lines.append(f"- ok: {str(bool(call.summary.get('ok'))).lower()}")
        for key in ("path", "cloned", "failure_class", "stamp"):
            if key not in call.summary:
                continue
            value = call.summary[key]
            if isinstance(value, bool):
                shown = str(value).lower()
            else:
                shown = _one_line(str(value))
            lines.append(f"- {key}: {shown}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _summary(result: Mapping[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {"ok": result.get("ok") is True}
    path = _path_of(result)
    if path:
        cleaned = _clean_text(path)
        if cleaned is not _DROP:
            summary["path"] = _one_line(str(cleaned))
    if isinstance(result.get("cloned"), bool):
        summary["cloned"] = result["cloned"]
    failure = result.get("failure_class")
    if not isinstance(failure, str) or not failure.strip():
        failure = result.get("primary_failure_class")
    if isinstance(failure, str) and failure.strip():
        summary["failure_class"] = _one_line(failure.strip())
    stamp = _stamp_prefix(result)
    if stamp:
        summary["stamp"] = stamp
    return summary


def _path_of(result: Mapping[str, Any]) -> str:
    for key in ("local_dir", "target_dir", "path"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    env = result.get("env")
    if isinstance(env, dict):
        for value in env.values():
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _stamp_prefix(value: Any, depth: int = 0) -> str | None:
    if depth > 5:
        return None
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                continue
            if _HASH_KEY.fullmatch(key):
                found = _hash_prefix(item)
                if found:
                    return found
            if _SKIP_WALK.search(key):
                continue
            found = _stamp_prefix(item, depth + 1)
            if found:
                return found
        return None
    if isinstance(value, list):
        for item in value[:20]:
            found = _stamp_prefix(item, depth + 1)
            if found:
                return found
    return None


def _hash_prefix(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    token = value.strip()
    if not _HASH_VALUE.fullmatch(token):
        return None
    return token[:_STAMP_PREFIX]


def _safe_args(raw: Mapping[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or key in _DROP_KEYS:
            continue
        if key in _BOOL_FLAGS and isinstance(value, bool):
            cleaned[key] = value
            continue
        if _SECRET_KEY.search(key):
            continue
        safe = _safe_value(value)
        if safe is _DROP:
            continue
        cleaned[key] = safe
    return cleaned


class _Drop:
    pass


_DROP = _Drop()


def _safe_value(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        return _clean_text(value)
    return _DROP


def _clean_text(value: str) -> str | _Drop:
    text = value.replace("\x00", "")
    if "://" in text and "@" in text.split("://", 1)[-1]:
        parts = urlsplit(text)
        if parts.username or parts.password:
            host = parts.hostname or ""
            if ":" in host and not host.startswith("["):
                host = f"[{host}]"
            port = f":{parts.port}" if parts.port else ""
            text = f"{parts.scheme}://{host}{port}{parts.path}"
            if parts.query:
                text += f"?{parts.query}"
    if not text.strip() or _SECRET_VALUE.search(text):
        return _DROP
    return text


def _json_field(path: Path, key: str) -> str:
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get(key) or "").strip()


def _same_path(left: str, right: str) -> bool:
    try:
        return Path(left).expanduser().resolve() == Path(right).expanduser().resolve()
    except OSError:
        return left.strip() == right.strip()


def _as_utc(now: datetime | None) -> datetime:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        return current.replace(tzinfo=UTC)
    return current.astimezone(UTC)


def _stamp(moment: datetime) -> str:
    return _as_utc(moment).strftime("%Y-%m-%dT%H:%M:%SZ")


def _one_line(value: str) -> str:
    return " ".join(value.split())
