"""
OptiTrade Continuous Learning — domain models.

The learning system never predicts and never votes - it only observes
completed `decision_engine.models.DecisionOutput`s (and, for shadow
engines, individual `decision_engine.models.EngineVote`s collected
outside of live voting), later compares them against actual market
outcomes, and derives accuracy/weighting/drift signals from that
history. `EngineVote` itself (already defined in `decision_engine.
models`) is reused verbatim as the "engine outputs" this system tracks
- no parallel vote-shape model is introduced.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from decision_engine.models import EngineVote, Prediction


class SampleSource(str, Enum):
    """Where a learning sample came from. Shadow samples are collected
    by directly invoking an engine's `vote()` outside of any live
    `DecisionEngine.decide()` call - they inform accuracy/promotion
    statistics but never influence a live decision."""

    LIVE = "live"
    SHADOW = "shadow"


class RollingWindow(str, Enum):
    SEVEN_DAY = "7d"
    THIRTY_DAY = "30d"
    NINETY_DAY = "90d"
    LIFETIME = "lifetime"


class WeightingPolicy(str, Enum):
    EXPONENTIAL_DECAY = "exponential_decay"
    ROLLING_AVERAGE = "rolling_average"
    BAYESIAN = "bayesian"


class DriftType(str, Enum):
    DEGRADING = "degrading"
    IMPROVING = "improving"
    UNSTABLE = "unstable"
    STABLE = "stable"


class LearningSample(BaseModel):
    """One trackable unit of learning: a decision (live, aggregated
    across engines) or a single shadow engine's vote, plus every
    contributing engine's raw vote, awaiting comparison against the
    actual market outcome once `evaluation_horizon_days` has elapsed."""

    id: Optional[int] = None
    symbol: str
    source: SampleSource
    decision: Prediction
    confidence: float = Field(..., ge=0.0, le=1.0)
    expected_return: float
    expected_volatility: float
    engine_results: List[EngineVote] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    decided_at: datetime
    evaluation_horizon_days: int = Field(..., gt=0)
    evaluated: bool = False
    evaluated_at: Optional[datetime] = None
    actual_return: Optional[float] = None
    actual_volatility: Optional[float] = None
    correct: Optional[bool] = None

    @field_validator("symbol")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value


class EngineOutcomeRecord(BaseModel):
    """A flattened, engine-scoped projection of one `LearningSample`'s
    contribution from a single engine - the unit `accuracy.py`,
    `weighting.py`, and `drift.py` all operate on. Denormalized at write
    time (one row per engine per sample) so per-engine accuracy queries
    never need to scan/parse every sample's full `engine_results` JSON
    blob."""

    id: Optional[int] = None
    sample_id: int
    engine_name: str
    engine_version: str
    symbol: str
    source: SampleSource
    prediction: Prediction
    confidence: float = Field(..., ge=0.0, le=1.0)
    expected_return: float
    expected_volatility: float
    decided_at: datetime
    evaluation_horizon_days: int = Field(..., gt=0)
    evaluated: bool = False
    evaluated_at: Optional[datetime] = None
    actual_return: Optional[float] = None
    actual_volatility: Optional[float] = None
    correct: Optional[bool] = None


class AccuracyMetrics(BaseModel):
    """One engine's performance summary over one rolling window,
    computed purely from evaluated `EngineOutcomeRecord`s."""

    engine_name: str
    engine_version: str
    window: RollingWindow
    sample_count: int = Field(..., ge=0)
    accuracy: float = Field(..., ge=0.0, le=1.0)
    precision: float = Field(..., ge=0.0, le=1.0)
    recall: float = Field(..., ge=0.0, le=1.0)
    calibration_error: float = Field(..., ge=0.0, le=1.0)
    confidence_reliability: float = Field(..., ge=0.0, le=1.0)
    expected_return_error: float = Field(..., ge=0.0)
    volatility_error: float = Field(..., ge=0.0)
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WeightUpdate(BaseModel):
    """An audit-trail row for one recomputed engine weight - written to
    the Feature Store (the value `decision_engine.weighting.
    AccuracyWeightProvider` reads) and persisted here for history/
    rollback/inspection."""

    engine_name: str
    engine_version: str
    old_weight: float
    new_weight: float
    policy: WeightingPolicy
    reason: str
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DriftSignal(BaseModel):
    """One drift-detection verdict for one engine, comparing a recent
    window's accuracy against a longer baseline window."""

    engine_name: str
    engine_version: str
    drift_type: DriftType
    magnitude: float = Field(..., ge=0.0)
    recent_window: RollingWindow
    baseline_window: RollingWindow
    evidence: str
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PromotionCandidate(BaseModel):
    """A non-live (shadow, or older/newer) version of an engine whose
    accuracy over `window` meets or exceeds the currently-live version
    by at least the configured margin - a recommendation for a human (or
    a future automated step) to review, never an automatic promotion."""

    engine_name: str
    candidate_version: str
    live_version: str
    window: RollingWindow
    candidate_accuracy: float = Field(..., ge=0.0, le=1.0)
    live_accuracy: float = Field(..., ge=0.0, le=1.0)
    candidate_sample_count: int = Field(..., ge=0)
