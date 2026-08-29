"""Runtime config + app anti-example linters (ZDH-24). Redact secrets in output."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.docs_links import docs_url

_SECRET_KEY = re.compile(r"(password|secret|token|api[_-]?key|authorization|bearer)", re.IGNORECASE)
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")
_HASH_LIT = re.compile(r"md5:[0-9a-fA-F]{32}")
_AUTH_MODES = {"none", "basic", "bearer", "session", "certificate"}


def _issue(field: str, level: str, message: str, failure_class: str | None = None) -> dict[str, str]:
    out = {"field": field, "level": level, "message": message}
    if failure_class:
        out["failure_class"] = failure_class
    return out


def _looks_secret_value(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    s = value.strip()
    if _ENV_NAME.match(s):
        return False  # env *name*, not a value
    return not s.startswith(("${", "env:"))


def redact_public(obj: Any) -> Any:
    """Deep copy with secret-looking values replaced. Never emit passwords/tokens."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if _SECRET_KEY.search(str(k)) and _looks_secret_value(v):
                out[k] = "***"
            else:
                out[k] = redact_public(v)
        return out
    if isinstance(obj, list):
        return [redact_public(x) for x in obj[:40]]
    if isinstance(obj, str) and len(obj) > 24 and _SECRET_KEY.search(obj):
        return "***"
    return obj


def _dig(doc: dict[str, Any], *keys: str) -> Any:
    cur: Any = doc
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def lint_runtime_config(cfg: HelperConfig, *, path: str) -> dict[str, Any]:
    """Lint a client config.json. Issues[] match validate_env shape. Secrets redacted."""
    _ = cfg
    p = Path(path).expanduser()
    if not p.is_file():
        return {
            "ok": False,
            "issues": [_issue("path", "error", f"not a file: {p}")],
            "docs": docs_url("zeus-client/config-reference.md"),
        }
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {
            "ok": False,
            "issues": [_issue("json", "error", f"invalid JSON: {e}")],
            "docs": docs_url("zeus-client/config-reference.md"),
        }
    if not isinstance(doc, dict):
        return {
            "ok": False,
            "issues": [_issue("json", "error", "config must be a JSON object")],
            "docs": docs_url("zeus-client/config-reference.md"),
        }

    issues: list[dict[str, str]] = []
    zeus = doc.get("zeus") if isinstance(doc.get("zeus"), dict) else {}
    url = str((zeus or {}).get("url") or doc.get("zeus_url") or "")
    if not url:
        issues.append(_issue("zeus.url", "warn", "zeus.url missing"))
    elif ":9091" in url or url.rstrip("/").endswith(":9091") or "/hub" in url.lower():
        issues.append(
            _issue(
                "zeus.url",
                "error",
                "Hub :9091 / /hub — app path must use public :8080",
                "wrong_port_hub_vs_public",
            )
        )
    elif ":8080" not in url and "localhost" in url:
        issues.append(_issue("zeus.url", "warn", "public API is usually :8080"))

    auth = str((zeus or {}).get("auth_mode") or doc.get("auth_mode") or "").strip().lower()
    if auth and auth not in _AUTH_MODES:
        issues.append(_issue("zeus.auth_mode", "error", f"unknown auth_mode {auth!r}"))
    elif not auth:
        issues.append(_issue("zeus.auth_mode", "warn", "auth_mode not set (none|basic|bearer|…)"))

    def _scan_secrets(obj: Any, prefix: str) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                loc = f"{prefix}.{k}" if prefix else k
                if _SECRET_KEY.search(str(k)) and _looks_secret_value(v):
                    issues.append(
                        _issue(
                            loc,
                            "error",
                            "secret-looking value in config — store env *names* (e.g. ZEUS_PASSWORD), not values",
                        )
                    )
                else:
                    _scan_secrets(v, loc)

    _scan_secrets(doc, "")

    samples = doc.get("samples") if isinstance(doc.get("samples"), dict) else {}
    default_sample = doc.get("default_sample")
    target = None
    if default_sample and isinstance(samples.get(default_sample), dict):
        target = samples[default_sample]
    elif isinstance(doc.get("target"), dict):
        target = doc["target"]
    if isinstance(target, dict):
        missing = [k for k in ("bucket", "scope", "collection") if not target.get(k)]
        if missing:
            issues.append(_issue("target", "warn", f"target triple missing {missing}"))
    else:
        issues.append(_issue("target", "warn", "no samples[default_sample] / target {bucket,scope,collection}"))

    ai_pr = _dig(doc, "settings", "ai_process_result")
    if ai_pr is True:
        issues.append(
            _issue(
                "settings.ai_process_result",
                "warn",
                "ai_process_result is true — cheap path default is false",
            )
        )

    sc = _dig(doc, "session", "semantic_cache", "enabled")
    if sc is True:
        issues.append(
            _issue(
                "session.semantic_cache.enabled",
                "warn",
                "semantic_cache enabled — default is false (needs Zeus >= 0.7.6)",
            )
        )

    ok = not any(i.get("level") == "error" for i in issues)
    return {
        "ok": ok,
        "path": str(p),
        "issues": issues,
        "public": redact_public(doc),
        "docs": docs_url("zeus-client/config-reference.md"),
        "next_action": "Fix errors; keep secrets in env; leave semantic_cache off unless opted in",
    }


def _scan_python(text: str, label: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    lines = text.splitlines()

    def _first_line(pred) -> int | None:
        for i, ln in enumerate(lines, 1):
            if pred(ln):
                return i
        return None

    imp = _first_line(
        lambda ln: "import zeus_client" in ln or "from zeus_client" in ln
    )
    env = _first_line(
        lambda ln: (
            "load_dotenv" in ln
            or "os.environ" in ln
            or "load_runtime_config" in ln
            or "getenv(" in ln
        )
    )
    if imp is not None and (env is None or imp < env):
        issues.append(
            _issue(
                label,
                "warn",
                f"zeus_client import at line {imp} before env/config load — set env first",
            )
        )

    run_count = sum(1 for ln in lines if "asyncio.run(" in ln)
    if run_count >= 2:
        issues.append(
            _issue(
                label,
                "warn",
                f"asyncio.run appears {run_count} times — smell of per-request event loops",
            )
        )

    if re.search(r"\bZeusClient\b", text) or re.search(r"\brun_agent\b", text):
        issues.append(
            _issue(
                label,
                "warn",
                "ZeusClient / run_agent is the V1 surface; 2.3 default is ZeusRuntime + run_turn "
                "(V1 lives under zeus_client.compat.v1)",
            )
        )

    lits = _HASH_LIT.findall(text)
    if lits:
        issues.append(
            _issue(
                label,
                "error",
                f"contract_hash literal {lits[0]} in source — bind from stamped catalog, never invent",
                "contract_hash_invent_forbidden",
            )
        )
    return issues


def _scan_dockerfile(text: str, label: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if "localhost:8080" in text or "127.0.0.1:8080" in text:
        issues.append(
            _issue(
                label,
                "warn",
                "localhost:8080 inside a Dockerfile usually cannot reach Zeus on the host — "
                "use host.docker.internal or a compose service name",
            )
        )
    if ":9091" in text:
        issues.append(
            _issue(
                label,
                "error",
                "Hub :9091 in Dockerfile — app path is public :8080",
                "wrong_port_hub_vs_public",
            )
        )
    return issues


def lint_app_code(cfg: HelperConfig, *, path: str) -> dict[str, Any]:
    """Anti-example scan of main.py (and sibling Dockerfiles if path is a dir)."""
    _ = cfg
    root = Path(path).expanduser()
    issues: list[dict[str, str]] = []
    scanned: list[str] = []
    if not root.exists():
        return {
            "ok": False,
            "issues": [_issue("path", "error", f"not found: {root}")],
            "docs": docs_url("zeus-client/using-zeus-client.md"),
        }

    files: list[Path] = []
    if root.is_file():
        files.append(root)
        if root.parent.is_dir():
            files.extend(sorted(root.parent.glob("Dockerfile*")))
    else:
        main = root / "main.py"
        if main.is_file():
            files.append(main)
        files.extend(sorted(root.glob("Dockerfile*")))
        if not files:
            return {
                "ok": False,
                "issues": [_issue("path", "error", f"no main.py or Dockerfile under {root}")],
                "docs": docs_url("zeus-client/using-zeus-client.md"),
            }

    seen: set[Path] = set()
    for f in files:
        rp = f.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        scanned.append(str(f))
        text = f.read_text(encoding="utf-8", errors="replace")
        name = f.name
        if name.endswith(".py"):
            issues.extend(_scan_python(text, str(f)))
        elif name.startswith("Dockerfile"):
            issues.extend(_scan_dockerfile(text, str(f)))

    ok = not any(i.get("level") == "error" for i in issues)
    return {
        "ok": ok,
        "scanned": scanned,
        "issues": issues,
        "docs": docs_url("zeus-client/using-zeus-client.md"),
        "next_action": (
            "Prefer ZeusRuntime, env-before-import, no hash literals, no :9091 in app images"
        ),
    }
