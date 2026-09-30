"""
OptiTrade Decision Engine — Domain Models
============================================
`EngineVote` is the structured output every voting engine (Technical,
Fundamental, News — implemented in later steps) returns. `DecisionOutput`
is the single, aggregated result the Decision Engine produces from a set
of votes.

LLMs are explanation engines only — they never vote and never influence
this aggregation (see docs/architecture/gap-analysis.md section 2).
`Prediction` below is a purely statistical BUY/HOLD/SELL vote from a
voting engine, never an LLM.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List

from pydantic import BaseModel, Field, field_validator


class Prediction(str, Enum):
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"


class EngineVote(BaseModel):
    """A single voting engine's opinion on one symbol."""

    engine_name: str
    engine_version: str
    prediction: Prediction
    confidence: float = Field(..., ge=0.0, le=1.0)
    expected_return: float
    volatility: float
    evidence: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("engine_name", "engine_version")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value


class DecisionOutput(BaseModel):
    """The Decision Engine's single, aggregated output for one symbol."""

    symbol: str
    decision: Prediction
    confidence: float = Field(..., ge=0.0, le=1.0)
    expected_return: float
    expected_volatility: float
    aggregation_strategy_version: str
    data_sufficiency: float = Field(..., ge=0.0, le=1.0)
    evidence: List[str] = Field(default_factory=list)
    engine_results: List[EngineVote] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
