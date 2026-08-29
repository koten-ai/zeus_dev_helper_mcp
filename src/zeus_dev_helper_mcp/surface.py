"""Surface router — which Zeus Client API to call (ZDH-18)."""

from __future__ import annotations

from typing import Any

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.docs_links import docs_url

# Intent ids accepted by recommend_surface.
INTENTS = ("nl_question", "typeahead", "single_verb", "multi_step")

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


def recommend_surface(
    cfg: HelperConfig,
    *,
    intent: str,
    qps: float | None = None,
    needs_llm: bool | None = None,
) -> dict[str, Any]:
    """Pick a Client surface + Trace-Class. Does not call Zeus."""
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

    if key == "typeahead":
        surface = "rt.data.search"
        trace_class = "direct.interactive"
        do_not = [_DO_NOT_PIPELINE_DIRECT, *_DO_NOT_COMMON]
        notes.append("Typeahead / suggest is Direct interactive — no LLM round.")
    elif key == "single_verb":
        surface = "rt.data.verb"
        trace_class = "direct.read"
        do_not = [_DO_NOT_PIPELINE_DIRECT, *_DO_NOT_COMMON]
        notes.append("Single V2 verb on Direct (find/get/describe/search/…). pipeline is not on Direct.")
    elif key == "multi_step":
        surface = "agent-for-pipeline"
        trace_class = "agent"
        do_not = [_DO_NOT_PIPELINE_DIRECT, *_DO_NOT_COMMON]
        notes.append(
            "Multi-step composition stays on the agent path (rt.agent.run_turn / catalog pipeline). "
            "Do not POST pipeline via Direct."
        )
    else:
        # nl_question
        if needs_llm is False:
            surface = "rt.data.verb"
            trace_class = "direct.read"
            do_not = [_DO_NOT_PIPELINE_DIRECT, *_DO_NOT_COMMON]
            notes.append(
                "needs_llm=false: prefer Direct verb/search over rt.agent.run_turn. "
                "Use intent=typeahead for suggest UI."
            )
        else:
            surface = "rt.agent.run_turn"
            trace_class = "agent"
            do_not = [_DO_NOT_PIPELINE_DIRECT, *_DO_NOT_COMMON]
            notes.append(
                "Natural-language questions go through ZeusRuntime.agent.run_turn → TurnResult. "
                "Default cheap path: ClientSettings(ai_process_result=False)."
            )

    if qps is not None and qps > 5:
        notes.append(
            f"qps={qps}: keep this off the agent loop. Typeahead/single_verb stay Direct; "
            "do not spawn run_turn per keystroke."
        )
        if key == "nl_question" and needs_llm is not False:
            notes.append(
                "High QPS plus NL usually means the UI should be typeahead (rt.data.search), "
                "not an agent turn per character."
            )

    notes.append(
        "ZeusRuntime.from_config() loads config and may set catalog_remote; "
        "still assign rt.services.zeus = HttpxZeusPort(...) and "
        "rt.services.llm = OpenAICompatibleLlmClient(...) for a live turn."
    )

    return {
        "ok": True,
        "intent": key,
        "surface": surface,
        "trace_class": trace_class,
        "do_not": list(do_not),
        "notes": notes,
        "qps": qps,
        "needs_llm": needs_llm,
        "header": "X-Zeus-Trace-Class: " + trace_class,
        "docs": {
            "using": docs_url("zeus-client/using-zeus-client.md"),
            "for_ai_agents": docs_url("zeus-client/for-ai-agents.md"),
        },
        "next_action": (
            "explain_verb / lint_verb_args for Direct; "
            "rt.agent.run_turn for NL; never pipeline on Direct"
        ),
    }
