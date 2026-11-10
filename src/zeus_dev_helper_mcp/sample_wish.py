"""Wish file for a red beer, travel, or yelp-demo gate (ZDM-58).

The creation log and the support journal stay unchanged. A red tool result
names this file and does not copy the items into the result.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from zeus_dev_helper_mcp import __version__
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.sample_support import (
    _GATE_TOOLS,
    _TITLES,
    _creation_sealed,
    _failure_class,
    _is_red,
    _kind_for,
    _message,
    _public_line,
    _read_text,
    _stamp,
    _write_text,
)

SECTION_CAP = 40
PACK_TAIL = 8
ITEM_CAP = 3

_FILES = {
    "beer": "beer-sample-wish.md",
    "travel": "travel-sample-wish.md",
    "yelp-demo": "yelp-demo-wish.md",
}
_INTRO = (
    "Gaps the coding agent lacked on a red gate. "
    "The creation log and the support journal stay unchanged."
)
_KINDS = ("file", "bucket", "env", "catalog", "other")
_SEVERITIES = ("low", "med", "high")
_SPECIFIC_FAILURES = frozenset(
    {"auth_default_bucket", "empty_tool_catalog", "stamp_fetch_failed"}
)
_SECRET_ENV = frozenset(
    {
        "ZEUS_PASSWORD",
        "ZEUS_BEARER_TOKEN",
        "LLM_API_KEY",
        "XAI_API_KEY",
        "OPENAI_API_KEY",
    }
)
_CATALOG_WHAT = {
    "empty_tool_catalog": "live tool catalog is empty",
    "stamp_fetch_failed": "live stamp could not be fetched",
}
_BUCKET_WHAT = "bucket on the hop is not the stored prereq bucket"
_BUCKET_WHY = "login was sent to the wrong bucket"
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]+$")
_NOT_A_FILE = re.compile(r"not a file:\s*(\S+)")
_HEADER = re.compile(r"^## (\d+)\. ([a-z][a-z0-9_]*)$")
_CATALOG_PARTS = frozenset({"chat_requests", "catalog", "catalogs"})


def observe_sample_wish(
    cfg: HelperConfig,
    tool: str,
    args: Mapping[str, Any] | None,
    result: Mapping[str, Any] | None,
    *,
    exc: BaseException | None = None,
    now: datetime | None = None,
) -> str | None:
    """Append one wish section when a sample gate finishes red or raises.

    ``use_sample`` is recorded even when the creation log was never sealed.
    The other gates wait until that creation log is a regular file. Returns
    the wish path after a section is written, else ``None``. Never raises.
    """
    try:
        return _observe(cfg, tool, args, result, exc=exc, now=now)
    except Exception:  # noqa: BLE001 — a wish-writer failure must not hide the tool
        return None


def wish_pack_lines(cfg: HelperConfig, kind: str) -> list[str]:
    """Last wish sections for the support paste. Reads only."""
    lines = ["", "## Wish journal", ""]
    tail = _parse_sections(_read_text(_wish_path(cfg, kind)))[-PACK_TAIL:]
    if not tail:
        lines.append("- (none)")
        return lines
    rendered = [
        _render_section(_section_index(item, index), _public_section(item)).rstrip("\n")
        for index, item in enumerate(tail, start=1)
    ]
    lines.append("\n\n".join(rendered))
    return lines


def _observe(
    cfg: HelperConfig,
    tool: str,
    args: Mapping[str, Any] | None,
    result: Mapping[str, Any] | None,
    *,
    exc: BaseException | None,
    now: datetime | None,
) -> str | None:
    if tool not in _GATE_TOOLS:
        return None
    if exc is None and not _is_red(result):
        return None
    kind = _kind_for(cfg, tool, args or {})
    if kind is None or kind not in _FILES:
        return None
    if tool != "use_sample" and not _creation_sealed(cfg, kind):
        return None
    failure = _failure_class(result, exc)
    return _append(
        cfg,
        kind,
        {
            "tool": tool,
            "version": __version__,
            "stamp": _stamp(now),
            "failure": failure,
            "items": _items(result, exc, failure),
        },
    )


def _items(
    result: Mapping[str, Any] | None,
    exc: BaseException | None,
    failure: str,
) -> list[dict[str, str]]:
    found = _Found()
    if isinstance(result, Mapping):
        _walk(result, found)
    items: list[dict[str, str]] = []
    for name in found.files:
        cleaned = _clean_item(
            {"what": f"missing required file {name}", "kind": "file"}
        )
        if cleaned:
            items.append(cleaned)
    if found.bucket:
        cleaned = _clean_item(
            {
                "what": _BUCKET_WHAT,
                "kind": "bucket",
                "why": _BUCKET_WHY,
                "severity": "high",
            }
        )
        if cleaned:
            items.append(cleaned)
    for name in found.env:
        cleaned = _clean_item({"what": name, "kind": "env"})
        if cleaned:
            items.append(cleaned)
    for name in found.catalog_classes:
        cleaned = _clean_item({"what": _CATALOG_WHAT[name], "kind": "catalog"})
        if cleaned:
            items.append(cleaned)
    for path in found.catalog_paths:
        cleaned = _clean_item(
            {"what": f"missing catalog path {path}", "kind": "catalog"}
        )
        if cleaned:
            items.append(cleaned)
    other = _other_item(result, exc, failure)
    if other and not _covered_by_item(other["what"], items):
        items.append(other)
    return items[:ITEM_CAP]


class _Found:
    def __init__(self) -> None:
        self.files: list[str] = []
        self.bucket = False
        self.env: list[str] = []
        self.catalog_classes: list[str] = []
        self.catalog_paths: list[str] = []
        self._files: set[str] = set()
        self._env: set[str] = set()
        self._paths: set[str] = set()


def _walk(node: Any, found: _Found) -> None:
    if isinstance(node, Mapping):
        _take_failure(node, found)
        _take_bucket_probe(node, found)
        _take_settings(node, found)
        message = node.get("message")
        if isinstance(message, str):
            _take_not_a_file(message, found)
        for value in node.values():
            _walk(value, found)
        return
    if isinstance(node, list):
        for value in node:
            _walk(value, found)


def _take_failure(node: Mapping[str, Any], found: _Found) -> None:
    for key in ("failure_class", "primary_failure_class"):
        text = node.get(key)
        if not isinstance(text, str):
            continue
        token = text.strip()
        if token == "auth_default_bucket":
            found.bucket = True
        elif token in _CATALOG_WHAT and token not in found.catalog_classes:
            found.catalog_classes.append(token)


def _take_bucket_probe(node: Mapping[str, Any], found: _Found) -> None:
    if found.bucket:
        return
    foreign = node.get("foreign_buckets")
    if isinstance(foreign, list) and any(
        isinstance(item, str) and item.strip() for item in foreign
    ):
        found.bucket = True
        return
    requests = node.get("request_buckets")
    if not isinstance(requests, list):
        return
    prereq = node.get("prereq_bucket")
    prereq_name = prereq.strip() if isinstance(prereq, str) else ""
    names = [item.strip() for item in requests if isinstance(item, str) and item.strip()]
    if not names:
        return
    if not prereq_name or any(name != prereq_name for name in names):
        found.bucket = True


def _take_settings(node: Mapping[str, Any], found: _Found) -> None:
    for key in ("missing_app_settings", "missing_process_settings"):
        values = node.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, str):
                continue
            name = item.strip()
            if (
                not name
                or name in _SECRET_ENV
                or name in found._env
                or not _ENV_NAME.fullmatch(name)
            ):
                continue
            found._env.add(name)
            found.env.append(name)


def _take_not_a_file(message: str, found: _Found) -> None:
    for match in _NOT_A_FILE.finditer(message):
        raw = match.group(1).strip("\"'`").rstrip(".,:;)")
        if not raw:
            continue
        if _is_catalog_path(raw):
            if raw not in found._paths:
                found._paths.add(raw)
                found.catalog_paths.append(raw)
            continue
        name = _base_name(raw)
        if name and name not in found._files:
            found._files.add(name)
            found.files.append(name)


def _is_catalog_path(path: str) -> bool:
    lowered = path.replace("\\", "/").lower()
    name = lowered.rsplit("/", 1)[-1]
    if "chat_request" in name or "chat-request" in name:
        return True
    parts = {part for part in lowered.split("/") if part}
    return bool(parts & _CATALOG_PARTS)


def _base_name(path: str) -> str:
    text = path.replace("\\", "/")
    name = text.rsplit("/", 1)[-1]
    return name or path


def _covered_by_item(what: str, items: list[dict[str, str]]) -> bool:
    """True when the free-text line is only a gap already recorded."""
    if any(item["what"] == what for item in items):
        return True
    match = _NOT_A_FILE.search(what)
    if not match:
        return False
    raw = match.group(1).strip("\"'`").rstrip(".,:;)")
    if not raw:
        return False
    if _is_catalog_path(raw):
        expected = _public_line(f"missing catalog path {raw}")
    else:
        expected = _public_line(f"missing required file {_base_name(raw)}")
    if not any(item["what"] == expected for item in items):
        return False
    remainder = _NOT_A_FILE.sub(" ", what)
    return not remainder.strip(" .:-")


def _other_item(
    result: Mapping[str, Any] | None,
    exc: BaseException | None,
    failure: str,
) -> dict[str, str] | None:
    if failure in _SPECIFIC_FAILURES:
        return None
    message = _message(result, exc)
    if (not message or message == "tool failed") and failure not in {"failed", "exception"}:
        message = _public_line(failure)
    if not message or message == "tool failed":
        return None
    return _clean_item({"what": message, "kind": "other"})


def _clean_item(item: Mapping[str, str]) -> dict[str, str] | None:
    what = _public_line(str(item.get("what") or ""))
    kind = str(item.get("kind") or "").strip()
    if not what or kind not in _KINDS:
        return None
    out = {"what": what, "kind": kind}
    if item.get("why"):
        why = _public_line(str(item.get("why") or ""))
        if why:
            out["why"] = why
    severity = str(item.get("severity") or "").strip()
    if severity in _SEVERITIES:
        out["severity"] = severity
    return out


def _append(cfg: HelperConfig, kind: str, section: dict[str, Any]) -> str | None:
    path = _wish_path(cfg, kind)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        return None
    existing = _read_text(path)
    if existing and not _owned(existing, kind):
        return None
    sections = _parse_sections(existing)
    sections.append(section)
    if len(sections) > SECTION_CAP:
        sections = sections[-SECTION_CAP:]
    if not _write_text(path, _render_journal(kind, sections)):
        return None
    return str(path)


def _wish_path(cfg: HelperConfig, kind: str) -> Path:
    return cfg.state_dir.expanduser() / _FILES[kind]


def _owned(text: str, kind: str) -> bool:
    lines = text.lstrip("\ufeff").splitlines()
    return bool(lines) and lines[0] == f"# {_TITLES[kind]} wish"


def _parse_sections(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    found: list[dict[str, Any]] = []
    index = 0
    total = len(lines)
    while index < total:
        match = _HEADER.match(lines[index])
        if not match:
            index += 1
            continue
        number, tool = match.group(1), match.group(2)
        start = index
        index += 1
        if index < total and lines[index] == "":
            index += 1
        fields, index, ok = _header_fields(lines, index)
        if not ok or fields.get("shown") != tool:
            index = start + 1
            continue
        items: list[dict[str, str]] = []
        if index < total and lines[index] == "- wish_i_knew:":
            index += 1
            while index < total and lines[index].startswith("  - what:"):
                item, index = _parse_item(lines, index)
                if item:
                    items.append(item)
        found.append(
            {
                "index": number,
                "tool": tool,
                "version": fields.get("version", "").strip(),
                "stamp": fields.get("stamp", "").strip(),
                "failure": fields.get("failure", "").strip() or "failed",
                "items": items[:ITEM_CAP],
            }
        )
    return found


def _header_fields(
    lines: list[str], index: int
) -> tuple[dict[str, str], int, bool]:
    labels = (
        ("version", "- Helper version: "),
        ("stamp", "- UTC timestamp: "),
        ("shown", "- Tool: `"),
        ("failure", "- failure_class: "),
    )
    fields: dict[str, str] = {}
    for key, prefix in labels:
        if index >= len(lines) or not lines[index].startswith(prefix):
            return fields, index, False
        if key == "shown":
            if not lines[index].endswith("`"):
                return fields, index, False
            fields[key] = lines[index][len(prefix) : -1]
        else:
            fields[key] = lines[index][len(prefix) :].strip()
        index += 1
    return fields, index, True


def _parse_item(lines: list[str], index: int) -> tuple[dict[str, str] | None, int]:
    raw = lines[index].split(": ", 1)[1] if ": " in lines[index] else ""
    item: dict[str, str] = {"what": raw.strip()}
    index += 1
    while index < len(lines) and lines[index].startswith("    "):
        text = lines[index].strip()
        if ": " not in text:
            break
        key, value = text.split(": ", 1)
        if key not in {"kind", "why", "severity"}:
            break
        item[key] = value.strip()
        index += 1
    return _clean_item(item), index


def _render_journal(kind: str, sections: list[dict[str, Any]]) -> str:
    chunks = [f"# {_TITLES[kind]} wish", "", _INTRO, ""]
    for index, section in enumerate(sections, start=1):
        chunks.append(_render_section(index, _public_section(section)).rstrip("\n"))
        chunks.append("")
    return "\n".join(chunks).rstrip() + "\n"


def _render_section(index: int, section: Mapping[str, Any]) -> str:
    lines = [
        f"## {index}. {section['tool']}",
        "",
        f"- Helper version: {section['version']}",
        f"- UTC timestamp: {section['stamp']}",
        f"- Tool: `{section['tool']}`",
        f"- failure_class: {section['failure']}",
        "- wish_i_knew:",
    ]
    for item in section.get("items") or []:
        if not isinstance(item, Mapping):
            continue
        lines.append(f"  - what: {item['what']}")
        lines.append(f"    kind: {item['kind']}")
        if item.get("why"):
            lines.append(f"    why: {item['why']}")
        if item.get("severity"):
            lines.append(f"    severity: {item['severity']}")
    return "\n".join(lines) + "\n"


def _public_section(section: Mapping[str, Any]) -> dict[str, Any]:
    items: list[dict[str, str]] = []
    for item in section.get("items") or []:
        if not isinstance(item, Mapping):
            continue
        cleaned = _clean_item(item)
        if cleaned:
            items.append(cleaned)
    return {
        "tool": section["tool"],
        "version": _public_line(str(section.get("version") or "")) or __version__,
        "stamp": str(section.get("stamp") or ""),
        "failure": _public_line(str(section.get("failure") or "")) or "failed",
        "items": items[:ITEM_CAP],
    }


def _section_index(section: Mapping[str, Any], fallback: int) -> int:
    raw = str(section.get("index") or "")
    if raw.isdigit():
        return int(raw)
    return fallback
