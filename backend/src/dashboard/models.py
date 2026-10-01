"""
OptiTrade Analytics & Dashboard Platform — domain models.

Wherever an existing package already owns a clean, complete shape for a
metric (`learning.models.AccuracyMetrics`/`WeightUpdate`/`DriftSignal`/
`PromotionCandidate`, `portfolio.models.PortfolioDashboard`,
`core.regime_scanner.MarketRegime`), this module reuses it directly
rather than redefining it - only genuinely new, dashboard-specific
shapes are declared here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from decision_engine.models import Prediction
from learning.models import AccuracyMetrics, DriftSignal, PromotionCandidate, RollingWindow
from portfolio.models import PortfolioDashboard


class _DashboardModel(BaseModel):
    """Several dashboard shapes have a `model_id` field (an ML model
    identifier) - `protected_namespaces=()` silences pydantic's default
    `model_*` collision warning for all of them."""

    model_config = ConfigDict(protected_namespaces=())

# ── Analytics primitives (shared building blocks) ────────────────────────

class TimeSeriesPoint(_DashboardModel):
    timestamp: datetime
    value: float


class TimeSeries(_DashboardModel):
    name: str
    points: List[TimeSeriesPoint] = Field(default_factory=list)


class Distribution(_DashboardModel):
    """Summary statistics of a set of observed values, plus the raw
    values themselves (small samples only - callers should not pass
    unbounded series through this)."""

    count: int = Field(..., ge=0)
    mean: float = 0.0
    median: float = 0.0
    stdev: float = 0.0
    minimum: float = 0.0
    maximum: float = 0.0
    values: List[float] = Field(default_factory=list)


class Histogram(_DashboardModel):
    bin_edges: List[float] = Field(default_factory=list)
    counts: List[int] = Field(default_factory=list)


class RollingMetric(_DashboardModel):
    window_size: int = Field(..., gt=0)
    points: List[TimeSeriesPoint] = Field(default_factory=list)


class CumulativeMetric(_DashboardModel):
    points: List[TimeSeriesPoint] = Field(default_factory=list)


# ── Overview ─────────────────────────────────────────────────────────────

class LearningStatus(_DashboardModel):
    engines_tracked: int = Field(..., ge=0)
    total_samples: int = Field(..., ge=0)
    pending_samples: int = Field(..., ge=0)
    last_evaluated_at: Optional[datetime] = None


class OverviewMetrics(_DashboardModel):
    total_users: int = Field(..., ge=0)
    active_users: int = Field(..., ge=0)
    total_portfolios: int = Field(..., ge=0)
    total_watchlists: int = Field(..., ge=0)
    total_alerts: int = Field(..., ge=0)
    total_paper_accounts: int = Field(..., ge=0)
    total_models: int = Field(..., ge=0)
    active_engines: int = Field(..., ge=0)
    learning_status: LearningStatus
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Decision Engine dashboard ────────────────────────────────────────────

class EngineAccuracySnapshot(_DashboardModel):
    engine_name: str
    engine_version: str
    accuracy_by_window: Dict[RollingWindow, AccuracyMetrics] = Field(default_factory=dict)
    current_weight: Optional[float] = None
    latest_drift: Optional[DriftSignal] = None


class CalibrationSnapshot(_DashboardModel):
    """A model-level (not engine-level) calibration result, read
    directly from `ml_training_calibration_results` (see repository.py)."""

    model_id: str
    method: str
    calibration_error_before: float
    calibration_error_after: float
    computed_at: datetime


class EngineDashboardView(_DashboardModel):
    engines: List[EngineAccuracySnapshot] = Field(default_factory=list)
    calibration: List[CalibrationSnapshot] = Field(default_factory=list)
    drift_signals: List[DriftSignal] = Field(default_factory=list)
    confidence_history: List[TimeSeriesPoint] = Field(default_factory=list)
    regime_distribution: Dict[str, int] = Field(default_factory=dict)
    expected_return_history: List[TimeSeriesPoint] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── ML dashboard ─────────────────────────────────────────────────────────

class ActiveModelInfo(_DashboardModel):
    model_id: str
    label_name: str
    horizon_days: int
    algorithm: str
    version: str
    promoted_at: Optional[datetime] = None
    is_rollback_override: bool = False


class ShadowModelInfo(_DashboardModel):
    model_id: str
    algorithm: str
    version: str
    label_name: str
    horizon_days: int
    training_date: Optional[datetime] = None


class RegistryEntrySnapshot(_DashboardModel):
    model_id: str
    algorithm: str
    version: str
    promotion_state: str
    label_name: str
    horizon_days: int
    engine_name: Optional[str] = None
    metrics: Dict[str, float] = Field(default_factory=dict)
    training_date: Optional[datetime] = None
    promoted_at: Optional[datetime] = None


class TrainingRunSnapshot(_DashboardModel):
    model_id: str
    algorithm: str
    task_type: str
    status: str
    metrics: Dict[str, float] = Field(default_factory=dict)
    training_date: Optional[datetime] = None


class PromotionHistoryEntry(_DashboardModel):
    engine_name: str
    candidate_version: str
    live_version: str
    recommendation: str
    rationale: str
    candidate_accuracy: Optional[float] = None
    live_accuracy: Optional[float] = None
    decided_at: datetime
    applied: bool = False
    applied_at: Optional[datetime] = None


class BenchmarkSnapshot(_DashboardModel):
    subject_type: str
    subject_a: str
    subject_b: str
    window_name: str
    p_value: Optional[float] = None
    significant: Optional[bool] = None
    created_at: datetime


class FeatureImportanceSnapshot(_DashboardModel):
    model_id: str
    method: str
    feature_name: str
    importance: float
    computed_at: datetime


class MLDashboardView(_DashboardModel):
    active_models: List[ActiveModelInfo] = Field(default_factory=list)
    shadow_models: List[ShadowModelInfo] = Field(default_factory=list)
    registry_entries: List[RegistryEntrySnapshot] = Field(default_factory=list)
    training_runs: List[TrainingRunSnapshot] = Field(default_factory=list)
    promotion_history: List[PromotionHistoryEntry] = Field(default_factory=list)
    benchmark_history: List[BenchmarkSnapshot] = Field(default_factory=list)
    feature_importance_history: List[FeatureImportanceSnapshot] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Portfolio dashboard ──────────────────────────────────────────────────

class PortfolioDashboardExtended(_DashboardModel):
    """`portfolio.models.PortfolioDashboard` reused directly - it already
    covers allocation (incl. sector/currency breakdown), pnl, drawdown,
    and risk (`RiskAnalytics`) in full; the only thing genuinely missing
    for this requirement is a realized Sharpe ratio, computed here from
    the account's own equity history."""

    dashboard: PortfolioDashboard
    sharpe_ratio: Optional[float] = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Watchlist dashboard ──────────────────────────────────────────────────

class WatchlistDashboardView(_DashboardModel):
    total_watchlists: int = Field(..., ge=0)
    total_items: int = Field(..., ge=0)
    total_favorites: int = Field(..., ge=0)
    most_tracked_symbols: List[str] = Field(default_factory=list)
    items_by_folder: Dict[str, int] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Paper trading dashboard ──────────────────────────────────────────────

class JournalStatistics(_DashboardModel):
    total_entries: int = Field(..., ge=0)
    entries_by_decision: Dict[str, int] = Field(default_factory=dict)
    entries_by_regime: Dict[str, int] = Field(default_factory=dict)
    average_confidence: Optional[float] = None
    most_common_tags: List[str] = Field(default_factory=list)


class PaperTradingDashboardView(_DashboardModel):
    account_id: int
    win_rate: float
    expectancy: float
    equity_curve: List[TimeSeriesPoint] = Field(default_factory=list)
    monthly_performance: List[Dict[str, Any]] = Field(default_factory=list)
    journal_statistics: JournalStatistics
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Learning dashboard ───────────────────────────────────────────────────

class EngineRanking(_DashboardModel):
    engine_name: str
    engine_version: str
    accuracy: float
    current_weight: Optional[float] = None
    rank: int


class LearningSampleSnapshot(_DashboardModel):
    symbol: str
    source: str
    decision: Prediction
    confidence: float
    decided_at: datetime
    evaluated: bool
    correct: Optional[bool] = None


class CalibrationHistoryPoint(_DashboardModel):
    engine_name: str
    engine_version: str
    window: RollingWindow
    calibration_error: float
    confidence_reliability: float
    computed_at: datetime


class LearningDashboardView(_DashboardModel):
    engine_rankings: List[EngineRanking] = Field(default_factory=list)
    recent_samples: List[LearningSampleSnapshot] = Field(default_factory=list)
    promotion_candidates: List[PromotionCandidate] = Field(default_factory=list)
    drift_alerts: List[DriftSignal] = Field(default_factory=list)
    calibration_history: List[CalibrationHistoryPoint] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Alert dashboard ──────────────────────────────────────────────────────

class TriggerEventSnapshot(_DashboardModel):
    alert_id: int
    symbol: Optional[str] = None
    message: str
    triggered_at: datetime


class AlertDashboardView(_DashboardModel):
    active_alerts: int = Field(..., ge=0)
    fired_last_24h: int = Field(..., ge=0)
    recently_fired: List[TriggerEventSnapshot] = Field(default_factory=list)
    trigger_frequency_by_type: Dict[str, int] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Market dashboard ─────────────────────────────────────────────────────

class SectorSnapshot(_DashboardModel):
    sector: str
    opportunity_score: float
    avg_change_pct: float
    trend: str


class NewsImpactSnapshot(_DashboardModel):
    symbol: str
    sentiment_score: float
    sentiment_label: str
    headline_count: int


class MarketDashboardView(_DashboardModel):
    regime_distribution: Dict[str, int] = Field(default_factory=dict)
    volatility_map: Dict[str, float] = Field(default_factory=dict)
    sector_heatmap: List[SectorSnapshot] = Field(default_factory=list)
    news_impact_summary: List[NewsImpactSnapshot] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Reports ──────────────────────────────────────────────────────────────

class ReportPeriod(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class ReportFormat(str, Enum):
    JSON = "json"
    CSV = "csv"


class DashboardReport(_DashboardModel):
    period: ReportPeriod
    period_start: datetime
    period_end: datetime
    summary: Dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
