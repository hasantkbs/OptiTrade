"""
OptiTrade Paper Trading & Trade Journal Platform — FastAPI request/response schemas.

Domain models that are already API-safe as-is (`ClosedTrade`,
`EquityPoint`, `MonthlyPerformance`, `TradeReport`,
`portfolio.models.PositionAnalytics`) are reused directly rather than
re-declared here - only entities needing request shapes or a trimmed/
`from_attributes` response projection get their own schema.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from paper_trading.models import MarketRegime, OrderSide, OrderStatus, OrderType
from decision_engine.models import Prediction


class _ResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Accounts ─────────────────────────────────────────────────────────────

class CreateAccountRequest(BaseModel):
    """`owner_email` is deliberately not a client-supplied field - the
    FastAPI layer derives it from the authenticated user (see main.py),
    so nobody can open a paper account under someone else's identity."""

    name: str = "Paper Trading Account"
    starting_balance: float = Field(default=100_000.0, gt=0)


class AccountResponse(_ResponseModel):
    id: int
    user_id: int
    portfolio_id: int
    name: str
    starting_balance: float
    created_at: datetime


# ── Orders ───────────────────────────────────────────────────────────────

class PlaceOrderRequest(BaseModel):
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float = Field(..., gt=0)
    limit_price: Optional[float] = Field(default=None, gt=0)
    stop_price: Optional[float] = Field(default=None, gt=0)
    notes: str = ""


class ModifyOrderRequest(BaseModel):
    quantity: Optional[float] = Field(default=None, gt=0)
    limit_price: Optional[float] = Field(default=None, gt=0)
    stop_price: Optional[float] = Field(default=None, gt=0)


class OrderResponse(_ResponseModel):
    id: int
    account_id: int
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    status: OrderStatus
    filled_quantity: float
    average_fill_price: Optional[float] = None
    commission_paid: float
    tax_paid: float
    created_at: datetime
    updated_at: datetime
    cancelled_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    notes: str


class FillResponse(_ResponseModel):
    id: int
    order_id: int
    account_id: int
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    slippage: float
    spread_cost: float
    commission: float
    tax: float
    executed_at: datetime


# ── Trade journal ────────────────────────────────────────────────────────

class UpdateJournalNotesRequest(BaseModel):
    notes: str


class AddJournalTagsRequest(BaseModel):
    tags: List[str]


class AddScreenshotRequest(BaseModel):
    url: str
    caption: str = ""


class EngineVoteResponse(_ResponseModel):
    engine_name: str
    engine_version: str
    prediction: Prediction
    confidence: float
    expected_return: float
    volatility: float
    evidence: List[str]


class ScreenshotResponse(_ResponseModel):
    id: int
    journal_entry_id: int
    url: str
    caption: str
    uploaded_at: datetime


class JournalEntryResponse(_ResponseModel):
    id: int
    order_id: int
    account_id: int
    symbol: str
    decision: Optional[Prediction] = None
    confidence: Optional[float] = None
    expected_return: Optional[float] = None
    expected_volatility: Optional[float] = None
    risk_level: Optional[str] = None
    data_sufficiency: Optional[float] = None
    evidence: List[str]
    engine_votes: List[EngineVoteResponse]
    explanation_text: str
    market_regime: MarketRegime
    feature_snapshot: dict
    notes: str
    tags: List[str]
    screenshots: List[ScreenshotResponse]
    created_at: datetime
    updated_at: datetime
