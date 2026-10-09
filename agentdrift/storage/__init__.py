"""Storage abstraction: one interface, two backends.

- Local (default)  -> :class:`LocalHybridStore` (SQLite + LanceDB, ``~/.agentdrift/``)
- Cloud (URL set)  -> :class:`SupabasePgVectorStore` (Supabase Postgres + pgvector)

Selection: :func:`get_store` returns the Supabase backend when
``SUPABASE_DATABASE_URL`` (or ``AGENTDRIFT_DATABASE_URL``) is set, else local.
"""

from agentdrift.storage.base import BaseStore, DriftReport
from agentdrift.storage.factory import backend_name, get_store
from agentdrift.storage.local import LocalHybridStore

__all__ = ["BaseStore", "DriftReport", "LocalHybridStore", "backend_name", "get_store"]
