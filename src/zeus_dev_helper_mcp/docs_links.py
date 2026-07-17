"""Canonical published docs URLs (https://docs.koten.ai/).

GitHub koten_docs remains the *source* repo; the public site is docs.koten.ai
(GitBook). Paths follow repo file paths without .md (see koten_docs SUMMARY).
While the site is still a placeholder, links still point at the future home.
"""

from __future__ import annotations

import os

DEFAULT_DOCS_BASE = "https://docs.koten.ai"
DEFAULT_DOCS_SOURCE = "https://github.com/koten-ai/koten_docs"


def docs_base() -> str:
    return (os.environ.get("KOTEN_DOCS_BASE_URL") or DEFAULT_DOCS_BASE).rstrip("/")


def docs_source_repo() -> str:
    return (os.environ.get("KOTEN_DOCS_SOURCE_URL") or DEFAULT_DOCS_SOURCE).rstrip("/")


def docs_url(path: str) -> str:
    """Map a koten_docs relative path to the published site.

    Examples:
      zeus-client/using-zeus-client.md -> https://docs.koten.ai/zeus-client/using-zeus-client
      zeus-client/errors.md#err-409-drift -> https://docs.koten.ai/zeus-client/errors#err-409-drift
      agent-index.yaml -> GitHub source (machine index)
    """
    raw = (path or "").strip().lstrip("/")
    anchor = ""
    if "#" in raw:
        raw, frag = raw.split("#", 1)
        anchor = f"#{frag}"
    p = raw
    # YAML / raw machine files: prefer source repo until published on the site
    if p.endswith(".yaml") or p.endswith(".yml"):
        branch = os.environ.get("KOTEN_DOCS_BRANCH", "zeus-v1.0.0").strip() or "zeus-v1.0.0"
        return f"{docs_source_repo()}/blob/{branch}/{raw}{anchor}"
    if p.endswith(".md"):
        p = p[: -len(".md")]
    if not p:
        return docs_base() + "/" + anchor.lstrip("#") if not anchor else docs_base() + "/"
    return f"{docs_base()}/{p}{anchor}"
