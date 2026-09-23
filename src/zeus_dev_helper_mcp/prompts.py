"""MCP prompts for day-one walkthroughs (ZDH-38)."""

from __future__ import annotations

from typing import Any

from zeus_dev_helper_mcp.mcp_compat import register_prompt

FIRST_GREEN = """You are coaching a first Zeus Client app to green using the Developer Helper MCP.

Human docs for first green: https://docs.koten.ai/zeus-client (For AI agents, Start, Using Zeus Client, Errors, Dev Helper MCP). Prefer that live hub + Helper tools (zeus-helper:// / next_step) + live Zeus :8080. Do not clone koten_docs or grep the Zeus engine for first green; agent-index.yaml is a machine map only.

Hard constraints:
- Public Zeus API is :8080, never Hub :9091 from the app path.
- Never invent contract_hash. bind_contract copies a stamped hash only.
- Catalog templates from fetch_chat_request / zeus-helper://catalog/modes are TEMPLATE ONLY. Prefer a live Zeus stamp.
- No secrets in tool results or checklist evidence.
- Semantic cache stays off.
- scaffold_app / smoke_test_agent emit ZeusRuntime + rt.agent.run_turn (not V1 ZeusClient / run_agent).
- Credentials: if the user pasted Zeus URL / username / password in chat, put secrets in the host env or a gitignored .env. Call set_prereq with zeus_url + auth_mode + has_username/has_password (booleans only). NEVER pass password/username/token values into MCP tools.

App kind (important):
- **TravelPlan / demo_travel_sample = agent-plane example** (LLM chat UI: ZeusRuntime + rt.agent.run_turn). Default when the user does not say API vs UI and wants a chat app: **UI** → start_project(sample=travel) → use_sample (clones public demo_travel_sample when missing; optional project_name; sets DEMO_TRAVEL_SAMPLE_DIR). Docs: Agent = run_turn; Direct = rt.data.find/search/get (no LLM) — https://docs.koten.ai/zeus-client/using-zeus-client
- **demo_beer_sample = data-plane catalog example** (zero-LLM catalog UI: one public `pipeline` per search, find or FTS then get; no LLM key). The Python client `rt.data.verb` still rejects `pipeline` (060010); this sample posts the HTTP verb. Never the default for every “make a website from this endpoint” utterance when beer-sample / no LLM is named.
- If the user asks for an **API** / REST / FastAPI Zeus app: start_project(sample=api) → scaffold_app(app_kind=api, coding_language=python). Output is a FastAPI app (GET /healthz, POST /turn) on kotenai-zeus-client (zeus_client_python).
- Application-user class (zero Zeus vocabulary): “I have Zeus at HOST:8080 and beer-sample enabled — make a sample website” (or “don’t use an LLM / show cards”). Prefer Direct/beer over travel. Call set_prereq with the user’s URL + bucket=beer-sample + scope=_default + has_llm_key=false when they said no LLM. **Do not clone demo_travel_sample** and do not require an LLM key for first paint. recommend_surface(needs_llm=false) → Direct (not travel agent). Disk path: start_project(sample=beer) → use_sample(sample=beer) writes demo_beer_sample. Named beer bucket + has_llm_key=false wins over the travel default.
- When building a **Direct website**, you may copy TravelPlan’s BFF / same-origin / config.json shape only. **Do not copy rt.agent.run_turn** unless this is an agent (LLM) app.
- coding_language other than python (golang, node, …): do not invent scaffolds — report unsupported and keep python or the UI sample.

Order:
1. doctor
2. If the user gave a Zeus URL and/or sample/bucket name: call set_prereq with those values first (zeus_url from the user sentence — not Helper’s default localhost; bucket/scope; has_llm_key true/false). Do not explore the Zeus source tree or hand-roll curl OpenAPI for first green.
3. start_project — sample=travel (default UI), sample=api (API-only), or sample=beer when the user named beer-sample / website + no LLM
4. next_step — then only the recommended tool
5. validate_env / readiness_check / recommend_surface as next_step directs
6. Read zeus-helper://checklist and zeus-helper://glossary/{topic} / verbs/* instead of dumping encyclopedia tools or grepping Zeus docs
7. bind_contract from a Hub-stamped catalog when on the agent path (never compute_local). Direct catalog UI does not need an invented hash for first paint.
8. use_sample (UI travel or beer Direct) OR scaffold_app(app_kind=api) (API) OR scaffold_app(app_kind=cli) as fallback
9. smoke_test_zeus; smoke_test_agent only when an LLM key exists and the surface is agent — if has_llm_key=false / sample=beer, stay on Direct and do not treat travel + smoke_test_agent as the only path

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
