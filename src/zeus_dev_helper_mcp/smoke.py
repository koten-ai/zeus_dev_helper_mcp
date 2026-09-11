"""Smoke tests for Zeus and Zeus Client agent loop (ZDH-7)."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urljoin

import httpx

from zeus_dev_helper_mcp.checklist import set_item_status
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.readiness import run_readiness_check
from zeus_dev_helper_mcp.docs_links import docs_url


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

    # Scope-level describe (V2)
    url = describe_scope_url(cfg) or f"{base}/v2/{bucket}/{scope}/describe"
    body: dict[str, Any] = {}  # server defaults
    status = 0
    req_id = ""
    err = None
    preview = ""
    try:
        with httpx.Client(timeout=httpx.Timeout(30.0, connect=5.0), headers=_headers()) as client:
            r = client.post(url, json=body, auth=_auth(cfg))
            status = r.status_code
            req_id = r.headers.get("X-Zeus-Req-Id") or r.headers.get("x-zeus-req-id") or ""
            preview = (r.text or "")[:400]
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


def smoke_test_agent(
    cfg: HelperConfig,
    *,
    question: str = "In one short sentence, what data is available in this scope?",
    update_checklist: bool = True,
) -> dict[str, Any]:
    """One ZeusRuntime run_turn if kotenai-zeus-client >= 2.3.0 is installed."""
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
        return {
            "ok": False,
            "failure_class": None,
            "implemented": True,
            "next_action": (
                "pip install 'kotenai-zeus-client>=2.3.0' (or zeus-dev-helper-mcp[agent]) "
                "and configure LLM + Zeus, then retry smoke_test_agent"
            ),
            "docs": {
                "using": docs_url("zeus-client/using-zeus-client.md"),
                "recipe_01": docs_url("zeus-client/recipes/01-minimal-qa.md"),
            },
        }

    if not cfg.has_llm_key and not any(
        os.environ.get(k) for k in ("LLM_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY")
    ):
        return {
            "ok": False,
            "failure_class": "llm_key_missing",
            "next_action": "Set LLM_API_KEY (or provider key) for the agent smoke",
        }

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

    async def _run() -> dict[str, Any]:
        rt_cfg = config_from_mapping(mapping)
        secrets = EnvSecretStore()
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
            try:
                loaded = await rt.catalog.load(mode=rt.config.settings.mode)
                chat_request = dict(loaded.body)
            except Exception as e:  # noqa: BLE001
                try:
                    sync_result = await rt.catalog.sync()
                    synced = len(getattr(sync_result, "synced", None) or [])
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
