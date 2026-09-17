"""demo_travel_sample golden path integration (ZDH-10)."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from zeus_dev_helper_mcp.checklist import set_item_status
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.docs_links import docs_url

TRAVEL_REPO = "https://github.com/koten-ai/demo_travel_sample"
TRAVEL_REPO_GIT = f"{TRAVEL_REPO}.git"
DEFAULT_TRAVEL_DIR_NAME = "demo_travel_sample"
ENV_TRAVEL_DIR = "DEMO_TRAVEL_SAMPLE_DIR"
_DIR_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

TRAVEL_MARKERS = (
    "README.md",
    "pyproject.toml",
    "requirements.txt",
    "src",
    "Makefile",
    "docker-compose.yml",
    "Dockerfile",
)

_COMPOSE_NAMES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")
_README_DOCKER_RE = re.compile(
    r"docker\s+compose|docker-compose|###\s*docker\b|docker\s*\(\s*recommended\s*\)",
    re.IGNORECASE,
)
_HOST_PORT_RE = re.compile(
    r"localhost:(\d{2,5})|ports:\s*\n(?:\s*-\s*[\"']?)(\d{2,5}):",
    re.IGNORECASE,
)


def _travel_state_path(cfg: HelperConfig) -> Path:
    return cfg.state_dir / "travel_sample.json"


def save_travel_sample_dir(cfg: HelperConfig, root: Path) -> None:
    """Persist discovered travel sample path for later smokes."""
    try:
        cfg.state_dir.mkdir(parents=True, exist_ok=True)
        _travel_state_path(cfg).write_text(
            json.dumps({"travel_sample_dir": str(root.resolve())}) + "\n",
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001, S110
        pass


def load_travel_sample_dir(cfg: HelperConfig | None = None) -> Path | None:
    if cfg is not None:
        path = _travel_state_path(cfg)
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                raw = str(data.get("travel_sample_dir") or "").strip()
                if raw:
                    p = Path(raw).expanduser().resolve()
                    if p.is_dir():
                        return p
            except Exception:  # noqa: BLE001, S110
                pass
    return None


def _candidate_travel_dirs(here: Path) -> list[Path]:
    """Common clone locations relative to Helper package / cwd."""
    # here = .../zeus_dev_helper_mcp/src/zeus_dev_helper_mcp/travel.py
    helper_root = here.parents[2]  # zeus_dev_helper_mcp
    monorepo = helper_root.parent  # e.g. koten-ai
    names = ("demo_travel_sample", "travel-sample", "demos/travel-sample")
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
    # Explicit demos layout under monorepo
    out.append(monorepo / "demos" / "travel-sample")
    out.append(Path.cwd() / "demos" / "travel-sample")
    # Dedupe while preserving order
    seen: set[str] = set()
    unique: list[Path] = []
    for p in out:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


def _find_travel_dir(explicit: str = "", cfg: HelperConfig | None = None) -> Path | None:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        return p if p.is_dir() else None
    env = os.environ.get(ENV_TRAVEL_DIR, "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        if p.is_dir():
            return p
    persisted = load_travel_sample_dir(cfg)
    if persisted is not None:
        return persisted
    here = Path(__file__).resolve()
    for c in _candidate_travel_dirs(here):
        if c.is_dir():
            return c
    return None


def sanitize_travel_dir_name(project_name: str = "") -> str:
    """Directory name for a travel clone. Default demo_travel_sample."""
    raw = (project_name or "").strip()
    if not raw:
        return DEFAULT_TRAVEL_DIR_NAME
    # Reject path separators / traversal; allow a single segment only.
    if any(sep in raw for sep in ("/", "\\", "..")):
        return DEFAULT_TRAVEL_DIR_NAME
    name = raw.replace(" ", "-")
    if not name or name in {".", ".."} or not _DIR_NAME_RE.match(name):
        return DEFAULT_TRAVEL_DIR_NAME
    return name


def set_demo_travel_sample_dir_env(root: Path) -> str:
    """Set process env DEMO_TRAVEL_SAMPLE_DIR to the sample root."""
    path = str(root.expanduser().resolve())
    os.environ[ENV_TRAVEL_DIR] = path
    return path


def _default_clone_parent() -> Path:
    """Prefer monorepo sibling of Helper; else cwd."""
    here = Path(__file__).resolve()
    helper_root = here.parents[2]  # zeus_dev_helper_mcp
    monorepo = helper_root.parent
    if monorepo.is_dir():
        return monorepo
    return Path.cwd()


def clone_travel_sample(
    *,
    dest: Path,
    repo_url: str = TRAVEL_REPO_GIT,
    timeout_s: int = 120,
) -> dict[str, Any]:
    """Shallow-clone public demo_travel_sample into dest (dest must not exist yet)."""
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
    except OSError as e:
        return {
            "ok": False,
            "cloned": False,
            "dest": str(dest),
            "error": f"cannot create parent {parent}: {e}",
            "next_action": "Choose a writable parent directory",
        }

    cmd = ["git", "clone", "--depth", "1", repo_url, str(dest)]
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
            "next_action": "Install git, or clone manually and set DEMO_TRAVEL_SAMPLE_DIR",
            "clone_cmd": " ".join(cmd),
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "cloned": False,
            "dest": str(dest),
            "error": f"git clone timed out after {timeout_s}s",
            "next_action": "Retry use_sample or clone manually",
            "clone_cmd": " ".join(cmd),
        }

    if proc.returncode != 0 or not dest.is_dir():
        err = (proc.stderr or proc.stdout or "").strip()[:800]
        return {
            "ok": False,
            "cloned": False,
            "dest": str(dest),
            "error": err or f"git clone failed (exit {proc.returncode})",
            "next_action": "Fix network/git access, or clone manually and set DEMO_TRAVEL_SAMPLE_DIR",
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
    """Destination directory for a new travel clone."""
    parent = (
        Path(parent_dir).expanduser().resolve()
        if parent_dir.strip()
        else _default_clone_parent()
    )
    raw = sample_dir.strip()
    if raw:
        p = Path(raw).expanduser()
        # Absolute or nested path → use as the clone destination directory.
        if p.is_absolute() or len(p.parts) > 1:
            return p.resolve()
        # Bare name → under parent (prefer project_name when provided).
        name = sanitize_travel_dir_name(project_name or p.name)
        return parent / name
    return parent / sanitize_travel_dir_name(project_name)


def ensure_travel_sample(
    cfg: HelperConfig,
    *,
    sample_dir: str = "",
    project_name: str = "",
    parent_dir: str = "",
    clone_if_missing: bool = True,
) -> dict[str, Any]:
    """Locate demo_travel_sample or clone the public repo; set DEMO_TRAVEL_SAMPLE_DIR.

    - If sample_dir points at an existing directory, use it (no clone).
    - If no local sample is found and clone_if_missing, shallow-clone into
      parent_dir/project_name (defaults: Helper monorepo parent / demo_travel_sample).
    - On success, sets process env DEMO_TRAVEL_SAMPLE_DIR and persists state.
    """
    dir_name = sanitize_travel_dir_name(project_name)
    found = _find_travel_dir(sample_dir, cfg=cfg)
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
            clone_info = clone_travel_sample(dest=dest)
            if clone_info.get("ok"):
                found = dest
            else:
                return {
                    "ok": False,
                    "local_dir": None,
                    "cloned": False,
                    "project_name": dir_name,
                    "clone": clone_info,
                    "env": {ENV_TRAVEL_DIR: None},
                    "next_action": clone_info.get("next_action")
                    or "Clone manually and set DEMO_TRAVEL_SAMPLE_DIR, or scaffold_app",
                    "repo": TRAVEL_REPO,
                    "private": False,
                }

    if found is None:
        return {
            "ok": False,
            "local_dir": None,
            "cloned": False,
            "project_name": dir_name,
            "clone": clone_info,
            "env": {ENV_TRAVEL_DIR: None},
            "next_action": (
                "No local demo_travel_sample; enable clone_if_missing or set "
                f"{ENV_TRAVEL_DIR} / sample_dir"
            ),
            "repo": TRAVEL_REPO,
            "private": False,
        }

    env_path = set_demo_travel_sample_dir_env(found)
    save_travel_sample_dir(cfg, found)
    layout = validate_travel_layout(found)
    return {
        "ok": bool(layout.get("ok")),
        "local_dir": str(found),
        "cloned": bool(clone_info and clone_info.get("cloned")),
        "project_name": found.name,
        "clone": clone_info,
        "layout": layout,
        "env": {ENV_TRAVEL_DIR: env_path},
        "repo": TRAVEL_REPO,
        "private": False,
        "next_action": (
            f"DEMO_TRAVEL_SAMPLE_DIR={env_path}. Continue readiness_check and smokes "
            "(optional: docker compose up --build for the demo UI)."
            if layout.get("ok")
            else "Clone/path exists but layout looks incomplete — check README / sample_dir"
        ),
    }


def validate_travel_layout(root: Path) -> dict[str, Any]:
    found = []
    missing = []
    for name in TRAVEL_MARKERS:
        p = root / name
        if p.exists():
            found.append(name)
        else:
            missing.append(name)
    # soft pass if README + something python-ish exists
    ok = (root / "README.md").is_file() and (
        (root / "pyproject.toml").is_file()
        or (root / "requirements.txt").is_file()
        or (root / "src").is_dir()
    )
    return {
        "ok": ok,
        "root": str(root),
        "found": found,
        "missing": missing,
        "note": "Markers are soft — sample layout may evolve",
    }


def _compose_file(root: Path) -> Path | None:
    for name in _COMPOSE_NAMES:
        p = root / name
        if p.is_file():
            return p
    return None


def _parse_host_port(*texts: str, default: int = 5050) -> int:
    for text in texts:
        if not text:
            continue
        m = _HOST_PORT_RE.search(text)
        if not m:
            continue
        for g in m.groups():
            if g:
                try:
                    return int(g)
                except ValueError:
                    continue
    return default


def docker_install_next_action(root: Path, *, host_port: int = 5050) -> str:
    return (
        f"demo_travel_sample documents Docker install. In {root}: "
        "cp config.example.json config.json; set llm_provider.api_key and zeus.url; "
        f"then `docker compose up --build` and open http://localhost:{host_port} "
        f"(tracer: http://localhost:{host_port}/?debug=true). "
        "Or install 'kotenai-zeus-client>=2.3.0' / zeus-dev-helper-mcp[agent] and retry smoke_test_agent."
    )


def detect_docker_install(root: Path | None) -> dict[str, Any]:
    """Detect Docker packaging / README install instructions for a travel sample root."""
    if root is None or not root.is_dir():
        return {
            "ok": False,
            "local_dir": None,
            "has_compose": False,
            "has_dockerfile": False,
            "readme_signals": False,
            "recommended": False,
            "host_port": 5050,
            "next_action": "",
        }

    compose = _compose_file(root)
    has_compose = compose is not None
    has_dockerfile = (root / "Dockerfile").is_file()
    readme_text = ""
    readme = root / "README.md"
    if readme.is_file():
        try:
            readme_text = readme.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            readme_text = ""
    readme_signals = bool(readme_text and _README_DOCKER_RE.search(readme_text))
    recommended = bool(
        re.search(r"docker\s*\(\s*recommended\s*\)", readme_text, re.IGNORECASE)
    )
    compose_text = ""
    if compose is not None:
        try:
            compose_text = compose.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            compose_text = ""
    host_port = _parse_host_port(readme_text, compose_text, default=5050)
    ok = bool(has_compose or has_dockerfile or readme_signals)
    next_action = docker_install_next_action(root, host_port=host_port) if ok else ""
    return {
        "ok": ok,
        "local_dir": str(root),
        "has_compose": has_compose,
        "has_dockerfile": has_dockerfile,
        "readme_signals": readme_signals,
        "recommended": recommended,
        "host_port": host_port,
        "compose_file": str(compose) if compose else None,
        "next_action": next_action,
    }


def resolve_travel_docker_guidance(
    cfg: HelperConfig | None = None,
    *,
    sample_dir: str = "",
) -> dict[str, Any] | None:
    """Return docker detect payload when travel sample + Docker install are present."""
    root = _find_travel_dir(sample_dir, cfg=cfg)
    if root is None:
        return None
    layout = validate_travel_layout(root)
    if not layout.get("ok"):
        return None
    docker = detect_docker_install(root)
    if not docker.get("ok"):
        return None
    docker = dict(docker)
    docker["layout"] = layout
    docker["sample"] = "travel"
    return docker


def travel_golden_path(
    cfg: HelperConfig,
    *,
    sample_dir: str = "",
    project_name: str = "",
    parent_dir: str = "",
    clone_if_missing: bool = True,
) -> dict[str, Any]:
    """Locate or clone public demo_travel_sample; validate layout; set DEMO_TRAVEL_SAMPLE_DIR."""
    ensured = ensure_travel_sample(
        cfg,
        sample_dir=sample_dir,
        project_name=project_name,
        parent_dir=parent_dir,
        clone_if_missing=clone_if_missing,
    )
    root_s = ensured.get("local_dir")
    root = Path(root_s) if root_s else None
    layout = ensured.get("layout") or (validate_travel_layout(root) if root else None)
    docker = detect_docker_install(root) if root else None

    phase5 = (
        "smoke_test_zeus then docker compose up --build (demo UI) "
        "or smoke_test_agent with [agent] extra"
        if docker and docker.get("ok")
        else "smoke_test_zeus then sample make smoke / smoke_test_agent"
    )

    phases = [
        {"phase": "0", "action": "start_project(goal=single-agent, sample=travel)"},
        {"phase": "1", "action": "set_prereq with travel-sample bucket/scope from sample README"},
        {"phase": "2", "action": "readiness_check against Zeus :8080"},
        {
            "phase": "3",
            "action": (
                "use_sample clones public demo_travel_sample when missing "
                "(optional project_name for directory); or scaffold_app fallback"
            ),
        },
        {"phase": "4", "action": "bootstrap_scope + stamp catalog in Hub Workbench"},
        {"phase": "5", "action": phase5},
        {"phase": "6+", "action": "gap_report; customize domain"},
    ]

    env_path = (ensured.get("env") or {}).get(ENV_TRAVEL_DIR)
    helper_readme_section = f"""## Use with Developer Helper MCP

1. Install [zeus_dev_helper_mcp](https://github.com/koten-ai/zeus_dev_helper_mcp).
2. `use_sample` clones this public repo when needed and sets `DEMO_TRAVEL_SAMPLE_DIR`.
3. `export DEMO_TRAVEL_SAMPLE_DIR={env_path or "/path/to/this/repo"}` in your shell for new processes.
4. `export ZEUS_URL=http://localhost:8080` and scope env from this sample's docs.
5. MCP tools: `start_project(sample=travel)` → `use_sample` → `readiness_check` → smokes.
6. If this sample documents Docker: `cp config.example.json config.json` then `docker compose up --build`.
7. Published docs: https://docs.koten.ai/
"""

    if layout and layout.get("ok") and root is not None:
        try:
            set_item_status(cfg, "0.2", "done", evidence=f"travel_layout={root}")
            set_item_status(cfg, "3.1", "done", evidence=f"travel_dir={root}")
        except Exception:  # noqa: BLE001, S110
            pass

    if not ensured.get("ok") and root is None:
        next_action = ensured.get("next_action") or (
            "Clone failed — fix git/network or scaffold_app for a minimal path without the demo UI."
        )
    elif root and docker and docker.get("ok"):
        next_action = (
            "Layout found with Docker install docs — "
            f"{docker.get('next_action') or 'run docker compose from the sample root'}; "
            "continue readiness_check and smokes with travel scope env."
        )
    elif root:
        next_action = ensured.get("next_action") or (
            "Layout found — continue readiness_check and smokes with travel scope env."
        )
    else:
        next_action = ensured.get("next_action") or "use_sample to clone demo_travel_sample"

    return {
        "ok": bool(ensured.get("ok")),
        "sample": "travel",
        "repo": TRAVEL_REPO,
        "private": False,
        "clone": (ensured.get("clone") or {}).get("clone_cmd")
        or f"git clone --depth 1 {TRAVEL_REPO_GIT}",
        "cloned": bool(ensured.get("cloned")),
        "project_name": ensured.get("project_name"),
        "local_dir": str(root) if root else None,
        "layout": layout,
        "docker": docker,
        "ensure": ensured,
        "env": {
            ENV_TRAVEL_DIR: env_path,
            "ZEUS_URL": "http://localhost:8080",
            "ZEUS_BUCKET": "(from sample README — often travel-sample)",
            "ZEUS_SCOPE": "(from sample README)",
        },
        "helper_phases": phases,
        "sample_readme_snippet": helper_readme_section,
        "next_action": next_action,
        "docs": {
            "using_client": docs_url("zeus-client/using-zeus-client.md"),
            "helper": docs_url("zeus-client/dev-helper-mcp.md"),
            "demo_builder": "https://github.com/koten-ai/zeus_client_python/tree/main/docs/demo-builder",
            "repo": TRAVEL_REPO,
        },
        "jira": "https://kotenai.atlassian.net/browse/ZDH-10",
    }
