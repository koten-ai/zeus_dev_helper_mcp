"""V2 verb encyclopedia + MINI-SCHEMA lint (ZDH-18). Coach only — never POST."""

from __future__ import annotations

import json
import re
from typing import Any

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.docs_links import docs_url

# Static table from Zeus docs/API/API.md + docs/API/V2/find.md. Do not scrape Hub.
_BARE = "bare"
_SCOPE = "scope"
_COLLECTION = "collection"
_NAMED = "named_query"

_MONGO_OPS = ("$gt", "$gte", "$lt", "$lte", "$ne", "$in", "$nin", "$regex", "$exists", "$eq", "$and", "$or", "$not")

_FTS_KEY_RE = re.compile(r"^(biz|file|src):", re.IGNORECASE)

_VERBS: dict[str, dict[str, Any]] = {
    "explain": {
        "path_class": _BARE,
        "http_path": "POST /v2/{verb}",
        "demux": None,
        "siblings": ["return", "find"],
        "direct_ok": True,
        "summary": "Query planner (no Couchbase). Bare POST /v2/explain.",
    },
    "return": {
        "path_class": _BARE,
        "http_path": "POST /v2/{verb}",
        "demux": None,
        "siblings": ["explain", "pipeline"],
        "direct_ok": True,
        "summary": "Emit the final answer (return_result). Bare POST /v2/return.",
    },
    "describe": {
        "path_class": _SCOPE,
        "http_path": "POST /v2/{bucket}/{scope}/{verb}",
        "demux": "include[] (stats, entity_types, edge_types, modes, tools, indexes)",
        "siblings": ["find", "analyze"],
        "direct_ok": True,
        "summary": "Scope orientation: entity types / stats. Discovery, not rows.",
    },
    "analyze": {
        "path_class": _SCOPE,
        "http_path": "POST /v2/{bucket}/{scope}/{verb}",
        "demux": "job (communities, duplicates, super_nodes, …)",
        "siblings": ["find", "describe", "pipeline"],
        "direct_ok": True,
        "summary": "Named analytics job. job is required. pending ≠ broken.",
    },
    "get": {
        "path_class": _COLLECTION,
        "http_path": "POST /v2/{bucket}/{scope}/{collection}/{verb}",
        "demux": "ids[] → batch_get_nodes (graph n_* tokens, not FTS biz: keys)",
        "siblings": ["find", "search", "project"],
        "direct_ok": True,
        "summary": "Hydrate 1..50 graph node ids. Not source doc keys.",
    },
    "find": {
        "path_class": _COLLECTION,
        "http_path": "POST /v2/{bucket}/{scope}/{collection}/{verb}",
        "demux": (
            "return is the router: rows|ids → find_nodes; count → count_nodes; "
            "selectivity → entity_selectivity; rows/ids + via_entity → entity_mentions; "
            "rows/ids + overlap_with → docs_sharing_entity"
        ),
        "siblings": ["search", "get", "pipeline"],
        "direct_ok": True,
        "summary": "Type-and-predicate lookup. where is equality-only; MINI-SCHEMA is authoritative.",
    },
    "search": {
        "path_class": _COLLECTION,
        "http_path": "POST /v2/{bucket}/{scope}/{collection}/{verb}",
        "demux": "strategy (vector|semantic|fts|hybrid|spatial) + optional target",
        "siblings": ["find", "get", "pipeline"],
        "direct_ok": True,
        "summary": "Recall. strategy is required. Typeahead UI uses rt.data.search (not this raw verb only).",
    },
    "traverse": {
        "path_class": _COLLECTION,
        "http_path": "POST /v2/{bucket}/{scope}/{collection}/{verb}",
        "demux": None,
        "siblings": ["find", "search", "get"],
        "direct_ok": True,
        "summary": "Graph expansion / FK walks from an id set.",
    },
    "set": {
        "path_class": _COLLECTION,
        "http_path": "POST /v2/{bucket}/{scope}/{collection}/{verb}",
        "demux": None,
        "siblings": ["order", "enrich", "project", "pipeline"],
        "direct_ok": True,
        "summary": "Pipeline transform: bind a value. Usually inside pipeline, not a lone Direct call.",
    },
    "order": {
        "path_class": _COLLECTION,
        "http_path": "POST /v2/{bucket}/{scope}/{collection}/{verb}",
        "demux": None,
        "siblings": ["set", "enrich", "project", "pipeline"],
        "direct_ok": True,
        "summary": "Pipeline transform: sort a prior id/row set.",
    },
    "enrich": {
        "path_class": _COLLECTION,
        "http_path": "POST /v2/{bucket}/{scope}/{collection}/{verb}",
        "demux": None,
        "siblings": ["set", "order", "project", "pipeline"],
        "direct_ok": True,
        "summary": "Pipeline transform: join extra fields onto a prior set.",
    },
    "project": {
        "path_class": _COLLECTION,
        "http_path": "POST /v2/{bucket}/{scope}/{collection}/{verb}",
        "demux": None,
        "siblings": ["get", "find", "pipeline"],
        "direct_ok": True,
        "summary": "Shape/hydrate a prior id set. Do not pass FTS biz: keys as node ids.",
    },
    "pipeline": {
        "path_class": _COLLECTION,
        "http_path": "POST /v2/{bucket}/{scope}/{collection}/{verb}",
        "demux": "steps[] of read/transform verbs; not exposed on Direct",
        "siblings": ["find", "search", "traverse", "analyze"],
        "direct_ok": False,
        "summary": "Server-side read-only DAG. Rejected on Direct (rt.data.verb). Use agent-for-pipeline.",
    },
    "named_query": {
        "path_class": _NAMED,
        "http_path": "POST /v2/{bucket}/{scope}/named_queries/{name}/execute",
        "demux": None,
        "siblings": ["find", "search"],
        "direct_ok": True,
        "summary": "Execute a stored named query. Not a free-form find.",
    },
}

_VERB_ALIASES = {
    "named_queries": "named_query",
    "named-query": "named_query",
    "execute": "named_query",
    "run_find": "find",
    "run_get": "get",
    "run_search": "search",
    "run_describe": "describe",
}


def _norm_verb(name: str) -> str:
    raw = (name or "").strip().lower().replace("-", "_")
    return _VERB_ALIASES.get(raw, raw)


def _docs() -> dict[str, str]:
    return {
        "api": docs_url("zeus/developers/api/probes.md"),
        "using": docs_url("zeus-client/using-zeus-client.md"),
        "errors": docs_url("zeus-client/errors.md"),
    }


def explain_verb(cfg: HelperConfig, *, name: str) -> dict[str, Any]:
    """Static verb encyclopedia. Does not call Zeus."""
    key = _norm_verb(name)
    entry = _VERBS.get(key)
    if not entry:
        return {
            "ok": False,
            "name": name,
            "known_verbs": sorted(_VERBS.keys()),
            "next_action": "Pass a V2 verb (find, search, get, describe, pipeline, …)",
            "docs": _docs(),
        }
    out: dict[str, Any] = {
        "ok": True,
        "name": key,
        "path_class": entry["path_class"],
        "http_path": entry["http_path"],
        "demux": entry["demux"],
        "siblings": list(entry["siblings"]),
        "direct_ok": entry["direct_ok"],
        "summary": entry["summary"],
        "docs": _docs(),
    }
    if not entry["direct_ok"]:
        out["not_on_direct"] = True
        out["next_action"] = (
            "pipeline is not on Direct. recommend_surface(intent=multi_step) → agent-for-pipeline"
        )
    elif key == "find":
        out["pitfalls"] = [
            "return is the router — wrong return silently picks the wrong v1 tool",
            "where is equality-only; {\"abv\":{\"$gt\":5}} matches nothing",
            "where keys must exist in the scope MINI-SCHEMA",
        ]
        out["next_action"] = "lint_verb_args before POST; never invent where operators"
    elif key in ("get", "project"):
        out["pitfalls"] = [
            "Ids are graph node tokens (n_*), not FTS biz: / file: source keys",
        ]
        out["next_action"] = "lint_verb_args if ids came from typeahead/FTS"
    else:
        out["next_action"] = "lint_verb_args with optional mini_schema; suggest_verb_call drafts only"
    return out


def _parse_json(value: Any, *, field: str) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as e:
            raise ValueError(f"{field} is not valid JSON: {e}") from e
    raise ValueError(f"{field} must be a JSON object/array or JSON string")


def _schema_fields(mini_schema: Any) -> set[str] | None:
    """Return allowed where/field names, or None if schema not supplied."""
    if mini_schema is None or mini_schema == "" or mini_schema == {}:
        return None
    names: set[str] = set()
    if isinstance(mini_schema, str):
        mini_schema = json.loads(mini_schema)
    if isinstance(mini_schema, list):
        for item in mini_schema:
            if isinstance(item, str) and item.strip():
                names.add(item.strip())
            elif isinstance(item, dict):
                names.update(_schema_fields(item) or [])
        return names or None
    if isinstance(mini_schema, dict):
        # {fields: [...]} or {Beer: ["abv", ...]} or {entity_types: [{name, fields}]}
        if "fields" in mini_schema and isinstance(mini_schema["fields"], list):
            for f in mini_schema["fields"]:
                if isinstance(f, str):
                    names.add(f)
                elif isinstance(f, dict) and f.get("name"):
                    names.add(str(f["name"]))
        for k, v in mini_schema.items():
            if k in ("fields", "entity_types", "types", "properties"):
                nested = _schema_fields(v)
                if nested:
                    names.update(nested)
            elif isinstance(v, list) and v and all(isinstance(x, str) for x in v):
                names.update(v)
                names.add(k)
            elif isinstance(v, dict):
                nested = _schema_fields(v)
                if nested:
                    names.update(nested)
        return names or None
    return None


def _field_names_from_describe(payload: Any, *, cap: int = 200) -> list[str]:
    """Entity type + field names only — never document bodies."""
    names: list[str] = []
    seen: set[str] = set()

    def add(s: str) -> None:
        s = (s or "").strip()
        if not s or s in seen or len(names) >= cap:
            return
        seen.add(s)
        names.append(s)

    def walk(node: Any, hint: str = "") -> None:
        if len(names) >= cap:
            return
        if isinstance(node, dict):
            for key in ("name", "type", "entity_type", "id"):
                val = node.get(key)
                if isinstance(val, str) and hint in ("entity", "field", "type"):
                    add(val)
            fields = node.get("fields") or node.get("properties") or node.get("attributes")
            if isinstance(fields, list):
                for f in fields:
                    if isinstance(f, str):
                        add(f)
                    elif isinstance(f, dict):
                        fname = f.get("name") or f.get("field") or f.get("path")
                        if isinstance(fname, str):
                            add(fname)
            ents = node.get("entity_types") or node.get("entities") or node.get("types")
            if isinstance(ents, list):
                for e in ents:
                    walk(e, "entity")
            if "result" in node:
                walk(node["result"])
            # Mini-schema brief sometimes nests under mini_schema / schema
            for k in ("mini_schema", "schema", "brief"):
                if k in node:
                    walk(node[k])
        elif isinstance(node, list):
            for item in node:
                walk(item, hint)

    walk(payload)
    return names


def _probe_mini_schema(cfg: HelperConfig) -> tuple[list[str] | None, str | None]:
    """Optional live describe — field names only. Skip if Zeus is down."""
    if not cfg.zeus_url or not cfg.default_bucket or not cfg.default_scope:
        return None, "no_live_target"
    if ":9091" in (cfg.zeus_url or ""):
        return None, "wrong_port_hub_vs_public"
    try:
        import httpx

        from zeus_dev_helper_mcp.smoke import (
            describe_scope_url,
            request_auth,
            request_headers,
        )
    except Exception as e:  # noqa: BLE001
        return None, f"import:{e}"

    url = describe_scope_url(cfg)
    if not url:
        return None, "no_live_target"
    try:
        with httpx.Client(timeout=httpx.Timeout(8.0, connect=3.0), headers=request_headers()) as client:
            r = client.post(url, json={"include": ["entity_types"]}, auth=request_auth())
        if r.status_code >= 400:
            return None, f"http_{r.status_code}"
        payload = r.json()
    except Exception:  # noqa: BLE001 — Zeus down: skip schema rules
        return None, "zeus_unavailable"

    fields = _field_names_from_describe(payload)
    return (fields or None), None


def _where_issues(where: Any, schema: set[str] | None) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if where is None:
        return issues
    if not isinstance(where, dict):
        issues.append(
            {
                "code": "where_not_equality",
                "path": "where",
                "message": "where must be an object of equality pairs, not an array/operator tree",
                "failure_class": "where_not_in_mini_schema",
            }
        )
        return issues
    for key, val in where.items():
        path = f"where.{key}"
        if str(key).startswith("$"):
            issues.append(
                {
                    "code": "where_not_equality",
                    "path": path,
                    "message": f"where key {key!r} is an operator; Zeus where is equality-only",
                    "failure_class": "where_not_in_mini_schema",
                }
            )
            continue
        if schema is not None and key not in schema:
            issues.append(
                {
                    "code": "where_key_not_in_schema",
                    "path": path,
                    "message": f"where key {key!r} is not in MINI-SCHEMA",
                    "failure_class": "where_not_in_mini_schema",
                }
            )
        if isinstance(val, dict):
            ops = [k for k in val if str(k).startswith("$") or str(k) in _MONGO_OPS]
            issues.append(
                {
                    "code": "where_not_equality",
                    "path": path,
                    "message": (
                        f"where.{key} uses nested operators {ops or list(val)}; "
                        "equality only (e.g. {\"abv\": 5} not {\"abv\":{\"$gt\":5}})"
                    ),
                    "failure_class": "where_not_in_mini_schema",
                }
            )
        elif isinstance(val, list):
            issues.append(
                {
                    "code": "where_not_equality",
                    "path": path,
                    "message": f"where.{key} is a list; equality-only scalars are required",
                    "failure_class": "where_not_in_mini_schema",
                }
            )
    return issues


def _collect_ids(body: dict[str, Any]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for key in ("ids", "id", "node_ids", "node_id"):
        val = body.get(key)
        if isinstance(val, str):
            found.append((key, val))
        elif isinstance(val, list):
            for i, item in enumerate(val):
                if isinstance(item, str):
                    found.append((f"{key}[{i}]", item))
    return found


def lint_verb_args(
    cfg: HelperConfig,
    *,
    verb: str,
    body: Any = None,
    mini_schema: Any = None,
    use_live_schema: bool = True,
) -> dict[str, Any]:
    """Lint a would-be verb body. Never POSTs. Optional live MINI-SCHEMA field names."""
    key = _norm_verb(verb)
    issues: list[dict[str, str]] = []
    schema_source = "none"
    schema: set[str] | None = None
    live_note = None

    try:
        parsed = _parse_json(body, field="body")
    except ValueError as e:
        return {
            "ok": False,
            "verb": verb,
            "issues": [
                {
                    "code": "invalid_json",
                    "path": "body",
                    "message": str(e),
                    "failure_class": "dispatch_failed",
                }
            ],
            "posted": False,
            "docs": _docs(),
        }
    if parsed is None:
        parsed = {}
    if not isinstance(parsed, dict):
        return {
            "ok": False,
            "verb": key,
            "issues": [
                {
                    "code": "invalid_json",
                    "path": "body",
                    "message": "body must be a JSON object",
                    "failure_class": "dispatch_failed",
                }
            ],
            "posted": False,
            "docs": _docs(),
        }

    if key not in _VERBS and key:
        issues.append(
            {
                "code": "unknown_verb",
                "path": "verb",
                "message": f"unknown verb {verb!r}",
                "failure_class": "dispatch_failed",
            }
        )

    if key == "pipeline" or (isinstance(parsed.get("steps"), list) and key in ("pipeline", "")):
        issues.append(
            {
                "code": "pipeline_on_direct",
                "path": "verb",
                "message": "pipeline is not on Direct; use recommend_surface(intent=multi_step)",
                "failure_class": "pipeline_not_on_direct",
            }
        )

    try:
        caller_schema = _schema_fields(mini_schema) if mini_schema not in (None, "") else None
    except (json.JSONDecodeError, ValueError) as e:
        return {
            "ok": False,
            "verb": key,
            "issues": [
                {
                    "code": "invalid_json",
                    "path": "mini_schema",
                    "message": f"mini_schema is not valid JSON: {e}",
                    "failure_class": "dispatch_failed",
                }
            ],
            "posted": False,
            "docs": _docs(),
        }

    if caller_schema:
        schema = caller_schema
        schema_source = "caller"
    elif use_live_schema:
        live_fields, live_note = _probe_mini_schema(cfg)
        if live_fields:
            schema = set(live_fields)
            schema_source = "live_describe"
        elif live_note and live_note not in ("no_live_target",):
            schema_source = f"skipped:{live_note}"

    if "where" in parsed:
        issues.extend(_where_issues(parsed.get("where"), schema))

    if key in ("get", "project", "find", "search", "traverse"):
        for path, ident in _collect_ids(parsed):
            if _FTS_KEY_RE.match(ident) or ident.startswith("biz:"):
                issues.append(
                    {
                        "code": "fts_key_as_node_id",
                        "path": path,
                        "message": (
                            f"{ident!r} looks like an FTS/source key, not a graph node id (n_*). "
                            "get/project with biz: keys come back missing."
                        ),
                        "failure_class": "fts_key_used_as_node_id",
                    }
                )

    ok = not issues
    return {
        "ok": ok,
        "verb": key or verb,
        "issues": issues,
        "schema_source": schema_source,
        "schema_field_count": len(schema) if schema is not None else 0,
        "posted": False,
        "docs": _docs(),
        "next_action": (
            "Fix issues then call Zeus from the app (this tool does not POST)"
            if issues
            else "Body looks legal; POST from the app / rt.data.verb — helper does not POST"
        ),
    }


def suggest_verb_call(
    cfg: HelperConfig,
    *,
    goal: str,
    mini_schema: Any = None,
    use_live_schema: bool = True,
) -> dict[str, Any]:
    """Draft a legal verb body. Guidance only — does not POST."""
    g = (goal or "").strip().lower()
    schema: set[str] | None = None
    schema_source = "none"
    try:
        caller_schema = _schema_fields(mini_schema) if mini_schema not in (None, "") else None
    except (json.JSONDecodeError, ValueError) as e:
        return {
            "ok": False,
            "posted": False,
            "error": f"mini_schema is not valid JSON: {e}",
            "docs": _docs(),
        }
    if caller_schema:
        schema = caller_schema
        schema_source = "caller"
    elif use_live_schema:
        live_fields, note = _probe_mini_schema(cfg)
        if live_fields:
            schema = set(live_fields)
            schema_source = "live_describe"
        elif note:
            schema_source = f"skipped:{note}"

    notes: list[str] = ["Guidance only — this tool does not POST to Zeus."]
    if any(w in g for w in ("pipeline", "multi-step", "multi step", "then find", "dag")):
        return {
            "ok": True,
            "posted": False,
            "verb": None,
            "surface": "agent-for-pipeline",
            "body": None,
            "schema_source": schema_source,
            "notes": notes
            + [
                "Do not draft Direct pipeline JSON. recommend_surface(intent=multi_step).",
            ],
            "docs": _docs(),
            "next_action": "Use rt.agent.run_turn / catalog pipeline — not rt.data.verb('pipeline')",
        }

    if any(w in g for w in ("describe", "entity type", "what's in", "what is in", "schema", "mini-schema")):
        verb = "describe"
        body: dict[str, Any] = {"include": ["stats", "entity_types", "edge_types"]}
    elif any(w in g for w in ("typeahead", "autocomplete", "suggest", "as-you-type")):
        verb = "search"
        body = {"strategy": "fts", "query_text": (goal or "").strip()[:120]}
        notes.append("Typeahead: prefer rt.data.search (Trace-Class direct.interactive).")
    elif any(w in g for w in ("hydrate", "get by id", "node id", "n_")) or g.startswith("get "):
        verb = "get"
        body = {"ids": [], "include": ["summary"]}
        notes.append("Fill ids with graph n_* tokens from find/search — not biz: FTS keys.")
    elif any(w in g for w in ("traverse", "neighbor", "hop", "edge")):
        verb = "traverse"
        body = {"ids": [], "limit": 20}
    elif any(w in g for w in ("analy", "communit", "duplicate", "outlier")):
        verb = "analyze"
        body = {"job": "communities"}
        notes.append("job is the router; pending means the offline model has not run yet.")
    else:
        verb = "find"
        body = {"return": "ids", "limit": 20}
        # Prefer an entity type that looks like a schema key with a capital letter
        if schema:
            types = [s for s in sorted(schema) if s[:1].isupper()]
            fields = [s for s in sorted(schema) if s[:1].islower()]
            if types:
                body["entity_type"] = types[0]
            # equality-only example using a real field name if present
            if fields:
                body["where"] = {fields[0]: "<equality-value>"}
                notes.append("where is equality-only; replace the placeholder with a scalar.")
        notes.append("find.return is the router (ids|rows|count|selectivity).")

    lint = lint_verb_args(
        cfg,
        verb=verb,
        body=body,
        mini_schema=sorted(schema) if schema else None,
        use_live_schema=False,
    )
    # Placeholder equality values are not schema misses; strip placeholder-only nits
    issues = [
        i
        for i in (lint.get("issues") or [])
        if i.get("code") != "where_key_not_in_schema"
        or (body.get("where") or {}) != {"<equality-value>": None}
    ]

    info = explain_verb(cfg, name=verb)
    return {
        "ok": True,
        "posted": False,
        "verb": verb,
        "path_class": info.get("path_class"),
        "http_path": info.get("http_path"),
        "body": body,
        "issues": issues,
        "schema_source": schema_source,
        "notes": notes,
        "docs": _docs(),
        "next_action": "Copy the draft into the app; helper does not POST",
    }
