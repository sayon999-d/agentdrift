"""Backend selection: Supabase when a database URL is set, else local hybrid."""

from __future__ import annotations

from agentdrift.storage.base import BaseStore
from agentdrift.storage.supabase import resolve_url


def backend_name() -> str:
    """'supabase-pgvector' when configured, else 'local-hybrid'."""
    return "supabase-pgvector" if resolve_url() else "local-hybrid"


def get_store(data_dir: str | None = None) -> BaseStore:
    """Return the configured store (lazy: no network I/O on selection)."""
    url = resolve_url()
    if url:
        from agentdrift.storage.supabase import SupabasePgVectorStore

        return SupabasePgVectorStore(url)
    from agentdrift.storage.local import LocalHybridStore

    return LocalHybridStore(data_dir=data_dir)
