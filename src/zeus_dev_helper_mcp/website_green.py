"""Install, start, and check a catalog website (ZDM-20, ZDM-21).

``smoke_test_zeus`` stays the health / ready / version / describe probe.
This tool checks the running page. A describe HTTP 200 is not a pass.
A search card whose name is only a title-cased ``doc_key`` or ``src_keys``
entry is ``fts_doc_key_only``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from zeus_dev_helper_mcp.config import HelperConfig, llm_key_in_process_env

POLL_TRIES = 20
POLL_PAUSE = 0.25
_PAGE = 24


def install_app(root: Path) -> dict[str, Any]:
    """Install ``requirements.txt`` when the app has one. Stdout stays out of the result."""
    req = root / "requirements.txt"
    if not req.is_file():
        return {"ok": True, "installed": False}
    python = root / ".venv" / "bin" / "python"
    exe = str(python) if python.is_file() else sys.executable
    try:
        proc = subprocess.run(
            [exe, "-m", "pip", "install", "-r", str(req)],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {
            "ok": False,
            "installed": False,
            "failure_class": "install_failed",
            "next_action": "Install the app requirements, then call website_green again.",
        }
    if proc.returncode != 0:
        return {
            "ok": False,
            "installed": False,
            "failure_class": "install_failed",
            "next_action": "pip install failed. Fix the app requirements, then retry website_green.",
        }
    return {"ok": True, "installed": True}


def start_app(root: Path, port: int) -> dict[str, Any]:
    """Start ``uvicorn main:app`` on the app port. Leaves the process running."""
    python = root / ".venv" / "bin" / "python"
    exe = str(python) if python.is_file() else sys.executable
    try:
        proc = subprocess.Popen(
            [
                exe,
                "-m",
                "uvicorn",
                "main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return {
            "ok": False,
            "started": False,
            "failure_class": "health_timeout",
            "next_action": "Start the app, then call website_green again.",
        }
    return {"ok": True, "started": True, "pid": proc.pid}


def _folded_title(value: str) -> str:
    """Compare key ``cains-ipa`` with a title-cased card ``Cains IPA``."""
    chars = [" " if ch in "-_:" else ch for ch in value.strip()]
    return " ".join("".join(chars).split()).casefold()


def _add_keys(raw: Any, found: list[str]) -> None:
    if isinstance(raw, str) and raw.strip():
        found.append(raw.strip())
        return
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.strip():
                found.append(item.strip())


def _collect_keys(value: Any, found: list[str]) -> None:
    if isinstance(value, dict):
        _add_keys(value.get("doc_key"), found)
        _add_keys(value.get("src_keys"), found)
        node = value.get("node")
        if isinstance(node, dict):
            _collect_keys(node, found)
        meta = value.get("metadata")
        if isinstance(meta, dict):
            _collect_keys(meta, found)
        return
    if isinstance(value, list):
        for item in value:
            _collect_keys(item, found)


def _is_key_title(name: str, keys: list[str]) -> bool:
    folded = _folded_title(name)
    if not folded:
        return False
    return any(_folded_title(key) == folded for key in keys)


def _document_field_name(card: dict[str, Any]) -> str:
    """``name`` or ``metadata.name`` from a find or get row. ``title`` does not count."""
    value = card.get("name")
    if isinstance(value, str) and value.strip():
        return value.strip()
    meta = card.get("metadata")
    if isinstance(meta, dict):
        nested = meta.get("name")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    return ""


def _sources(card: dict[str, Any]) -> list[dict[str, Any]]:
    sources = [card]
    meta = card.get("metadata")
    if isinstance(meta, dict):
        sources.append(meta)
    return sources


def card_display_name(card: dict[str, Any]) -> str:
    """Non-empty display name. A title-cased ``doc_key`` or ``src_keys`` entry is not a name."""
    found = ""
    for source in _sources(card):
        for key in ("name", "title"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                found = value.strip()
                break
        if found:
            break
    if not found:
        return ""
    keys: list[str] = []
    _collect_keys(card, keys)
    if keys and _is_key_title(found, keys):
        return ""
    return found


def _named_cards(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("cards")
    if not isinstance(raw, list):
        raw = payload.get("items")
    if not isinstance(raw, list):
        return []
    named: list[dict[str, Any]] = []
    for row in raw:
        if isinstance(row, dict) and card_display_name(row):
            named.append(row)
    return named


def _listen_port(root: Path) -> int:
    from zeus_dev_helper_mcp.beer import beer_listen_port

    for name in (".env", ".env.example"):
        path = root / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(line.strip().startswith("PORT=") for line in text.splitlines()):
            return beer_listen_port(root)
    marker = root / "sample_meta.json"
    if marker.is_file():
        try:
            meta = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        if isinstance(meta, dict) and meta.get("sample") == "catalog":
            return 8091
    main = root / "main.py"
    if main.is_file():
        try:
            source = main.read_text(encoding="utf-8", errors="replace")
        except OSError:
            source = ""
        if "/turn" in source and "/api/beers" not in source:
            return 8000
    return beer_listen_port(root)


def _is_api_app(root: Path) -> bool:
    main = root / "main.py"
    if not main.is_file():
        return False
    try:
        source = main.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return "/turn" in source and "/api/beers" not in source


def _resolve_root(cfg: HelperConfig, target_dir: str) -> Path | None:
    raw = (target_dir or "").strip()
    if raw:
        path = Path(raw).expanduser()
        return path if path.is_dir() else None
    from zeus_dev_helper_mcp.beer import load_recorded_beer_dir

    recorded = load_recorded_beer_dir(cfg)
    if recorded is not None and recorded.is_dir():
        return recorded
    return None


def _get_json(url: str) -> tuple[int, dict[str, Any], str]:
    try:
        response = httpx.get(url, timeout=2.0, trust_env=False)
    except httpx.HTTPError:
        return 0, {}, ""
    header = str(
        response.headers.get("X-Zeus-Req-Id")
        or response.headers.get("x-zeus-req-id")
        or ""
    ).strip()
    try:
        body = response.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    return response.status_code, body, header


def _remember(ids: list[str], header: str, body: dict[str, Any]) -> None:
    found = list(body.get("req_ids") or [])
    one = body.get("req_id")
    if isinstance(one, str):
        found.append(one)
    if header:
        found.append(header)
    for item in found:
        if isinstance(item, str) and item.strip() and item.strip() not in ids:
            ids.append(item.strip())


def _health(base: str) -> str:
    code, body, _header = _get_json(base + "/healthz")
    if code == 0:
        return "down"
    if code == 200 and str(body.get("status") or "") == "ok":
        return "up"
    return "busy"


def _poll_health(base: str) -> str:
    state = "down"
    for attempt in range(POLL_TRIES):
        state = _health(base)
        if state != "down":
            return state
        if attempt + 1 < POLL_TRIES:
            time.sleep(POLL_PAUSE)
    return state


def _result(**extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ok": False,
        "failure_class": None,
        "url": "",
        "list_count": 0,
        "search_card_count": 0,
        "req_ids": [],
        "pour_enabled": False,
        "search_skipped": False,
        "search_class": None,
        "describe_checked": False,
        "recommended_tools": ["diagnose_error"],
        "next_action": "",
    }
    out.update(extra)
    tools = [
        name
        for name in out.get("recommended_tools") or []
        if name != "smoke_test_agent"
    ]
    if out.get("ok"):
        tools = [name for name in tools if name != "diagnose_error"]
    out["recommended_tools"] = tools
    return out


def _mint_failure(cfg: HelperConfig) -> dict[str, Any] | None:
    mode = (cfg.zeus_auth_mode or "none").strip().lower()
    if mode != "basic":
        return None
    from zeus_dev_helper_mcp.readiness import mint_scope_session

    minted = mint_scope_session(cfg)
    if minted.get("ok"):
        return None
    failure = str(minted.get("failure_class") or "auth_failed")
    return _result(
        failure_class=failure,
        next_action=str(
            minted.get("next_action")
            or "The session mint failed. A describe 200 is not a login."
        ),
    )


def _label_is_of_zero(payload: dict[str, Any]) -> bool:
    label = str(payload.get("range_label") or "")
    return "of 0" in label


def _page_ids(payload: dict[str, Any]) -> list[str]:
    from zeus_dev_helper_mcp.beer import row_identities

    rows = (
        payload.get("cards")
        if isinstance(payload.get("cards"), list)
        else payload.get("items")
    )
    if not isinstance(rows, list):
        return []
    return row_identities(rows)


def _entity_name(payload: dict[str, Any], path: str) -> str:
    entity = str(payload.get("entity") or "").strip()
    if entity:
        return entity
    if "/api/beers" in path:
        return "Beer"
    if "/api/breweries" in path:
        return "Brewery"
    return ""


def _matches_scope(entity: str, types: list[str]) -> bool:
    if not entity or not types:
        return True
    wanted = entity.casefold()
    known = {item.casefold() for item in types}
    return wanted in known


def _search_rows(body: dict[str, Any]) -> list[dict[str, Any]]:
    raw = body.get("cards")
    if not isinstance(raw, list):
        raw = body.get("items")
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, dict)]


def _row_is_key_title(row: dict[str, Any], keys: list[str]) -> bool:
    for source in _sources(row):
        for field in ("name", "title"):
            value = source.get(field)
            if isinstance(value, str) and value.strip() and _is_key_title(value, keys):
                return True
    return False


def _search_outcome(body: dict[str, Any]) -> dict[str, Any]:
    """Passing search names come from ``name`` or ``metadata.name``, not a key title."""
    keys: list[str] = []
    for field in ("items", "cards", "gets", "get"):
        _collect_keys(body.get(field), keys)
    real = 0
    titled = False
    for row in _search_rows(body):
        doc_name = _document_field_name(row)
        if doc_name and not _is_key_title(doc_name, keys):
            real += 1
            continue
        if _row_is_key_title(row, keys):
            titled = True
    empty = str(body.get("empty_state") or "").strip()
    key_hit_without_name = real == 0 and (
        empty == "fts_doc_key_only" or (bool(keys) and not empty)
    )
    if titled or key_hit_without_name:
        return {
            "search_skipped": False,
            "search_card_count": 0,
            "search_class": None,
            "failure_class": "fts_doc_key_only",
            "pour_enabled": True,
        }
    if real:
        return {
            "search_skipped": False,
            "search_card_count": real,
            "search_class": None,
            "failure_class": None,
            "pour_enabled": True,
        }
    if empty:
        return {
            "search_skipped": False,
            "search_card_count": 0,
            "search_class": empty,
            "failure_class": None,
            "pour_enabled": True,
        }
    return {
        "search_skipped": False,
        "search_card_count": 0,
        "search_class": None,
        "failure_class": "search_empty",
        "pour_enabled": True,
    }


def _search_check(
    base: str,
    *,
    pour: bool,
    ids: list[str],
) -> dict[str, Any]:
    if not pour:
        return {
            "search_skipped": True,
            "search_card_count": 0,
            "search_class": None,
            "failure_class": None,
            "pour_enabled": False,
        }
    _code, body, header = _get_json(f"{base}/api/search?q=porter&limit={_PAGE}")
    _remember(ids, header, body)
    return _search_outcome(body)


def _record_website_green(cfg: HelperConfig, result: dict[str, Any]) -> None:
    """Remember ok and failure_class only. No URL, password, or session id."""
    path = cfg.state_dir / "website_green.json"
    payload = {
        "ok": bool(result.get("ok")),
        "failure_class": result.get("failure_class"),
    }
    try:
        cfg.state_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    except OSError:
        return


def website_green(cfg: HelperConfig, target_dir: str = "") -> dict[str, Any]:
    """Install, start, and check the catalog page.

    Calls the session mint when auth is basic. Does not call describe and
    does not call smoke_test_agent.
    """
    out = _run_website_green(cfg, target_dir)
    _record_website_green(cfg, out)
    return out


def _run_website_green(cfg: HelperConfig, target_dir: str = "") -> dict[str, Any]:
    blocked = _mint_failure(cfg)
    if blocked is not None:
        return blocked
    root = _resolve_root(cfg, target_dir)
    if root is None:
        return _result(
            failure_class="sample_dir_missing",
            next_action="use_sample writes the catalog, then website_green checks the page.",
        )
    port = _listen_port(root)
    base = f"http://127.0.0.1:{port}"
    state = _health(base)
    if state == "busy":
        return _result(
            failure_class="port_in_use",
            url=base,
            next_action=(
                f"{base} is open and is not this app. "
                "Do not start another process on this port."
            ),
        )
    if state == "down":
        installed = install_app(root)
        if not installed.get("ok"):
            return _result(
                failure_class=installed.get("failure_class") or "install_failed",
                url=base,
                next_action=str(installed.get("next_action") or ""),
            )
        started = start_app(root, port)
        if not started.get("ok"):
            return _result(
                failure_class=started.get("failure_class") or "health_timeout",
                url=base,
                next_action=str(started.get("next_action") or ""),
            )
        state = _poll_health(base)
    if state != "up":
        failure = "port_in_use" if state == "busy" else "health_timeout"
        return _result(
            failure_class=failure,
            url=base,
            next_action=f"{base}/healthz did not answer for this app.",
        )

    ids: list[str] = []
    _config_code, config, config_header = _get_json(base + "/api/config")
    _remember(ids, config_header, config)
    if "pour_enabled" in config:
        pour = bool(config.get("pour_enabled"))
    else:
        pour = llm_key_in_process_env()

    list_code, page, list_header = _get_json(f"{base}/api/beers?limit={_PAGE}")
    list_path = "/api/beers"
    if list_code == 404:
        list_code, page, list_header = _get_json(f"{base}/api/breweries?limit={_PAGE}")
        list_path = "/api/breweries"
    if list_code == 404:
        if _is_api_app(root) and state == "up":
            return _result(
                ok=True,
                url=base,
                list_count=0,
                search_skipped=True,
                pour_enabled=False,
                next_action=(
                    "API app health is up. This app has no catalog list route. "
                    "Do not call smoke_test_agent for that list."
                ),
                recommended_tools=[],
            )
        return _result(
            failure_class="list_route_missing",
            url=base,
            next_action="The app has no /api/beers list. A describe 200 is not the website check.",
        )
    _remember(ids, list_header, page)
    if _label_is_of_zero(page):
        return _result(
            failure_class="total_null_rendered_as_zero",
            url=base,
            req_ids=ids,
            pour_enabled=pour,
            next_action="The count label says of 0. A describe 200 does not fix that.",
        )
    named = _named_cards(page)
    if not named:
        return _result(
            failure_class="list_empty",
            url=base,
            list_count=0,
            req_ids=ids,
            pour_enabled=pour,
            next_action=(
                "The list has no named card. A describe 200 is not the website check."
            ),
        )
    page2_code, page2, page2_header = _get_json(
        f"{base}{list_path}?limit={_PAGE}&offset={_PAGE}"
    )
    if page2_code == 200:
        _remember(ids, page2_header, page2)
        first = _page_ids(page)
        second = _page_ids(page2)
        if first and second and first == second:
            return _result(
                failure_class="find_offset_ignored",
                url=base,
                list_count=len(named),
                req_ids=ids,
                pour_enabled=pour,
                next_action="Page 2 returned the same ids as page 1.",
            )

    entity = _entity_name(page, list_path)
    if (cfg.zeus_url or "").strip():
        from zeus_dev_helper_mcp.explain_scope import explain_scope

        summary = explain_scope(cfg)
        scope_id = str(summary.get("req_id") or "").strip()
        if scope_id and scope_id not in ids:
            ids.append(scope_id)
        types = [
            str(item) for item in summary.get("entity_types") or [] if str(item).strip()
        ]
        if summary.get("ok") and types and not _matches_scope(entity, types):
            return _result(
                failure_class="entity_not_in_scope",
                url=base,
                list_count=len(named),
                req_ids=ids,
                pour_enabled=pour,
                entity_types=types,
                next_action=(
                    f"List entity {entity} is not in the live scope. "
                    "Call explain_scope before inventing an entity."
                ),
            )

    searched = _search_check(base, pour=pour, ids=ids)
    if searched.get("failure_class"):
        failure = str(searched["failure_class"])
        if failure == "fts_doc_key_only":
            action = (
                "Search returned a doc_key or src_keys hit with no document name. "
                "A passing card needs name or metadata.name on a find or get row. "
                "Do not turn that key into a card title."
            )
        else:
            action = (
                "Search returned no named card and no empty-result class. "
                "Do not call smoke_test_agent."
            )
        return _result(
            failure_class=failure,
            url=base,
            list_count=len(named),
            search_card_count=0,
            req_ids=ids,
            pour_enabled=bool(searched.get("pour_enabled")),
            search_skipped=False,
            next_action=action,
        )
    skipped = bool(searched.get("search_skipped"))
    if skipped:
        action = (
            f"List has {len(named)} named card(s) at {base}. "
            "Pour is off, so search was not run. Do not call smoke_test_agent."
        )
    elif searched.get("search_class"):
        action = (
            f"List has {len(named)} named card(s). "
            f"Search is {searched['search_class']}."
        )
    else:
        action = (
            f"List has {len(named)} named card(s). "
            f"Search returned {searched['search_card_count']} named card(s) at {base}."
        )
    return _result(
        ok=True,
        url=base,
        list_count=len(named),
        search_card_count=int(searched.get("search_card_count") or 0),
        req_ids=ids,
        pour_enabled=bool(searched.get("pour_enabled")),
        search_skipped=skipped,
        search_class=searched.get("search_class"),
        next_action=action,
        recommended_tools=[],
    )
