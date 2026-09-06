"""Semantic cache / agent_memory coach (ZDH-28). Default off. Direct must not call it."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import httpx

from zeus_dev_helper_mcp.compat import eval_feature_gates
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.docs_links import docs_url
from zeus_dev_helper_mcp.readiness import (
    _auth_headers,
    _base_url,
    _get,
    _looks_like_hub,
)

STATUS_PATH = "/v2/agent_memory/status"


def interpret_memory_status(status_code: int, body: Any = None) -> dict[str, Any]:
    """Map GET /v2/agent_memory/status to a coach result (no secrets)."""
    if status_code == 404:
        return {
            "probe": "miss",
            "available": False,
            "detail": "engine too old or flag off (GET /v2/agent_memory/status → 404)",
        }
    if status_code == 401:
        return {
            "probe": "auth",
            "available": None,
            "failure_class": "auth_failed",
            "detail": "401 on agent_memory/status",
        }
    if status_code == 200:
        enabled = None
        embedder = None
        if isinstance(body, dict):
            enabled = body.get("enabled")
            embedder = body.get("embedder") or body.get("embedder_present")
        return {
            "probe": "ok",
            "available": True,
            "engine_enabled": enabled,
            "embedder": embedder,
            "detail": "status endpoint present — still leave client enabled=false unless you opt in",
        }
    return {
        "probe": "error",
        "available": None,
        "detail": f"HTTP {status_code} on {STATUS_PATH}",
    }


def semantic_cache_status(cfg: HelperConfig, *, zeus_url: str = "") -> dict[str, Any]:
    """Coach semantic cache. Never recommends enabling. Optional live GET /status."""
    url = (zeus_url or cfg.zeus_url or "").strip()
    base = _base_url(url)
    rec = {
        "client_enabled": False,
        "apply_to": ["agent"],
        "do_not": [
            "Do not enable in start_project / scaffolds",
            "Do not call agent_memory from Direct / typeahead",
            "Do not treat MATRIX as supported — flag, cosine_scan MVP",
        ],
    }
    docs = {
        "using": docs_url("zeus-client/using-zeus-client.md"),
        "compat": docs_url("compatibility.md"),
    }
    gates = [g for g in eval_feature_gates(None) if g["id"] == "semantic_cache"]

    if not base:
        return {
            "ok": True,
            "recommended_enabled": False,
            "recommendation": rec,
            "probe": {"probe": "skip", "detail": "ZEUS_URL not set — not probing"},
            "gates": gates,
            "docs": docs,
            "next_action": "Leave session.semantic_cache.enabled=false; set ZEUS_URL to probe /v2/agent_memory/status",
        }

    if _looks_like_hub(base):
        return {
            "ok": False,
            "recommended_enabled": False,
            "failure_class": "wrong_port_hub_vs_public",
            "recommendation": rec,
            "docs": docs,
            "next_action": "Point ZEUS_URL at public :8080, not Hub :9091",
        }

    probe: dict[str, Any]
    try:
        with httpx.Client(
            timeout=httpx.Timeout(5.0, connect=3.0), headers=_auth_headers(cfg)
        ) as client:
            r = _get(client, base, STATUS_PATH)
            payload: Any = None
            try:
                payload = r.json()
            except Exception:  # noqa: BLE001
                payload = None
            probe = interpret_memory_status(r.status_code, payload)
            probe["url"] = urljoin(base + "/", STATUS_PATH.lstrip("/"))
    except httpx.RequestError as e:
        probe = {
            "probe": "error",
            "failure_class": "network_timeout",
            "detail": str(e)[:200],
        }

    return {
        "ok": probe.get("probe") in ("ok", "miss", "skip"),
        "recommended_enabled": False,
        "recommendation": rec,
        "probe": probe,
        "gates": gates,
        "docs": docs,
        "next_action": (
            "Leave enabled=false. Direct/typeahead must not call agent_memory. "
            + str(probe.get("detail") or "")
        ).strip(),
    }
