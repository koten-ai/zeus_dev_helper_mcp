"""Curated explain(topic) — mirrors koten_docs glossary (ZDH-13 docs source)."""

from __future__ import annotations

from zeus_dev_helper_mcp.config import HelperConfig

# Short answers; deep-links to koten_docs. Expand from glossary.md as needed.
TOPICS: dict[str, dict[str, str]] = {
    "zeus": {
        "summary": "Zeus is the AI-ready data engine beside Couchbase: tools, contracts, sessions, audit on public :8080.",
        "doc": "zeus-client/glossary.md#zeus",
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
    "catalog": {
        "summary": "Allowed tools/verbs for a bind. Prefer live Zeus stamp; public min templates: zeus_chat_request.",
        "doc": "zeus-client/glossary.md#catalog",
    },
    "scope": {
        "summary": "Couchbase scope (with bucket) is the usual Zeus enablement unit for contracts and catalogs.",
        "doc": "zeus-client/glossary.md#scope",
    },
    "hub": {
        "summary": "Hub is admin UI on :9091. App code uses public API :8080 only.",
        "doc": "zeus-client/glossary.md#hub",
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
    "v2_verbs": {
        "summary": "Modern Zeus tool surface via catalog; prefer default_api_version v2.",
        "doc": "zeus-client/glossary.md#v2_verbs",
    },
    "zeus_chat_request": {
        "summary": "Published V2 min chat_request templates for clients/MCP/demos (not stamped for your cluster).",
        "doc": "zeus-client/contracts-and-catalog.md",
        "external": "https://github.com/koten-ai/zeus_chat_request",
    },
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
    }
    key = aliases.get(key, key)
    entry = TOPICS.get(key)
    base = f"https://github.com/koten-ai/koten_docs/blob/{cfg.docs_branch}/"
    if not entry:
        return {
            "topic": topic,
            "found": False,
            "known_topics": sorted(TOPICS.keys()),
            "hint": "Use a known topic id or see glossary.md",
            "docs_glossary": base + "zeus-client/glossary.md",
        }
    out = {
        "topic": key,
        "found": True,
        "summary": entry["summary"],
        "doc_url": base + entry["doc"],
    }
    if entry.get("external"):
        out["external_url"] = entry["external"]
    return out
