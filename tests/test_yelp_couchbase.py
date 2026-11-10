"""Yelp Couchbase .env merge. The password value is never an argument."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from zeus_dev_helper_mcp.clarify import Gate
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.process_login import _LOGIN_KEYS, load_process_login
from zeus_dev_helper_mcp.yelp import apply_couchbase_env, write_yelp_couchbase_env

SECRET = "cb-secret-sentinel"


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_login_keys_do_not_include_the_couchbase_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert "COUCHBASE_PASSWORD" not in _LOGIN_KEYS
    monkeypatch.delenv("COUCHBASE_PASSWORD", raising=False)
    monkeypatch.delenv("ZEUS_USERNAME", raising=False)
    monkeypatch.delenv("ZEUS_PASSWORD", raising=False)
    path = tmp_path / "login.env"
    path.write_text(
        f"ZEUS_USERNAME=tap-user\nZEUS_PASSWORD=zeus-only\nCOUCHBASE_PASSWORD={SECRET}\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)
    out = load_process_login(str(path))
    assert out["ok"] is True
    assert "COUCHBASE_PASSWORD" not in out["loaded"]
    assert os.environ.get("COUCHBASE_PASSWORD") in (None, "")
    assert SECRET not in json.dumps(out)


def test_write_creates_env_from_example_without_a_password_value(tmp_path: Path) -> None:
    root = tmp_path / "demo_yelp"
    root.mkdir()
    (root / ".env.example").write_text(
        "COUCHBASE_QUERY_URL=http://old.example:8093\nOTHER=kept\n",
        encoding="utf-8",
    )
    report = write_yelp_couchbase_env(root, "http://localhost:8093", "Administrator")
    env = root / ".env"
    text = env.read_text(encoding="utf-8")
    assert _mode(env) == 0o600
    assert "COUCHBASE_QUERY_URL=http://localhost:8093\n" in text
    assert "COUCHBASE_USERNAME=Administrator\n" in text
    assert "COUCHBASE_PASSWORD=\n" in text
    assert "OTHER=kept" in text
    assert SECRET not in text
    assert report["env_change"] is False
    assert report["settings_written"] == ["COUCHBASE_QUERY_URL", "COUCHBASE_USERNAME"]
    assert report["secret_presence"] == {"COUCHBASE_PASSWORD": False}
    assert ".env" in (root / ".gitignore").read_text(encoding="utf-8")
    assert SECRET not in json.dumps(report)


def test_write_keeps_an_existing_password_line(tmp_path: Path) -> None:
    root = tmp_path / "demo_yelp"
    root.mkdir()
    env = root / ".env"
    env.write_text(
        "export COUCHBASE_QUERY_URL=http://old.example:8093\n"
        "COUCHBASE_USERNAME=old-user\n"
        f'export COUCHBASE_PASSWORD="{SECRET}"\n',
        encoding="utf-8",
    )
    report = write_yelp_couchbase_env(root, "http://127.0.0.1:8093", "cb-admin")
    text = env.read_text(encoding="utf-8")
    assert f'export COUCHBASE_PASSWORD="{SECRET}"' in text
    assert "export COUCHBASE_QUERY_URL=http://127.0.0.1:8093" in text
    assert "COUCHBASE_USERNAME=cb-admin" in text
    assert _mode(env) == 0o600
    assert report["env_change"] is True
    assert report["settings_written"] == ["COUCHBASE_QUERY_URL", "COUCHBASE_USERNAME"]
    assert report["secret_presence"] == {"COUCHBASE_PASSWORD": True}
    assert "COUCHBASE_PASSWORD" not in report["settings_written"]
    assert SECRET not in json.dumps(report)


def test_apply_writes_strings_and_skips_userinfo_and_other_samples(tmp_path: Path) -> None:
    root = tmp_path / "demo_yelp"
    root.mkdir()
    (root / "README.md").write_text("# yelp\n", encoding="utf-8")
    payload = {
        "ok": True,
        "sample": {"sample": "demo_yelp", "name": "demo_yelp"},
        "local_dir": str(root),
        "next_action": "start",
    }
    skipped = apply_couchbase_env(
        dict(payload),
        Gate(
            proceed=True,
            cards_accepted=True,
            couchbase_query_url=f"http://user:{SECRET}@127.0.0.1:8093",
            couchbase_username="Administrator",
            couchbase_password_in_env=False,
        ),
    )
    assert not (root / ".env").exists()
    assert "settings_written" not in skipped
    assert SECRET not in json.dumps(skipped)

    written = apply_couchbase_env(
        dict(payload),
        Gate(
            proceed=True,
            cards_accepted=True,
            couchbase_query_url="http://127.0.0.1:8093",
            couchbase_username="cb-admin",
            couchbase_password_in_env=False,
        ),
    )
    text = (root / ".env").read_text(encoding="utf-8")
    assert "COUCHBASE_QUERY_URL=http://127.0.0.1:8093" in text
    assert "COUCHBASE_USERNAME=cb-admin" in text
    assert "COUCHBASE_PASSWORD=\n" in text
    assert SECRET not in text
    assert written["settings_written"] == ["COUCHBASE_QUERY_URL", "COUCHBASE_USERNAME"]
    assert written["secret_presence"] == {"COUCHBASE_PASSWORD": False}
    assert "Fill COUCHBASE_PASSWORD" in written["next_action"]
    assert str(root / ".env") in written["next_action"]
    assert "python -m local_guide" in written["next_action"]
    assert "Do not type the password into the form" in written["next_action"]
    assert SECRET not in json.dumps(written)

    beer = {"ok": True, "sample": "beer", "local_dir": str(root), "next_action": "pour"}
    before = (root / ".env").read_text(encoding="utf-8")
    assert apply_couchbase_env(beer, Gate(proceed=True, cards_accepted=True)) == beer
    assert (root / ".env").read_text(encoding="utf-8") == before

    quiet = apply_couchbase_env(
        dict(payload),
        Gate(proceed=True, cards_accepted=False, couchbase_password_in_env=False),
    )
    assert "settings_written" not in quiet


def test_config_json_does_not_receive_the_couchbase_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zeus_dev_helper_mcp.yelp_config import write_yelp_config

    monkeypatch.delenv("ZEUS_PASSWORD", raising=False)
    monkeypatch.setenv("ZEUS_PASSWORD", "zeus-only-sentinel")
    root = tmp_path / "demo_yelp"
    root.mkdir()
    (root / ".env").write_text(f"COUCHBASE_PASSWORD={SECRET}\n", encoding="utf-8")
    cfg = HelperConfig(
        state_dir=tmp_path / "state",
        zeus_url="http://zeus-dev.local:8080",
        default_bucket="yelp-demo",
        default_scope="_default",
        zeus_auth_mode="none",
    )
    assert write_yelp_config(cfg, root)["created"] is True
    text = (root / "config.json").read_text(encoding="utf-8")
    assert SECRET not in text
    assert "COUCHBASE" not in text
    assert "zeus-only-sentinel" in text
