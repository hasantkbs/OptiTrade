"""
OptiTrade Research Lab — shared domain models.

Every subpackage (experiments, hypothesis, backtesting, benchmarking,
feature_analysis, model_analysis, datasets, shadow, promotion, reports)
imports its models from here rather than defining its own parallel
copies. Several models deliberately reuse types already defined
elsewhere instead of duplicating them:

  - `learning.models.RollingWindow` - the same 7d/30d/90d/lifetime
    windows Continuous Learning already uses.
  - `learning.models.AccuracyMetrics` - embedded directly in
    `ModelAnalysisResult` rather than re-deriving accuracy/precision/
    recall/calibration a second time.

This package is a fully isolated, offline research environment - see
`tests/test_research_isolation.py` for the enforced boundary. Nothing
here ever executes against live/production data paths.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from learning.models import AccuracyMetrics, RollingWindow

# ── Experiments ──────────────────────────────────────────────────────────


class ExperimentStatus(str, Enum):
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class Experiment(BaseModel):
    """One quant research experiment. Never deleted - only ever moves
    forward through `ExperimentStatus` (see `experiments/lifecycle.py`),
    so a rejected/failed experiment remains permanently queryable."""

    id: Optional[int] = None
    name: str
    description: str = ""
    hypothesis_id: Optional[int] = None
    author: str
    status: ExperimentStatus = ExperimentStatus.DRAFT
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("name", "author")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value


# ── Hypothesis registry ─────────────────────────────────────────────────


class HypothesisOutcome(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


class Hypothesis(BaseModel):
    """Every experiment must begin with one of these. Never deleted -
    rejected and inconclusive hypotheses are kept exactly like accepted
    ones, so no failed experiment's reasoning is ever lost."""

    id: Optional[int] = None
    statement: str
    outcome: Optional[HypothesisOutcome] = None
    evidence: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None

    @field_validator("statement")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value


# ── Backtesting ──────────────────────────────────────────────────────────


class BacktestMethod(str, Enum):
    WALK_FORWARD = "walk_forward"
    ROLLING_WINDOW = "rolling_window"
    PURGED_CV = "purged_cv"
    STRESS_TEST = "stress_test"
    OUT_OF_SAMPLE = "out_of_sample"


class FoldResult(BaseModel):
    """One fold's (or one stress scenario's) performance, computed over
    its held-out test period only."""

    fold_index: int = Field(..., ge=0)
    test_start: datetime
    test_end: datetime
    sample_count: int = Field(..., ge=0)
    total_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float = Field(..., ge=0.0)
    win_rate: float = Field(..., ge=0.0, le=1.0)
    expected_value: float


class BacktestResult(BaseModel):
    """The full result of running one backtest method against one
    engine/version's (optionally symbol-scoped) historical return
    series."""

    id: Optional[int] = None
    experiment_id: Optional[int] = None
    method: BacktestMethod
    engine_name: str
    engine_version: str
    symbol: Optional[str] = None
    window_start: datetime
    window_end: datetime
    folds: List[FoldResult] = Field(default_factory=list)
    aggregate_sharpe: float = 0.0
    aggregate_sortino: float = 0.0
    aggregate_max_drawdown: float = 0.0
    aggregate_win_rate: float = 0.0
    aggregate_expected_value: float = 0.0
    sample_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Benchmarking ─────────────────────────────────────────────────────────


class BenchmarkSubjectType(str, Enum):
    ENGINE_VERSION = "engine_version"
    FEATURE_SET = "feature_set"
    WEIGHTING_POLICY = "weighting_policy"
    MODEL = "model"


class BenchmarkResult(BaseModel):
    """A statistical comparison between two named subjects of the same
    type (e.g. two engine versions), using a two-sample t-test over
    their historical return/outcome series."""

    id: Optional[int] = None
    experiment_id: Optional[int] = None
    subject_type: BenchmarkSubjectType
    subject_a: str
    subject_b: str
    window: RollingWindow
    metrics_a: Dict[str, float] = Field(default_factory=dict)
    metrics_b: Dict[str, float] = Field(default_factory=dict)
    p_value: float = Field(..., ge=0.0, le=1.0)
    significant: bool
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Feature analysis ─────────────────────────────────────────────────────


class FeatureImportanceRecord(BaseModel):
    symbol: str
    engine_name: str
    feature_name: str
    importance: float = Field(..., ge=0.0, le=1.0)
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FeatureCorrelationRecord(BaseModel):
    symbol: str
    feature_a: str
    feature_b: str
    correlation: float = Field(..., ge=-1.0, le=1.0)
    sample_count: int = Field(..., ge=0)
    window_start: datetime
    window_end: datetime
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FeatureStabilityRecord(BaseModel):
    """Higher `stability_score` (derived from the coefficient of
    variation of the feature's historical values) means the feature's
    value has stayed relatively consistent over the window."""

    symbol: str
    feature_name: str
    stability_score: float = Field(..., ge=0.0, le=1.0)
    coefficient_of_variation: float = Field(..., ge=0.0)
    sample_count: int = Field(..., ge=0)
    window_start: datetime
    window_end: datetime
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FeatureDriftRecord(BaseModel):
    """A two-sample Kolmogorov-Smirnov test comparing a feature's value
    distribution in a recent window against a baseline window."""

    symbol: str
    feature_name: str
    drift_statistic: float = Field(..., ge=0.0)
    p_value: float = Field(..., ge=0.0, le=1.0)
    drifted: bool
    baseline_window_start: datetime
    baseline_window_end: datetime
    recent_window_start: datetime
    recent_window_end: datetime
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Model analysis ───────────────────────────────────────────────────────


class ModelAnalysisResult(BaseModel):
    """Combines Continuous Learning's already-computed
    accuracy/precision/recall/calibration (`AccuracyMetrics`, reused
    verbatim - never re-derived) with trading-specific risk metrics
    Learning does not compute: Sharpe, Sortino, max drawdown, and
    expected value."""

    engine_name: str
    engine_version: str
    window: RollingWindow
    accuracy_metrics: AccuracyMetrics
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float = Field(..., ge=0.0)
    expected_value: float
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Shadow evaluation / promotion ────────────────────────────────────────


class PromotionRecommendation(str, Enum):
    PROMOTE = "promote"
    KEEP_SHADOW = "keep_shadow"
    REJECT = "reject"


class PromotionDecision(BaseModel):
    """A recommendation only - the Research Lab never promotes an
    engine version automatically. A human (or a later, explicitly
    separate automation step) acts on this."""

    id: Optional[int] = None
    experiment_id: Optional[int] = None
    engine_name: str
    candidate_version: str
    live_version: str
    recommendation: PromotionRecommendation
    rationale: str
    window: RollingWindow
    candidate_accuracy: float = Field(..., ge=0.0, le=1.0)
    live_accuracy: float = Field(..., ge=0.0, le=1.0)
    candidate_sample_count: int = Field(..., ge=0)
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Datasets ─────────────────────────────────────────────────────────────


class DatasetDefinition(BaseModel):
    """Metadata describing a reproducible historical dataset. Only the
    definition is persisted - the actual feature values are always
    rebuilt on demand from the Feature Store (the durable source of
    truth), never duplicated into a second store."""

    id: Optional[int] = None
    name: str
    symbols: List[str]
    feature_names: List[str]
    start: datetime
    end: datetime
    version: str = "v1"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value


# ── Reports ──────────────────────────────────────────────────────────────


class ReportType(str, Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    BENCHMARK = "benchmark"
    EXPERIMENT_SUMMARY = "experiment_summary"


class Report(BaseModel):
    id: Optional[int] = None
    report_type: ReportType
    title: str
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    content: Dict = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
