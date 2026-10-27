"""Ask the agent to choose Python or Docker before a sample server starts.

The helper does not run Docker. A checkout with both a Dockerfile and a
compose file gets ``serve_options``. ``run`` stays empty until the user
chooses. ``website_green`` reads that choice and does not start Python
while the choice is open or when the choice is Docker.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from zeus_dev_helper_mcp.config import HelperConfig

_COMPOSE_NAMES = (
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
)
_PORT_RE = re.compile(r"(\d{2,5})\s*:\s*\d{2,5}")
_STATE_NAME = "serve_choice.json"

ASK = (
    "Ask the user whether to serve this app with Python or Docker. "
    "Wait for the answer. Do not start either command until they choose. "
    "Pass serve_with=python or serve_with=docker to use_sample or website_green. "
    "The commands are in serve_options. The helper does not run Docker."
)


def compose_file(root: Path) -> Path | None:
    for name in _COMPOSE_NAMES:
        path = root / name
        if path.is_file():
            return path
    return None


def has_serve_choice(root: Path) -> bool:
    """True when this checkout can start with Python or Docker."""
    return (root / "Dockerfile").is_file() and compose_file(root) is not None


def parse_serve_with(raw: str) -> tuple[str, bool]:
    """Return ``(python|docker|"", valid)``. Empty is valid and means unset."""
    value = (raw or "").strip().lower()
    if value in {"", "python", "docker"}:
        return value, True
    return "", False


def published_host_port(root: Path) -> int | None:
    path = compose_file(root)
    if path is None:
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = _PORT_RE.search(text)
    if match is None:
        return None
    port = int(match.group(1))
    if 1 <= port <= 65535:
        return port
    return None


def docker_notes(root: Path) -> str:
    path = compose_file(root)
    text = ""
    if path is not None:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
    notes = ["The helper does not run Docker."]
    if "HOST" in text and "0.0.0.0" in text:
        notes.append("Compose sets HOST=0.0.0.0.")
    if "host.docker.internal:8080" in text:
        notes.append("Compose points ZEUS_URL at http://host.docker.internal:8080.")
    if "./data:" in text or "./data/" in text:
        notes.append("./data is bind-mounted.")
    if "env_file" in text or ".env:" in text:
        notes.append(".env stays on the host and is not copied into the image.")
    return " ".join(notes)


def python_serve_command(root: Path) -> tuple[str, str]:
    """Python start command and URL for this checkout. Names only."""
    if (root / "src" / "local_guide" / "__main__.py").is_file():
        run = (
            f"cd {root} && pip install -e . && python -m local_guide"
            "  # API http://127.0.0.1:5000; "
            "cd frontend && npm install && npm run dev"
        )
        return run, "http://localhost:5173/"

    blob = ""
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            blob = pyproject.read_text(encoding="utf-8", errors="replace")
        except OSError:
            blob = ""
    readme = root / "README.md"
    if readme.is_file():
        try:
            blob += "\n" + readme.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    travel_src = root / "src" / "travel_planner"
    if "travel_planner" in blob or travel_src.is_dir():
        copy = ""
        if (root / "config.example.json").is_file() and not (
            root / "config.json"
        ).is_file():
            copy = "cp config.example.json config.json && "
        run = f'cd {root} && {copy}pip install -e ".[dev]" && python -m travel_planner'
        return run, "http://127.0.0.1:5000/"

    if (root / "main.py").is_file() and (root / "requirements.txt").is_file():
        from zeus_dev_helper_mcp.beer import beer_listen_port, beer_quick_start
        from zeus_dev_helper_mcp.python_runtime import venv_setup_shell

        port = beer_listen_port(root)
        meta = root / "sample_meta.json"
        if meta.is_file():
            try:
                doc = json.loads(meta.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                doc = {}
            if isinstance(doc, dict) and doc.get("sample") == "catalog":
                port = 8091
                setup = venv_setup_shell()
                run = (
                    f"cd {root} && {setup} && "
                    "pip install -r requirements.txt && "
                    "uvicorn main:app --port 8091"
                )
                return run, "http://127.0.0.1:8091/"
        return (
            f"cd {root} && {beer_quick_start()}",
            f"http://127.0.0.1:{port}/",
        )

    from zeus_dev_helper_mcp.python_runtime import venv_setup_shell

    setup = venv_setup_shell()
    if (root / "requirements.txt").is_file():
        return (
            f"cd {root} && {setup} && pip install -r requirements.txt",
            "http://127.0.0.1:8000/",
        )
    if pyproject.is_file():
        return f"cd {root} && {setup} && pip install -e .", "http://127.0.0.1:8000/"
    return f"cd {root} && {setup}", "http://127.0.0.1:8000/"


def serve_options(root: Path) -> list[dict[str, str]]:
    python_run, python_url = python_serve_command(root)
    host_port = published_host_port(root)
    docker_url = f"http://127.0.0.1:{host_port}/" if host_port else python_url
    return [
        {
            "id": "python",
            "label": "Python",
            "run": python_run,
            "url": python_url,
        },
        {
            "id": "docker",
            "label": "Docker",
            "run": f"cd {root} && docker compose up --build",
            "url": docker_url,
            "notes": docker_notes(root),
        },
    ]


def remember_serve_with(cfg: HelperConfig, root: Path, choice: str) -> None:
    """Remember python or docker for this checkout. No secrets."""
    if choice not in {"python", "docker"}:
        return
    path = cfg.state_dir / _STATE_NAME
    payload: dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = {}
        if isinstance(loaded, dict):
            payload = loaded
    choices = payload.get("choices")
    if not isinstance(choices, dict):
        choices = {}
    choices[str(root.resolve())] = choice
    payload["choices"] = choices
    try:
        cfg.state_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return


def stored_serve_with(cfg: HelperConfig, root: Path) -> str:
    path = cfg.state_dir / _STATE_NAME
    if not path.is_file():
        return ""
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(loaded, dict):
        return ""
    choices = loaded.get("choices")
    if not isinstance(choices, dict):
        return ""
    value = choices.get(str(root.resolve()))
    if value in {"python", "docker"}:
        return str(value)
    return ""


def _without_start_commands(text: str) -> str:
    """Keep coaching sentences. Drop any that still name a start command."""
    parts = re.split(r"(?<=[.])\s+", text)
    kept = []
    for part in parts:
        lowered = part.lower()
        if "python main.py" in part:
            continue
        if "docker compose" in lowered or "docker-compose" in lowered:
            continue
        cleaned = part.strip()
        if cleaned:
            kept.append(cleaned)
    return " ".join(kept)


def _coaching_tail(action: str, python_run: str) -> str:
    from zeus_dev_helper_mcp.beer import beer_quick_start

    quick = beer_quick_start()
    if quick and quick in action:
        text = action.replace(quick, " ").replace(python_run, " ")
        text = text.replace("From that directory:", " ")
        return _without_start_commands(" ".join(text.split()))
    lowered = action.lower()
    if "docker compose" in lowered or "docker-compose" in lowered:
        kept: list[str] = []
        if "readiness_check" in action or "smokes" in action:
            kept.append(
                "Continue readiness_check and smokes with the sample bucket and scope."
            )
        if "Do not clone demo_travel_sample" in action:
            kept.append("Do not clone demo_travel_sample.")
        if "website_green" in action:
            kept.append("Call website_green after the app is serving.")
        if "LLM_API_KEY" in action:
            kept.append("Leave config.json llm.api_key_env as the name LLM_API_KEY.")
        return " ".join(kept)
    return _without_start_commands(action)


def annotate_serve_choice(
    result: dict[str, Any],
    root: Path | None,
    *,
    cfg: HelperConfig | None = None,
    serve_with: str = "",
) -> dict[str, Any]:
    """Attach the Python-or-Docker ask when both packaging files exist.

    An already-serving checkout and a failed result stay as they are.
    """
    if root is None or not result.get("ok"):
        return result
    if result.get("already_serving") or result.get("page_only"):
        return result
    parsed, valid = parse_serve_with(serve_with)
    if not has_serve_choice(root):
        if serve_with.strip() and not valid:
            prior = str(result.get("next_action") or "")
            result["next_action"] = (
                f"serve_with must be python or docker. {prior}".strip()
            )
        return result

    options = serve_options(root)
    result["serve_options"] = options
    python_run = options[0]["run"]
    tail = _coaching_tail(str(result.get("next_action") or ""), python_run)
    docker_hint = result.get("docker")
    if isinstance(docker_hint, dict):
        docker_hint = dict(docker_hint)
        docker_hint["next_action"] = (
            "Choose Python or Docker. Commands are in serve_options."
        )
        result["docker"] = docker_hint
    if not valid:
        parsed = ""
        tail = f"serve_with must be python or docker. {tail}".strip()
    if parsed in {"python", "docker"}:
        picked = options[0] if parsed == "python" else options[1]
        if cfg is not None:
            remember_serve_with(cfg, root, parsed)
        result["serve_choice_required"] = False
        result["serve_with"] = parsed
        result["run"] = picked["run"]
        result["next_action"] = (
            f"The user chose {picked['label']}. "
            f"Start only this command: {picked['run']} "
            f"Open {picked['url']}. "
            "Do not start the other option. "
            f"{tail}"
        ).strip()
        return result

    result["serve_choice_required"] = True
    result["serve_with"] = ""
    result["run"] = ""
    result["next_action"] = f"{ASK} {tail}".strip()
    return result
