"""Backward-compatible source-tree shim for :mod:`agentdrift.cli`."""

from agentdrift.cli import *  # noqa: F401,F403
from agentdrift.cli import main

if __name__ == "__main__":
    main()
