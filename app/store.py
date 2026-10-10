"""Storage layer: Supabase Postgres when DATABASE_URL is set, else hybrid
embedded (SQLite + LanceDB at ~/.agentdrift), else in-memory fallback.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import desc, func, select

from app import database
from app.config import get_settings
from app.drift import decide_drift
from app.models import AgentExecution, AgentSession, DriftDetection

log = logging.getLogger("agentdrift.store")


def _now():
    return datetime.now(UTC)


def _row_to_session(s: AgentSession) -> dict:
    return {
        "session_id": s.session_id,
        "agent_id": s.agent_id,
        "parent_session_id": s.parent_session_id,
        "status": s.status,
        "metadata": s.meta or {},
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    }


def _row_to_execution(e: AgentExecution) -> dict:
    emb = e.payload_embedding
    if emb is not None and not isinstance(emb, list):
        try:
            emb = list(emb)
        except Exception:
            emb = None
    return {
        "execution_id": e.execution_id,
        "session_id": e.session_id,
        "parent_execution_id": e.parent_execution_id,
        "agent_id": e.agent_id,
        "node_id": e.node_id,
        "sequence": e.sequence,
        "status": e.status,
        "input_payload": e.input_payload or {},
        "output_payload": e.output_payload or {},
        "thinking_trace": e.thinking_trace,
        "state_hash": e.state_hash,
        "payload_embedding": emb,
        "metadata": e.meta or {},
        "frozen_at": e.frozen_at,
        "created_at": e.created_at,
    }


def _row_to_detection(d: DriftDetection) -> dict:
    return {
        "detection_id": d.detection_id,
        "session_id": d.session_id,
        "execution_id": d.execution_id,
        "prior_execution_id": d.prior_execution_id,
        "kind": d.kind,
        "agent_id": d.agent_id,
        "similarity": d.similarity,
        "threshold": d.threshold,
        "evidence": d.evidence or {},
        "created_at": d.created_at,
    }


class MemoryStore:
    """Process-local fallback (also used by tests)."""

    def __init__(self) -> None:
        self.sessions: dict[str, dict] = {}
        self.executions: dict[str, dict] = {}
        self.detections: dict[str, dict] = {}

    # sessions
    def create_session(self, data: dict) -> dict:
        sid = data.get("session_id") or f"sess_{uuid.uuid4().hex[:12]}"
        if sid in self.sessions:
            raise ValueError("session already exists")
        now = _now()
        row = {
            "session_id": sid,
            "agent_id": data["agent_id"],
            "parent_session_id": data.get("parent_session_id"),
            "status": data.get("status", "active"),
            "metadata": data.get("metadata", {}),
            "created_at": now,
            "updated_at": now,
        }
        self.sessions[sid] = row
        return row

    def list_sessions(self, limit=100, offset=0) -> tuple[list[dict], int]:
        rows = sorted(self.sessions.values(), key=lambda r: r["created_at"], reverse=True)
        return rows[offset : offset + limit], len(rows)

    def update_session(self, sid: str, patch: dict) -> dict | None:
        row = self.sessions.get(sid)
        if not row:
            return None
        if patch.get("status"):
            row["status"] = patch["status"]
        if patch.get("metadata") is not None:
            row["metadata"] = patch["metadata"]
        if "parent_session_id" in patch:
            row["parent_session_id"] = patch["parent_session_id"]
        row["updated_at"] = _now()
        return row

    # executions
    def _prior(self, session_id: str, sequence: int) -> dict | None:
        cands = [
            e
            for e in self.executions.values()
            if e["session_id"] == session_id and e["sequence"] < sequence
        ]
        return max(cands, key=lambda e: e["sequence"]) if cands else None

    def ingest_execution(
        self, data: dict, threshold: float | None = None
    ) -> tuple[dict, dict | None]:
        sid = data["session_id"]
        if sid not in self.sessions:
            raise KeyError("session not found")
        seq = data.get("sequence")
        if seq is None:
            seqs = [e["sequence"] for e in self.executions.values() if e["session_id"] == sid]
            seq = (max(seqs) + 1) if seqs else 1
        prior = self._prior(sid, seq)
        current = {**data, "sequence": seq}
        if not current.get("execution_id"):
            current["execution_id"] = f"exec_{uuid.uuid4().hex[:12]}"
        decision = decide_drift(prior=prior, current=current, threshold=threshold)
        current["payload_embedding"] = decision.pop("embedding")
        now = _now()
        current["created_at"] = now
        if data.get("freeze"):
            current["frozen_at"] = now
        self.executions[current["execution_id"]] = current
        det = None
        if decision["kind"] != "no_drift":
            det = {
                "detection_id": uuid.uuid4(),
                "session_id": sid,
                "execution_id": current["execution_id"],
                "prior_execution_id": prior["execution_id"] if prior else None,
                "kind": decision["kind"],
                "agent_id": current["agent_id"],
                "similarity": decision["similarity"],
                "threshold": decision["threshold"],
                "evidence": decision["evidence"],
                "created_at": now,
            }
            self.detections[str(det["detection_id"])] = det
        return current, det

    def list_executions(
        self, session_id: str | None = None, limit=200, offset=0
    ) -> tuple[list[dict], int]:
        rows = list(self.executions.values())
        if session_id:
            rows = [r for r in rows if r["session_id"] == session_id]
        rows.sort(key=lambda r: r["sequence"])
        total = len(rows)
        return rows[offset : offset + limit], total

    def list_detections(
        self, session_id: str | None = None, limit=200, offset=0
    ) -> tuple[list[dict], int]:
        rows = list(self.detections.values())
        if session_id:
            rows = [r for r in rows if r["session_id"] == session_id]
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return rows[offset : offset + limit], len(rows)

    def stats(self) -> dict:
        kinds: dict[str, int] = {}
        for d in self.detections.values():
            kinds[d["kind"]] = kinds.get(d["kind"], 0) + 1
        return {
            "sessions": len(self.sessions),
            "executions": len(self.executions),
            "detections": len(self.detections),
            "by_kind": kinds,
        }


MEM = MemoryStore()


def use_db() -> bool:
    return database.db_configured() and database.get_session_factory() is not None


# ---- DB-backed implementations ----
async def db_create_session(data: dict) -> dict:
    factory = database.get_session_factory()
    async with factory() as s:
        row = AgentSession(
            session_id=data.get("session_id") or f"sess_{uuid.uuid4().hex[:12]}",
            agent_id=data["agent_id"],
            parent_session_id=data.get("parent_session_id"),
            status=data.get("status", "active"),
            meta=data.get("metadata", {}),
        )
        s.add(row)
        await s.commit()
        await s.refresh(row)
        return _row_to_session(row)


async def db_get_session(sid: str) -> dict | None:
    factory = database.get_session_factory()
    async with factory() as s:
        row = await s.get(AgentSession, sid)
        return _row_to_session(row) if row else None


async def db_list_sessions(limit=100, offset=0) -> tuple[list[dict], int]:
    factory = database.get_session_factory()
    async with factory() as s:
        total = (await s.execute(select(func.count()).select_from(AgentSession))).scalar() or 0
        rows = (
            (
                await s.execute(
                    select(AgentSession)
                    .order_by(desc(AgentSession.created_at))
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return [_row_to_session(r) for r in rows], total


async def db_update_session(sid: str, patch: dict) -> dict | None:
    factory = database.get_session_factory()
    async with factory() as s:
        row = await s.get(AgentSession, sid)
        if not row:
            return None
        if patch.get("status"):
            row.status = patch["status"]
        if patch.get("metadata") is not None:
            row.meta = patch["metadata"]
        if "parent_session_id" in patch:
            row.parent_session_id = patch["parent_session_id"]
        await s.commit()
        await s.refresh(row)
        return _row_to_session(row)


async def db_ingest_execution(
    data: dict, threshold: float | None = None
) -> tuple[dict, dict | None]:
    factory = database.get_session_factory()
    settings = get_settings()
    thr = threshold if threshold is not None else settings.DRIFT_SIMILARITY_THRESHOLD
    async with factory() as s:
        sess = await s.get(AgentSession, data["session_id"])
        if not sess:
            raise KeyError("session not found")
        seq = data.get("sequence")
        if seq is None:
            mx = (
                await s.execute(
                    select(func.max(AgentExecution.sequence)).where(
                        AgentExecution.session_id == data["session_id"]
                    )
                )
            ).scalar()
            seq = (mx + 1) if mx is not None else 1
        prior_row = (
            (
                await s.execute(
                    select(AgentExecution)
                    .where(
                        AgentExecution.session_id == data["session_id"],
                        AgentExecution.sequence < seq,
                    )
                    .order_by(desc(AgentExecution.sequence))
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        prior = _row_to_execution(prior_row) if prior_row else None
        current = {**data, "sequence": seq}
        if not current.get("execution_id"):
            current["execution_id"] = f"exec_{uuid.uuid4().hex[:12]}"
        decision = decide_drift(prior=prior, current=current, threshold=thr)
        emb = decision.pop("embedding")
        row = AgentExecution(
            execution_id=current["execution_id"],
            session_id=current["session_id"],
            parent_execution_id=current.get("parent_execution_id"),
            agent_id=current["agent_id"],
            node_id=current.get("node_id", "default"),
            sequence=seq,
            status=current.get("status", "ok"),
            input_payload=current.get("input_payload", {}),
            output_payload=current.get("output_payload", {}),
            thinking_trace=current.get("thinking_trace"),
            state_hash=current.get("state_hash"),
            payload_embedding=emb,
            meta=current.get("metadata", {}),
            frozen_at=_now() if current.get("freeze") else None,
        )
        s.add(row)
        det_dict = None
        if decision["kind"] != "no_drift":
            det = DriftDetection(
                session_id=row.session_id,
                execution_id=row.execution_id,
                prior_execution_id=prior["execution_id"] if prior else None,
                kind=decision["kind"],
                agent_id=row.agent_id,
                similarity=decision["similarity"],
                threshold=decision["threshold"],
                evidence=decision["evidence"],
            )
            s.add(det)
            await s.flush()
            det_dict = _row_to_detection(det)
        await s.commit()
        await s.refresh(row)
        out = _row_to_execution(row)
        return out, det_dict


async def db_list_executions(session_id: str | None, limit=200, offset=0):
    factory = database.get_session_factory()
    async with factory() as s:
        q = select(AgentExecution)
        c = select(func.count()).select_from(AgentExecution)
        if session_id:
            q = q.where(AgentExecution.session_id == session_id)
            c = c.where(AgentExecution.session_id == session_id)
        total = (await s.execute(c)).scalar() or 0
        rows = (
            (await s.execute(q.order_by(AgentExecution.sequence).limit(limit).offset(offset)))
            .scalars()
            .all()
        )
        return [_row_to_execution(r) for r in rows], total


async def db_list_detections(session_id: str | None, limit=200, offset=0):
    factory = database.get_session_factory()
    async with factory() as s:
        q = select(DriftDetection)
        c = select(func.count()).select_from(DriftDetection)
        if session_id:
            q = q.where(DriftDetection.session_id == session_id)
            c = c.where(DriftDetection.session_id == session_id)
        total = (await s.execute(c)).scalar() or 0
        rows = (
            (
                await s.execute(
                    q.order_by(desc(DriftDetection.created_at)).limit(limit).offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return [_row_to_detection(r) for r in rows], total


async def db_stats() -> dict:
    factory = database.get_session_factory()
    async with factory() as s:
        sessions = (await s.execute(select(func.count()).select_from(AgentSession))).scalar() or 0
        executions = (
            await s.execute(select(func.count()).select_from(AgentExecution))
        ).scalar() or 0
        detections = (
            await s.execute(select(func.count()).select_from(DriftDetection))
        ).scalar() or 0
        return {
            "sessions": sessions,
            "executions": executions,
            "detections": detections,
            "by_kind": {},
        }


# ---- Unified dispatch: Postgres -> hybrid (SQLite + LanceDB) -> memory ----
def get_hybrid():
    """Hybrid store instance, or None (missing deps / init failure -> MEM fallback)."""
    try:
        from app.hybrid_store import get_hybrid_store

        return get_hybrid_store()
    except Exception as exc:
        log.debug("hybrid store unavailable, using in-memory fallback: %s", exc)
        return None


def hybrid_info() -> dict | None:
    try:
        from app.hybrid_store import HEALTH_DB_MODE, HEALTH_STORAGE_PATH
    except Exception:
        return None
    if get_hybrid() is None:
        return None
    import os as _os

    override = _os.getenv("AGENTDRIFT_DATA_DIR", "").strip()
    return {"mode": HEALTH_DB_MODE, "storage_path": override or HEALTH_STORAGE_PATH}


async def create_session(data: dict) -> dict:
    if use_db():
        return await db_create_session(data)
    h = get_hybrid()
    return await h.create_session(data) if h is not None else MEM.create_session(data)


async def get_session(sid: str) -> dict | None:
    if use_db():
        return await db_get_session(sid)
    h = get_hybrid()
    return await h.get_session(sid) if h is not None else MEM.sessions.get(sid)


async def ensure_session(session_id: str, agent_id: str = "unknown") -> dict:
    if use_db():
        existing = await db_get_session(session_id)
        if existing:
            return existing
        try:
            return await db_create_session({"session_id": session_id, "agent_id": agent_id})
        except Exception:
            return await db_get_session(session_id)
    h = get_hybrid()
    if h is not None:
        return await h.ensure_session(session_id, agent_id)
    if session_id not in MEM.sessions:
        MEM.create_session({"session_id": session_id, "agent_id": agent_id})
    return MEM.sessions[session_id]


async def list_sessions(limit: int = 100, offset: int = 0):
    if use_db():
        return await db_list_sessions(limit, offset)
    h = get_hybrid()
    return (
        await h.list_sessions(limit, offset) if h is not None else MEM.list_sessions(limit, offset)
    )


async def update_session(sid: str, patch: dict) -> dict | None:
    if use_db():
        return await db_update_session(sid, patch)
    h = get_hybrid()
    return await h.update_session(sid, patch) if h is not None else MEM.update_session(sid, patch)


async def ingest_execution(data: dict, threshold: float | None = None):
    if use_db():
        return await db_ingest_execution(data, threshold)
    h = get_hybrid()
    if h is not None:
        return await h.ingest_execution(data, threshold)
    return MEM.ingest_execution(data, threshold)


async def list_executions(session_id: str | None = None, limit: int = 200, offset: int = 0):
    if use_db():
        return await db_list_executions(session_id, limit, offset)
    h = get_hybrid()
    if h is not None:
        return await h.list_executions(session_id, limit, offset)
    return MEM.list_executions(session_id, limit, offset)


async def list_detections(session_id: str | None = None, limit: int = 200, offset: int = 0):
    if use_db():
        return await db_list_detections(session_id, limit, offset)
    h = get_hybrid()
    if h is not None:
        return await h.list_detections(session_id, limit, offset)
    return MEM.list_detections(session_id, limit, offset)


async def stats() -> dict:
    if use_db():
        return await db_stats()
    h = get_hybrid()
    return await h.stats() if h is not None else MEM.stats()
