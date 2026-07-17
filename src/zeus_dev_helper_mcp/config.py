"""Helper runtime config from environment (no secrets in logs)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_DOCS_BRANCH = "zeus-v1.0.0"
DEFAULT_CHAT_REQUEST_REPO = "koten-ai/zeus_chat_request"
DEFAULT_CHAT_REQUEST_BRANCH = "main"
DEFAULT_KOTEN_DOCS_REPO = "koten-ai/koten_docs"


@dataclass
class HelperConfig:
    zeus_url: str = ""
    zeus_auth_mode: str = "none"
    # presence flags only in public dumps
    has_zeus_user: bool = False
    has_zeus_password: bool = False
    has_bearer: bool = False
    has_llm_key: bool = False
    default_bucket: str = ""
    default_scope: str = ""
    default_collection: str = "_default"
    default_mode: str = "analytics"
    role: str = "dev"  # dev | admin
    # Catalog distribution (ZDH-14)
    chat_request_dir: Path | None = None
    chat_request_repo: str = DEFAULT_CHAT_REQUEST_REPO
    chat_request_branch: str = DEFAULT_CHAT_REQUEST_BRANCH
    github_token: str = ""
    # Docs
    docs_repo: str = DEFAULT_KOTEN_DOCS_REPO
    docs_branch: str = DEFAULT_DOCS_BRANCH
    docs_local_dir: Path | None = None
    # Project state dir
    state_dir: Path = field(default_factory=lambda: Path.home() / ".config" / "zeus_dev_helper")

    def public_view(self) -> dict:
        return {
            "zeus_url": self.zeus_url or None,
            "zeus_auth_mode": self.zeus_auth_mode,
            "has_zeus_user": self.has_zeus_user,
            "has_zeus_password": self.has_zeus_password,
            "has_bearer": self.has_bearer,
            "has_llm_key": self.has_llm_key,
            "default_bucket": self.default_bucket or None,
            "default_scope": self.default_scope or None,
            "default_collection": self.default_collection,
            "default_mode": self.default_mode,
            "role": self.role,
            "chat_request_dir": str(self.chat_request_dir) if self.chat_request_dir else None,
            "chat_request_repo": self.chat_request_repo,
            "chat_request_branch": self.chat_request_branch,
            "docs_branch": self.docs_branch,
            "docs_local_dir": str(self.docs_local_dir) if self.docs_local_dir else None,
            "state_dir": str(self.state_dir),
        }


def load_config() -> HelperConfig:
    cr_dir = os.environ.get("ZEUS_CHAT_REQUEST_DIR", "").strip()
    docs_dir = os.environ.get("KOTEN_DOCS_DIR", "").strip()
    state = os.environ.get("ZEUS_DEV_HELPER_STATE_DIR", "").strip()
    return HelperConfig(
        zeus_url=os.environ.get("ZEUS_URL", "").strip(),
        zeus_auth_mode=os.environ.get("ZEUS_AUTH_MODE", "none").strip() or "none",
        has_zeus_user=bool(os.environ.get("ZEUS_USERNAME") or os.environ.get("ZEUS_USER")),
        has_zeus_password=bool(os.environ.get("ZEUS_PASSWORD")),
        has_bearer=bool(os.environ.get("ZEUS_BEARER_TOKEN") or os.environ.get("ZEUS_TOKEN")),
        has_llm_key=bool(
            os.environ.get("LLM_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("XAI_API_KEY")
        ),
        default_bucket=os.environ.get("ZEUS_BUCKET", "").strip(),
        default_scope=os.environ.get("ZEUS_SCOPE", "").strip(),
        default_collection=os.environ.get("ZEUS_COLLECTION", "_default").strip() or "_default",
        default_mode=os.environ.get("ZEUS_MODE", "analytics").strip() or "analytics",
        role=os.environ.get("ZEUS_HELPER_ROLE", "dev").strip() or "dev",
        chat_request_dir=Path(cr_dir).expanduser() if cr_dir else None,
        chat_request_repo=os.environ.get("ZEUS_CHAT_REQUEST_REPO", DEFAULT_CHAT_REQUEST_REPO).strip()
        or DEFAULT_CHAT_REQUEST_REPO,
        chat_request_branch=os.environ.get("ZEUS_CHAT_REQUEST_BRANCH", DEFAULT_CHAT_REQUEST_BRANCH).strip()
        or DEFAULT_CHAT_REQUEST_BRANCH,
        github_token=os.environ.get("GITHUB_TOKEN", "").strip()
        or os.environ.get("GH_TOKEN", "").strip(),
        docs_repo=os.environ.get("KOTEN_DOCS_REPO", DEFAULT_KOTEN_DOCS_REPO).strip()
        or DEFAULT_KOTEN_DOCS_REPO,
        docs_branch=os.environ.get("KOTEN_DOCS_BRANCH", DEFAULT_DOCS_BRANCH).strip()
        or DEFAULT_DOCS_BRANCH,
        docs_local_dir=Path(docs_dir).expanduser() if docs_dir else None,
        state_dir=Path(state).expanduser() if state else Path.home() / ".config" / "zeus_dev_helper",
    )


# Module-level singleton for tools
CFG = load_config()


def reload_config() -> HelperConfig:
    global CFG
    CFG = load_config()
    return CFG
