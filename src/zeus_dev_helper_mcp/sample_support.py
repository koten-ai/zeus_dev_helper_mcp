"""Append-only support journal for beer, travel, and yelp-demo (ZDM-25).

The ZDM-24 creation logs stay write-once. This module records a red gate
after that file exists, and a ``use_sample`` that never seals. The paste
tool reads local state and does not call Zeus.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from zeus_dev_helper_mcp import __version__
from zeus_dev_helper_mcp.config import HelperConfig, llm_key_in_process_env
from zeus_dev_helper_mcp.config_lint import _ENV_NAME
from zeus_dev_helper_mcp.error_log import MESSAGE_CAP, public_origin, scrub_text
from zeus_dev_helper_mcp.llm_key import inspect_app_llm_key
from zeus_dev_helper_mcp.sample_log import bound_sample_dirs, sample_kind

SECTION_CAP = 40
JOURNAL_TAIL = 8
METRIC_TAIL = 20

_FILES = {
    "beer": "beer-sample-support.md",
    "travel": "travel-sample-support.md",
    "yelp-demo": "yelp-demo-support.md",
}
_BUILD_FILES = {
    "beer": "beer-sample-build.md",
    "travel": "travel-sample-build.md",
    "yelp-demo": "yelp-demo-build.md",
}
_TITLES = {
    "beer": "beer-sample",
    "travel": "travel-sample",
    "yelp-demo": "yelp-demo",
}
_GATE_TOOLS = frozenset(
    {
        "use_sample",
        "readiness_check",
        "validate_env",
        "load_process_login",
        "verify_local_setup",
        "smoke_test_zeus",
        "smoke_test_agent",
        "website_green",
    }
)
_PRESENCE = ("has_llm_key", "has_bearer", "has_username", "has_password")
_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_SESSION_ID = re.compile(
    r"(?i)(session[._\s-]*id)(\s*[\"']?\s*[:=]\s*[\"']?)([^\"'\s,}\]]+)"
)
_SECTION = re.compile(
    r"^## (?P<index>\d+)\. (?P<tool>[a-z][a-z0-9_]*)\n"
    r"\n"
    r"- Helper version: (?P<version>[^\n]+)\n"
    r"- UTC timestamp: (?P<stamp>[^\n]+)\n"
    r"- Tool: `(?P<shown>[a-z][a-z0-9_]*)`\n"
    r"- failure_class: (?P<failure>[^\n]*)\n"
    r"- message: (?P<message>[^\n]*)\n",
    re.MULTILINE,
)


def observe_sample_support(
    cfg: HelperConfig,
    tool: str,
    args: Mapping[str, Any] | None,
    result: Mapping[str, Any] | None,
    *,
    exc: BaseException | None = None,
    now: datetime | None = None,
) -> None:
    """Append one journal section when a sample gate finishes red or raises.

    ``use_sample`` is recorded even when the creation log was never sealed.
    The other gates wait until that creation log is a regular file. A write
    never opens ``*-build.md``.
    """
    try:
        _observe(cfg, tool, args, result, exc=exc, now=now)
    except Exception:  # noqa: BLE001 — the journal must not hide the tool result
        return


def sample_support_pack(cfg: HelperConfig, sample: str) -> dict[str, Any]:
    """One Markdown paste. Writes nothing and calls no Zeus API."""
    kind = sample_kind(sample or "")
    if kind is None:
        return {
            "ok": False,
            "failure_class": "sample_not_supported",
            "markdown": "",
            "next_action": (
                "Pass sample=beer, sample=travel, or sample=demo_yelp. "
                "sample=api and bare sample=yelp stay out of this paste."
            ),
        }
    return {
        "ok": True,
        "sample": kind,
        "markdown": _render_pack(cfg, kind),
        "failure_class": None,
        "next_action": "Paste the markdown into the support request.",
    }


def _observe(
    cfg: HelperConfig,
    tool: str,
    args: Mapping[str, Any] | None,
    result: Mapping[str, Any] | None,
    *,
    exc: BaseException | None,
    now: datetime | None,
) -> None:
    if tool not in _GATE_TOOLS:
        return
    if exc is None and not _is_red(result):
        return
    kind = _kind_for(cfg, tool, args or {})
    if kind is None:
        return
    if tool != "use_sample" and not _creation_sealed(cfg, kind):
        return
    _append(
        cfg,
        kind,
        {
            "tool": tool,
            "version": __version__,
            "stamp": _stamp(now),
            "failure": _failure_class(result, exc),
            "message": _message(result, exc),
        },
    )


def _kind_for(cfg: HelperConfig, tool: str, args: Mapping[str, Any]) -> str | None:
    if tool == "use_sample":
        raw = args.get("sample") if "sample" in args else "travel"
        if raw is None or not str(raw).strip():
            raw = "travel"
        return sample_kind(str(raw))
    return _project_kind(cfg)


def _project_kind(cfg: HelperConfig) -> str | None:
    data = _read_json(cfg.state_dir / "checklist.json")
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    sample = str((meta or {}).get("sample") or "").strip()
    if not sample:
        return None
    return sample_kind(sample)


def _is_red(result: Mapping[str, Any] | None) -> bool:
    if not isinstance(result, Mapping):
        return False
    if result.get("ok") is True:
        return False
    return result.get("ok") is False or result.get("overall") == "fail"


def _failure_class(result: Mapping[str, Any] | None, exc: BaseException | None) -> str:
    if exc is not None:
        return "exception"
    if isinstance(result, Mapping):
        for key in ("failure_class", "primary_failure_class"):
            text = _clean_token(result.get(key))
            if text:
                return text
        issues = result.get("issues")
        if isinstance(issues, list):
            for issue in issues:
                if not isinstance(issue, dict) or issue.get("level") != "error":
                    continue
                text = _clean_token(issue.get("failure_class"))
                if text:
                    return text
    return "failed"


def _message(result: Mapping[str, Any] | None, exc: BaseException | None) -> str:
    raw = ""
    if exc is not None:
        raw = str(exc).strip() or exc.__class__.__name__
    elif isinstance(result, Mapping):
        for key in ("error", "message", "next_action"):
            if not isinstance(result.get(key), str):
                continue
            text = str(result.get(key)).strip()
            if text:
                raw = text
                break
        if not raw:
            issues = result.get("issues")
            if isinstance(issues, list):
                for issue in issues:
                    if not isinstance(issue, dict) or issue.get("level") != "error":
                        continue
                    if isinstance(issue.get("message"), str) and issue.get("message").strip():
                        raw = str(issue.get("message")).strip()
                        break
    if not raw:
        raw = "tool failed"
    return _public_line(raw) or "tool failed"


def _append(cfg: HelperConfig, kind: str, section: dict[str, str]) -> None:
    path = _support_path(cfg, kind)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        return
    existing = _read_text(path)
    if existing and not _owned(existing, kind):
        return
    sections = _parse_sections(existing)
    sections.append(section)
    if len(sections) > SECTION_CAP:
        sections = sections[-SECTION_CAP:]
    _write_text(path, _render_journal(kind, sections))


def _render_pack(cfg: HelperConfig, kind: str) -> str:
    recorded = str(bound_sample_dirs(cfg).get(kind) or "").strip()
    root: Path | None = None
    on_disk = False
    if recorded:
        try:
            root = Path(recorded).expanduser()
            on_disk = root.is_dir()
        except OSError:
            root = None
            on_disk = False
    creation = _creation_line(cfg, kind)
    prereqs = _read_json(cfg.state_dir / "prereqs.json")
    origin = public_origin(str(prereqs.get("zeus_url") or "")) or "omitted"
    key_state, api_key_env = _local_llm(root if on_disk else None)
    lines = [
        f"# {_TITLES[kind]} support pack",
        "",
        f"- sample: {kind}",
        f"- bound directory: {_show_path(recorded)}",
        f"- directory on disk: {'yes' if on_disk else 'no'}",
        f"- Helper version: {__version__}",
        f"- creation log: {creation}",
        "",
        "## Prereqs",
        "",
        f"- origin: {origin}",
        f"- auth_mode: {_show_field(prereqs.get('auth_mode'))}",
        f"- bucket: {_show_field(prereqs.get('bucket'))}",
        f"- scope: {_show_field(prereqs.get('scope'))}",
    ]
    for name in _PRESENCE:
        lines.append(f"- {name}: {_flag(prereqs, name)}")
    lines.extend(["", "## Checklist", ""])
    rows = _checklist_rows(cfg)
    lines.extend(rows or ["- (none)"])
    green = _website_class(cfg)
    smoke = (cfg.state_dir / "last_smoke_agent.json").is_file()
    lines.extend(
        [
            "",
            "## Gates",
            "",
            f"- website_green class: {green}",
            f"- last_smoke_agent.json: {'present' if smoke else 'absent'}",
            "",
            "## Local setup",
            "",
            f"- process LLM key: {'present' if llm_key_in_process_env() else 'absent'}",
            f"- app .env key: {key_state}",
            f"- llm.api_key_env: {api_key_env}",
        ]
    )
    if kind == "yelp-demo":
        lines.append("- API port: 5000")
        lines.append("- frontend port: 5173")
    lines.extend(["", "## Recent tools", ""])
    tools = _recent_tools(cfg)
    lines.extend([f"- {name}" for name in tools] or ["- (none)"])
    lines.extend(["", "## Support journal", ""])
    tail = _parse_sections(_read_text(_support_path(cfg, kind)))[-JOURNAL_TAIL:]
    if tail:
        rendered = [
            _render_section(_section_index(item, index), _public_section(item))
            for index, item in enumerate(tail, start=1)
        ]
        lines.append("\n\n".join(part.rstrip("\n") for part in rendered))
    else:
        lines.append("- (none)")
    return "\n".join(lines).rstrip() + "\n"


def _creation_line(cfg: HelperConfig, kind: str) -> str:
    path = cfg.state_dir.expanduser() / _BUILD_FILES[kind]
    if path.is_symlink() or not path.is_file():
        return "never sealed"
    return str(path)


def _local_llm(root: Path | None) -> tuple[str, str]:
    if root is None:
        return "absent", "(none)"
    report = inspect_app_llm_key(root)
    if not report.get("applies"):
        return "absent", "(none)"
    names = _env_names(report.get("api_key_env"))
    state = "present" if report.get("ok") else "absent"
    if names and all(_ENV_NAME.fullmatch(name) for name in names):
        return state, ", ".join(names)
    message = str(report.get("message") or "")
    if "environment variable name" in message or "not valid JSON" in message:
        return "absent", "not a variable name"
    if names:
        return "absent", "not a variable name"
    return state, "(none)"


def _env_names(value: Any) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return []


def _checklist_rows(cfg: HelperConfig) -> list[str]:
    data = _read_json(cfg.state_dir / "checklist.json")
    phases = data.get("phases")
    if not isinstance(phases, list):
        return []
    rows: list[str] = []
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        number = _phase_number(str(phase.get("id") or ""))
        if number is None or number < 1 or number > 5:
            continue
        items = phase.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "")
            if status not in {"todo", "blocked"}:
                continue
            item_id = _one_line(str(item.get("id") or "")) or "?"
            title = _public_line(str(item.get("title") or "")) or item_id
            line = f"- {item_id} {status}: {title}"
            evidence = item.get("evidence")
            if isinstance(evidence, str) and evidence.strip():
                shown = _public_line(evidence)
                if shown:
                    line += f" evidence: {shown}"
            rows.append(line)
    return rows


def _website_class(cfg: HelperConfig) -> str:
    data = _read_json(cfg.state_dir / "website_green.json")
    text = _clean_token(data.get("failure_class"))
    return text or "none"


def _recent_tools(cfg: HelperConfig) -> list[str]:
    path = cfg.state_dir / "metrics.jsonl"
    if path.is_symlink() or not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    names: list[str] = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict) or row.get("event") != "tool_call":
            continue
        name = str(row.get("tool") or "").strip()
        if _TOOL_NAME.fullmatch(name):
            names.append(name)
    return names[-METRIC_TAIL:]


def _flag(prereqs: Mapping[str, Any], name: str) -> str:
    if name not in prereqs or not isinstance(prereqs.get(name), bool):
        return "absent"
    return "true" if prereqs.get(name) else "false"


def _show_field(value: Any) -> str:
    if not isinstance(value, str):
        return "(none)"
    return _public_line(value) or "(none)"


def _show_path(value: str) -> str:
    if not value:
        return "(none)"
    return _public_line(value) or "(none)"


def _phase_number(phase_id: str) -> int | None:
    head = phase_id.split("_", 1)[0]
    if not head.isdigit():
        return None
    return int(head)


def _support_path(cfg: HelperConfig, kind: str) -> Path:
    return cfg.state_dir.expanduser() / _FILES[kind]


def _creation_sealed(cfg: HelperConfig, kind: str) -> bool:
    path = cfg.state_dir.expanduser() / _BUILD_FILES[kind]
    return path.is_file() and not path.is_symlink()


def _owned(text: str, kind: str) -> bool:
    lines = text.lstrip("\ufeff").splitlines()
    return bool(lines) and lines[0] == f"# {_TITLES[kind]} support"


def _parse_sections(text: str) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    for match in _SECTION.finditer(text):
        if match.group("tool") != match.group("shown"):
            continue
        found.append(
            {
                "index": match.group("index"),
                "tool": match.group("tool"),
                "version": match.group("version").strip(),
                "stamp": match.group("stamp").strip(),
                "failure": match.group("failure").strip() or "failed",
                "message": match.group("message").strip() or "tool failed",
            }
        )
    return found


def _render_journal(kind: str, sections: list[dict[str, str]]) -> str:
    chunks = [
        f"# {_TITLES[kind]} support",
        "",
        "Red gate results. The creation log stays write-once.",
        "",
    ]
    for index, section in enumerate(sections, start=1):
        chunks.append(_render_section(index, section).rstrip("\n"))
        chunks.append("")
    return "\n".join(chunks).rstrip() + "\n"


def _render_section(index: int, section: Mapping[str, str]) -> str:
    return (
        f"## {index}. {section['tool']}\n"
        "\n"
        f"- Helper version: {section['version']}\n"
        f"- UTC timestamp: {section['stamp']}\n"
        f"- Tool: `{section['tool']}`\n"
        f"- failure_class: {section['failure']}\n"
        f"- message: {section['message']}\n"
    )


def _read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _read_text(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _write_text(path: Path, text: str) -> bool:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(tmp, flags, 0o644)
    except FileExistsError:
        if tmp.is_symlink() or not tmp.is_file():
            return False
        try:
            tmp.unlink()
            fd = os.open(tmp, flags, 0o644)
        except OSError:
            return False
    except OSError:
        return False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        tmp.unlink(missing_ok=True)
        return False
    try:
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        return False
    try:
        dir_fd = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return True
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
    return True


def _clean_token(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return _public_line(value.strip())


def _public_line(value: str) -> str:
    text = _strip_sessions(scrub_text(value))
    text = _one_line(text)
    return text[:MESSAGE_CAP]


def _section_index(section: Mapping[str, str], fallback: int) -> int:
    raw = str(section.get("index") or "")
    if raw.isdigit():
        return int(raw)
    return fallback


def _public_section(section: Mapping[str, str]) -> dict[str, str]:
    shown = dict(section)
    shown["failure"] = _public_line(str(section.get("failure") or "")) or "failed"
    shown["message"] = _public_line(str(section.get("message") or "")) or "tool failed"
    shown["version"] = _public_line(str(section.get("version") or "")) or __version__
    return shown


def _strip_sessions(text: str) -> str:
    return _SESSION_ID.sub(r"\1\2[REDACTED]", text)


def _one_line(value: str) -> str:
    return " ".join(value.split())


def _stamp(now: datetime | None) -> str:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        return current.replace(tzinfo=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return current.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
