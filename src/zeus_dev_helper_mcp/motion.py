"""recommend_motion — Zeus interaction motions (ZDH-26). Guidance only."""

from __future__ import annotations

from typing import Any

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.docs_links import docs_url
from zeus_dev_helper_mcp.surface import recommend_surface

# Source: Zeus docs/public/motions/ZEUS_MOTIONS_GUIDE.md (13 motions).
MOTIONS_DOC = "https://github.com/koten-ai/Zeus/blob/main/docs/public/motions"
MOTIONS: dict[str, dict[str, Any]] = {
    "funnel": {
        "user_shape": "Help me complete the action.",
        "success": "Fewest rounds to the order/action",
        "typical_verbs": ["find", "search", "get", "named_query"],
        "modes": ["tenant", "open"],
        "keywords": (
            "book", "buy", "order", "dispatch", "complete", "checkout", "reserve",
            "schedule", "claim", "funnel", "purchase",
        ),
    },
    "explore": {
        "user_shape": "Help me investigate.",
        "success": "Useful, defensible insight",
        "typical_verbs": ["describe", "search", "find", "traverse"],
        "modes": ["open", "analytics", "research", "code", "private"],
        "keywords": (
            "investigate", "explore", "what's going on", "what is going on",
            "pattern", "related", "discover", "look around", "unhappy",
        ),
    },
    "verify": {
        "user_shape": "Is this true, allowed, or supported?",
        "success": "Evidence-backed judgment",
        "typical_verbs": ["get", "find", "explain", "return"],
        "modes": ["regulated", "tenant", "fraud", "research"],
        "keywords": (
            "is this true", "allowed", "eligible", "verify", "claim", "policy",
            "supported", "violate", "permit",
        ),
    },
    "compare": {
        "user_shape": "Which option is better, closer, or safer?",
        "success": "Ranked explainable alternatives",
        "typical_verbs": ["find", "search", "analyze"],
        "modes": ["open", "analytics", "research"],
        "keywords": ("which", "better", "compare", "vs", "versus", "closer", "safer", "best"),
    },
    "monitor": {
        "user_shape": "Tell me when this changes.",
        "success": "Timely actionable signal",
        "typical_verbs": ["describe", "search", "find"],
        "modes": ["regulated", "fraud"],
        "keywords": ("when it changes", "monitor", "alert", "watch", "notify"),
    },
    "explain": {
        "user_shape": "Why did this result happen?",
        "success": "Reviewable evidence path",
        "typical_verbs": ["explain", "find", "get"],
        "modes": ["open", "analytics", "regulated", "code"],
        "keywords": ("why did", "why is", "explain why", "how did zeus", "evidence path"),
    },
    "compose": {
        "user_shape": "Build a valid plan from constraints.",
        "success": "Constraint-satisfying candidate",
        "typical_verbs": ["find", "search", "return"],
        "modes": ["tenant", "analytics"],
        "keywords": ("plan", "compose", "constraints", "itinerary", "build me"),
    },
    "simulate": {
        "user_shape": "What happens if X changes?",
        "success": "Blast-radius / impact view",
        "typical_verbs": ["analyze", "traverse", "find"],
        "modes": ["analytics", "fraud", "regulated", "code"],
        "keywords": ("what if", "simulate", "impact", "blast", "assumption changes"),
    },
    "triage": {
        "user_shape": "What should we handle first?",
        "success": "Prioritized work queue",
        "typical_verbs": ["find", "analyze", "search"],
        "modes": ["analytics", "tenant", "fraud", "regulated"],
        "keywords": ("first", "priority", "triage", "which ones matter", "queue"),
    },
    "route": {
        "user_shape": "Where should this go?",
        "success": "Correct governed path / handoff",
        "typical_verbs": ["find", "named_query", "return"],
        "modes": ["tenant", "auto", "code"],
        "keywords": ("where should", "route", "handoff", "assign", "which queue"),
    },
    "refine": {
        "user_shape": "This ask failed; what is the safe next-best option?",
        "success": "Recovery from dead ends",
        "typical_verbs": ["search", "find", "describe"],
        "modes": ["open", "auto"],
        "keywords": ("failed", "try again", "refine", "next best", "dead end", "no results"),
    },
    "remember": {
        "user_shape": "Reuse what we learned safely.",
        "success": "Less repeated context, more continuity",
        "typical_verbs": ["find", "get"],
        "modes": ["tenant", "private", "research"],
        "keywords": ("remember", "reuse", "last time", "continuity", "we learned"),
        "note": "Semantic cache / agent_memory stays off unless opted in (Zeus >= 0.7.6).",
    },
    "custom": {
        "user_shape": "Just give me the API and let me build my own dashboard.",
        "success": "Self-served charts over endpoint / named-query metrics",
        "typical_verbs": ["describe", "named_query", "get"],
        "modes": ["custom", "analytics"],
        "keywords": ("dashboard", "custom api", "own dashboard", "metrics api"),
    },
}


def motion_doc(name: str) -> str:
    return f"{MOTIONS_DOC}/{name.upper()}.md"


def recommend_motion(cfg: HelperConfig, *, user_job: str) -> dict[str, Any]:
    """Pick a motion for a user job. Does not generate a chat_request."""
    job = (user_job or "").strip().lower()
    if not job:
        return {
            "ok": False,
            "known_motions": sorted(MOTIONS.keys()),
            "next_action": "Pass user_job (what the user/agent is trying to do)",
            "docs": f"{MOTIONS_DOC}/ZEUS_MOTIONS_GUIDE.md",
        }
    scores = {
        name: sum(1 for kw in (row.get("keywords") or ()) if kw in job)
        for name, row in MOTIONS.items()
    }
    best = max(scores, key=lambda n: scores[n])
    if scores[best] == 0:
        best = "explore"
    row = MOTIONS[best]
    surface = recommend_surface(
        cfg,
        intent="nl_question" if best not in ("custom",) else "single_verb",
    )
    out: dict[str, Any] = {
        "ok": True,
        "motion": best,
        "user_shape": row["user_shape"],
        "success": row["success"],
        "typical_verbs": list(row["typical_verbs"]),
        "modes": list(row["modes"]),
        "vs_mode": (
            "Motions are interaction shapes. Zeus modes (analytics, tenant, …) are "
            "deployment controls for tools/plugins on a scope. Pick the motion for the "
            "job, then a mode that usually supports it."
        ),
        "surface_hint": {
            "intent": surface.get("intent"),
            "surface": surface.get("surface"),
            "trace_class": surface.get("trace_class"),
        },
        "chat_request": None,
        "docs": {
            "motion": motion_doc(best),
            "guide": f"{MOTIONS_DOC}/ZEUS_MOTIONS_GUIDE.md",
            "using": docs_url("zeus-client/using-zeus-client.md"),
        },
        "next_action": (
            "Use typical_verbs via lint_verb_args / recommend_surface. "
            "Do not generate a custom chat_request from this tool."
        ),
    }
    if row.get("note"):
        out["note"] = row["note"]
    if best == "funnel":
        out["do_not"] = ["Do not run pipeline on Direct — use agent-for-pipeline for multi-step"]
    return out
