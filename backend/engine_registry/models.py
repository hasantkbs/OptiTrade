"""OptiTrade Engine Registry — domain models."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from decision_engine.models import EngineVote


class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    DISABLED = "disabled"


class ExecutionMetadata(BaseModel):
    """Result of executing one registered engine, returned alongside (or
    instead of) its vote — always produced, even on failure, so a caller
    executing all engines can see exactly what happened to each one."""

    engine_name: str
    engine_version: str
    status: ExecutionStatus
    duration_ms: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error_type: Optional[str] = None
    vote: Optional[EngineVote] = None
