"""Req-id policy, Detective URL templates, redacted support packs (ZDH-23)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.diagnose import _detective_links
from zeus_dev_helper_mcp.docs_links import docs_url

SMOKE_ARTIFACT = "last_smoke_agent.json"
_SECRET_KEY = re.compile(
    r"(password|secret|token|api[_-]?key|authorization|bearer|prompt|messages|body|result_json)",
    re.IGNORECASE,
)
_DROP_KEYS = frozenset(
    {
        "password",
        "token",
        "api_key",
        "authorization",
        "prompt",
        "messages",
        "body",
        "result",
        "arguments",
        "args",
        "snippet",
        "content",
        "journal",
    }
)


def explain_req_id_policy(cfg: HelperConfig) -> dict[str, Any]:
    """One opaque UUID per HTTP hop. Never composite hop ids. Never Rewind /turn."""
    _ = cfg
    return {
        "ok": True,
        "rules": [
            "One hop = one X-Zeus-Req-Id (opaque UUID v4 preferred)",
            "Never composite hop ids (base:1, search:2, uuid:2) — Zeus 0.7+ returns 400 invalid_req_id",
            "Group hops with X-Zeus-Chat-Id (conversation) and X-Zeus-Turn-Id (one user gesture)",
            "Open Detective/Rewind on the tool hop, never POST /v2/session/{id}/turn",
            "Do not reuse X-Zeus-Req-Id across hops",
        ],
        "do_not": [
            "Do not send X-Zeus-Req-Id: base:1",
            "Do not Rewind /v2/session/{id}/turn",
            "Do not scrape Hub Detective payloads",
        ],
        "docs": {
            "errors": docs_url("zeus-client/errors.md"),
            "req_id_policy": docs_url("zeus-client/errors.md"),
        },
        "next_action": "diagnose_error on 400 invalid_req_id; detective_links(req_id=...) for URL templates only",
    }


def detective_links(
    cfg: HelperConfig,
    *,
    req_id: str = "",
    chat_id: str = "",
    zeus_url: str = "",
) -> dict[str, Any]:
    """Hub Detective URL templates only — never fetched."""
    url = (zeus_url or cfg.zeus_url or "").strip()
    links = _detective_links(zeus_url=url, req_id=(req_id or "").strip(), chat_id=(chat_id or "").strip())
    return {
        "ok": bool(links),
        "links": links or {},
        "note": "URL templates only — Helper does not scrape Hub/Detective/Rewind.",
        "do_not": [
            "Do not Rewind POST /v2/session/{id}/turn",
            "Do not fetch these URLs from the Helper",
        ],
        "next_action": (
            "Open the tool hop /hub/debug/req/<id> (not the session turn)"
            if links
            else "Pass req_id and/or chat_id"
        ),
        "docs": docs_url("zeus-client/errors.md"),
    }


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if lk in _DROP_KEYS or _SECRET_KEY.search(str(k)):
                continue
            out[k] = _redact(v)
        return out
    if isinstance(obj, list):
        return [_redact(x) for x in obj[:40]]
    if isinstance(obj, str) and len(obj) > 400:
        return obj[:200] + "…"
    return obj


def _ids_from(doc: dict[str, Any]) -> dict[str, Any]:
    hops_in = doc.get("hops") or doc.get("tool_calls") or []
    hops: list[dict[str, Any]] = []
    if isinstance(hops_in, list):
        for h in hops_in[:20]:
            if not isinstance(h, dict):
                continue
            hops.append(
                {
                    "name": h.get("name") or h.get("verb") or h.get("tool"),
                    "status": h.get("status"),
                    "req_id": h.get("req_id") or h.get("zeus_req_id"),
                    "path_class": h.get("path_class"),
                }
            )
    req_ids = doc.get("req_ids") or []
    if not isinstance(req_ids, list):
        req_ids = [req_ids] if req_ids else []
    preferred = doc.get("preferred_req_id") or (req_ids[0] if req_ids else None)
    if not preferred and hops:
        preferred = hops[0].get("req_id")
    session = doc.get("session")
    session_id = doc.get("session_id")
    if not session_id and isinstance(session, dict):
        session_id = session.get("id") or session.get("session_id")
    target = doc.get("target")
    target_out: Any = target
    if isinstance(target, dict):
        target_out = {
            "bucket": target.get("bucket"),
            "scope": target.get("scope"),
            "collection": target.get("collection"),
        }
    return {
        "chat_id": doc.get("chat_id"),
        "turn_id": doc.get("turn_id"),
        "session_id": session_id,
        "req_ids": [str(x) for x in req_ids if x][:10],
        "preferred_req_id": preferred,
        "hops": hops,
        "zeus_url": doc.get("zeus_url"),
        "target": target_out,
    }


def _markdown(ids: dict[str, Any], links: dict[str, str]) -> str:
    lines = [
        "# Zeus support pack (ids + hops only)",
        "",
        f"- chat_id: {ids.get('chat_id') or '—'}",
        f"- turn_id: {ids.get('turn_id') or '—'}",
        f"- session_id: {ids.get('session_id') or '—'}",
        f"- preferred_req_id: {ids.get('preferred_req_id') or '—'}",
        f"- req_ids: {', '.join(ids.get('req_ids') or []) or '—'}",
        "",
        "## Hops (name / status / req_id)",
    ]
    hops = ids.get("hops") or []
    if not hops:
        lines.append("- (none)")
    for h in hops:
        lines.append(
            f"- {h.get('name') or '?'} status={h.get('status') or '—'} req_id={h.get('req_id') or '—'}"
        )
    lines.extend(["", "## Detective (URL templates, not fetched)"])
    if links:
        for k, v in links.items():
            lines.append(f"- {k}: {v}")
    else:
        lines.append("- (pass req_id or chat_id)")
    lines.extend(
        [
            "",
            "Do not attach tool bodies, prompts, tokens, or journal dumps.",
            "Do not Rewind POST /v2/session/{id}/turn — open the tool hop.",
        ]
    )
    return "\n".join(lines) + "\n"


def _load_debug(*, debug_json: str, path: str, state_dir: Path) -> tuple[dict[str, Any] | None, str | None]:
    raw = (debug_json or "").strip()
    if path:
        p = Path(path).expanduser()
        if not p.is_file():
            return None, f"file not found: {p}"
        raw = p.read_text(encoding="utf-8")
    if not raw:
        art = state_dir / SMOKE_ARTIFACT
        if art.is_file():
            raw = art.read_text(encoding="utf-8")
        else:
            return None, "pass debug_json= or path=, or run smoke_test_agent to write last_smoke_agent.json"
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"invalid JSON: {e}"
    if not isinstance(doc, dict):
        return None, "debug JSON must be an object"
    # Nested TurnResult.debug
    if isinstance(doc.get("debug"), dict):
        inner = dict(doc["debug"])
        for k in ("session_id", "chat_id", "turn_id"):
            if k in doc and k not in inner:
                inner[k] = doc[k]
        doc = inner
    return doc, None


def support_pack_from_turn(
    cfg: HelperConfig,
    *,
    debug_json: str = "",
    path: str = "",
    zeus_url: str = "",
) -> dict[str, Any]:
    """Markdown support pack from redacted debug JSON or last smoke artifact. No Hub fetch."""
    doc, err = _load_debug(debug_json=debug_json, path=path, state_dir=cfg.state_dir)
    if err:
        return {
            "ok": False,
            "next_action": err,
            "docs": docs_url("zeus-client/errors.md"),
        }
    assert doc is not None
    redacted = _redact(doc)
    ids = _ids_from(redacted if isinstance(redacted, dict) else {})
    url = (zeus_url or cfg.zeus_url or ids.get("zeus_url") or "") or ""
    req = str(ids.get("preferred_req_id") or ((ids.get("req_ids") or [None])[0] or ""))
    chat = str(ids.get("chat_id") or "")
    links = _detective_links(zeus_url=str(url), req_id=req, chat_id=chat) or {}
    md = _markdown(ids, links)
    return {
        "ok": True,
        "markdown": md,
        "ids": ids,
        "detective": links,
        "note": "Ids + hop names/statuses only. No Hub scrape, no journal/tool bodies/prompts.",
        "docs": docs_url("zeus-client/errors.md"),
        "next_action": "Paste markdown into the ticket; open Detective on the tool req_id",
    }
