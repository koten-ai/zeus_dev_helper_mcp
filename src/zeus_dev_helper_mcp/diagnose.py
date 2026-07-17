"""Map error signals to failure_class (ZDH-7)."""

from __future__ import annotations

from typing import Any

from zeus_dev_helper_mcp.config import HelperConfig

# Ordered rules: first match wins
_RULES: list[tuple[list[str], str, str]] = [
    (["9091", "hub admin", "wrong port"], "wrong_port_hub_vs_public", "err-wrong-port"),
    (["401", "unauthor", "auth failed", "login failed"], "auth_failed", "err-401-auth"),
    (["409", "drift", "contract_hash", "hash mismatch"], "hash_drift", "err-409-drift"),
    (["timeout", "timed out", "deadline"], "network_timeout", "err-timeout"),
    (["api_key", "llm_key", "openai", "missing key"], "llm_key_missing", "err-llm-key"),
    (["empty catalog", "no tools", "chat_request", "no chat_request"], "empty_tool_catalog", "err-empty-catalog"),
    (["not enabled", "scope_not", "404 bootstrap"], "scope_not_enabled", "err-scope-not-enabled"),
    (["collection"], "collection_not_registered", "err-collection"),
    (["contract_required", "unbound"], "contract_required", "err-contract-required"),
    (["dispatch_failed", "tool failed"], "dispatch_failed", "err-dispatch-failed"),
]

_NEXT: dict[str, str] = {
    "wrong_port_hub_vs_public": "Point ZEUS_URL at public :8080, not Hub :9091",
    "auth_failed": "Fix credentials / principal; re-mint session",
    "hash_drift": "Resync stamped catalog; never hand-edit contract_hash",
    "network_timeout": "curl $ZEUS_URL/healthz; check TOOL_TIMEOUT / network",
    "llm_key_missing": "Set LLM_API_KEY / provider api_key in client config",
    "empty_tool_catalog": "sync_chat_requests + stamp; check mode",
    "scope_not_enabled": "Enable scope in Hub or fix bucket/scope names",
    "collection_not_registered": "Align collection with enabled map",
    "contract_required": "Bind scope_contracts from stamped catalog",
    "dispatch_failed": "Inspect trace tool_calls + req_id; see engine logs",
}


def diagnose_error(
    cfg: HelperConfig,
    *,
    status: str = "",
    body: str = "",
    message: str = "",
    req_id: str = "",
    session_id: str = "",
    zeus_url: str = "",
) -> dict[str, Any]:
    blob = f"{status} {body} {message} {zeus_url}".lower()
    failure = "dispatch_failed"
    anchor = "err-dispatch-failed"
    for needles, fc, anc in _RULES:
        if any(n in blob for n in needles):
            failure = fc
            anchor = anc
            break

    # explicit status code
    st = str(status).strip()
    if st == "401":
        failure, anchor = "auth_failed", "err-401-auth"
    elif st == "409":
        failure, anchor = "hash_drift", "err-409-drift"

    base = f"https://github.com/koten-ai/koten_docs/blob/{cfg.docs_branch}/zeus-client/errors.md"
    return {
        "implemented": True,
        "failure_class": failure,
        "next_action": _NEXT.get(failure, "See errors.md"),
        "doc_path": "zeus-client/errors.md",
        "doc_anchor": anchor,
        "doc_url": f"{base}#{anchor}",
        "evidence": {
            "status": status or None,
            "req_id": req_id or None,
            "session_id": session_id or None,
            "zeus_url": zeus_url or cfg.zeus_url or None,
            "message_preview": (message or body)[:300] or None,
        },
        "agent_index": (
            f"https://github.com/koten-ai/koten_docs/blob/{cfg.docs_branch}/agent-index.yaml"
        ),
    }
