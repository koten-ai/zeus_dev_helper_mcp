import json
from pathlib import Path

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.config_lint import (
    lint_app,
    lint_app_code,
    lint_runtime_config,
    redact_public,
)


def test_redact_secret_values() -> None:
    public = redact_public(
        {
            "zeus": {"url": "http://localhost:8080", "password": "hunter2", "username": "demo"},
            "llm_provider": {"api_key": "sk-secret", "api_key_env": "XAI_API_KEY"},
        }
    )
    dump = json.dumps(public)
    assert "hunter2" not in dump
    assert "sk-secret" not in dump
    assert public["zeus"]["password"] == "***"
    assert public["llm_provider"]["api_key_env"] == "XAI_API_KEY"
    assert public["zeus"]["url"] == "http://localhost:8080"


def test_lint_config_hub_port_and_secrets(tmp_path: Path) -> None:
    p = tmp_path / "config.json"
    p.write_text(
        json.dumps(
            {
                "zeus": {
                    "url": "http://localhost:9091",
                    "auth_mode": "basic",
                    "password": "s3cret",
                },
                "settings": {"ai_process_result": True},
                "session": {"semantic_cache": {"enabled": True}},
            }
        ),
        encoding="utf-8",
    )
    out = lint_runtime_config(HelperConfig(), path=str(p))
    assert out["ok"] is False
    dump = json.dumps(out)
    assert "s3cret" not in dump
    fields = {i["field"] for i in out["issues"]}
    assert "zeus.url" in fields
    assert any(i.get("failure_class") == "wrong_port_hub_vs_public" for i in out["issues"])
    assert "zeus.password" in fields
    assert "settings.ai_process_result" in fields
    assert "session.semantic_cache.enabled" in fields


def test_lint_config_ok_8080(tmp_path: Path) -> None:
    p = tmp_path / "config.json"
    p.write_text(
        json.dumps(
            {
                "zeus": {"url": "http://localhost:8080", "auth_mode": "none", "password_env": "ZEUS_PASSWORD"},
                "settings": {"ai_process_result": False},
                "session": {"semantic_cache": {"enabled": False}},
                "default_sample": "beer",
                "samples": {"beer": {"bucket": "beer-sample", "scope": "_default", "collection": "_default"}},
            }
        ),
        encoding="utf-8",
    )
    out = lint_runtime_config(HelperConfig(), path=str(p))
    assert out["ok"] is True
    assert out["public"]["zeus"]["password_env"] == "ZEUS_PASSWORD"


def test_lint_app_stale_v1_and_hash_literal(tmp_path: Path) -> None:
    main = tmp_path / "main.py"
    main.write_text(
        "from zeus_client import ZeusClient, run_agent\n"
        "CONTRACT = 'md5:0123456789abcdef0123456789abcdef'\n"
        "def go():\n"
        "    import asyncio\n"
        "    asyncio.run(run_agent())\n"
        "    asyncio.run(run_agent())\n",
        encoding="utf-8",
    )
    out = lint_app_code(HelperConfig(), path=str(main))
    assert out["ok"] is False
    blob = json.dumps(out["issues"]).lower()
    assert "zeusclient" in blob or "run_agent" in blob
    assert any(i.get("failure_class") == "contract_hash_invent_forbidden" for i in out["issues"])
    assert any("asyncio.run" in i["message"] for i in out["issues"])


def test_lint_dockerfile_localhost(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text(
        "ENV ZEUS_URL=http://localhost:8080\nENV HUB=http://x:9091\n",
        encoding="utf-8",
    )
    out = lint_app_code(HelperConfig(), path=str(tmp_path))
    messages = " ".join(i["message"] for i in out["issues"])
    assert "localhost:8080" in messages
    assert any(i.get("failure_class") == "wrong_port_hub_vs_public" for i in out["issues"])


def test_lint_app_combines_config_and_code(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text(
        json.dumps({"zeus": {"url": "http://localhost:9091", "auth_mode": "none"}}),
        encoding="utf-8",
    )
    (tmp_path / "main.py").write_text(
        "from zeus_client import ZeusClient\n",
        encoding="utf-8",
    )
    out = lint_app(HelperConfig(), path=str(tmp_path))
    assert out["ok"] is False
    assert "runtime_config" in out["sections"]
    assert "app_code" in out["sections"]
    classes = {i.get("failure_class") for i in out["issues"]}
    assert "wrong_port_hub_vs_public" in classes
