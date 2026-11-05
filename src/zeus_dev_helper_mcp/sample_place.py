"""Where a sample checkout is created, moved, or left serving.

Beer and travel share the directory rules. Each sample supplies its own
health check and its own notion of a matching tree.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SampleTarget:
    """Directory a sample tool will read or clone into."""

    root: Path
    serving_verdict: dict[str, Any] | None = None
    relocated_from: str = ""
    foreign_blocked: bool = False


def nonempty_dir(path: Path) -> bool:
    try:
        return path.exists() and any(path.iterdir())
    except OSError:
        return False


def env_listen_port(root: Path, default: int) -> int:
    """Port from ``.env``, then ``.env.example``. ``default`` when neither sets one."""
    for name in (".env", ".env.example"):
        path = root / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if (
                not stripped
                or stripped.startswith("#")
                or not stripped.startswith("PORT=")
            ):
                continue
            raw = stripped.split("=", 1)[1].strip().strip('"').strip("'")
            try:
                port = int(raw)
            except ValueError:
                continue
            if 1 <= port <= 65535:
                return port
    return default


def next_open_dir(
    parent: Path,
    default_name: str,
    looks_like: Callable[[Path], bool],
) -> Path | None:
    """Next ``<name>-N`` that is missing, empty, or already this sample."""
    for number in range(2, 100):
        candidate = parent / f"{default_name}-{number}"
        if not (nonempty_dir(candidate) and not looks_like(candidate)):
            return candidate
    return None


def place_sample(
    dest: Path,
    *,
    explicit: bool,
    default_name: str,
    looks_like: Callable[[Path], bool],
    recorded: Path | None = None,
    serving_of: Callable[[Path], dict[str, Any] | None] | None = None,
    relocate: bool = True,
    block_explicit_foreign: bool = False,
) -> SampleTarget:
    """Recorded serving checkout, else the next open sibling of a foreign default."""
    if (
        not explicit
        and recorded is not None
        and looks_like(recorded)
        and serving_of is not None
    ):
        verdict = serving_of(recorded)
        if verdict is not None:
            return SampleTarget(root=recorded, serving_verdict=verdict)
    foreign = nonempty_dir(dest) and not looks_like(dest)
    if relocate and not explicit and foreign and dest.name == default_name:
        sibling = next_open_dir(dest.parent, default_name, looks_like)
        if sibling is None:
            return SampleTarget(root=dest, foreign_blocked=True)
        return SampleTarget(root=sibling, relocated_from=str(dest))
    if block_explicit_foreign and explicit and foreign:
        return SampleTarget(root=dest, foreign_blocked=True)
    return SampleTarget(root=dest)
