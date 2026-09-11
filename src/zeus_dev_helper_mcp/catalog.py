"""Fetch V2 min chat_request templates from zeus_chat_request (ZDH-14)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.docs_links import docs_url

STAMP_WARNING = (
    "TEMPLATE ONLY — not stamped for your cluster. "
    "Verify/stamp on your Zeus (Hub) before production; never invent contract_hash."
)


class CatalogError(Exception):
    def __init__(self, message: str, failure_class: str = "empty_tool_catalog"):
        super().__init__(message)
        self.failure_class = failure_class
        self.message = message


def _github_headers(cfg: HelperConfig) -> dict[str, str]:
    h = {
        "Accept": "application/vnd.github.raw+json",
        "User-Agent": "zeus-dev-helper-mcp",
    }
    if cfg.github_token:
        h["Authorization"] = f"Bearer {cfg.github_token}"
    return h


def _raw_url(cfg: HelperConfig, rel_path: str) -> str:
    # raw.githubusercontent.com works for public; private needs token + api
    return (
        f"https://raw.githubusercontent.com/{cfg.chat_request_repo}/"
        f"{cfg.chat_request_branch}/{rel_path.lstrip('/')}"
    )


def _api_contents_url(cfg: HelperConfig, rel_path: str) -> str:
    return (
        f"https://api.github.com/repos/{cfg.chat_request_repo}/contents/"
        f"{rel_path.lstrip('/')}?ref={cfg.chat_request_branch}"
    )


def _read_local(cfg: HelperConfig, rel_path: str) -> bytes | None:
    if not cfg.chat_request_dir:
        return None
    p = cfg.chat_request_dir / rel_path
    if p.is_file():
        return p.read_bytes()
    # also allow pointing dir at repo root
    return None


def _fetch_bytes(cfg: HelperConfig, rel_path: str) -> bytes:
    local = _read_local(cfg, rel_path)
    if local is not None:
        return local

    # Prefer GitHub Contents API when token present (private repos)
    if cfg.github_token:
        url = _api_contents_url(cfg, rel_path)
        with httpx.Client(timeout=30.0, headers=_github_headers(cfg)) as client:
            r = client.get(url)
            if r.status_code == 404:
                raise CatalogError(
                    f"Not found in {cfg.chat_request_repo}@{cfg.chat_request_branch}: {rel_path}",
                    "empty_tool_catalog",
                )
            r.raise_for_status()
            # raw accept header returns file body
            return r.content

    # Public raw URL
    url = _raw_url(cfg, rel_path)
    with httpx.Client(timeout=30.0, headers={"User-Agent": "zeus-dev-helper-mcp"}) as client:
        r = client.get(url)
        if r.status_code == 404:
            raise CatalogError(
                f"Not found (public raw): {url}. "
                "For private repos set GITHUB_TOKEN or ZEUS_CHAT_REQUEST_DIR.",
                "empty_tool_catalog",
            )
        if r.status_code in (401, 403):
            raise CatalogError(
                "GitHub denied access to zeus_chat_request. "
                "Set GITHUB_TOKEN or clone the repo and set ZEUS_CHAT_REQUEST_DIR.",
                "auth_failed",
            )
        r.raise_for_status()
        return r.content


def load_manifest(cfg: HelperConfig) -> dict[str, Any]:
    raw = _fetch_bytes(cfg, "manifest.json")
    return json.loads(raw.decode("utf-8"))


def list_modes(cfg: HelperConfig) -> dict[str, Any]:
    manifest = load_manifest(cfg)
    catalogs = manifest.get("catalogs") or []
    modes = [
        {
            "mode": c.get("mode"),
            "file": c.get("file"),
            "verb_count": c.get("verb_count"),
            "format": c.get("format"),
            "sha256": c.get("sha256"),
        }
        for c in catalogs
    ]
    return {
        "profile": manifest.get("profile"),
        "repo": f"https://github.com/{cfg.chat_request_repo}",
        "branch": cfg.chat_request_branch,
        "source": "local" if cfg.chat_request_dir else "github",
        "modes": modes,
        "warning": STAMP_WARNING,
        "docs": {
            "contracts": (
                docs_url("zeus-client/contracts-and-catalog.md")
            ),
            "using_client": (
                docs_url("zeus-client/using-zeus-client.md")
            ),
        },
    }


def fetch_chat_request(
    cfg: HelperConfig,
    mode: str,
    *,
    detail: str = "summary",
) -> dict[str, Any]:
    """Return a V2 min template for mode.

    detail: summary | full
    """
    mode = (mode or "").strip().lower()
    if not mode:
        raise CatalogError("mode is required (e.g. analytics)", "empty_tool_catalog")

    manifest = load_manifest(cfg)
    catalogs = manifest.get("catalogs") or []
    entry = next((c for c in catalogs if c.get("mode") == mode), None)
    if not entry:
        known = sorted(c.get("mode") for c in catalogs if c.get("mode"))
        raise CatalogError(
            f"Unknown mode {mode!r}. Known: {', '.join(known)}",
            "empty_tool_catalog",
        )

    rel = entry["file"]
    raw = _fetch_bytes(cfg, rel)
    doc = json.loads(raw.decode("utf-8"))

    out: dict[str, Any] = {
        "mode": mode,
        "file": rel,
        "repo": f"https://github.com/{cfg.chat_request_repo}/blob/{cfg.chat_request_branch}/{rel}",
        "format": doc.get("_format"),
        "version": doc.get("_version"),
        "verb_count": len(doc.get("verbs") or []),
        "contract_metadata_from_template": doc.get("contract"),
        "sha256": entry.get("sha256"),
        "warning": STAMP_WARNING,
        "next_action": (
            "Stamp this catalog on your Zeus (Hub Catalog → Verify/Stamp), "
            "then rt.catalog.sync / load and pin scope_contracts."
        ),
        "docs": {
            "contracts": (
                docs_url("zeus-client/contracts-and-catalog.md")
            ),
            "errors_hash_drift": (
                docs_url("zeus-client/errors.md#err-409-drift")
            ),
        },
    }

    if detail == "full":
        out["chat_request"] = doc
    else:
        out["summary"] = {
            "keys": sorted(doc.keys()),
            "verb_names": [
                (v.get("function") or {}).get("name") or v.get("name")
                for v in (doc.get("verbs") or [])
            ][:20],
            "has_messages": bool(doc.get("messages")),
        }

    return out


def resolve_local_repo_hint() -> str:
    """Sibling path hint when developing monorepo-style."""
    here = Path(__file__).resolve()
    # .../zeus_dev_helper_mcp/src/zeus_dev_helper_mcp/catalog.py
    # parents[0]=pkg, [1]=src, [2]=repo root, [3]=sibling parent
    for root in (here.parents[2], here.parents[3] if len(here.parents) > 3 else here.parents[2]):
        sibling = root / "zeus_chat_request"
        if (sibling / "manifest.json").is_file():
            return str(sibling)
        sibling = root.parent / "zeus_chat_request"
        if (sibling / "manifest.json").is_file():
            return str(sibling)
    return ""
