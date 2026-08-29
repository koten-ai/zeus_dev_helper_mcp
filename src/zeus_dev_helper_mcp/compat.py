"""compat_check — Zeus / client feature gates (ZDH-21).

Static gates only. Never invent a COMPAT matrix row.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.docs_links import docs_url
from zeus_dev_helper_mcp.readiness import (
    _auth_headers,
    _base_url,
    _get,
    _looks_like_hub,
)

# Floor advertised by this Helper (pyproject [agent] extra). Not a COMPAT triple.
CLIENT_FLOOR = "2.3.0"

# Data table — feature → minimum Zeus. Not a published COMPAT row.
_FEATURE_GATES: tuple[dict[str, str], ...] = (
    {
        "id": "semantic_cache",
        "feature": "semantic cache / agent_memory",
        "requires_zeus": ">=0.7.6",
    },
    {
        "id": "invalid_req_id",
        "feature": "invalid_req_id reject + Trace-Class",
        "requires_zeus": "0.7.x",
    },
    {
        "id": "v1_removed",
        "feature": "V1 /v1/session and /v1/tools/* gone",
        "requires_zeus": "0.7.x",
    },
)

_VER_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


def parse_version(raw: str | None) -> tuple[int, int, int] | None:
    if not raw:
        return None
    m = _VER_RE.search(str(raw).strip().lstrip("vV"))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)


def _meets(parsed: tuple[int, int, int] | None, spec: str) -> bool | None:
    """True/False if comparable, None if version unknown."""
    if parsed is None:
        return None
    spec = spec.strip()
    if spec.startswith(">="):
        need = parse_version(spec[2:])
        return need is not None and parsed >= need
    if spec.endswith(".x"):
        base = parse_version(spec[:-2] + ".0")
        if base is None:
            return None
        # 0.7.x means >= 0.7.0 (0.8.0 counts as having the 0.7.x behaviours)
        return parsed >= base
    need = parse_version(spec)
    return need is not None and parsed >= need


def eval_feature_gates(zeus_version: str | None) -> list[dict[str, Any]]:
    parsed = parse_version(zeus_version)
    gates: list[dict[str, Any]] = []
    for row in _FEATURE_GATES:
        ok = _meets(parsed, row["requires_zeus"])
        if ok is True:
            status = "pass"
            detail = f"zeus {zeus_version} satisfies {row['requires_zeus']}"
        elif ok is False:
            status = "fail"
            detail = f"this Zeus version lacks {row['feature']} (need {row['requires_zeus']}; got {zeus_version})"
        else:
            status = "unknown"
            detail = f"zeus_version unavailable; cannot evaluate {row['feature']}"
        gates.append(
            {
                "id": row["id"],
                "feature": row["feature"],
                "requires_zeus": row["requires_zeus"],
                "status": status,
                "detail": detail,
            }
        )
    return gates


def _client_version() -> tuple[str | None, str]:
    """Prefer importlib.metadata (no adapters). Skip if that pulls the SDK."""
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("kotenai-zeus-client"), "importlib.metadata"
        except PackageNotFoundError:
            return None, "not_installed"
    except Exception:  # noqa: BLE001
        return None, "unavailable"


def _parse_version_body(text: str, payload: Any) -> str | None:
    if isinstance(payload, dict):
        v = payload.get("version") or payload.get("Version") or payload.get("zeus_version")
        if v:
            return str(v).strip()
    if isinstance(payload, str) and payload.strip():
        return payload.strip().strip('"')
    t = (text or "").strip().strip('"')
    return t or None


def compat_check(cfg: HelperConfig, *, zeus_url: str = "") -> dict[str, Any]:
    """Probe :8080 /version + /healthz and evaluate static 0.7 feature gates."""
    url = (zeus_url or cfg.zeus_url or "").strip()
    base = _base_url(url)
    client_version, client_source = _client_version()
    docs = {
        "COMPAT_0.7": docs_url("compatibility.md"),
        "note": (
            "Static feature gates from the 0.6 plan — not a published COMPAT matrix row. "
            "Do not invent client/engine/docs triples."
        ),
        "probes": docs_url("zeus/developers/api/probes.md"),
    }
    client_gate: dict[str, Any] = {
        "id": "client_floor",
        "feature": f"kotenai-zeus-client >= {CLIENT_FLOOR}",
        "requires_client": f">={CLIENT_FLOOR}",
        "status": "unknown",
        "detail": f"client_version={client_version} source={client_source}",
    }
    cv = parse_version(client_version)
    floor = parse_version(CLIENT_FLOOR)
    if cv is not None and floor is not None:
        if cv >= floor:
            client_gate["status"] = "pass"
            client_gate["detail"] = f"client {client_version} meets floor {CLIENT_FLOOR}"
        else:
            client_gate["status"] = "fail"
            client_gate["detail"] = f"client {client_version} below floor {CLIENT_FLOOR}"
    elif client_source == "not_installed":
        client_gate["status"] = "skip"
        client_gate["detail"] = f"[agent] extra not installed; floor is {CLIENT_FLOOR}"

    if not base:
        return {
            "ok": False,
            "zeus_version": None,
            "client_version": client_version,
            "client_floor": CLIENT_FLOOR,
            "gates": eval_feature_gates(None) + [client_gate],
            "docs": docs,
            "next_action": "Set ZEUS_URL=http://<host>:8080 or pass zeus_url=",
        }

    if _looks_like_hub(base):
        port_gate = {
            "id": "public_port",
            "feature": "public API :8080 (not Hub :9091)",
            "status": "fail",
            "failure_class": "wrong_port_hub_vs_public",
            "detail": f"URL looks like Hub/admin: {base}",
        }
        return {
            "ok": False,
            "zeus_version": None,
            "client_version": client_version,
            "client_floor": CLIENT_FLOOR,
            "gates": [port_gate] + eval_feature_gates(None) + [client_gate],
            "docs": docs,
            "next_action": "Point ZEUS_URL at public :8080, not Hub :9091",
        }

    headers = _auth_headers(cfg)
    zeus_version = None
    probe_gates: list[dict[str, Any]] = []
    try:
        with httpx.Client(timeout=httpx.Timeout(5.0, connect=3.0), headers=headers) as client:
            try:
                hz = _get(client, base, "/healthz")
                probe_gates.append(
                    {
                        "id": "healthz",
                        "feature": "GET /healthz",
                        "status": "pass" if hz.status_code == 200 else "fail",
                        "detail": f"HTTP {hz.status_code}",
                        "failure_class": (
                            "auth_failed"
                            if hz.status_code == 401
                            else ("network_timeout" if hz.status_code >= 500 else None)
                        ),
                    }
                )
            except httpx.RequestError as e:
                probe_gates.append(
                    {
                        "id": "healthz",
                        "feature": "GET /healthz",
                        "status": "fail",
                        "failure_class": "network_timeout",
                        "detail": str(e),
                    }
                )
            try:
                vr = _get(client, base, "/version")
                payload: Any = None
                try:
                    payload = vr.json()
                except Exception:  # noqa: BLE001
                    payload = None
                zeus_version = _parse_version_body(vr.text or "", payload) if vr.status_code == 200 else None
                probe_gates.append(
                    {
                        "id": "version",
                        "feature": "GET /version",
                        "status": "pass" if vr.status_code == 200 and zeus_version else "fail",
                        "detail": f"HTTP {vr.status_code}" + (f" version={zeus_version}" if zeus_version else ""),
                    }
                )
            except httpx.RequestError as e:
                probe_gates.append(
                    {
                        "id": "version",
                        "feature": "GET /version",
                        "status": "fail",
                        "failure_class": "network_timeout",
                        "detail": str(e),
                    }
                )
    except Exception as e:  # noqa: BLE001
        probe_gates.append(
            {
                "id": "client",
                "feature": "HTTP client",
                "status": "fail",
                "detail": str(e),
            }
        )

    feature_gates = eval_feature_gates(zeus_version)
    gates = probe_gates + feature_gates + [client_gate]
    fails = [g for g in gates if g.get("status") == "fail"]
    ok = not fails
    next_action = (
        "Zeus/client gates look compatible — continue recommend_surface / bind_contract"
        if ok
        else (fails[0].get("detail") or "Fix failing compat gates")
    )
    return {
        "ok": ok,
        "zeus_version": zeus_version,
        "client_version": client_version,
        "client_floor": CLIENT_FLOOR,
        "gates": gates,
        "docs": docs,
        "next_action": next_action,
    }
