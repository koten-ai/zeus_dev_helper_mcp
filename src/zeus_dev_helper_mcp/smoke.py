"""Smoke tests for Zeus and Zeus Client agent loop (ZDH-7)."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx

from zeus_dev_helper_mcp.checklist import set_item_status
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.docs_links import docs_url
from zeus_dev_helper_mcp.readiness import (
    bucket_probe_from_names,
    bucket_probe_report,
    run_readiness_check,
    take_scope_session,
)


def _base(cfg: HelperConfig) -> str:
    return (cfg.zeus_url or "").strip().rstrip("/")


def request_auth(cfg: HelperConfig | None = None) -> tuple[str, str] | None:
    """Basic auth from env (values never logged). cfg unused; signature matches callers."""
    _ = cfg
    user = (os.environ.get("ZEUS_USERNAME") or os.environ.get("ZEUS_USER") or "").strip()
    password = (os.environ.get("ZEUS_PASSWORD") or "").strip()
    if user and password:
        return user, password
    return None


def request_headers() -> dict[str, str]:
    h = {"User-Agent": "zeus-dev-helper-mcp", "Accept": "application/json", "Content-Type": "application/json"}
    token = (os.environ.get("ZEUS_BEARER_TOKEN") or os.environ.get("ZEUS_TOKEN") or "").strip()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def describe_scope_url(cfg: HelperConfig) -> str | None:
    """POST /v2/{bucket}/{scope}/describe — no Hub, no document bodies."""
    base = _base(cfg)
    bucket = cfg.default_bucket
    scope = cfg.default_scope
    if not base or not bucket or not scope:
        return None
    return f"{base}/v2/{bucket}/{scope}/describe"


def _auth(cfg: HelperConfig) -> tuple[str, str] | None:
    return request_auth(cfg)


def _headers() -> dict[str, str]:
    return request_headers()


_AUTH_STOPS = frozenset({"login_not_in_process", "auth_failed"})
_SMOKE_SESSION_ENV = "ZEUS_SMOKE_SESSION"


def _auth_mode(cfg: HelperConfig) -> str:
    return (cfg.zeus_auth_mode or "none").strip().lower()


def _readiness_auth_stop(ready: dict[str, Any]) -> str | None:
    """A login failure must not continue into an anonymous describe."""
    if ready.get("overall") != "fail":
        return None
    failure = ready.get("primary_failure_class")
    if failure in _AUTH_STOPS:
        return str(failure)
    return None


class _SmokeSessionStore:
    """Holds one minted scope session for this smoke. Not the process environment."""

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id

    def get(self, name: str) -> str | None:
        if name == _SMOKE_SESSION_ENV and self._session_id:
            return self._session_id
        if not name:
            return None
        val = os.environ.get(name)
        if val is None or val == "":
            return None
        return val

    def __repr__(self) -> str:
        return "_SmokeSessionStore(session=set)"


def _use_scope_session(zeus: dict[str, Any]) -> dict[str, Any]:
    """Later calls send only X-Zeus-Session. Basic auth is not repeated."""
    out = dict(zeus)
    out["auth_mode"] = "session"
    out["token_env"] = _SMOKE_SESSION_ENV
    out.pop("password_env", None)
    out.pop("username", None)
    return out


def _merge_probe_buckets(
    ready: dict[str, Any],
    prereq_bucket: str,
    extra_urls: list[str],
) -> dict[str, Any]:
    extra = bucket_probe_report(prereq_bucket, extra_urls)
    return bucket_probe_from_names(
        prereq_bucket,
        list(ready.get("request_buckets") or []) + list(extra["request_buckets"]),
        ready.get("authenticated_bucket") or extra.get("authenticated_bucket"),
    )


def smoke_test_zeus(cfg: HelperConfig, *, update_checklist: bool = True) -> dict[str, Any]:
    """No LLM: readiness + POST describe on scope."""
    base = _base(cfg)
    if not base:
        return {
            "ok": False,
            "failure_class": None,
            "next_action": "Set ZEUS_URL then readiness_check / smoke_test_zeus",
            "steps": [],
        }
    if ":9091" in base:
        return {
            "ok": False,
            "failure_class": "wrong_port_hub_vs_public",
            "next_action": "Use public API :8080, not Hub :9091",
            "steps": [],
        }

    steps: list[dict[str, Any]] = []
    ready = run_readiness_check(cfg, update_checklist=False, probe_bootstrap=True)
    steps.append(
        {
            "name": "readiness_check",
            "ok": ready.get("overall") == "pass",
            "overall": ready.get("overall"),
            "failed_count": ready.get("failed_count"),
            "primary_failure_class": ready.get("primary_failure_class"),
        }
    )

    bucket = cfg.default_bucket
    scope = cfg.default_scope
    collection = cfg.default_collection or "_default"
    if not bucket or not scope:
        out = {
            "ok": False,
            "failure_class": "scope_not_enabled",
            "next_action": "set_prereq(bucket=..., scope=...) or ZEUS_BUCKET/ZEUS_SCOPE, then retry",
            "steps": steps,
            "readiness": ready,
        }
        return out

    # Scope-level describe (V2). A foreign bucket is a failed check and is not sent.
    url = describe_scope_url(cfg) or f"{base}/v2/{bucket}/{scope}/describe"
    buckets = _merge_probe_buckets(ready, bucket, [url])
    if not buckets["ok"]:
        return {
            "ok": False,
            "failure_class": "auth_default_bucket",
            "next_action": buckets.get("next_action")
            or "Keep probes on the set_prereq bucket",
            "bucket": bucket,
            "scope": scope,
            "collection": collection,
            "authenticated_bucket": buckets.get("authenticated_bucket"),
            "prereq_bucket": buckets.get("prereq_bucket"),
            "request_buckets": buckets.get("request_buckets") or [],
            "steps": steps,
            "readiness": ready,
        }
    stopped = _readiness_auth_stop(ready)
    if stopped:
        return {
            "ok": False,
            "failure_class": stopped,
            "next_action": ready.get("next_action")
            or "Fix the login before describe. A describe 200 is not a login.",
            "bucket": bucket,
            "scope": scope,
            "collection": collection,
            "authenticated_bucket": buckets.get("authenticated_bucket"),
            "prereq_bucket": buckets.get("prereq_bucket"),
            "request_buckets": buckets.get("request_buckets") or [],
            "steps": steps,
            "readiness": ready,
        }
    body: dict[str, Any] = {}  # server defaults
    status = 0
    req_id = ""
    preview = ""
    sid: str | None = None
    client_headers = _headers()
    if _auth_mode(cfg) == "basic":
        client_headers.pop("Authorization", None)
    try:
        with httpx.Client(timeout=httpx.Timeout(30.0, connect=5.0), headers=client_headers) as client:
            auth = _auth(cfg)
            headers = dict(client_headers)
            if _auth_mode(cfg) == "basic":
                minted, sid = take_scope_session(cfg, client)
                steps.append(
                    {
                        "name": "auth_session",
                        "ok": bool(minted.get("ok")),
                        "status": minted.get("status"),
                        "failure_class": minted.get("failure_class"),
                        "has_session_id": bool(minted.get("has_session_id")),
                    }
                )
                if not minted.get("ok") or not sid:
                    failure = str(minted.get("failure_class") or "auth_failed")
                    return {
                        "ok": False,
                        "failure_class": failure,
                        "next_action": minted.get("next_action")
                        or "The session mint failed. A describe 200 is not a login.",
                        "bucket": bucket,
                        "scope": scope,
                        "collection": collection,
                        "authenticated_bucket": buckets.get("authenticated_bucket"),
                        "prereq_bucket": buckets.get("prereq_bucket"),
                        "request_buckets": buckets.get("request_buckets") or [],
                        "steps": steps,
                        "readiness": ready,
                    }
                headers["X-Zeus-Session"] = sid
                headers.pop("Authorization", None)
                auth = None
            r = client.post(url, json=body, auth=auth, headers=headers)
            status = r.status_code
            req_id = r.headers.get("X-Zeus-Req-Id") or r.headers.get("x-zeus-req-id") or ""
            preview = (r.text or "")[:400]
            if sid and sid in preview:
                preview = preview.replace(sid, "[REDACTED]")
            if status >= 400:
                err = preview
    except httpx.RequestError as e:
        steps.append(
            {
                "name": "describe",
                "ok": False,
                "url": url,
                "error": str(e),
                "failure_class": "network_timeout",
            }
        )
        return {
            "ok": False,
            "failure_class": "network_timeout",
            "next_action": "Check ZEUS_URL / network; ensure Zeus is up",
            "bucket": bucket,
            "scope": scope,
            "authenticated_bucket": buckets.get("authenticated_bucket"),
            "prereq_bucket": buckets.get("prereq_bucket"),
            "request_buckets": buckets.get("request_buckets") or [],
            "steps": steps,
            "readiness": ready,
        }

    describe_ok = 200 <= status < 300
    steps.append(
        {
            "name": "describe",
            "ok": describe_ok,
            "url": url,
            "status": status,
            "req_id": req_id or None,
            "body_preview": preview if not describe_ok else preview[:200],
            "failure_class": (
                None
                if describe_ok
                else (
                    "auth_failed"
                    if status == 401
                    else "scope_not_enabled"
                    if status == 404
                    else "dispatch_failed"
                )
            ),
        }
    )

    ok = describe_ok and ready.get("overall") in ("pass", "unknown")
    # Allow ready unknown if describe works
    if describe_ok and ready.get("overall") != "fail":
        ok = True
    if ready.get("overall") == "fail" and not describe_ok:
        ok = False

    failure = None
    next_action = "Zeus smoke green — proceed to smoke_test_agent"
    if not describe_ok:
        failure = steps[-1].get("failure_class") or "dispatch_failed"
        next_action = (
            "Fix describe failure (auth/scope/enablement); see errors.md; hand ops req_id if present"
        )
    elif ready.get("overall") == "fail":
        failure = ready.get("primary_failure_class")
        next_action = ready.get("next_action") or "Fix readiness gates then re-smoke"

    if update_checklist:
        try:
            if ok:
                set_item_status(cfg, "5.1", "done", evidence=f"describe ok req_id={req_id or 'n/a'}")
            else:
                set_item_status(cfg, "5.1", "blocked", evidence=f"status={status} req_id={req_id}")
        except Exception:  # noqa: BLE001
            pass

    if ok:
        try:
            from zeus_dev_helper_mcp.handoff import record_metric

            record_metric(cfg, "smoke_test_zeus_ok")
        except Exception:  # noqa: BLE001
            pass

    return {
        "ok": ok,
        "failure_class": failure,
        "next_action": next_action,
        "bucket": bucket,
        "scope": scope,
        "collection": collection,
        "authenticated_bucket": buckets.get("authenticated_bucket"),
        "prereq_bucket": buckets.get("prereq_bucket"),
        "request_buckets": buckets.get("request_buckets") or [],
        "req_id": req_id or None,
        "steps": steps,
        "docs": {
            "errors": docs_url("zeus-client/errors.md"),
            "probes": docs_url("zeus/developers/api/probes.md"),
        },
    }


def _turn_hops(result: Any) -> list[dict[str, Any]]:
    debug = getattr(result, "debug", None)
    raw: list[Any] = list(getattr(debug, "hops", ()) or ())
    if not raw:
        raw = list(getattr(result, "tool_trail", ()) or ())
    hops: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        hops.append(
            {
                "name": item.get("name") or item.get("verb") or item.get("tool"),
                "status": item.get("status"),
                "req_id": item.get("req_id") or item.get("zeus_req_id"),
            }
        )
        if len(hops) >= 20:
            break
    return hops


def _pip_agent_next_action() -> str:
    return (
        "pip install 'kotenai-zeus-client>=2.3.0' (or zeus-dev-helper-mcp[agent]) "
        "and configure LLM + Zeus, then retry smoke_test_agent"
    )


def _agent_docs() -> dict[str, str]:
    return {
        "using": docs_url("zeus-client/using-zeus-client.md"),
        "recipe_01": docs_url("zeus-client/recipes/01-minimal-qa.md"),
        "errors": docs_url("zeus-client/errors.md"),
    }


def client_floor_for_catalog(body: Any) -> str | None:
    """Floor required by ``_lineage.base_id``, or None when the stamp has none."""
    try:
        from zeus_client.domain.catalog import lineage_base_id
        from zeus_client.domain.floor import floor_required_for_base_id
    except ImportError:
        return None
    base_id = lineage_base_id(body if isinstance(body, dict) else None)
    if not base_id:
        return None
    floor = floor_required_for_base_id(base_id).strip()
    return floor or None


def stamped_catalog_floor(
    *,
    root: str | Path | None,
    mode: str | None = None,
    bucket: str | None = None,
    scope: str | None = None,
) -> str | None:
    """Read the catalog ``smoke_test_agent`` will load and return its floor."""
    if not root:
        return None
    try:
        from zeus_client.domain.catalog import resolve_catalog_path
    except ImportError:
        return None
    path = resolve_catalog_path(
        mode=(mode or "analytics").strip() or "analytics",
        bucket=(bucket or "").strip() or None,
        scope=(scope or "").strip() or None,
        user_dir=Path(root),
    )
    if path is None:
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return client_floor_for_catalog(raw)


def apply_smoke_client_floor(mapping: dict[str, Any], cfg: HelperConfig) -> str | None:
    """Set ``mapping['client_floor']`` from the on-disk stamp. Scaffold stays unset."""
    target = mapping.get("target") if isinstance(mapping.get("target"), dict) else {}
    settings = mapping.get("settings") if isinstance(mapping.get("settings"), dict) else {}
    root = mapping.get("chat_requests_dir") or (
        str(cfg.chat_request_dir) if cfg.chat_request_dir else None
    )
    floor = stamped_catalog_floor(
        root=root,
        mode=str(settings.get("mode") or cfg.default_mode or "analytics"),
        bucket=str(target.get("bucket") or cfg.default_bucket or ""),
        scope=str(target.get("scope") or cfg.default_scope or ""),
    )
    if floor:
        mapping["client_floor"] = floor
    return floor


def pin_runtime_client_floor(rt: Any) -> str | None:
    """Point ``rt.config.client_floor`` at the catalog now on disk.

    ``RuntimeConfig`` is frozen. A stamp that arrives in ``catalog.sync`` is
    visible only after the config object is replaced.
    """
    catalog = getattr(getattr(rt, "services", None), "catalog", None)
    root = getattr(catalog, "root", None) or getattr(rt.config, "chat_requests_dir", None)
    target = rt.config.target
    settings = rt.config.settings
    floor = stamped_catalog_floor(
        root=root,
        mode=getattr(settings, "mode", None) or "analytics",
        bucket=getattr(target, "bucket", None),
        scope=getattr(target, "scope", None),
    )
    if not floor or floor == rt.config.client_floor:
        return floor
    rt.config = replace(rt.config, client_floor=floor)
    return floor


def _docker_guidance_for_agent(cfg: HelperConfig) -> dict[str, Any] | None:
    """Guide-only: travel sample with Docker install docs → prefer compose guidance."""
    try:
        from zeus_dev_helper_mcp.travel import resolve_travel_docker_guidance

        return resolve_travel_docker_guidance(cfg)
    except Exception:  # noqa: BLE001
        return None


def smoke_test_agent(
    cfg: HelperConfig,
    *,
    question: str = "In one short sentence, what data is available in this scope?",
    update_checklist: bool = True,
) -> dict[str, Any]:
    """One ZeusRuntime run_turn if kotenai-zeus-client >= 2.3.0 is installed.

    When the client package is missing and demo_travel_sample documents Docker install,
    return guide-only Docker compose next_action instead of only pip install.
    """
    try:
        import asyncio

        from zeus_client import ClientSettings, ZeusRuntime
        from zeus_client.adapters.catalog_fs.store import FsCatalogStore
        from zeus_client.adapters.llm_openai_compatible import OpenAICompatibleLlmClient
        from zeus_client.adapters.secrets_env.store import EnvSecretStore
        from zeus_client.adapters.zeus_http import HttpxZeusPort
        from zeus_client.adapters.zeus_http.catalog_remote import HttpxCatalogRemote
        from zeus_client.config.loader import config_from_mapping
    except ImportError:
        docker = _docker_guidance_for_agent(cfg)
        if docker:
            return {
                "ok": False,
                "failure_class": None,
                "implemented": True,
                "install_path": "docker",
                "sample": docker.get("sample") or "travel",
                "local_dir": docker.get("local_dir"),
                "docker": {
                    "has_compose": docker.get("has_compose"),
                    "has_dockerfile": docker.get("has_dockerfile"),
                    "readme_signals": docker.get("readme_signals"),
                    "recommended": docker.get("recommended"),
                    "host_port": docker.get("host_port"),
                    "compose_file": docker.get("compose_file"),
                },
                "next_action": docker.get("next_action") or _pip_agent_next_action(),
                "docs": _agent_docs(),
            }
        return {
            "ok": False,
            "failure_class": None,
            "implemented": True,
            "install_path": "pip",
            "next_action": _pip_agent_next_action(),
            "docs": _agent_docs(),
        }

    from zeus_dev_helper_mcp.config import llm_key_in_process_env

    if not llm_key_in_process_env():
        docker = _docker_guidance_for_agent(cfg)
        next_action = (
            "Set LLM_API_KEY, XAI_API_KEY, or OPENAI_API_KEY in this process "
            "before smoke_test_agent. A stored has_llm_key flag is not the key. "
            "In the app, put the secret in .env and leave llm.api_key_env as that name."
        )
        out: dict[str, Any] = {
            "ok": False,
            "failure_class": "llm_key_missing",
            "next_action": next_action,
            "docs": _agent_docs(),
        }
        if docker:
            out["install_path"] = "docker"
            out["sample"] = docker.get("sample") or "travel"
            out["local_dir"] = docker.get("local_dir")
            out["docker"] = {
                "has_compose": docker.get("has_compose"),
                "has_dockerfile": docker.get("has_dockerfile"),
                "readme_signals": docker.get("readme_signals"),
                "recommended": docker.get("recommended"),
                "host_port": docker.get("host_port"),
            }
            out["next_action"] = (
                f"{next_action}. Alternate (demo_travel_sample Docker path): "
                f"{docker.get('next_action')}"
            )
        return out

    base = _base(cfg)
    if not base:
        return {
            "ok": False,
            "next_action": "Set ZEUS_URL before smoke_test_agent",
        }
    if ":9091" in base:
        return {
            "ok": False,
            "failure_class": "wrong_port_hub_vs_public",
            "next_action": "Use public API :8080, not Hub :9091",
        }

    from zeus_dev_helper_mcp.scaffold import runtime_config_dict

    mapping = runtime_config_dict(cfg)
    if not mapping["target"].get("bucket") or not mapping["target"].get("scope"):
        return {
            "ok": False,
            "failure_class": "scope_not_enabled",
            "next_action": "Set ZEUS_BUCKET/ZEUS_SCOPE or client target in config.json",
        }
    apply_smoke_client_floor(mapping, cfg)

    secrets_override = None
    if _auth_mode(cfg) == "basic":
        minted, sid = take_scope_session(cfg)
        if not minted.get("ok") or not sid:
            return {
                "ok": False,
                "failure_class": str(minted.get("failure_class") or "auth_failed"),
                "next_action": minted.get("next_action")
                or "The session mint failed. A describe 200 is not a login.",
                "docs": _agent_docs(),
            }
        mapping["zeus"] = _use_scope_session(mapping["zeus"])
        secrets_override = _SmokeSessionStore(sid)

    async def _run() -> dict[str, Any]:
        rt_cfg = config_from_mapping(mapping)
        secrets = secrets_override or EnvSecretStore()
        catalog = None
        chat_dir = rt_cfg.chat_requests_dir or (
            str(cfg.chat_request_dir) if cfg.chat_request_dir else None
        )
        if chat_dir:
            catalog = FsCatalogStore(root=chat_dir)
        async with ZeusRuntime(rt_cfg, secrets=secrets, catalog=catalog) as rt:
            rt.services.zeus = HttpxZeusPort(
                endpoint=rt.config.zeus, secrets=secrets, journal=rt.journal
            )
            rt.services.llm = OpenAICompatibleLlmClient(
                config=rt.config.llm, secrets=secrets, journal=rt.journal
            )
            if rt.services.catalog_remote is None:
                rt.services.catalog_remote = HttpxCatalogRemote(
                    endpoint=rt.config.zeus, secrets=secrets
                )

            synced = 0
            sync_err = None
            chat_request = None
            pin_runtime_client_floor(rt)
            try:
                loaded = await rt.catalog.load(mode=rt.config.settings.mode)
                chat_request = dict(loaded.body)
            except Exception as e:  # noqa: BLE001
                try:
                    sync_result = await rt.catalog.sync()
                    synced = len(getattr(sync_result, "synced", None) or [])
                    pin_runtime_client_floor(rt)
                    loaded = await rt.catalog.load(mode=rt.config.settings.mode)
                    chat_request = dict(loaded.body)
                except Exception as sync_exc:  # noqa: BLE001
                    sync_err = f"{e}; {sync_exc}"

            result = await rt.agent.run_turn(
                question,
                settings=ClientSettings(
                    ai_process_result=False,
                    mode=rt.config.settings.mode,
                ),
                chat_request=chat_request,
            )
            debug = result.debug
            hops = _turn_hops(result)
            n_tools = len(hops)
            req_ids = [str(x) for x in (getattr(debug, "req_ids", ()) or ()) if x]
            if not req_ids:
                req_ids = [h["req_id"] for h in hops if h.get("req_id")]
            pref = getattr(debug, "preferred_req_id", None)
            if pref and pref not in req_ids:
                req_ids.insert(0, str(pref))
            session = result.session
            sid = getattr(session, "session_id", None) or getattr(debug, "session_id", None)
            round_n = getattr(session, "round", None)
            if round_n is None:
                round_n = getattr(debug, "rounds", None)
            notes = list(getattr(debug, "notes", ()) or ())
            answer = result.answer or ""
            status = str(getattr(result.status, "value", result.status)).lower()
            grounded = n_tools > 0
            ok = bool(answer) and grounded and status in ("ok", "clarify")
            if result.error is not None:
                ok = False
            failure = None
            next_action = "Agent smoke green — log session_id and continue customize checklist"
            if result.error is not None:
                failure = "dispatch_failed"
                err = result.error
                next_action = (
                    f"Turn error {getattr(err, 'code', '')}: "
                    f"{getattr(err, 'message', err)} — diagnose_error"
                )
            elif not grounded:
                failure = "empty_tool_catalog"
                next_action = (
                    "No Zeus hops — check stamped catalog, mode, contract bind, scope enablement"
                )
            elif not answer:
                failure = failure or "dispatch_failed"
                next_action = "Empty answer — inspect TurnResult.debug.notes and LLM config"
            elif status not in ("ok", "clarify"):
                failure = "dispatch_failed"
                next_action = f"Turn status {status!r} — inspect debug hops / notes"
            return {
                "ok": ok,
                "failure_class": failure,
                "next_action": next_action,
                "answer_preview": answer[:500],
                "status": status,
                "session_id": sid,
                "turn_id": getattr(debug, "turn_id", None) or None,
                "chat_id": getattr(debug, "chat_id", None) or None,
                "round": round_n,
                "tool_call_count": n_tools,
                "req_ids": req_ids[:5],
                "hops": hops,
                "notes_preview": [str(n)[:200] for n in notes][:5],
                "bucket": rt.config.target.bucket,
                "scope": rt.config.target.scope,
                "mode": rt.config.settings.mode,
                "catalogs_synced": synced,
                "sync_err": sync_err,
            }

    try:
        result = asyncio.run(_run())
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        failure = "dispatch_failed"
        low = msg.lower()
        if "401" in low or "auth" in low:
            failure = "auth_failed"
        elif "409" in low or "drift" in low:
            failure = "hash_drift"
        elif "timeout" in low:
            failure = "network_timeout"
        elif "api_key" in low or "llm" in low:
            failure = "llm_key_missing"
        result = {
            "ok": False,
            "failure_class": failure,
            "error": msg[:800],
            "next_action": "diagnose_error with the message; fix config; see using-zeus-client.md",
        }

    if update_checklist:
        try:
            if result.get("ok"):
                set_item_status(
                    cfg,
                    "5.2",
                    "done",
                    evidence=f"session_id={result.get('session_id')} tools={result.get('tool_call_count')}",
                )
            else:
                set_item_status(
                    cfg,
                    "5.2",
                    "blocked",
                    evidence=result.get("failure_class") or result.get("error") or "agent smoke failed",
                )
        except Exception:  # noqa: BLE001
            pass

    if result.get("ok"):
        try:
            from zeus_dev_helper_mcp.handoff import record_metric

            record_metric(cfg, "smoke_test_agent_ok")
        except Exception:  # noqa: BLE001
            pass
        try:
            cfg.state_dir.mkdir(parents=True, exist_ok=True)
            artifact = {
                "session_id": result.get("session_id"),
                "turn_id": result.get("turn_id"),
                "chat_id": result.get("chat_id"),
                "req_ids": result.get("req_ids") or [],
                "hops": result.get("hops") or [],
                "bucket": result.get("bucket"),
                "scope": result.get("scope"),
                "mode": result.get("mode"),
            }
            (cfg.state_dir / "last_smoke_agent.json").write_text(
                json.dumps(artifact) + "\n", encoding="utf-8"
            )
        except Exception:  # noqa: BLE001
            pass

    result["docs"] = {
        "using": docs_url("zeus-client/using-zeus-client.md"),
        "errors": docs_url("zeus-client/errors.md"),
        "recipe_01": docs_url("zeus-client/recipes/01-minimal-qa.md"),
    }
    return result
