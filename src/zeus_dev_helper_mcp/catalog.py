"""Fetch V2 min chat_request templates from zeus_chat_request (ZDH-14)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import httpx

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.docs_links import docs_url

STAMP_WARNING = (
    "TEMPLATE ONLY — not stamped for your cluster. "
    "Verify/stamp on your Zeus (Hub) before production; never invent contract_hash."
)

ENV_CHAT_REQUEST_DIR = "ZEUS_CHAT_REQUEST_DIR"
DEFAULT_CHAT_REQUEST_DIR_NAME = "zeus_chat_request"
DEFAULT_CHAT_REQUEST_REPO_URL = "https://github.com/koten-ai/zeus_chat_request.git"


class CatalogError(Exception):
    def __init__(self, message: str, failure_class: str = "empty_tool_catalog"):
        super().__init__(message)
        self.failure_class = failure_class
        self.message = message


def _chat_request_state_path(cfg: HelperConfig) -> Path:
    return cfg.state_dir / "chat_request.json"


def save_chat_request_dir(cfg: HelperConfig, root: Path) -> None:
    """Persist discovered/cloned zeus_chat_request path for later catalog tools."""
    try:
        cfg.state_dir.mkdir(parents=True, exist_ok=True)
        _chat_request_state_path(cfg).write_text(
            json.dumps({"chat_request_dir": str(root.resolve())}) + "\n",
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001, S110
        pass


def load_chat_request_dir(cfg: HelperConfig | None = None) -> Path | None:
    if cfg is None:
        return None
    path = _chat_request_state_path(cfg)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = str(data.get("chat_request_dir") or "").strip()
        if not raw:
            return None
        p = Path(raw).expanduser().resolve()
        if _is_chat_request_root(p):
            return p
    except Exception:  # noqa: BLE001, S110
        pass
    return None


def _is_chat_request_root(root: Path) -> bool:
    return root.is_dir() and (root / "manifest.json").is_file()


def set_chat_request_dir_env(root: Path) -> str:
    """Set process env ZEUS_CHAT_REQUEST_DIR to the catalog repo root."""
    path = str(root.expanduser().resolve())
    os.environ[ENV_CHAT_REQUEST_DIR] = path
    return path


def _default_clone_parent() -> Path:
    """Prefer monorepo sibling of Helper; else cwd."""
    here = Path(__file__).resolve()
    helper_root = here.parents[2]  # zeus_dev_helper_mcp
    monorepo = helper_root.parent
    if monorepo.is_dir():
        return monorepo
    return Path.cwd()


def _candidate_chat_request_dirs() -> list[Path]:
    here = Path(__file__).resolve()
    helper_root = here.parents[2]
    monorepo = helper_root.parent
    out: list[Path] = []
    for base in (monorepo, helper_root.parent, Path.cwd(), Path.cwd().parent):
        out.append(base / DEFAULT_CHAT_REQUEST_DIR_NAME)
    seen: set[str] = set()
    unique: list[Path] = []
    for p in out:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


def _find_chat_request_dir(
    cfg: HelperConfig,
    *,
    explicit: str = "",
) -> Path | None:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        return p if _is_chat_request_root(p) else None
    if cfg.chat_request_dir is not None:
        p = cfg.chat_request_dir.expanduser().resolve()
        if _is_chat_request_root(p):
            return p
    env = os.environ.get(ENV_CHAT_REQUEST_DIR, "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        if _is_chat_request_root(p):
            return p
    persisted = load_chat_request_dir(cfg)
    if persisted is not None:
        return persisted
    for c in _candidate_chat_request_dirs():
        if _is_chat_request_root(c):
            return c.resolve()
    hint = resolve_local_repo_hint()
    if hint:
        p = Path(hint)
        if _is_chat_request_root(p):
            return p.resolve()
    return None


def clone_chat_request(
    *,
    dest: Path,
    repo_url: str = DEFAULT_CHAT_REQUEST_REPO_URL,
    branch: str = "main",
    timeout_s: int = 120,
) -> dict[str, Any]:
    """Shallow-clone public zeus_chat_request into dest (dest must not exist yet)."""
    dest = dest.expanduser().resolve()
    if dest.exists():
        return {
            "ok": False,
            "cloned": False,
            "dest": str(dest),
            "error": f"destination already exists: {dest}",
            "next_action": (
                f"Set {ENV_CHAT_REQUEST_DIR} to the existing clone, or choose another parent"
            ),
        }
    parent = dest.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return {
            "ok": False,
            "cloned": False,
            "dest": str(dest),
            "error": f"cannot create parent {parent}: {e}",
            "next_action": "Choose a writable parent directory",
        }

    cmd = ["git", "clone", "--depth", "1", "--branch", branch, repo_url, str(dest)]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError:
        return {
            "ok": False,
            "cloned": False,
            "dest": str(dest),
            "error": "git not found on PATH",
            "next_action": (
                f"Install git, or clone manually and set {ENV_CHAT_REQUEST_DIR}"
            ),
            "clone_cmd": " ".join(cmd),
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "cloned": False,
            "dest": str(dest),
            "error": f"git clone timed out after {timeout_s}s",
            "next_action": "Retry list_catalog_modes / fetch_chat_request or clone manually",
            "clone_cmd": " ".join(cmd),
        }

    if proc.returncode != 0 or not _is_chat_request_root(dest):
        err = (proc.stderr or proc.stdout or "").strip()[:800]
        return {
            "ok": False,
            "cloned": False,
            "dest": str(dest),
            "error": err or f"git clone failed (exit {proc.returncode})",
            "next_action": (
                f"Fix network/git access, or clone manually and set {ENV_CHAT_REQUEST_DIR}"
            ),
            "clone_cmd": " ".join(cmd),
        }

    return {
        "ok": True,
        "cloned": True,
        "dest": str(dest),
        "repo": repo_url,
        "branch": branch,
        "clone_cmd": " ".join(cmd),
    }


def ensure_chat_request_dir(
    cfg: HelperConfig,
    *,
    parent_dir: str = "",
    clone_if_missing: bool = True,
) -> dict[str, Any]:
    """Locate zeus_chat_request or clone the public repo; set ZEUS_CHAT_REQUEST_DIR.

    When ZEUS_CHAT_REQUEST_DIR / cfg.chat_request_dir is unset or invalid:
    discover a sibling checkout, else shallow-clone into parent_dir/zeus_chat_request
    (default parent: Helper monorepo parent). On success, sets process env and
    updates cfg.chat_request_dir.
    """
    found = _find_chat_request_dir(cfg)
    clone_info: dict[str, Any] | None = None
    repo_url = f"https://github.com/{cfg.chat_request_repo}.git"
    branch = cfg.chat_request_branch or "main"

    if found is None and clone_if_missing:
        parent = (
            Path(parent_dir).expanduser().resolve()
            if parent_dir.strip()
            else _default_clone_parent()
        )
        dest = parent / DEFAULT_CHAT_REQUEST_DIR_NAME
        if _is_chat_request_root(dest):
            found = dest
        else:
            clone_info = clone_chat_request(
                dest=dest,
                repo_url=repo_url,
                branch=branch,
            )
            if clone_info.get("ok"):
                found = dest
            else:
                return {
                    "ok": False,
                    "local_dir": None,
                    "cloned": False,
                    "clone": clone_info,
                    "env": {ENV_CHAT_REQUEST_DIR: None},
                    "next_action": clone_info.get("next_action")
                    or f"Clone manually and set {ENV_CHAT_REQUEST_DIR}, or set GITHUB_TOKEN",
                    "repo": f"https://github.com/{cfg.chat_request_repo}",
                    "private": False,
                }

    if found is None:
        return {
            "ok": False,
            "local_dir": None,
            "cloned": False,
            "clone": clone_info,
            "env": {ENV_CHAT_REQUEST_DIR: None},
            "next_action": (
                f"No local zeus_chat_request; enable clone_if_missing or set "
                f"{ENV_CHAT_REQUEST_DIR}"
            ),
            "repo": f"https://github.com/{cfg.chat_request_repo}",
            "private": False,
        }

    env_path = set_chat_request_dir_env(found)
    cfg.chat_request_dir = found
    save_chat_request_dir(cfg, found)
    return {
        "ok": True,
        "local_dir": str(found),
        "cloned": bool(clone_info and clone_info.get("cloned")),
        "clone": clone_info,
        "env": {ENV_CHAT_REQUEST_DIR: env_path},
        "repo": f"https://github.com/{cfg.chat_request_repo}",
        "private": False,
        "next_action": (
            f"{ENV_CHAT_REQUEST_DIR}={env_path}. Templates are local; still stamp on Hub "
            "before production."
        ),
    }


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
    # When ZEUS_CHAT_REQUEST_DIR is unset, locate or shallow-clone public repo.
    ensure_chat_request_dir(cfg)
    raw = _fetch_bytes(cfg, "manifest.json")
    return json.loads(raw.decode("utf-8"))


def list_modes(cfg: HelperConfig) -> dict[str, Any]:
    # ensure runs inside load_manifest; call once here for cloned/env fields.
    ensure = ensure_chat_request_dir(cfg)
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
        "local_dir": str(cfg.chat_request_dir) if cfg.chat_request_dir else None,
        "cloned": bool(ensure.get("cloned")),
        "env": ensure.get("env") or {ENV_CHAT_REQUEST_DIR: os.environ.get(ENV_CHAT_REQUEST_DIR)},
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

    ensure = ensure_chat_request_dir(cfg)
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
        "source": "local" if cfg.chat_request_dir else "github",
        "local_dir": str(cfg.chat_request_dir) if cfg.chat_request_dir else None,
        "cloned": bool(ensure.get("cloned")),
        "env": ensure.get("env") or {ENV_CHAT_REQUEST_DIR: os.environ.get(ENV_CHAT_REQUEST_DIR)},
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
