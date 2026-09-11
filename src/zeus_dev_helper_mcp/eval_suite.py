"""First-green eval suite (ZDH-40). Prompt corpus + trace checks. No payloads."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PROMPT_SAMPLES = ROOT / "guides" / "LIST_OF_PROMPT_SAMPLES.md"

# First-green coach order: doctor or next_step must precede disk generation.
COACH_BEFORE_SCAFFOLD = frozenset({"doctor", "next_step"})

# Twenty tools whose first numbered sample is the eval corpus.
EVAL_TOOLS: tuple[str, ...] = (
    "doctor",
    "start_project",
    "next_step",
    "set_prereq",
    "readiness_check",
    "scaffold_app",
    "use_sample",
    "bind_contract",
    "recommend_surface",
    "smoke_test_zeus",
    "smoke_test_agent",
    "diagnose_error",
    "list_catalog_modes",
    "fetch_chat_request",
    "explain",
    "lint_chat_request",
    "lint_runtime_config",
    "recommend_motion",
    "support_pack_from_turn",
    "handoff_to_multi",
)

_HEADING = re.compile(r"^### `([a-z0-9_]+)`\s*$", re.MULTILINE)
_ITEM = re.compile(r"^\d+\.\s+(.+)$", re.MULTILINE)
_HUB_AS_TARGET = re.compile(
    r"(?:ZEUS_URL\s*=\s*|use(?:\s+public)?\s+API\s+|point\s+\w+\s+at\s+)[^\n]*:9091",
    re.IGNORECASE,
)
_INVENT_HASH = re.compile(
    r"\b(?:invent|make up|compute_local|compute a (?:production )?hash)\b",
    re.IGNORECASE,
)


def load_prompt_cases(path: Path | None = None) -> list[dict[str, str]]:
    """One eval case per EVAL_TOOLS entry: first numbered prompt under that heading."""
    text = (path or PROMPT_SAMPLES).read_text(encoding="utf-8")
    headings = list(_HEADING.finditer(text))
    by_tool: dict[str, str] = {}
    for i, m in enumerate(headings):
        tool = m.group(1)
        start = m.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        block = text[start:end]
        item = _ITEM.search(block)
        if item:
            by_tool[tool] = item.group(1).strip()
    cases: list[dict[str, str]] = []
    for tool in EVAL_TOOLS:
        prompt = by_tool.get(tool)
        if not prompt:
            continue
        cases.append({"id": f"{tool}.1", "expected_tool": tool, "prompt": prompt})
    return cases


def check_prompt_constraints(prompt: str, *, expected_tool: str = "") -> list[str]:
    """Static checks on user-facing samples. Diagnose may mention :9091 as the error."""
    issues: list[str] = []
    if expected_tool != "diagnose_error" and _HUB_AS_TARGET.search(prompt):
        issues.append("prompt treats Hub :9091 as the app target")
    skip_hash = expected_tool in {
        "bind_contract",
        "lint_chat_request",
        "explain_hash_boundary",
        "diagnose_error",
    }
    if (
        not skip_hash
        and _INVENT_HASH.search(prompt)
        and "never" not in prompt.lower()
        and "do not" not in prompt.lower()
    ):
        issues.append("prompt may instruct inventing contract_hash")
    if (
        expected_tool not in {"lint_chat_request", "bind_contract", "explain_hash_boundary"}
        and "compute_local" in prompt.lower()
        and "not" not in prompt.lower()
        and "never" not in prompt.lower()
    ):
        issues.append("prompt may instruct compute_local")
    return issues


def check_trace(tool_names: list[str]) -> dict[str, Any]:
    """Assert coach sequence on a recorded first-green session (tool ids only)."""
    names = [n for n in tool_names if n]
    issues: list[str] = []
    if "scaffold_app" in names:
        idx = names.index("scaffold_app")
        before = set(names[:idx])
        if not (before & COACH_BEFORE_SCAFFOLD):
            issues.append("scaffold_app without prior doctor or next_step")
    return {
        "ok": not issues,
        "issues": issues,
        "tool_count": len(names),
        "unique": sorted(set(names)),
    }


def evaluate_corpus(path: Path | None = None) -> dict[str, Any]:
    cases = load_prompt_cases(path)
    failed: list[dict[str, Any]] = []
    for case in cases:
        issues = check_prompt_constraints(case["prompt"], expected_tool=case["expected_tool"])
        if issues:
            failed.append({**case, "issues": issues})
    return {
        "ok": len(cases) >= 20 and not failed,
        "case_count": len(cases),
        "failed": failed,
        "ids": [c["id"] for c in cases],
    }
