"""Backward-compatible shim for :mod:`agentdrift.mcp.server`."""
from agentdrift.mcp.server import *  # noqa: F401,F403
from agentdrift.mcp.server import main
from agentdrift.mcp.server import _BearerAuthMiddleware

if __name__ == "__main__":
    main()
