"""Map error signals to failure_class (ZDH-7 + ZDH-19).

Does **not** import kotenai-zeus-client. ErrorCode strings are a static table.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.docs_links import docs_url

# Ordered rules: first match wins (after explicit error_code / HTTP status).
_RULES: list[tuple[list[str], str, str]] = [
    (["9091", "hub admin", "wrong port"], "wrong_port_hub_vs_public", "err-wrong-port"),
    (["base:1", "uuid:2", "composite hop", "composite_hop", "prefix:digits"], "composite_req_id", "err-composite-req-id"),
    (["invalid_req_id"], "invalid_req_id", "err-invalid-req-id"),
    (["/v1/session", "v1/session", "v1 session"], "v1_session_removed", "err-v1-session-removed"),
    (["pipeline not on direct", "pipeline_not_on_direct", "not on direct"], "pipeline_not_on_direct", "err-pipeline-not-on-direct"),
    (["biz:", "fts key", "src_keys as node"], "fts_key_used_as_node_id", "err-fts-key-as-node-id"),
    (["where_not_in_mini_schema", "not in mini-schema", "mini_schema", "$gt", "$gte", "$lt", "$lte"], "where_not_in_mini_schema", "err-where-not-in-mini-schema"),
    (["invent hash", "invented hash", "compute_local", "contract_hash_invent"], "contract_hash_invent_forbidden", "err-contract-hash-invent"),
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

# Well-known kotenai-zeus-client ErrorCode values (copied; do not import the package).
_ERROR_CODE_MAP: dict[str, tuple[str, str]] = {
    "030005": ("contract_hash_invent_forbidden", "err-contract-hash-invent"),
    "CONTRACT_HASH_INVENT_FORBIDDEN": ("contract_hash_invent_forbidden", "err-contract-hash-invent"),
    "060010": ("pipeline_not_on_direct", "err-pipeline-not-on-direct"),
    "ZEUS_PIPELINE_NOT_ON_DIRECT": ("pipeline_not_on_direct", "err-pipeline-not-on-direct"),
    "060004": ("contract_required", "err-contract-required"),
    "ZEUS_CONTRACT_REQUIRED": ("contract_required", "err-contract-required"),
    "050010": ("llm_rate_limit", "err-llm-key"),
    "LLM_RATE_LIMIT": ("llm_rate_limit", "err-llm-key"),
    "050011": ("llm_rate_limit", "err-llm-key"),
    "LLM_QUOTA_EXHAUSTED": ("llm_rate_limit", "err-llm-key"),
    "010012": ("llm_key_missing", "err-llm-key"),
    "LLM_API_KEY_MISSING": ("llm_key_missing", "err-llm-key"),
    "060005": ("auth_failed", "err-401-auth"),
    "ZEUS_AUTH_FAILED": ("auth_failed", "err-401-auth"),
    "100001": ("auth_failed", "err-401-auth"),
    "AUTH_FAILED": ("auth_failed", "err-401-auth"),
    "010007": ("dispatch_failed", "err-dispatch-failed"),
    "ZEUS_URL_MISSING": ("dispatch_failed", "err-dispatch-failed"),
    "060002": ("dispatch_failed", "err-dispatch-failed"),
    "ZEUS_HTTP_4XX": ("dispatch_failed", "err-dispatch-failed"),
    "060003": ("network_timeout", "err-timeout"),
    "ZEUS_HTTP_5XX": ("network_timeout", "err-timeout"),
    "000005": ("network_timeout", "err-timeout"),
    "TIMEOUT": ("network_timeout", "err-timeout"),
}

# Zeus JSON error_class / error strings.
_ERROR_CLASS_MAP: dict[str, tuple[str, str]] = {
    "invalid_req_id": ("invalid_req_id", "err-invalid-req-id"),
    "composite_hop": ("composite_req_id", "err-composite-req-id"),
    "composite_req_id": ("composite_req_id", "err-composite-req-id"),
    "v1_session_removed": ("v1_session_removed", "err-v1-session-removed"),
    "pipeline_not_on_direct": ("pipeline_not_on_direct", "err-pipeline-not-on-direct"),
    "where_not_in_mini_schema": ("where_not_in_mini_schema", "err-where-not-in-mini-schema"),
    "fts_key_used_as_node_id": ("fts_key_used_as_node_id", "err-fts-key-as-node-id"),
    "contract_hash_invent_forbidden": ("contract_hash_invent_forbidden", "err-contract-hash-invent"),
    "hash_drift": ("hash_drift", "err-409-drift"),
    "contract_required": ("contract_required", "err-contract-required"),
    "auth_failed": ("auth_failed", "err-401-auth"),
}

_NEXT: dict[str, str] = {
    "wrong_port_hub_vs_public": "Point ZEUS_URL at public :8080, not Hub :9091",
    "auth_failed": "Fix credentials / principal; re-mint session",
    "hash_drift": "Resync stamped catalog; never hand-edit contract_hash",
    "network_timeout": "curl $ZEUS_URL/healthz; check TOOL_TIMEOUT / network",
    "llm_key_missing": "Set LLM_API_KEY / provider api_key in client config",
    "llm_rate_limit": "Backoff/retry; ErrorCode 050010 is rate/quota, not a missing key",
    "empty_tool_catalog": "rt.catalog.sync / load + stamp; check mode",
    "scope_not_enabled": "Enable scope in Hub or fix bucket/scope names",
    "collection_not_registered": "Align collection with enabled map",
    "contract_required": "Bind scope_contracts from stamped catalog",
    "dispatch_failed": "Inspect trace tool_calls + req_id; see engine logs",
    "invalid_req_id": (
        "One opaque UUID per HTTP hop. Do not send composite hop ids. "
        "Group hops with X-Zeus-Chat-Id / X-Zeus-Turn-Id."
    ),
    "composite_req_id": (
        "X-Zeus-Req-Id rejected as composite (e.g. base:1). Mint one UUID per hop; "
        "never reuse or suffix hop indexes."
    ),
    "v1_session_removed": (
        "V1 /v1/session is gone. Use ZeusRuntime + /v2/session or rt.agent.run_turn. "
        "Do not call V1 session APIs."
    ),
    "pipeline_not_on_direct": (
        "pipeline is not on Direct. recommend_surface(intent=multi_step) → agent-for-pipeline."
    ),
    "where_not_in_mini_schema": (
        "where is equality-only and keys must exist in MINI-SCHEMA. Use lint_verb_args."
    ),
    "fts_key_used_as_node_id": (
        "Do not get/project FTS biz: keys as graph node ids. Prefer find → project."
    ),
    "contract_hash_invent_forbidden": (
        "Never invent or locally compute production contract_hash; bind from a stamped catalog only."
    ),
}

_ANCHOR: dict[str, str] = {
    "wrong_port_hub_vs_public": "err-wrong-port",
    "auth_failed": "err-401-auth",
    "hash_drift": "err-409-drift",
    "network_timeout": "err-timeout",
    "llm_key_missing": "err-llm-key",
    "llm_rate_limit": "err-llm-key",
    "empty_tool_catalog": "err-empty-catalog",
    "scope_not_enabled": "err-scope-not-enabled",
    "collection_not_registered": "err-collection",
    "contract_required": "err-contract-required",
    "dispatch_failed": "err-dispatch-failed",
    "invalid_req_id": "err-invalid-req-id",
    "composite_req_id": "err-composite-req-id",
    "v1_session_removed": "err-v1-session-removed",
    "pipeline_not_on_direct": "err-pipeline-not-on-direct",
    "where_not_in_mini_schema": "err-where-not-in-mini-schema",
    "fts_key_used_as_node_id": "err-fts-key-as-node-id",
    "contract_hash_invent_forbidden": "err-contract-hash-invent",
}


def _norm_code(value: str) -> str:
    s = (value or "").strip()
    if not s:
        return ""
    if s.isdigit() and len(s) < 6:
        s = s.zfill(6)
    return s.replace("-", "_").replace(" ", "").upper()


def _lookup_code(error_code: str) -> tuple[str, str] | None:
    raw = (error_code or "").strip()
    if not raw:
        return None
    for candidate in (raw, _norm_code(raw), raw.upper(), raw.lower()):
        hit = _ERROR_CODE_MAP.get(candidate) or _ERROR_CODE_MAP.get(candidate.upper())
        if hit:
            return hit
        hit = _ERROR_CLASS_MAP.get(candidate.lower())
        if hit:
            return hit
    return None


def _lookup_class(error_class: str) -> tuple[str, str] | None:
    raw = (error_class or "").strip()
    if not raw:
        return None
    hit = _ERROR_CLASS_MAP.get(raw.lower())
    if hit:
        return hit
    return _lookup_code(raw)


def _hub_origin(zeus_url: str) -> str:
    """Detective lives on Hub. URL template only — never fetched."""
    u = (zeus_url or "").strip()
    if not u:
        return ""
    parsed = urlparse(u if "://" in u else "http://" + u)
    host = parsed.hostname or "localhost"
    scheme = parsed.scheme or "http"
    port = parsed.port
    if port == 8080:
        return f"{scheme}://{host}:9091"
    if port:
        return f"{scheme}://{host}:{port}"
    return f"{scheme}://{host}"


def _detective_links(
    *,
    zeus_url: str,
    req_id: str,
    chat_id: str,
) -> dict[str, str] | None:
    if not req_id and not chat_id:
        return None
    origin = _hub_origin(zeus_url)
    links: dict[str, str] = {}
    if req_id:
        path = f"/hub/debug/req/{req_id}"
        links["req"] = f"{origin}{path}" if origin else path
    if chat_id:
        path = f"/hub/debug?chat_id={chat_id}"
        links["chat"] = f"{origin}{path}" if origin else path
    return links or None


def diagnose_error(
    cfg: HelperConfig,
    *,
    status: str = "",
    body: str = "",
    message: str = "",
    req_id: str = "",
    session_id: str = "",
    zeus_url: str = "",
    error_code: str = "",
    error_class: str = "",
    chat_id: str = "",
    turn_id: str = "",
) -> dict[str, Any]:
    blob = f"{status} {body} {message} {zeus_url} {error_code} {error_class}".lower()
    failure = "dispatch_failed"
    anchor = "err-dispatch-failed"
    matched = "default"

    # 1. Explicit client ErrorCode / Zeus error_class
    hit = _lookup_code(error_code) or _lookup_class(error_class)
    if hit:
        failure, anchor = hit
        matched = "error_code" if error_code else "error_class"
        if failure == "invalid_req_id" and (
            "base:1" in blob or "composite" in blob or (error_class or "").lower() == "composite_hop"
        ):
            failure, anchor = "composite_req_id", "err-composite-req-id"
    else:
        # 2. HTTP status
        st = str(status).strip()
        if st == "401":
            failure, anchor = "auth_failed", "err-401-auth"
            matched = "status"
        elif st == "409":
            failure, anchor = "hash_drift", "err-409-drift"
            matched = "status"
        elif st == "404" and any(n in blob for n in ("/v1/session", "v1/session", "v1 session", "v1/tools")):
            failure, anchor = "v1_session_removed", "err-v1-session-removed"
            matched = "status"
        elif st == "400" and ("invalid_req_id" in blob or "base:1" in blob or "composite_hop" in blob):
            if "base:1" in blob or "composite" in blob:
                failure, anchor = "composite_req_id", "err-composite-req-id"
            else:
                failure, anchor = "invalid_req_id", "err-invalid-req-id"
            matched = "status"
        else:
            # 3. Needles
            for needles, fc, anc in _RULES:
                if any(n in blob for n in needles):
                    failure = fc
                    anchor = anc
                    matched = "needle"
                    break

    url = zeus_url or cfg.zeus_url or ""
    detective = _detective_links(zeus_url=url, req_id=req_id.strip(), chat_id=chat_id.strip())
    base = docs_url("zeus-client/errors.md")
    out: dict[str, Any] = {
        "implemented": True,
        "failure_class": failure,
        "next_action": _NEXT.get(failure, "See errors.md"),
        "doc_path": "zeus-client/errors.md",
        "doc_anchor": _ANCHOR.get(failure, anchor),
        "doc_url": f"{base}#{_ANCHOR.get(failure, anchor)}",
        "matched_via": matched,
        "evidence": {
            "status": status or None,
            "error_code": error_code or None,
            "error_class": error_class or None,
            "req_id": req_id or None,
            "session_id": session_id or None,
            "chat_id": chat_id or None,
            "turn_id": turn_id or None,
            "zeus_url": url or None,
            "message_preview": (message or body)[:300] or None,
        },
        "agent_index": docs_url("agent-index.yaml"),
    }
    if detective:
        out["detective"] = detective
        out["detective_note"] = "URL templates only — Helper does not scrape Hub/Detective."
        if failure in ("invalid_req_id", "composite_req_id"):
            out["detective_note"] += " invalid_req_id has no hop to rewind; fix the client header first."
    return out
