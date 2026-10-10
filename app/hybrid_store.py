"""Hybrid embedded storage engine: SQLite (relational) + LanceDB (vectors).

Layout (created automatically):
    <data_dir>/agentdrift.db        SQLite: sessions, executions, drift_detections
    <data_dir>/vectors.lance/       LanceDB: execution_vectors(execution_id, session_id, vector[384])

``<data_dir>`` defaults to ``~/.agentdrift`` and can be overridden with the
``AGENTDRIFT_DATA_DIR`` env var (used by the test-suite for isolation).

All public methods are ``async``; the underlying sqlite3 / LanceDB calls are
synchronous and run via ``asyncio.to_thread`` behind a lock so the FastAPI
event loop is never blocked.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger("agentdrift.hybrid")

try:
    import lancedb
except Exception:  # optional at import time; get_hybrid_store() raises clearly
    lancedb = None  # type: ignore[assignment]

try:
    import pyarrow as pa
except Exception:
    pa = None  # type: ignore[assignment]

EMBEDDING_DIM = 384
VECTOR_TABLE = "execution_vectors"
HEALTH_DB_MODE = "hybrid (sqlite + lancedb)"
HEALTH_STORAGE_PATH = "~/.agentdrift"

DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    status TEXT,
    metadata TEXT,
    created_at REAL
);
CREATE TABLE IF NOT EXISTS executions (
    execution_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    parent_execution_id TEXT,
    agent_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    status TEXT,
    input_payload TEXT,
    output_payload TEXT,
    thinking_trace TEXT,
    state_hash TEXT,
    created_at REAL
);
CREATE INDEX IF NOT EXISTS idx_executions_session_seq ON executions(session_id, sequence);
CREATE INDEX IF NOT EXISTS idx_executions_created ON executions(created_at);
CREATE TABLE IF NOT EXISTS drift_detections (
    detection_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    prior_execution_id TEXT,
    kind TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    similarity REAL NOT NULL,
    threshold REAL NOT NULL,
    evidence TEXT,
    created_at REAL
);
"""


def data_dir() -> Path:
    override = os.getenv("AGENTDRIFT_DATA_DIR", "").strip()
    base = Path(override).expanduser() if override else Path("~/.agentdrift").expanduser()
    base.mkdir(parents=True, exist_ok=True)
    return base


def _jdumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, default=str)


def _jloads(text, default):
    if text is None:
        return default
    if isinstance(text, (dict, list)):
        return text
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


def _ts(dt: float | None) -> datetime | None:
    return datetime.fromtimestamp(dt, tz=UTC) if dt is not None else None


class HybridStore:
    """SQLite + LanceDB persistence. Create via :func:`get_hybrid_store`."""

    def __init__(self, directory: Path) -> None:
        if lancedb is None or pa is None:
            raise RuntimeError("lancedb + pyarrow are required for the hybrid store")
        self.directory = directory
        self.db_path = directory / "agentdrift.db"
        self.vectors_path = directory / "vectors.lance"
        self._lock = threading.Lock()
        self._sql = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._sql.row_factory = sqlite3.Row
        with self._lock:
            self._sql.executescript(DDL)
            self._sql.commit()
        schema = pa.schema(
            [
                ("execution_id", pa.string()),
                ("session_id", pa.string()),
                ("vector", pa.list_(pa.float32(), EMBEDDING_DIM)),
            ]
        )
        lance_db = lancedb.connect(str(self.vectors_path))
        try:
            self._vectors = lance_db.open_table(VECTOR_TABLE)
        except Exception:
            try:
                self._vectors = lance_db.create_table(VECTOR_TABLE, schema=schema)
            except TypeError:  # very old lancedb without schema= kwarg
                self._vectors = lance_db.create_table(VECTOR_TABLE, data=[], schema=schema)
        log.info("hybrid store ready at %s", self.directory)

    # -- internal sync helpers (run under to_thread) ----------------------
    def _execute(self, sql: str, params: tuple = ()):
        with self._lock:
            cur = self._sql.execute(sql, params)
            self._sql.commit()
            return cur

    def _fetchall(self, sql: str, params: tuple = ()):
        with self._lock:
            return self._sql.execute(sql, params).fetchall()

    def _fetchone(self, sql: str, params: tuple = ()):
        with self._lock:
            return self._sql.execute(sql, params).fetchone()

    # -- row mapping --------------------------------------------------------
    @staticmethod
    def _session_out(row: sqlite3.Row) -> dict:
        return {
            "session_id": row["session_id"],
            "agent_id": row["agent_id"],
            "parent_session_id": None,
            "status": row["status"] or "active",
            "metadata": _jloads(row["metadata"], {}),
            "created_at": _ts(row["created_at"]),
            "updated_at": _ts(row["created_at"]),
        }

    @staticmethod
    def _payload_out(text) -> dict:
        parsed = _jloads(text, {})
        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed} if parsed is not None else {}

    @staticmethod
    def _execution_out(row: sqlite3.Row) -> dict:
        return {
            "execution_id": row["execution_id"],
            "session_id": row["session_id"],
            "parent_execution_id": row["parent_execution_id"],
            "agent_id": row["agent_id"],
            "node_id": row["node_id"],
            "sequence": row["sequence"],
            "status": row["status"] or "ok",
            "input_payload": HybridStore._payload_out(row["input_payload"]),
            "output_payload": HybridStore._payload_out(row["output_payload"]),
            "thinking_trace": _jloads(row["thinking_trace"], None),
            "state_hash": row["state_hash"],
            "payload_embedding": None,  # vectors live in LanceDB; fetched on demand
            "metadata": {},
            "frozen_at": None,
            "created_at": _ts(row["created_at"]),
        }

    @staticmethod
    def _detection_out(row: sqlite3.Row) -> dict:
        return {
            "detection_id": row["detection_id"],
            "session_id": row["session_id"],
            "execution_id": row["execution_id"],
            "prior_execution_id": row["prior_execution_id"],
            "kind": row["kind"],
            "agent_id": row["agent_id"],
            "similarity": row["similarity"],
            "threshold": row["threshold"],
            "evidence": _jloads(row["evidence"], {}),
            "created_at": _ts(row["created_at"]),
        }

    # -- sessions ------------------------------------------------------------
    async def create_session(self, data: dict) -> dict:
        def _op():
            sid = data.get("session_id") or f"sess_{uuid.uuid4().hex[:12]}"
            if self._fetchone("SELECT 1 FROM sessions WHERE session_id=?", (sid,)):
                raise ValueError("session already exists")
            now = time.time()
            self._execute(
                "INSERT INTO sessions(session_id, agent_id, status, metadata, created_at)"
                " VALUES(?,?,?,?,?)",
                (
                    sid,
                    data["agent_id"],
                    data.get("status", "active"),
                    _jdumps(data.get("metadata", {})),
                    now,
                ),
            )
            return self._session_out(
                self._fetchone("SELECT * FROM sessions WHERE session_id=?", (sid,))
            )

        return await asyncio.to_thread(_op)

    async def get_session(self, session_id: str) -> dict | None:
        def _op():
            row = self._fetchone("SELECT * FROM sessions WHERE session_id=?", (session_id,))
            return self._session_out(row) if row else None

        return await asyncio.to_thread(_op)

    async def ensure_session(self, session_id: str, agent_id: str = "unknown") -> dict:
        existing = await self.get_session(session_id)
        if existing:
            return existing
        try:
            return await self.create_session({"session_id": session_id, "agent_id": agent_id})
        except ValueError:
            return await self.get_session(session_id)  # raced creation

    async def list_sessions(self, limit: int = 100, offset: int = 0):
        def _op():
            total = self._fetchone("SELECT COUNT(*) AS n FROM sessions")["n"]
            rows = self._fetchall(
                "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)
            )
            return [self._session_out(r) for r in rows], total

        return await asyncio.to_thread(_op)

    async def update_session(self, session_id: str, patch: dict) -> dict | None:
        def _op():
            if not self._fetchone("SELECT 1 FROM sessions WHERE session_id=?", (session_id,)):
                return None
            if patch.get("status"):
                self._execute(
                    "UPDATE sessions SET status=? WHERE session_id=?", (patch["status"], session_id)
                )
            if patch.get("metadata") is not None:
                self._execute(
                    "UPDATE sessions SET metadata=? WHERE session_id=?",
                    (_jdumps(patch["metadata"]), session_id),
                )
            return self._session_out(
                self._fetchone("SELECT * FROM sessions WHERE session_id=?", (session_id,))
            )

        return await asyncio.to_thread(_op)

    # -- vectors --------------------------------------------------------------
    def _store_vector_sync(self, execution_id: str, session_id: str, vector: list[float]) -> None:
        vec = [float(x) for x in vector]
        with self._lock:
            try:
                self._vectors.delete(f"execution_id = '{execution_id}'")
            except Exception:
                pass
            self._vectors.add(
                [
                    {
                        "execution_id": execution_id,
                        "session_id": session_id,
                        "vector": vec,
                    }
                ]
            )

    def _cosine_via_search(
        self,
        session_id: str,
        query_vec: list[float],
        target_id: str,
        limit: int = 2000,
    ) -> float | None:
        """Cosine similarity from LanceDB vector search (1 - cosine distance)."""
        safe_sid = session_id.replace("'", "")
        safe_tid = target_id.replace("'", "")
        with self._lock:
            try:
                rows = (
                    self._vectors.search(query_vec, vector_column_name="vector")
                    .metric("cosine")
                    .where(f"session_id = '{safe_sid}'")
                    .limit(limit)
                    .to_list()
                )
            except Exception as exc:
                log.debug("vector search unavailable, will use local cosine: %s", exc)
                return None
        for row in rows:
            if str(row.get("execution_id")) == safe_tid:
                try:
                    return round(1.0 - float(row["_distance"]), 4)
                except (KeyError, TypeError, ValueError):
                    return None
        return None

    def _local_cosine(self, session_id: str, id_a: str, id_b: str) -> float | None:
        """Fallback: exact cosine over vectors fetched from LanceDB."""
        try:
            from app.embeddings import get_embedding_service

            svc = get_embedding_service()
            with self._lock:
                try:
                    arrow = self._vectors.to_arrow()
                except Exception:
                    return None
            cols = {name: arrow.column(name).to_pylist() for name in arrow.schema.names}
            vecs = {str(e): v for e, v in zip(cols.get("execution_id", []), cols.get("vector", []))}
            va, vb = vecs.get(id_a), vecs.get(id_b)
            if va is None or vb is None:
                return None
            return round(float(svc.cosine(va, vb)), 4)
        except Exception:
            return None

    async def pair_similarity(
        self, session_id: str, id_a: str, id_b: str, query_vec: list[float] | None = None
    ) -> float | None:
        """Similarity between two stored executions, preferring vector search."""

        def _op():
            if query_vec is not None:
                sim = self._cosine_via_search(session_id, query_vec, id_a)
                if sim is not None:
                    return sim
            return self._local_cosine(session_id, id_a, id_b)

        return await asyncio.to_thread(_op)

    # -- executions -------------------------------------------------------------
    async def ingest_execution(
        self, data: dict, threshold: float | None = None
    ) -> tuple[dict, dict | None]:
        from app.drift import decide_drift
        from app.embeddings import get_embedding_service

        def _insert_seq() -> tuple[int, str, dict | None]:
            if not self._fetchone(
                "SELECT 1 FROM sessions WHERE session_id=?", (data["session_id"],)
            ):
                raise KeyError("session not found")
            seq = data.get("sequence")
            if seq is None:
                row = self._fetchone(
                    "SELECT MAX(sequence) AS m FROM executions WHERE session_id=?",
                    (data["session_id"],),
                )
                seq = (row["m"] + 1) if row and row["m"] is not None else 1
            prior = self._fetchone(
                "SELECT * FROM executions WHERE session_id=? AND sequence<?"
                " ORDER BY sequence DESC LIMIT 1",
                (data["session_id"], seq),
            )
            eid = data.get("execution_id") or f"exec_{uuid.uuid4().hex[:12]}"
            return seq, eid, prior

        seq, eid, prior_row = await asyncio.to_thread(_insert_seq)
        svc = get_embedding_service()
        cur_vec = await asyncio.to_thread(
            svc.embed_payload, data.get("input_payload"), data.get("output_payload")
        )
        prior = self._execution_out(prior_row) if prior_row else None
        current = {**data, "execution_id": eid, "sequence": seq, "payload_embedding": cur_vec}
        decision = decide_drift(prior=prior, current=current, threshold=threshold)
        decision.pop("embedding", None)

        def _persist():
            now = time.time()
            self._execute(
                "INSERT INTO executions(execution_id, session_id, parent_execution_id,"
                " agent_id, node_id, sequence, status, input_payload, output_payload,"
                " thinking_trace, state_hash, created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    eid,
                    data["session_id"],
                    data.get("parent_execution_id"),
                    data["agent_id"],
                    data.get("node_id", "default"),
                    seq,
                    data.get("status", "ok"),
                    _jdumps(data.get("input_payload", {})),
                    _jdumps(data.get("output_payload", {})),
                    _jdumps(data.get("thinking_trace")),
                    data.get("state_hash"),
                    now,
                ),
            )
            det = None
            if decision["kind"] != "no_drift":
                did = uuid.uuid4().hex
                self._execute(
                    "INSERT INTO drift_detections(detection_id, session_id, execution_id,"
                    " prior_execution_id, kind, agent_id, similarity, threshold, evidence, created_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        did,
                        data["session_id"],
                        eid,
                        prior["execution_id"] if prior else None,
                        decision["kind"],
                        data["agent_id"],
                        decision["similarity"],
                        decision["threshold"],
                        _jdumps(decision["evidence"]),
                        now,
                    ),
                )
                det = self._detection_out(
                    self._fetchone("SELECT * FROM drift_detections WHERE detection_id=?", (did,))
                )
            out = self._execution_out(
                self._fetchone("SELECT * FROM executions WHERE execution_id=?", (eid,))
            )
            out["payload_embedding"] = cur_vec
            return out, det

        out, det = await asyncio.to_thread(_persist)
        await asyncio.to_thread(self._store_vector_sync, eid, data["session_id"], cur_vec)
        return out, det

    async def list_executions(
        self, session_id: str | None = None, limit: int = 200, offset: int = 0
    ):
        def _op():
            where, params = ("WHERE session_id=?", (session_id,)) if session_id else ("", ())
            total = self._fetchone(f"SELECT COUNT(*) AS n FROM executions {where}", params)["n"]
            rows = self._fetchall(
                f"SELECT * FROM executions {where} ORDER BY sequence LIMIT ? OFFSET ?",
                (*params, limit, offset),
            )
            return [self._execution_out(r) for r in rows], total

        return await asyncio.to_thread(_op)

    # -- detections ---------------------------------------------------------------
    async def list_detections(
        self, session_id: str | None = None, limit: int = 200, offset: int = 0
    ):
        def _op():
            where, params = ("WHERE session_id=?", (session_id,)) if session_id else ("", ())
            total = self._fetchone(f"SELECT COUNT(*) AS n FROM drift_detections {where}", params)[
                "n"
            ]
            rows = self._fetchall(
                f"SELECT * FROM drift_detections {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            )
            return [self._detection_out(r) for r in rows], total

        return await asyncio.to_thread(_op)

    async def has_loop_alert(self, execution_id: str) -> bool:
        def _op():
            return bool(
                self._fetchone(
                    "SELECT 1 FROM drift_detections WHERE execution_id=? AND kind='ping_pong_loop'",
                    (execution_id,),
                )
            )

        return await asyncio.to_thread(_op)

    async def record_loop(
        self,
        *,
        session_id: str,
        execution_id: str,
        prior_execution_id: str | None,
        agent_id: str,
        similarity: float,
        threshold: float,
        evidence: dict,
    ) -> None:
        def _op():
            if self._fetchone(
                "SELECT 1 FROM drift_detections WHERE execution_id=? AND kind='ping_pong_loop'",
                (execution_id,),
            ):
                return
            self._execute(
                "INSERT INTO drift_detections(detection_id, session_id, execution_id,"
                " prior_execution_id, kind, agent_id, similarity, threshold, evidence, created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    uuid.uuid4().hex,
                    session_id,
                    execution_id,
                    prior_execution_id,
                    "ping_pong_loop",
                    agent_id,
                    similarity,
                    threshold,
                    _jdumps(evidence),
                    time.time(),
                ),
            )

        await asyncio.to_thread(_op)

    async def stats(self) -> dict:
        def _op():
            s = self._fetchone("SELECT COUNT(*) AS n FROM sessions")["n"]
            e = self._fetchone("SELECT COUNT(*) AS n FROM executions")["n"]
            d = self._fetchone("SELECT COUNT(*) AS n FROM drift_detections")["n"]
            kinds: dict[str, int] = {}
            for row in self._fetchall(
                "SELECT kind, COUNT(*) AS n FROM drift_detections GROUP BY kind"
            ):
                kinds[row["kind"]] = row["n"]
            return {"sessions": s, "executions": e, "detections": d, "by_kind": kinds}

        return await asyncio.to_thread(_op)

    # -- sentinel scan ---------------------------------------------------------
    async def sentinel_scan(self, threshold: float) -> dict:
        """Flag consecutive steps with matching state_hash or LanceDB cosine
        similarity >= threshold as ping_pong_loop; persist alerts to SQLite."""
        from app.embeddings import get_embedding_service

        svc = get_embedding_service()

        def _sessions() -> list[str]:
            return [r["session_id"] for r in self._fetchall("SELECT session_id FROM sessions")]

        loops: list[dict] = []
        for sid in await asyncio.to_thread(_sessions):
            exes, _ = await self.list_executions(sid, limit=10000, offset=0)
            for prev, cur in zip(exes, exes[1:]):
                ph, ch = prev.get("state_hash"), cur.get("state_hash")
                same_hash = bool(ph and ch and str(ph) == str(ch))
                sim: float | None = None
                try:
                    cur_vec = await asyncio.to_thread(
                        svc.embed_payload, cur.get("input_payload"), cur.get("output_payload")
                    )
                    sim = await self.pair_similarity(
                        sid, str(prev["execution_id"]), str(cur["execution_id"]), cur_vec
                    )
                    if sim is None:  # vectors predate this engine version; backfill
                        await asyncio.to_thread(
                            self._store_vector_sync,
                            str(prev["execution_id"]),
                            sid,
                            await asyncio.to_thread(
                                svc.embed_payload,
                                prev.get("input_payload"),
                                prev.get("output_payload"),
                            ),
                        )
                        await asyncio.to_thread(
                            self._store_vector_sync, str(cur["execution_id"]), sid, cur_vec
                        )
                        sim = await self.pair_similarity(
                            sid, str(prev["execution_id"]), str(cur["execution_id"]), cur_vec
                        )
                except Exception as exc:
                    log.debug("similarity failed for %s: %s", cur.get("execution_id"), exc)
                    sim = 1.0 if same_hash else 0.0
                if sim is None:
                    sim = 1.0 if same_hash else 0.0
                if same_hash or sim >= threshold:
                    reason = (
                        "matching state_hash" if same_hash else f"cosine {sim:.4f} >= {threshold}"
                    )
                    loops.append(
                        {
                            "session_id": sid,
                            "execution_id": cur["execution_id"],
                            "prior_execution_id": prev["execution_id"],
                            "kind": "ping_pong_loop",
                            "similarity": round(float(sim), 4),
                            "threshold": threshold,
                            "evidence": {
                                "reason": reason,
                                "state_hash": ch if same_hash else None,
                                "prev_sequence": prev.get("sequence"),
                                "sequence": cur.get("sequence"),
                            },
                        }
                    )
        for loop in loops:
            exes, _ = await self.list_executions(loop["session_id"], limit=10000, offset=0)
            agent_id = next(
                (e["agent_id"] for e in exes if e["execution_id"] == loop["execution_id"]),
                "unknown",
            )
            await self.record_loop(
                agent_id=agent_id,
                **{
                    k: loop[k]
                    for k in (
                        "session_id",
                        "execution_id",
                        "prior_execution_id",
                        "similarity",
                        "threshold",
                        "evidence",
                    )
                },
            )
        return {"ok": True, "detections": len(loops), "threshold": threshold, "loops": loops}

    # -- seed ---------------------------------------------------------------------
    async def ensure_seed(
        self, session_id: str = "seed-loop-session", state_hash: str = "seed-loop-state-v1"
    ) -> None:
        from app.embeddings import get_embedding_service

        svc = get_embedding_service()
        await self.ensure_session(session_id, "sentinel-seed-agent")
        exes, _ = await self.list_executions(session_id, limit=10, offset=0)
        for i in range(len(exes), 2):
            seq = (max(e["sequence"] for e in exes) + 1) if exes else i + 1
            out = {"step": f"repeat action {i}", "state": "waiting-for-tool"}
            vec = await asyncio.to_thread(
                svc.embed_payload, {"goal": "seeded ping-pong loop check"}, out
            )
            eid = f"seed_exec_{i + 1}"
            now = time.time()

            def _insert():
                if self._fetchone("SELECT 1 FROM executions WHERE execution_id=?", (eid,)):
                    return
                self._execute(
                    "INSERT INTO executions(execution_id, session_id, parent_execution_id,"
                    " agent_id, node_id, sequence, status, input_payload, output_payload,"
                    " thinking_trace, state_hash, created_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        eid,
                        session_id,
                        f"seed_exec_{i}" if i > 0 else None,
                        "sentinel-seed-agent",
                        "seed-node",
                        seq,
                        "ok",
                        _jdumps({"goal": "seeded ping-pong loop check"}),
                        _jdumps(out),
                        _jdumps(None),
                        state_hash,
                        now,
                    ),
                )

            await asyncio.to_thread(_insert)
            await asyncio.to_thread(self._store_vector_sync, eid, session_id, vec)

    def close(self) -> None:
        with self._lock:
            try:
                self._sql.close()
            except Exception:
                pass


_instance: HybridStore | None = None
_instance_dir: str | None = None


def get_hybrid_store() -> HybridStore:
    """Lazy singleton (path re-read when AGENTDRIFT_DATA_DIR changes, e.g. tests)."""
    global _instance, _instance_dir
    directory = data_dir()
    if _instance is None or _instance_dir != str(directory):
        if _instance is not None:
            try:
                _instance.close()
            except Exception:
                pass
        _instance = HybridStore(directory)
        _instance_dir = str(directory)
    return _instance


def reset_hybrid_store() -> None:
    global _instance, _instance_dir
    if _instance is not None:
        try:
            _instance.close()
        except Exception:
            pass
    _instance, _instance_dir = None, None
