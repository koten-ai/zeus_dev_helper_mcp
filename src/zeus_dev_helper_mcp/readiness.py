"""Live Zeus readiness probes (ZDH-4)."""

from __future__ import annotations

import contextvars
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


# Paths the readiness and smoke probes actually request. /v1/ai/* and /v2/session/*
# are control-plane routes, not a data bucket.
_AUTH_BUCKET_RE = re.compile(r"/v1/(?P<bucket>[^/]+)/[^/]+/auth/session(?:$|\?)")
_V2_BUCKET_RE = re.compile(r"/v2/(?P<bucket>[^/]+)/[^/]+/")
_RESERVED_BUCKETS = frozenset({"ai", "session", "agent_memory"})
_probe_urls: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "zeus_helper_probe_urls",
    default=None,
)


def note_probe_url(url: str) -> None:
    urls = _probe_urls.get()
    if urls is not None:
        urls.append(url)


def buckets_from_probe_url(url: str) -> tuple[str | None, str | None]:
    """Return (auth bucket, v2 data bucket) for one probe URL."""
    path = urlparse(url).path or ""
    auth_bucket = None
    data_bucket = None
    auth_match = _AUTH_BUCKET_RE.search(path)
    if auth_match and auth_match.group("bucket") not in _RESERVED_BUCKETS:
        auth_bucket = auth_match.group("bucket")
    data_match = _V2_BUCKET_RE.search(path)
    if data_match and data_match.group("bucket") not in _RESERVED_BUCKETS:
        data_bucket = data_match.group("bucket")
    return auth_bucket, data_bucket


def bucket_probe_from_names(
    prereq_bucket: str,
    request_buckets: list[str],
    authenticated_bucket: str | None,
) -> dict[str, Any]:
    """Fail when a probe bucket is not the set_prereq bucket."""
    prereq = (prereq_bucket or "").strip()
    names: list[str] = []
    for name in request_buckets:
        if name and name not in names:
            names.append(name)
    if prereq:
        foreign = [name for name in names if name != prereq]
    else:
        foreign = list(names)
    report: dict[str, Any] = {
        "ok": not foreign,
        "authenticated_bucket": authenticated_bucket,
        "prereq_bucket": prereq or None,
        "request_buckets": names,
    }
    if foreign:
        shown = ",".join(names) if names else "(none)"
        report["failure_class"] = "auth_default_bucket"
        report["foreign_buckets"] = foreign
        report["next_action"] = (
            "A probe touched a bucket other than the set_prereq bucket. "
            f"prereq_bucket={prereq or '(empty)'} "
            f"authenticated_bucket={authenticated_bucket or '(none)'} "
            f"request_buckets={shown}. "
            "Generated apps keep settings.durable_sessions false until post_trace "
            "receives this target."
        )
    return report


def bucket_probe_report(prereq_bucket: str, urls: list[str]) -> dict[str, Any]:
    auth_bucket: str | None = None
    names: list[str] = []
    for url in urls:
        auth, data = buckets_from_probe_url(url)
        if auth and auth_bucket is None:
            auth_bucket = auth
        for name in (auth, data):
            if name and name not in names:
                names.append(name)
    return bucket_probe_from_names(prereq_bucket, names, auth_bucket)


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


_AUTH_REASONS = (
    "bad_credential",
    "unknown_user",
    "user_not_found",
    "account_locked",
)


def _auth_reason(body: Any) -> str | None:
    """A public login reason from the 401 JSON. Never the raw body."""
    if not isinstance(body, dict):
        return None
    parts: list[str] = []
    for key in ("reason", "code", "error", "failure", "message"):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip().lower())
    blob = " ".join(parts)
    if not blob:
        return None
    for reason in _AUTH_REASONS:
        if reason in blob:
            return reason
    return None


def _login_failure_text(bucket: str, scope: str, reason: str | None) -> tuple[str, str]:
    where = f"POST /v1/{bucket}/{scope}/auth/session → HTTP 401"
    if reason:
        detail = f"{where}. Zeus said {reason}."
        action = (
            f"Login failed for bucket {bucket} scope {scope}: {reason}. "
            "Do not try another password."
        )
        return detail, action
    detail = f"{where}. The body did not say bad_credential or an unknown user."
    action = (
        f"Login failed for bucket {bucket} scope {scope} with HTTP 401. "
        "The response did not say whether the password was wrong or the user is unknown. "
        "Do not try another password."
    )
    return detail, action


def mint_scope_session(
    cfg: HelperConfig,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """POST /v1/{bucket}/{scope}/auth/session on the set_prereq bucket.

    This mint is the login. A describe HTTP 200 is not a login.
    The return value carries status, has_session_id, bucket, and scope.
    It never includes the session id, the password, or an API key.
    ``website_green`` calls this same helper.
    """
    bucket = (cfg.default_bucket or "").strip()
    scope = (cfg.default_scope or "").strip()
    base = _base_url(cfg.zeus_url)
    public: dict[str, Any] = {
        "ok": False,
        "bucket": bucket or None,
        "scope": scope or None,
        "has_session_id": False,
        "login_probe": "POST /v1/{bucket}/{scope}/auth/session",
        "stopped": False,
    }
    basic = _basic_auth(cfg)
    if basic is None:
        public["failure_class"] = "login_not_in_process"
        public["stopped"] = True
        public["detail"] = (
            "auth_mode=basic and ZEUS_USERNAME or ZEUS_PASSWORD is empty in this process"
        )
        public["next_action"] = (
            "Write ZEUS_USERNAME and ZEUS_PASSWORD to a mode-600 env file and "
            "call load_process_login with that path. Do not pass the password "
            "as a tool argument. set_prereq stores presence flags only. "
            "A describe 200 is not a login."
        )
        return public
    if not base or not bucket or not scope:
        public["failure_class"] = "login_not_in_process"
        public["stopped"] = True
        public["detail"] = "basic auth needs ZEUS_URL, bucket, and scope before the session mint"
        public["next_action"] = (
            "Call set_prereq with zeus_url, bucket, and scope. "
            "Keep the password in the process environment. "
            "A describe 200 is not a login."
        )
        return public

    path = f"/v1/{bucket}/{scope}/auth/session"
    public["login_probe"] = f"POST {path}"
    login_url = urljoin(base + "/", path.lstrip("/"))
    note_probe_url(login_url)
    owns_client = client is None
    if client is None:
        client = httpx.Client(
            timeout=httpx.Timeout(5.0, connect=3.0),
            headers=_auth_headers(cfg),
            follow_redirects=True,
        )
    try:
        response = client.post(
            login_url,
            auth=basic,
            headers=_auth_headers(cfg),
        )
        status = response.status_code
        has_sid = False
        if status in (200, 201):
            body: Any = {}
            try:
                body = response.json()
            except Exception:  # noqa: BLE001
                body = {}
            if isinstance(body, dict):
                has_sid = bool(body.get("session_id") or body.get("id"))
        public["status"] = status
        public["has_session_id"] = has_sid
        public["detail"] = f"POST {path} → HTTP {status}"
        if status in (200, 201):
            public["ok"] = True
        elif status == 401:
            reason_body: Any = {}
            try:
                reason_body = response.json()
            except Exception:  # noqa: BLE001
                reason_body = {}
            detail, action = _login_failure_text(bucket, scope, _auth_reason(reason_body))
            public["failure_class"] = "auth_failed"
            public["stopped"] = True
            public["detail"] = detail
            public["auth_reason"] = _auth_reason(reason_body)
            public["next_action"] = action + " A describe 200 is not a login."
        else:
            public["next_action"] = (
                "Inspect Zeus auth docs; credentials may still work for other paths. "
                "A describe 200 is not a login."
            )
        return public
    except httpx.RequestError as exc:
        public["failure_class"] = "network_timeout"
        public["detail"] = str(exc)
        public["next_action"] = "Check network / ZEUS_URL reachability"
        return public
    finally:
        if owns_client:
            client.close()


def _gate_from_mint(minted: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    failure = minted.get("failure_class")
    if minted.get("ok"):
        status: GateStatus = (
            "pass" if minted.get("has_session_id") or minted.get("status") == 200 else "unknown"
        )
    elif failure:
        status = "fail"
    else:
        status = "unknown"
    evidence = {
        "status": minted.get("status"),
        "has_session_id": bool(minted.get("has_session_id")),
        "bucket": minted.get("bucket"),
        "scope": minted.get("scope"),
    }
    evidence = {key: value for key, value in evidence.items() if value is not None}
    gate = _gate(
        "auth",
        "Auth principal (basic session mint)",
        status,
        failure_class=failure if isinstance(failure, str) else None,
        detail=str(minted.get("detail") or ""),
        next_action=str(minted.get("next_action") or ""),
        evidence=evidence,
    )
    stopped = bool(minted.get("stopped")) and failure in {"auth_failed", "login_not_in_process"}
    return gate, stopped


def _auth_probe(
    cfg: HelperConfig,
    client: httpx.Client,
    headers: dict[str, str],
    basic: tuple[str, str] | None,
) -> tuple[list[dict[str, Any]], bool]:
    """Login probe. HTTP 401 on the session mint stops later Zeus probes."""
    mode = (cfg.zeus_auth_mode or "none").strip().lower()
    if mode in ("none", "") and not basic and not headers.get("Authorization"):
        return (
            [
                _gate(
                    "auth",
                    "Auth principal",
                    "skip",
                    detail="auth_mode=none and no credentials in env",
                    next_action=(
                        "If Zeus requires auth, set ZEUS_USERNAME/PASSWORD or ZEUS_BEARER_TOKEN"
                    ),
                )
            ],
            False,
        )
    if mode == "basic" or (basic and cfg.default_bucket and cfg.default_scope):
        gate, stopped = _gate_from_mint(mint_scope_session(cfg, client))
        return [gate], stopped
    if headers.get("Authorization"):
        try:
            response = _get(client, _base_url(cfg.zeus_url), "/readyz")
            if response.status_code == 401:
                return (
                    [
                        _gate(
                            "auth",
                            "Auth principal (bearer)",
                            "fail",
                            failure_class="auth_failed",
                            detail="readyz returned 401 with bearer token",
                            next_action="Refresh ZEUS_BEARER_TOKEN / principal",
                        )
                    ],
                    True,
                )
            return (
                [
                    _gate(
                        "auth",
                        "Auth principal (bearer)",
                        "pass" if response.status_code < 500 else "unknown",
                        detail=f"readyz with bearer → HTTP {response.status_code}",
                    )
                ],
                False,
            )
        except httpx.RequestError as exc:
            return (
                [
                    _gate(
                        "auth",
                        "Auth principal",
                        "fail",
                        failure_class="network_timeout",
                        detail=str(exc),
                    )
                ],
                False,
            )
    return (
        [
            _gate(
                "auth",
                "Auth principal",
                "skip",
                detail="No bucket/scope for basic mint and no bearer token",
                next_action="Set ZEUS_BUCKET + ZEUS_SCOPE for basic auth probe, or ZEUS_BEARER_TOKEN",
            )
        ],
        False,
    )


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
    note_probe_url(url)
    return client.get(url, auth=auth)


def run_readiness_check(
    cfg: HelperConfig,
    *,
    update_checklist: bool = True,
    probe_bootstrap: bool = True,
) -> dict[str, Any]:
    """Ordered platform gates. Never returns secret values."""
    probe_urls: list[str] = []
    token = _probe_urls.set(probe_urls)
    try:
        return _readiness_check_impl(
            cfg,
            update_checklist=update_checklist,
            probe_bootstrap=probe_bootstrap,
            probe_urls=probe_urls,
        )
    finally:
        _probe_urls.reset(token)


def _readiness_check_impl(
    cfg: HelperConfig,
    *,
    update_checklist: bool = True,
    probe_bootstrap: bool = True,
    probe_urls: list[str] | None = None,
) -> dict[str, Any]:
    """Ordered platform gates. Never returns secret values."""
    recorded = probe_urls if probe_urls is not None else []
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
        return _finish_readiness(
            cfg, gates, update_checklist=update_checklist, urls=recorded
        )

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
        return _finish_readiness(
            cfg, gates, update_checklist=update_checklist, urls=recorded
        )

    with client:
        # Gate 2: healthz
        gates.append(_probe_json(client, base, "healthz", "GET /healthz (liveness)", "/healthz"))

        # Gate 3: readyz
        gates.append(_probe_json(client, base, "readyz", "GET /readyz (readiness)", "/readyz"))

        # Gate 4: version
        gates.append(_probe_json(client, base, "version", "GET /version", "/version"))

        # Gate 5: login is the scope session mint. A describe 200 is not a login.
        auth_gates, auth_stopped = _auth_probe(cfg, client, headers, basic)
        gates.extend(auth_gates)

        # Gate 6: bootstrap / chat_request (if scope known). 401 stops this path.
        if auth_stopped:
            gates.append(
                _gate(
                    "bootstrap_scope",
                    "Bootstrap / scope binding",
                    "skip",
                    detail="Skipped after the session login failed. A describe 200 is not a login.",
                    next_action=(
                        "Fix ZEUS_USERNAME and ZEUS_PASSWORD for this bucket and scope, "
                        "then run readiness_check again."
                    ),
                )
            )
            gates.append(
                _gate(
                    "live_chat_request",
                    "Live chat_request",
                    "skip",
                    detail="Skipped after the session login failed. A describe 200 is not a login.",
                )
            )
        elif probe_bootstrap and cfg.default_bucket and cfg.default_scope:
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

    return _finish_readiness(
        cfg, gates, update_checklist=update_checklist, urls=recorded
    )


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


def _finish_readiness(
    cfg: HelperConfig,
    gates: list[dict[str, Any]],
    *,
    update_checklist: bool,
    urls: list[str],
) -> dict[str, Any]:
    report = bucket_probe_report(cfg.default_bucket or "", urls)
    detail = (
        f"authenticated bucket={report['authenticated_bucket'] or '(none)'} "
        f"prereq bucket={report['prereq_bucket'] or '(none)'}"
    )
    evidence = {
        "authenticated_bucket": report["authenticated_bucket"],
        "prereq_bucket": report["prereq_bucket"],
        "request_buckets": report["request_buckets"],
    }
    gate = _gate(
        "probe_bucket",
        "Probes stay on the set_prereq bucket",
        "pass" if report["ok"] else "fail",
        failure_class=None if report["ok"] else "auth_default_bucket",
        detail=detail,
        next_action="" if report["ok"] else str(report.get("next_action") or ""),
        evidence=evidence,
    )
    if report["ok"]:
        gates.append(gate)
    else:
        gates.insert(0, gate)
    out = _finish(cfg, gates, update_checklist=update_checklist)
    out["authenticated_bucket"] = report["authenticated_bucket"]
    out["prereq_bucket"] = report["prereq_bucket"]
    out["request_buckets"] = list(report["request_buckets"])
    return out


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
            # 1.2: URL plus a real process LLM key when this path calls the model.
            from zeus_dev_helper_mcp.llm_key import sync_checklist_llm_prereq

            sync_checklist_llm_prereq(cfg)
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
