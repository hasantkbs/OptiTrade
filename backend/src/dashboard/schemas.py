"""
OptiTrade Analytics & Dashboard Platform — FastAPI request schemas.

Every dashboard is a read (GET) endpoint, so almost all of this
platform's API-facing shapes are already the plain response models in
`models.py` (reused directly, `from_attributes`-free since they're
built fresh by each `*_dashboard.py` service, never round-tripped from
an ORM row). The only genuinely new shapes needed here are the handful
of request bodies for endpoints that take a symbol list or a report
format too long/structured for query parameters.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from dashboard.models import ReportFormat


class MarketDashboardRequest(BaseModel):
    symbols: Optional[List[str]] = None
    market: str = "US"


class EngineDashboardRequest(BaseModel):
    symbol: Optional[str] = None
    regime_symbols: Optional[List[str]] = None


class ReportRequest(BaseModel):
    format: ReportFormat = ReportFormat.JSON


class RefreshCacheResponse(BaseModel):
    refreshed: dict = Field(default_factory=dict)
