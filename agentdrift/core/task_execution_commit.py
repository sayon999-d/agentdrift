"""Typed, auditable work history records shared by coding agents."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FileChangeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    change_type: Literal["added", "modified", "deleted", "audited"]
    diff_summary: str | None = None


class TaskExecutionCommit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commit_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex[:7],
        description="Short SHA-like identifier for this task execution record.",
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    agent_id: str = Field(min_length=1, description="Agent that performed or audited the work.")
    task_intent: str = Field(min_length=1, description="Objective of the task.")
    execution_summary: str = Field(
        min_length=1,
        description="Concise technical bullet list of exact decisions and changes.",
    )
    files_touched: list[FileChangeRecord] = Field(default_factory=list)
    exported_contracts: dict[str, Any] | None = None
    status: Literal["completed", "reverted", "audited"] = "completed"
