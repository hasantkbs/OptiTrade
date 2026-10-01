"""
OptiTrade Pipeline — domain and API-response models.

`EngineExecutionResult` is the pipeline's own internal record of one
engine's attempt (status, timing, retries) - `EngineBreakdownItem` is
the trimmed, API-facing projection of it actually returned to callers.
`decision_engine.models.EngineVote`/`Prediction` are reused directly
rather than re-defined.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from decision_engine.models import EngineVote, Prediction


class QuantAnalysisRequest(BaseModel):
    symbol: str
    asset_type: str = "stock"  # "stock" | "crypto"


class EngineExecutionStatus(str, Enum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    FAILED = "failed"
    INVALID = "invalid"


class EngineExecutionResult(BaseModel):
    """Internal record of one engine's execution attempt - not itself
    the API response shape (see `EngineBreakdownItem`)."""

    engine_name: str
    engine_version: str
    status: EngineExecutionStatus
    vote: Optional[EngineVote] = None
    error_type: Optional[str] = None
    duration_ms: float = Field(..., ge=0.0)
    attempts: int = Field(..., ge=1)


class EngineBreakdownItem(BaseModel):
    """The API-facing summary of one engine's contribution."""

    engine_name: str
    engine_version: str
    status: EngineExecutionStatus
    prediction: Optional[Prediction] = None
    confidence: Optional[float] = None
    expected_return: Optional[float] = None
    volatility: Optional[float] = None
    evidence: List[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    risk_level: str  # "LOW" | "MEDIUM" | "HIGH"
    expected_volatility: float
    data_sufficiency: float = Field(..., ge=0.0, le=1.0)


class PipelineMetadata(BaseModel):
    pipeline_version: str
    total_duration_ms: float = Field(..., ge=0.0)
    stage_durations_ms: Dict[str, float] = Field(default_factory=dict)
    engines_available: int = Field(..., ge=0)
    engines_succeeded: int = Field(..., ge=0)
    degraded: bool
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PipelineResponse(BaseModel):
    symbol: str
    decision: Prediction
    confidence: float = Field(..., ge=0.0, le=1.0)
    expected_return: float
    expected_volatility: float
    engine_breakdown: List[EngineBreakdownItem] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    risk: RiskAssessment
    explanation: str
    metadata: PipelineMetadata
