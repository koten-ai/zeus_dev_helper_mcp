"""demo_yelp sample path.

use_sample writes the yelp-demo app (search is rt.agent.run_turn). Clone helpers
remain for a manual checkout and are not the created app.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from zeus_dev_helper_mcp.config import HelperConfig

YELP_REPO = "https://github.com/koten-ai/demo_yelp"
YELP_REPO_GIT = f"{YELP_REPO}.git"
DEFAULT_YELP_DIR_NAME = "demo_yelp"
ENV_YELP_DIR = "DEMO_YELP_SAMPLE_DIR"
YELP_BUCKET = "yelp-demo"
YELP_SCOPE = "_default"
_DIR_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

# Bare "yelp" and "multi" stay the multi-agent handoff. Do not add them here.
YELP_DEMO_ALIASES = frozenset(
    {
        "demo_yelp",
        "demo-yelp",
        "yelp-demo",
        "yelp_demo",
        "yelpdemo",
    }
)

def is_yelp_demo_sample(name: str) -> bool:
    """True for the yelp UI template. False for bare yelp / multi."""
    return (name or "").lower().strip() in YELP_DEMO_ALIASES


def sanitize_yelp_dir_name(project_name: str = "") -> str:
    """Directory name for a yelp clone. Default demo_yelp."""
    raw = (project_name or "").strip()
    if not raw:
        return DEFAULT_YELP_DIR_NAME
    if any(sep in raw for sep in ("/", "\\", "..")):
        return DEFAULT_YELP_DIR_NAME
    name = raw.replace(" ", "-")
    if not name or name in {".", ".."} or not _DIR_NAME_RE.match(name):
        return DEFAULT_YELP_DIR_NAME
    return name


def _state_path(cfg: HelperConfig) -> Path:
    return cfg.state_dir / "yelp_sample.json"


def save_yelp_sample_dir(cfg: HelperConfig, root: Path) -> None:
    """Persist the yelp sample path for later steps."""
    try:
        cfg.state_dir.mkdir(parents=True, exist_ok=True)
        _state_path(cfg).write_text(
            json.dumps({"yelp_sample_dir": str(root.resolve())}) + "\n",
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001, S110
        pass


def load_yelp_sample_dir(cfg: HelperConfig | None = None) -> Path | None:
    if cfg is None:
        return None
    path = _state_path(cfg)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = str(data.get("yelp_sample_dir") or "").strip()
        if not raw:
            return None
        found = Path(raw).expanduser().resolve()
        return found if found.is_dir() else None
    except Exception:  # noqa: BLE001
        return None


def recorded_yelp_sample_dir(cfg: HelperConfig | None = None) -> Path | None:
    """Directory named by DEMO_YELP_SAMPLE_DIR or yelp_sample.json, if it exists.

    A sibling checkout that use_sample has not recorded does not count.
    """
    env = os.environ.get(ENV_YELP_DIR, "").strip()
    if env:
        found = Path(env).expanduser()
        if found.is_dir():
            return found.resolve()
    return load_yelp_sample_dir(cfg)


def _candidate_yelp_dirs(here: Path) -> list[Path]:
    """Common clone locations relative to the Helper package and cwd."""
    helper_root = here.parents[2]
    monorepo = helper_root.parent
    names = ("demo_yelp", "yelp-demo", "demos/demo_yelp")
    out: list[Path] = []
    for base in (
        monorepo,
        helper_root.parent,
        Path.home() / "Documents/git_folders/fujio-turner",
        Path.cwd(),
        Path.cwd().parent,
    ):
        for name in names:
            out.append(base / name)
    out.append(monorepo / "demos" / "demo_yelp")
    out.append(Path.cwd() / "demos" / "demo_yelp")
    seen: set[str] = set()
    unique: list[Path] = []
    for candidate in out:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _find_yelp_dir(explicit: str = "", cfg: HelperConfig | None = None) -> Path | None:
    if explicit:
        found = Path(explicit).expanduser().resolve()
        return found if found.is_dir() else None
    env = os.environ.get(ENV_YELP_DIR, "").strip()
    if env:
        found = Path(env).expanduser().resolve()
        if found.is_dir():
            return found
    persisted = load_yelp_sample_dir(cfg)
    if persisted is not None:
        return persisted
    here = Path(__file__).resolve()
    for candidate in _candidate_yelp_dirs(here):
        if candidate.is_dir():
            return candidate
    return None


def set_demo_yelp_sample_dir_env(root: Path) -> str:
    """Set process env DEMO_YELP_SAMPLE_DIR to the sample root."""
    path = str(root.expanduser().resolve())
    os.environ[ENV_YELP_DIR] = path
    return path


def _default_clone_parent() -> Path:
    """Prefer the directory that contains the Helper repo; else cwd."""
    here = Path(__file__).resolve()
    helper_root = here.parents[2]
    monorepo = helper_root.parent
    if monorepo.is_dir():
        return monorepo
    return Path.cwd()


def clone_yelp_sample(
    *,
    dest: Path,
    repo_url: str = YELP_REPO_GIT,
    timeout_s: int = 120,
) -> dict[str, Any]:
    """Shallow-clone demo_yelp into dest (dest must not exist yet).

    The repo may be private. The clone URL carries no token. Failure tells the
    caller to clone manually and set DEMO_YELP_SAMPLE_DIR.
    """
    dest = dest.expanduser().resolve()
    if dest.exists():
        return {
            "ok": False,
            "cloned": False,
            "dest": str(dest),
            "error": f"destination already exists: {dest}",
            "next_action": "Pass an unused project_name / path, or set sample_dir to the existing clone",
        }
    parent = dest.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {
            "ok": False,
            "cloned": False,
            "dest": str(dest),
            "error": f"cannot create parent {parent}: {exc}",
            "next_action": "Choose a writable parent directory",
        }

    cmd = ["git", "clone", "--depth", "1", repo_url, str(dest)]
    manual = f"clone manually and set {ENV_YELP_DIR}"
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
            "cloned": False,
            "dest": str(dest),
            "error": "git not found on PATH",
            "next_action": f"Install git, or {manual}",
            "clone_cmd": " ".join(cmd),
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "cloned": False,
            "dest": str(dest),
            "error": f"git clone timed out after {timeout_s}s",
            "next_action": f"Retry use_sample or {manual}",
            "clone_cmd": " ".join(cmd),
        }

    if proc.returncode != 0 or not dest.is_dir():
        err = (proc.stderr or proc.stdout or "").strip()[:800]
        return {
            "ok": False,
            "cloned": False,
            "dest": str(dest),
            "error": err or f"git clone failed (exit {proc.returncode})",
            "next_action": f"Fix network/git access, or {manual}",
            "clone_cmd": " ".join(cmd),
        }

    return {
        "ok": True,
        "cloned": True,
        "dest": str(dest),
        "repo": repo_url,
        "clone_cmd": " ".join(cmd),
    }


def _resolve_clone_dest(
    *,
    sample_dir: str = "",
    project_name: str = "",
    parent_dir: str = "",
) -> Path:
    """Destination directory for a new yelp clone."""
    parent = (
        Path(parent_dir).expanduser().resolve()
        if parent_dir.strip()
        else _default_clone_parent()
    )
    raw = sample_dir.strip()
    if raw:
        dest = Path(raw).expanduser()
        if dest.is_absolute() or len(dest.parts) > 1:
            return dest.resolve()
        name = sanitize_yelp_dir_name(project_name or dest.name)
        return parent / name
    return parent / sanitize_yelp_dir_name(project_name)


def validate_yelp_layout(root: Path) -> dict[str, Any]:
    """README plus the frontend package or the Python project file."""
    readme = (root / "README.md").is_file()
    frontend_package = (root / "frontend" / "package.json").is_file()
    pyproject = (root / "pyproject.toml").is_file()
    return {
        "ok": readme and (frontend_package or pyproject),
        "readme": readme,
        "frontend_package": frontend_package,
        "pyproject": pyproject,
    }


def ensure_yelp_sample(
    cfg: HelperConfig,
    *,
    sample_dir: str = "",
    project_name: str = "",
    parent_dir: str = "",
    clone_if_missing: bool = True,
) -> dict[str, Any]:
    """Write the yelp-demo app and set DEMO_YELP_SAMPLE_DIR.

    Search is rt.agent.run_turn with chat_request omitted. A git checkout at the
    destination is left unchanged.
    """
    from zeus_dev_helper_mcp.yelp_app import ensure_yelp_app

    return ensure_yelp_app(
        cfg,
        sample_dir=sample_dir,
        project_name=project_name,
        parent_dir=parent_dir,
        clone_if_missing=clone_if_missing,
    )
