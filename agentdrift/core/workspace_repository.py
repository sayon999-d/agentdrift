"""Persistence boundary for shared workspace memory."""

from __future__ import annotations

import json
from typing import Any, Protocol

from sqlalchemy import text

from app.database import get_session_factory


class WorkspaceRepository(Protocol):
    async def upsert_session(self, session: dict[str, Any]) -> dict[str, Any]: ...
    async def record_action(self, action: dict[str, Any]) -> dict[str, Any]: ...
    async def list_actions(self, session_id: str) -> list[dict[str, Any]]: ...
    async def upsert_artifact(self, artifact: dict[str, Any]) -> dict[str, Any]: ...
    async def list_artifacts(self, session_id: str) -> list[dict[str, Any]]: ...
    async def list_audits(self, session_id: str) -> list[dict[str, Any]]: ...
    async def record_audit(self, audit: dict[str, Any]) -> dict[str, Any]: ...
    async def get_session(self, session_id: str) -> dict[str, Any] | None: ...
    async def claim_task(self, claim: dict[str, Any]) -> dict[str, Any]: ...
    async def complete_task_claim(self, session_id: str, normalized_task: str) -> None: ...


class InMemoryWorkspaceRepository:
    """Deterministic repository for local mode and tests."""

    def __init__(self) -> None:
        self.actions: list[dict[str, Any]] = []
        self.artifacts: dict[tuple[str, str], dict[str, Any]] = {}
        self.audits: dict[tuple[str, str], dict[str, Any]] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.task_claims: list[dict[str, Any]] = []

    async def record_action(self, action):
        self.actions.append(dict(action))
        return dict(action)

    async def list_actions(self, session_id):
        return [dict(a) for a in self.actions if a["session_id"] == session_id]

    async def upsert_artifact(self, artifact):
        key = (artifact["session_id"], artifact["artifact_key"])
        self.artifacts[key] = dict(artifact)
        return dict(artifact)

    async def list_artifacts(self, session_id):
        return [dict(a) for a in self.artifacts.values() if a["session_id"] == session_id]

    async def list_audits(self, session_id):
        return [dict(a) for a in self.audits.values() if a["session_id"] == session_id]

    async def record_audit(self, audit):
        self.audits[(audit["session_id"], audit["file_path"])] = dict(audit)
        return dict(audit)

    async def get_session(self, session_id):
        return self.sessions.get(session_id)

    async def claim_task(self, claim):
        files = set(claim["target_files"])
        for existing in self.task_claims:
            if (
                existing["session_id"] == claim["session_id"]
                and existing["normalized_task"] == claim["normalized_task"]
                and existing.get("status") != "released"
                and files.intersection(existing["target_files"])
            ):
                return {**existing, "is_new": False}
        saved = {**claim, "is_new": True, "status": "active"}
        self.task_claims.append(saved)
        return saved

    async def complete_task_claim(self, session_id, normalized_task):
        for claim in self.task_claims:
            if claim["session_id"] == session_id and claim["normalized_task"] == normalized_task:
                claim["status"] = "completed"

    async def upsert_session(self, session):
        existing = self.sessions.get(session["id"], {})
        self.sessions[session["id"]] = {**existing, **session}
        return dict(self.sessions[session["id"]])


class PostgresWorkspaceRepository:
    """PostgreSQL repository using the application's async SQLAlchemy engine."""

    @staticmethod
    def _json(row):
        return dict(row._mapping) if row else None

    async def _run(self, sql: str, params: dict[str, Any], *, many: bool = False):
        factory = get_session_factory()
        if factory is None:
            raise RuntimeError("PostgreSQL is not configured")
        async with factory() as session:
            result = await session.execute(text(sql), params)
            rows = result.fetchall() if many else None
            if not many:
                row = result.fetchone()
                await session.commit()
                return self._json(row)
            return [self._json(row) for row in rows]

    async def record_action(self, a):
        params = {
            key: a[key]
            for key in (
                "session_id",
                "agent_name",
                "action_type",
                "files_touched",
                "summary",
                "diff_hash",
            )
        }
        return await self._run(
            """WITH ensured AS (INSERT INTO workspace_sessions(id)
            VALUES (:session_id) ON CONFLICT (id) DO UPDATE SET id=EXCLUDED.id RETURNING id)
            INSERT INTO agent_actions
            (session_id,agent_name,action_type,files_touched,summary,diff_hash)
            VALUES (:session_id,:agent_name,:action_type,:files_touched,:summary,:diff_hash)
            RETURNING *""",
            params,
        )

    async def upsert_session(self, s):
        s = {**s, "architecture_metadata": json.dumps(s.get("architecture_metadata", {}))}
        return await self._run(
            """INSERT INTO workspace_sessions
            (id,repository_token,active_branch,architecture_metadata)
            VALUES (:id,:repository_token,:active_branch,CAST(:architecture_metadata AS jsonb))
            ON CONFLICT(id) DO UPDATE SET
            repository_token=COALESCE(EXCLUDED.repository_token,workspace_sessions.repository_token),
            active_branch=COALESCE(EXCLUDED.active_branch,workspace_sessions.active_branch),
            architecture_metadata=CASE WHEN EXCLUDED.architecture_metadata='{}'::jsonb
                THEN workspace_sessions.architecture_metadata ELSE EXCLUDED.architecture_metadata END,
            updated_at=now() RETURNING *""",
            s,
        )

    async def list_actions(self, sid):
        return await self._run(
            "SELECT * FROM agent_actions WHERE session_id=:sid ORDER BY created_at",
            {"sid": sid},
            many=True,
        )

    async def upsert_artifact(self, a):
        a = {**a, "schema_payload": json.dumps(a["schema_payload"])}
        return await self._run(
            """INSERT INTO workspace_artifacts
            (session_id,artifact_key,producer_agent,schema_payload,status)
            VALUES (:session_id,:artifact_key,:producer_agent,CAST(:schema_payload AS jsonb),:status)
            ON CONFLICT(session_id,artifact_key) DO UPDATE SET producer_agent=EXCLUDED.producer_agent,
            schema_payload=EXCLUDED.schema_payload,status=EXCLUDED.status,updated_at=now() RETURNING *""",
            a,
        )

    async def list_artifacts(self, sid):
        return await self._run(
            "SELECT * FROM workspace_artifacts WHERE session_id=:sid ORDER BY artifact_key",
            {"sid": sid},
            many=True,
        )

    async def list_audits(self, sid):
        return await self._run(
            "SELECT * FROM audit_checkpoints WHERE session_id=:sid", {"sid": sid}, many=True
        )

    async def record_audit(self, a):
        return await self._run(
            """INSERT INTO audit_checkpoints
            (session_id,file_path,last_scanned_commit_or_hash,scan_status,auditor_agent)
            VALUES (:session_id,:file_path,:last_scanned_commit_or_hash,:scan_status,:auditor_agent)
            ON CONFLICT(session_id,file_path) DO UPDATE SET
            last_scanned_commit_or_hash=EXCLUDED.last_scanned_commit_or_hash,
            scan_status=EXCLUDED.scan_status,auditor_agent=EXCLUDED.auditor_agent,updated_at=now()
            RETURNING *""",
            a,
        )

    async def get_session(self, sid):
        return await self._run("SELECT * FROM workspace_sessions WHERE id=:sid", {"sid": sid})

    async def claim_task(self, claim):
        factory = get_session_factory()
        if factory is None:
            raise RuntimeError("PostgreSQL is not configured")
        async with factory() as session:
            async with session.begin():
                await session.execute(
                    text(
                        "INSERT INTO workspace_sessions(id) VALUES (:sid) ON CONFLICT(id) DO NOTHING"
                    ),
                    {"sid": claim["session_id"]},
                )
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:sid))"),
                    {"sid": claim["session_id"]},
                )
                found = await session.execute(
                    text("""SELECT *, false AS is_new FROM workspace_task_claims
                    WHERE session_id=:session_id AND normalized_task=:normalized_task AND status <> 'released'
                    AND target_files && CAST(:target_files AS text[]) ORDER BY created_at LIMIT 1"""),
                    claim,
                )
                row = found.fetchone()
                if row:
                    return dict(row._mapping)
                result = await session.execute(
                    text("""INSERT INTO workspace_task_claims
                    (session_id,agent_name,task_description,normalized_task,target_files)
                    VALUES (:session_id,:agent_name,:task_description,:normalized_task,:target_files)
                    RETURNING *, true AS is_new"""),
                    claim,
                )
                return dict(result.fetchone()._mapping)

    async def complete_task_claim(self, session_id, normalized_task):
        factory = get_session_factory()
        if factory is None:
            raise RuntimeError("PostgreSQL is not configured")
        async with factory() as session:
            await session.execute(
                text(
                    "UPDATE workspace_task_claims SET status='completed',updated_at=now() WHERE session_id=:sid AND normalized_task=:task"
                ),
                {"sid": session_id, "task": normalized_task},
            )
            await session.commit()
