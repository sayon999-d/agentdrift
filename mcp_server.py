"""Backward-compatible shim for :mod:`agentdrift.mcp.server`."""

from agentdrift.mcp.server import *  # noqa: F401,F403
from agentdrift.mcp.server import main

if __name__ == "__main__":
    main()
