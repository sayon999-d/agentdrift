"""AgentDrift shared library.

Layout note: ``app/`` is the FastAPI daemon package and ``cli.py`` /
``mcp_server.py`` are runtime entrypoints; this ``agentdrift/`` package holds
the backend-agnostic storage abstraction (``agentdrift.storage``) shared by
both runtimes.
"""

__version__ = "0.1.0"
