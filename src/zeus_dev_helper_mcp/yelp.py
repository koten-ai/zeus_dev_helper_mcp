"""LocalAI yelp-demo template: locate or shallow-clone koten-ai/demo_yelp.

Same coach shape as travel (find, else clone, set an env var). The git checkout
is the app. This module does not write a BFF and does not rewrite Docker packaging.
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

_QUICK_START = (
    "pip install -e . && python -m local_guide"
    "  # API http://127.0.0.1:5000; "
    "cd frontend && npm install && npm run dev"
    "  # SPA http://localhost:5173, proxies /api to port 5000"
)
# The git checkout is the app. A beer-shaped BFF is a different product.
_DO_NOT_REPLACE = [
    "Do not scaffold_app",
    "Do not copy demo_beer_sample",
    "Do not write a new FastAPI or static app",
    "The demo_yelp git checkout is the app; run that repository",
]


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


def _template_dir(path: Path | None) -> Path | None:
    """Return path when it is a LocalAI demo_yelp checkout."""
    if path is None:
        return None
    resolved = path.expanduser().resolve()
    if resolved.is_dir() and validate_yelp_layout(resolved).get("ok"):
        return resolved
    return None


def recorded_yelp_sample_dir(cfg: HelperConfig | None = None) -> Path | None:
    """LocalAI checkout named by DEMO_YELP_SAMPLE_DIR or yelp_sample.json.

    A generated app, or any directory without the template layout, does not count.
    A sibling checkout that use_sample has not recorded does not count.
    """
    env = os.environ.get(ENV_YELP_DIR, "").strip()
    if env:
        found = _template_dir(Path(env))
        if found is not None:
            return found
    return _template_dir(load_yelp_sample_dir(cfg))


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
        found = _template_dir(Path(env))
        if found is not None:
            return found
    found = _template_dir(load_yelp_sample_dir(cfg))
    if found is not None:
        return found
    here = Path(__file__).resolve()
    for candidate in _candidate_yelp_dirs(here):
        found = _template_dir(candidate)
        if found is not None:
            return found
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


def _ready_next_action(env_path: str, images: dict[str, Any] | None = None) -> str:
    text = (
        f"The app is the LocalAI template ({YELP_REPO}) at {env_path}. "
        f"Run it: {_QUICK_START} (http://localhost:5173). "
        "Search POSTs /api/search. That handler loads the live "
        f"chat_request.json for {YELP_BUCKET}/{YELP_SCOPE} mode analytics and "
        "sends that document as the session body. "
        "The business page GETs /api/business/{id} for an id that is not in the "
        "bundled catalog. Review text is the source document, not the rev: doc key. "
        "This repository is the template. "
        "Do not scaffold_app, do not copy demo_beer_sample, and do not write a new app. "
        f"{ENV_YELP_DIR}={env_path}. "
        f"Bucket {YELP_BUCKET}, scope {YELP_SCOPE}."
    )
    if not images or images.get("skipped"):
        return text
    files = int(images.get("files") or 0)
    failed = int(images.get("failed") or 0)
    text += (
        f" Business photos: {files} file(s) under frontend/public/business-images/<id>/ "
        "(no biz: prefix, no API key)."
    )
    if failed:
        text += f" {failed} photo download(s) failed."
    return text


def _unbound(
    *,
    dir_name: str,
    clone_info: dict[str, Any] | None,
    next_action: str,
) -> dict[str, Any]:
    return {
        "ok": False,
        "local_dir": None,
        "cloned": False,
        "project_name": dir_name,
        "clone": clone_info,
        "layout": None,
        "env": {ENV_YELP_DIR: None},
        "next_action": next_action,
        "repo": YELP_REPO,
        "private": True,
        "do_not": list(_DO_NOT_REPLACE),
    }


def ensure_yelp_sample(
    cfg: HelperConfig,
    *,
    sample_dir: str = "",
    project_name: str = "",
    parent_dir: str = "",
    clone_if_missing: bool = True,
) -> dict[str, Any]:
    """Locate the LocalAI demo_yelp template or clone it; set DEMO_YELP_SAMPLE_DIR.

    - If sample_dir points at an existing directory, use it (no clone).
    - If parent_dir is set and sample_dir is not, clone into
      parent_dir/project_name. A checkout outside that directory is not used.
    - Otherwise, if no local sample is found and clone_if_missing, shallow-clone
      into the Helper repo parent / demo_yelp.
    - On success, sets process env DEMO_YELP_SAMPLE_DIR and persists state.
      The checkout is the app.
    """
    dir_name = sanitize_yelp_dir_name(project_name)
    clone_info: dict[str, Any] | None = None
    # parent_dir is the caller's workspace. A sibling checkout outside it is
    # not the app they asked to create.
    pin_parent = bool(parent_dir.strip()) and not sample_dir.strip()
    if pin_parent:
        found = None
        dest = _resolve_clone_dest(project_name=project_name, parent_dir=parent_dir)
        if dest.is_dir():
            found = dest
        elif clone_if_missing:
            clone_info = clone_yelp_sample(dest=dest)
            if clone_info.get("ok"):
                found = dest
            else:
                sibling = _find_yelp_dir("", cfg=cfg)
                extra = ""
                if sibling is not None and sibling.resolve() != dest.resolve():
                    extra = (
                        f" An existing checkout is at {sibling}. "
                        "Pass sample_dir to use that checkout. Do not write a new app."
                    )
                return _unbound(
                    dir_name=dir_name,
                    clone_info=clone_info,
                    next_action=(
                        clone_info.get("next_action")
                        or f"Clone manually and set {ENV_YELP_DIR}"
                    )
                    + extra,
                )
        if found is None:
            return _unbound(
                dir_name=dir_name,
                clone_info=clone_info,
                next_action=(
                    f"No demo_yelp under {parent_dir}; enable clone_if_missing "
                    f"or set {ENV_YELP_DIR} / sample_dir. Do not write a new app."
                ),
            )
    else:
        found = _find_yelp_dir(sample_dir, cfg=cfg)
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
                    return _unbound(
                        dir_name=dir_name,
                        clone_info=clone_info,
                        next_action=clone_info.get("next_action")
                        or f"Clone manually and set {ENV_YELP_DIR}",
                    )
        if found is None:
            return _unbound(
                dir_name=dir_name,
                clone_info=clone_info,
                next_action=(
                    f"No local demo_yelp; enable clone_if_missing or set {ENV_YELP_DIR} / sample_dir"
                ),
            )

    layout = validate_yelp_layout(found)
    if not layout.get("ok"):
        return _unbound(
            dir_name=dir_name,
            clone_info=clone_info,
            next_action=(
                f"{found} is not the LocalAI template ({YELP_REPO}). "
                "Need README.md and frontend/package.json or pyproject.toml. "
                "Do not overwrite it and do not write a new app."
            ),
        )
    from zeus_dev_helper_mcp.yelp_config import pin_yelp_client, write_yelp_config
    from zeus_dev_helper_mcp.yelp_images import apply_yelp_business_images
    from zeus_dev_helper_mcp.yelp_search import apply_yelp_live_search

    search = apply_yelp_live_search(found)
    images = apply_yelp_business_images(found)
    client_pin = pin_yelp_client(found)
    app_config = write_yelp_config(cfg, found)
    env_path = set_demo_yelp_sample_dir_env(found)
    save_yelp_sample_dir(cfg, found)
    config_blocked = app_config.get("failure_class") == "login_not_in_process"
    return {
        "ok": not config_blocked,
        "local_dir": str(found),
        "cloned": bool(clone_info and clone_info.get("cloned")),
        "project_name": found.name,
        "clone": clone_info,
        "layout": layout,
        "search": search,
        "images": images,
        "client": client_pin,
        "app_config": {key: value for key, value in app_config.items() if key != "next_action"},
        "failure_class": app_config.get("failure_class"),
        "env": {ENV_YELP_DIR: env_path},
        "repo": YELP_REPO,
        "private": True,
        "do_not": list(_DO_NOT_REPLACE),
        "next_action": (
            str(app_config.get("next_action"))
            if config_blocked
            else _ready_next_action(env_path, images)
        ),
    }
