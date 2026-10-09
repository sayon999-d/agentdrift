"""Cloud backend: Supabase PostgreSQL + pgvector.

Requires ``SUPABASE_DATABASE_URL`` (or ``AGENTDRIFT_DATABASE_URL``) pointing
at a database with :file:`migrations/002_supabase_mcp.sql` applied, plus the
``asyncpg`` and ``pgvector`` packages. Connections are lazy: constructing the
store never touches the network; the pool is created on first use.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from agentdrift.storage.base import BaseStore, DriftReport

EMBEDDING_DIM = 384


def resolve_url(url: str | None = None) -> str | None:
    if url:
        return url
    return (os.getenv("SUPABASE_DATABASE_URL", "").strip()
            or os.getenv("AGENTDRIFT_DATABASE_URL", "").strip()
            or None)


class SupabasePgVectorStore(BaseStore):
    """Supabase Postgres (relational) + pgvector (384-d embeddings)."""

    def __init__(self, database_url: str | None = None) -> None:
        resolved = resolve_url(database_url)
        if not resolved:
            raise RuntimeError(
                "Supabase backend needs SUPABASE_DATABASE_URL "
                "(or AGENTDRIFT_DATABASE_URL) to be set")
        self.database_url = resolved
        self._pool = None

    @property
    def backend(self) -> str:
        return "supabase-pgvector"

    async def _pool_conn(self):
        try:
            import asyncpg
            from pgvector.asyncpg import register_vector
        except ImportError as exc:
            raise RuntimeError(
                "supabase backend needs the 'asyncpg' and 'pgvector' packages") from exc
        if self._pool is None:
            async def _init(conn):
                await register_vector(conn)

            self._pool = await asyncpg.create_pool(
                self.database_url, min_size=1, max_size=5, init=_init)
        return self._pool

    async def _embedding(self, payload: dict, thinking) -> list[float]:
        from app.embeddings import get_embedding_service

        svc = get_embedding_service()
        import asyncio

        vec = await asyncio.to_thread(svc.embed_payload, payload, thinking)
        return [float(x) for x in vec[:EMBEDDING_DIM]]

    @staticmethod
    def _state_hash(payload: dict) -> str:
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:32]

    @staticmethod
    def _row_execution(row) -> dict[str, Any]:
        payload = row["payload"] if isinstance(row.get("payload"), dict) else {}
        try:
            payload = json.loads(row["payload"]) if isinstance(row.get("payload"), str) else payload
        except (TypeError, ValueError):
            payload = {}
        emb = row.get("embedding")
        try:
            emb = [float(x) for x in list(emb)] if emb is not None else None
        except TypeError:
            emb = None
        return {
            "execution_id": str(row["execution_id"]),
            "session_id": row["session_id"],
            "agent_id": row["agent_id"],
            "node_id": row["node_id"],
            "sequence": row["sequence"],
            "input_payload": payload.get("input_payload", payload) if isinstance(payload, dict) else {},
            "output_payload": payload.get("output_payload", payload) if isinstance(payload, dict) else {},
            "thinking_trace": row.get("thinking"),
            "state_hash": row.get("state_hash"),
            "payload_embedding": emb,
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        }

    async def record_execution(
        self,
        session_id: str,
        agent_id: str,
        node_id: str,
        payload: dict[str, Any],
        thinking: str | dict[str, Any] | None,
        embedding: list[float] | None,
    ) -> dict[str, Any]:
        pool = await self._pool_conn()
        payload = dict(payload or {})
        state_hash = payload.pop("state_hash", None) or self._state_hash(payload)
        thinking_text = thinking if isinstance(thinking, str) else json.dumps(
            thinking, default=str) if thinking is not None else None
        vec = [float(x) for x in embedding] if embedding else await self._embedding(payload, thinking)
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO agent_sessions(session_id, agent_id) VALUES($1, $2)"
                    " ON CONFLICT(session_id) DO NOTHING",
                    session_id, agent_id or "unknown")
                seq = await conn.fetchval(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM agent_executions"
                    " WHERE session_id = $1", session_id)
                row = await conn.fetchrow(
                    "INSERT INTO agent_executions(session_id, agent_id, node_id, sequence,"
                    " payload, thinking, state_hash, embedding)"
                    " VALUES($1, $2, $3, $4, $5, $6, $7, $8)"
                    " RETURNING execution_id, session_id, agent_id, node_id, sequence,"
                    " payload, thinking, state_hash, embedding, created_at",
                    session_id, agent_id or "unknown", node_id or "default", seq,
                    json.dumps(payload, default=str), thinking_text, state_hash, vec)
        return self._row_execution(dict(row))

    async def check_drift(self, session_id: str | None, threshold: float = 0.92) -> DriftReport:
        pool = await self._pool_conn()
        loops: list[dict[str, Any]] = []
        async with pool.acquire() as conn:
            if session_id:
                sessions = [session_id]
            else:
                sessions = [r["session_id"] for r in
                            await conn.fetch("SELECT session_id FROM agent_sessions")]
            for sid in sessions:
                rows = await conn.fetch(
                    "SELECT execution_id, session_id, agent_id, node_id, sequence, payload,"
                    " thinking, state_hash, embedding, created_at FROM agent_executions"
                    " WHERE session_id = $1 ORDER BY sequence", sid)
                for prev, cur in zip(rows, rows[1:]):
                    ph, ch = prev["state_hash"], cur["state_hash"]
                    same_hash = bool(ph and ch and str(ph) == str(ch))
                    sim: float | None = None
                    if cur["embedding"] is not None and prev["embedding"] is not None:
                        try:
                            sim = round(float(await conn.fetchval(
                                "SELECT 1 - (embedding <=> $1) FROM agent_executions"
                                " WHERE execution_id = $2",
                                list(cur["embedding"]),
                                str(prev["execution_id"]))), 4)
                        except Exception:
                            sim = None
                    if sim is None:
                        sim = 1.0 if same_hash else 0.0
                    if same_hash or sim >= threshold:
                        reason = ("matching state_hash" if same_hash
                                  else f"cosine {sim:.4f} >= {threshold}")
                        exists = await conn.fetchval(
                            "SELECT 1 FROM drift_detections WHERE execution_id = $1"
                            " AND kind = 'ping_pong_loop'",
                            str(cur["execution_id"]))
                        if not exists:
                            await conn.execute(
                                "INSERT INTO drift_detections(session_id, execution_id,"
                                " prior_execution_id, agent_id, kind, similarity, threshold, evidence)"
                                " VALUES($1, $2, $3, $4, 'ping_pong_loop', $5, $6, $7)",
                                sid, str(cur["execution_id"]), str(prev["execution_id"]),
                                cur["agent_id"], sim, threshold,
                                json.dumps({"reason": reason, "state_hash": ch if same_hash else None,
                                            "prev_sequence": prev["sequence"],
                                            "sequence": cur["sequence"]}))
                        loops.append({
                            "session_id": sid,
                            "execution_id": str(cur["execution_id"]),
                            "prior_execution_id": str(prev["execution_id"]),
                            "kind": "ping_pong_loop",
                            "similarity": round(float(sim), 4),
                            "threshold": threshold,
                            "evidence": {"reason": reason},
                        })
        return DriftReport(ok=True, session_id=session_id, detections=len(loops),
                           threshold=threshold, loops=loops)

    async def list_recent_executions(
        self, session_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        pool = await self._pool_conn()
        async with pool.acquire() as conn:
            if session_id:
                rows = await conn.fetch(
                    "SELECT execution_id, session_id, agent_id, node_id, sequence, payload,"
                    " thinking, state_hash, embedding, created_at FROM agent_executions"
                    " WHERE session_id = $1 ORDER BY created_at DESC LIMIT $2",
                    session_id, limit)
            else:
                rows = await conn.fetch(
                    "SELECT execution_id, session_id, agent_id, node_id, sequence, payload,"
                    " thinking, state_hash, embedding, created_at FROM agent_executions"
                    " ORDER BY created_at DESC LIMIT $1", limit)
        out = [self._row_execution(dict(r)) for r in rows]
        for row in out:
            row.pop("payload_embedding", None)
        return out

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
