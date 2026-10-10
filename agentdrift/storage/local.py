"""Local backend: embedded SQLite + LanceDB (offline, zero-cloud).

Thin adapter over :mod:`app.hybrid_store` so the daemon's battle-tested
engine stays the single implementation; this module only translates the
:class:`BaseStore` interface onto it.
"""

from __future__ import annotations

from typing import Any

from agentdrift.storage.base import BaseStore, DriftReport


def _split_payload(payload: dict[str, Any]) -> tuple[dict, dict, str | None]:
    data = dict(payload or {})
    state_hash = data.pop("state_hash", None)
    for in_key, out_key in (("input_payload", "output_payload"), ("input", "output")):
        if isinstance(data.get(in_key), dict) or isinstance(data.get(out_key), dict):
            return (
                data.get(in_key) or {},
                data.get(out_key) or {},
                state_hash if isinstance(state_hash, str) else None,
            )
    return ({}, data, state_hash if isinstance(state_hash, str) else None)


class LocalHybridStore(BaseStore):
    """SQLite (relational) + LanceDB (384-d vectors) at ``~/.agentdrift/``."""

    def __init__(self, data_dir: str | None = None) -> None:
        import os

        if data_dir:
            os.environ.setdefault("AGENTDRIFT_DATA_DIR", data_dir)
        from app.hybrid_store import get_hybrid_store

        self._hybrid = get_hybrid_store()

    @property
    def backend(self) -> str:
        return "local-hybrid"

    async def record_execution(
        self,
        session_id: str,
        agent_id: str,
        node_id: str,
        payload: dict[str, Any],
        thinking: str | dict[str, Any] | None,
        embedding: list[float] | None,
    ) -> dict[str, Any]:
        input_payload, output_payload, state_hash = _split_payload(payload or {})
        await self._hybrid.ensure_session(session_id, agent_id or "unknown")
        execution, _detection = await self._hybrid.ingest_execution(
            {
                "session_id": session_id,
                "agent_id": agent_id or "unknown",
                "node_id": node_id or "default",
                "input_payload": input_payload,
                "output_payload": output_payload,
                "thinking_trace": thinking,
                "state_hash": state_hash,
            }
        )
        if embedding:  # caller-supplied vector wins over the computed one
            import asyncio

            await asyncio.to_thread(
                self._hybrid._store_vector_sync,
                execution["execution_id"],
                session_id,
                [float(x) for x in embedding],
            )
        execution.pop("payload_embedding", None)
        return execution

    async def check_drift(self, session_id: str | None, threshold: float = 0.92) -> DriftReport:
        result = await self._hybrid.sentinel_scan(threshold)
        loops = result.get("loops", [])
        if session_id:
            loops = [lp for lp in loops if lp.get("session_id") == session_id]
        return DriftReport(
            ok=True, session_id=session_id, detections=len(loops), threshold=threshold, loops=loops
        )

    async def list_recent_executions(
        self, session_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        rows, _ = await self._hybrid.list_executions(session_id, limit=max(limit * 4, 100))
        rows.sort(
            key=lambda e: (str(e.get("created_at") or ""), e.get("sequence") or 0), reverse=True
        )
        out = rows[: max(limit, 0)]
        for row in out:
            row.pop("payload_embedding", None)
        return out
