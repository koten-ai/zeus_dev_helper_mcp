"""demo_yelp UI template: locate or shallow-clone the repo.

Same coach shape as travel (find, else clone, set an env var). This module does
not write a BFF and does not rewrite Docker packaging.
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

_QUICK_START = "cd frontend && npm install && npm run dev"


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


def _ready_next_action(env_path: str) -> str:
    return (
        f"{ENV_YELP_DIR}={env_path}. "
        f"UI quick start: {_QUICK_START} (http://localhost:5173). "
        f"Continue readiness_check with bucket {YELP_BUCKET} scope {YELP_SCOPE}."
    )


def ensure_yelp_sample(
    cfg: HelperConfig,
    *,
    sample_dir: str = "",
    project_name: str = "",
    parent_dir: str = "",
    clone_if_missing: bool = True,
) -> dict[str, Any]:
    """Locate demo_yelp or clone it; set DEMO_YELP_SAMPLE_DIR.

    - If sample_dir points at an existing directory, use it (no clone).
    - If no local sample is found and clone_if_missing, shallow-clone into
      parent_dir/project_name (defaults: Helper repo parent / demo_yelp).
    - On success, sets process env DEMO_YELP_SAMPLE_DIR and persists state.
    """
    dir_name = sanitize_yelp_dir_name(project_name)
    found = _find_yelp_dir(sample_dir, cfg=cfg)
    clone_info: dict[str, Any] | None = None

    if found is None and clone_if_missing:
        dest = _resolve_clone_dest(
            sample_dir=sample_dir,
            project_name=project_name,
            parent_dir=parent_dir,
        )
        if dest.is_dir():
            found = dest
        else:
            clone_info = clone_yelp_sample(dest=dest)
            if clone_info.get("ok"):
                found = dest
            else:
                return {
                    "ok": False,
                    "local_dir": None,
                    "cloned": False,
                    "project_name": dir_name,
                    "clone": clone_info,
                    "layout": None,
                    "env": {ENV_YELP_DIR: None},
                    "next_action": clone_info.get("next_action")
                    or f"Clone manually and set {ENV_YELP_DIR}",
                    "repo": YELP_REPO,
                    "private": True,
                }

    if found is None:
        return {
            "ok": False,
            "local_dir": None,
            "cloned": False,
            "project_name": dir_name,
            "clone": clone_info,
            "layout": None,
            "env": {ENV_YELP_DIR: None},
            "next_action": (
                f"No local demo_yelp; enable clone_if_missing or set {ENV_YELP_DIR} / sample_dir"
            ),
            "repo": YELP_REPO,
            "private": True,
        }

    env_path = set_demo_yelp_sample_dir_env(found)
    save_yelp_sample_dir(cfg, found)
    layout = validate_yelp_layout(found)
    if layout.get("ok"):
        next_action = _ready_next_action(env_path)
    else:
        next_action = (
            f"{ENV_YELP_DIR}={env_path}. "
            "Clone/path exists but layout looks incomplete — need README.md and "
            "frontend/package.json or pyproject.toml."
        )
    return {
        "ok": bool(layout.get("ok")),
        "local_dir": str(found),
        "cloned": bool(clone_info and clone_info.get("cloned")),
        "project_name": found.name,
        "clone": clone_info,
        "layout": layout,
        "env": {ENV_YELP_DIR: env_path},
        "repo": YELP_REPO,
        "private": True,
        "next_action": next_action,
    }
