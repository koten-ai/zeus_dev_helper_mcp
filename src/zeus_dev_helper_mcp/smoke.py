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


def _auth(cfg: HelperConfig) -> tuple[str, str] | None:
    user = (os.environ.get("ZEUS_USERNAME") or os.environ.get("ZEUS_USER") or "").strip()
    password = (os.environ.get("ZEUS_PASSWORD") or "").strip()
    if user and password:
        return user, password
    return None


def _headers() -> dict[str, str]:
    h = {"User-Agent": "zeus-dev-helper-mcp", "Accept": "application/json", "Content-Type": "application/json"}
    token = (os.environ.get("ZEUS_BEARER_TOKEN") or os.environ.get("ZEUS_TOKEN") or "").strip()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


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
    url = f"{base}/v2/{bucket}/{scope}/describe"
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


def smoke_test_agent(
    cfg: HelperConfig,
    *,
    question: str = "In one short sentence, what data is available in this scope?",
    update_checklist: bool = True,
) -> dict[str, Any]:
    """One Zeus Client run_agent turn if kotenai-zeus-client is installed."""
    # Prefer optional dependency
    try:
        import asyncio

        from zeus_client import (  # type: ignore
            ZeusClient,
            load_config,
            resolve_llm_provider_config,
            resolve_zeus_config,
            run_agent,
            sync_chat_requests,
        )
    except ImportError:
        return {
            "ok": False,
            "failure_class": None,
            "implemented": True,
            "next_action": (
                "pip install kotenai-zeus-client and configure LLM + Zeus, "
                "then retry smoke_test_agent"
            ),
            "docs": {
                "using": (
                    docs_url("zeus-client/using-zeus-client.md")
                ),
                "recipe_01": (
                    docs_url("zeus-client/recipes/01-minimal-qa.md")
                ),
            },
        }

    if not cfg.has_llm_key and not (
        os.environ.get("LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("XAI_API_KEY")
    ):
        # re-check env directly — has_llm_key may be stale presence flag
        if not any(
            os.environ.get(k)
            for k in ("LLM_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY")
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

    async def _run() -> dict[str, Any]:
        async with ZeusClient():
            zcfg_file = await load_config()
            # Override URL from helper config when set
            if base:
                zcfg_file.setdefault("zeus", {})
                if isinstance(zcfg_file["zeus"], dict):
                    zcfg_file["zeus"]["url"] = base
            zcfg = resolve_zeus_config(zcfg_file)
            provider = resolve_llm_provider_config(zcfg_file)
            try:
                sync_result = await sync_chat_requests(zcfg_file)
                synced = len(getattr(sync_result, "synced", None) or [])
            except Exception as e:  # noqa: BLE001
                synced = 0
                sync_err = str(e)
            else:
                sync_err = None

            bucket = cfg.default_bucket
            scope = cfg.default_scope
            collection = cfg.default_collection or "_default"
            if not bucket or not scope:
                # try sample from client config
                samples = zcfg_file.get("samples") or {}
                key = zcfg_file.get("default_sample")
                sample = samples.get(key) if key else None
                if isinstance(sample, dict):
                    bucket = sample.get("bucket") or bucket
                    scope = sample.get("scope") or scope
                    collection = sample.get("collection") or collection
            if not bucket or not scope:
                return {
                    "ok": False,
                    "failure_class": "scope_not_enabled",
                    "next_action": "Set ZEUS_BUCKET/ZEUS_SCOPE or client samples",
                    "sync_err": sync_err,
                }

            api_version = zcfg_file.get("default_api_version", "v2")
            mode = cfg.default_mode or zcfg_file.get("default_mode", "analytics")
            models = provider.get("models") or ["unknown"]
            answer, trace, turns, session_meta = await run_agent(
                zcfg["url"],
                zcfg,
                provider["base_url"],
                provider["api_key"],
                models[0],
                api_version,
                mode,
                bucket,
                scope,
                collection,
                question,
                prior_turns=[],
            )
            tool_calls = (trace or {}).get("tool_calls") or []
            notes = (trace or {}).get("notes") or []
            # count tool activity
            n_tools = len(tool_calls) if isinstance(tool_calls, list) else 0
            sid = (session_meta or {}).get("session_id")
            # req_id from tool calls if present
            req_ids = []
            if isinstance(tool_calls, list):
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        rid = tc.get("req_id") or tc.get("zeus_req_id")
                        if rid:
                            req_ids.append(rid)

            grounded = n_tools > 0
            ok = bool(answer) and grounded
            failure = None
            next_action = "Agent smoke green — log session_id and continue customize checklist"
            if not grounded:
                failure = "empty_tool_catalog"
                next_action = (
                    "No Zeus tool calls — check stamped catalog, mode, contract bind, scope enablement"
                )
            if not answer:
                failure = failure or "dispatch_failed"
                next_action = "Empty answer — inspect trace notes and LLM config"

            return {
                "ok": ok,
                "failure_class": failure,
                "next_action": next_action,
                "answer_preview": (answer or "")[:500],
                "session_id": sid,
                "round": (session_meta or {}).get("round"),
                "tool_call_count": n_tools,
                "req_ids": req_ids[:5],
                "notes_preview": [str(n)[:200] for n in (notes if isinstance(notes, list) else [])][:5],
                "bucket": bucket,
                "scope": scope,
                "mode": mode,
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

    result["docs"] = {
        "using": docs_url("zeus-client/using-zeus-client.md"),
        "errors": docs_url("zeus-client/errors.md"),
        "recipe_01": docs_url("zeus-client/recipes/01-minimal-qa.md"),
    }
    return result
