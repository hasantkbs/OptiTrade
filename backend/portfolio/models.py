"""
OptiTrade Portfolio Intelligence Platform — domain models.

Positions are never stored directly - `service.py` always derives them
by replaying a portfolio's `Transaction` history (weighted-average-cost
accounting), the same "definition/ledger only, never a second mutable
copy" philosophy already established for `research_lab.datasets`/
`ml_training.datasets`. `Transaction` is therefore the only persisted
per-holding record; `PortfolioSnapshot` is the only persisted portfolio-
level history record (requirement 1's "portfolio history").

Reuses `decision_engine.models.Prediction` for the recommendation
engine's signal-derived recommendations (requirement 7 - "Use Decision
Engine outputs").
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from decision_engine.models import Prediction


# ── Portfolio / transactions (requirement 1) ────────────────────────────


class TransactionType(str, Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"
    FEE = "fee"
    TAX = "tax"


_SYMBOL_REQUIRED_TYPES = {TransactionType.BUY, TransactionType.SELL}


class Portfolio(BaseModel):
    id: Optional[int] = None
    owner: str
    name: str
    base_currency: str = "USD"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("owner", "name", "base_currency")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value


class Transaction(BaseModel):
    """One ledger entry. `quantity`/`price` are only meaningful for
    BUY/SELL; `fee`/`tax` may accompany any transaction type (a
    standalone FEE/TAX transaction is also supported for charges not
    tied to a specific trade, e.g. a custody fee or withheld dividend
    tax)."""

    id: Optional[int] = None
    portfolio_id: int
    transaction_type: TransactionType
    symbol: Optional[str] = None
    quantity: Optional[float] = Field(default=None, gt=0.0)
    price: Optional[float] = Field(default=None, gt=0.0)
    amount: float = Field(..., ge=0.0)
    fee: float = Field(default=0.0, ge=0.0)
    tax: float = Field(default=0.0, ge=0.0)
    currency: str = "USD"
    executed_at: datetime
    notes: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("symbol")
    @classmethod
    def _uppercase_symbol(cls, value: Optional[str]) -> Optional[str]:
        return value.upper() if value else value


class Position(BaseModel):
    """A derived (never persisted directly) holding, replayed from
    weighted-average-cost accounting over a symbol's BUY/SELL history."""

    portfolio_id: int
    symbol: str
    quantity: float = Field(..., ge=0.0)
    average_cost: float = Field(..., ge=0.0)
    realized_pnl: float = 0.0


class PortfolioSnapshot(BaseModel):
    """One point-in-time portfolio history record (requirement 1's
    "portfolio history") - taken explicitly via
    `service.py:PortfolioService.take_snapshot`, mirroring
    `learning.service.LearningService.run_learning_cycle`'s "invoked by
    an external caller, never self-scheduled" convention."""

    id: Optional[int] = None
    portfolio_id: int
    as_of: datetime
    cash_balance: float
    positions_value: float
    total_value: float
    unrealized_pnl: float
    realized_pnl: float
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Position analytics (requirement 2) ──────────────────────────────────


class PositionAnalytics(BaseModel):
    symbol: str
    quantity: float = Field(..., ge=0.0)
    average_cost: float = Field(..., ge=0.0)
    current_price: float = Field(..., ge=0.0)
    cost_basis: float = Field(..., ge=0.0)
    current_value: float = Field(..., ge=0.0)
    unrealized_pnl: float
    unrealized_pnl_pct: float
    realized_pnl: float
    weight_pct: float = Field(..., ge=0.0, le=100.0)
    sector: str
    country: str
    currency: str


class AllocationBreakdown(BaseModel):
    by_symbol_pct: Dict[str, float] = Field(default_factory=dict)
    by_sector_pct: Dict[str, float] = Field(default_factory=dict)
    by_country_pct: Dict[str, float] = Field(default_factory=dict)
    by_currency_pct: Dict[str, float] = Field(default_factory=dict)
    cash_weight_pct: float = Field(..., ge=0.0, le=100.0)


# ── Risk analytics (requirement 3) ──────────────────────────────────────


class RiskAnalytics(BaseModel):
    volatility_pct: float = Field(..., ge=0.0)
    beta: Optional[float] = None
    correlation_matrix: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    diversification_score: float = Field(..., ge=0.0, le=1.0)
    var_95_pct: float
    cvar_95_pct: float
    max_drawdown_pct: float = Field(..., le=0.0)
    expected_drawdown_pct: float = Field(..., le=0.0)
    downside_risk_pct: float = Field(..., ge=0.0)
    concentration_risk: float = Field(..., ge=0.0, le=1.0)


# ── Portfolio optimization (requirement 4) ──────────────────────────────


class OptimizationStrategy(str, Enum):
    MEAN_VARIANCE = "mean_variance"
    RISK_PARITY = "risk_parity"
    MIN_VARIANCE = "min_variance"
    MAX_SHARPE = "max_sharpe"
    MONTE_CARLO = "monte_carlo"


class OptimizationResult(BaseModel):
    strategy: OptimizationStrategy
    symbols: List[str]
    weights: Dict[str, float] = Field(default_factory=dict)
    expected_annual_return_pct: float
    annual_volatility_pct: float = Field(..., ge=0.0)
    sharpe_ratio: float
    used_prediction_views: bool = False


class EfficientFrontierPoint(BaseModel):
    volatility_pct: float = Field(..., ge=0.0)
    expected_return_pct: float
    weights: Dict[str, float] = Field(default_factory=dict)


class EfficientFrontier(BaseModel):
    symbols: List[str]
    points: List[EfficientFrontierPoint] = Field(default_factory=list)
    max_sharpe_point: Optional[EfficientFrontierPoint] = None
    min_variance_point: Optional[EfficientFrontierPoint] = None


# ── Rebalancing (requirement 5) ─────────────────────────────────────────


class RebalanceTrigger(str, Enum):
    THRESHOLD = "threshold"
    SCHEDULED = "scheduled"
    MANUAL = "manual"


class RebalanceAction(str, Enum):
    BUY = "buy"
    SELL = "sell"


class RebalanceTrade(BaseModel):
    symbol: str
    action: RebalanceAction
    current_weight_pct: float
    target_weight_pct: float
    drift_pct: float
    quantity: float = Field(..., ge=0.0)
    estimated_price: float = Field(..., ge=0.0)
    estimated_amount: float = Field(..., ge=0.0)
    estimated_fee: float = Field(..., ge=0.0)


class RebalancePlan(BaseModel):
    portfolio_id: int
    trigger: RebalanceTrigger
    needs_rebalancing: bool
    trades: List[RebalanceTrade] = Field(default_factory=list)
    total_estimated_fees: float = Field(default=0.0, ge=0.0)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Scenario analysis (requirement 6) ───────────────────────────────────


class ScenarioType(str, Enum):
    MARKET_CRASH = "market_crash"
    VOLATILITY_SHOCK = "volatility_shock"
    INTEREST_RATE_SHOCK = "interest_rate_shock"
    MONTE_CARLO = "monte_carlo"
    CUSTOM = "custom"


class ScenarioResult(BaseModel):
    scenario_type: ScenarioType
    portfolio_value_before: float = Field(..., ge=0.0)
    portfolio_value_after: float = Field(..., ge=0.0)
    pnl: float
    pnl_pct: float
    per_position_impact_pct: Dict[str, float] = Field(default_factory=dict)
    details: Dict[str, float] = Field(default_factory=dict)


# ── Recommendation engine (requirement 7) ───────────────────────────────


class RecommendationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class RecommendationType(str, Enum):
    REBALANCE = "rebalance"
    OVERWEIGHT = "overweight"
    DIVERSIFICATION = "diversification"
    CONCENTRATION = "concentration"
    DECISION_SIGNAL = "decision_signal"


class Recommendation(BaseModel):
    recommendation_type: RecommendationType
    severity: RecommendationSeverity
    symbol: Optional[str] = None
    message: str
    evidence: List[str] = Field(default_factory=list)
    related_decision: Optional[Prediction] = None


# ── Dashboard (requirement 9) ────────────────────────────────────────────


class PortfolioDashboard(BaseModel):
    """Assembled purely from already-computed pieces (analytics, risk,
    recommendations) - never recomputes anything itself, satisfying
    requirement 9's "no duplicated calculations"."""

    portfolio_id: int
    as_of: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cash_balance: float
    total_value: float = Field(..., ge=0.0)
    realized_pnl: float
    unrealized_pnl: float
    positions: List[PositionAnalytics] = Field(default_factory=list)
    allocation: AllocationBreakdown
    risk: Optional[RiskAnalytics] = None
    recommendations: List[Recommendation] = Field(default_factory=list)


# ── API request models (requirement 8) ──────────────────────────────────


class CreatePortfolioRequest(BaseModel):
    name: str
    base_currency: str = "USD"
    owner: Optional[str] = None  # deprecated: ignored - owner is always the authenticated caller


class DepositRequest(BaseModel):
    amount: float = Field(..., gt=0.0)
    currency: Optional[str] = None
    notes: str = ""


class WithdrawRequest(BaseModel):
    amount: float = Field(..., gt=0.0)
    currency: Optional[str] = None
    notes: str = ""


class TradeRequest(BaseModel):
    symbol: str
    quantity: float = Field(..., gt=0.0)
    price: float = Field(..., gt=0.0)
    fee: float = Field(default=0.0, ge=0.0)
    tax: float = Field(default=0.0, ge=0.0)
    notes: str = ""


class DividendRequest(BaseModel):
    symbol: str
    amount: float = Field(..., gt=0.0)
    tax: float = Field(default=0.0, ge=0.0)
    notes: str = ""


class OptimizeRequest(BaseModel):
    symbols: List[str]
    strategy: OptimizationStrategy = OptimizationStrategy.MAX_SHARPE
    risk_tolerance: float = Field(default=0.5, ge=0.0, le=1.0)
    use_prediction_views: bool = False


class RebalanceRequest(BaseModel):
    target_weights_pct: Dict[str, float]
    trigger: RebalanceTrigger = RebalanceTrigger.MANUAL
    threshold_pct: Optional[float] = None


class ScenarioRequest(BaseModel):
    scenario_type: ScenarioType
    drop_pct: Optional[float] = None
    volatility_multiplier: Optional[float] = None
    rate_change_bps: Optional[float] = None
    n_simulations: Optional[int] = None
    horizon_days: Optional[int] = None


class RecommendationsRequest(BaseModel):
    target_weights_pct: Optional[Dict[str, float]] = None
