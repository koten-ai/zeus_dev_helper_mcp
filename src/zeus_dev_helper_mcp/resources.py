"""MCP resources for glossary, checklist, verbs, policies, catalog modes (ZDH-33)."""

from __future__ import annotations

import json
from typing import Any

from zeus_dev_helper_mcp.catalog import CatalogError, list_modes
from zeus_dev_helper_mcp.checklist import load_checklist
from zeus_dev_helper_mcp.config import reload_config
from zeus_dev_helper_mcp.contract import explain_hash_boundary
from zeus_dev_helper_mcp.explain import TOPICS, explain_topic
from zeus_dev_helper_mcp.mcp_compat import register_resource
from zeus_dev_helper_mcp.support import explain_req_id_policy
from zeus_dev_helper_mcp.verbs import explain_verb, known_verbs

RESOURCE_SCHEME = "zeus-helper"


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, default=str) + "\n"


def _cfg():
    return reload_config()


def register_resources(mcp: Any) -> None:
    @register_resource_fn(mcp, f"{RESOURCE_SCHEME}://checklist", "checklist", "First-app coaching checklist JSON")
    def checklist() -> str:
        return _dump(load_checklist(_cfg()))

    @register_resource_fn(
        mcp,
        f"{RESOURCE_SCHEME}://glossary",
        "glossary",
        "Glossary topic index (read zeus-helper://glossary/{topic} for a page)",
    )
    def glossary_index() -> str:
        return _dump(
            {
                "topics": sorted(TOPICS.keys()),
                "read": f"{RESOURCE_SCHEME}://glossary/{{topic}}",
            }
        )

    @register_resource_fn(
        mcp,
        f"{RESOURCE_SCHEME}://glossary/{{topic}}",
        "glossary_topic",
        "Glossary page for a Zeus/Client topic",
    )
    def glossary_topic(topic: str) -> str:
        return _dump(explain_topic(_cfg(), topic))

    @register_resource_fn(
        mcp,
        f"{RESOURCE_SCHEME}://verbs",
        "verbs",
        "V2 verb index (read zeus-helper://verbs/{name} for a page)",
    )
    def verbs_index() -> str:
        return _dump({"verbs": known_verbs(), "read": f"{RESOURCE_SCHEME}://verbs/{{name}}"})

    @register_resource_fn(
        mcp,
        f"{RESOURCE_SCHEME}://verbs/{{name}}",
        "verb",
        "V2 verb encyclopedia page (path class, demux, Direct)",
    )
    def verb_page(name: str) -> str:
        return _dump(explain_verb(_cfg(), name=name))

    @register_resource_fn(
        mcp,
        f"{RESOURCE_SCHEME}://policy/hash-boundary",
        "hash_boundary",
        "What is excluded from contract_hash (MINI-SCHEMA / brief)",
    )
    def hash_boundary() -> str:
        return _dump(explain_hash_boundary(_cfg()))

    @register_resource_fn(
        mcp,
        f"{RESOURCE_SCHEME}://policy/req-id",
        "req_id_policy",
        "One UUID per hop; never composite hop ids; never Rewind /turn",
    )
    def req_id_policy() -> str:
        return _dump(explain_req_id_policy(_cfg()))

    @register_resource_fn(
        mcp,
        f"{RESOURCE_SCHEME}://catalog/modes",
        "catalog_modes",
        "V2 min chat_request modes from zeus_chat_request (TEMPLATE ONLY)",
    )
    def catalog_modes() -> str:
        try:
            return _dump(list_modes(_cfg()))
        except CatalogError as e:
            return _dump(
                {
                    "ok": False,
                    "error": e.message,
                    "failure_class": e.failure_class,
                    "next_action": (
                        "Helper clones public zeus_chat_request when "
                        "ZEUS_CHAT_REQUEST_DIR is unset; fix git/network or set "
                        "ZEUS_CHAT_REQUEST_DIR / GITHUB_TOKEN."
                    ),
                }
            )


def register_resource_fn(mcp: Any, uri: str, name: str, description: str):
    """Decorator that registers `fn` as a resource and returns `fn` unchanged."""

    def deco(fn):
        register_resource(mcp, uri, fn, name=name, description=description)
        return fn

    return deco
