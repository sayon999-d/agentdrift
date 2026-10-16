"""Application service for cross-agent workspace memory."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from agentdrift.core.workspace_repository import InMemoryWorkspaceRepository, WorkspaceRepository


class WorkspaceService:
    def __init__(self, repository: WorkspaceRepository | None = None) -> None:
        self.repository = repository or InMemoryWorkspaceRepository()

    async def register_workspace_session(
        self,
        session_id: str,
        *,
        repository_token: str | None = None,
        active_branch: str | None = None,
        architecture_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self.repository.upsert_session(
            {
                "id": session_id,
                "repository_token": repository_token,
                "active_branch": active_branch,
                "architecture_metadata": architecture_metadata or {},
            }
        )

    async def record_agent_work(
        self,
        session_id: str,
        agent_name: str,
        files_touched: list[str],
        summary: str,
        diff_hash: str,
        *,
        action_type: str = "edit",
        exported_contracts: dict[str, Any] | None = None,
        audit_status: str = "passed",
    ) -> dict[str, Any]:
        if action_type not in {"create", "edit", "audit", "refactor"}:
            raise ValueError("action_type must be create, edit, audit, or refactor")
        if action_type == "audit" and audit_status not in {"passed", "flagged"}:
            raise ValueError("audit_status must be passed or flagged")
        action = await self.repository.record_action(
            {
                "id": str(uuid.uuid4()),
                "session_id": session_id,
                "agent_name": agent_name,
                "action_type": action_type,
                "files_touched": sorted(set(files_touched)),
                "summary": summary,
                "diff_hash": diff_hash,
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
        for key, payload in (exported_contracts or {}).items():
            await self.repository.upsert_artifact(
                {
                    "session_id": session_id,
                    "artifact_key": key,
                    "producer_agent": agent_name,
                    "schema_payload": payload,
                    "status": "verified"
                    if action_type == "audit" and audit_status == "passed"
                    else "draft",
                }
            )
        if action_type == "audit":
            for path in action["files_touched"]:
                await self.repository.record_audit(
                    {
                        "session_id": session_id,
                        "file_path": path,
                        "last_scanned_commit_or_hash": diff_hash,
                        "scan_status": audit_status,
                        "auditor_agent": agent_name,
                    }
                )
        await self.repository.complete_task_claim(session_id, self._normalize_task(summary))
        return action

    async def get_incremental_context(
        self,
        session_id: str,
        target_scope: str = "all",
        querying_agent: str = "unknown",
        query: str | None = None,
    ) -> dict[str, Any]:
        actions = await self.repository.list_actions(session_id)
        artifacts = await self.repository.list_artifacts(session_id)
        workspace = await self.repository.get_session(session_id)
        scope_words = {
            "backend": ("api", "server", "backend", "db", "migration"),
            "frontend": ("web", "ui", "frontend", "component"),
            "audit": ("audit", "security"),
            "all": (),
        }.get(target_scope, ())
        if scope_words:
            actions = [
                a
                for a in actions
                if any(
                    w in (a["summary"] + " " + " ".join(a["files_touched"])).lower()
                    for w in scope_words
                )
            ]
            artifacts = [
                a for a in artifacts if any(w in a["artifact_key"].lower() for w in scope_words)
            ]
        if query and query.strip():
            terms = set(re.findall(r"[a-z0-9]+", query.lower()))
            matching_actions = [
                a
                for a in actions
                if terms.intersection(
                    set(
                        re.findall(
                            r"[a-z0-9]+",
                            a["summary"].lower() + " " + " ".join(a["files_touched"]).lower(),
                        )
                    )
                )
            ]
            matching_artifacts = [
                a
                for a in artifacts
                if terms.intersection(
                    set(
                        re.findall(
                            r"[a-z0-9]+",
                            a["artifact_key"].lower() + " " + str(a["schema_payload"]).lower(),
                        )
                    )
                )
            ]
            actions, artifacts = matching_actions, matching_artifacts
        actions.sort(key=lambda a: a.get("created_at", ""), reverse=True)
        return {
            "session_id": session_id,
            "querying_agent": querying_agent,
            "workspace": workspace,
            "recent_work": [
                {
                    "agent": a["agent_name"],
                    "action": a["action_type"],
                    "files": a["files_touched"],
                    "summary": a["summary"],
                    "hash": a["diff_hash"],
                }
                for a in actions[:30]
            ],
            "contracts": [
                {
                    "key": a["artifact_key"],
                    "producer": a["producer_agent"],
                    "status": a["status"],
                    "schema": a["schema_payload"],
                }
                for a in artifacts
            ],
            "module_boundaries": sorted(
                {p.split("/")[0] for a in actions for p in a["files_touched"] if "/" in p}
            ),
        }

    async def get_pending_audit_files(
        self, session_id: str, auditor_agent: str
    ) -> list[dict[str, Any]]:
        actions = await self.repository.list_actions(session_id)
        audits = {a["file_path"]: a for a in await self.repository.list_audits(session_id)}
        latest: dict[str, dict[str, Any]] = {}
        for action in actions:
            if action["action_type"] == "audit":
                continue
            for path in action["files_touched"]:
                if path not in latest or action.get("created_at", "") > latest[path].get(
                    "created_at", ""
                ):
                    latest[path] = action
        return [
            {
                "file_path": path,
                "last_change_hash": action["diff_hash"],
                "agent_name": action["agent_name"],
                "summary": action["summary"],
            }
            for path, action in latest.items()
            if path not in audits
            or audits[path].get("last_scanned_commit_or_hash") != action["diff_hash"]
        ]

    async def assert_task_novelty(
        self,
        session_id: str,
        proposed_task: str,
        proposed_files: list[str],
        *,
        claiming_agent: str | None = None,
    ) -> dict[str, Any]:
        task = self._normalize_task(proposed_task)
        files = set(proposed_files)
        for action in reversed(await self.repository.list_actions(session_id)):
            overlap = files.intersection(action["files_touched"])
            same_task = task == self._normalize_task(action["summary"])
            if overlap and same_task:
                return {
                    "status": "BLOCKED_REDUNDANT",
                    "prior_agent": action["agent_name"],
                    "prior_summary": action["summary"],
                    "prior_files": action["files_touched"],
                    "prior_hash": action["diff_hash"],
                }
        if claiming_agent:
            claim = await self.repository.claim_task(
                {
                    "session_id": session_id,
                    "agent_name": claiming_agent,
                    "task_description": proposed_task,
                    "normalized_task": task,
                    "target_files": sorted(files),
                }
            )
            if not claim.get("is_new", False):
                return {
                    "status": "BLOCKED_REDUNDANT",
                    "prior_agent": claim["agent_name"],
                    "prior_summary": claim["task_description"],
                    "prior_files": claim["target_files"],
                    "claim_status": claim["status"],
                }
        return {"status": "PERMITTED", "warning": None}

    @staticmethod
    def _normalize_task(task: str) -> str:
        return re.sub(r"\W+", " ", task.lower()).strip()

    async def detect_redundancy_and_drift(
        self,
        session_id: str,
        proposed_task: str,
        proposed_files: list[str],
        *,
        claiming_agent: str | None = None,
    ) -> dict[str, Any]:
        return await self.assert_task_novelty(
            session_id, proposed_task, proposed_files, claiming_agent=claiming_agent
        )

    async def timeline(self, session_id: str) -> list[dict[str, Any]]:
        actions = await self.repository.list_actions(session_id)
        return sorted(actions, key=lambda a: a.get("created_at", ""))


def default_service() -> WorkspaceService:
    from app.config import get_settings

    settings = get_settings()
    repository = None
    if settings.async_db_url:
        from agentdrift.core.workspace_repository import PostgresWorkspaceRepository

        repository = PostgresWorkspaceRepository()
    return WorkspaceService(repository)
