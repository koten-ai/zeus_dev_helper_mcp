"""Catalog / contract coach (ZDH-22). Never stamps; never computes production hashes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from zeus_dev_helper_mcp.bootstrap import bootstrap_scope
from zeus_dev_helper_mcp.catalog import STAMP_WARNING
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.docs_links import docs_url

# Copied from kotenai-zeus-client domain.contract (stamped field only — no compute).
_PLACEHOLDER = "TO_BE_FILLED"
EXPECTED_FORMAT = "zeus.chat_request.v2"
HASH_EXCLUDED_ROOTS = ("guidance", "contract", "metadata", "_*")
HASH_EXCLUDED_MARKERS = ("## SCOPE BRIEF", "## MINI-SCHEMA")


def extract_stamped_hash(doc: Any) -> str:
    """Authoritative server hash from a stamped chat_request. Empty if placeholder/absent."""
    if not isinstance(doc, dict):
        return ""

    def _is_real(h: str) -> bool:
        hs = (h or "").strip()
        if not hs or _PLACEHOLDER in hs:
            return False
        return hs.lower() not in ("compute_local", "compute-local", "local")

    for candidate in (doc, doc.get("stamped_chat_request") or {}, doc.get("stamped") or {}):
        if not isinstance(candidate, dict):
            continue
        cb = candidate.get("contract") or {}
        if isinstance(cb, dict):
            h = str(cb.get("hash") or cb.get("_hash") or "").strip()
            if _is_real(h):
                return h
        for k in ("_hash", "hash"):
            h = str(candidate.get(k) or "").strip()
            if _is_real(h):
                return h
    return ""


def _load_doc(*, path: str = "", json_text: str = "") -> tuple[dict[str, Any] | None, str | None]:
    raw = (json_text or "").strip()
    if path and not raw:
        p = Path(path).expanduser()
        if not p.is_file():
            return None, f"file not found: {p}"
        raw = p.read_text(encoding="utf-8")
    if not raw:
        return None, "pass path= or json_text= with a chat_request JSON"
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"invalid JSON: {e}"
    if not isinstance(doc, dict):
        return None, "chat_request must be a JSON object"
    return doc, None


def _walk_placeholders(obj: Any, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            hits.extend(_walk_placeholders(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:50]):
            hits.extend(_walk_placeholders(v, f"{path}[{i}]"))
    elif isinstance(obj, str) and _PLACEHOLDER in obj:
        hits.append(path)
    return hits[:20]


def _issue(field: str, level: str, message: str, failure_class: str | None = None) -> dict[str, str]:
    out = {"field": field, "level": level, "message": message}
    if failure_class:
        out["failure_class"] = failure_class
    return out


def _try_client_extract(doc: dict[str, Any]) -> dict[str, Any] | None:
    """Optional wrap of client extract_stamped_hash. Never compute_contract_hash."""
    try:
        from zeus_client.domain.contract import extract_stamped_hash as client_extract
    except Exception:  # noqa: BLE001 — default extra must not require the SDK
        return None
    try:
        h = client_extract(doc) or ""
    except Exception as e:  # noqa: BLE001
        return {"source": "zeus_client.domain.contract.extract_stamped_hash", "error": str(e)[:200]}
    return {
        "source": "zeus_client.domain.contract.extract_stamped_hash",
        "stamped_hash_prefix": (h[:12] + "…") if len(h) > 12 else (h or None),
        "present": bool(h),
    }


def lint_chat_request(
    cfg: HelperConfig,
    *,
    path: str = "",
    json_text: str = "",
) -> dict[str, Any]:
    """Read-only catalog lint. Local subset always; optional client extract if [agent] installed."""
    _ = cfg
    doc, err = _load_doc(path=path, json_text=json_text)
    if err:
        return {
            "ok": False,
            "issues": [_issue("input", "error", err, "empty_tool_catalog")],
            "docs": docs_url("zeus-client/contracts-and-catalog.md"),
            "warning": STAMP_WARNING,
        }
    assert doc is not None
    issues: list[dict[str, str]] = []
    fmt = doc.get("_format")
    if fmt != EXPECTED_FORMAT:
        issues.append(
            _issue(
                "_format",
                "error" if not fmt else "warn",
                f"_format is {fmt!r}; expected {EXPECTED_FORMAT}",
                "empty_tool_catalog",
            )
        )
    verbs = doc.get("verbs") or doc.get("tools")
    if not isinstance(verbs, list) or not verbs:
        issues.append(
            _issue("verbs", "error", "missing or empty verbs[]", "empty_tool_catalog")
        )
    placeholders = _walk_placeholders(doc)
    if placeholders:
        issues.append(
            _issue(
                "TO_BE_FILLED",
                "error",
                f"placeholder {_PLACEHOLDER} at {', '.join(placeholders[:8])}",
                "contract_hash_invent_forbidden",
            )
        )
    stamped = extract_stamped_hash(doc)
    cb = doc.get("contract") if isinstance(doc.get("contract"), dict) else {}
    raw_hash = str((cb or {}).get("hash") or doc.get("_hash") or "")
    if raw_hash and _PLACEHOLDER in raw_hash:
        issues.append(
            _issue(
                "contract.hash",
                "error",
                "placeholder hash — stamp on Hub, never invent",
                "contract_hash_invent_forbidden",
            )
        )
    elif not stamped:
        issues.append(
            _issue(
                "contract.hash",
                "warn",
                "no stamped hash (template or unstamped). Production bind needs Hub stamp.",
                "contract_required",
            )
        )
    client_assist = _try_client_extract(doc)
    ok = not any(i.get("level") == "error" for i in issues)
    return {
        "ok": ok,
        "issues": issues,
        "format": fmt,
        "verb_count": len(verbs) if isinstance(verbs, list) else 0,
        "has_stamped_hash": bool(stamped),
        "client_assist": client_assist,
        "warning": STAMP_WARNING,
        "docs": docs_url("zeus-client/contracts-and-catalog.md"),
        "next_action": (
            "bind_contract after Hub stamp"
            if ok and stamped
            else "Fix issues; stamp on Hub — never compute_local for production"
        ),
    }


def bind_contract(
    cfg: HelperConfig,
    *,
    path: str = "",
    json_text: str = "",
    bucket: str = "",
    scope: str = "",
    mode: str = "",
) -> dict[str, Any]:
    """Extract stamped hash only. Refuse empty / TO_BE_FILLED / compute_local for prod."""
    doc, err = _load_doc(path=path, json_text=json_text)
    if err:
        return {
            "ok": False,
            "failure_class": "contract_required",
            "next_action": err,
            "docs": docs_url("zeus-client/contracts-and-catalog.md"),
        }
    assert doc is not None
    h = extract_stamped_hash(doc)
    if not h:
        return {
            "ok": False,
            "failure_class": "contract_hash_invent_forbidden",
            "next_action": (
                "No real stamped hash. Stamp on Hub / Workbench. "
                "Do not compute_local for production bind."
            ),
            "docs": docs_url("zeus-client/contracts-and-catalog.md"),
            "warning": STAMP_WARNING,
        }
    cb = doc.get("contract") if isinstance(doc.get("contract"), dict) else {}
    cid = str((cb or {}).get("id") or (cb or {}).get("contract_id") or doc.get("contract_id") or "") or None
    b = (bucket or cfg.default_bucket or "<bucket>").strip()
    s = (scope or cfg.default_scope or "<scope>").strip()
    m = (mode or cfg.default_mode or "analytics").strip()
    pin = {"contract_id": cid or "<contract_id from stamp>", "contract_hash": h}
    snippet = {
        "zeus": {
            "scope_contracts": {
                f"{b}/{s}": {m: pin},
            }
        }
    }
    return {
        "ok": True,
        "contract_id": cid,
        "contract_hash": h,
        "scope_key": f"{b}/{s}",
        "mode": m,
        "scope_contracts": snippet["zeus"]["scope_contracts"],
        "runtime_config_snippet": snippet,
        "note": "Copied from stamped fields only — Helper did not compute a hash.",
        "docs": docs_url("zeus-client/contracts-and-catalog.md"),
        "next_action": "Paste scope_contracts into RuntimeConfig / config.json; then smoke_test_agent",
    }


def explain_hash_boundary(cfg: HelperConfig) -> dict[str, Any]:
    """MINI-SCHEMA / brief are excluded from hash; injected at call time."""
    _ = cfg
    return {
        "ok": True,
        "excluded_roots": list(HASH_EXCLUDED_ROOTS),
        "excluded_string_markers": list(HASH_EXCLUDED_MARKERS),
        "summary": (
            "contract_hash fingerprints locked catalog rules (verbs, instructions, masq, …). "
            "guidance, contract stamp metadata, metadata, and _* keys are excluded. "
            "SCOPE BRIEF and MINI-SCHEMA suffixes are stripped from strings before hash — "
            "they are injected at call/session time and must not be baked into the stamp."
        ),
        "do_not": [
            "Do not compute production hashes locally (compute_local)",
            "Do not invent contract_hash",
            "Do not include live MINI-SCHEMA / brief in the stamped file expecting it to affect the hash",
        ],
        "docs": docs_url("zeus-client/contracts-and-catalog.md"),
        "next_action": "bind_contract from a Hub-stamped file; inject MINI-SCHEMA at runtime",
    }


def _hash_prefix(h: str) -> str | None:
    h = (h or "").strip()
    if not h:
        return None
    return h if len(h) <= 16 else h[:12] + "…"


def catalog_diff(
    cfg: HelperConfig,
    *,
    path: str = "",
    json_text: str = "",
    bound_hash: str = "",
) -> dict[str, Any]:
    """Live bootstrap summary vs on-disk file vs bound hash prefix. Not full bodies."""
    disk: dict[str, Any] | None = None
    if path or json_text:
        doc, err = _load_doc(path=path, json_text=json_text)
        if err:
            return {"ok": False, "issues": [_issue("disk", "error", err)], "posted": False}
        assert doc is not None
        verbs = doc.get("verbs") or doc.get("tools") or []
        disk = {
            "path": path or None,
            "format": doc.get("_format"),
            "verb_count": len(verbs) if isinstance(verbs, list) else None,
            "hash_prefix": _hash_prefix(extract_stamped_hash(doc)),
        }

    live: dict[str, Any] | None = None
    if cfg.zeus_url and cfg.default_bucket and cfg.default_scope:
        boot = bootstrap_scope(cfg, detail="summary", update_checklist=False)
        cr = boot.get("live_chat_request") if isinstance(boot, dict) else None
        live = {
            "ok": bool(boot.get("ok")),
            "failure_class": boot.get("failure_class"),
            "format": (cr or {}).get("format") if isinstance(cr, dict) else None,
            "verb_count": (cr or {}).get("verb_count") if isinstance(cr, dict) else None,
            "bootstrap_top_keys": boot.get("bootstrap_top_keys"),
        }
        if boot.get("failure_class") == "wrong_port_hub_vs_public":
            live["failure_class"] = "wrong_port_hub_vs_public"

    bound_prefix = _hash_prefix(bound_hash)
    compare: dict[str, Any] = {}
    disk_hash = (disk or {}).get("hash_prefix") if disk else None
    if disk_hash and bound_prefix:
        n = min(len(str(disk_hash).rstrip("…")), len(str(bound_prefix).rstrip("…")), 16)
        compare["disk_vs_bound"] = str(disk_hash)[:n] == str(bound_prefix)[:n]
    if disk and live and disk.get("verb_count") is not None and live.get("verb_count") is not None:
        compare["disk_vs_live_verb_count"] = disk.get("verb_count") == live.get("verb_count")
    if disk and live and disk.get("format") and live.get("format"):
        compare["disk_vs_live_format"] = disk.get("format") == live.get("format")

    return {
        "ok": True,
        "live": live,
        "disk": disk,
        "bound_hash_prefix": bound_prefix,
        "compare": compare,
        "note": "Summaries only — no catalog bodies, no Hub POST /admin/api/contracts.",
        "warning": STAMP_WARNING,
        "docs": docs_url("zeus-client/contracts-and-catalog.md"),
        "next_action": "Align bound hash with stamped disk file; stamp on Hub if prefixes differ",
    }
