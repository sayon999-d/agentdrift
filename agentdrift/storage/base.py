"""Abstract store interface shared by local and cloud backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class DriftReport(BaseModel):
    """Result of a drift check over a session (or all sessions)."""

    ok: bool = True
    session_id: str | None = None
    detections: int = 0
    threshold: float = 0.92
    loops: list[dict[str, Any]] = Field(default_factory=list)


class BaseStore(ABC):
    """Backend-agnostic persistence + drift interface."""

    @abstractmethod
    async def record_execution(
        self,
        session_id: str,
        agent_id: str,
        node_id: str,
        payload: dict[str, Any],
        thinking: str | dict[str, Any] | None,
        embedding: list[float] | None,
    ) -> dict[str, Any]:
        """Persist one agent step; return the stored execution record."""
        raise NotImplementedError

    @abstractmethod
    async def check_drift(self, session_id: str | None, threshold: float = 0.92) -> DriftReport:
        """Flag ping-pong loops among consecutive steps; persist alerts."""
        raise NotImplementedError

    @abstractmethod
    async def list_recent_executions(
        self, session_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Newest-first execution records, optionally filtered by session."""
        raise NotImplementedError
