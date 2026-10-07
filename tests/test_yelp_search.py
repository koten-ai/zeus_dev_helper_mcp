"""Behavior of the live chat-request search patch.

The clone test checks that search.py, client.ts, and vite.config.ts change.
These tests run the patched search helper: the scope document has to carry the
scope brief, and a login failure stays a failure.
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

from zeus_dev_helper_mcp.yelp_search import apply_yelp_live_search

_DOC = {
    "messages": [
        {
            "role": "system",
            "content": "hello\n## SCOPE BRIEF\nbrief\n## MINI-SCHEMA\nschema\n",
        }
    ]
}


def _search_source(*, turns: bool = True) -> str:
    indent = "        "
    lines = [
        "from pathlib import Path",
        "",
        "class ClientSettings:",
        "    def __init__(self, ai_process_result: bool = False) -> None:",
        "        self.ai_process_result = ai_process_result",
        "",
        "DEMO_OUTPUT_SCHEMA: dict = {}",
        "CHATS: dict = {}",
        "",
        "async def run_agent(*args, **kwargs):",
        "    raise NotImplementedError",
        "",
        "async def run_search(",
        "    query: str,",
        "):",
        f"{indent}settings = ClientSettings(ai_process_result=bool(ai_process_result))",
        f"{indent}answer, trace, new_turns, session_meta, structured = await run_agent(",
        f"{indent}    zeus_url,",
        f"{indent}    zcfg,",
        f"{indent}    base_catalog_dirs=base_catalog_dirs,",
        f"{indent})",
    ]
    if turns:
        lines.extend(["", f'{indent}CHATS[chat_id]["turns"] = new_turns'])
    lines.append(f"{indent}return answer, trace, session_meta, structured")
    return "\n".join(lines) + "\n"


def _load(path: Path) -> dict:
    namespace: dict = {"__name__": "yelp_search_under_test"}
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)  # noqa: S102
    return namespace


def _install_catalog(monkeypatch, doc: object) -> dict:
    seen: dict = {}

    async def load_live_chat_request(zeus_url, mode, bucket, scope, extra):
        seen.update(
            zeus_url=zeus_url,
            mode=mode,
            bucket=bucket,
            scope=scope,
            extra=extra,
        )
        return doc

    package = types.ModuleType("zeus_client")
    package.__path__ = []
    zeus = types.ModuleType("zeus_client.zeus")
    zeus.__path__ = []
    catalog = types.ModuleType("zeus_client.zeus.catalog")
    catalog.load_live_chat_request = load_live_chat_request
    monkeypatch.setitem(sys.modules, "zeus_client", package)
    monkeypatch.setitem(sys.modules, "zeus_client.zeus", zeus)
    monkeypatch.setitem(sys.modules, "zeus_client.zeus.catalog", catalog)
    return seen


def _bind(namespace: dict, run_agent) -> None:
    namespace["run_agent"] = run_agent
    namespace["ai_process_result"] = False
    namespace["zeus_url"] = "https://zeus.example:8080"
    namespace["zcfg"] = {"auth_mode": "basic", "username": "user"}
    namespace["base_url"] = "https://llm.example"
    namespace["api_key"] = "test-key"
    namespace["model"] = "grok"
    namespace["api_version"] = "2024"
    namespace["mode"] = "analytics"
    namespace["bucket"] = "yelp-demo"
    namespace["scope"] = "_default"
    namespace["collection"] = "business"
    namespace["message"] = "tacos"
    namespace["prior_turns"] = []
    namespace["provider_id"] = "xai"
    namespace["chat_id"] = "c1"
    namespace["prior_sid"] = ""
    namespace["prior_round"] = 0
    namespace["base_id"] = "base"
    namespace["base_catalog_dirs"] = []
    namespace["CHATS"] = {"c1": {}}


def _patched_search(tmp_path: Path) -> dict:
    root = tmp_path / "demo_yelp"
    path = root / "src" / "local_guide" / "search.py"
    path.parent.mkdir(parents=True)
    path.write_text(_search_source(), encoding="utf-8")
    report = apply_yelp_live_search(root)
    assert "src/local_guide/search.py" in report["patched"]
    assert report["live_chat_request"] is False
    body = path.read_text(encoding="utf-8")
    assert body.count("def fetch_search_chat_request") == 1
    assert "login failed" not in body
    assert 'auth_mode"] = "none"' not in body
    assert apply_yelp_live_search(root)["patched"] == []
    assert path.read_text(encoding="utf-8").count("def fetch_search_chat_request") == 1
    return _load(path)


def _coordinate_sources() -> tuple[str, str]:
    search = """
LOCAL_PROMPT_PREFIX = (
    "- After FTS/hybrid, project using @step.ids / node_ids returned by that step — "
    "do not batch_get raw source keys like biz:… alone if get returns missing.\\n"
    "- pipeline confidence must be a STRING: high|med|low (never an object).\\n"
)


def synthesize_answer_from_results(query: str, results: list[dict]) -> str:
    return query


async def run_search() -> None:
        results = []
        CHATS[chat_id]["last_results"] = results
"""
    detail = """
async def get_business(business_id: str, chat_id: str | None = None) -> dict:
    cached = find_cached_business(business_id)
    if cached:
        apply_local_images(cached)
        return {
            "business": cached,
            "chat_id": None,
            "source": "cache",
            "ai_process_result": False,
        }
"""
    return search, detail


def test_sample_creation_fills_search_coordinates(tmp_path: Path) -> None:
    root = tmp_path / "demo_yelp"
    search = root / "src" / "local_guide" / "search.py"
    detail = root / "src" / "local_guide" / "detail.py"
    search.parent.mkdir(parents=True)
    search_src, detail_src = _coordinate_sources()
    search.write_text(search_src, encoding="utf-8")
    detail.write_text(detail_src, encoding="utf-8")

    report = apply_yelp_live_search(root)
    body = search.read_text(encoding="utf-8")
    detail_body = detail.read_text(encoding="utf-8")
    assert "src/local_guide/search.py" in report["patched"]
    assert "src/local_guide/detail.py" in report["patched"]
    assert report["coordinates"] is True
    assert "Every Business project fields list must include" in body
    assert "def fill_missing_coordinates" in body
    assert 'return f"biz:yelp:{bare}"' in body
    assert "await fill_missing_coordinates(results)" in body
    assert "await fill_missing_coordinates([cached])" in detail_body
    assert apply_yelp_live_search(root)["patched"] == []

    namespace = _load(search)
    assert namespace["yelp_business_doc_key"]("abc") == "biz:yelp:abc"
    assert namespace["yelp_business_doc_key"]("biz:yelp:abc") == "biz:yelp:abc"
    cards = [{"name": "Pagano's Steaks", "business_id": "abc"}]
    namespace["apply_coordinate_rows"](
        cards,
        [{"doc_key": "biz:yelp:abc", "latitude": 40.07, "longitude": -75.15}],
    )
    assert cards[0]["latitude"] == "40.07"
    assert cards[0]["longitude"] == "-75.15"


def test_apply_live_search_reports_missing_files(tmp_path: Path) -> None:
    report = apply_yelp_live_search(tmp_path)
    assert report["patched"] == []
    assert report["missing"] == [
        "src/local_guide/search.py",
        "frontend/src/api/client.ts",
        "frontend/vite.config.ts",
        "src/local_guide/detail.py",
        "src/local_guide/results_parser.py",
        "src/local_guide/answer_parser.py",
    ]
    assert report["live_chat_request"] is False
    assert report["business_page"] is False
    assert report["scope"] == "yelp-demo/_default"
    assert report["mode"] == "analytics"


def test_search_patch_does_not_write_when_turns_marker_is_missing(
    tmp_path: Path,
) -> None:
    root = tmp_path / "demo_yelp"
    path = root / "src" / "local_guide" / "search.py"
    path.parent.mkdir(parents=True)
    original = _search_source(turns=False)
    path.write_text(original, encoding="utf-8")
    report = apply_yelp_live_search(root)
    assert path.read_text(encoding="utf-8") == original
    assert "src/local_guide/search.py" not in report["patched"]


def test_client_without_fetch_business_anchor_is_unchanged(tmp_path: Path) -> None:
    root = tmp_path / "demo_yelp"
    client = root / "frontend" / "src" / "api"
    client.mkdir(parents=True)
    original = (
        "export async function search(\n"
        "  query: string,\n"
        "  chatId?: string | null,\n"
        "  options?: SearchOptions\n"
        "): Promise<SearchResponse> {\n"
        "  const q = query.trim();\n"
        "  await delay(420, options?.signal);\n"
        "  return { query: q };\n"
        "}\n"
    )
    (client / "client.ts").write_text(original, encoding="utf-8")
    report = apply_yelp_live_search(root)
    assert (client / "client.ts").read_text(encoding="utf-8") == original
    assert "frontend/src/api/client.ts" not in report["patched"]


def test_vite_with_an_existing_proxy_is_unchanged(tmp_path: Path) -> None:
    root = tmp_path / "demo_yelp"
    path = root / "frontend" / "vite.config.ts"
    path.parent.mkdir(parents=True)
    original = (
        "export default defineConfig({\n"
        "  server: {\n"
        '    host: "0.0.0.0",\n'
        "    port: 5173,\n"
        "    proxy: {\n"
        '      "/api": { target: "http://127.0.0.1:9" },\n'
        "    },\n"
        "  },\n"
        "});\n"
    )
    path.write_text(original, encoding="utf-8")
    report = apply_yelp_live_search(root)
    assert path.read_text(encoding="utf-8") == original
    assert "frontend/vite.config.ts" not in report["patched"]


def test_fetch_search_chat_request_requires_the_scope_document(
    tmp_path: Path, monkeypatch
) -> None:
    namespace = _patched_search(tmp_path)
    fetch = namespace["fetch_search_chat_request"]
    seen = _install_catalog(monkeypatch, _DOC)
    doc = asyncio.run(
        fetch("https://zeus.example:8080", "analytics", "yelp-demo", "_default")
    )
    assert doc is _DOC
    assert seen == {
        "zeus_url": "https://zeus.example:8080",
        "mode": "analytics",
        "bucket": "yelp-demo",
        "scope": "_default",
        "extra": {},
    }

    _install_catalog(
        monkeypatch, {"messages": [{"role": "system", "content": "## SCOPE BRIEF"}]}
    )
    try:
        asyncio.run(
            fetch("https://zeus.example:8080", "analytics", "yelp-demo", "_default")
        )
    except ValueError as exc:
        assert "mini-schema" in str(exc)
    else:
        raise AssertionError("expected ValueError")

    _install_catalog(monkeypatch, ["not", "an", "object"])
    try:
        asyncio.run(
            fetch("https://zeus.example:8080", "analytics", "yelp-demo", "_default")
        )
    except ValueError as exc:
        assert "not a JSON object" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_run_search_does_not_retry_a_login_failure(
    tmp_path: Path, monkeypatch
) -> None:
    namespace = _patched_search(tmp_path)
    _install_catalog(monkeypatch, _DOC)
    calls: list[tuple[tuple, dict]] = []

    async def run_agent(*args, **kwargs):
        calls.append((args, kwargs))
        raise RuntimeError("LOGIN FAILED: 401")

    _bind(namespace, run_agent)
    try:
        asyncio.run(namespace["run_search"]("tacos"))
    except RuntimeError as exc:
        assert "LOGIN FAILED" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
    assert len(calls) == 1
    assert calls[0][0][1]["auth_mode"] == "basic"
    assert namespace["zcfg"]["auth_mode"] == "basic"
    assert calls[0][1]["chat_req_override"] is _DOC


def test_run_search_does_not_retry_other_runtime_errors(
    tmp_path: Path, monkeypatch
) -> None:
    namespace = _patched_search(tmp_path)
    _install_catalog(monkeypatch, _DOC)
    calls: list[tuple] = []

    async def run_agent(*args, **kwargs):
        calls.append(args)
        raise RuntimeError("session closed")

    _bind(namespace, run_agent)
    try:
        asyncio.run(namespace["run_search"]("tacos"))
    except RuntimeError as exc:
        assert str(exc) == "session closed"
    else:
        raise AssertionError("expected RuntimeError")
    assert len(calls) == 1


def test_auth_none_retry_is_stripped(tmp_path: Path) -> None:
    root = tmp_path / "demo_yelp"
    path = root / "src" / "local_guide" / "search.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "async def run_search(query: str):\n"
        "        settings = ClientSettings(ai_process_result=bool(ai_process_result))\n"
        "        chat_request = await fetch_search_chat_request(zeus_url, mode, bucket, scope)\n"
        "        turn_zcfg = zcfg\n"
        "        try:\n"
        "            answer, trace, new_turns, session_meta, structured = await _run_search_agent(\n"
        "                zeus_url=zeus_url,\n"
        "                zcfg=turn_zcfg,\n"
        "                chat_request=chat_request,\n"
        "            )\n"
        "        except RuntimeError as exc:\n"
        '            if "login failed" not in str(exc).lower():\n'
        "                raise\n"
        "            public = dict(zcfg)\n"
        '            public["auth_mode"] = "none"\n'
        "            answer, trace, new_turns, session_meta, structured = await _run_search_agent(\n"
        "                zeus_url=zeus_url,\n"
        "                zcfg=public,\n"
        "                chat_request=chat_request,\n"
        "            )\n"
        "\n"
        '        CHATS[chat_id]["turns"] = new_turns\n',
        encoding="utf-8",
    )
    report = apply_yelp_live_search(root)
    assert "src/local_guide/search.py" in report["patched"]
    body = path.read_text(encoding="utf-8")
    assert "login failed" not in body
    assert 'auth_mode"] = "none"' not in body
    assert body.count("zcfg=zcfg") == 1
    assert body.count("fetch_search_chat_request(zeus_url, mode, bucket, scope)") == 1
    assert body.count("settings = ClientSettings") == 1
    assert apply_yelp_live_search(root)["patched"] == []


def test_fetch_health_reads_api_health(tmp_path: Path) -> None:
    root = tmp_path / "demo_yelp"
    client = root / "frontend" / "src" / "api"
    client.mkdir(parents=True)
    (client / "client.ts").write_text(
        'const res = await fetch("/api/search", { method: "POST" });\n'
        "export async function fetchBusiness(businessId: string) {\n"
        "  return { business: null };\n"
        "}\n"
        "export async function fetchHealth(): Promise<HealthResponse> {\n"
        "  return {\n"
        "    ok: true,\n"
        '    app_version: "0.1.0",\n'
        "    business_count: BUSINESSES.length,\n"
        '    corpus_label: "businesses",\n'
        '    corpus_source: "sample",\n'
        "  };\n"
        "}\n",
        encoding="utf-8",
    )
    report = apply_yelp_live_search(root)
    assert "frontend/src/api/client.ts" in report["patched"]
    body = (client / "client.ts").read_text(encoding="utf-8")
    assert 'fetch("/api/health")' in body
    assert "BUSINESSES.length" not in body
    assert apply_yelp_live_search(root)["patched"] == []
