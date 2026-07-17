"""demo_travel_sample golden path integration (ZDH-10)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from zeus_dev_helper_mcp.checklist import set_item_status
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.docs_links import docs_url

TRAVEL_REPO = "https://github.com/koten-ai/demo_travel_sample"
TRAVEL_MARKERS = (
    "README.md",
    "pyproject.toml",
    "requirements.txt",
    "src",
    "Makefile",
)


def _find_travel_dir(explicit: str = "") -> Path | None:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        return p if p.is_dir() else None
    env = os.environ.get("DEMO_TRAVEL_SAMPLE_DIR", "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        if p.is_dir():
            return p
    # sibling of helper repo
    here = Path(__file__).resolve()
    # .../zeus_dev_helper_mcp/src/zeus_dev_helper_mcp/travel.py
    candidates = [
        here.parents[2].parent / "demo_travel_sample",
        Path.home() / "Documents/git_folders/fujio-turner/demo_travel_sample",
        Path.cwd() / "demo_travel_sample",
        Path.cwd().parent / "demo_travel_sample",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return None


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


def travel_golden_path(cfg: HelperConfig, *, sample_dir: str = "") -> dict[str, Any]:
    """Describe + optionally validate demo_travel_sample as Helper golden path."""
    root = _find_travel_dir(sample_dir)
    layout = validate_travel_layout(root) if root else None

    phases = [
        {"phase": "0", "action": "start_project(goal=single-agent, sample=travel)"},
        {"phase": "1", "action": "set_prereq with travel-sample bucket/scope from sample README"},
        {"phase": "2", "action": "readiness_check against Zeus :8080"},
        {"phase": "3", "action": "clone demo_travel_sample OR scaffold_app fallback"},
        {"phase": "4", "action": "bootstrap_scope + stamp catalog in Hub Workbench"},
        {"phase": "5", "action": "smoke_test_zeus then sample make smoke / smoke_test_agent"},
        {"phase": "6+", "action": "gap_report; customize domain"},
    ]

    helper_readme_section = """## Use with Developer Helper MCP

1. Install [zeus_dev_helper_mcp](https://github.com/koten-ai/zeus_dev_helper_mcp).
2. `export DEMO_TRAVEL_SAMPLE_DIR=/path/to/this/repo`
3. `export ZEUS_URL=http://localhost:8080` and scope env from this sample's docs.
4. MCP tools: `start_project(sample=travel)` → `use_sample` → `readiness_check` → smokes.
5. Published docs: https://docs.koten.ai/
"""

    if layout and layout.get("ok"):
        try:
            set_item_status(cfg, "0.2", "done", evidence=f"travel_layout={root}")
            set_item_status(cfg, "3.1", "done", evidence=f"travel_dir={root}")
        except Exception:  # noqa: BLE001
            pass

    return {
        "ok": True,
        "sample": "travel",
        "repo": TRAVEL_REPO,
        "private": True,
        "clone": f"git clone {TRAVEL_REPO}.git",
        "local_dir": str(root) if root else None,
        "layout": layout,
        "env": {
            "DEMO_TRAVEL_SAMPLE_DIR": "absolute path to clone",
            "ZEUS_URL": "http://localhost:8080",
            "ZEUS_BUCKET": "(from sample README — often travel-sample)",
            "ZEUS_SCOPE": "(from sample README)",
        },
        "helper_phases": phases,
        "sample_readme_snippet": helper_readme_section,
        "next_action": (
            "Clone demo_travel_sample if you have access; set DEMO_TRAVEL_SAMPLE_DIR; "
            "or scaffold_app for a minimal path without the full demo UI."
            if not root
            else "Layout found — continue readiness_check and smokes with travel scope env."
        ),
        "docs": {
            "using_client": docs_url("zeus-client/using-zeus-client.md"),
            "helper": docs_url("zeus-client/dev-helper-mcp.md"),
            "demo_builder": "https://github.com/koten-ai/zeus_client_python/tree/main/docs/demo-builder",
        },
        "jira": "https://kotenai.atlassian.net/browse/ZDH-10",
    }
