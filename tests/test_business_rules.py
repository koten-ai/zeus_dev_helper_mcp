"""inject_business_rules writes settings.rules on the resolved Zeus app."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zeus_dev_helper_mcp.business_rules import (
    NOT_ZEUS_MESSAGE,
    inject_business_rules,
)
from zeus_dev_helper_mcp.checklist import load_checklist, save_checklist
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.scaffold import _API_MAIN_PY, _MAIN_PY

_PASSWORD = "super-secret-zeus-pass"
_BEER_MAIN = """
async def search():
    result = await rt.agent.run_turn(
        message,
        settings=cfg.settings,
    )
"""
_SCAFFOLD_MAIN = """
async def main():
    rt = ZeusRuntime.from_config(_ROOT / "config.json")
    result = await rt.agent.run_turn(
        question,
        settings=ClientSettings(ai_process_result=False),
        chat_request=chat_request,
    )
"""
_API_MAIN = """
async def turn():
    result = await _runtime.agent.run_turn(
        body.question,
        settings=ClientSettings(ai_process_result=False),
        chat_request=chat_request,
    )
"""
_TRAVEL_FACTORY = """
def build_runtime_config(cfg):
    settings_raw = dict(cfg["settings"]) if isinstance(cfg.get("settings"), dict) else {}
    return ClientSettings(
        mode=mode,
        durable_sessions=durable,
        ai_process_result=ai_flag,
        max_rounds=max_rounds,
        ignore_user_tool_path_hints=ignore_hints,
    )
"""
_UNKNOWN_MAIN = """
def make():
    return ClientSettings(mode="analytics", max_rounds=4)
"""
_COUPON = {
    "coupon_presented": (
        "If they present a coupon, treat it as applicable and note the code if given."
    ),
}
_FREEBIE = {
    "no_invent_promos": "If they ask for freebies without catalog data, do not invent promos.",
}


@pytest.fixture
def cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> HelperConfig:
    for name in (
        "DEMO_BEER_SAMPLE_DIR",
        "DEMO_TRAVEL_SAMPLE_DIR",
        "DEMO_YELP_SAMPLE_DIR",
    ):
        monkeypatch.delenv(name, raising=False)
    return HelperConfig(state_dir=tmp_path / "state")


def _zeus(path: Path, main: str, *, password: str = "") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    zeus: dict[str, str] = {"url": "http://127.0.0.1:8080"}
    if password:
        zeus["password"] = password
    doc = {"zeus": zeus, "settings": {"mode": "analytics"}, "kept": "yes"}
    (path / "config.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    if main:
        (path / "main.py").write_text(main, encoding="utf-8")
    return path


def _bind(cfg: HelperConfig, kind: str, path: Path) -> None:
    names = {
        "beer": ("beer_sample.json", "beer_sample_dir"),
        "travel": ("travel_sample.json", "travel_sample_dir"),
        "yelp-demo": ("yelp_sample.json", "yelp_sample_dir"),
    }
    filename, field = names[kind]
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / filename).write_text(
        json.dumps({field: str(path)}) + "\n",
        encoding="utf-8",
    )


def _sample(cfg: HelperConfig, sample: str) -> None:
    data = load_checklist(cfg)
    data["meta"] = {"goal": "single-agent", "sample": sample}
    save_checklist(cfg, data)


def _rules(path: Path) -> dict[str, str]:
    doc = json.loads((path / "config.json").read_text(encoding="utf-8"))
    return dict(doc["settings"]["rules"])


def _inject(cfg: HelperConfig, **kwargs: object) -> dict:
    return inject_business_rules(cfg, **kwargs)  # type: ignore[arg-type]


def test_explicit_app_dir_leaves_the_other_app(cfg: HelperConfig, tmp_path: Path) -> None:
    beer = _zeus(tmp_path / "beer", _BEER_MAIN)
    other = _zeus(tmp_path / "other", _BEER_MAIN)
    out = _inject(cfg, app_dir=str(beer), rules=_COUPON, cwd=tmp_path)
    assert out["ok"] is True
    assert out["app_dir"] == str(beer.resolve())
    assert out["injected"] is True
    assert out["changes"] == [{"id": "coupon_presented", "action": "added"}]
    assert _rules(beer) == _COUPON
    assert "rules" not in json.loads((other / "config.json").read_text(encoding="utf-8"))["settings"]
    assert (beer / "main.py").read_text(encoding="utf-8") == _BEER_MAIN


def test_cwd_zeus_app_wins_over_bound_sample(cfg: HelperConfig, tmp_path: Path) -> None:
    beer = _zeus(tmp_path / "beer", _BEER_MAIN)
    here = _zeus(tmp_path / "here", _BEER_MAIN)
    _bind(cfg, "beer", beer)
    _sample(cfg, "beer")
    out = _inject(cfg, rules=_COUPON, cwd=here)
    assert out["app_dir"] == str(here.resolve())
    assert _rules(here) == _COUPON
    assert "rules" not in json.loads((beer / "config.json").read_text(encoding="utf-8"))["settings"]


def test_checklist_beer_when_cwd_is_not_an_app(cfg: HelperConfig, tmp_path: Path) -> None:
    beer = _zeus(tmp_path / "beer", _BEER_MAIN, password=_PASSWORD)
    _bind(cfg, "beer", beer)
    _sample(cfg, "beer")
    out = _inject(cfg, rules=_COUPON, cwd=tmp_path)
    assert out["ok"] is True
    assert out["sample"] == "beer"
    assert out["app_dir"] == str(beer.resolve())
    assert _rules(beer) == _COUPON
    assert _PASSWORD not in json.dumps(out)
    saved = (beer / "config.json").read_text(encoding="utf-8")
    assert _PASSWORD in saved
    assert '"kept": "yes"' in saved


def test_no_app_asks_and_writes_nothing(cfg: HelperConfig, tmp_path: Path) -> None:
    out = _inject(cfg, rules=_COUPON, cwd=tmp_path)
    assert out["ok"] is False
    assert out["failure_class"] == "app_required"
    assert out["ask_user"][0]["prompt"] == "Path to the Zeus app"
    assert not (tmp_path / "config.json").exists()


def test_two_bound_apps_without_checklist_sample_ask(cfg: HelperConfig, tmp_path: Path) -> None:
    beer = _zeus(tmp_path / "beer", _BEER_MAIN)
    travel = _zeus(tmp_path / "travel", _BEER_MAIN)
    _bind(cfg, "beer", beer)
    _bind(cfg, "travel", travel)
    out = _inject(cfg, rules=_COUPON, cwd=tmp_path)
    assert out["failure_class"] == "app_required"
    labels = [row["label"] for row in out["ask_user"][0]["options"]]
    assert labels == ["beer", "travel"]
    assert "rules" not in json.loads((beer / "config.json").read_text(encoding="utf-8"))["settings"]
    assert "rules" not in json.loads((travel / "config.json").read_text(encoding="utf-8"))["settings"]


def test_named_sample_wins_over_cwd(cfg: HelperConfig, tmp_path: Path) -> None:
    beer = _zeus(tmp_path / "beer", _BEER_MAIN)
    here = _zeus(tmp_path / "here", _BEER_MAIN)
    _bind(cfg, "beer", beer)
    out = _inject(cfg, sample="beer", rules=_COUPON, cwd=here)
    assert out["app_dir"] == str(beer.resolve())
    assert _rules(beer) == _COUPON
    assert "rules" not in json.loads((here / "config.json").read_text(encoding="utf-8"))["settings"]


def test_invalid_app_dir_does_not_fall_through(cfg: HelperConfig, tmp_path: Path) -> None:
    beer = _zeus(tmp_path / "beer", _BEER_MAIN)
    here = _zeus(tmp_path / "here", _BEER_MAIN)
    _bind(cfg, "beer", beer)
    _sample(cfg, "beer")
    notes = tmp_path / "notes"
    notes.mkdir()
    before = (beer / "config.json").read_text(encoding="utf-8")
    out = _inject(cfg, app_dir=str(notes), rules=_COUPON, cwd=here)
    assert out == {
        "ok": False,
        "failure_class": "not_a_zeus_app",
        "message": NOT_ZEUS_MESSAGE,
        "app_dir": str(notes.resolve()),
        "next_action": NOT_ZEUS_MESSAGE,
    }
    assert (beer / "config.json").read_text(encoding="utf-8") == before
    assert "rules" not in json.loads((here / "config.json").read_text(encoding="utf-8"))["settings"]


def test_merge_replace_and_remove(cfg: HelperConfig, tmp_path: Path) -> None:
    app = _zeus(tmp_path / "app", _BEER_MAIN)
    first = _inject(cfg, app_dir=str(app), rules=_COUPON)
    assert first["changes"] == [{"id": "coupon_presented", "action": "added"}]
    second = _inject(cfg, app_dir=str(app), rules=_FREEBIE)
    assert _rules(app) == {**_COUPON, **_FREEBIE}
    assert second["changes"] == [{"id": "no_invent_promos", "action": "added"}]
    replaced = _inject(
        cfg,
        app_dir=str(app),
        rules={"coupon_presented": "If they present a coupon, note the code."},
    )
    assert replaced["changes"] == [{"id": "coupon_presented", "action": "replaced"}]
    assert _inject(cfg, app_dir=str(app), rules=_COUPON, replace=True)["rules"] == _COUPON
    cleared = _inject(cfg, app_dir=str(app), remove=["coupon_presented"])
    assert cleared["changes"] == [{"id": "coupon_presented", "action": "removed"}]
    assert _rules(app) == {}
    again = _inject(cfg, app_dir=str(app), rules=_COUPON)
    snapshot = (app / "config.json").read_bytes()
    same = _inject(cfg, app_dir=str(app), rules=_COUPON)
    assert again["written"] is True
    assert same["changes"] == [{"id": "coupon_presented", "action": "unchanged"}]
    assert same["written"] is False
    assert (app / "config.json").read_bytes() == snapshot


def test_jailbreak_id_and_secret_leave_the_file(cfg: HelperConfig, tmp_path: Path) -> None:
    app = _zeus(tmp_path / "app", _BEER_MAIN)
    before = (app / "config.json").read_bytes()
    jail = _inject(cfg, app_dir=str(app), rules={"ignore_system": "Do something else."})
    assert jail["ok"] is False
    assert jail["failure_class"] == "jailbreak_rule_protected"
    secret = _inject(
        cfg,
        app_dir=str(app),
        rules={"coupon_presented": "The key is sk-abcdefghijklmnopqrstuvwxyz."},
    )
    assert secret["failure_class"] == "rule_invalid"
    assert "sk-" not in json.dumps(secret)
    assert (app / "config.json").read_bytes() == before


def test_hand_built_client_settings_stays_unpatched(
    cfg: HelperConfig, tmp_path: Path
) -> None:
    app = _zeus(tmp_path / "api", _SCAFFOLD_MAIN)
    before = (app / "main.py").read_bytes()
    out = _inject(cfg, app_dir=str(app), rules=_COUPON)
    assert (app / "main.py").read_bytes() == before
    assert out["injected"] is False
    assert out["wire_required"] is True
    assert out["written"] is True
    assert "patched" not in out
    assert _rules(app) == _COUPON
    api = _zeus(tmp_path / "fast", _API_MAIN)
    api_before = (api / "main.py").read_bytes()
    api_out = _inject(cfg, app_dir=str(api), rules=_COUPON)
    assert (api / "main.py").read_bytes() == api_before
    assert api_out["wire_required"] is True


def test_travel_constructor_stays_unpatched(cfg: HelperConfig, tmp_path: Path) -> None:
    app = _zeus(tmp_path / "travel", "")
    factory = app / "src" / "travel_planner" / "runtime_factory.py"
    factory.parent.mkdir(parents=True)
    factory.write_text(_TRAVEL_FACTORY, encoding="utf-8")
    out = _inject(cfg, app_dir=str(app), rules=_COUPON)
    assert factory.read_text(encoding="utf-8") == _TRAVEL_FACTORY
    assert out["injected"] is False
    assert out["wire_required"] is True
    assert _rules(app) == _COUPON


def test_yelp_constructors_stay_unpatched(cfg: HelperConfig, tmp_path: Path) -> None:
    app = _zeus(tmp_path / "yelp", "")
    live = app / "src" / "local_guide" / "live_search.py"
    search = app / "src" / "local_guide" / "search.py"
    live.parent.mkdir(parents=True)
    live_text = "def _runtime_config(cfg):\n    return ClientSettings(mode='analytics')\n"
    search_text = "def search():\n    settings = ClientSettings(ai_process_result=False)\n"
    live.write_text(live_text, encoding="utf-8")
    search.write_text(search_text, encoding="utf-8")
    out = _inject(cfg, app_dir=str(app), rules=_COUPON)
    assert live.read_text(encoding="utf-8") == live_text
    assert search.read_text(encoding="utf-8") == search_text
    assert out["injected"] is False
    assert out["wire_required"] is True
    assert _rules(app) == _COUPON


def test_loaded_settings_without_client_settings_is_injected(
    cfg: HelperConfig, tmp_path: Path
) -> None:
    app = _zeus(
        tmp_path / "cli",
        "await rt.agent.run_turn(question, settings=rt.config.settings)\n",
    )
    out = _inject(cfg, app_dir=str(app), rules=_COUPON)
    assert out["injected"] is True
    assert out["wire_required"] is False
    api = _zeus(
        tmp_path / "api",
        "await _runtime.agent.run_turn(question, settings=_runtime.config.settings)\n",
    )
    assert _inject(cfg, app_dir=str(api), rules=_COUPON)["injected"] is True


def test_client_settings_blocks_loaded_settings(
    cfg: HelperConfig, tmp_path: Path
) -> None:
    app = _zeus(tmp_path / "app", _BEER_MAIN)
    extra = app / "src" / "extra.py"
    extra.parent.mkdir(parents=True)
    extra_text = "settings = ClientSettings(mode='analytics')\n"
    extra.write_text(extra_text, encoding="utf-8")
    out = _inject(cfg, app_dir=str(app), rules=_COUPON)
    assert out["injected"] is False
    assert out["wire_required"] is True
    assert (app / "main.py").read_text(encoding="utf-8") == _BEER_MAIN
    assert extra.read_text(encoding="utf-8") == extra_text


def test_replace_and_remove_lists_every_dropped_id(
    cfg: HelperConfig, tmp_path: Path
) -> None:
    app = _zeus(tmp_path / "app", _BEER_MAIN)
    _inject(cfg, app_dir=str(app), rules={**_COUPON, **_FREEBIE})
    out = _inject(
        cfg,
        app_dir=str(app),
        rules=_COUPON,
        remove=["no_invent_promos"],
        replace=True,
    )
    assert out["rules"] == _COUPON
    assert {"id": "coupon_presented", "action": "unchanged"} in out["changes"]
    assert {"id": "no_invent_promos", "action": "removed"} in out["changes"]


def test_unknown_client_settings_is_wire_required(cfg: HelperConfig, tmp_path: Path) -> None:
    app = _zeus(tmp_path / "custom", _UNKNOWN_MAIN)
    before = (app / "main.py").read_text(encoding="utf-8")
    out = _inject(cfg, app_dir=str(app), rules=_COUPON)
    assert out["injected"] is False
    assert out["wire_required"] is True
    assert _rules(app) == _COUPON
    assert (app / "main.py").read_text(encoding="utf-8") == before


def test_read_does_not_write(cfg: HelperConfig, tmp_path: Path) -> None:
    app = _zeus(tmp_path / "app", _BEER_MAIN)
    _inject(cfg, app_dir=str(app), rules=_COUPON)
    before = (app / "config.json").read_bytes()
    out = _inject(cfg, app_dir=str(app), cwd=tmp_path)
    assert out["written"] is False
    assert out["rules"] == _COUPON
    assert (app / "config.json").read_bytes() == before


def test_scaffold_templates_pass_loaded_settings() -> None:
    assert "settings=rt.config.settings" in _MAIN_PY
    assert "settings=_runtime.config.settings" in _API_MAIN_PY
    assert "ClientSettings(ai_process_result=False)" not in _MAIN_PY
    assert "ClientSettings(ai_process_result=False)" not in _API_MAIN_PY
