"""
OptiTrade Model Serving Platform — domain models.

Reuses rather than re-derives:

  - `decision_engine.models.EngineVote`/`Prediction` for the actual
    prediction shape - a served model's vote is structurally identical
    to any other voting engine's, which is exactly what lets
    `model_serving` register served models directly into the Pipeline
    (see `service.py`).
  - `ml_training.models.{ModelAlgorithm, LabelName, PromotionState}` for
    every field that already has a canonical enum there.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from decision_engine.models import EngineVote
from ml_training.models import LabelName, ModelAlgorithm, PromotionState


class _ModelIdBase(BaseModel):
    """See `ml_training.models._ModelIdBase` - identical rationale:
    `model_id` collides with pydantic v2's protected `model_` namespace."""

    model_config = ConfigDict(protected_namespaces=())


class MLPredictionRequest(BaseModel):
    """API request shape for a direct ML model prediction (see
    `main.py`'s `/quant/predict` route). `main.py` itself never imports
    `ml_training` - it only ever imports this already-typed model from
    `model_serving`, so FastAPI validates `label_name` against the
    canonical enum without main.py's own source containing a single
    `ml_training` import statement (see `tests/test_research_isolation.py`)."""

    symbol: str
    label_name: LabelName = LabelName.DIRECTION
    horizon_days: int = Field(default=1, gt=0)


class LoadedModelInfo(_ModelIdBase):
    """Metadata about one currently in-process-loaded model - the
    Model Cache's payload (see `cache.py`) and the Model Loader's own
    bookkeeping (see `loader.py`)."""

    model_id: str
    algorithm: ModelAlgorithm
    label_name: LabelName
    horizon_days: int = Field(..., gt=0)
    engine_name: str
    engine_version: str
    promotion_state: PromotionState
    checksum: str
    is_calibrated: bool
    loaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PredictionMetadata(_ModelIdBase):
    """Everything about *which* model produced a prediction and how -
    the "metadata" half of the Prediction Service's contract."""

    model_id: str
    algorithm: ModelAlgorithm
    engine_version: str
    promotion_state: PromotionState
    is_calibrated: bool
    checksum: str
    feature_count: int = Field(..., ge=0)
    version_override_used: bool = False
    loaded_at: datetime


class MLPredictionResult(BaseModel):
    """One Prediction Service call's full result: the actual vote
    (reusing `EngineVote` - the same shape Decision Engine/Pipeline
    already consume), the metadata describing which model produced it,
    and the explanation inputs (feature importance, read back from the
    Feature Store exactly as `ml_training.importance` persisted them)
    a caller can hand to `explanation_engine` or its own UI."""

    symbol: str
    label_name: LabelName
    horizon_days: int = Field(..., gt=0)
    vote: EngineVote
    metadata: PredictionMetadata
    explanation_inputs: Dict[str, float] = Field(default_factory=dict)


class ModelHealthStatus(_ModelIdBase):
    model_id: str
    loaded: bool
    loaded_at: Optional[datetime] = None
    stale: bool = False
    last_error: Optional[str] = None


class CacheHealthStatus(BaseModel):
    healthy: bool
    latency_ms: Optional[float] = None
    error: Optional[str] = None


class InferenceLatencyStats(BaseModel):
    sample_count: int = Field(..., ge=0)
    avg_ms: float = Field(default=0.0, ge=0.0)
    p50_ms: float = Field(default=0.0, ge=0.0)
    p95_ms: float = Field(default=0.0, ge=0.0)


class ServingHealthReport(BaseModel):
    cache: CacheHealthStatus
    models: List[ModelHealthStatus] = Field(default_factory=list)
    inference_latency: InferenceLatencyStats
    loading_failure_count: int = Field(default=0, ge=0)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
