"""Regression checks for wheel-safe console script entrypoints."""

import importlib
import tomllib
from pathlib import Path


def test_console_scripts_target_installed_package_modules():
    project = tomllib.loads(Path("pyproject.toml").read_text())
    assert project["project"]["scripts"] == {
        "agentdrift": "agentdrift.cli:main",
        "agentdrift-mcp": "agentdrift.mcp.server:main",
    }
    assert callable(importlib.import_module("agentdrift.cli").main)
    assert callable(importlib.import_module("agentdrift.mcp.server").main)


def test_package_version_matches_project_metadata():
    project = tomllib.loads(Path("pyproject.toml").read_text())
    from agentdrift import __version__

    assert project["project"]["version"] == __version__
