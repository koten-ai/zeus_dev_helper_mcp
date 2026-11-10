"""Tell the agent which env names to ask for.

Missing-name questions stay on the model and login gates. A sample build asks
the full auth and LLM set every time. Password fields carry no values.
The agent writes a mode-600 env file and calls ``load_process_login``.
"""

from __future__ import annotations

import json
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


_AUTH_CHOICES = ("none", "basic", "bearer")
_BEER_USERNAME = "tester_beer"
_TRAVEL_USERNAME = "demo_1"
_TRAVEL_SAMPLES = frozenset(
    {"travel", "demo_travel", "travel_sample", "demo_travel_sample", "ui"}
)
_TEXT_PREFILL = (
    "ZEUS_USERNAME",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "COUCHBASE_QUERY_URL",
    "COUCHBASE_USERNAME",
)
_NONSECRET_KEYS = frozenset(_TEXT_PREFILL) | {"ZEUS_URL"}
_PRESENCE_KEYS = frozenset(
    {
        "ZEUS_PASSWORD",
        "ZEUS_BEARER_TOKEN",
        "LLM_API_KEY",
        "XAI_API_KEY",
        "OPENAI_API_KEY",
        "COUCHBASE_PASSWORD",
    }
)


def beer_username_default() -> str:
    return _BEER_USERNAME


def travel_username_default(root: Path | None = None) -> str:
    """Username from ``config.example.json`` when that file names one."""
    if root is not None:
        example = root / "config.example.json"
        if example.is_file() and not example.is_symlink():
            try:
                doc = json.loads(example.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                doc = None
            if isinstance(doc, dict):
                zeus = doc.get("zeus")
                if isinstance(zeus, dict):
                    name = str(zeus.get("username") or "").strip()
                    if name:
                        return name
    return _TRAVEL_USERNAME


def provider_for_base_url(base_url: str) -> str:
    """Match a base URL to a provider id. An empty URL is Grok."""
    raw = (base_url or "").strip().rstrip("/")
    if not raw:
        return "grok"
    for row in _DEFAULTS:
        if row["base_url"].rstrip("/") == raw:
            return row["id"]
    return "other"


def base_url_for_provider(provider_id: str) -> str:
    ident = (provider_id or "").strip().lower()
    for row in _DEFAULTS:
        if row["id"] == ident:
            return row["base_url"]
    return ""


def default_model_for_provider(provider_id: str) -> str:
    ident = (provider_id or "").strip().lower()
    for row in _DEFAULTS:
        if row["id"] == ident:
            return row["model"]
    return ""


def llm_base_and_model(provider_id: str, model: str, current_base: str) -> tuple[str, str]:
    """Base URL and model for an accepted provider. ``other`` keeps the current URL."""
    ident = (provider_id or "").strip().lower()
    chosen = (model or "").strip()
    if ident == "other":
        return (current_base or "").strip(), chosen
    for row in _DEFAULTS:
        if row["id"] == ident:
            return row["base_url"], chosen or row["model"]
    return (current_base or "").strip(), chosen


def dotenv_nonsecret(root: Path | None, key: str) -> str:
    """Text value from the app ``.env``. Password, token, and API key stay out."""
    if root is None or key not in _NONSECRET_KEYS:
        return ""
    return _file_value(Path(root) / ".env", key).strip()


def dotenv_example_nonsecret(root: Path | None, key: str) -> str:
    """Text value from ``.env.example``. Password, token, and API key stay out."""
    if root is None or key not in _NONSECRET_KEYS:
        return ""
    return _file_value(Path(root) / ".env.example", key).strip()


def dotenv_present(root: Path | None, key: str) -> bool:
    """True when the app ``.env`` has a non-empty value. The value is not returned."""
    if root is None or key not in _PRESENCE_KEYS | _NONSECRET_KEYS:
        return False
    return bool(_file_value(Path(root) / ".env", key).strip())


_ASSIGN_RE = re.compile(
    r"^(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$"
)


HOST_FORM = (
    "Call the host question tool and pass this question. Wait for its answer. "
    "Grok calls ask_user_question. Claude Code calls AskUserQuestion. "
    "Codex calls request_user_input. A chat sentence is not the answer."
)

_AUTH_OPTIONS: tuple[tuple[str, str], ...] = (
    (
        "none",
        (
            "Write ZEUS_AUTH_MODE=none. Skip ZEUS_USERNAME, ZEUS_PASSWORD, "
            "and ZEUS_BEARER_TOKEN."
        ),
    ),
    (
        "basic",
        (
            "Write ZEUS_AUTH_MODE=basic. Then ask ZEUS_USERNAME as text and "
            "ZEUS_PASSWORD as a password."
        ),
    ),
    (
        "bearer",
        "Write ZEUS_AUTH_MODE=bearer. Then ask ZEUS_BEARER_TOKEN as a password.",
    ),
)


def _provider_option(row: dict[str, str]) -> dict[str, str]:
    """Label carries the id. The host option shape has no separate id field."""
    label = f"{row['label']} ({row['id']})"
    if row["id"] == "other":
        description = (
            "Ask for the provider name and LLM_BASE_URL. This choice has no env var."
        )
    else:
        description = (
            f"Set LLM_BASE_URL to {row['base_url']}. "
            f"The model default is {row['model']}."
        )
    return {"label": label, "description": description}


def _choice_options(
    pairs: tuple[tuple[str, str], ...] | list[tuple[str, str]],
) -> list[dict[str, str]]:
    return [
        {"label": label, "description": description} for label, description in pairs
    ]


def sample_build_ask_text() -> str:
    """Instructions for the sample-build form. No secret values."""
    return (
        "This sample build shows ask_user every time, including when values "
        "are already set. "
        f"{HOST_FORM} "
        "Call that tool once per ask_user row, in order. "
        "Skip a row whose when does not match the answers so far. "
        "A choice row has question and options. Pass that row. "
        "The selected ZEUS_AUTH_MODE label is none, basic, or bearer. "
        "basic then asks ZEUS_USERNAME as text and ZEUS_PASSWORD as a password. "
        "bearer asks ZEUS_BEARER_TOKEN as a password. "
        "none skips username, password, and the bearer token. "
        "The selected llm_provider label is the display name and the id in "
        "parentheses, for example Grok (grok). Write that id. "
        "A named provider sets LLM_BASE_URL from llm_options. "
        "Other asks for the provider name and LLM_BASE_URL as text. "
        "Ask LLM_MODEL as text and offer that entry's model as the default. "
        "Other has no model default. "
        "Ask LLM_API_KEY as a password through the host question tool's text field. "
        "Password, bearer token, and API key have no options and no value "
        "in this result. Write the names to a mode-600 env file and call "
        "load_process_login with that path. Write the same names in the app "
        ".env. Leave config.json llm.api_key_env as the name LLM_API_KEY. "
        "Call set_prereq with auth_mode and the presence flags has_username, "
        "has_password, has_bearer, and has_llm_key. Do not pass the password, "
        "bearer token, or API key as a tool argument."
    )


def _couchbase_ask_text() -> str:
    """Yelp-only instruction. The password is not collected here."""
    return (
        "Ask COUCHBASE_QUERY_URL and COUCHBASE_USERNAME as text. "
        "Write COUCHBASE_PASSWORD in the app .env. "
        "Do not ask for that password and do not pass it as a tool argument."
    )


def _auth_default(cfg: Any) -> str:
    if cfg is not None:
        raw = str(getattr(cfg, "zeus_auth_mode", "") or "").strip().lower()
        if raw in _AUTH_CHOICES:
            return raw
    raw = (os.environ.get("ZEUS_AUTH_MODE") or "").strip().lower()
    if raw in _AUTH_CHOICES:
        return raw
    return ""


def _unquote_env(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1]
    return text.strip()


def _file_value(path: Path, key: str) -> str:
    if not path.is_file() or path.is_symlink():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for line in text.splitlines():
        match = _ASSIGN_RE.match(line.strip())
        if match is None or match.group("key") != key:
            continue
        return _unquote_env(match.group("value"))
    return ""


def _text_prefill(key: str, root: Path | None) -> str:
    """Current text value. Password, token, and API key stay out."""
    if key not in _TEXT_PREFILL:
        return ""
    if key == "ZEUS_USERNAME":
        current = _username()
    else:
        current = (os.environ.get(key) or "").strip()
    if current:
        return current
    if root is None:
        return ""
    for name in (".env", ".env.example"):
        found = _file_value(root / name, key)
        if found:
            return found
    return ""


def _with_default(row: dict[str, Any], default: str) -> dict[str, Any]:
    if default:
        row["default"] = default
    return row


def sample_build_questions(
    sample: str,
    *,
    root: Path | None = None,
    cfg: Any = None,
    example_text: str | None = None,
) -> list[dict[str, Any]]:
    """One hint per field. Text defaults only. No secret values."""
    if example_text is not None:
        options = llm_options(example_text)
    else:
        options = llm_options_for_dir(root)
    username = _text_prefill("ZEUS_USERNAME", root)
    sample_name = (sample or "").strip().lower()
    if not username and sample_name == "beer":
        username = _BEER_USERNAME
    if not username and sample_name in _TRAVEL_SAMPLES:
        username = travel_username_default(root)
    provider_ids = [row["id"] for row in options]
    provider_options = [_provider_option(row) for row in options]
    questions = [
        _with_default(
            {
                "env": "ZEUS_AUTH_MODE",
                "kind": "choice",
                "choices": list(_AUTH_CHOICES),
                "question": "Which ZEUS_AUTH_MODE should this app use?",
                "options": _choice_options(_AUTH_OPTIONS),
                "prompt": "Pass this row. The selected label is ZEUS_AUTH_MODE.",
            },
            _auth_default(cfg),
        ),
        _with_default(
            {
                "env": "ZEUS_USERNAME",
                "kind": "text",
                "when": {"env": "ZEUS_AUTH_MODE", "equals": "basic"},
                "prompt": (
                    "Ask for ZEUS_USERNAME through the host question tool's "
                    "text field. This row has no options."
                ),
            },
            username,
        ),
        {
            "env": "ZEUS_PASSWORD",
            "kind": "password",
            "when": {"env": "ZEUS_AUTH_MODE", "equals": "basic"},
            "prompt": (
                "Ask for ZEUS_PASSWORD through the host question tool's "
                "text field. This row has no options and no value."
            ),
        },
        {
            "env": "ZEUS_BEARER_TOKEN",
            "kind": "password",
            "when": {"env": "ZEUS_AUTH_MODE", "equals": "bearer"},
            "prompt": (
                "Ask for ZEUS_BEARER_TOKEN through the host question tool's "
                "text field. This row has no options and no value."
            ),
        },
        {
            "id": "llm_provider",
            "kind": "choice",
            "choices": provider_ids,
            "question": "Which LLM provider should this app use?",
            "options": provider_options,
            "prompt": (
                "Pass this row. The id is in parentheses on the selected label. "
                "This choice has no env var."
            ),
        },
        {
            "id": "provider_name",
            "kind": "text",
            "when": {"id": "llm_provider", "equals": "other"},
            "prompt": (
                "Ask for the provider name through the host question tool's "
                "text field. This row has no options and no env var."
            ),
        },
        _with_default(
            {
                "env": "LLM_BASE_URL",
                "kind": "text",
                "when": {"id": "llm_provider", "equals": "other"},
                "prompt": (
                    "Ask for LLM_BASE_URL through the host question tool's "
                    "text field. A named provider sets LLM_BASE_URL from "
                    "llm_options and is not asked. This row has no options."
                ),
            },
            _text_prefill("LLM_BASE_URL", root),
        ),
        _with_default(
            {
                "env": "LLM_MODEL",
                "kind": "text",
                "prompt": (
                    "Ask for LLM_MODEL through the host question tool's text "
                    "field. Offer the chosen option's model as the default. "
                    "Other has no default. This row has no options."
                ),
            },
            _text_prefill("LLM_MODEL", root),
        ),
        {
            "env": "LLM_API_KEY",
            "kind": "password",
            "prompt": (
                "Ask for LLM_API_KEY through the host question tool's text "
                "field. This row has no options and no value."
            ),
        },
    ]
    from zeus_dev_helper_mcp.yelp import is_yelp_demo_sample

    if is_yelp_demo_sample(sample_name):
        spot = next(
            index
            for index, row in enumerate(questions)
            if row.get("env") == "LLM_API_KEY"
        )
        questions[spot:spot] = _couchbase_question_rows(root)
    return questions


def _couchbase_question_rows(root: Path | None) -> list[dict[str, Any]]:
    """Two text rows. No password row. The user writes the password in ``.env``."""
    url = _text_prefill("COUCHBASE_QUERY_URL", root) or "http://localhost:8093"
    username = _text_prefill("COUCHBASE_USERNAME", root) or "Administrator"
    password_note = "Write COUCHBASE_PASSWORD in the app .env. Do not ask for the password."
    return [
        _with_default(
            {
                "env": "COUCHBASE_QUERY_URL",
                "kind": "text",
                "prompt": (
                    "Ask for COUCHBASE_QUERY_URL through the host question "
                    f"tool's text field. {password_note} This row has no options."
                ),
            },
            url,
        ),
        _with_default(
            {
                "env": "COUCHBASE_USERNAME",
                "kind": "text",
                "prompt": (
                    "Ask for COUCHBASE_USERNAME through the host question "
                    f"tool's text field. {password_note} This row has no options."
                ),
            },
            username,
        ),
    ]


def attach_sample_build_ask(
    payload: dict[str, Any],
    *,
    sample: str,
    root: Path | None = None,
    cfg: Any = None,
) -> dict[str, Any]:
    """Replace ask_user with the sample-build form. Values stay out."""
    payload["sample_build_form"] = True
    payload["llm_choice_required"] = True
    payload["llm_options"] = llm_options_for_dir(root)
    payload["ask_user"] = sample_build_questions(sample, root=root, cfg=cfg)
    nested = payload.get("app_config")
    if isinstance(nested, dict) and "ask_user" in nested:
        kept = dict(nested)
        kept.pop("ask_user", None)
        payload["app_config"] = kept
    text = sample_build_ask_text()
    from zeus_dev_helper_mcp.yelp import is_yelp_demo_sample

    if is_yelp_demo_sample(sample):
        extra = _couchbase_ask_text()
        if extra not in text:
            text = f"{text} {extra}"
    prior = str(payload.get("next_action") or "").strip()
    if text not in prior:
        payload["next_action"] = f"{text} {prior}".strip()
    return payload
