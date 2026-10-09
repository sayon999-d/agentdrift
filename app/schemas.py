"""Pydantic v2 request/response schemas (dashboard-facing)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


# --- Sessions ---
class SessionCreate(BaseModel):
    session_id: str | None = None
    agent_id: str
    parent_session_id: str | None = None
    status: str = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionUpdate(BaseModel):
    status: str | None = None
    metadata: dict[str, Any] | None = None
    parent_session_id: str | None = None


class SessionOut(BaseModel):
    session_id: str
    agent_id: str
    parent_session_id: str | None = None
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


# --- Executions ---
class ExecutionIngest(BaseModel):
    execution_id: str | None = None
    session_id: str
    parent_execution_id: str | None = None
    agent_id: str
    node_id: str = "default"
    sequence: int | None = None  # auto-assigned (max+1) when omitted
    status: str = "ok"
    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_payload: dict[str, Any] = Field(default_factory=dict)
    thinking_trace: dict[str, Any] | list[Any] | None = None
    state_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    freeze: bool = False


class ExecutionOut(BaseModel):
    execution_id: str
    session_id: str
    parent_execution_id: str | None = None
    agent_id: str
    node_id: str
    sequence: int
    status: str
    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_payload: dict[str, Any] = Field(default_factory=dict)
    thinking_trace: Any | None = None
    state_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    frozen_at: datetime | None = None
    created_at: datetime | None = None


# --- Drift ---
DriftKind = Literal[
    "semantic_drift", "state_drift", "logical_drift", "schema_drift", "no_drift",
]


class DriftDetectionOut(BaseModel):
    detection_id: UUID
    session_id: str
    execution_id: str
    prior_execution_id: str | None = None
    kind: str
    agent_id: str
    similarity: float
    threshold: float
    evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class DetectRequest(BaseModel):
    session_id: str
    execution_id: str | None = None  # default: latest
    threshold: float | None = None
    kinds: list[str] | None = None


class HealthOut(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    db_connected: bool = False
    db_mode: str = "memory"
    embeddings: str = "hash-fallback"
    uptime_seconds: float = 0.0
