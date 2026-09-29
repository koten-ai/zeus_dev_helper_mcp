"""ZDM-16: probes stay on the set_prereq bucket; generated sessions stay off."""

from __future__ import annotations

import json
from pathlib import Path

from zeus_dev_helper_mcp.beer import write_beer_sample
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.readiness import bucket_probe_report, run_readiness_check
from zeus_dev_helper_mcp.scaffold import scaffold_app
from zeus_dev_helper_mcp.smoke import smoke_test_zeus

_SESSION = "zdm16-session-sentinel"
_PASSWORD = "zdm16-password-sentinel"


def test_bucket_probe_report_rejects_yelp_data() -> None:
    report = bucket_probe_report(
        "beer-sample",
        [
            "http://lab.example:8080/healthz",
            "http://lab.example:8080/v1/yelp-data/_default/auth/session",
            "http://lab.example:8080/v1/ai/bootstrap/scope/beer-sample/_default",
            "http://lab.example:8080/v2/session/trace",
        ],
    )
    assert report["ok"] is False
    assert report["failure_class"] == "auth_default_bucket"
    assert report["authenticated_bucket"] == "yelp-data"
    assert report["request_buckets"] == ["yelp-data"]
    assert report["prereq_bucket"] == "beer-sample"


def test_bucket_probe_report_accepts_prereq_bucket() -> None:
    report = bucket_probe_report(
        "beer-sample",
        [
            "http://lab.example:8080/v1/beer-sample/_default/auth/session",
            "http://lab.example:8080/v2/beer-sample/_default/describe",
            "http://lab.example:8080/v1/ai/chat_request.json?mode=analytics&bucket=beer-sample",
        ],
    )
    assert report["ok"] is True
    assert report["authenticated_bucket"] == "beer-sample"
    assert report["request_buckets"] == ["beer-sample"]
    assert "failure_class" not in report


def test_readiness_records_authenticated_bucket(tmp_path: Path, monkeypatch) -> None:
    class _Resp:
        status_code = 200
        content = b"{}"
        text = "{}"

        def json(self):
            return {"session_id": _SESSION, "status": "ok"}

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> bool:
            return False

        def get(self, url, **kwargs):
            assert "yelp-data" not in str(url)
            return _Resp()

        def post(self, url, **kwargs):
            assert "yelp-data" not in str(url)
            assert _PASSWORD not in str(url)
            return _Resp()

        def close(self) -> None:
            return None

    monkeypatch.setattr("zeus_dev_helper_mcp.readiness.httpx.Client", _Client)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.readiness.list_modes",
        lambda cfg: {"modes": [{"name": "analytics"}]},
    )
    monkeypatch.setenv("ZEUS_USERNAME", "tap-user")
    monkeypatch.setenv("ZEUS_PASSWORD", _PASSWORD)
    cfg = HelperConfig(
        zeus_url="http://lab.example:8080",
        zeus_auth_mode="basic",
        default_bucket="beer-sample",
        default_scope="_default",
        state_dir=tmp_path / "state",
        chat_request_dir=tmp_path / "catalog",
    )
    out = run_readiness_check(cfg, update_checklist=False)
    assert out["authenticated_bucket"] == "beer-sample"
    assert out["prereq_bucket"] == "beer-sample"
    assert out["request_buckets"] == ["beer-sample"]
    assert out.get("primary_failure_class") != "auth_default_bucket"
    blob = json.dumps(out)
    assert _PASSWORD not in blob
    assert _SESSION not in blob
    gate = next(item for item in out["gates"] if item["id"] == "probe_bucket")
    assert gate["status"] == "pass"
    assert "beer-sample" in gate["detail"]


def test_smoke_refuses_foreign_describe(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.smoke.run_readiness_check",
        lambda *args, **kwargs: {
            "overall": "pass",
            "authenticated_bucket": "beer-sample",
            "prereq_bucket": "beer-sample",
            "request_buckets": ["beer-sample"],
            "primary_failure_class": None,
            "next_action": "ready",
        },
    )
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.smoke.describe_scope_url",
        lambda cfg: "http://lab.example:8080/v2/yelp-data/_default/describe",
    )

    def _boom(*args, **kwargs):
        raise AssertionError("foreign describe must not be sent")

    monkeypatch.setattr("zeus_dev_helper_mcp.smoke.httpx.Client", _boom)
    cfg = HelperConfig(
        zeus_url="http://lab.example:8080",
        default_bucket="beer-sample",
        default_scope="_default",
        state_dir=tmp_path / "state",
    )
    out = smoke_test_zeus(cfg, update_checklist=False)
    assert out["ok"] is False
    assert out["failure_class"] == "auth_default_bucket"
    assert out["authenticated_bucket"] == "beer-sample"
    assert "yelp-data" in out["request_buckets"]
    assert _PASSWORD not in json.dumps(out)


def test_scaffold_sessions_stay_off(tmp_path: Path) -> None:
    cfg = HelperConfig(
        zeus_url="http://lab.example:8080",
        default_bucket="beer-sample",
        default_scope="_default",
        state_dir=tmp_path / "state",
    )
    cli = scaffold_app(cfg, str(tmp_path / "cli"), project_name="demo_app")
    api = scaffold_app(
        cfg,
        str(tmp_path / "api"),
        project_name="demo_api",
        app_kind="api",
    )
    for out in (cli, api):
        assert out["ok"] is True
        root = Path(out["target_dir"])
        doc = json.loads((root / "config.json").read_text(encoding="utf-8"))
        assert doc["settings"]["durable_sessions"] is False
        readme = (root / "README.md").read_text(encoding="utf-8")
        assert "yelp-data" in readme
        assert "post_trace" in readme


def test_existing_beer_tree_pins_sessions_off(tmp_path: Path) -> None:
    cfg = HelperConfig(
        state_dir=tmp_path / "state",
        default_bucket="beer-sample",
        default_scope="_default",
    )
    first = write_beer_sample(cfg, tmp_path / "demo_beer_sample")
    assert first["ok"] is True
    root = Path(first["local_dir"])
    config_path = root / "config.json"
    doc = json.loads(config_path.read_text(encoding="utf-8"))
    doc["settings"]["durable_sessions"] = True
    config_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    (root / "README.md").write_text("old readme\n", encoding="utf-8")
    again = write_beer_sample(cfg, root)
    assert again["ok"] is True
    assert again.get("written") is False
    pinned = json.loads(config_path.read_text(encoding="utf-8"))
    assert pinned["settings"]["durable_sessions"] is False
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "yelp-data" in readme
    assert "old readme" not in readme
