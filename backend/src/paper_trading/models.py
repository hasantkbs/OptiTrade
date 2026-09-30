"""
OptiTrade Paper Trading & Trade Journal Platform — domain models.

A paper account is backed by a REAL `portfolio.PortfolioService` ledger
(`PaperAccount.portfolio_id`) - fills are synchronized into it via
`portfolio_sync.py` so cash/positions/P&L reuse the already-built,
tested Portfolio Intelligence Platform ledger rather than duplicating
it. `Order`/`Fill` are this package's own concepts (order lifecycle,
simulated execution detail) with no equivalent in `portfolio`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from decision_engine.models import Prediction

# ── Orders ───────────────────────────────────────────────────────────────

class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    TAKE_PROFIT = "take_profit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


_OPEN_STATUSES = {OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED}


class PaperAccount(BaseModel):
    id: Optional[int] = None
    user_id: int
    portfolio_id: int
    name: str
    starting_balance: float = Field(..., gt=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value


class Order(BaseModel):
    id: Optional[int] = None
    account_id: int
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float = Field(..., gt=0)
    limit_price: Optional[float] = Field(default=None, gt=0)
    stop_price: Optional[float] = Field(default=None, gt=0)
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = Field(default=0.0, ge=0)
    average_fill_price: Optional[float] = None
    commission_paid: float = Field(default=0.0, ge=0)
    tax_paid: float = Field(default=0.0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cancelled_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    notes: str = ""

    @field_validator("symbol")
    @classmethod
    def _uppercase_symbol(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value.strip().upper()

    @model_validator(mode="after")
    def _validate_price_fields(self) -> "Order":
        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            raise ValueError("limit orders require a limit_price")
        if self.order_type in (OrderType.STOP, OrderType.TAKE_PROFIT) and self.stop_price is None:
            raise ValueError(f"{self.order_type.value} orders require a stop_price")
        return self

    @property
    def is_open(self) -> bool:
        return self.status in _OPEN_STATUSES

    @property
    def remaining_quantity(self) -> float:
        return max(self.quantity - self.filled_quantity, 0.0)


class Fill(BaseModel):
    id: Optional[int] = None
    order_id: int
    account_id: int
    symbol: str
    side: OrderSide
    quantity: float = Field(..., gt=0)
    price: float = Field(..., gt=0)
    slippage: float = 0.0
    spread_cost: float = Field(default=0.0, ge=0)
    commission: float = Field(default=0.0, ge=0)
    tax: float = Field(default=0.0, ge=0)
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Trade journal ────────────────────────────────────────────────────────

class MarketRegime(str, Enum):
    TRENDING_BULLISH = "trending_bullish"
    TRENDING_BEARISH = "trending_bearish"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    UNKNOWN = "unknown"


class EngineVoteSnapshot(BaseModel):
    """A frozen projection of one voting engine's contribution to a
    decision, captured at trade time (from `PipelineResponse.engine_breakdown`)."""

    engine_name: str
    engine_version: str
    prediction: Prediction
    confidence: float
    expected_return: float
    volatility: float
    evidence: List[str] = Field(default_factory=list)


class ScreenshotMetadata(BaseModel):
    id: Optional[int] = None
    journal_entry_id: Optional[int] = None
    url: str
    caption: str = ""
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("url")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value


class TradeJournalEntry(BaseModel):
    """Everything captured about the decision context behind one order,
    plus user-editable annotations. One entry per `Order` (created when
    the order is placed, updatable afterwards for notes/tags/screenshots)."""

    id: Optional[int] = None
    order_id: int
    account_id: int
    symbol: str
    decision: Optional[Prediction] = None
    confidence: Optional[float] = None
    expected_return: Optional[float] = None
    expected_volatility: Optional[float] = None
    risk_level: Optional[str] = None
    data_sufficiency: Optional[float] = None
    evidence: List[str] = Field(default_factory=list)
    engine_votes: List[EngineVoteSnapshot] = Field(default_factory=list)
    explanation_text: str = ""
    market_regime: MarketRegime = MarketRegime.UNKNOWN
    feature_snapshot: Dict[str, float] = Field(default_factory=dict)
    notes: str = ""
    tags: List[str] = Field(default_factory=list)
    screenshots: List[ScreenshotMetadata] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Analytics ────────────────────────────────────────────────────────────

class ClosedTrade(BaseModel):
    """One FIFO-matched round trip (an opening fill matched against a
    later closing fill of the same quantity, oldest-open-lot-first)."""

    account_id: int
    symbol: str
    side: OrderSide
    quantity: float
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    commission: float
    tax: float
    gross_pnl: float
    net_pnl: float
    holding_seconds: float


class AnalyticsSummary(BaseModel):
    total_trades: int = Field(..., ge=0)
    win_rate: float
    profit_factor: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    max_drawdown: float
    average_holding_time_seconds: float
    expectancy: float
    best_trade: Optional[ClosedTrade] = None
    worst_trade: Optional[ClosedTrade] = None


class EquityPoint(BaseModel):
    as_of: datetime
    equity: float


class MonthlyPerformance(BaseModel):
    year: int
    month: int
    net_pnl: float
    trades: int
    win_rate: float


# ── Reports ──────────────────────────────────────────────────────────────

class ReportPeriod(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class TradeReport(BaseModel):
    account_id: int
    period: ReportPeriod
    period_start: datetime
    period_end: datetime
    total_trades: int
    net_pnl: float
    win_rate: float
    profit_factor: Optional[float] = None
    best_trade: Optional[ClosedTrade] = None
    worst_trade: Optional[ClosedTrade] = None
