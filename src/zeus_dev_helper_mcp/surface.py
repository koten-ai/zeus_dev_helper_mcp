"""Surface router — which Zeus Client API to call (ZDH-18)."""

from __future__ import annotations

from typing import Any

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.docs_links import docs_url

# Intent ids accepted by recommend_surface.
INTENTS = ("nl_question", "typeahead", "single_verb", "multi_step")

# Catalog question box stays inside 2–4 rounds. A copilot may use 8.
CATALOG_MAX_ROUNDS = 4
COPILOT_MAX_ROUNDS = 8
JOB_WALL_MS = 120000
JOB_WALL_LONG_MS = 300000

_DIRECT_INPUTS = (
    ("list", ("find", "get")),
    ("chips", ("find", "get", "search")),
    ("typeahead", ("search",)),
    ("paging", ("find", "get")),
    ("detail", ("get",)),
)

_DO_NOT_COMMON = (
    "Do not use Hub :9091 from the app path (public API is :8080)",
    "Do not invent contract_hash",
    "Do not send composite hop ids (base:1) as X-Zeus-Req-Id",
    "Do not call agent_memory from Direct / typeahead",
)

_DO_NOT_PIPELINE_DIRECT = "Do not run pipeline on Direct (rt.data.verb / run_verb)"

_ALIAS = {
    "nl": "nl_question",
    "question": "nl_question",
    "agent": "nl_question",
    "chat": "nl_question",
    "run_turn": "nl_question",
    "suggest": "typeahead",
    "autocomplete": "typeahead",
    "search": "typeahead",
    "interactive": "typeahead",
    "verb": "single_verb",
    "direct": "single_verb",
    "find": "single_verb",
    "get": "single_verb",
    "describe": "single_verb",
    "pipeline": "multi_step",
    "multi": "multi_step",
    "dag": "multi_step",
    "compose": "multi_step",
}


def _normalize_intent(intent: str) -> str:
    raw = (intent or "").strip().lower().replace("-", "_").replace(" ", "_")
    return _ALIAS.get(raw, raw)


def _count(value: int | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def job_decision(
    *,
    url_count: int | None = None,
    scope_count: int | None = None,
    report_wait_s: float | None = None,
    source_type_count: int | None = None,
    page_interaction: bool = False,
    settings_mode: str | None = None,
) -> dict[str, Any]:
    """Job hint for two or more targets, or a long report. One scope stays One chat.

    ``settings.mode=analytics`` does not promote an input. A confirm cannot
    override a hard stop. ``write`` stays false until the caller passes confirm.
    """
    urls = 1 if url_count is None else max(0, url_count)
    scopes = 1 if scope_count is None else max(0, scope_count)
    wait = 0.0 if report_wait_s is None else float(report_wait_s)
    types = 1 if source_type_count is None else max(0, source_type_count)
    mode = (settings_mode or "").strip().lower()
    multi_target = urls >= 2 or scopes >= 2
    long_report = wait >= 20
    # 120000 covers a wait through 2 minutes. 300000 is only for a wait
    # the operator put past that, up to 5 minutes.
    wall_ms = JOB_WALL_LONG_MS if wait > 120 else JOB_WALL_MS
    base = {
        "hint": False,
        "hard_stop": None,
        "write": False,
        "wall_ms": None,
        "settings_mode": mode or None,
        "url_count": urls,
        "scope_count": scopes,
        "source_type_count": types,
    }
    if page_interaction:
        base["hard_stop"] = "page_interaction"
        return base
    if not multi_target and not long_report:
        base["hard_stop"] = "two_source_types" if types >= 2 else "one_scope"
        return base
    reason = "multi_url" if urls >= 2 else "multi_scope" if scopes >= 2 else "long_report"
    base.update(
        {
            "hint": True,
            "hard_stop": None,
            "reason": reason,
            "wall_ms": wall_ms,
            "confirm_required": True,
        }
    )
    return base


def _direct_inputs() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, verbs in _DIRECT_INPUTS:
        rows.append(
            {
                "input": name,
                "mode": "direct",
                "verbs": list(verbs),
                "llm": False,
                "enabled": True,
                "chat_request": None,
            }
        )
    return rows


def _question_input(*, needs_llm: bool | None, page: str | None) -> dict[str, Any]:
    kind = (page or "catalog").strip().lower()
    rounds = COPILOT_MAX_ROUNDS if kind == "copilot" else CATALOG_MAX_ROUNDS
    row: dict[str, Any] = {
        "input": "question",
        "mode": "one_chat",
        "surface": "rt.agent.run_turn",
        "trace_class": "agent",
        "verbs": ["run_turn"],
        "chat_request": "omit",
        "max_rounds": rounds,
        "llm": True,
        "enabled": needs_llm is not False,
        "one_url": True,
        "one_scope": True,
    }
    if needs_llm is False:
        row["reason"] = (
            "Pour is off until LLM_API_KEY, XAI_API_KEY, or OPENAI_API_KEY "
            "is in the app environment."
        )
    return row


def recommend_surface(
    cfg: HelperConfig,
    *,
    intent: str,
    qps: float | None = None,
    needs_llm: bool | None = None,
    url_count: int | None = None,
    scope_count: int | None = None,
    report_wait_s: float | None = None,
    source_type_count: int | None = None,
    page: str | None = None,
    settings_mode: str | None = None,
    page_interaction: bool = False,
) -> dict[str, Any]:
    """Name each website input. A single box still returns one surface.

    Does not call Zeus. A website (``nl_question``) has no single ``surface``.
    """
    del cfg
    key = _normalize_intent(intent)
    notes: list[str] = []

    if key not in INTENTS:
        return {
            "ok": False,
            "intent": intent,
            "known_intents": list(INTENTS),
            "next_action": "Pass intent=nl_question|typeahead|single_verb|multi_step",
            "docs": {
                "using": docs_url("zeus-client/using-zeus-client.md"),
                "helper": docs_url("zeus-client/dev-helper-mcp.md"),
            },
        }

    supplied = any(
        value is not None
        for value in (url_count, scope_count, report_wait_s, source_type_count, settings_mode)
    ) or page_interaction
    decision = job_decision(
        url_count=_count(url_count),
        scope_count=_count(scope_count),
        report_wait_s=report_wait_s,
        source_type_count=_count(source_type_count),
        page_interaction=page_interaction,
        settings_mode=settings_mode,
    )

    surface: str | None = None
    trace_class: str | None = None
    inputs: list[dict[str, Any]] | None = None
    do_not = [_DO_NOT_PIPELINE_DIRECT, *_DO_NOT_COMMON]

    if key == "typeahead":
        surface = "rt.data.search"
        trace_class = "direct.interactive"
        notes.append("Typeahead / suggest is Direct interactive — no LLM round.")
    elif key == "single_verb":
        surface = "rt.data.verb"
        trace_class = "direct.read"
        notes.append("Single V2 verb on Direct (find/get/describe/search/…). pipeline is not on Direct.")
    elif key == "multi_step":
        surface = "agent-for-pipeline"
        trace_class = "agent"
        notes.append(
            "A multi-step pipeline on one URL and one scope stays One chat "
            "(rt.agent.run_turn). Do not POST pipeline via Direct."
        )
    else:
        inputs = [*_direct_inputs(), _question_input(needs_llm=needs_llm, page=page)]
        notes.append(
            "List, chips, typeahead, paging, and detail are Direct. "
            "The question box is One chat: rt.agent.run_turn with chat_request omitted."
        )
        if needs_llm is False:
            notes.append(
                "Direct inputs stay on. The question box stays off until an LLM key is in the app environment."
            )
        else:
            rounds = inputs[-1]["max_rounds"]
            notes.append(
                f"Question box max_rounds is {rounds}. Many entity types stay in that one chat."
            )

    if qps is not None and qps > 5 and key != "nl_question":
        notes.append(
            f"qps={qps}: keep this off the agent loop. Typeahead/single_verb stay Direct; "
            "do not spawn run_turn per keystroke."
        )

    if key != "nl_question":
        notes.append(
            "ZeusRuntime.from_config() loads config and may set catalog_remote; "
            "still assign rt.services.zeus = HttpxZeusPort(...) and "
            "rt.services.llm = OpenAICompatibleLlmClient(...) for a live turn."
        )

    if key in {"nl_question", "multi_step"} or supplied:
        if decision.get("hint"):
            notes.append(
                "Job hint only. Name one unit per scope and wait for a yes "
                "before jobs.host_url or orchestrator and advisor roles. "
                f"Default wall_ms is {decision.get('wall_ms')}."
            )
        elif decision.get("hard_stop"):
            notes.append(
                "This stays One chat. Smoke-green does not write jobs.host_url, "
                "orchestrator or advisor roles, or a job wall."
            )

    if inputs is not None:
        next_action = (
            "Name each input. Direct boxes need no LLM key. "
            "Leave the question box off until LLM_API_KEY, XAI_API_KEY, or OPENAI_API_KEY "
            "is in the app environment."
            if needs_llm is False
            else (
                "Name each input. Direct boxes are find, get, and search. "
                "The question box is rt.agent.run_turn with chat_request omitted."
            )
        )
    else:
        next_action = (
            "explain_verb / lint_verb_args for Direct; "
            "rt.agent.run_turn for NL; never pipeline on Direct"
        )
    if decision.get("hint") and (key in {"nl_question", "multi_step"} or supplied):
        next_action = (
            "Job hint only. Name the units and wait for a yes before writing "
            "jobs.host_url or orchestrator and advisor roles."
        )

    out: dict[str, Any] = {
        "ok": True,
        "intent": key,
        "do_not": list(do_not),
        "notes": notes,
        "qps": qps,
        "needs_llm": needs_llm,
        "docs": {
            "using": docs_url("zeus-client/using-zeus-client.md"),
            "for_ai_agents": docs_url("zeus-client/for-ai-agents.md"),
        },
        "next_action": next_action,
        "recommended_tools": (
            ["readiness_check", "use_sample"]
            if key == "nl_question"
            else []
        ),
    }
    if inputs is not None:
        out["inputs"] = inputs
        out["page"] = "copilot" if (page or "").strip().lower() == "copilot" else "catalog"
    else:
        out["surface"] = surface
        out["trace_class"] = trace_class
        out["header"] = "X-Zeus-Trace-Class: " + str(trace_class)
    if key in {"nl_question", "multi_step"} or supplied:
        out["job"] = decision
    return out
