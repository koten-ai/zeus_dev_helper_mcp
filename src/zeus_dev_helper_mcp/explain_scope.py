"""Live stamp summary and the generic catalog page (ZDM-14)."""

from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from zeus_dev_helper_mcp.config import HelperConfig

STAMP_NOTE = (
    "The offline zeus_chat_request file is what the client merges. "
    "The live stamp is the contract. fetch_chat_request is template only."
)
_VERBS = {"list": "find", "detail": "get", "search": "search"}
_ENTITY_RE = re.compile(r"^###\s+(?P<ent>.+?)\s+\(fields:\s*(?P<n>\d+)\)\s*$")
_FIELD_RE = re.compile(
    r"^\s+-\s+(?P<path>\S+)\s+(?P<kind>\S+)\s+\[(?P<idx>[^\]]+)\]"
    r"(?:\s+(?P<trailer>.*\S))?\s*$"
)
_FK_TO_RE = re.compile(r"fk_to=(\S+)")
_BEER_BUCKETS = frozenset({"beer-sample", "beer_sample", "beersample", "beer"})
_BEER_ENTITIES = frozenset({"beer", "brewery"})
DEFAULT_CATALOG_DIR = "demo_catalog_sample"


def _public_url(url: str) -> str:
    parts = urlsplit((url or "").strip())
    if not parts.username and not parts.password:
        return (url or "").strip().rstrip("/")
    host = parts.hostname or ""
    netloc = host
    if parts.port:
        netloc = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, "", "")).rstrip("/")


def _shapes() -> dict[str, str]:
    from zeus_dev_helper_mcp.walkthrough import RESULT_SHAPES

    return dict(RESULT_SHAPES)


def _empty(
    cfg: HelperConfig, failure_class: str, next_action: str, **extra: Any
) -> dict[str, Any]:
    out = {
        "ok": False,
        "failure_class": failure_class,
        "entity_types": [],
        "entities": [],
        "verbs": {},
        "req_id": "",
        "bucket": cfg.default_bucket or "",
        "scope": cfg.default_scope or "",
        "zeus_url": _public_url(cfg.zeus_url),
        "note": STAMP_NOTE,
        "result_shapes": _shapes(),
        "next_action": next_action,
    }
    out.update(extra)
    return out


def _system_text(doc: dict[str, Any]) -> str:
    messages = doc.get("messages") or []
    if messages and isinstance(messages[0], dict):
        content = str(messages[0].get("content") or "")
        if "## MINI-SCHEMA" in content:
            return content
    instr = doc.get("instructions") if isinstance(doc.get("instructions"), dict) else {}
    return str((instr or {}).get("system_prompt") or "")


def parse_mini_schema(text: str) -> dict[str, dict[str, dict[str, Any]]]:
    """Entity name → field path → kind / index / fk. No prompt text."""
    start = text.find("## MINI-SCHEMA")
    if start < 0:
        return {}
    rest = text[start:]
    nxt = re.search(r"\n##\s+(?!MINI-SCHEMA)", rest)
    block = rest[: nxt.start()] if nxt else rest
    entities: dict[str, dict[str, dict[str, Any]]] = {}
    current = ""
    for line in block.splitlines():
        header = _ENTITY_RE.match(line)
        if header:
            current = header.group("ent").strip()
            entities[current] = {}
            continue
        if not current:
            continue
        field = _FIELD_RE.match(line)
        if not field:
            continue
        trailer = field.group("trailer") or ""
        fk = _FK_TO_RE.search(trailer)
        entities[current][field.group("path")] = {
            "kind": field.group("kind"),
            "indexed": field.group("idx"),
            "fk_to": fk.group(1) if fk else "",
        }
    return entities


def _field_names(
    fields: dict[str, dict[str, Any]],
    *,
    display: bool = False,
    text: bool = False,
    fk: bool = False,
) -> list[str]:
    found: list[str] = []
    for path, meta in fields.items():
        kind = str(meta.get("kind") or "")
        indexed = str(meta.get("indexed") or "")
        matches = (
            (display and (kind == "display" or indexed == "display"))
            or (text and (kind == "text_fts" or indexed == "fts"))
            or (fk and (kind == "entity_fk" or bool(meta.get("fk_to"))))
        )
        if matches:
            found.append(path)
    return found


def summarize_entities(
    entities: dict[str, dict[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, fields in entities.items():
        rows.append(
            {
                "name": name,
                "display_fields": _field_names(fields, display=True),
                "text_search_fields": _field_names(fields, text=True),
                "fk_fields": _field_names(fields, fk=True),
            }
        )
    return rows


def summary_is_beer(bucket: str, entity_types: list[str]) -> bool:
    if (bucket or "").strip().lower() in _BEER_BUCKETS:
        return True
    names = {name.strip().casefold() for name in entity_types if name.strip()}
    return names == _BEER_ENTITIES


def _req_id(headers: httpx.Headers) -> str:
    return str(
        headers.get("X-Zeus-Req-Id") or headers.get("x-zeus-req-id") or ""
    ).strip()


def _auth(cfg: HelperConfig) -> httpx.Auth | None:
    mode = (cfg.zeus_auth_mode or "none").strip().lower()
    if mode != "basic":
        return None
    user = (
        os.environ.get("ZEUS_USERNAME") or os.environ.get("ZEUS_USER") or ""
    ).strip()
    password = (os.environ.get("ZEUS_PASSWORD") or "").strip()
    if not user or not password:
        return None
    return httpx.BasicAuth(user, password)


def _bearer_headers(cfg: HelperConfig) -> dict[str, str]:
    mode = (cfg.zeus_auth_mode or "none").strip().lower()
    if mode not in {"bearer", "session"}:
        return {}
    token = (
        os.environ.get("ZEUS_BEARER_TOKEN") or os.environ.get("ZEUS_SESSION_ID") or ""
    ).strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def explain_scope(cfg: HelperConfig) -> dict[str, Any]:
    """GET the live chat_request stamp and return entity fields only."""
    from zeus_dev_helper_mcp.readiness import _looks_like_hub

    url = _public_url(cfg.zeus_url)
    if not url:
        return _empty(
            cfg,
            "zeus_url_missing",
            "set_prereq with the public :8080 URL, bucket, and scope.",
        )
    if _looks_like_hub(url):
        return _empty(
            cfg,
            "wrong_port_hub_vs_public",
            "Use the public API :8080. explain_scope does not call Hub :9091.",
        )
    bucket = (cfg.default_bucket or "").strip()
    scope = (cfg.default_scope or "_default").strip() or "_default"
    mode = (cfg.default_mode or "analytics").strip() or "analytics"
    scoped = f"/v1/ai/chat_request.json?mode={mode}&bucket={bucket}&scope={scope}"
    plain = f"/v1/ai/chat_request.json?mode={mode}"
    try:
        with httpx.Client(
            timeout=5.0,
            auth=_auth(cfg),
            headers=_bearer_headers(cfg),
            trust_env=False,
        ) as client:
            response = client.get(url + scoped)
            if response.status_code >= 400:
                response = client.get(url + plain)
    except httpx.HTTPError:
        return _empty(
            cfg,
            "stamp_fetch_failed",
            "The live chat_request.json stamp did not answer. No entity types were filled in.",
        )
    req_id = _req_id(response.headers)
    if response.status_code == 401:
        return _empty(
            cfg,
            "auth_failed",
            "The live stamp returned HTTP 401. Fix the process login and call explain_scope again.",
            req_id=req_id,
        )
    if response.status_code != 200:
        return _empty(
            cfg,
            "stamp_fetch_failed",
            f"The live stamp returned HTTP {response.status_code}. No entity types were filled in.",
            req_id=req_id,
        )
    try:
        doc = response.json()
    except ValueError:
        doc = None
    if not isinstance(doc, dict):
        return _empty(
            cfg,
            "stamp_fetch_failed",
            "The live stamp was not a JSON object. No entity types were filled in.",
            req_id=req_id,
        )
    parsed = parse_mini_schema(_system_text(doc))
    entities = summarize_entities(parsed)
    if not entities:
        return _empty(
            cfg,
            "missing_mini_schema",
            "The live stamp has no MINI-SCHEMA entities. No entity types were filled in.",
            req_id=req_id,
        )
    return {
        "ok": True,
        "failure_class": None,
        "zeus_url": url,
        "bucket": bucket,
        "scope": scope,
        "mode": mode,
        "req_id": req_id,
        "entity_types": [row["name"] for row in entities],
        "entities": entities,
        "verbs": dict(_VERBS),
        "note": STAMP_NOTE,
        "result_shapes": _shapes(),
        "next_action": "use_sample(sample=catalog) writes a page from these fields.",
    }


def render_catalog_page(summary: dict[str, Any]) -> str:
    """Static page. Buttons, columns, and card lines come from the summary."""
    bucket = html.escape(str(summary.get("bucket") or "scope"))
    scope = html.escape(str(summary.get("scope") or "_default"))
    entities = (
        summary.get("entities") if isinstance(summary.get("entities"), list) else []
    )
    buttons: list[str] = []
    fields: list[str] = []
    for row in entities:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        safe = html.escape(name)
        buttons.append(f'<button type="button" data-entity="{safe}">{safe}</button>')
        for field in row.get("display_fields") or []:
            text = str(field).strip()
            if text and text not in fields:
                fields.append(text)
    if not fields:
        fields = ["name"]
    heads = "".join(
        f'<th data-field="{html.escape(field)}">{html.escape(field)}</th>'
        for field in fields
    )
    lines = "".join(
        f'<p class="card-line" data-field="{html.escape(field)}">{html.escape(field)}</p>'
        for field in fields
    )
    verb = summary.get("verbs") if isinstance(summary.get("verbs"), dict) else _VERBS
    list_verb = html.escape(str(verb.get("list") or "find"))
    detail_verb = html.escape(str(verb.get("detail") or "get"))
    search_verb = html.escape(str(verb.get("search") or "search"))
    return f"""<!DOCTYPE html>
<html lang="en" data-catalog="generic">
<head>
  <meta charset="utf-8" />
  <title>{bucket} / {scope}</title>
</head>
<body>
  <h1>{bucket} / {scope}</h1>
  <nav>{"".join(buttons)}</nav>
  <table><thead><tr>{heads}</tr></thead></table>
  <article class="card">{lines}</article>
  <p class="verbs">list {list_verb} · detail {detail_verb} · search {search_verb}</p>
</body>
</html>
"""


def _catalog_main(summary: dict[str, Any]) -> str:
    payload = {
        "zeus_url": _public_url(str(summary.get("zeus_url") or "")),
        "bucket": str(summary.get("bucket") or ""),
        "scope": str(summary.get("scope") or ""),
        "entities": summary.get("entity_types") or [],
        "verbs": summary.get("verbs") or dict(_VERBS),
    }
    blob = json.dumps(payload, indent=2)
    return f'''"""Generic catalog page. Fields come from the live stamp summary."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

app = FastAPI(title="Catalog UI")
ROOT = Path(__file__).resolve().parent
CONFIG = {blob}

@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {{"status": "ok", "sample": "catalog"}}


@app.get("/api/config")
def api_config() -> dict:
    return CONFIG


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")
'''


def write_catalog_sample(
    cfg: HelperConfig,
    summary: dict[str, Any],
    target_dir: str | Path,
) -> dict[str, Any]:
    """Write the generic page. Refuses to invent entities when the summary failed."""
    root = Path(target_dir).expanduser().resolve()
    if not summary.get("ok") or not summary.get("entity_types"):
        return {
            "ok": False,
            "written": False,
            "failure_class": summary.get("failure_class") or "stamp_fetch_failed",
            "entity_types": [],
            "entities": [],
            "local_dir": str(root),
            "note": STAMP_NOTE,
            "result_shapes": _shapes(),
            "next_action": summary.get("next_action")
            or "explain_scope must return entity types before the page is written.",
        }
    if root.exists() and any(root.iterdir()):
        marker = root / "sample_meta.json"
        current = False
        if marker.is_file():
            try:
                meta = json.loads(marker.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                meta = {}
            current = isinstance(meta, dict) and meta.get("sample") == "catalog"
        if not current:
            return {
                "ok": False,
                "written": False,
                "failure_class": "foreign_sample_dir",
                "local_dir": str(root),
                "entity_types": list(summary.get("entity_types") or []),
                "result_shapes": _shapes(),
                "next_action": "Pick an empty directory. This one was not written.",
            }
    root.mkdir(parents=True, exist_ok=True)
    (root / "static").mkdir(parents=True, exist_ok=True)
    page = render_catalog_page(summary)
    (root / "static" / "index.html").write_text(page, encoding="utf-8")
    (root / "main.py").write_text(_catalog_main(summary), encoding="utf-8")
    (root / "requirements.txt").write_text(
        "fastapi>=0.115.0\nuvicorn[standard]>=0.30.0\n",
        encoding="utf-8",
    )
    readme = (
        f"# {root.name}\n\n"
        f"Catalog page for `{summary.get('bucket')}` / `{summary.get('scope')}`.\n"
        "Buttons are the entity types from the live stamp. "
        "Columns and card lines are the display fields.\n"
        f"{STAMP_NOTE}\n"
    )
    (root / "README.md").write_text(readme, encoding="utf-8")
    meta = {
        "sample": "catalog",
        "bucket": summary.get("bucket") or "",
        "scope": summary.get("scope") or "",
        "entity_types": list(summary.get("entity_types") or []),
    }
    (root / "sample_meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "ok": True,
        "written": True,
        "local_dir": str(root),
        "project_name": root.name,
        "entity_types": list(summary.get("entity_types") or []),
        "entities": summary.get("entities") or [],
        "verbs": summary.get("verbs") or dict(_VERBS),
        "catalog_kind": "generic",
        "note": STAMP_NOTE,
        "result_shapes": _shapes(),
        "run": f"cd {root} && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && uvicorn main:app --port 8091",
        "next_action": (
            "Open the catalog page. Buttons and card lines are the live stamp fields. "
            + STAMP_NOTE
        ),
    }


def _catalog_dest(*, sample_dir: str, project_name: str, parent_dir: str) -> Path:
    from zeus_dev_helper_mcp.beer import sanitize_beer_dir_name

    parent = (
        Path(parent_dir).expanduser().resolve() if parent_dir.strip() else Path.cwd()
    )
    raw = sample_dir.strip()
    if raw:
        return Path(raw).expanduser().resolve()
    name = (
        sanitize_beer_dir_name(project_name)
        if project_name.strip()
        else DEFAULT_CATALOG_DIR
    )
    return parent / name


def use_catalog_sample(
    cfg: HelperConfig,
    *,
    sample_dir: str = "",
    project_name: str = "",
    parent_dir: str = "",
) -> dict[str, Any]:
    """sample=catalog. Beer copy only for beer-sample or Beer + Brewery."""
    dest = _catalog_dest(
        sample_dir=sample_dir,
        project_name=project_name,
        parent_dir=parent_dir,
    )
    if summary_is_beer(cfg.default_bucket or "", []):
        from zeus_dev_helper_mcp.scaffold import use_sample

        out = use_sample(
            cfg,
            sample="beer",
            sample_dir=sample_dir,
            project_name=project_name,
            parent_dir=parent_dir,
        )
        out["catalog_kind"] = "beer"
        return out
    summary = explain_scope(cfg)
    if summary.get("ok") and summary_is_beer(
        "", list(summary.get("entity_types") or [])
    ):
        from zeus_dev_helper_mcp.scaffold import use_sample

        out = use_sample(
            cfg,
            sample="beer",
            sample_dir=sample_dir,
            project_name=project_name,
            parent_dir=parent_dir,
        )
        out["catalog_kind"] = "beer"
        out["explain_scope"] = {
            "entity_types": summary.get("entity_types") or [],
            "req_id": summary.get("req_id") or "",
            "note": STAMP_NOTE,
        }
        return out
    if not summary.get("ok"):
        summary["written"] = False
        summary["local_dir"] = str(dest)
        summary["entity_types"] = []
        summary["entities"] = []
        return summary
    written = write_catalog_sample(cfg, summary, dest)
    written["req_id"] = summary.get("req_id") or ""
    written["zeus_url"] = summary.get("zeus_url") or ""
    return written
