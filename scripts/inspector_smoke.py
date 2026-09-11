#!/usr/bin/env python3
"""MCP Inspector CLI smoke (ZDH-39). No live Zeus. Requires npx + a Helper install."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "run-helper-mcp.sh"
INSPECTOR_PKG = "@modelcontextprotocol/inspector@2.6.0"
CORE_CAP = 15
FORBIDDEN = frozenset(
    {
        "explain_hash_boundary",
        "detective_links",
        "semantic_cache_status",
        "get_checklist",
        "validate_env",
    }
)
REQUIRED_PROMPTS = frozenset({"first_green", "smoke_question", "support_pack"})


def _inspect(method: str) -> dict:
    py = sys.executable
    path = str(Path(py).parent) + os.pathsep + os.environ.get("PATH", "")
    cmd = [
        "npx",
        "--yes",
        INSPECTOR_PKG,
        "--cli",
        str(WRAPPER),
        "--method",
        method,
        "--format",
        "json",
        "--connect-timeout",
        "30000",
        "-e",
        f"PYTHON={py}",
        "-e",
        f"PATH={path}",
        "-e",
        "ZEUS_DEV_HELPER_TOOLSETS=core",
    ]
    env = os.environ.copy()
    env["PYTHON"] = py
    env["PATH"] = path
    env.setdefault("ZEUS_DEV_HELPER_TOOLSETS", "core")
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr or proc.stdout or f"inspector failed rc={proc.returncode}\n")
        raise SystemExit(proc.returncode or 1)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        sys.stderr.write(proc.stdout[:2000] + "\n")
        raise SystemExit(f"inspector stdout is not JSON: {e}") from e


def main() -> None:
    if not WRAPPER.is_file():
        raise SystemExit(f"missing wrapper {WRAPPER}")
    tools_raw = _inspect("tools/list")
    tools = (tools_raw.get("result") or tools_raw).get("tools") or []
    names = {t.get("name") for t in tools if isinstance(t, dict)}
    if len(names) > CORE_CAP:
        raise SystemExit(f"core tools/list count {len(names)} exceeds cap {CORE_CAP}")
    leaked = names & FORBIDDEN
    if leaked:
        raise SystemExit(f"core tools/list includes hidden tools: {sorted(leaked)}")
    for t in tools:
        anns = t.get("annotations") or {}
        if anns.get("readOnlyHint") is None:
            raise SystemExit(f"{t.get('name')} missing readOnlyHint")

    resources_raw = _inspect("resources/list")
    resources = (resources_raw.get("result") or resources_raw).get("resources") or []
    uris = " ".join(str(r.get("uri") or "") for r in resources if isinstance(r, dict))
    if "checklist" not in uris:
        # templates may live in resourceTemplates
        templates = (resources_raw.get("result") or resources_raw).get("resourceTemplates") or []
        uris += " " + " ".join(
            str(t.get("uriTemplate") or t.get("uri") or "") for t in templates if isinstance(t, dict)
        )
    if "checklist" not in uris:
        raise SystemExit(f"resources/list missing checklist: {resources_raw}")

    prompts_raw = _inspect("prompts/list")
    prompts = (prompts_raw.get("result") or prompts_raw).get("prompts") or []
    pnames = {p.get("name") for p in prompts if isinstance(p, dict)}
    missing = REQUIRED_PROMPTS - pnames
    if missing:
        raise SystemExit(f"prompts/list missing {sorted(missing)}")

    print(
        json.dumps(
            {
                "ok": True,
                "tools": sorted(names),
                "tool_count": len(names),
                "prompts": sorted(pnames),
            }
        )
    )


if __name__ == "__main__":
    main()
