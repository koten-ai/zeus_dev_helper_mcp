"""Resolve a sample git tag, then shallow-clone that one ref.

Beer, travel, and yelp share this. A named tag that exists is that tag.
An empty version or a missing tag is the latest semver tag. ``main`` is used
only when the remote has no semver tags. ``ls-remote`` failure, missing git,
and a clone timeout stay ``clone_failed`` and do not try another ref.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

_SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
_TAG_PREFIX = "refs/tags/"
DEFAULT_REF = "main"


def parse_remote_tags(text: str) -> list[str]:
    """Tag names from ``git ls-remote --tags``. Peeled ``^{}`` lines are ignored."""
    names: list[str] = []
    seen: set[str] = set()
    for raw in (text or "").splitlines():
        parts = raw.split()
        if len(parts) < 2:
            continue
        ref = parts[-1]
        if ref.endswith("^{}"):
            continue
        if not ref.startswith(_TAG_PREFIX):
            continue
        name = ref[len(_TAG_PREFIX) :]
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def semver_key(name: str) -> tuple[int, int, int] | None:
    """``major, minor, patch`` as integers. ``0.1.0`` and ``v0.1.0`` both match."""
    match = _SEMVER.fullmatch(name)
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def latest_semver_tag(tags: list[str]) -> str | None:
    """Greatest major.minor.patch. On a tie, prefer the name without a ``v``."""
    best: tuple[tuple[int, int, int], int, str] | None = None
    chosen: str | None = None
    for name in tags:
        key = semver_key(name)
        if key is None:
            continue
        plain = 0 if name.startswith("v") else 1
        rank = (key, plain, name)
        if best is None or rank > best:
            best = rank
            chosen = name
    return chosen


def resolve_ref(tags: list[str], version: str) -> str:
    """Exact existing tag, else the latest semver tag, else ``main``."""
    requested = (version or "").strip()
    if requested and requested in tags:
        return requested
    latest = latest_semver_tag(tags)
    if latest:
        return latest
    return DEFAULT_REF


def _requested(version: str) -> str:
    return "" if version is None else str(version).strip()


def _proc_error(proc: subprocess.CompletedProcess[str], fallback: str) -> str:
    err = (proc.stderr or proc.stdout or "").strip()
    return (err or fallback)[:800]


def resolve_clone_ref(
    repo_url: str,
    version: str = "",
    *,
    timeout_s: int = 120,
) -> dict[str, Any]:
    """List tags with ``git ls-remote --tags`` and choose the clone ref."""
    requested = _requested(version)
    cmd = ["git", "ls-remote", "--tags", repo_url]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError:
        return {
            "ok": False,
            "failure_class": "clone_failed",
            "error": "git not found on PATH",
            "kind": "git_missing",
            "requested_version": requested,
            "clone_cmd": " ".join(cmd),
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "failure_class": "clone_failed",
            "error": f"git ls-remote timed out after {timeout_s}s",
            "kind": "timeout",
            "requested_version": requested,
            "clone_cmd": " ".join(cmd),
        }
    if proc.returncode != 0:
        return {
            "ok": False,
            "failure_class": "clone_failed",
            "error": _proc_error(proc, f"git ls-remote failed (exit {proc.returncode})"),
            "kind": "ls_remote_failed",
            "requested_version": requested,
            "clone_cmd": " ".join(cmd),
        }
    tags = parse_remote_tags(proc.stdout or "")
    return {
        "ok": True,
        "ref": resolve_ref(tags, requested),
        "requested_version": requested,
        "tags": tags,
    }


def remove_partial_checkout(dest: Path) -> None:
    """Remove a directory a failed clone left behind. A symlink is unlinked only."""
    if dest.is_symlink():
        dest.unlink(missing_ok=True)
        return
    if dest.exists():
        shutil.rmtree(dest)


def _failed(
    *,
    dest: Path,
    requested: str,
    error: str,
    next_action: str,
    clone_cmd: str,
    ref: str = "",
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ok": False,
        "cloned": False,
        "failure_class": "clone_failed",
        "dest": str(dest),
        "requested_version": requested,
        "error": error,
        "next_action": next_action,
        "clone_cmd": clone_cmd,
    }
    if ref:
        out["ref"] = ref
    return out


def shallow_clone_ref(
    *,
    dest: Path,
    repo_url: str,
    version: str = "",
    timeout_s: int = 120,
    git_missing_next: str,
    timeout_next: str,
    failed_next: str,
) -> dict[str, Any]:
    """Shallow-clone ``repo_url`` at the resolved ref. One ref; no second attempt.

    When the clone fails and leaves ``dest``, that partial directory is removed
    before this returns. This does not fall through to another ref.
    """
    requested = _requested(version)
    resolved = resolve_clone_ref(repo_url, requested, timeout_s=timeout_s)
    if not resolved.get("ok"):
        kind = resolved.get("kind")
        if kind == "git_missing":
            next_action = git_missing_next
        elif kind == "timeout":
            next_action = timeout_next
        else:
            next_action = failed_next
        return _failed(
            dest=dest,
            requested=requested,
            error=str(resolved.get("error") or "git ls-remote failed"),
            next_action=next_action,
            clone_cmd=str(resolved.get("clone_cmd") or ""),
        )
    ref = str(resolved["ref"])
    cmd = ["git", "clone", "--depth", "1", "--branch", ref, repo_url, str(dest)]
    clone_cmd = " ".join(cmd)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError:
        remove_partial_checkout(dest)
        return _failed(
            dest=dest,
            requested=requested,
            error="git not found on PATH",
            next_action=git_missing_next,
            clone_cmd=clone_cmd,
            ref=ref,
        )
    except subprocess.TimeoutExpired:
        remove_partial_checkout(dest)
        return _failed(
            dest=dest,
            requested=requested,
            error=f"git clone timed out after {timeout_s}s",
            next_action=timeout_next,
            clone_cmd=clone_cmd,
            ref=ref,
        )
    if proc.returncode != 0 or not dest.is_dir():
        err = _proc_error(proc, f"git clone failed (exit {proc.returncode})")
        remove_partial_checkout(dest)
        return _failed(
            dest=dest,
            requested=requested,
            error=err,
            next_action=failed_next,
            clone_cmd=clone_cmd,
            ref=ref,
        )
    return {
        "ok": True,
        "cloned": True,
        "dest": str(dest),
        "repo": repo_url,
        "requested_version": requested,
        "ref": ref,
        "clone_cmd": clone_cmd,
    }
