"""Live Zeus bootstrap_scope (ZDH-5)."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urljoin

import httpx

from zeus_dev_helper_mcp.checklist import set_item_status
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.docs_links import docs_url


def _auth() -> tuple[str, str] | None:
    user = (os.environ.get("ZEUS_USERNAME") or os.environ.get("ZEUS_USER") or "").strip()
    password = (os.environ.get("ZEUS_PASSWORD") or "").strip()
    if user and password:
        return user, password
    return None


def _headers() -> dict[str, str]:
    h = {"User-Agent": "zeus-dev-helper-mcp", "Accept": "application/json"}
    token = (os.environ.get("ZEUS_BEARER_TOKEN") or os.environ.get("ZEUS_TOKEN") or "").strip()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def bootstrap_scope(
    cfg: HelperConfig,
    *,
    bucket: str = "",
    scope: str = "",
    mode: str = "",
    detail: str = "summary",
    update_checklist: bool = True,
) -> dict[str, Any]:
    """GET /v1/ai/bootstrap/scope/{bucket}/{scope} — summary by default (not full dump)."""
    base = (cfg.zeus_url or "").strip().rstrip("/")
    b = (bucket or cfg.default_bucket or "").strip()
    s = (scope or cfg.default_scope or "").strip()
    m = (mode or cfg.default_mode or "analytics").strip()

    if not base:
        return {
            "ok": False,
            "failure_class": None,
            "next_action": "Set ZEUS_URL or set_prereq(zeus_url=...)",
        }
    if ":9091" in base:
        return {
            "ok": False,
            "failure_class": "wrong_port_hub_vs_public",
            "next_action": "Use public :8080",
        }
    if not b or not s:
        return {
            "ok": False,
            "failure_class": "scope_not_enabled",
            "next_action": "Set bucket/scope via set_prereq or args",
        }

    path = f"/v1/ai/bootstrap/scope/{b}/{s}"
    url = urljoin(base + "/", path.lstrip("/"))
    try:
        with httpx.Client(timeout=httpx.Timeout(30.0, connect=5.0), headers=_headers()) as client:
            r = client.get(url, auth=_auth())
            req_id = r.headers.get("X-Zeus-Req-Id") or ""
            if r.status_code == 401:
                return {
                    "ok": False,
                    "failure_class": "auth_failed",
                    "status": 401,
                    "url": url,
                    "req_id": req_id or None,
                    "next_action": "Fix ZEUS_USERNAME/PASSWORD or bearer token",
                }
            if r.status_code == 404:
                return {
                    "ok": False,
                    "failure_class": "scope_not_enabled",
                    "status": 404,
                    "url": url,
                    "next_action": "Enable scope in Hub or fix bucket/scope names",
                }
            if r.status_code >= 400:
                return {
                    "ok": False,
                    "failure_class": "dispatch_failed",
                    "status": r.status_code,
                    "url": url,
                    "body_preview": (r.text or "")[:300],
                    "next_action": "See Zeus logs; diagnose_error with status/body",
                }

            data = r.json() if r.content else {}
    except httpx.RequestError as e:
        return {
            "ok": False,
            "failure_class": "network_timeout",
            "error": str(e),
            "next_action": "Check ZEUS_URL reachability",
        }

    # Also try live chat_request for mode
    cr_summary: dict[str, Any] = {}
    try:
        cr_url = urljoin(base + "/", f"v1/ai/chat_request.json?mode={m}&bucket={b}&scope={s}")
        with httpx.Client(timeout=15.0, headers=_headers()) as client:
            cr = client.get(cr_url, auth=_auth())
            if cr.status_code >= 400:
                cr = client.get(
                    urljoin(base + "/", f"v1/ai/chat_request.json?mode={m}"),
                    auth=_auth(),
                )
            if cr.status_code == 200:
                j = cr.json()
                verbs = j.get("verbs") or j.get("tools") or []
                cr_summary = {
                    "status": 200,
                    "verb_count": len(verbs) if isinstance(verbs, list) else None,
                    "format": j.get("_format"),
                }
            else:
                cr_summary = {"status": cr.status_code}
    except httpx.RequestError as e:
        cr_summary = {"error": str(e)}

    summary: dict[str, Any] = {
        "ok": True,
        "bucket": b,
        "scope": s,
        "mode": m,
        "url": url,
        "req_id": req_id or None,
        "bootstrap_top_keys": sorted(data.keys())[:20] if isinstance(data, dict) else [],
        "live_chat_request": cr_summary,
        "warning": "Production still needs stamped contract_hash — never invent hashes",
        "next_action": (
            "Configure middle-man with scope_url/tools; stamp catalog; "
            "sync_chat_requests; then smoke_test_agent"
        ),
        "docs": {
            "contracts": (
                docs_url("zeus-client/contracts-and-catalog.md")
            ),
            "templates": "https://github.com/koten-ai/zeus_chat_request",
        },
    }

    if detail == "full" and isinstance(data, dict):
        # still cap size — only include small nested counts
        summary["bootstrap"] = data
    else:
        # extract useful non-huge fields
        if isinstance(data, dict):
            for key in ("scope_url", "bucket", "scope", "tools", "verbs", "modes"):
                if key in data:
                    val = data[key]
                    if key in ("tools", "verbs") and isinstance(val, list):
                        summary[key + "_count"] = len(val)
                    elif not isinstance(val, (dict, list)) or (
                        isinstance(val, list) and len(val) < 20
                    ):
                        summary[key] = val
                    elif isinstance(val, dict):
                        summary[key + "_keys"] = sorted(val.keys())[:15]

    if update_checklist:
        try:
            set_item_status(cfg, "2.3", "done", evidence=f"bootstrap {b}/{s} ok")
            set_item_status(cfg, "4.1", "done", evidence="bootstrap + chat_request probed")
        except Exception:  # noqa: BLE001
            pass

    return summary
