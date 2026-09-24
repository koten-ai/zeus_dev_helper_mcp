"""Ask for a public Zeus URL, then auth mode, before a first-green write.

The URL form runs only when ``prereqs.json`` has no ``zeus_url``. Host
``ZEUS_URL`` is a prefill. Passwords never appear in the form or the result.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any, Literal

import httpx
from pydantic import BaseModel, Field

from zeus_dev_helper_mcp.beer import is_beer_sample

try:
    from mcp.server.elicitation import (
        AcceptedElicitation,
        CancelledElicitation,
        DeclinedElicitation,
        ElicitationResult,
        render_elicitation_schema,
    )
    from mcp.server.mcpserver import Context
    from mcp.server.mcpserver.resolve import (
        Elicit,
        Resolve,
        _decode_state,
        _request_digest,
    )
    from mcp_types import ElicitRequest, ElicitRequestFormParams, ElicitResult

    HAS_ELICIT = True
except ImportError:  # mcp 1.x has no resolver elicitation
    AcceptedElicitation = None  # type: ignore[misc, assignment]
    CancelledElicitation = None  # type: ignore[misc, assignment]
    DeclinedElicitation = None  # type: ignore[misc, assignment]
    Context = Any  # type: ignore[misc, assignment]
    Elicit = None  # type: ignore[misc, assignment]
    HAS_ELICIT = False

URL_MESSAGE = (
    "Enter the public Zeus URL (port 8080). If you do not have one, ask your admin."
)
HUB_MESSAGE = (
    "That URL is not the public Zeus API. "
    "Enter an http(s) URL on port 8080. Hub port 9091 is not the app path. "
    "If you do not have one, ask your admin."
)
AUTH_MESSAGE = (
    "This Zeus URL requires authentication. "
    "Put the username and password in ZEUS_USERNAME and ZEUS_PASSWORD, "
    "or a token in ZEUS_BEARER_TOKEN. "
    "Do not type the password into this form. "
    "Then confirm the auth mode."
)
URL_FIELD_DESCRIPTION = (
    "Public Zeus API base URL on port 8080. Ask your admin if you do not have one."
)
COACH_URL_NEXT = (
    "Ask the user for the public Zeus URL (port 8080). "
    "If they do not have one, they should ask their admin. "
    "Leave zeus_url empty so this tool can show the form, "
    "or call set_prereq with the URL they give you. "
    "Do not copy the host ZEUS_URL. Do not pass a password."
)
HUB_NEXT = (
    "That URL is not the public Zeus API. "
    "Enter an http(s) URL on port 8080. Hub port 9091 is not the app path. "
    "If you do not have one, ask your admin."
)
DECLINE_URL_NEXT = (
    "Zeus URL is required before continuing. "
    "Enter the public URL on port 8080, or ask your admin."
)
CANCEL_URL_NEXT = (
    "Zeus URL entry was cancelled. "
    "Enter the public URL on port 8080, or ask your admin."
)
AUTH_COACH_NEXT = (
    "This Zeus URL returned 401 or 403. "
    "Ask the user to put credentials in ZEUS_USERNAME and ZEUS_PASSWORD "
    "or ZEUS_BEARER_TOKEN, then call set_prereq with auth_mode and presence flags only. "
    "Do not pass the password."
)
DECLINE_AUTH_NEXT = (
    "Authentication is required for this Zeus URL. "
    "Set ZEUS_USERNAME and ZEUS_PASSWORD, or ZEUS_BEARER_TOKEN, in the environment. "
    "Do not pass the password into a tool."
)

_ENV_MAP = {
    "zeus_url": "ZEUS_URL",
    "auth_mode": "ZEUS_AUTH_MODE",
    "bucket": "ZEUS_BUCKET",
    "scope": "ZEUS_SCOPE",
    "collection": "ZEUS_COLLECTION",
    "mode": "ZEUS_MODE",
    "role": "ZEUS_HELPER_ROLE",
}


class _Unasked:
    def __repr__(self) -> str:
        return "UNASKED"


UNASKED = _Unasked()


class Clarification(BaseModel):
    confirmed: bool = False
    zeus_url: str = ""
    auth_mode: str = ""
    has_username: bool | None = None
    has_password: bool | None = None
    has_bearer: bool | None = None
    save_url: bool = False
    save_auth: bool = False
    declined: bool = False
    next_action: str | None = None


class AuthModeForm(BaseModel):
    auth_mode: Literal["none", "basic", "bearer"] = Field(
        description="How this Zeus deployment authenticates."
    )
    credentials_ready: bool = Field(
        description=(
            "True after ZEUS_USERNAME and ZEUS_PASSWORD, or ZEUS_BEARER_TOKEN, "
            "are set in the environment."
        )
    )


@dataclass(frozen=True)
class Gate:
    proceed: bool
    direct: bool = False
    zeus_url: str = ""
    auth_mode: str = ""
    has_username: bool | None = None
    has_password: bool | None = None
    has_bearer: bool | None = None
    save_url: bool = False
    save_auth: bool = False
    next_action: str | None = None


def valid_public_url(url: str) -> bool:
    """True for an http(s) public API URL. Hub :9091 and userinfo are rejected."""
    raw = (url or "").strip()
    lowered = raw.lower()
    if not lowered.startswith(("http://", "https://")):
        return False
    if ":9091" in raw or raw.rstrip("/").endswith(":9091"):
        return False
    rest = raw.split("://", 1)[1].strip()
    if not rest or rest.startswith("/"):
        return False
    host = rest.split("/", 1)[0]
    return "@" not in host


def url_decision(argument: str, stored: str) -> str:
    """``use``, ``ask``, or ``reject``. Env ``ZEUS_URL`` is not an input."""
    arg = (argument or "").strip()
    kept = (stored or "").strip()
    if arg:
        return "use" if valid_public_url(arg) else "reject"
    if valid_public_url(kept):
        return "use"
    return "ask"


def env_prefill() -> str:
    raw = (os.environ.get("ZEUS_URL") or "").strip()
    return raw if valid_public_url(raw) else ""


def stored_zeus_url() -> str:
    from zeus_dev_helper_mcp.config import reload_config
    from zeus_dev_helper_mcp.prereqs import load_prereqs

    return str(load_prereqs(reload_config()).get("zeus_url") or "").strip()


def credentials_for(mode: str) -> dict[str, Any]:
    """Presence only. Flags are included when the required env vars exist."""
    mode_l = (mode or "").strip().lower()
    if mode_l == "none":
        return {"ok": True, "auth_mode": "none"}
    if mode_l == "bearer":
        ok = bool(os.environ.get("ZEUS_BEARER_TOKEN") or os.environ.get("ZEUS_TOKEN"))
        out: dict[str, Any] = {"ok": ok, "auth_mode": "bearer"}
        if ok:
            out["has_bearer"] = True
        return out
    if mode_l == "basic":
        has_username = bool(
            os.environ.get("ZEUS_USERNAME") or os.environ.get("ZEUS_USER")
        )
        has_password = bool(os.environ.get("ZEUS_PASSWORD"))
        ok = has_username and has_password
        out = {"ok": ok, "auth_mode": "basic"}
        if ok:
            out["has_username"] = True
            out["has_password"] = True
        return out
    return {"ok": False, "auth_mode": mode_l}


def satisfied_auth() -> dict[str, Any] | None:
    basic = credentials_for("basic")
    if basic["ok"]:
        return basic
    bearer = credentials_for("bearer")
    if bearer["ok"]:
        return bearer
    return None


def creds_next(mode: str) -> str:
    if (mode or "").strip().lower() == "bearer":
        return (
            "Set ZEUS_BEARER_TOKEN in the environment, then call this tool again. "
            "Do not pass the token into the tool."
        )
    return (
        "Set ZEUS_USERNAME and ZEUS_PASSWORD in the environment "
        "(or ZEUS_BEARER_TOKEN for bearer auth), then call this tool again. "
        "Do not pass the password into the tool."
    )


def probe_auth_required(url: str, bucket: str, scope: str) -> str:
    """``unauthorized``, ``open``, or ``unreachable``.

    GET the scope bootstrap path. Only 401 and 403 mean credentials are required.
    ``POST .../auth/session`` is the login route and is not used as the signal.
    """
    base = (url or "").strip().rstrip("/")
    path = f"/v1/ai/bootstrap/scope/{bucket}/{scope}"
    try:
        response = httpx.get(
            base + path,
            timeout=httpx.Timeout(5.0, connect=3.0),
            follow_redirects=False,
        )
    except httpx.HTTPError:
        return "unreachable"
    if response.status_code in (401, 403):
        return "unauthorized"
    return "open"


def probe_target(sample: str) -> tuple[str, str] | None:
    """Bucket/scope to probe. Beer with nothing stored uses beer-sample/_default."""
    from zeus_dev_helper_mcp.config import reload_config
    from zeus_dev_helper_mcp.prereqs import load_prereqs

    prefs = load_prereqs(reload_config())
    bucket = str(prefs.get("bucket") or "").strip()
    scope = str(prefs.get("scope") or "").strip()
    if bucket:
        return bucket, scope or "_default"
    if is_beer_sample(sample):
        return "beer-sample", "_default"
    return None


def auth_form_schema() -> dict[str, Any]:
    schema = AuthModeForm.model_json_schema()
    if HAS_ELICIT:
        schema = render_elicitation_schema(AuthModeForm)
    return schema


@lru_cache(maxsize=8)
def _url_form(prefill: str) -> type[BaseModel]:
    default = prefill

    class ZeusUrlForm(BaseModel):
        zeus_url: str = Field(default=default, description=URL_FIELD_DESCRIPTION)

    ZeusUrlForm.__name__ = "ZeusUrlForm"
    ZeusUrlForm.__qualname__ = "ZeusUrlForm"
    return ZeusUrlForm


def persist_gate(gate: Gate) -> None:
    """Write non-secret routing and presence flags. Idempotent."""
    from zeus_dev_helper_mcp.config import reload_config
    from zeus_dev_helper_mcp.prereqs import save_prereqs

    payload: dict[str, Any] = {}
    if gate.save_url and gate.zeus_url:
        payload["zeus_url"] = gate.zeus_url
    if gate.save_auth and gate.auth_mode:
        payload["auth_mode"] = gate.auth_mode
    if gate.has_username is not None:
        payload["has_username"] = gate.has_username
    if gate.has_password is not None:
        payload["has_password"] = gate.has_password
    if gate.has_bearer is not None:
        payload["has_bearer"] = gate.has_bearer
    if not payload:
        return
    stored = save_prereqs(reload_config(), payload)
    for key, env_name in _ENV_MAP.items():
        val = stored.get(key)
        if val is not None and str(val).strip() != "":
            os.environ[env_name] = str(val).strip()
    reload_config()


def interpret_gate(outcome: Any) -> Gate:
    if outcome is UNASKED:
        return Gate(proceed=True, direct=True)
    if DeclinedElicitation is not None and isinstance(outcome, DeclinedElicitation):
        return Gate(proceed=False, next_action=DECLINE_URL_NEXT)
    if CancelledElicitation is not None and isinstance(outcome, CancelledElicitation):
        return Gate(proceed=False, next_action=CANCEL_URL_NEXT)
    data = (
        outcome.data
        if AcceptedElicitation is not None and isinstance(outcome, AcceptedElicitation)
        else outcome
    )
    if isinstance(data, Clarification):
        if data.declined or not data.confirmed:
            return Gate(
                proceed=False,
                zeus_url=data.zeus_url,
                save_url=bool(data.save_url and data.zeus_url),
                next_action=data.next_action or DECLINE_URL_NEXT,
            )
        return Gate(
            proceed=True,
            zeus_url=data.zeus_url,
            auth_mode=data.auth_mode,
            has_username=data.has_username,
            has_password=data.has_password,
            has_bearer=data.has_bearer,
            save_url=bool(data.save_url and data.zeus_url),
            save_auth=bool(data.save_auth and data.auth_mode),
        )
    url = str(getattr(data, "zeus_url", "") or "").strip()
    if valid_public_url(url):
        return Gate(proceed=True, zeus_url=url, save_url=True)
    return Gate(proceed=False, next_action=HUB_NEXT)


def _can_elicit(ctx: Any) -> bool:
    if not HAS_ELICIT:
        return False
    try:
        caps = ctx.client_capabilities
    except Exception:  # noqa: BLE001 — no session means no form
        return False
    if caps is None or getattr(caps, "elicitation", None) is None:
        return False
    elic = caps.elicitation
    return elic.form is not None or elic.url is None


def _wire_key(fn: Any) -> str:
    qualname = getattr(fn, "__qualname__", None) or type(fn).__qualname__
    module = getattr(fn, "__module__", None) or type(fn).__module__
    return f"{module}:{qualname}"


def _digest(message: str, schema: type[BaseModel]) -> str:
    request = ElicitRequest(
        params=ElicitRequestFormParams(
            message=message,
            requested_schema=render_elicitation_schema(schema),
        )
    )
    return _request_digest(request)


def _peek(ctx: Any, fn: Any, message: str, schema: type[BaseModel]) -> Any | None:
    """Return the answer only when it was given for this exact question."""
    responses = getattr(ctx, "input_responses", None) or {}
    key = _wire_key(fn)
    answer = responses.get(key)
    if not isinstance(answer, ElicitResult):
        return None
    state = _decode_state(getattr(ctx, "request_state", None))
    if state.asked.get(key) != _digest(message, schema):
        return None
    return answer


def _content_url(answer: Any) -> str:
    content = getattr(answer, "content", None) or {}
    return str(content.get("zeus_url") or "").strip()


def _declined_clarification(action: str) -> Clarification:
    if action == "cancel":
        return Clarification(
            confirmed=False, declined=True, next_action=CANCEL_URL_NEXT
        )
    return Clarification(confirmed=False, declined=True, next_action=DECLINE_URL_NEXT)


def _resolve_url(ctx: Any, argument: str, fn: Any) -> Any:
    arg = (argument or "").strip()
    if arg:
        if valid_public_url(arg):
            return Clarification(confirmed=True, zeus_url=arg, save_url=True)
        if not _can_elicit(ctx):
            return Clarification(confirmed=False, next_action=HUB_NEXT)
    else:
        stored = stored_zeus_url()
        if valid_public_url(stored):
            return Clarification(confirmed=True, zeus_url=stored, save_url=False)
        if not _can_elicit(ctx):
            return Clarification(confirmed=False, next_action=COACH_URL_NEXT)
    if not _can_elicit(ctx):
        return Clarification(
            confirmed=False, next_action=HUB_NEXT if arg else COACH_URL_NEXT
        )

    form = _url_form(env_prefill() if not arg else "")
    message = HUB_MESSAGE if arg else URL_MESSAGE
    if not arg:
        initial = _peek(ctx, fn, URL_MESSAGE, form)
        if (
            initial is not None
            and initial.action == "accept"
            and not valid_public_url(_content_url(initial))
        ):
            message = HUB_MESSAGE
        elif initial is not None and initial.action != "accept":
            return _declined_clarification(initial.action)
    current = _peek(ctx, fn, message, form)
    if current is not None and current.action != "accept":
        return _declined_clarification(current.action)
    if (
        current is not None
        and current.action == "accept"
        and message == HUB_MESSAGE
        and not valid_public_url(_content_url(current))
    ):
        return Clarification(confirmed=False, next_action=HUB_NEXT)
    # A valid accept is returned as the same Elicit so the SDK stores it in
    # request_state. The following auth round then restores it instead of asking again.
    return Elicit(message, form)


def _as_clarification(outcome: Any) -> Clarification:
    if DeclinedElicitation is not None and isinstance(outcome, DeclinedElicitation):
        return _declined_clarification("decline")
    if CancelledElicitation is not None and isinstance(outcome, CancelledElicitation):
        return _declined_clarification("cancel")
    data = (
        outcome.data
        if AcceptedElicitation is not None and isinstance(outcome, AcceptedElicitation)
        else outcome
    )
    if isinstance(data, Clarification):
        return data
    url = str(getattr(data, "zeus_url", "") or "").strip()
    if valid_public_url(url):
        return Clarification(confirmed=True, zeus_url=url, save_url=True)
    return Clarification(confirmed=False, next_action=HUB_NEXT)


def _apply_auth_flags(info: Clarification, creds: dict[str, Any]) -> Clarification:
    return info.model_copy(
        update={
            "confirmed": True,
            "auth_mode": str(creds.get("auth_mode") or ""),
            "save_auth": True,
            "save_url": info.save_url,
            "has_username": creds.get("has_username"),
            "has_password": creds.get("has_password"),
            "has_bearer": creds.get("has_bearer"),
        }
    )


def _resolve_auth(ctx: Any, url_outcome: Any, sample: str, fn: Any) -> Any:
    info = _as_clarification(url_outcome)
    if not info.confirmed:
        return info
    target = probe_target(sample)
    if target is None:
        return info
    status = probe_auth_required(info.zeus_url, target[0], target[1])
    if status != "unauthorized":
        return info
    already = satisfied_auth()
    if already is not None:
        return _apply_auth_flags(info, already)
    if not _can_elicit(ctx):
        return info.model_copy(
            update={"confirmed": False, "next_action": AUTH_COACH_NEXT}
        )
    answer = _peek(ctx, fn, AUTH_MESSAGE, AuthModeForm)
    if answer is None:
        return Elicit(AUTH_MESSAGE, AuthModeForm)
    if answer.action != "accept":
        return Clarification(
            confirmed=False,
            declined=True,
            zeus_url=info.zeus_url,
            save_url=bool(info.zeus_url),
            next_action=DECLINE_AUTH_NEXT,
        )
    content = answer.content or {}
    mode = str(content.get("auth_mode") or "").strip().lower()
    ready = bool(content.get("credentials_ready"))
    if mode == "none":
        return info.model_copy(update={"auth_mode": "none", "save_auth": True})
    creds = credentials_for(mode)
    if not ready or not creds["ok"]:
        return Clarification(
            confirmed=False,
            zeus_url=info.zeus_url,
            save_url=bool(info.zeus_url),
            next_action=creds_next(mode),
        )
    return _apply_auth_flags(info, creds)


if HAS_ELICIT:

    def clarify_url(ctx: Context) -> Elicit[Any] | Clarification:  # type: ignore[valid-type]
        """URL gate for tools that do not take a zeus_url argument."""
        return _resolve_url(ctx, "", clarify_url)

    def clarify_url_argument(
        ctx: Context, zeus_url: str = ""
    ) -> Elicit[Any] | Clarification:  # type: ignore[valid-type]
        """URL gate for set_prereq. A non-empty valid argument skips the form."""
        return _resolve_url(ctx, zeus_url, clarify_url_argument)

    def clarify_project(
        ctx: Context,
        url: Annotated[ElicitationResult[Clarification], Resolve(clarify_url)],
        sample: str = "",
    ) -> Elicit[Any] | Clarification:  # type: ignore[valid-type]
        """Auth gate after the URL gate."""
        return _resolve_auth(ctx, url, sample, clarify_project)

    def clarify_scaffold(
        ctx: Context,
        url: Annotated[ElicitationResult[Clarification], Resolve(clarify_url)],
    ) -> Elicit[Any] | Clarification:  # type: ignore[valid-type]
        """Auth gate for scaffold_app, which has no sample argument."""
        return _resolve_auth(ctx, url, "", clarify_scaffold)
