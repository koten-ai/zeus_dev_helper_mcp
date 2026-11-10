"""Connection and LLM cards for the first sample create.

The URL and auth gate stays in ``clarify``. These cards run only while that
sample's creation log is absent. The directory they name is the one beer,
travel, yelp, or ``scaffold_app`` will write.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from zeus_dev_helper_mcp.clarify import (
    HUB_NEXT,
    URL_FIELD_DESCRIPTION,
    AcceptedElicitation,
    CancelledElicitation,
    Clarification,
    DeclinedElicitation,
    Elicit,
    _can_elicit,
    _peek,
    _resolve_auth,
    env_prefill,
    query_url_has_userinfo,
    stored_zeus_url,
    valid_public_url,
)

CONNECTION_PASSWORD_DESCRIPTION = (
    "True after ZEUS_PASSWORD is in the app .env. "
    "Do not type the password into this form."
)
LLM_KEY_DESCRIPTION = (
    "True after LLM_API_KEY is in the app .env. "
    "Do not type the API key into this form. "
    "config.json llm.api_key_env stays the name LLM_API_KEY."
)
COUCHBASE_PASSWORD_DESCRIPTION = (
    "True after COUCHBASE_PASSWORD is in the app .env. "
    "Put COUCHBASE_PASSWORD in that file. "
    "Do not type the password into this form."
)
COUCHBASE_URL_DEFAULT = "http://localhost:8093"
COUCHBASE_USERNAME_DEFAULT = "Administrator"
DECLINE_COUCHBASE_NEXT = (
    "Couchbase setup was declined. The app was not created. "
    "Enter COUCHBASE_QUERY_URL and COUCHBASE_USERNAME. "
    "Put COUCHBASE_PASSWORD in the app .env. Do not type the password into this form."
)
CANCEL_COUCHBASE_NEXT = (
    "Couchbase setup was cancelled. The app was not created. "
    "Enter COUCHBASE_QUERY_URL and COUCHBASE_USERNAME. "
    "Put COUCHBASE_PASSWORD in the app .env. Do not type the password into this form."
)
COUCHBASE_USERINFO_NEXT = (
    "COUCHBASE_QUERY_URL must not include a username or password. "
    "Enter the query URL without userinfo. "
    "Put COUCHBASE_PASSWORD in the app .env. Do not type the password into this form."
)
DECLINE_CREATE_NEXT = (
    "Sample setup was declined. The app was not created. "
    "Enter the public Zeus URL on port 8080 and ZEUS_USERNAME. "
    "Put ZEUS_PASSWORD in the app .env. Do not pass the password."
)
CANCEL_CREATE_NEXT = (
    "Sample setup was cancelled. The app was not created. "
    "Enter the public Zeus URL on port 8080 and ZEUS_USERNAME. "
    "Put ZEUS_PASSWORD in the app .env. Do not pass the password."
)
DECLINE_LLM_NEXT = (
    "LLM setup was declined. The app was not created. "
    "Choose a provider and model, and put LLM_API_KEY in the app .env. "
    "Do not pass the API key."
)
_TRAVEL_NAMES = frozenset(
    {"", "travel", "demo_travel", "travel_sample", "demo_travel_sample", "ui"}
)
_API_NAMES = frozenset({"api", "rest", "api_only", "api-only", "fastapi"})
_PROVIDER_IDS = frozenset({"grok", "openai", "anthropic", "gemini", "other"})


def is_api_kind(app_kind: str) -> bool:
    return (app_kind or "").strip().lower().replace("-", "_") in {
        "api",
        "rest",
        "api_only",
        "fastapi",
    }


def create_needs_llm_card(sample: str) -> bool:
    """True when this create's checklist keeps an LLM key open.

    Beer Pour uses checklist 3.2. Travel, the yelp demo, and the API sample
    use checklist 1.2. Travel with ``has_llm_key`` false is the Direct opt-out.
    """
    from zeus_dev_helper_mcp.beer import is_beer_sample
    from zeus_dev_helper_mcp.config import reload_config
    from zeus_dev_helper_mcp.prereqs import load_prereqs
    from zeus_dev_helper_mcp.yelp import is_yelp_demo_sample

    text = (sample or "").strip().lower()
    if is_beer_sample(text):
        return True
    if text in _TRAVEL_NAMES:
        return load_prereqs(reload_config()).get("has_llm_key") is not False
    return text in _API_NAMES or is_yelp_demo_sample(text)


def sample_destination(
    sample: str,
    *,
    sample_dir: str = "",
    project_name: str = "",
    parent_dir: str = "",
) -> Path:
    """Directory ``use_sample`` will read or create for this sample."""
    from zeus_dev_helper_mcp.beer import beer_destination, is_beer_sample
    from zeus_dev_helper_mcp.config import reload_config
    from zeus_dev_helper_mcp.travel import travel_destination
    from zeus_dev_helper_mcp.yelp import is_yelp_demo_sample, yelp_destination

    cfg = reload_config()
    if is_beer_sample(sample):
        return beer_destination(
            cfg,
            sample_dir=sample_dir,
            project_name=project_name,
            parent_dir=parent_dir,
        ).root
    if is_yelp_demo_sample(sample):
        return yelp_destination(
            cfg,
            sample_dir=sample_dir,
            project_name=project_name,
            parent_dir=parent_dir,
        )
    return travel_destination(
        cfg,
        sample_dir=sample_dir,
        project_name=project_name,
        parent_dir=parent_dir,
    ).root


def _nonempty_dir(path: Path) -> bool:
    try:
        return path.is_dir() and any(path.iterdir())
    except OSError:
        return False


def _prefill_url(root: Path | None) -> str:
    from zeus_dev_helper_mcp.env_questions import dotenv_nonsecret

    from_file = dotenv_nonsecret(root, "ZEUS_URL")
    if valid_public_url(from_file):
        return from_file
    stored = stored_zeus_url()
    if valid_public_url(stored):
        return stored
    return env_prefill()


def _prefill_username(sample: str, root: Path | None) -> str:
    from zeus_dev_helper_mcp.beer import is_beer_sample
    from zeus_dev_helper_mcp.env_questions import (
        beer_username_default,
        dotenv_nonsecret,
    )

    found = dotenv_nonsecret(root, "ZEUS_USERNAME")
    if found:
        return found
    from zeus_dev_helper_mcp.app_env import process_username

    current = process_username()
    if current:
        return current
    if is_beer_sample(sample):
        return beer_username_default()
    return ""


def _llm_prefill(root: Path | None) -> tuple[str, str, str]:
    """Provider id, model, and current base URL. No API key."""
    from zeus_dev_helper_mcp.env_questions import (
        default_model_for_provider,
        dotenv_nonsecret,
        provider_for_base_url,
    )

    base = dotenv_nonsecret(root, "LLM_BASE_URL") or (
        os.environ.get("LLM_BASE_URL") or ""
    ).strip()
    model = dotenv_nonsecret(root, "LLM_MODEL") or (
        os.environ.get("LLM_MODEL") or ""
    ).strip()
    provider = provider_for_base_url(base)
    if not model:
        model = default_model_for_provider(provider)
    return provider, model, base


def _password_ready(root: Path | None) -> bool:
    from zeus_dev_helper_mcp.env_questions import dotenv_present

    return dotenv_present(root, "ZEUS_PASSWORD")


def _llm_key_ready(root: Path | None) -> bool:
    from zeus_dev_helper_mcp.env_questions import dotenv_present

    return any(
        dotenv_present(root, name)
        for name in ("LLM_API_KEY", "XAI_API_KEY", "OPENAI_API_KEY")
    )


def _connection_message(env_path: Path, exists: bool, *, hub: bool = False) -> str:
    if hub:
        lead = (
            "That URL is not the public Zeus API. "
            "Enter an http(s) URL on port 8080. Hub port 9091 is not the app path."
        )
    else:
        lead = "Confirm the public Zeus URL (port 8080) and ZEUS_USERNAME."
    if exists:
        where = (
            f"Put ZEUS_PASSWORD in {env_path}. "
            "You can edit that file while this card is open."
        )
    else:
        where = (
            f"This create will write {env_path}. "
            "Put ZEUS_PASSWORD there after the file appears."
        )
    return f"{lead} {where} Do not type the password into this form."


def _llm_message(env_path: Path, exists: bool) -> str:
    if exists:
        where = f"Put LLM_API_KEY in {env_path}."
    else:
        where = (
            f"This create will write {env_path}. "
            "Put LLM_API_KEY there after the file appears."
        )
    return (
        "Choose the LLM provider and model. "
        f"{where} Do not type the API key into this form. "
        "config.json llm.api_key_env stays the name LLM_API_KEY."
    )


def _declined_create(
    action: str, *, llm: bool = False, couchbase: bool = False
) -> Clarification:
    if llm:
        action_text = DECLINE_LLM_NEXT
    elif couchbase and action == "cancel":
        action_text = CANCEL_COUCHBASE_NEXT
    elif couchbase:
        action_text = DECLINE_COUCHBASE_NEXT
    elif action == "cancel":
        action_text = CANCEL_CREATE_NEXT
    else:
        action_text = DECLINE_CREATE_NEXT
    return Clarification(
        confirmed=False,
        declined=True,
        first_create=True,
        next_action=action_text,
    )


def skip_cards() -> Clarification:
    """Proceed when the client cannot show the card. ``ask_user`` stays."""
    stored = stored_zeus_url()
    url = stored if valid_public_url(stored) else env_prefill()
    return Clarification(
        confirmed=True,
        zeus_url=url,
        save_url=False,
        first_create=True,
        cards_accepted=False,
    )


@lru_cache(maxsize=32)
def _connection_form(url: str, username: str, password_ready: bool) -> type[BaseModel]:
    url_default = url
    username_default = username
    ready_default = password_ready

    class ZeusConnectionForm(BaseModel):
        zeus_url: str = Field(default=url_default, description=URL_FIELD_DESCRIPTION)
        zeus_username: str = Field(
            default=username_default,
            description="ZEUS_USERNAME for this app. This is a text field.",
        )
        password_in_env: bool = Field(
            default=ready_default,
            description=CONNECTION_PASSWORD_DESCRIPTION,
        )

    ZeusConnectionForm.__name__ = "ZeusConnectionForm"
    ZeusConnectionForm.__qualname__ = "ZeusConnectionForm"
    return ZeusConnectionForm


@lru_cache(maxsize=32)
def _llm_form(provider: str, model: str, key_ready: bool) -> type[BaseModel]:
    provider_default = provider if provider in _PROVIDER_IDS else "grok"
    model_default = model
    ready_default = key_ready

    class LlmSetupForm(BaseModel):
        llm_provider: Literal["grok", "openai", "anthropic", "gemini", "other"] = Field(
            default=provider_default,
            description="LLM provider. Other keeps the current LLM_BASE_URL.",
        )
        llm_model: str = Field(
            default=model_default,
            description="LLM_MODEL. The current model is the default.",
        )
        llm_key_in_env: bool = Field(
            default=ready_default,
            description=LLM_KEY_DESCRIPTION,
        )

    LlmSetupForm.__name__ = "LlmSetupForm"
    LlmSetupForm.__qualname__ = "LlmSetupForm"
    return LlmSetupForm


@lru_cache(maxsize=32)
def _couchbase_form(query_url: str, username: str, password_ready: bool) -> type[BaseModel]:
    url_default = query_url
    username_default = username
    ready_default = password_ready

    class CouchbaseForm(BaseModel):
        couchbase_query_url: str = Field(
            default=url_default,
            description=(
                "COUCHBASE_QUERY_URL. A string. "
                "Do not put a username or password in this URL."
            ),
        )
        couchbase_username: str = Field(
            default=username_default,
            description="COUCHBASE_USERNAME. A string. This is a text field.",
        )
        couchbase_password_in_env: bool = Field(
            default=ready_default,
            description=COUCHBASE_PASSWORD_DESCRIPTION,
        )

    CouchbaseForm.__name__ = "CouchbaseForm"
    CouchbaseForm.__qualname__ = "CouchbaseForm"
    return CouchbaseForm


def _content(answer: Any) -> dict[str, Any]:
    raw = getattr(answer, "content", None) or {}
    return dict(raw) if isinstance(raw, dict) else {}


def _unwrap_outcome(outcome: Any) -> Any:
    if DeclinedElicitation is not None and isinstance(outcome, DeclinedElicitation):
        return _declined_create("decline")
    if CancelledElicitation is not None and isinstance(outcome, CancelledElicitation):
        return _declined_create("cancel")
    if AcceptedElicitation is not None and isinstance(outcome, AcceptedElicitation):
        return outcome.data
    return outcome


def _couchbase_text(root: Path | None, key: str, default: str) -> str:
    """Prefill from the app ``.env``, then ``.env.example``. No process env."""
    from zeus_dev_helper_mcp.env_questions import (
        dotenv_example_nonsecret,
        dotenv_nonsecret,
    )

    found = dotenv_nonsecret(root, key)
    if found:
        return found
    found = dotenv_example_nonsecret(root, key)
    if found:
        return found
    return default


def _couchbase_password_ready(root: Path | None) -> bool:
    from zeus_dev_helper_mcp.env_questions import dotenv_present

    return dotenv_present(root, "COUCHBASE_PASSWORD")


def _couchbase_message(env_path: Path, exists: bool, *, userinfo: bool = False) -> str:
    if userinfo:
        lead = (
            "COUCHBASE_QUERY_URL must not include a username or password. "
            "Enter the query service URL without userinfo."
        )
    else:
        lead = "Confirm COUCHBASE_QUERY_URL and COUCHBASE_USERNAME for the yelp demo."
    if exists:
        where = (
            f"Put COUCHBASE_PASSWORD in {env_path}. "
            "You can edit that file while this card is open."
        )
    else:
        where = (
            f"This create will write {env_path}. "
            "Put COUCHBASE_PASSWORD there after the file appears."
        )
    return f"{lead} {where} Do not type the password into this form."


def _couchbase_url_of(answer: Any) -> str:
    return str(_content(answer).get("couchbase_query_url") or "")


def _ask_couchbase(ctx: Any, fn: Any, *, root: Path) -> Any:
    """Yelp Couchbase card. Decline, cancel, or userinfo writes nothing.

    A query URL with userinfo is asked once more. A second userinfo answer
    stops the create. An accept returns the same card so the SDK restores it.
    The retry is peeked first: that answer replaced the normal digest.
    """
    exists = _nonempty_dir(root)
    env_root = root if exists else None
    form = _couchbase_form(
        _couchbase_text(env_root, "COUCHBASE_QUERY_URL", COUCHBASE_URL_DEFAULT),
        _couchbase_text(env_root, "COUCHBASE_USERNAME", COUCHBASE_USERNAME_DEFAULT),
        _couchbase_password_ready(env_root),
    )
    env_path = root / ".env"
    normal = _couchbase_message(env_path, exists)
    retry = _couchbase_message(env_path, exists, userinfo=True)
    retry_answer = _peek(ctx, fn, retry, form)
    if retry_answer is not None:
        if retry_answer.action != "accept":
            return _declined_create(retry_answer.action, couchbase=True)
        if query_url_has_userinfo(_couchbase_url_of(retry_answer)):
            return Clarification(
                confirmed=False,
                first_create=True,
                next_action=COUCHBASE_USERINFO_NEXT,
            )
        return Elicit(retry, form)
    initial = _peek(ctx, fn, normal, form)
    if initial is not None and initial.action != "accept":
        return _declined_create(initial.action, couchbase=True)
    if initial is not None and query_url_has_userinfo(_couchbase_url_of(initial)):
        return Elicit(retry, form)
    return Elicit(normal, form)


def ask_yelp_couchbase(
    ctx: Any,
    fn: Any,
    outcome: Any,
    *,
    sample: str,
    root: Path,
) -> Any:
    """Ask the Couchbase card only for a yelp first create that can show a form."""
    from zeus_dev_helper_mcp.config import reload_config
    from zeus_dev_helper_mcp.sample_log import first_create_pending
    from zeus_dev_helper_mcp.yelp import is_yelp_demo_sample

    if not is_yelp_demo_sample(sample) or not _can_elicit(ctx):
        return _unwrap_outcome(outcome)
    if not first_create_pending(reload_config(), sample):
        return _unwrap_outcome(outcome)
    data = _unwrap_outcome(outcome)
    if isinstance(data, Clarification):
        if (
            data.declined
            or not data.confirmed
            or not data.first_create
            or not data.cards_accepted
        ):
            return data
        return _ask_couchbase(ctx, fn, root=root)
    if not hasattr(data, "password_in_env"):
        return data
    info = _connection_clarification(data)
    if not info.confirmed:
        return info
    return _ask_couchbase(ctx, fn, root=root)


def _merge_couchbase(info: Clarification, outcome: Any) -> Clarification:
    """Copy the accepted Couchbase strings. The password value is not on the form."""
    if outcome is None:
        return info
    data = _unwrap_outcome(outcome)
    if isinstance(data, Clarification):
        if data.declined or not data.confirmed:
            return data
        if data.couchbase_password_in_env is None:
            return info
        return info.model_copy(
            update={
                "couchbase_query_url": data.couchbase_query_url,
                "couchbase_username": data.couchbase_username,
                "couchbase_password_in_env": data.couchbase_password_in_env,
            }
        )
    if not hasattr(data, "couchbase_password_in_env"):
        return info
    url = str(getattr(data, "couchbase_query_url", "") or "").strip()
    if query_url_has_userinfo(url):
        return Clarification(
            confirmed=False,
            first_create=True,
            next_action=COUCHBASE_USERINFO_NEXT,
        )
    return info.model_copy(
        update={
            "couchbase_query_url": url,
            "couchbase_username": str(getattr(data, "couchbase_username", "") or "").strip(),
            "couchbase_password_in_env": bool(data.couchbase_password_in_env),
        }
    )


def _after_connection_card(
    ctx: Any,
    fn: Any,
    info: Clarification,
    *,
    sample: str,
    root: Path,
    couchbase: Any,
) -> Any:
    """Couchbase card, then the LLM card. Yelp only for Couchbase."""
    from zeus_dev_helper_mcp.yelp import is_yelp_demo_sample

    if is_yelp_demo_sample(sample) and info.first_create and info.cards_accepted:
        merged = _merge_couchbase(info, couchbase)
        if not merged.confirmed or merged.declined:
            return merged
        info = merged
    return _ask_llm(ctx, fn, sample=sample, root=root, info=info)


def ask_connection(
    ctx: Any,
    fn: Any,
    *,
    sample: str,
    root: Path,
) -> Any:
    exists = _nonempty_dir(root)
    env_root = root if exists else None
    env_path = root / ".env"
    form = _connection_form(
        _prefill_url(env_root),
        _prefill_username(sample, env_root),
        _password_ready(env_root),
    )
    message = _connection_message(env_path, exists)
    initial = _peek(ctx, fn, message, form)
    if initial is not None and initial.action != "accept":
        return _declined_create(initial.action)
    if initial is not None and not valid_public_url(
        str(_content(initial).get("zeus_url") or "")
    ):
        message = _connection_message(env_path, exists, hub=True)
    current = _peek(ctx, fn, message, form)
    if current is not None and current.action != "accept":
        return _declined_create(current.action)
    if (
        current is not None
        and message != _connection_message(env_path, exists)
        and not valid_public_url(str(_content(current).get("zeus_url") or ""))
    ):
        return Clarification(confirmed=False, first_create=True, next_action=HUB_NEXT)
    return Elicit(message, form)


def _connection_clarification(data: Any) -> Clarification:
    url = str(getattr(data, "zeus_url", "") or "").strip()
    username = str(getattr(data, "zeus_username", "") or "").strip()
    if not valid_public_url(url):
        return Clarification(confirmed=False, first_create=True, next_action=HUB_NEXT)
    return Clarification(
        confirmed=True,
        first_create=True,
        cards_accepted=True,
        zeus_url=url,
        zeus_username=username,
        save_url=True,
    )


def _ask_llm(ctx: Any, fn: Any, *, sample: str, root: Path, info: Clarification) -> Any:
    if not create_needs_llm_card(sample):
        return info
    if not _can_elicit(ctx):
        return info.model_copy(update={"cards_accepted": False})
    exists = _nonempty_dir(root)
    env_root = root if exists else None
    provider, model, base = _llm_prefill(env_root)
    form = _llm_form(provider, model, _llm_key_ready(env_root))
    message = _llm_message(root / ".env", exists)
    answer = _peek(ctx, fn, message, form)
    if answer is None:
        return Elicit(message, form)
    if answer.action != "accept":
        return _declined_create(answer.action, llm=True)
    from zeus_dev_helper_mcp.env_questions import llm_base_and_model

    content = _content(answer)
    chosen = str(content.get("llm_provider") or provider).strip().lower()
    chosen_model = str(content.get("llm_model") or model).strip()
    base_url, final_model = llm_base_and_model(chosen, chosen_model, base)
    return info.model_copy(
        update={
            "confirmed": True,
            "cards_accepted": True,
            "llm_provider": chosen,
            "llm_model": final_model,
            "llm_base_url": base_url,
        }
    )


def finish_connection(
    ctx: Any,
    fn: Any,
    outcome: Any,
    *,
    sample: str,
    root: Path,
    couchbase: Any = None,
) -> Any:
    """Turn a connection result into the LLM card.

    The yelp resolver passes the accepted Couchbase card as ``couchbase``.
    """
    if DeclinedElicitation is not None and isinstance(outcome, DeclinedElicitation):
        return _declined_create("decline")
    if CancelledElicitation is not None and isinstance(outcome, CancelledElicitation):
        return _declined_create("cancel")
    data = (
        outcome.data
        if AcceptedElicitation is not None and isinstance(outcome, AcceptedElicitation)
        else outcome
    )
    if isinstance(data, Clarification):
        if data.declined or not data.confirmed:
            return data
        if not data.first_create:
            return _resolve_auth(ctx, outcome, sample, fn)
        if not data.cards_accepted:
            return data
        return _after_connection_card(
            ctx, fn, data, sample=sample, root=root, couchbase=couchbase
        )
    if hasattr(data, "password_in_env"):
        info = _connection_clarification(data)
        if not info.confirmed:
            return info
        return _after_connection_card(
            ctx, fn, info, sample=sample, root=root, couchbase=couchbase
        )
    return _resolve_auth(ctx, outcome, sample, fn)
