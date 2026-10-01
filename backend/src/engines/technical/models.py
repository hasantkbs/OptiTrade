"""
OptiTrade Technical Engine — domain models.

`AnalyzerResult` is the structured shape every analyzer module (trend,
momentum, oscillator, volatility, volume, market_structure) returns.
`TechnicalAnalysisResult` is the engine's own rich native output
(superset of what `decision_engine.interfaces.VotingEngineProtocol`
requires — `engine.py::TechnicalEngine.vote()` adapts it down to a plain
`decision_engine.models.EngineVote` for Decision Engine consumption).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from pydantic import BaseModel, Field, field_validator

from decision_engine.models import Prediction


class AnalyzerResult(BaseModel):
    """One analyzer module's structured opinion, derived purely from
    already-resolved Feature Store values — never from raw price data."""

    analyzer_name: str
    signal: float = Field(..., ge=-1.0, le=1.0, description="-1 (bearish) .. +1 (bullish)")
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: List[str] = Field(default_factory=list)
    features_used: List[str] = Field(default_factory=list)

    @field_validator("analyzer_name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value


class TechnicalExecutionMetadata(BaseModel):
    """The engine's own internal telemetry for one `analyze()` call —
    distinct from `engine_registry.models.ExecutionMetadata`, which
    describes the registry's view of running this engine as a whole."""

    total_duration_ms: float
    analyzer_durations_ms: Dict[str, float] = Field(default_factory=dict)
    features_from_cache: List[str] = Field(default_factory=list)
    features_computed_fresh: List[str] = Field(default_factory=list)


class TechnicalAnalysisResult(BaseModel):
    """The Technical Engine's full, native output for one symbol."""

    symbol: str
    prediction: Prediction
    confidence: float = Field(..., ge=0.0, le=1.0)
    expected_return: float
    expected_volatility: float
    evidence: List[str] = Field(default_factory=list)
    feature_importance: Dict[str, float] = Field(default_factory=dict)
    execution_metadata: TechnicalExecutionMetadata
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
