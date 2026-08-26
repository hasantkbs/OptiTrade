"""
OptiTrade ML Training Platform — shared domain models.

Every subpackage (datasets, labels, features, training, optimization,
evaluation, calibration, importance, registry, shadow) imports its
models from here. Reuses types already defined elsewhere instead of
duplicating them:

  - `decision_engine.models.Prediction` (BUY/HOLD/SELL) - the
    `direction` label and a trained classifier's directional output
    both reuse this exact enum rather than inventing a parallel one.
  - `learning.models.AccuracyMetrics` - embedded in `ModelMetrics`
    rather than re-deriving accuracy/precision/recall/calibration.

This platform never executes during a live production request - see
`tests/test_research_isolation.py`, which guards every production
package from ever importing it, the same way it guards `research_lab`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from decision_engine.models import Prediction
from learning.models import AccuracyMetrics


class _ModelIdBase(BaseModel):
    """Base for every model that has a `model_id` field - pydantic v2
    reserves the `model_` prefix for its own methods (`model_dump`,
    `model_validate`, ...) and warns on any field name that collides
    with it; `model_id` is the correct, meaningful name here, so the
    protected-namespace check is disabled instead of renaming it."""

    model_config = ConfigDict(protected_namespaces=())

# ── Datasets ─────────────────────────────────────────────────────────────


class DatasetType(str, Enum):
    TRADER = "trader"
    INVESTOR = "investor"


class DatasetVersion(BaseModel):
    """Metadata for one built dataset. Mirrors
    `research_lab.models.DatasetDefinition`'s "definition only, never a
    data copy" philosophy - `row_count`/`feature_names`/`label_names`
    describe what was built, but the actual feature values always come
    from the Feature Store, never a second store."""

    id: Optional[int] = None
    name: str
    dataset_type: DatasetType
    symbols: List[str]
    horizons_days: List[int]
    feature_names: List[str]
    label_names: List[str]
    start: datetime
    end: datetime
    row_count: int = Field(..., ge=0)
    version: str = "v1"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value


# ── Features ─────────────────────────────────────────────────────────────


class FeatureCategory(str, Enum):
    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"
    NEWS = "news"
    RISK = "risk"
    REGIME = "regime"
    RELATIVE_STRENGTH = "relative_strength"
    OTHER = "other"


class FeatureVector(BaseModel):
    """One symbol's full, point-in-time feature snapshot - every
    feature the Feature Store has for that symbol as of `as_of`,
    auto-discovered (see `features/extractor.py`), grouped by category
    for reporting."""

    symbol: str
    as_of: datetime
    values: Dict[str, float] = Field(default_factory=dict)
    categories: Dict[FeatureCategory, List[str]] = Field(default_factory=dict)


# ── Labels ───────────────────────────────────────────────────────────────


class LabelName(str, Enum):
    DIRECTION = "direction"
    EXPECTED_RETURN = "expected_return"
    EXPECTED_VOLATILITY = "expected_volatility"
    TREND_CONTINUATION = "trend_continuation"
    TREND_REVERSAL = "trend_reversal"
    BREAKOUT = "breakout"
    REJECTION = "rejection"


class LabelSet(BaseModel):
    """Ground-truth labels for one (symbol, as_of, horizon) triple,
    derived purely from realized forward price action - never from a
    live prediction."""

    symbol: str
    as_of: datetime
    horizon_days: int = Field(..., gt=0)
    direction: Prediction
    expected_return: float
    expected_volatility: float = Field(..., ge=0.0)
    trend_continuation: bool
    trend_reversal: bool
    breakout: bool
    rejection: bool


class TrainingSample(BaseModel):
    """One row of a built dataset: a feature snapshot paired with its
    forward-looking labels."""

    symbol: str
    as_of: datetime
    horizon_days: int = Field(..., gt=0)
    features: Dict[str, float] = Field(default_factory=dict)
    labels: LabelSet


# ── Training / algorithms ───────────────────────────────────────────────


class ModelAlgorithm(str, Enum):
    LIGHTGBM = "lightgbm"
    XGBOOST = "xgboost"
    CATBOOST = "catboost"
    RANDOM_FOREST = "random_forest"


class TaskType(str, Enum):
    CLASSIFICATION = "classification"
    REGRESSION = "regression"


_CLASSIFICATION_LABELS = {
    LabelName.DIRECTION, LabelName.TREND_CONTINUATION, LabelName.TREND_REVERSAL,
    LabelName.BREAKOUT, LabelName.REJECTION,
}


def task_type_for_label(label_name: LabelName) -> TaskType:
    return TaskType.CLASSIFICATION if label_name in _CLASSIFICATION_LABELS else TaskType.REGRESSION


# ── Evaluation ───────────────────────────────────────────────────────────


class ModelMetrics(BaseModel):
    """`accuracy`/`precision`/`recall`/`f1`/`calibration_error` are
    computed directly from a raw train/test split (via scikit-learn's
    `precision_score`/`recall_score`, the exact functions
    `learning/accuracy.py` already uses, and
    `learning.calibration.expected_calibration_error`'s ECE algorithm
    reused via lightweight duck-typed points - see
    `evaluation/metrics.py`). `accuracy_metrics` is a SEPARATE,
    optional enrichment: once a model is shadow-deployed and
    Continuous Learning has accumulated real evaluated outcomes for it,
    `learning.accuracy.compute_accuracy_metrics`'s own windowed
    `AccuracyMetrics` can be embedded here verbatim instead of being
    re-derived. ROC AUC/MAE/RMSE are not tracked anywhere else.
    Sharpe/Sortino/max drawdown/expected value are reused directly from
    `research_lab.model_analysis.metrics`; profit factor is new."""

    accuracy: float = Field(default=0.0, ge=0.0, le=1.0)
    precision: float = Field(default=0.0, ge=0.0, le=1.0)
    recall: float = Field(default=0.0, ge=0.0, le=1.0)
    f1: float = Field(default=0.0, ge=0.0, le=1.0)
    calibration_error: float = Field(default=0.0, ge=0.0, le=1.0)
    accuracy_metrics: Optional[AccuracyMetrics] = None
    roc_auc: Optional[float] = None
    mae: Optional[float] = None
    rmse: Optional[float] = None
    expected_value: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = Field(default=0.0, ge=0.0)


# ── Calibration ──────────────────────────────────────────────────────────


class CalibrationMethod(str, Enum):
    ISOTONIC = "isotonic"
    PLATT = "platt"


class CalibrationResult(_ModelIdBase):
    model_id: str
    method: CalibrationMethod
    calibration_error_before: float = Field(..., ge=0.0)
    calibration_error_after: float = Field(..., ge=0.0)
    artifact_path: str
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Feature importance ───────────────────────────────────────────────────


class ImportanceMethod(str, Enum):
    SHAP = "shap"
    PERMUTATION = "permutation"


class FeatureImportanceEntry(_ModelIdBase):
    model_id: str
    feature_name: str
    importance: float
    method: ImportanceMethod
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Hyperparameter optimization ─────────────────────────────────────────


class OptimizationResult(_ModelIdBase):
    model_id: str
    algorithm: ModelAlgorithm
    best_params: Dict[str, float] = Field(default_factory=dict)
    best_score: float
    n_trials: int = Field(..., ge=0)
    study_name: str
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Training run ─────────────────────────────────────────────────────────


class TrainingRunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TrainingRun(_ModelIdBase):
    id: Optional[int] = None
    model_id: str
    algorithm: ModelAlgorithm
    task_type: TaskType
    label_name: LabelName
    horizon_days: int = Field(..., gt=0)
    dataset_id: Optional[int] = None
    hyperparameters: Dict[str, float] = Field(default_factory=dict)
    metrics: Optional[ModelMetrics] = None
    feature_list: List[str] = Field(default_factory=list)
    status: TrainingRunStatus = TrainingRunStatus.RUNNING
    experiment_id: Optional[int] = None
    artifact_path: Optional[str] = None
    training_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Model registry ───────────────────────────────────────────────────────


class PromotionState(str, Enum):
    ACTIVE = "active"
    SHADOW = "shadow"
    CANDIDATE = "candidate"
    ARCHIVED = "archived"


class ModelRegistryEntry(_ModelIdBase):
    """One tracked model version. `engine_name`/`engine_version` are
    the (name, version) pair this model is registered under in
    `engine_registry.registry.default_registry` once wrapped as a
    shadow voting engine (see `shadow/adapter.py`) - reused directly by
    `research_lab.promotion` for promotion recommendations, and by
    `learning` for accuracy/weight tracking, without either package
    needing to know a "model" is behind the vote."""

    id: Optional[int] = None
    model_id: str
    algorithm: ModelAlgorithm
    version: str
    dataset_id: Optional[int] = None
    hyperparameters: Dict[str, float] = Field(default_factory=dict)
    metrics: Optional[ModelMetrics] = None
    feature_list: List[str] = Field(default_factory=list)
    label_name: LabelName
    horizon_days: int = Field(..., gt=0)
    training_date: datetime
    promotion_state: PromotionState = PromotionState.CANDIDATE
    engine_name: str
    engine_version: str
    artifact_path: str
    approved_by: Optional[str] = None
    promoted_at: Optional[datetime] = None

    @field_validator("model_id", "engine_name", "engine_version", "artifact_path")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value
