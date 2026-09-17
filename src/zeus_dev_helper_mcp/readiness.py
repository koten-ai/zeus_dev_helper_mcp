"""Live Zeus readiness probes (ZDH-4)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from zeus_dev_helper_mcp.catalog import list_modes
from zeus_dev_helper_mcp.checklist import set_item_status
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.docs_links import docs_url

GateStatus = str  # pass | fail | unknown | skip


def _base_url(url: str) -> str:
    u = (url or "").strip().rstrip("/")
    return u


def _looks_like_hub(url: str) -> bool:
    return bool(re.search(r":9091\b", url or "")) or "/hub" in (url or "").lower()


def _auth_headers(cfg: HelperConfig) -> dict[str, str]:
    import os

    headers: dict[str, str] = {"User-Agent": "zeus-dev-helper-mcp", "Accept": "application/json"}
    token = (
        os.environ.get("ZEUS_BEARER_TOKEN")
        or os.environ.get("ZEUS_TOKEN")
        or ""
    ).strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _basic_auth(cfg: HelperConfig) -> tuple[str, str] | None:
    import os

    user = (os.environ.get("ZEUS_USERNAME") or os.environ.get("ZEUS_USER") or "").strip()
    password = (os.environ.get("ZEUS_PASSWORD") or "").strip()
    if user and password:
        return user, password
    return None


def _gate(
    gate_id: str,
    title: str,
    status: GateStatus,
    *,
    failure_class: str | None = None,
    detail: str = "",
    next_action: str = "",
    evidence: dict | None = None,
) -> dict[str, Any]:
    return {
        "id": gate_id,
        "title": title,
        "status": status,
        "failure_class": failure_class,
        "detail": detail,
        "next_action": next_action,
        "evidence": evidence or {},
    }


def _get(
    client: httpx.Client,
    base: str,
    path: str,
    *,
    auth: tuple[str, str] | None = None,
) -> httpx.Response:
    url = urljoin(base + "/", path.lstrip("/"))
    return client.get(url, auth=auth)


def run_readiness_check(
    cfg: HelperConfig,
    *,
    update_checklist: bool = True,
    probe_bootstrap: bool = True,
) -> dict[str, Any]:
    """Ordered platform gates. Never returns secret values."""
    gates: list[dict[str, Any]] = []
    base = _base_url(cfg.zeus_url)

    # Gate 0: URL configured
    if not base:
        gates.append(
            _gate(
                "url_configured",
                "ZEUS_URL configured",
                "fail",
                failure_class=None,
                detail="ZEUS_URL is empty",
                next_action="Set ZEUS_URL=http://<host>:8080 or call set_prereq(zeus_url=...)",
            )
        )
        return _finish(cfg, gates, update_checklist=update_checklist)

    gates.append(
        _gate(
            "url_configured",
            "ZEUS_URL configured",
            "pass",
            detail=base,
        )
    )

    # Gate 1: not Hub port
    if _looks_like_hub(base):
        gates.append(
            _gate(
                "public_port",
                "Public API port (not Hub :9091)",
                "fail",
                failure_class="wrong_port_hub_vs_public",
                detail=f"URL looks like Hub/admin: {base}",
                next_action="Use public API :8080 for app/readiness probes, not Hub :9091",
            )
        )
    else:
        parsed = urlparse(base)
        port = parsed.port
        detail = f"host={parsed.hostname} port={port or 'default'}"
        gates.append(
            _gate(
                "public_port",
                "Public API port (not Hub :9091)",
                "pass" if port != 9091 else "fail",
                failure_class="wrong_port_hub_vs_public" if port == 9091 else None,
                detail=detail,
            )
        )

    timeout = httpx.Timeout(5.0, connect=3.0)
    headers = _auth_headers(cfg)
    basic = _basic_auth(cfg)

    try:
        client = httpx.Client(timeout=timeout, headers=headers, follow_redirects=True)
    except Exception as e:  # noqa: BLE001
        gates.append(
            _gate(
                "client",
                "HTTP client",
                "fail",
                detail=str(e),
                next_action="Fix local HTTP client configuration",
            )
        )
        return _finish(cfg, gates, update_checklist=update_checklist)

    with client:
        # Gate 2: healthz
        gates.append(_probe_json(client, base, "healthz", "GET /healthz (liveness)", "/healthz"))

        # Gate 3: readyz
        gates.append(_probe_json(client, base, "readyz", "GET /readyz (readiness)", "/readyz"))

        # Gate 4: version
        gates.append(_probe_json(client, base, "version", "GET /version", "/version"))

        # Gate 5: auth (optional)
        if cfg.zeus_auth_mode in ("none", "") and not basic and not headers.get("Authorization"):
            gates.append(
                _gate(
                    "auth",
                    "Auth principal",
                    "skip",
                    detail="auth_mode=none and no credentials in env",
                    next_action="If Zeus requires auth, set ZEUS_USERNAME/PASSWORD or ZEUS_BEARER_TOKEN",
                )
            )
        elif cfg.default_bucket and cfg.default_scope and basic:
            # basic login is per-scope on many deploys
            path = f"/v1/{cfg.default_bucket}/{cfg.default_scope}/auth/session"
            try:
                r = client.post(
                    urljoin(base + "/", path.lstrip("/")),
                    auth=basic,
                    headers=headers,
                )
                if r.status_code in (200, 201):
                    body = {}
                    try:
                        body = r.json()
                    except Exception:  # noqa: BLE001
                        pass
                    has_sid = bool(body.get("session_id") or body.get("id"))
                    gates.append(
                        _gate(
                            "auth",
                            "Auth principal (basic session mint)",
                            "pass" if has_sid or r.status_code == 200 else "unknown",
                            detail=f"POST {path} → HTTP {r.status_code}",
                            evidence={"status": r.status_code, "has_session_id": has_sid},
                        )
                    )
                elif r.status_code == 401:
                    gates.append(
                        _gate(
                            "auth",
                            "Auth principal (basic session mint)",
                            "fail",
                            failure_class="auth_failed",
                            detail=f"POST {path} → 401",
                            next_action="Fix username/password or scope_credentials for this bucket/scope",
                        )
                    )
                else:
                    gates.append(
                        _gate(
                            "auth",
                            "Auth principal (basic session mint)",
                            "unknown",
                            detail=f"POST {path} → HTTP {r.status_code}",
                            next_action="Inspect Zeus auth docs; credentials may still work for other paths",
                        )
                    )
            except httpx.RequestError as e:
                gates.append(
                    _gate(
                        "auth",
                        "Auth principal",
                        "fail",
                        failure_class="network_timeout",
                        detail=str(e),
                        next_action="Check network / ZEUS_URL reachability",
                    )
                )
        elif headers.get("Authorization"):
            # bearer: try a light authenticated path
            try:
                r = _get(client, base, "/readyz")
                if r.status_code == 401:
                    gates.append(
                        _gate(
                            "auth",
                            "Auth principal (bearer)",
                            "fail",
                            failure_class="auth_failed",
                            detail="readyz returned 401 with bearer token",
                            next_action="Refresh ZEUS_BEARER_TOKEN / principal",
                        )
                    )
                else:
                    gates.append(
                        _gate(
                            "auth",
                            "Auth principal (bearer)",
                            "pass" if r.status_code < 500 else "unknown",
                            detail=f"readyz with bearer → HTTP {r.status_code}",
                        )
                    )
            except httpx.RequestError as e:
                gates.append(
                    _gate(
                        "auth",
                        "Auth principal",
                        "fail",
                        failure_class="network_timeout",
                        detail=str(e),
                    )
                )
        else:
            gates.append(
                _gate(
                    "auth",
                    "Auth principal",
                    "skip",
                    detail="No bucket/scope for basic mint and no bearer token",
                    next_action="Set ZEUS_BUCKET + ZEUS_SCOPE for basic auth probe, or ZEUS_BEARER_TOKEN",
                )
            )

        # Gate 6: bootstrap / chat_request (if scope known)
        if probe_bootstrap and cfg.default_bucket and cfg.default_scope:
            b, s = cfg.default_bucket, cfg.default_scope
            path = f"/v1/ai/bootstrap/scope/{b}/{s}"
            try:
                r = _get(client, base, path, auth=basic)
                if r.status_code == 200:
                    tools_hint = None
                    try:
                        j = r.json()
                        # avoid dumping full catalog
                        if isinstance(j, dict):
                            tools_hint = {
                                "top_keys": sorted(j.keys())[:12],
                            }
                    except Exception:  # noqa: BLE001
                        tools_hint = None
                    gates.append(
                        _gate(
                            "bootstrap_scope",
                            f"Bootstrap scope {b}/{s}",
                            "pass",
                            detail=f"GET {path} → 200",
                            evidence=tools_hint or {},
                        )
                    )
                elif r.status_code == 401:
                    gates.append(
                        _gate(
                            "bootstrap_scope",
                            f"Bootstrap scope {b}/{s}",
                            "fail",
                            failure_class="auth_failed",
                            detail=f"GET {path} → 401",
                            next_action="Auth failed for bootstrap — fix credentials",
                        )
                    )
                elif r.status_code == 404:
                    gates.append(
                        _gate(
                            "bootstrap_scope",
                            f"Bootstrap scope {b}/{s}",
                            "fail",
                            failure_class="scope_not_enabled",
                            detail=f"GET {path} → 404",
                            next_action="Enable scope in Hub or fix bucket/scope names",
                        )
                    )
                else:
                    gates.append(
                        _gate(
                            "bootstrap_scope",
                            f"Bootstrap scope {b}/{s}",
                            "fail" if r.status_code >= 400 else "unknown",
                            failure_class="scope_not_enabled" if r.status_code >= 400 else None,
                            detail=f"GET {path} → HTTP {r.status_code}",
                            next_action="Check Hub enablement / bootstrap docs if not 200",
                        )
                    )
            except httpx.RequestError as e:
                gates.append(
                    _gate(
                        "bootstrap_scope",
                        "Bootstrap scope",
                        "fail",
                        failure_class="network_timeout",
                        detail=str(e),
                    )
                )

            # chat_request.json for mode
            mode = cfg.default_mode or "analytics"
            cr_path = f"/v1/ai/chat_request.json?mode={mode}"
            # some deployments want scope query — try with bucket/scope if present
            cr_path_scoped = f"/v1/ai/chat_request.json?mode={mode}&bucket={b}&scope={s}"
            try:
                r = _get(client, base, cr_path_scoped, auth=basic)
                if r.status_code >= 400:
                    r = _get(client, base, cr_path, auth=basic)
                if r.status_code == 200:
                    verb_count = None
                    try:
                        j = r.json()
                        verbs = j.get("verbs") or j.get("tools") or []
                        verb_count = len(verbs) if isinstance(verbs, list) else None
                    except Exception:  # noqa: BLE001
                        pass
                    empty = verb_count == 0
                    gates.append(
                        _gate(
                            "live_chat_request",
                            f"Live chat_request mode={mode}",
                            "fail" if empty else "pass",
                            failure_class="empty_tool_catalog" if empty else None,
                            detail=f"HTTP {r.status_code}"
                            + (f", verbs/tools={verb_count}" if verb_count is not None else ""),
                            next_action=(
                                "Catalog empty — stamp/sync or enable tools for mode"
                                if empty
                                else ""
                            ),
                            evidence={"status": r.status_code, "verb_count": verb_count},
                        )
                    )
                elif r.status_code == 401:
                    gates.append(
                        _gate(
                            "live_chat_request",
                            f"Live chat_request mode={mode}",
                            "fail",
                            failure_class="auth_failed",
                            detail=f"HTTP 401",
                        )
                    )
                else:
                    gates.append(
                        _gate(
                            "live_chat_request",
                            f"Live chat_request mode={mode}",
                            "unknown",
                            detail=f"HTTP {r.status_code}",
                            next_action="Optional: use fetch_chat_request templates then stamp",
                        )
                    )
            except httpx.RequestError as e:
                gates.append(
                    _gate(
                        "live_chat_request",
                        "Live chat_request",
                        "fail",
                        failure_class="network_timeout",
                        detail=str(e),
                    )
                )
        else:
            gates.append(
                _gate(
                    "bootstrap_scope",
                    "Bootstrap / scope binding",
                    "skip",
                    detail="Set ZEUS_BUCKET and ZEUS_SCOPE (or set_prereq) to probe bootstrap",
                    next_action="set_prereq(bucket=..., scope=...) then readiness_check again",
                )
            )

    # Gate: offline catalog templates (always useful)
    try:
        modes = list_modes(cfg)
        n = len(modes.get("modes") or [])
        gates.append(
            _gate(
                "template_catalogs",
                "zeus_chat_request templates",
                "pass" if n else "fail",
                failure_class="empty_tool_catalog" if not n else None,
                detail=f"{n} modes available",
                next_action=""
                if n
                else (
                    "Helper clones public zeus_chat_request when ZEUS_CHAT_REQUEST_DIR "
                    "is unset; fix git/network or set ZEUS_CHAT_REQUEST_DIR / GITHUB_TOKEN"
                ),
            )
        )
    except Exception as e:  # noqa: BLE001
        gates.append(
            _gate(
                "template_catalogs",
                "zeus_chat_request templates",
                "fail",
                failure_class="empty_tool_catalog",
                detail=str(e),
                next_action=(
                    "Helper clones public zeus_chat_request when ZEUS_CHAT_REQUEST_DIR "
                    "is unset; fix git/network or set the env / GITHUB_TOKEN"
                ),
            )
        )

    return _finish(cfg, gates, update_checklist=update_checklist)


def _probe_json(
    client: httpx.Client,
    base: str,
    gate_id: str,
    title: str,
    path: str,
) -> dict[str, Any]:
    try:
        r = _get(client, base, path)
    except httpx.ConnectError as e:
        return _gate(
            gate_id,
            title,
            "fail",
            failure_class="network_timeout",
            detail=f"connect error: {e}",
            next_action="Start Zeus or fix ZEUS_URL host/port (public :8080)",
        )
    except httpx.TimeoutException as e:
        return _gate(
            gate_id,
            title,
            "fail",
            failure_class="network_timeout",
            detail=f"timeout: {e}",
            next_action="Check Zeus load / network; retry",
        )
    except httpx.RequestError as e:
        return _gate(
            gate_id,
            title,
            "fail",
            failure_class="network_timeout",
            detail=str(e),
            next_action="Check ZEUS_URL reachability",
        )

    if r.status_code == 200:
        snippet = ""
        try:
            j = r.json()
            if isinstance(j, dict):
                # keep tiny evidence only
                keys = list(j.keys())[:8]
                snippet = f"keys={keys}"
        except Exception:  # noqa: BLE001
            snippet = f"body_len={len(r.content)}"
        return _gate(gate_id, title, "pass", detail=f"HTTP 200 {snippet}".strip())

    if r.status_code == 401:
        return _gate(
            gate_id,
            title,
            "fail",
            failure_class="auth_failed",
            detail=f"HTTP 401 on {path}",
            next_action="Provide credentials or use auth_mode that matches deploy",
        )

    return _gate(
        gate_id,
        title,
        "fail" if r.status_code >= 400 else "unknown",
        detail=f"HTTP {r.status_code} on {path}",
        next_action="Inspect Zeus logs / confirm public API path",
    )


def _finish(
    cfg: HelperConfig,
    gates: list[dict[str, Any]],
    *,
    update_checklist: bool,
) -> dict[str, Any]:
    fails = [g for g in gates if g["status"] == "fail"]
    passes = [g for g in gates if g["status"] == "pass"]
    overall = "pass" if not fails and passes else ("fail" if fails else "unknown")

    # first failure drives next_action
    primary = fails[0] if fails else None
    next_action = (primary or {}).get("next_action") or (
        "Platform ready — continue checklist (bind catalog / smoke)"
        if overall == "pass"
        else "Fix failing gates"
    )

    if update_checklist:
        try:
            # 2.1 Zeus reachable
            hz = next((g for g in gates if g["id"] == "healthz"), None)
            if hz and hz["status"] == "pass":
                set_item_status(cfg, "2.1", "done", evidence=hz.get("detail", "healthz ok"))
            elif hz and hz["status"] == "fail":
                set_item_status(cfg, "2.1", "blocked", evidence=hz.get("detail", "healthz fail"))
            # 2.2 auth
            au = next((g for g in gates if g["id"] == "auth"), None)
            if au and au["status"] == "pass":
                set_item_status(cfg, "2.2", "done", evidence=au.get("detail", "auth ok"))
            elif au and au["status"] == "fail":
                set_item_status(cfg, "2.2", "blocked", evidence=au.get("detail", "auth fail"))
            # 2.3 scope
            bs = next((g for g in gates if g["id"] == "bootstrap_scope"), None)
            if bs and bs["status"] == "pass":
                set_item_status(cfg, "2.3", "done", evidence=bs.get("detail", "bootstrap ok"))
            elif bs and bs["status"] == "fail":
                set_item_status(cfg, "2.3", "blocked", evidence=bs.get("detail", "bootstrap fail"))
            # 1.2 prereqs if URL set
            if cfg.zeus_url:
                set_item_status(cfg, "1.2", "done", evidence="ZEUS_URL set")
        except Exception:  # noqa: BLE001 — checklist optional
            pass

    docs = {
        "probes": (
            docs_url("zeus/developers/api/probes.md")
        ),
        "errors": (
            docs_url("zeus-client/errors.md")
        ),
        "dev_helper": (
            docs_url("zeus-client/dev-helper-mcp.md")
        ),
    }

    return {
        "overall": overall,
        "zeus_url": cfg.zeus_url or None,
        "bucket": cfg.default_bucket or None,
        "scope": cfg.default_scope or None,
        "mode": cfg.default_mode,
        "gates": gates,
        "failed_count": len(fails),
        "passed_count": len(passes),
        "primary_failure_class": (primary or {}).get("failure_class"),
        "next_action": next_action,
        "docs": docs,
    }
