"""
OptiTrade Watchlist & Alert Platform — domain models.

`Alert` is deliberately one flexible model across every category/type
rather than a dozen narrow subclasses - `parameters`/`last_state` are
free-form `Dict[str, float]`, mirroring the exact pattern
`ml_training.models.TrainingRun.hyperparameters`/`OptimizationResult.
best_params` already established for "the parameter set varies per
kind, don't build a type hierarchy for it".

Reuses `decision_engine.models.Prediction` for Decision Engine alerts.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from decision_engine.models import Prediction


# ── Watchlists (requirement: unlimited watchlists / favorites / folders / tags / notes) ──


class Watchlist(BaseModel):
    id: Optional[int] = None
    owner: str
    name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("owner", "name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value


class WatchlistItem(BaseModel):
    """One symbol tracked within a watchlist."""

    id: Optional[int] = None
    watchlist_id: int
    symbol: str
    is_favorite: bool = False
    folder: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    notes: str = ""
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("symbol")
    @classmethod
    def _uppercase_symbol(cls, value: str) -> str:
        return value.upper()


# ── Alerts ────────────────────────────────────────────────────────────────


class AlertCategory(str, Enum):
    PRICE = "price"
    TECHNICAL = "technical"
    DECISION = "decision"
    NEWS = "news"
    PORTFOLIO = "portfolio"


class AlertType(str, Enum):
    # Price
    PRICE_ABOVE = "price_above"
    PRICE_BELOW = "price_below"
    PRICE_PERCENT_MOVE = "price_percent_move"
    PRICE_GAP = "price_gap"
    # Technical
    RSI_THRESHOLD = "rsi_threshold"
    MACD_CROSSOVER = "macd_crossover"
    EMA_CROSSOVER = "ema_crossover"
    BOLLINGER_BREAKOUT = "bollinger_breakout"
    VOLUME_SPIKE = "volume_spike"
    ATR_EXPANSION = "atr_expansion"
    # Decision Engine
    DECISION_BUY = "decision_buy"
    DECISION_SELL = "decision_sell"
    CONFIDENCE_CHANGE = "confidence_change"
    EXPECTED_RETURN_CHANGE = "expected_return_change"
    RISK_CHANGE = "risk_change"
    # News
    NEWS_HIGH_IMPACT = "news_high_impact"
    NEWS_SECTOR = "news_sector"
    NEWS_BREAKING = "news_breaking"
    # Portfolio
    PORTFOLIO_ALLOCATION_EXCEEDED = "portfolio_allocation_exceeded"
    PORTFOLIO_VAR_EXCEEDED = "portfolio_var_exceeded"
    PORTFOLIO_DRAWDOWN_EXCEEDED = "portfolio_drawdown_exceeded"
    PORTFOLIO_CONCENTRATION = "portfolio_concentration"


_SYMBOL_REQUIRED_CATEGORIES = {AlertCategory.PRICE, AlertCategory.TECHNICAL, AlertCategory.DECISION}
_PORTFOLIO_ID_REQUIRED_TYPES = {
    AlertType.PORTFOLIO_ALLOCATION_EXCEEDED, AlertType.PORTFOLIO_VAR_EXCEEDED,
    AlertType.PORTFOLIO_DRAWDOWN_EXCEEDED, AlertType.PORTFOLIO_CONCENTRATION,
}

CATEGORY_TYPES: Dict[AlertCategory, set] = {
    AlertCategory.PRICE: {
        AlertType.PRICE_ABOVE, AlertType.PRICE_BELOW, AlertType.PRICE_PERCENT_MOVE, AlertType.PRICE_GAP,
    },
    AlertCategory.TECHNICAL: {
        AlertType.RSI_THRESHOLD, AlertType.MACD_CROSSOVER, AlertType.EMA_CROSSOVER,
        AlertType.BOLLINGER_BREAKOUT, AlertType.VOLUME_SPIKE, AlertType.ATR_EXPANSION,
    },
    AlertCategory.DECISION: {
        AlertType.DECISION_BUY, AlertType.DECISION_SELL, AlertType.CONFIDENCE_CHANGE,
        AlertType.EXPECTED_RETURN_CHANGE, AlertType.RISK_CHANGE,
    },
    AlertCategory.NEWS: {AlertType.NEWS_HIGH_IMPACT, AlertType.NEWS_SECTOR, AlertType.NEWS_BREAKING},
    AlertCategory.PORTFOLIO: _PORTFOLIO_ID_REQUIRED_TYPES,
}


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class Alert(BaseModel):
    """One user-configured alert. `symbol` is required for PRICE/
    TECHNICAL/DECISION alerts, `portfolio_id` for PORTFOLIO alerts;
    NEWS alerts may target either a `symbol` or be sector-wide (neither
    set - see `news_alerts.py`). `last_state` remembers whatever the
    previous scan observed (last decision, last confidence, ...) so
    "changed"/"appeared" semantics can be edge-triggered rather than
    firing on every scan the underlying condition remains true."""

    id: Optional[int] = None
    owner: str
    watchlist_id: Optional[int] = None
    symbol: Optional[str] = None
    portfolio_id: Optional[int] = None
    category: AlertCategory
    alert_type: AlertType
    parameters: Dict[str, float] = Field(default_factory=dict)
    cooldown_minutes: int = Field(default=60, ge=0)
    enabled: bool = True
    last_state: Dict[str, float] = Field(default_factory=dict)
    last_checked_at: Optional[datetime] = None
    last_triggered_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("symbol")
    @classmethod
    def _uppercase_symbol(cls, value: Optional[str]) -> Optional[str]:
        return value.upper() if value else value

    @field_validator("owner")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value


class AlertTriggerEvent(BaseModel):
    """The result of one alert firing."""

    alert_id: int
    owner: str
    symbol: Optional[str] = None
    portfolio_id: Optional[int] = None
    category: AlertCategory
    alert_type: AlertType
    severity: AlertSeverity = AlertSeverity.INFO
    message: str
    evidence: Dict[str, float] = Field(default_factory=dict)
    related_decision: Optional[Prediction] = None
    triggered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Notifications (payloads only - no provider implementation) ─────────────


class NotificationPayload(BaseModel):
    """A fully-prepared notification, ready to hand to a real provider
    (Firebase/APNS/...) later - this platform only ever builds this
    payload, never sends it anywhere."""

    alert_id: int
    owner: str
    title: str
    body: str
    data: Dict[str, str] = Field(default_factory=dict)
    severity: AlertSeverity = AlertSeverity.INFO
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Scheduler ────────────────────────────────────────────────────────────


class AlertCheckStatus(str, Enum):
    TRIGGERED = "triggered"
    NOT_TRIGGERED = "not_triggered"
    SKIPPED_COOLDOWN = "skipped_cooldown"
    SKIPPED_DEDUP = "skipped_dedup"
    SKIPPED_NOT_DUE = "skipped_not_due"
    TIMEOUT = "timeout"
    FAILED = "failed"


class AlertCheckOutcome(BaseModel):
    alert_id: int
    status: AlertCheckStatus
    duration_ms: float = Field(..., ge=0.0)
    attempts: int = Field(..., ge=0)
    error_type: Optional[str] = None
    trigger_event: Optional[AlertTriggerEvent] = None


class ScanReport(BaseModel):
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    total_alerts: int = Field(..., ge=0)
    checked_count: int = Field(..., ge=0)
    triggered_count: int = Field(..., ge=0)
    outcomes: List[AlertCheckOutcome] = Field(default_factory=list)
    duration_ms: float = Field(..., ge=0.0)
