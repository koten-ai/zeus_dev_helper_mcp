"""Policy / hooks recipes (ZDH-27). Snippets only — not a policy engine."""

from __future__ import annotations

from typing import Any

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.docs_links import docs_url

# ZeusRuntime 2.3 middleware is before_zeus / after_zeus.
# V1 AgentHooks.before_zeus_dispatch lives under zeus_client.compat.v1 — do not execute here.
_RECIPES: dict[str, dict[str, str]] = {
    "tenant_pin": {
        "title": "Pin tenant (bucket/scope) on every Zeus hop",
        "summary": "Force tool args onto the bound tenant. Do not let the model pick another scope.",
        "snippet": '''class TenantPin:
    name, critical = "tenant_pin", True
    def __init__(self, bucket: str, scope: str):
        self.bucket, self.scope = bucket, scope
    async def before_zeus(self, ctx, name, args):
        out = dict(args)
        out["bucket"] = self.bucket
        out["scope"] = self.scope
        return out
# Wire: ZeusRuntime(..., middleware=[TenantPin("travel-sample", "inventory"), ...])
# V1 equivalent: AgentHooks.before_zeus_dispatch — compat only, not the 2.3 default.
''',
    },
    "deny_pipeline_direct": {
        "title": "Deny pipeline on Direct",
        "summary": "pipeline is not on rt.data.verb. Refuse it in middleware if the model still asks.",
        "snippet": '''class DenyPipelineOnDirect:
    name, critical = "deny_pipeline_direct", True
    async def before_zeus(self, ctx, name, args):
        if name in ("pipeline", "pipeline.plan"):
            denied = list(ctx.data.get("denied_verbs") or [])
            denied.append(name)
            ctx.data["denied_verbs"] = denied
            raise PermissionError("pipeline is not on Direct; use recommend_surface(intent=multi_step)")
        return args
''',
    },
    "output_schema_allowlist": {
        "title": "output_schema allowlist",
        "summary": "Card/UI fields only. Do not dump full Zeus documents into the LLM or the app.",
        "snippet": '''output_schema = {
    "entity_type": "Hotel",
    "fields": ["id", "name", "rating"],  # allowlist; id/doc_key/entity_type are reserved
}
# Runtime: pass on run_turn settings / catalog guidance.injections.output_schema
# (hash-excluded). Precedence: call arg > catalog injection > MINI-SCHEMA.
# Unknown fields are dropped — do not widen the list from model output.
''',
    },
    "never_promote_ocr": {
        "title": "Never promote OCR to system",
        "summary": "OCR / extracted document text is untrusted. Keep it off the system prompt.",
        "snippet": '''class NeverPromoteOcr:
    name, critical = "never_promote_ocr", True
    async def before_llm(self, ctx, messages):
        for m in messages:
            if m.get("role") != "system":
                continue
            text = m.get("content") or ""
            if "OCR" in text or "ocr_text" in text.lower():
                raise PermissionError("never promote OCR / extracted document text to system")
        return None
# Put OCR on a user or tool message, not instructions/system.
''',
    },
}


def suggest_hooks(cfg: HelperConfig, *, recipe: str = "") -> dict[str, Any]:
    """Return middleware snippets. Does not install or run hooks."""
    _ = cfg
    key = (recipe or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "tenant": "tenant_pin",
        "pin": "tenant_pin",
        "pipeline": "deny_pipeline_direct",
        "direct": "deny_pipeline_direct",
        "schema": "output_schema_allowlist",
        "output_schema": "output_schema_allowlist",
        "allowlist": "output_schema_allowlist",
        "ocr": "never_promote_ocr",
        "system": "never_promote_ocr",
    }
    key = aliases.get(key, key)
    names = list(_RECIPES)
    selected = names if not key else ([key] if key in _RECIPES else [])
    if key and not selected:
        return {
            "ok": False,
            "executed": False,
            "known_recipes": names,
            "next_action": "Pass recipe=tenant_pin|deny_pipeline_direct|output_schema_allowlist|never_promote_ocr",
            "docs": docs_url("zeus-client/using-zeus-client.md"),
        }
    recipes = []
    for n in selected:
        row = _RECIPES[n]
        recipes.append(
            {
                "id": n,
                "title": row["title"],
                "summary": row["summary"],
                "snippet": row["snippet"].strip() + "\n",
            }
        )
    return {
        "ok": True,
        "executed": False,
        "note": (
            "Snippets only — Helper is not a policy engine and does not run "
            "before_zeus / before_zeus_dispatch."
        ),
        "runtime": "ZeusRuntime middleware (before_zeus). V1 AgentHooks is zeus_client.compat.v1.",
        "recipes": recipes,
        "docs": {
            "using": docs_url("zeus-client/using-zeus-client.md"),
            "hooks": docs_url("zeus-client/glossary.md#agent_hooks"),
        },
        "next_action": "Copy a snippet into the app middleware; do not execute policy in this MCP",
    }
