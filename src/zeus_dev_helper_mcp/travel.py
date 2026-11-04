"""demo_travel_sample golden path integration (ZDH-10)."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zeus_dev_helper_mcp.checklist import set_item_status
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.docs_links import docs_url
from zeus_dev_helper_mcp.python_runtime import launch_note, venv_setup_shell

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
# Upstream demo_travel_sample ships monorepo Docker (context: .. + sibling
# zeus_client_python). Standalone clones need a local-context rewrite.
_MONOREPO_DOCKER_MARKERS = (
    "demo_travel_sample/",
    "zeus_client_python",
    "file:../zeus_client_python",
)
# 2.4.x has parse_pipeline_envelope. 2.3.0 is not enough for the TravelPlan BFF
# (LL-2026-08-25-001 / LL-2026-08-25-003). The BFF calls run_turn; it does not POST /pipeline.
_STANDALONE_CLIENT_DEP = "kotenai-zeus-client>=2.4.0,<2.5"
_STANDALONE_DOCKERFILE = """\
FROM python:3.12-slim

WORKDIR /app

# Standalone build: compose context is this app directory (Helper-prepared).
# pip installs kotenai-zeus-client 2.4.x. Pipeline envelope recovery stays in
# that SDK. This BFF calls rt.agent.run_turn and does not POST /pipeline.
COPY pyproject.toml requirements.txt LICENSE ./
COPY src ./src
COPY data ./data
COPY config.example.json .

RUN pip install --no-cache-dir -r requirements.txt \\
    && pip install --no-cache-dir -e .

ENV PORT=5000
ENV ZEUS_CLIENT_CONFIG_DIR=/app
ENV ZEUS_CHAT_REQUESTS_DIR=/app/data/chat_requests

EXPOSE 5000
CMD ["python", "-m", "travel_planner"]
"""
_STANDALONE_COMPOSE = """\
services:
  travel-planner:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: {container_name}
    ports:
      - "5050:5000"
    environment:
      ENVIRONMENT: dev
      # Reach Zeus on the host from this container.
      ZEUS_URL: "http://host.docker.internal:8080"
      CHAT_LOG_PATH: "/app/data/chats.jsonl"
      ZEUS_CLIENT_CONFIG_DIR: "/app"
      ZEUS_CHAT_REQUESTS_DIR: "/app/data/chat_requests"
      PORT: "5000"
    volumes:
      - ./config.json:/app/config.json
      - ./data:/app/data
      - ./src/travel_planner/templates:/app/src/travel_planner/templates
      - ./src/travel_planner/static:/app/src/travel_planner/static
      - ./src/travel_planner:/app/src/travel_planner
      - ./data/chat_requests:/app/data/chat_requests
    extra_hosts:
      - "host.docker.internal:host-gateway"
    restart: unless-stopped
"""
_STANDALONE_DOCKERIGNORE = """\
__pycache__
*.pyc
.git
.grok
.venv
config.json
.env
mcps
terminals
*.md
data/chats.jsonl
data/*.jsonl
"""
_PYPROJECT_FILE_DEP_RE = re.compile(
    r"""["']kotenai-zeus-client\s*@\s*file:\.\./zeus_client_python["']""",
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


def recorded_travel_dir(cfg: HelperConfig | None = None) -> Path | None:
    """Checkout named by ``DEMO_TRAVEL_SAMPLE_DIR`` or ``travel_sample.json``."""
    env = os.environ.get(ENV_TRAVEL_DIR, "").strip()
    if env:
        path = Path(env).expanduser()
        if path.is_dir():
            return path.resolve()
    return load_travel_sample_dir(cfg)


def _find_travel_dir(explicit: str = "", cfg: HelperConfig | None = None) -> Path | None:
    """Recorded checkout for Docker guidance. Not the clone destination."""
    if explicit:
        path = Path(explicit).expanduser().resolve()
        return path if path.is_dir() else None
    return recorded_travel_dir(cfg)


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


def looks_like_travel_sample(root: Path) -> bool:
    """True for the TravelPlan tree or a layout ``validate_travel_layout`` accepts."""
    if not root.is_dir():
        return False
    if (root / "src" / "travel_planner").is_dir():
        return True
    return (root / "README.md").is_file() and (
        (root / "pyproject.toml").is_file()
        or (root / "requirements.txt").is_file()
        or (root / "src").is_dir()
    )


def travel_listen_port(root: Path) -> int:
    """Port TravelPlan binds. ``.env`` wins over ``.env.example``. Default 5000."""
    for name in (".env", ".env.example"):
        path = root / name
        if not path.is_file() or path.is_symlink():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or not stripped.startswith("PORT="):
                continue
            raw = stripped.split("=", 1)[1].strip().strip('"').strip("'")
            try:
                port = int(raw)
            except ValueError:
                continue
            if 1 <= port <= 65535:
                return port
    return 5000


def probe_travel_port(port: int, *, timeout: float = 0.6) -> dict[str, Any]:
    """GET /api/health on 127.0.0.1. A closed port is not reachable."""
    import httpx

    url = f"http://127.0.0.1:{int(port)}/"
    out: dict[str, Any] = {"url": url, "reachable": False, "health_ok": False}
    try:
        with httpx.Client(timeout=timeout) as client:
            try:
                health = client.get(url + "api/health")
            except httpx.HTTPError:
                return out
            out["reachable"] = True
            if health.status_code != 200:
                return out
            try:
                body = health.json()
            except Exception:  # noqa: BLE001
                body = {}
            if isinstance(body, dict) and str(body.get("status") or "") == "ok":
                out["health_ok"] = True
    except httpx.HTTPError:
        return out
    return out


def travel_port_verdict(root: Path) -> dict[str, Any] | None:
    """Report a live TravelPlan process. None when the port is closed.

    ``GET /api/health`` with ``status`` ok is ``already_serving``. Any other
    open port is ``port_in_use``. This does not start a process.
    """
    probe = probe_travel_port(travel_listen_port(root))
    if not probe["reachable"]:
        return None
    url = str(probe["url"])
    if probe["health_ok"]:
        return {
            "ok": True,
            "already_serving": True,
            "written": False,
            "url": url,
            "run": url,
            "next_action": (
                f"TravelPlan is already serving at {url}. "
                "GET /api/health returned status ok. Leave the process running."
            ),
        }
    return {
        "ok": False,
        "already_serving": False,
        "written": False,
        "failure_class": "port_in_use",
        "url": url,
        "run": "",
        "next_action": (
            f"{url}api/health is open and is not a healthy TravelPlan. "
            "Do not start another process on this port."
        ),
    }


def _nonempty(path: Path) -> bool:
    try:
        return path.exists() and any(path.iterdir())
    except OSError:
        return False


def _foreign_travel_dir(path: Path) -> bool:
    return _nonempty(path) and not looks_like_travel_sample(path)


def _next_open_travel_dir(parent: Path) -> Path | None:
    """Next demo_travel_sample-N that is missing, empty, or already the sample."""
    for n in range(2, 100):
        candidate = parent / f"{DEFAULT_TRAVEL_DIR_NAME}-{n}"
        if not _foreign_travel_dir(candidate):
            return candidate
    return None


@dataclass
class TravelTarget:
    """Directory ``ensure_travel_sample`` will read or clone into."""

    root: Path
    serving_verdict: dict[str, Any] | None = None
    relocated_from: str = ""
    foreign_blocked: bool = False


def travel_destination(
    cfg: HelperConfig | None,
    *,
    sample_dir: str = "",
    project_name: str = "",
    parent_dir: str = "",
) -> TravelTarget:
    """The path ``ensure_travel_sample`` uses, including a live checkout or a move.

    ``sample_dir``, or ``parent_dir`` plus ``project_name``, is the destination.
    A blank parent is the directory next to this Helper checkout. A recorded
    checkout is used only when that port is already serving.
    """
    dest = _resolve_clone_dest(
        sample_dir=sample_dir,
        project_name=project_name,
        parent_dir=parent_dir,
    )
    named = project_name.strip()
    explicit = bool(sample_dir.strip()) or (
        bool(named) and sanitize_travel_dir_name(named) != DEFAULT_TRAVEL_DIR_NAME
    )
    if not explicit and cfg is not None:
        recorded = recorded_travel_dir(cfg)
        if recorded is not None and looks_like_travel_sample(recorded):
            verdict = travel_port_verdict(recorded)
            if verdict is not None:
                return TravelTarget(root=recorded, serving_verdict=verdict)
    if (
        not explicit
        and _foreign_travel_dir(dest)
        and dest.name == DEFAULT_TRAVEL_DIR_NAME
    ):
        sibling = _next_open_travel_dir(dest.parent)
        if sibling is None:
            return TravelTarget(root=dest, foreign_blocked=True)
        return TravelTarget(root=sibling, relocated_from=str(dest.resolve()))
    if sample_dir.strip() and _foreign_travel_dir(dest):
        return TravelTarget(root=dest, foreign_blocked=True)
    return TravelTarget(root=dest)


def travel_quick_start() -> str:
    """Virtualenv, the travel repo install, and ``python -m travel_planner``."""
    return f'{venv_setup_shell()} && pip install -e ".[dev]" && python -m travel_planner'


def _copy_config_example(root: Path) -> bool:
    """Copy ``config.example.json`` only when ``config.json`` is missing."""
    dest = root / "config.json"
    example = root / "config.example.json"
    if dest.exists() or dest.is_symlink():
        return False
    if not example.is_file() or example.is_symlink():
        return False
    dest.write_bytes(example.read_bytes())
    return True


def _travel_setup_next_action(root: Path, result: dict[str, Any]) -> str:
    """Start text that matches the merged ``.env``. Names only."""
    app_missing = result.get("missing_app_settings") or []
    process_missing = result.get("missing_process_settings") or []
    app_names = ", ".join(app_missing) if app_missing else "none"
    process_names = ", ".join(process_missing) if process_missing else "none"
    skipped = str(result.get("skipped_llm_alias") or "").strip()
    alias_note = ""
    if skipped:
        alias_note = (
            f" {skipped} is set in this process. It was not copied to LLM_API_KEY "
            "because LLM_BASE_URL and LLM_MODEL do not match that provider. "
            "Set LLM_API_KEY, LLM_BASE_URL, and LLM_MODEL together."
        )
    note = launch_note()
    prefix = f"{note} " if note else ""
    port = travel_listen_port(root)
    return (
        f"{prefix}The checkout is the travel sample at {root} ({TRAVEL_REPO}). "
        "Read its README and use its source. "
        f"Start with python -m travel_planner. The port is {port} unless PORT is set. "
        ".env keeps populated values and adds missing Zeus and LLM names "
        "(preserve_existing_then_fill_missing). "
        "Do not replace .env when that file already has values. "
        "config.json is copied from config.example.json only when config.json is missing. "
        "Do not write a password or api_key into config.json. "
        f"App settings still empty: {app_names}. "
        f"This process is still missing: {process_names}. "
        "The app .env and this process stay separate. "
        "load_process_login loads a mode-600 env file into this process."
        f"{alias_note} "
        "Clone success is not website green. "
        "Call website_green for install, GET /api/health, and search. "
        "Beer cards are not required. "
        "Search stays off until an LLM key is in the app .env. "
        "A describe 200 is not this check. "
        f"From that directory: {travel_quick_start()}."
    )


def _bind_travel_env(
    cfg: HelperConfig,
    root: Path,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Merge the mode-600 ``.env``. Secret values stay out of the result."""
    from zeus_dev_helper_mcp.app_env import annotate_app_env

    _copy_config_example(root)
    serving = bool(result.get("already_serving"))
    if not serving and not result.get("run"):
        result["run"] = f"cd {root} && {travel_quick_start()}"
    result = annotate_app_env(cfg, root, result, report=True, travel=True)
    if not serving:
        result["next_action"] = _travel_setup_next_action(root, result)
    return result


def _foreign_travel_result(dest: Path) -> dict[str, Any]:
    return {
        "ok": False,
        "failure_class": "foreign_sample_dir",
        "cloned": False,
        "written": False,
        "local_dir": str(dest),
        "project_name": dest.name,
        "env": {ENV_TRAVEL_DIR: None},
        "repo": TRAVEL_REPO,
        "private": False,
        "error": f"sample_dir is not a travel sample: {dest}",
        "next_action": (
            "Pass project_name for an empty directory. "
            "The foreign sample_dir was not written."
        ),
    }


def ensure_travel_sample(
    cfg: HelperConfig,
    *,
    sample_dir: str = "",
    project_name: str = "",
    parent_dir: str = "",
    clone_if_missing: bool = True,
) -> dict[str, Any]:
    """Clone public demo_travel_sample when the destination is missing.

    The destination is ``sample_dir``, or ``parent_dir`` plus ``project_name``.
    A blank parent is the directory next to this Helper checkout. A recorded
    checkout that is already serving stays where it is. Basic auth with no
    process login returns before git clone. Docker files and the client pin
    stay as the repo shipped them.
    """
    dir_name = sanitize_travel_dir_name(project_name)
    target = travel_destination(
        cfg,
        sample_dir=sample_dir,
        project_name=project_name,
        parent_dir=parent_dir,
    )
    if target.serving_verdict is not None:
        root = target.root
        env_path = set_demo_travel_sample_dir_env(root)
        save_travel_sample_dir(cfg, root)
        result = {
            "ok": bool(target.serving_verdict.get("ok")),
            "local_dir": str(root.resolve()),
            "cloned": False,
            "written": False,
            "project_name": root.name,
            "clone": None,
            "layout": validate_travel_layout(root),
            "docker_setup": None,
            "env": {ENV_TRAVEL_DIR: env_path},
            "repo": TRAVEL_REPO,
            "private": False,
            **target.serving_verdict,
        }
        if result.get("ok"):
            return _bind_travel_env(cfg, root, result)
        return result
    if target.foreign_blocked:
        return _foreign_travel_result(target.root)

    dest = target.root
    relocated_from = target.relocated_from
    if relocated_from:
        dir_name = dest.name
    if dest.is_dir() and not _nonempty(dest):
        try:
            dest.rmdir()
        except OSError:
            pass

    clone_info: dict[str, Any] | None = None
    if not dest.exists():
        if not clone_if_missing:
            return {
                "ok": False,
                "local_dir": None,
                "cloned": False,
                "written": False,
                "project_name": dir_name,
                "clone": None,
                "env": {ENV_TRAVEL_DIR: None},
                "next_action": (
                    "No local demo_travel_sample; enable clone_if_missing or pass sample_dir"
                ),
                "repo": TRAVEL_REPO,
                "private": False,
            }
        from zeus_dev_helper_mcp.app_env import basic_login_blocked

        blocked = basic_login_blocked(cfg)
        if blocked is not None:
            blocked["local_dir"] = str(dest)
            blocked["cloned"] = False
            blocked["repo"] = TRAVEL_REPO
            return blocked
        clone_info = clone_travel_sample(dest=dest)
        if not clone_info.get("ok"):
            return {
                "ok": False,
                "local_dir": str(dest),
                "cloned": False,
                "written": False,
                "failure_class": "clone_failed",
                "project_name": dir_name,
                "clone": clone_info,
                "env": {ENV_TRAVEL_DIR: None},
                "error": clone_info.get("error"),
                "next_action": clone_info.get("next_action")
                or "Clone manually, or scaffold_app",
                "repo": TRAVEL_REPO,
                "private": False,
            }
    elif not looks_like_travel_sample(dest):
        return _foreign_travel_result(dest)

    verdict = travel_port_verdict(dest) if looks_like_travel_sample(dest) else None
    env_path = set_demo_travel_sample_dir_env(dest)
    save_travel_sample_dir(cfg, dest)
    layout = validate_travel_layout(dest)
    if verdict is not None:
        result = {
            "ok": bool(verdict.get("ok")),
            "local_dir": str(dest.resolve()),
            "cloned": bool(clone_info and clone_info.get("cloned")),
            "written": False,
            "project_name": dest.name,
            "clone": clone_info,
            "layout": layout,
            "docker_setup": None,
            "env": {ENV_TRAVEL_DIR: env_path},
            "repo": TRAVEL_REPO,
            "private": False,
            **verdict,
        }
        if result.get("ok"):
            return _bind_travel_env(cfg, dest, result)
        return result
    if not layout.get("ok"):
        return {
            "ok": False,
            "local_dir": str(dest.resolve()),
            "cloned": bool(clone_info and clone_info.get("cloned")),
            "written": False,
            "project_name": dest.name,
            "clone": clone_info,
            "layout": layout,
            "docker_setup": None,
            "env": {ENV_TRAVEL_DIR: env_path},
            "repo": TRAVEL_REPO,
            "private": False,
            "next_action": (
                "Clone/path exists but layout looks incomplete — check README / sample_dir"
            ),
        }
    result = {
        "ok": True,
        "local_dir": str(dest.resolve()),
        "cloned": bool(clone_info and clone_info.get("cloned")),
        "written": False,
        "project_name": dest.name,
        "clone": clone_info,
        "layout": layout,
        "docker_setup": None,
        "env": {ENV_TRAVEL_DIR: env_path},
        "repo": TRAVEL_REPO,
        "private": False,
        "run": f"cd {dest.resolve()} && {travel_quick_start()}",
        "next_action": "",
    }
    result = _bind_travel_env(cfg, dest, result)
    if relocated_from and result.get("ok"):
        result["relocated_from"] = relocated_from
        prior = str(result.get("next_action") or "").strip()
        result["next_action"] = (
            f"Default demo_travel_sample was a foreign tree at {relocated_from}. "
            f"Cloned the travel app to {dest}. {prior}"
        ).strip()
    return result


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
        "copy config.example.json to config.json only when config.json is missing; "
        f"then `docker compose up --build` and open http://localhost:{host_port} "
        f"(tracer: http://localhost:{host_port}/?debug=true). "
        "The helper does not run Docker."
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


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def monorepo_docker_layout_usable(root: Path) -> bool:
    """True when parent looks like the koten-ai monorepo Docker expects."""
    parent = root.parent
    sibling_client = parent / "zeus_client_python"
    # Upstream compose: context=parent, dockerfile=demo_travel_sample/Dockerfile
    dockerfile_via_parent = parent / "demo_travel_sample" / "Dockerfile"
    local_dockerfile = root / "Dockerfile"
    return bool(
        sibling_client.is_dir()
        and (dockerfile_via_parent.is_file() or (root.name == "demo_travel_sample" and local_dockerfile.is_file()))
    )


def _packaging_has_monorepo_markers(root: Path) -> bool:
    texts: list[str] = []
    for name in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml", "pyproject.toml"):
        p = root / name
        if p.is_file():
            texts.append(_read_text(p))
    blob = "\n".join(texts)
    return any(marker in blob for marker in _MONOREPO_DOCKER_MARKERS)


def _is_standalone_docker_packaging(root: Path) -> bool:
    dockerfile = root / "Dockerfile"
    if not dockerfile.is_file():
        return False
    text = _read_text(dockerfile)
    if any(marker in text for marker in _MONOREPO_DOCKER_MARKERS):
        return False
    return "COPY pyproject.toml" in text and "WORKDIR /app" in text


def needs_standalone_docker_setup(root: Path | None) -> bool:
    """True when UI sample Docker packaging won't build outside the monorepo."""
    if root is None or not root.is_dir():
        return False
    if monorepo_docker_layout_usable(root):
        return False
    if _is_standalone_docker_packaging(root) and not _packaging_has_monorepo_markers(root):
        return False
    # Only rewrite upstream monorepo packaging — do not invent Docker for plain trees.
    return _packaging_has_monorepo_markers(root)


def _pin_standalone_client(text: str) -> str:
    """Point a standalone clone at PyPI 2.4.x (envelope recovery). Leave other deps."""
    new = _PYPROJECT_FILE_DEP_RE.sub(f'"{_STANDALONE_CLIENT_DEP}"', text)
    new = new.replace(
        "kotenai-zeus-client @ file:../zeus_client_python",
        _STANDALONE_CLIENT_DEP,
    )
    new = new.replace("kotenai-zeus-client>=2.3.0", _STANDALONE_CLIENT_DEP)
    return new


def _rewrite_pyproject_client_dep(root: Path) -> bool:
    path = root / "pyproject.toml"
    if not path.is_file():
        return False
    text = _read_text(path)
    new_text = _pin_standalone_client(text)
    if new_text == text:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def _rewrite_requirements_client_dep(root: Path) -> bool:
    path = root / "requirements.txt"
    if not path.is_file():
        return False
    text = _read_text(path)
    new_text = _pin_standalone_client(text)
    if new_text == text:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def _rewrite_dockerignore(root: Path) -> bool:
    path = root / ".dockerignore"
    existing = _read_text(path) if path.is_file() else ""
    # Bare `data` excludes stamped chat_requests from the image build context.
    lines = [ln.strip() for ln in existing.splitlines() if ln.strip()]
    if "data" in lines or not path.is_file():
        path.write_text(_STANDALONE_DOCKERIGNORE, encoding="utf-8")
        return True
    return False


def prepare_standalone_docker(root: Path, *, force: bool = False) -> dict[str, Any]:
    """Rewrite travel-sample Docker packaging for a standalone clone.

    Upstream demo_travel_sample assumes compose ``context: ..`` and a sibling
    ``zeus_client_python``. When the sample is cloned outside that monorepo
    (typical Helper ``use_sample`` / ``project_name`` path), rewrite Dockerfile,
    compose, pyproject client dep, and ``.dockerignore`` so
    ``docker compose up --build`` works. Does not run Docker.
    """
    root = root.expanduser().resolve()
    if not root.is_dir():
        return {
            "ok": False,
            "prepared": False,
            "local_dir": str(root),
            "reason": "missing_dir",
            "next_action": "Clone or set sample_dir to a travel UI sample root",
            "files_written": [],
        }

    if monorepo_docker_layout_usable(root) and not force:
        return {
            "ok": True,
            "prepared": False,
            "skipped": "monorepo_layout",
            "local_dir": str(root),
            "reason": "monorepo_docker_usable",
            "next_action": (
                f"Monorepo Docker layout detected — from {root} run "
                "`docker compose up --build` (parent must contain zeus_client_python)."
            ),
            "files_written": [],
        }

    if _is_standalone_docker_packaging(root) and not _packaging_has_monorepo_markers(root) and not force:
        pinned: list[str] = []
        if _rewrite_pyproject_client_dep(root):
            pinned.append("pyproject.toml")
        if _rewrite_requirements_client_dep(root):
            pinned.append("requirements.txt")
        if pinned:
            return {
                "ok": True,
                "prepared": True,
                "local_dir": str(root),
                "reason": "upgraded_client_pin",
                "client_dep": _STANDALONE_CLIENT_DEP,
                "files_written": pinned,
                "next_action": (
                    f"Pinned {_STANDALONE_CLIENT_DEP} in {root} so the image has "
                    "pipeline envelope recovery. The BFF still calls rt.agent.run_turn."
                ),
            }
        return {
            "ok": True,
            "prepared": False,
            "skipped": "already_standalone",
            "local_dir": str(root),
            "reason": "already_standalone",
            "client_dep": _STANDALONE_CLIENT_DEP,
            "next_action": docker_install_next_action(root),
            "files_written": [],
        }

    if not force and not needs_standalone_docker_setup(root):
        return {
            "ok": True,
            "prepared": False,
            "skipped": "not_needed",
            "local_dir": str(root),
            "reason": "not_needed",
            "next_action": docker_install_next_action(root) if detect_docker_install(root).get("ok") else "",
            "files_written": [],
        }

    written: list[str] = []
    container_name = sanitize_travel_dir_name(root.name)
    if container_name == DEFAULT_TRAVEL_DIR_NAME:
        container_name = "travel-planner"

    # Prefer docker-compose.yml name used by the upstream sample.
    compose_path = root / "docker-compose.yml"
    existing_compose = _compose_file(root)
    if existing_compose is not None and existing_compose.name != "docker-compose.yml":
        compose_path = existing_compose

    (root / "Dockerfile").write_text(_STANDALONE_DOCKERFILE, encoding="utf-8")
    written.append("Dockerfile")
    compose_path.write_text(
        _STANDALONE_COMPOSE.format(container_name=container_name),
        encoding="utf-8",
    )
    written.append(compose_path.name)

    if _rewrite_pyproject_client_dep(root):
        written.append("pyproject.toml")
    if _rewrite_requirements_client_dep(root):
        written.append("requirements.txt")
    if _rewrite_dockerignore(root):
        written.append(".dockerignore")

    # Ensure LICENSE exists for Dockerfile COPY (upstream has it; keep soft).
    if not (root / "LICENSE").is_file() and (root / "LICENSE.md").is_file():
        pass  # Dockerfile expects LICENSE; leave as-is — build will fail loudly

    host_port = 5050
    next_action = (
        f"Standalone Docker packaging prepared in {root}. "
        "Copy config.example.json to config.json only when config.json is missing. "
        "Compose sets ZEUS_URL=host.docker.internal:8080. "
        f"Then `docker compose up --build` and open http://localhost:{host_port}. "
        "The helper does not run Docker."
    )
    return {
        "ok": True,
        "prepared": True,
        "local_dir": str(root),
        "reason": "rewrote_monorepo_docker",
        "container_name": container_name,
        "client_dep": _STANDALONE_CLIENT_DEP,
        "files_written": written,
        "next_action": next_action,
        "host_port": host_port,
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
    serve_with: str = "",
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
    docker_setup = ensured.get("docker_setup")

    from zeus_dev_helper_mcp.serve_choice import has_serve_choice

    packaged = root is not None and has_serve_choice(root)
    if ensured.get("already_serving"):
        phase5 = (
            "TravelPlan is already serving. GET /api/health returned status ok. "
            "Leave the process running."
        )
    elif packaged:
        phase5 = (
            "Follow host_question on this result and wait. "
            "Python is serve_with=python. Docker is serve_with=docker. "
            f"The Python command is {travel_quick_start()}. "
            "The Docker command is docker compose up --build. Then call website_green."
        )
    elif docker and docker.get("ok"):
        phase5 = (
            "Call website_green. Docker install docs say docker compose up --build. "
            "The helper does not run Docker."
        )
    else:
        phase5 = "Call website_green. GET /api/health status ok is the page check."

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
        {
            "phase": "4",
            "action": (
                "bind_contract with no path copies bootstrap chat_request.contract. "
                "Hub Workbench stamp only when that live document has no real hash"
            ),
        },
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
6. Copy config.example.json to config.json only when config.json is missing. When both a Dockerfile and a compose file exist, choose Python or Docker before starting. Python is `python -m travel_planner` on port 5000 unless PORT is set. The helper does not run Docker.
7. Published docs: https://docs.koten.ai/zeus-client
"""

    if layout and layout.get("ok") and root is not None:
        try:
            set_item_status(cfg, "0.2", "done", evidence=f"travel_layout={root}")
            set_item_status(cfg, "3.1", "done", evidence=f"travel_dir={root}")
        except Exception:  # noqa: BLE001, S110
            pass

    if not ensured.get("ok"):
        next_action = ensured.get("next_action") or (
            "Clone failed — fix git/network or scaffold_app for a minimal path without the demo UI."
        )
    elif packaged:
        next_action = str(ensured.get("next_action") or "")
    elif root and docker and docker.get("ok"):
        docker_text = str(docker.get("next_action") or "").strip()
        prior = str(ensured.get("next_action") or "").strip()
        next_action = f"{prior} {docker_text}".strip()
    elif root:
        next_action = ensured.get("next_action") or (
            "Layout found. Call website_green. GET /api/health status ok is the page check."
        )
    else:
        next_action = ensured.get("next_action") or "use_sample to clone demo_travel_sample"

    payload = {
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
        "docker_setup": docker_setup,
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
    for key in (
        "failure_class",
        "already_serving",
        "url",
        "app_env",
        "env_template",
        "env_target",
        "configuration_policy",
        "missing_app_settings",
        "missing_process_settings",
        "skipped_llm_alias",
        "missing_env",
        "relocated_from",
        "written",
        "run",
        "error",
    ):
        if ensured.get(key) is not None:
            payload[key] = ensured[key]
    from zeus_dev_helper_mcp.serve_choice import annotate_serve_choice

    return annotate_serve_choice(payload, root, cfg=cfg, serve_with=serve_with)
