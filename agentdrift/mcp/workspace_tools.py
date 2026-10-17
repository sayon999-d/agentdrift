"""Tool schemas and handlers for the workspace memory MCP surface."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from agentdrift.core.task_execution_commit import TaskExecutionCommit
from agentdrift.core.workspace_service import WorkspaceService, default_service

_service: WorkspaceService | None = None


def get_service() -> WorkspaceService:
    global _service
    if _service is None:
        _service = default_service()
    return _service


def set_service(service: WorkspaceService | None) -> None:
    global _service
    _service = service


TOOLS = [
    {
        "name": "mcp__record_task_execution_commit",
        "description": "Record completed agent work as a structured, auditable commit history entry.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "commit_id": {"type": "string"},
                "timestamp": {"type": "string", "format": "date-time"},
                "agent_id": {"type": "string"},
                "task_intent": {"type": "string"},
                "execution_summary": {"type": "string"},
                "files_touched": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "change_type": {
                                "type": "string",
                                "enum": ["added", "modified", "deleted", "audited"],
                            },
                            "diff_summary": {"type": "string"},
                        },
                        "required": ["path", "change_type"],
                    },
                },
                "exported_contracts": {"type": "object"},
                "status": {
                    "type": "string",
                    "enum": ["completed", "reverted", "audited"],
                },
            },
            "required": ["session_id", "agent_id", "task_intent", "execution_summary"],
        },
    },
    {
        "name": "mcp__get_workspace_state",
        "description": "Read structured commit history, file changes, and exported workspace contracts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "scope": {"type": "string", "enum": ["backend", "frontend", "audit", "all"]},
                "query": {"type": "string"},
            },
            "required": ["session_id", "scope"],
        },
    },
    {
        "name": "mcp__record_action",
        "description": "Compatibility tool; records legacy arguments as a structured commit history entry.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "agent_name": {"type": "string"},
                "action_type": {"type": "string", "enum": ["create", "edit", "audit", "refactor"]},
                "files_touched": {"type": "array", "items": {"type": "string"}},
                "summary": {"type": "string"},
                "diff_hash": {"type": "string"},
                "exported_contracts": {"type": "object"},
                "scan_status": {"type": "string", "enum": ["passed", "flagged"]},
            },
            "required": ["session_id", "agent_name", "action_type", "files_touched", "summary"],
        },
    },
    {
        "name": "mcp__get_pending_audits",
        "description": "List changed files whose latest content hash has not been audited.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "auditor_name": {"type": "string"},
                "scope": {"type": "string"},
            },
            "required": ["session_id", "auditor_name"],
        },
    },
    {
        "name": "mcp__assert_task_novelty",
        "description": "Check whether a task duplicates recent work on the same files.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "task_description": {"type": "string"},
                "target_files": {"type": "array", "items": {"type": "string"}},
                "querying_agent": {"type": "string"},
            },
            "required": ["session_id", "task_description", "target_files"],
        },
    },
]


async def call_tool(name: str, args: dict[str, Any]) -> Any:
    service = get_service()
    sid = args["session_id"]
    if name == "mcp__record_task_execution_commit":
        commit = TaskExecutionCommit.model_validate(
            {key: value for key, value in args.items() if key != "session_id"}
        )
        warning = await service.detect_redundancy_and_drift(
            sid, commit.task_intent, [record.path for record in commit.files_touched]
        )
        saved = await service.record_task_execution_commit(sid, commit)
        return {
            "commit_id": saved["commit_id"],
            "recorded": True,
            "commit": saved,
            "duplicate_check": warning,
        }
    if name == "mcp__get_workspace_state":
        return await service.get_incremental_context(
            sid, args.get("scope", "all"), args.get("querying_agent", "unknown"), args.get("query")
        )
    if name == "mcp__record_action":
        diff_hash = (
            args.get("diff_hash")
            or hashlib.sha256(
                json.dumps(
                    [sorted(set(args["files_touched"])), args["summary"]], separators=(",", ":")
                ).encode()
            ).hexdigest()
        )
        warning = await service.detect_redundancy_and_drift(
            sid, args["summary"], args["files_touched"]
        )
        action = await service.record_agent_work(
            sid,
            args["agent_name"],
            args["files_touched"],
            args["summary"],
            diff_hash,
            action_type=args["action_type"],
            exported_contracts=args.get("exported_contracts"),
            audit_status=args.get("scan_status", "passed"),
        )
        return {"checkpoint_id": action["id"], "recorded": True, "drift": warning}
    if name == "mcp__get_pending_audits":
        pending = await service.get_pending_audit_files(sid, args["auditor_name"])
        scope = args.get("scope")
        return [row for row in pending if not scope or row["file_path"].startswith(scope)]
    if name == "mcp__assert_task_novelty":
        return await service.assert_task_novelty(
            sid,
            args["task_description"],
            args["target_files"],
            claiming_agent=args.get("querying_agent", "unknown"),
        )
    raise KeyError(f"Unknown tool: {name}")
