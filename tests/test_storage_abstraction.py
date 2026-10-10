"""Storage abstraction + MCP server contracts (local backend, no network)."""

import pytest

from agentdrift.storage.base import BaseStore, DriftReport
from agentdrift.storage.factory import backend_name, get_store
from agentdrift.storage.local import LocalHybridStore


@pytest.fixture(autouse=True)
def _no_supabase_env(monkeypatch):
    monkeypatch.delenv("SUPABASE_DATABASE_URL", raising=False)
    monkeypatch.delenv("AGENTDRIFT_DATABASE_URL", raising=False)


def test_factory_defaults_to_local():
    assert backend_name() == "local-hybrid"
    store = get_store()
    assert isinstance(store, LocalHybridStore)
    assert isinstance(store, BaseStore)


def test_factory_selects_supabase_without_connecting(monkeypatch):
    monkeypatch.setenv("SUPABASE_DATABASE_URL", "postgresql://user:pw@host:5432/db")
    from agentdrift.storage.supabase import SupabasePgVectorStore

    assert backend_name() == "supabase-pgvector"
    store = get_store()
    assert isinstance(store, SupabasePgVectorStore)
    assert store._pool is None  # lazy: no network I/O on selection


async def test_local_record_list_and_drift():
    store = LocalHybridStore()
    sid = "storage-abstract-test"
    await store.record_execution(
        sid, "agent-x", "node-a", {"output": "repeat this"}, "thinking a", None
    )
    await store.record_execution(
        sid, "agent-x", "node-a", {"output": "repeat this"}, "thinking a", None
    )
    recent = await store.list_recent_executions(sid, limit=50)
    assert len(recent) == 2
    assert recent[0]["sequence"] >= recent[1]["sequence"]  # newest first
    report = await store.check_drift(sid, threshold=0.92)
    assert isinstance(report, DriftReport)
    assert report.ok and report.detections >= 1
    assert report.loops[0]["kind"] == "ping_pong_loop"


async def test_mcp_tools_end_to_end():
    from fastmcp import Client

    from mcp_server import create_mcp

    mcp = create_mcp(LocalHybridStore())
    async with Client(mcp) as client:
        names = {t.name for t in await client.list_tools()}
        assert {"record_execution", "check_drift", "list_recent_executions", "get_health"} <= names
        health = (await client.call_tool("get_health", {})).data
        assert health["status"] == "ok" and health["backend"] == "local-hybrid"
        rec = (
            await client.call_tool(
                "record_execution",
                {
                    "session_id": "mcp-e2e",
                    "agent_id": "agent-mcp",
                    "node_id": "n1",
                    "payload": {"v": 1},
                },
            )
        ).data
        assert rec["session_id"] == "mcp-e2e"
        recent = (await client.call_tool("list_recent_executions", {"session_id": "mcp-e2e"})).data
        assert isinstance(recent, list) and len(recent) >= 1
