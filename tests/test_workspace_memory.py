"""Shared memory service tests run entirely against the repository abstraction."""
import pytest

from agentdrift.core.workspace_repository import InMemoryWorkspaceRepository
from agentdrift.core.workspace_service import WorkspaceService


@pytest.fixture
def service():
    return WorkspaceService(InMemoryWorkspaceRepository())


@pytest.mark.asyncio
async def test_agent_b_sees_agent_a_summary(service):
    await service.record_agent_work("repo-1", "codex", ["api/routes.py"],
        "Added health endpoint", "abc123", action_type="create",
        exported_contracts={"api/v1/health": {"method": "GET", "response": "Health"}})
    digest = await service.get_incremental_context("repo-1", "all", "cline")
    assert digest["recent_work"][0]["summary"] == "Added health endpoint"
    assert digest["contracts"][0]["key"] == "api/v1/health"
    assert "source" not in digest


@pytest.mark.asyncio
async def test_pending_audits_only_include_new_or_changed_hashes(service):
    await service.record_agent_work("repo-1", "codex", ["a.py", "b.py"], "Implement feature", "h1")
    await service.record_agent_work("repo-1", "claude-audit", ["a.py"], "Security audit", "h1", action_type="audit")
    pending = await service.get_pending_audit_files("repo-1", "claude-audit")
    assert [row["file_path"] for row in pending] == ["b.py"]
    await service.record_agent_work("repo-1", "cline", ["a.py"], "Update feature", "h2")
    pending = await service.get_pending_audit_files("repo-1", "claude-audit")
    assert {row["file_path"] for row in pending} == {"a.py", "b.py"}


@pytest.mark.asyncio
async def test_identical_task_on_same_files_is_blocked(service):
    await service.record_agent_work("repo-1", "codex", ["src/auth.py"], "Add token validation", "h1", action_type="edit")
    result = await service.assert_task_novelty("repo-1", "Add token validation", ["src/auth.py"])
    assert result["status"] == "BLOCKED_REDUNDANT"
    assert result["prior_agent"] == "codex"
    assert result["prior_hash"] == "h1"


@pytest.mark.asyncio
async def test_novel_task_is_permitted(service):
    result = await service.assert_task_novelty("repo-1", "Add token validation", ["src/auth.py"])
    assert result["status"] == "PERMITTED"


@pytest.mark.asyncio
async def test_novelty_guard_claims_task_for_other_agents(service):
    first = await service.assert_task_novelty("repo-1", "Add token validation", ["src/auth.py"], claiming_agent="codex")
    second = await service.assert_task_novelty("repo-1", "Add token validation", ["src/auth.py"], claiming_agent="cline")
    assert first["status"] == "PERMITTED"
    assert second["status"] == "BLOCKED_REDUNDANT"
    assert second["prior_agent"] == "codex"


def test_authenticated_mcp_http_transport(monkeypatch):
    from fastapi.testclient import TestClient

    from agentdrift.mcp.workspace_tools import set_service
    from app.main import app

    svc = WorkspaceService(InMemoryWorkspaceRepository())
    set_service(svc)
    monkeypatch.setenv("AGENTDRIFT_SERVICE_TOKEN", "test-secret")
    monkeypatch.delenv("AGENTDRIFT_REQUIRE_AUTH", raising=False)
    try:
        # Do not enter the daemon lifespan: it seeds demo embeddings and may
        # load an optional model, neither of which belongs in these tests.
        client = TestClient(app)
        denied = client.post("/api/v1/mcp/tools/call", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert denied.status_code == 401
        response = client.post("/api/v1/mcp/tools/call",
            headers={"Authorization": "Bearer test-secret"},
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert response.status_code == 200
        names = [tool["name"] for tool in response.json()["result"]["tools"]]
        assert "mcp__get_workspace_state" in names
    finally:
        set_service(None)
