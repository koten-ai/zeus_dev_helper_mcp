"""Curated explain(topic) — mirrors koten_docs glossary (ZDH-13)."""

from __future__ import annotations

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.docs_links import docs_url
from zeus_dev_helper_mcp.motion import MOTIONS, motion_doc

# Short answers; deep-links to koten_docs. Expand only after glossary.md updates.
TOPICS: dict[str, dict[str, str]] = {
    "zeus": {
        "summary": "Zeus is the AI-ready data engine beside Couchbase: tools, contracts, sessions, audit on public :8080.",
        "doc": "zeus-client/glossary.md#zeus",
    },
    "couchbase": {
        "summary": "Underlying database cluster. Zeus sits beside it; apps usually talk to Zeus, not raw N1QL for agent paths.",
        "doc": "zeus-client/glossary.md#couchbase",
    },
    "bucket": {
        "summary": "Top-level Couchbase container. Zeus enablement and contracts are usually scoped under bucket + scope.",
        "doc": "zeus-client/glossary.md#bucket",
    },
    "scope": {
        "summary": "Couchbase scope (with bucket) is the usual Zeus enablement unit for contracts and catalogs.",
        "doc": "zeus-client/glossary.md#scope",
    },
    "collection": {
        "summary": "Documents live in a collection under a scope. Tools often bind a default collection for describe/search.",
        "doc": "zeus-client/glossary.md#collection",
    },
    "mode": {
        "summary": "chat_request / agent mode name (e.g. analytics). Selects which catalog/guidance apply for a turn.",
        "doc": "zeus-client/glossary.md#mode",
    },
    "zeus_client": {
        "summary": "Zeus Client is the middleman library (kotenai-zeus-client): auth → catalog → LLM rounds → Zeus tools.",
        "doc": "zeus-client/glossary.md#zeus_client",
    },
    "chat_request": {
        "summary": "A chat_request catalog describes allowed tools/guidance per mode. Production uses a stamped copy.",
        "doc": "zeus-client/glossary.md#chat_request",
    },
    "contract": {
        "summary": "A contract stamps allowed tools/modes/binding. Client binds contract_id + contract_hash per scope.",
        "doc": "zeus-client/glossary.md#contract",
    },
    "contract_hash": {
        "summary": "Server-authoritative fingerprint of the stamped catalog. Never invent production hashes.",
        "doc": "zeus-client/glossary.md#contract_hash",
    },
    "enforce_contracts": {
        "summary": "When enforce is on, Zeus rejects tool use that drifts from the stamped contract/hash.",
        "doc": "zeus-client/glossary.md#enforce_contracts",
    },
    "catalog": {
        "summary": "Allowed tools/verbs for a bind. Prefer live Zeus stamp; public min templates: zeus_chat_request.",
        "doc": "zeus-client/glossary.md#catalog",
    },
    "hub": {
        "summary": "Hub is admin UI on :9091. App code uses public API :8080 only.",
        "doc": "zeus-client/glossary.md#hub",
    },
    "workbench": {
        "summary": "Hub Workbench stamps chat_request / contracts for a scope. Operators stamp; apps bind the result.",
        "doc": "zeus-client/glossary.md#workbench",
    },
    "enable_wizard": {
        "summary": "Hub flow to enable Zeus on a scope (collections, tools, contracts). Admin path — not Helper mutations.",
        "doc": "zeus-client/glossary.md#enable_wizard",
    },
    "public_api": {
        "summary": "Zeus public API for agents/clients is port :8080.",
        "doc": "zeus-client/glossary.md#public_api",
    },
    "middleman": {
        "summary": "Zeus Client role: only layer that should talk to LLM, Zeus, and domain extras.",
        "doc": "zeus-client/glossary.md#middleman",
    },
    "session": {
        "summary": "Durable multi-turn conversation on Zeus when enabled; client returns session_id in session_meta.",
        "doc": "zeus-client/glossary.md#session",
    },
    "turn": {
        "summary": "One agent request/response cycle (may include multiple Zeus tool calls).",
        "doc": "zeus-client/glossary.md#turn",
    },
    "req_id": {
        "summary": "Request id from Zeus responses/logs for support and audit correlation.",
        "doc": "zeus-client/glossary.md#req_id",
    },
    "v2_verbs": {
        "summary": "Modern Zeus tool surface via catalog; prefer default_api_version v2.",
        "doc": "zeus-client/glossary.md#v2_verbs",
    },
    "v1_tools": {
        "summary": "Legacy tool surface. Prefer v2 verbs/catalog for new apps.",
        "doc": "zeus-client/glossary.md#v1_tools",
    },
    "detective": {
        "summary": "Evidence/audit style motion — grounded answers with tool proof, not free-form invention.",
        "doc": "zeus-client/glossary.md#detective",
    },
    "motion": {
        "summary": (
            "Motions are interaction shapes, not Zeus modes. The 13 motions: Funnel, Explore, "
            "Verify, Compare, Monitor, Explain, Compose, Simulate, Triage, Route, Refine, "
            "Remember, Custom. A Zeus mode (analytics, tenant, regulated, …) is a deployment "
            "control for tools on a scope. Use recommend_motion(user_job) — it does not generate "
            "a chat_request."
        ),
        "doc": "zeus-client/glossary.md#motion",
        "external": "https://github.com/koten-ai/Zeus/blob/main/docs/public/motions/ZEUS_MOTIONS_GUIDE.md",
    },
    "single_agent": {
        "summary": "One middle-man agent loop to first green. Helper MVP track before multi-agent graduation.",
        "doc": "zeus-client/glossary.md#single_agent",
    },
    "multi_agent": {
        "summary": "Orchestrator / workers / advisor patterns. Helper only hands off (ZDH-11); jobs live in ZJA.",
        "doc": "zeus-client/glossary.md#multi_agent",
    },
    "crawl_walk_run_turbo": {
        "summary": "Capability ladder from first green (crawl) toward multi-agent turbo. See docs ladder page.",
        "doc": "zeus-client/crawl-walk-run-turbo.md",
    },
    "agent_hooks": {
        "summary": "Extension points around agent turns (logging, policy, tools). Product-specific; keep secrets out.",
        "doc": "zeus-client/glossary.md#agent_hooks",
    },
    "evidence": {
        "summary": "Grounding: tool results, req_id, citations. Checklist evidence must never include secrets.",
        "doc": "zeus-client/glossary.md#evidence",
    },
    "zeus_chat_request": {
        "summary": "Published V2 min chat_request templates for clients/MCP/demos (not stamped for your cluster).",
        "doc": "zeus-client/contracts-and-catalog.md",
        "external": "https://github.com/koten-ai/zeus_chat_request",
    },
    "data_plane_mcp": {
        "summary": "Future scope-bound Explore/Verify MCP after first app is green. Helper only recommends/handoffs.",
        "doc": "zeus-client/dev-helper-mcp.md",
    },
    "helper_mcp": {
        "summary": "This product: onboarding coach MCP — checklist, readiness, scaffold, smoke. Not data-plane tools.",
        "doc": "zeus-client/dev-helper-mcp.md",
    },
    "bootstrap": {
        "summary": "GET bootstrap for a scope returns what Zeus knows (collections, chat_request summary, etc.).",
        "doc": "zeus-client/using-zeus-client.md",
    },
    "zeus_runtime": {
        "summary": (
            "ZeusRuntime is the kotenai-zeus-client ≥2.3 default (V1 ZeusClient/run_agent lives under "
            "zeus_client.compat.v1). from_config() loads config and may set catalog_remote; apps still "
            "assign rt.services.zeus = HttpxZeusPort(...) and rt.services.llm = OpenAICompatibleLlmClient(...)."
        ),
        "doc": "zeus-client/using-zeus-client.md",
    },
    "turn_result": {
        "summary": (
            "await rt.agent.run_turn(...) returns TurnResult (answer, debug, session). "
            "Do not expect the V1 (answer, trace, turns, session_meta) tuple on the default import."
        ),
        "doc": "zeus-client/using-zeus-client.md",
    },
    "cheap_path": {
        "summary": (
            "Cheap agent path: ClientSettings(ai_process_result=False) — default. "
            "Skip extra LLM post-processing of Zeus tool results."
        ),
        "doc": "zeus-client/using-zeus-client.md",
    },
    "semantic_cache": {
        "summary": (
            "Semantic cache is POST/GET /v2/agent_memory/* (not the graph tool agent_memory.read). "
            "Client session.semantic_cache.enabled defaults OFF — leave it false in start_project and "
            "scaffolds. Needs Zeus ≥ 0.7.6; GET /v2/agent_memory/status 404 means engine too old or flag off. "
            "Direct/typeahead must not call agent_memory. Use semantic_cache_status to probe."
        ),
        "doc": "zeus-client/using-zeus-client.md",
    },
    "req_id_policy": {
        "summary": (
            "One opaque UUID per HTTP hop (X-Zeus-Req-Id). Never base:1 / uuid:2 composites "
            "(400 invalid_req_id). Group hops with X-Zeus-Chat-Id and X-Zeus-Turn-Id. "
            "Open Detective/Rewind on the tool hop, never POST /v2/session/{id}/turn."
        ),
        "doc": "zeus-client/errors.md",
    },
    "trace_class": {
        "summary": (
            "X-Zeus-Trace-Class: agent (run_turn hops), session (/v2/session*), "
            "direct.interactive (typeahead search), direct.read (rt.data.* verbs). "
            "Do not invent a jobs Trace-Class."
        ),
        "doc": "zeus-client/using-zeus-client.md",
    },
    "direct": {
        "summary": (
            "Direct data plane is rt.data.* with no LLM. Typeahead → rt.data.search "
            "(direct.interactive); single verb → rt.data.verb (direct.read). pipeline is not on Direct."
        ),
        "doc": "zeus-client/using-zeus-client.md",
    },
    "demo_travel_sample": {
        "summary": (
            "TravelPlan (public demo_travel_sample) is the agent-plane / LLM UI example: "
            "Flask BFF, config.json, ZeusRuntime, rt.agent.run_turn, catalog bind. "
            "use_sample(sample=travel) clones it when the user wants a chat UI and has an LLM key. "
            "Do not default it for beer-sample / website / no-LLM utterances."
        ),
        "doc": "zeus-client/using-zeus-client.md",
        "external": "https://github.com/koten-ai/demo_travel_sample",
    },
    "demo_beer_sample": {
        "summary": (
            "demo_beer_sample is the data-plane catalog UI for beer-sample: "
            "FastAPI same-origin BFF. Search follows travel — rt.agent.run_turn with "
            "chat_request omitted so catalog.load_for_turn merges SCOPE BRIEF + MINI-SCHEMA. "
            "An LLM key is required. The BFF does not build a pipeline body. "
            "use_sample(sample=beer) writes it. Do not clone demo_travel_sample for this bucket."
        ),
        "doc": "zeus-client/using-zeus-client.md",
    },
    "typeahead": {
        "summary": (
            "As-you-type suggest is rt.data.search with Trace-Class direct.interactive. "
            "Do not call rt.agent.run_turn per keystroke; do not pipeline on Direct."
        ),
        "doc": "zeus-client/using-zeus-client.md",
    },
    "pipeline": {
        "summary": (
            "pipeline is a server-side read-only DAG of V2 verbs. It is rejected on Direct "
            "(ErrorCode 060010). Use recommend_surface(intent=multi_step) → agent-for-pipeline."
        ),
        "doc": "zeus-client/using-zeus-client.md",
    },
    "hash_boundary": {
        "summary": (
            "MINI-SCHEMA and SCOPE BRIEF are excluded from contract_hash and injected at call time. "
            "guidance, contract metadata, and _* roots are also excluded. Never compute production hashes."
        ),
        "doc": "zeus-client/contracts-and-catalog.md",
    },
}

for _mname, _mrow in MOTIONS.items():
    _key = "explain_motion" if _mname == "explain" else _mname
    TOPICS[_key] = {
        "summary": (
            f"{_mname.title()} motion: {_mrow['user_shape']} "
            f"Typical verbs: {', '.join(_mrow['typical_verbs'])}. "
            f"Modes that often support it: {', '.join(_mrow['modes'])}."
        ),
        "doc": "zeus-client/glossary.md#motion",
        "external": motion_doc(_mname),
    }


def explain_topic(cfg: HelperConfig, topic: str) -> dict:
    key = (topic or "").strip().lower().replace("-", "_").replace(" ", "_")
    # aliases
    aliases = {
        "chatrequest": "chat_request",
        "contract_hash": "contract_hash",
        "hash": "contract_hash",
        "middle_man": "middleman",
        "middle-man": "middleman",
        "client": "zeus_client",
        "port": "public_api",
        "8080": "public_api",
        "9091": "hub",
        "min_catalog": "zeus_chat_request",
        "catalog_repo": "zeus_chat_request",
        "wizard": "enable_wizard",
        "turbo": "crawl_walk_run_turbo",
        "ladder": "crawl_walk_run_turbo",
        "cwr": "crawl_walk_run_turbo",
        "data_plane": "data_plane_mcp",
        "helper": "helper_mcp",
        "dev_helper": "helper_mcp",
        "request_id": "req_id",
        "multi": "multi_agent",
        "single": "single_agent",
        "tools_v2": "v2_verbs",
        "tools_v1": "v1_tools",
        "runtime": "zeus_runtime",
        "zeusruntime": "zeus_runtime",
        "run_turn": "turn_result",
        "turnresult": "turn_result",
        "ai_process_result": "cheap_path",
        "cheap": "cheap_path",
        "cache": "semantic_cache",
        "agent_memory": "semantic_cache",
        "correlation": "req_id_policy",
        "reqid": "req_id_policy",
        "trace": "trace_class",
        "traceclass": "trace_class",
        "direct_path": "direct",
        "rt_data": "direct",
        "travelplan": "demo_travel_sample",
        "travel_plan": "demo_travel_sample",
        "demo_travel": "demo_travel_sample",
        "travel_sample": "demo_travel_sample",
        "agent_plane": "demo_travel_sample",
        "beer_direct": "demo_beer_sample",
        "demo_beer": "demo_beer_sample",
        "beer_sample_ui": "demo_beer_sample",
        "suggest": "typeahead",
        "autocomplete": "typeahead",
        "dag": "pipeline",
        "hash_boundary": "hash_boundary",
        "mini_schema": "hash_boundary",
        "compat": "zeus_runtime",
        "funnel": "funnel",
        "explore": "explore",
        "investigate": "explore",
        "verify": "verify",
        "compare": "compare",
        "monitor": "monitor",
        "explain_motion": "explain_motion",
        "why": "explain_motion",
        "compose": "compose",
        "simulate": "simulate",
        "triage": "triage",
        "route": "route",
        "refine": "refine",
        "remember": "remember",
        "custom_motion": "custom",
        "motions": "motion",
    }
    key = aliases.get(key, key)
    entry = TOPICS.get(key)
    if not entry:
        return {
            "topic": topic,
            "found": False,
            "known_topics": sorted(TOPICS.keys()),
            "hint": "Use a known topic id or see glossary.md",
            "docs_glossary": docs_url("zeus-client/glossary.md"),
            "docs_home": docs_url(""),
            "docs_pin": "koten_docs branch zeus-v1.0.0 (canonical); explain snapshots summaries only",
        }
    out = {
        "topic": key,
        "found": True,
        "summary": entry["summary"],
        "doc_url": docs_url(entry["doc"]),
        "docs_home": docs_url(""),
        "docs_pin": "koten_docs branch zeus-v1.0.0",
    }
    if entry.get("external"):
        out["external_url"] = entry["external"]
    return out
