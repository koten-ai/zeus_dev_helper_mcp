"""MCP prompts for day-one walkthroughs (ZDH-38)."""

from __future__ import annotations

from typing import Any

from zeus_dev_helper_mcp.mcp_compat import register_prompt

FIRST_GREEN = """You are coaching a first Zeus Client app to green using the Developer Helper MCP.

Hard constraints:
- Public Zeus API is :8080, never Hub :9091 from the app path.
- Never invent contract_hash. bind_contract copies a stamped hash only.
- Catalog templates from fetch_chat_request / zeus-helper://catalog/modes are TEMPLATE ONLY. Prefer a live Zeus stamp.
- No secrets in tool results or checklist evidence.
- Semantic cache stays off.
- scaffold_app / smoke_test_agent emit ZeusRuntime + rt.agent.run_turn (not V1 ZeusClient / run_agent).

Order:
1. doctor
2. start_project (single-agent, travel sample unless the user said otherwise)
3. next_step — then only the recommended tool
4. set_prereq / validate_env / readiness_check as next_step directs
5. Read zeus-helper://checklist and zeus-helper://glossary/{topic} instead of dumping encyclopedia tools
6. bind_contract from a Hub-stamped catalog (never compute_local)
7. scaffold_app or use_sample
8. smoke_test_zeus then smoke_test_agent until session_id / req_id exist

Prefer next_step over get_checklist. Knowledge lives on zeus-helper:// resources. After 5.1+5.2 green, data-plane and multi-agent are handoffs only.
"""

SMOKE_QUESTION_DEFAULT = (
    "In one short sentence, what data is available in this scope?"
)

SUPPORT_PACK = """Build a redacted first-green support pack.

1. Call diagnose_error with the HTTP status, body snippet, ErrorCode / error_class, and ids you have.
2. Read zeus-helper://policy/req-id. Never send composite hop ids (base:1). Never Rewind POST /v2/session/{id}/turn.
3. If the support toolset is on, call support_pack_from_turn with debug JSON or last_smoke_agent.json. Detective links are URL templates only — do not scrape Hub.
4. Evidence may include session_id / req_id / hop ids. Never include passwords, tokens, prompts, or full Zeus bodies.
"""


def register_prompts(mcp: Any) -> None:
    def first_green() -> str:
        """Day-one path to a first green ZeusRuntime turn (session_id / req_id on :8080)."""
        return FIRST_GREEN

    def smoke_question(
        question: str = SMOKE_QUESTION_DEFAULT,
    ) -> str:
        """Advice-shaped question for smoke_test_agent (not raw SQL)."""
        q = (question or SMOKE_QUESTION_DEFAULT).strip() or SMOKE_QUESTION_DEFAULT
        return (
            f"Call smoke_test_agent with this advice-shaped question:\n\n{q}\n\n"
            "Capture session_id / req_id only. Public API :8080. Do not invent contract_hash. "
            "If the smoke fails, call diagnose_error with the failure_class."
        )

    def support_pack() -> str:
        """Redacted support pack from a failed turn (ids/hops only)."""
        return SUPPORT_PACK

    register_prompt(
        mcp,
        first_green,
        name="first_green",
        description="Day-one path to a first green ZeusRuntime turn.",
    )
    register_prompt(
        mcp,
        smoke_question,
        name="smoke_question",
        description="Advice-shaped question for smoke_test_agent.",
    )
    register_prompt(
        mcp,
        support_pack,
        name="support_pack",
        description="Redacted support pack from a failed turn.",
    )
