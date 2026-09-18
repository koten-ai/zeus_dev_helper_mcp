"""Invariants required to publish to PyPI and the official MCP Registry."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from zeus_dev_helper_mcp import __version__

ROOT = Path(__file__).resolve().parents[1]
MCP_NAME = "io.github.koten-ai/zeus-dev-helper"
PYPI_NAME = "zeus-dev-helper-mcp"


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())


def _server() -> dict:
    return json.loads((ROOT / "server.json").read_text())


def test_versions_aligned() -> None:
    py_ver = _pyproject()["project"]["version"]
    server = _server()
    assert py_ver == __version__
    assert server["version"] == py_ver
    assert server["packages"][0]["version"] == py_ver


def test_server_json_pypi_package() -> None:
    server = _server()
    assert server["name"] == MCP_NAME
    assert 1 <= len(server["description"]) <= 100
    assert server["repository"]["url"] == "https://github.com/koten-ai/zeus_dev_helper_mcp"
    assert server["repository"]["source"] == "github"
    pkg = server["packages"][0]
    assert pkg["registryType"] == "pypi"
    assert pkg["identifier"] == PYPI_NAME
    assert pkg["transport"]["type"] == "stdio"
    assert pkg["runtimeHint"] == "uvx"
    assert _pyproject()["project"]["name"] == PYPI_NAME
    env_names = {item["name"] for item in pkg["environmentVariables"]}
    assert "ZEUS_URL" in env_names
    assert "ZEUS_PASSWORD" in env_names
    secrets = {item["name"] for item in pkg["environmentVariables"] if item.get("isSecret")}
    assert secrets == {"ZEUS_USERNAME", "ZEUS_PASSWORD", "ZEUS_BEARER_TOKEN", "GITHUB_TOKEN"}


def test_readme_has_mcp_name_marker() -> None:
    readme = (ROOT / "README.md").read_text()
    assert f"mcp-name: {MCP_NAME}" in readme


def test_license_is_bsd_3_clause() -> None:
    project = _pyproject()["project"]
    assert project["license"] == "BSD-3-Clause"
    assert "LICENSE" in project.get("license-files", [])
    assert "License :: OSI Approved :: BSD License" in project["classifiers"]
    license_text = (ROOT / "LICENSE").read_text()
    assert "BSD 3-Clause License" in license_text
    assert "Copyright (c) 2026, Koten AI" in license_text
    readme = (ROOT / "README.md").read_text()
    assert "BSD-3-Clause" in readme
    assert "[LICENSE](LICENSE)" in readme
