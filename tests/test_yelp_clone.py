"""demo_yelp clone + DEMO_YELP_SAMPLE_DIR. Bare sample=yelp stays the multi gate."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

from zeus_dev_helper_mcp.checklist import load_checklist
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.explain import explain_topic
from zeus_dev_helper_mcp.scaffold import use_sample
from zeus_dev_helper_mcp.yelp import (
    DEFAULT_YELP_DIR_NAME,
    ENV_YELP_DIR,
    YELP_REPO_GIT,
    clone_yelp_sample,
    ensure_yelp_sample,
    is_yelp_demo_sample,
    sanitize_yelp_dir_name,
    validate_yelp_layout,
)


def _cfg(tmp_path: Path) -> HelperConfig:
    return HelperConfig(state_dir=tmp_path / "state")


def _write_layout(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "README.md").write_text("# yelp\n", encoding="utf-8")
    frontend = dest / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text("{}\n", encoding="utf-8")


def test_sanitize_and_aliases() -> None:
    assert sanitize_yelp_dir_name("") == DEFAULT_YELP_DIR_NAME
    assert sanitize_yelp_dir_name("../etc") == DEFAULT_YELP_DIR_NAME
    assert sanitize_yelp_dir_name("my_yelp") == "my_yelp"
    assert is_yelp_demo_sample("yelp") is False
    assert is_yelp_demo_sample("multi") is False
    assert is_yelp_demo_sample("yelp-demo") is True
    assert is_yelp_demo_sample("demo_yelp") is True
    assert is_yelp_demo_sample("yelpdemo") is True


def test_validate_layout(tmp_path: Path) -> None:
    root = tmp_path / "demo_yelp"
    root.mkdir()
    assert validate_yelp_layout(root)["ok"] is False
    (root / "README.md").write_text("# yelp\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='local-guide'\n", encoding="utf-8")
    assert validate_yelp_layout(root)["ok"] is True


def test_clone_yelp_sample_success(tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "demo_yelp"
    seen: dict[str, list[str]] = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = list(cmd)
        _write_layout(dest)
        proc = MagicMock()
        proc.returncode = 0
        proc.stderr = ""
        proc.stdout = "Cloning...\n"
        return proc

    monkeypatch.setattr("zeus_dev_helper_mcp.yelp.subprocess.run", fake_run)
    out = clone_yelp_sample(dest=dest)
    assert out["ok"] is True
    assert out["cloned"] is True
    assert dest.is_dir()
    assert seen["cmd"][:4] == ["git", "clone", "--depth", "1"]
    assert seen["cmd"][4] == YELP_REPO_GIT


def test_clone_yelp_sample_dest_exists(tmp_path: Path) -> None:
    dest = tmp_path / "demo_yelp"
    dest.mkdir()
    out = clone_yelp_sample(dest=dest)
    assert out["ok"] is False
    assert out["cloned"] is False


def test_ensure_clones_and_sets_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(ENV_YELP_DIR, raising=False)
    parent = tmp_path / "apps"
    parent.mkdir()
    dest = parent / "my_yelp_boot"

    def fake_run(cmd, **kwargs):
        _write_layout(dest)
        proc = MagicMock()
        proc.returncode = 0
        proc.stderr = ""
        proc.stdout = ""
        return proc

    monkeypatch.setattr("zeus_dev_helper_mcp.yelp.subprocess.run", fake_run)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp._find_yelp_dir",
        lambda explicit="", cfg=None: None,
    )
    monkeypatch.setattr("zeus_dev_helper_mcp.yelp._default_clone_parent", lambda: parent)

    cfg = _cfg(tmp_path)
    out = ensure_yelp_sample(cfg, project_name="my_yelp_boot", parent_dir=str(parent))
    assert out["ok"] is True
    assert out["cloned"] is True
    assert out["local_dir"] == str(dest.resolve())
    assert os.environ.get(ENV_YELP_DIR) == str(dest.resolve())
    assert out["env"][ENV_YELP_DIR] == str(dest.resolve())
    assert "npm install" in out["next_action"]
    assert "LocalAI" in out["next_action"]
    assert "github.com/koten-ai/demo_yelp" in out["next_action"]
    assert "yelp-demo" in out["next_action"]
    saved = json.loads((cfg.state_dir / "yelp_sample.json").read_text(encoding="utf-8"))
    assert saved["yelp_sample_dir"] == str(dest.resolve())


def test_ensure_uses_existing_sample_dir(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "already"
    _write_layout(root)
    monkeypatch.delenv(ENV_YELP_DIR, raising=False)
    called = {"n": 0}

    def no_clone(**kwargs):
        called["n"] += 1
        return {"ok": False}

    monkeypatch.setattr("zeus_dev_helper_mcp.yelp.clone_yelp_sample", no_clone)
    cfg = _cfg(tmp_path)
    out = ensure_yelp_sample(cfg, sample_dir=str(root))
    assert out["ok"] is True
    assert out["cloned"] is False
    assert called["n"] == 0
    assert os.environ[ENV_YELP_DIR] == str(root.resolve())


def test_use_sample_yelp_demo_passes_project_name(tmp_path: Path, monkeypatch) -> None:
    parent = tmp_path / "ws"
    parent.mkdir()
    dest = parent / "BootYelp"

    def fake_run(cmd, **kwargs):
        _write_layout(dest)
        proc = MagicMock()
        proc.returncode = 0
        proc.stderr = ""
        proc.stdout = ""
        return proc

    monkeypatch.setattr("zeus_dev_helper_mcp.yelp.subprocess.run", fake_run)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp._find_yelp_dir",
        lambda explicit="", cfg=None: None,
    )
    monkeypatch.setattr("zeus_dev_helper_mcp.yelp._default_clone_parent", lambda: parent)
    monkeypatch.delenv(ENV_YELP_DIR, raising=False)

    cfg = _cfg(tmp_path)
    out = use_sample(cfg, sample="yelp-demo", project_name="BootYelp", parent_dir=str(parent))
    assert out["ok"] is True
    assert out["cloned"] is True
    assert out["project_name"] == "BootYelp"
    assert out["local_dir"] == str(dest.resolve())
    assert out["sample"]["sample"] == "demo_yelp"
    assert out["sample"]["name"] == "demo_yelp"
    assert out["app_kind"] == "ui"
    assert os.environ[ENV_YELP_DIR] == str(dest.resolve())
    data = load_checklist(cfg)
    statuses = {
        item["id"]: item["status"]
        for phase in data["phases"]
        for item in phase["items"]
    }
    assert statuses["0.2"] == "done"
    assert statuses["3.1"] == "done"


def test_use_sample_bare_yelp_stays_blocked(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    out = use_sample(cfg, sample="yelp")
    assert out["ok"] is False
    assert out["blocked"] is True


def test_failed_clone_does_not_fall_through(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DEMO_TRAVEL_SAMPLE_DIR", raising=False)
    monkeypatch.delenv(ENV_YELP_DIR, raising=False)
    parent = tmp_path / "apps"
    parent.mkdir()
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp._find_yelp_dir",
        lambda explicit="", cfg=None: None,
    )
    monkeypatch.setattr("zeus_dev_helper_mcp.yelp._default_clone_parent", lambda: parent)

    def fake_run(cmd, **kwargs):
        proc = MagicMock()
        proc.returncode = 1
        proc.stderr = "authentication failed"
        proc.stdout = ""
        return proc

    monkeypatch.setattr("zeus_dev_helper_mcp.yelp.subprocess.run", fake_run)
    cfg = _cfg(tmp_path)
    out = use_sample(cfg, sample="demo_yelp", parent_dir=str(parent))
    assert out["ok"] is False
    assert out.get("blocked") is not True
    assert out["sample"]["sample"] == "demo_yelp"
    assert "DEMO_YELP_SAMPLE_DIR" in (out.get("next_action") or "")
    assert os.environ.get("DEMO_TRAVEL_SAMPLE_DIR") is None
    assert os.environ.get(ENV_YELP_DIR) is None
    assert list(parent.rglob("main.py")) == []


def test_start_project_demo_yelp(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv(ENV_YELP_DIR, raising=False)
    from zeus_dev_helper_mcp.config import reload_config
    from zeus_dev_helper_mcp.prereqs import save_prereqs
    from zeus_dev_helper_mcp.server import start_project
    from zeus_dev_helper_mcp.walkthrough import enriched_next_step

    out = start_project(sample="yelp-demo")
    assert out["started"] is True
    assert out.get("blocked") is not True
    assert out["sample"] == "demo_yelp"
    assert out["track"] == "ui"
    assert out["app_kind"] == "ui"
    assert out.get("recommended_tools") == ["set_prereq"]

    cfg = reload_config()
    checklist = load_checklist(cfg)
    item_01 = next(
        item
        for phase in checklist["phases"]
        for item in phase["items"]
        if item["id"] == "0.1"
    )
    assert item_01["status"] == "done"
    nxt = enriched_next_step(cfg)
    assert nxt.get("app_track") == "ui"
    assert nxt.get("item", {}).get("id") == "0.2"
    assert nxt.get("recommended_tools") == ["set_prereq"]

    save_prereqs(
        cfg,
        {
            "zeus_url": "http://192.168.0.219:8080",
            "bucket": "yelp-demo",
            "scope": "_default",
        },
    )
    nxt = enriched_next_step(cfg)
    assert nxt.get("recommended_tools") == ["readiness_check", "use_sample"]
    hint = nxt.get("use_sample_args_hint") or {}
    assert hint.get("sample") == "demo_yelp"
    assert hint.get("project_name") == "demo_yelp"
    assert "yelp-demo" in (hint.get("note") or "")


def test_next_step_unbound_yelp_after_green_checklist(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv(ENV_YELP_DIR, raising=False)
    from zeus_dev_helper_mcp.checklist import set_item_status
    from zeus_dev_helper_mcp.config import reload_config
    from zeus_dev_helper_mcp.server import start_project
    from zeus_dev_helper_mcp.walkthrough import enriched_next_step
    from zeus_dev_helper_mcp.yelp import save_yelp_sample_dir

    start_project(sample="yelp-demo")
    cfg = reload_config()
    for iid in (
        "0.1",
        "0.2",
        "1.1",
        "1.2",
        "2.1",
        "2.2",
        "2.3",
        "3.1",
        "3.2",
        "4.1",
        "4.2",
        "5.1",
        "5.2",
    ):
        set_item_status(cfg, iid, "done", evidence="test")
    nxt = enriched_next_step(cfg)
    assert nxt.get("recommended_tools") == ["use_sample"]
    hint = nxt.get("use_sample_args_hint") or {}
    assert hint.get("sample") == "demo_yelp"
    assert hint.get("project_name") == "demo_yelp"

    root = tmp_path / "demo_yelp"
    root.mkdir()
    save_yelp_sample_dir(cfg, root)
    nxt = enriched_next_step(cfg)
    assert nxt.get("recommended_tools") == ["use_sample"]

    _write_layout(root)
    nxt = enriched_next_step(cfg)
    assert nxt.get("recommended_tools") == []
    note = nxt.get("note") or ""
    assert str(root.resolve()) in note
    assert "LocalAI" in note
    assert "demo_beer_sample" in note
    assert "template" in note


def test_generated_app_is_not_the_localai_template(tmp_path: Path, monkeypatch) -> None:
    generated = tmp_path / "demos" / "demo_yelp"
    generated.mkdir(parents=True)
    (generated / "README.md").write_text("# Yelp demo\n", encoding="utf-8")
    (generated / "main.py").write_text("print('neighborhood')\n", encoding="utf-8")
    (generated / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    static = generated / "static"
    static.mkdir()
    (static / "index.html").write_text("<h1>Neighborhood</h1>\n", encoding="utf-8")
    localai = tmp_path / "demo_yelp"
    _write_layout(localai)
    (localai / "frontend" / "package.json").write_text(
        '{"name": "localai-ui-template"}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv(ENV_YELP_DIR, str(generated))
    cfg = _cfg(tmp_path)
    from zeus_dev_helper_mcp.yelp import recorded_yelp_sample_dir, save_yelp_sample_dir

    save_yelp_sample_dir(cfg, generated)
    assert recorded_yelp_sample_dir(cfg) is None
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp._candidate_yelp_dirs",
        lambda here: [generated, localai],
    )
    out = ensure_yelp_sample(cfg)
    assert out["ok"] is True
    assert out["cloned"] is False
    assert out["local_dir"] == str(localai.resolve())
    assert os.environ[ENV_YELP_DIR] == str(localai.resolve())
    assert "LocalAI" in out["next_action"]
    assert "github.com/koten-ai/demo_yelp" in out["next_action"]
    assert not (localai / "main.py").exists()
    assert (generated / "main.py").read_text(encoding="utf-8").startswith("print")
    saved = json.loads((cfg.state_dir / "yelp_sample.json").read_text(encoding="utf-8"))
    assert saved["yelp_sample_dir"] == str(localai.resolve())


def test_parent_dir_clones_instead_of_outside_checkout(tmp_path: Path, monkeypatch) -> None:
    sibling = tmp_path / "elsewhere" / "demo_yelp"
    _write_layout(sibling)
    parent = tmp_path / "demos"
    parent.mkdir()
    dest = parent / "demo_yelp"
    monkeypatch.delenv(ENV_YELP_DIR, raising=False)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp._find_yelp_dir",
        lambda explicit="", cfg=None: sibling,
    )

    def fake_run(cmd, **kwargs):
        assert cmd[-1] == str(dest.resolve())
        _write_layout(dest)
        proc = MagicMock()
        proc.returncode = 0
        proc.stderr = ""
        proc.stdout = ""
        return proc

    monkeypatch.setattr("zeus_dev_helper_mcp.yelp.subprocess.run", fake_run)
    cfg = _cfg(tmp_path)
    out = use_sample(
        cfg,
        sample="demo_yelp",
        project_name="demo_yelp",
        parent_dir=str(parent),
    )
    assert out["ok"] is True
    assert out["cloned"] is True
    assert out["local_dir"] == str(dest.resolve())
    assert out["local_dir"] != str(sibling.resolve())
    assert "template" in (out.get("next_action") or "")
    assert "demo_beer_sample" in (out.get("next_action") or "")
    joined = " ".join(out.get("do_not") or [])
    assert "scaffold_app" in joined
    assert "demo_beer_sample" in joined


def test_parent_dir_clone_failure_names_outside_checkout(
    tmp_path: Path, monkeypatch
) -> None:
    sibling = tmp_path / "elsewhere" / "demo_yelp"
    _write_layout(sibling)
    parent = tmp_path / "demos"
    parent.mkdir()
    monkeypatch.delenv(ENV_YELP_DIR, raising=False)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp._find_yelp_dir",
        lambda explicit="", cfg=None: sibling,
    )

    def fake_run(cmd, **kwargs):
        proc = MagicMock()
        proc.returncode = 1
        proc.stderr = "authentication failed"
        proc.stdout = ""
        return proc

    monkeypatch.setattr("zeus_dev_helper_mcp.yelp.subprocess.run", fake_run)
    cfg = _cfg(tmp_path)
    out = ensure_yelp_sample(cfg, project_name="demo_yelp", parent_dir=str(parent))
    assert out["ok"] is False
    assert out["local_dir"] is None
    assert str(sibling.resolve()) in (out.get("next_action") or "")
    assert "sample_dir" in (out.get("next_action") or "")
    assert "demo_beer_sample" in " ".join(out.get("do_not") or [])
    assert os.environ.get(ENV_YELP_DIR) is None
    assert not (parent / "demo_yelp").exists()


def test_use_sample_wires_live_chat_request_search(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "demo_yelp"
    _write_layout(root)
    search = root / "src" / "local_guide"
    search.mkdir(parents=True)
    (search / "search.py").write_text(
        "async def run_search(\n"
        "    query: str,\n"
        "):\n"
        "        settings = ClientSettings(ai_process_result=bool(ai_process_result))\n"
        "        answer, trace, new_turns, session_meta, structured = await run_agent(\n"
        "            zeus_url,\n"
        "            zcfg,\n"
        "            base_catalog_dirs=base_catalog_dirs,\n"
        "        )\n"
        "\n"
        '        CHATS[chat_id]["turns"] = new_turns\n',
        encoding="utf-8",
    )
    client = root / "frontend" / "src" / "api"
    client.mkdir(parents=True)
    (client / "client.ts").write_text(
        "export async function search(\n"
        "  query: string,\n"
        "  chatId?: string | null,\n"
        "  options?: SearchOptions\n"
        "): Promise<SearchResponse> {\n"
        "  const q = query.trim();\n"
        "  await delay(420, options?.signal);\n"
        "  return { chat_id: q, query: q, answer: \"\", structured_answer: null, results: [] };\n"
        "}\n"
        "export async function fetchBusiness(businessId: string) {\n"
        "  return { business: null };\n"
        "}\n",
        encoding="utf-8",
    )
    (root / "frontend" / "vite.config.ts").write_text(
        "export default defineConfig({\n"
        "  server: {\n"
        "    host: \"0.0.0.0\",\n"
        "    port: 5173,\n"
        "  },\n"
        "});\n",
        encoding="utf-8",
    )
    monkeypatch.delenv(ENV_YELP_DIR, raising=False)
    monkeypatch.setattr("zeus_dev_helper_mcp.yelp.clone_yelp_sample", lambda **kwargs: {"ok": False})
    cfg = _cfg(tmp_path)
    out = ensure_yelp_sample(cfg, sample_dir=str(root))
    assert out["ok"] is True
    report = out["search"]
    assert report["live_chat_request"] is True
    assert "src/local_guide/search.py" in report["patched"]
    assert "frontend/src/api/client.ts" in report["patched"]
    assert "frontend/vite.config.ts" in report["patched"]
    body = (search / "search.py").read_text(encoding="utf-8")
    assert "fetch_search_chat_request" in body
    assert "chat_req_override=chat_request" in body
    ui = (client / "client.ts").read_text(encoding="utf-8")
    assert 'fetch("/api/search"' in ui
    assert "fetchBusiness" in ui
    vite = (root / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    assert "127.0.0.1:5000" in vite
    again = ensure_yelp_sample(cfg, sample_dir=str(root))
    assert again["search"]["patched"] == []
    assert again["search"]["live_chat_request"] is True
    assert "chat_request.json" in out["next_action"]


def test_start_project_bare_yelp_still_blocked(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    from zeus_dev_helper_mcp.server import start_project

    out = start_project(sample="yelp")
    assert out["started"] is False
    assert out["blocked"] is True


def test_probe_target_and_glossary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ZEUS_DEV_HELPER_STATE_DIR", str(tmp_path / "state"))
    from zeus_dev_helper_mcp.clarify import probe_target

    assert probe_target("yelp-demo") == ("yelp-demo", "_default")
    assert probe_target("yelp") is None
    cfg = _cfg(tmp_path)
    topic = explain_topic(cfg, "yelp-demo")
    assert topic["found"] is True
    assert topic["topic"] == "demo_yelp"
