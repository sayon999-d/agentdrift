"""Application service for cross-agent workspace memory."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from agentdrift.core.task_execution_commit import FileChangeRecord, TaskExecutionCommit
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
        task_intent: str | None = None,
    ) -> dict[str, Any]:
        if action_type not in {"create", "edit", "audit", "refactor"}:
            raise ValueError("action_type must be create, edit, audit, or refactor")
        if action_type == "audit" and audit_status not in {"passed", "flagged"}:
            raise ValueError("audit_status must be passed or flagged")
        change_type = {
            "create": "added",
            "edit": "modified",
            "refactor": "modified",
            "audit": "audited",
        }[action_type]
        commit = TaskExecutionCommit(
            agent_id=agent_name,
            task_intent=task_intent or summary,
            execution_summary=summary,
            files_touched=[
                FileChangeRecord(path=path, change_type=change_type) for path in sorted(set(files_touched))
            ],
            exported_contracts=exported_contracts,
            status="audited" if action_type == "audit" else "completed",
        )
        action = await self.record_task_execution_commit(session_id, commit, diff_hash=diff_hash)
        return self._commit_as_action(action, diff_hash)

    async def record_task_execution_commit(
        self,
        session_id: str,
        commit: TaskExecutionCommit,
        *,
        diff_hash: str | None = None,
        audit_status: str = "passed",
    ) -> dict[str, Any]:
        if audit_status not in {"passed", "flagged"}:
            raise ValueError("audit_status must be passed or flagged")
        payload = commit.model_dump(mode="json")
        payload["session_id"] = session_id
        payload["diff_hash"] = diff_hash or hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        saved = await self.repository.record_commit(payload)
        for key, contract in (commit.exported_contracts or {}).items():
            await self.repository.upsert_artifact(
                {
                    "session_id": session_id,
                    "artifact_key": key,
                    "producer_agent": commit.agent_id,
                    "schema_payload": contract,
                    "status": "verified" if commit.status == "audited" else "draft",
                }
            )
        if commit.status == "audited":
            for record in commit.files_touched:
                if record.change_type == "audited":
                    await self.repository.record_audit(
                        {
                            "session_id": session_id,
                            "file_path": record.path,
                            "last_scanned_commit_or_hash": payload["diff_hash"],
                            "scan_status": audit_status,
                            "auditor_agent": commit.agent_id,
                        }
                    )
        await self.repository.complete_task_claim(
            session_id, self._normalize_task(commit.task_intent)
        )
        return {**saved, "diff_hash": payload["diff_hash"]}

    @staticmethod
    def _commit_as_action(commit: dict[str, Any], diff_hash: str) -> dict[str, Any]:
        files = commit.get("files_touched", [])
        paths = [f["path"] if isinstance(f, dict) else f.path for f in files]
        first_change = files[0].get("change_type", "modified") if files and isinstance(files[0], dict) else "modified"
        action_type = {
            "added": "create",
            "modified": "edit",
            "deleted": "edit",
            "audited": "audit",
        }[first_change]
        return {
            **commit,
            "id": commit["commit_id"],
            "agent_name": commit["agent_id"],
            "action_type": action_type,
            "files_touched": paths,
            "file_change_records": files,
            "summary": commit["execution_summary"],
            "diff_hash": diff_hash,
            "created_at": commit["timestamp"],
        }

    async def get_incremental_context(
        self,
        session_id: str,
        target_scope: str = "all",
        querying_agent: str = "unknown",
        query: str | None = None,
    ) -> dict[str, Any]:
        actions = await self._list_actions(session_id)
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
                            a.get("task_intent", a["summary"]).lower()
                            + " "
                            + a["summary"].lower()
                            + " "
                            + " ".join(a["files_touched"]).lower(),
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
                    "commit_id": a["id"],
                    "agent_id": a["agent_name"],
                    "task_intent": a.get("task_intent", a["summary"]),
                    "execution_summary": a["summary"],
                    "files_touched": a.get("file_change_records", []),
                    "exported_contracts": a.get("exported_contracts"),
                    "status": a.get("status", "completed"),
                    "timestamp": a["created_at"],
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
        actions = await self._list_actions(session_id)
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
        for action in reversed(await self._list_actions(session_id)):
            overlap = files.intersection(action["files_touched"])
            same_task = task == self._normalize_task(action.get("task_intent", action["summary"]))
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
        actions = await self._list_actions(session_id)
        return sorted(actions, key=lambda a: a.get("created_at", ""))

    async def _list_actions(self, session_id: str) -> list[dict[str, Any]]:
        commits = await self.repository.list_commits(session_id)
        return [self._commit_as_action(commit, commit.get("diff_hash", "")) for commit in commits]


def default_service() -> WorkspaceService:
    from app.config import get_settings

    settings = get_settings()
    repository = None
    if settings.async_db_url:
        from agentdrift.core.workspace_repository import PostgresWorkspaceRepository

        repository = PostgresWorkspaceRepository()
    return WorkspaceService(repository)
