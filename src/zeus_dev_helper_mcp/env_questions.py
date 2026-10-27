"""Tell the agent which missing env names to ask for.

The password and the API key are never form fields and never tool arguments.
The agent asks, writes a mode-600 env file, and calls ``load_process_login``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

_COMMENT_RE = re.compile(
    r"^#\s*(?P<label>[^:]+):\s*(?P<url>https?://\S+)"
    r"(?:\s+model\s+(?P<model>\S+))?\s*$",
    re.IGNORECASE,
)

# Base URLs match demo_beer_sample ``.env.example``. Models are the offered defaults.
_DEFAULTS: tuple[dict[str, str], ...] = (
    {
        "id": "grok",
        "label": "Grok",
        "base_url": "https://api.x.ai/v1",
        "model": "grok-4.5-latest",
    },
    {
        "id": "openai",
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-5.6-sol",
    },
    {
        "id": "anthropic",
        "label": "Anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "model": "claude-opus-5-5",
    },
    {
        "id": "gemini",
        "label": "Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-3.8-flash",
    },
)

_HOST_MODEL = {row["base_url"].split("/")[2]: row["model"] for row in _DEFAULTS}

_OTHER: dict[str, str] = {
    "id": "other",
    "label": "Other",
    "base_url": "",
    "model": "",
}

_LOGIN_PROMPTS = {
    "ZEUS_USERNAME": "Ask the user for ZEUS_USERNAME. Wait for the answer.",
    "ZEUS_PASSWORD": "Ask the user for ZEUS_PASSWORD. Wait for the answer.",
}

LLM_PROVIDER_COMMENTS = "\n".join(
    f"# {row['label']}: {row['base_url']} model {row['model']}" for row in _DEFAULTS
)


def _username() -> str:
    return (os.environ.get("ZEUS_USERNAME") or os.environ.get("ZEUS_USER") or "").strip()


def _password() -> str:
    return (os.environ.get("ZEUS_PASSWORD") or "").strip()


def missing_login_names() -> list[str]:
    """Env names that basic auth still needs. Values stay out."""
    missing: list[str] = []
    if not _username():
        missing.append("ZEUS_USERNAME")
    if not _password():
        missing.append("ZEUS_PASSWORD")
    return missing


def login_ask_text(missing: list[str] | None = None) -> str:
    names = [name for name in (missing or []) if name in _LOGIN_PROMPTS]
    if not names:
        names = ["ZEUS_USERNAME", "ZEUS_PASSWORD"]
    joined = " and ".join(names)
    wait = "Wait for each answer." if len(names) > 1 else "Wait for the answer."
    return (
        f"Ask the user for {joined}. {wait} "
        "Write the answers to a mode-600 env file and call load_process_login "
        "with that path. Do not pass the password as a tool argument. "
        "set_prereq stores presence flags only."
    )


def attach_login_ask(
    payload: dict[str, Any],
    missing: list[str] | None = None,
    *,
    replace: bool = False,
) -> dict[str, Any]:
    """Add one question per missing login name. No secret values."""
    source = missing if missing is not None else missing_login_names()
    names = [name for name in source if name in _LOGIN_PROMPTS]
    if not names:
        return payload
    questions = [{"env": name, "prompt": _LOGIN_PROMPTS[name]} for name in names]
    existing = payload.get("ask_user")
    if replace or not isinstance(existing, list):
        payload["ask_user"] = questions
    else:
        payload["ask_user"] = [*questions, *existing]
    if "missing_env" not in payload:
        payload["missing_env"] = names
    return payload


def _host(url: str) -> str:
    text = url.strip()
    if "://" in text:
        text = text.split("://", 1)[1]
    return text.split("/", 1)[0].split("@")[-1].split(":")[0].lower()


def _slug(label: str) -> str:
    raw = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return raw or "provider"


def llm_options_from_example(text: str) -> list[dict[str, str]] | None:
    """Read ``# Name: https://...`` lines. A known host supplies the model."""
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        match = _COMMENT_RE.match(line.strip())
        if match is None:
            continue
        url = match.group("url")
        short = match.group("label").split("(", 1)[0].strip()
        model = (match.group("model") or "").strip() or _HOST_MODEL.get(_host(url), "")
        ident = _slug(short)
        if ident in seen or ident == "other":
            continue
        seen.add(ident)
        found.append(
            {
                "id": ident,
                "label": short,
                "base_url": url,
                "model": model,
            }
        )
    if not found:
        return None
    found.append(dict(_OTHER))
    return found


def llm_options(example_text: str | None = None) -> list[dict[str, str]]:
    if example_text:
        parsed = llm_options_from_example(example_text)
        if parsed:
            return parsed
    return [dict(row) for row in _DEFAULTS] + [dict(_OTHER)]


def llm_options_for_dir(root: Path | None) -> list[dict[str, str]]:
    if root is not None:
        path = Path(root) / ".env.example"
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            parsed = llm_options_from_example(text)
            if parsed:
                return parsed
    return llm_options()


def llm_ask_text() -> str:
    return (
        "This step calls the model. Ask the user to choose one entry in "
        "llm_options and wait. Set LLM_BASE_URL to that entry's base_url. "
        "For Other, ask the user for the base URL. Then ask for LLM_MODEL "
        "and offer that entry's model as the default. Then ask for LLM_API_KEY. "
        "Write LLM_BASE_URL, LLM_MODEL, and LLM_API_KEY to a mode-600 env file "
        "and call load_process_login with that path. Also write them in the app "
        ".env. Leave config.json llm.api_key_env as the name LLM_API_KEY. "
        "Do not pass the API key as a tool argument. "
        "Set LLM_API_KEY, XAI_API_KEY, or OPENAI_API_KEY in this process. "
        "set_prereq(has_llm_key=true) does not count."
    )


def attach_llm_ask(
    payload: dict[str, Any],
    *,
    example_text: str | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Add the provider list and the model, then key, questions."""
    if example_text is not None:
        options = llm_options(example_text)
    else:
        options = llm_options_for_dir(root)
    payload["llm_choice_required"] = True
    payload["llm_options"] = options
    questions = [
        {
            "env": "LLM_BASE_URL",
            "prompt": (
                "Ask the user to choose an LLM from llm_options. Wait. "
                "Set LLM_BASE_URL to the chosen base_url. "
                "For Other, ask the user for the base URL."
            ),
        },
        {
            "env": "LLM_MODEL",
            "prompt": (
                "Ask the user for LLM_MODEL. Offer the chosen option's model "
                "as the default. Wait for the answer."
            ),
        },
        {
            "env": "LLM_API_KEY",
            "prompt": "Ask the user for LLM_API_KEY. Wait for the answer.",
        },
    ]
    existing = payload.get("ask_user")
    if isinstance(existing, list):
        payload["ask_user"] = [*existing, *questions]
    else:
        payload["ask_user"] = questions
    return payload
