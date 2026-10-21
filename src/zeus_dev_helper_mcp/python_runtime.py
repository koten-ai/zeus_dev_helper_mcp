"""Python 3.11 floor before a sample installs kotenai-zeus-client.

The Helper process is already 3.11 or newer. The interpreter that matters is
``python3`` on PATH, or ``<app>/.venv/bin/python`` when that file exists.
A 3.9 virtualenv makes pip report ``from versions: none`` for this package.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from zeus_dev_helper_mcp.config import HelperConfig

MIN_PYTHON = (3, 11)
MIN_TEXT = "3.11"
_VERSION_LINE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_PROBE = "import sys; v = sys.version_info; print(f'{v[0]}.{v[1]}.{v[2]}')"
# Bound at import so a test can stub pip's subprocess.run without skipping this probe.
_run = subprocess.run


def read_version(exe: str) -> tuple[int, int, int] | None:
    """Run ``exe -c`` and return ``(major, minor, micro)``. Never raises."""
    if not exe:
        return None
    try:
        proc = _run(
            [exe, "-c", _PROBE],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    found: tuple[int, int, int] | None = None
    for line in (proc.stdout or "").splitlines():
        match = _VERSION_LINE.match(line.strip())
        if match:
            found = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return found


def _format(version: tuple[int, int, int] | None) -> str:
    if version is None:
        return ""
    return f"{version[0]}.{version[1]}.{version[2]}"


def _meets(version: tuple[int, int, int] | None) -> bool:
    return version is not None and version[:2] >= MIN_PYTHON


def _old_python3_note(shown: str, command: str) -> str:
    head = f"python3 is {shown}." if shown else "python3 is not on PATH."
    return (
        f"{head} kotenai-zeus-client needs Python {MIN_TEXT} or newer. "
        f"The run command uses `{command}`."
    )


def launcher() -> dict[str, str]:
    """Shell pieces for a virtualenv on Python 3.11 or newer.

    ``python3 -m venv`` stays when ``python3`` already meets the floor.
    Otherwise the command names ``python3.11``–``python3.15`` or
    ``uv venv --python 3.12``.
    """
    py3 = shutil.which("python3")
    py3_version = read_version(py3) if py3 else None
    shown = _format(py3_version)
    if _meets(py3_version):
        command = "python3 -m venv .venv"
        return {
            "via": "python3",
            "command": command,
            "setup": f"{command} && source .venv/bin/activate",
            "recreate": "python3 -m venv --clear .venv",
            "note": "",
            "python3_version": shown,
        }
    for minor in range(15, 10, -1):
        name = f"python3.{minor}"
        path = shutil.which(name)
        if not path:
            continue
        version = read_version(path)
        if not _meets(version):
            continue
        command = f"{name} -m venv .venv"
        return {
            "via": name,
            "command": command,
            "setup": f"{command} && source .venv/bin/activate",
            "recreate": f"{name} -m venv --clear .venv",
            "note": _old_python3_note(shown, command),
            "python3_version": shown,
        }
    if shutil.which("uv"):
        command = "uv venv --python 3.12 .venv"
        return {
            "via": "uv",
            "command": command,
            "setup": f"{command} && source .venv/bin/activate",
            "recreate": "uv venv --python 3.12 --clear .venv",
            "note": _old_python3_note(shown, command),
            "python3_version": shown,
        }
    command = "python3.12 -m venv .venv"
    return {
        "via": "missing",
        "command": command,
        "setup": f"{command} && source .venv/bin/activate",
        "recreate": "python3.12 -m venv --clear .venv",
        "note": _old_python3_note(shown, command),
        "python3_version": shown,
    }


def venv_setup_shell() -> str:
    """``python3 -m venv .venv && source .venv/bin/activate`` on a 3.11+ interpreter."""
    return launcher()["setup"]


def launch_note() -> str:
    """Empty when ``python3`` is already 3.11 or newer."""
    return launcher()["note"]


def _refusal(source: str, shown: str) -> str:
    fix = launcher()["recreate"]
    if shown and shown != "unknown":
        head = f"{source} is Python {shown}."
    else:
        head = f"Could not read the Python version of {source}."
    return (
        f"{head} kotenai-zeus-client needs Python {MIN_TEXT} or newer. "
        f"Recreate the virtualenv with `{fix}`, then call website_green again."
    )


def pip_block(exe: str, *, source: str) -> dict[str, Any] | None:
    """Return an ``install_failed`` result when ``exe`` must not run pip."""
    version = read_version(exe)
    if _meets(version):
        return None
    shown = _format(version) or "unknown"
    return {
        "ok": False,
        "installed": False,
        "failure_class": "install_failed",
        "next_action": _refusal(source, shown),
    }


def inspect_app_python(root: Path | None) -> dict[str, Any]:
    """Probe the app virtualenv, or ``python3`` on PATH when it does not exist."""
    if root is not None:
        venv = Path(root) / ".venv" / "bin" / "python"
        if venv.is_file():
            return _report(str(venv), ".venv")
    exe = shutil.which("python3")
    if not exe:
        return {
            "ok": False,
            "version": None,
            "path": "",
            "source": "python3",
            "evidence": "python3 missing; need >=3.11",
            "message": _refusal("python3", "unknown"),
        }
    return _report(exe, "python3")


def _report(exe: str, source: str) -> dict[str, Any]:
    version = read_version(exe)
    shown = _format(version)
    ok = _meets(version)
    if ok:
        evidence = f"{source} {shown}"
        message = ""
    elif version is None:
        evidence = f"{source} unreadable; need >=3.11"
        message = _refusal(source, "unknown")
    else:
        evidence = f"{source} {shown}; need >=3.11"
        message = _refusal(source, shown)
    return {
        "ok": ok,
        "version": shown or None,
        "path": exe,
        "source": source,
        "evidence": evidence[:180],
        "message": message,
    }


def sync_checklist_python(cfg: HelperConfig, report: dict[str, Any]) -> None:
    """Mark checklist 1.1 from a probe. Evidence is the version, not a path."""
    from zeus_dev_helper_mcp.checklist import set_item_status

    status = "done" if report.get("ok") else "blocked"
    evidence = str(report.get("evidence") or "")[:180]
    try:
        set_item_status(cfg, "1.1", status, evidence=evidence or None)
    except Exception:  # noqa: BLE001
        return
