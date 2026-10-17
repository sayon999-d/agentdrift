"""AgentDrift shared library.

The package owns the CLI, MCP server, API, and backend-agnostic storage
abstraction so installed entrypoints resolve entirely within the package.
"""

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

_project_file = Path(__file__).resolve().parent.parent / "pyproject.toml"
try:
    __version__ = tomllib.loads(_project_file.read_text(encoding="utf-8"))["project"]["version"]
except (FileNotFoundError, KeyError, tomllib.TOMLDecodeError):
    try:
        __version__ = version("agentdrift-mcp")
    except PackageNotFoundError:
        __version__ = "0+unknown"
