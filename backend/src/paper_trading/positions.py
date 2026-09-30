"""
OptiTrade Paper Trading & Trade Journal Platform — live positions.

A thin, account-scoped wrapper around the Portfolio Intelligence
Platform's own `PositionAnalyticsService`/`PortfolioService` - paper
positions ARE portfolio positions (see `portfolio_sync.py`), so this
module never re-derives quantity/cost/P&L itself.
"""
from __future__ import annotations

from typing import List, Optional

from portfolio.analytics import PositionAnalyticsService
from portfolio.models import PositionAnalytics
from portfolio.service import PortfolioService

from paper_trading.models import PaperAccount


class PositionService:
    def __init__(
        self, portfolio_service: PortfolioService, position_analytics_service: Optional[PositionAnalyticsService] = None,
    ) -> None:
        self._portfolio_service = portfolio_service
        self._position_analytics_service = position_analytics_service or PositionAnalyticsService(
            portfolio_service=portfolio_service,
        )

    def get_positions(self, account: PaperAccount) -> List[PositionAnalytics]:
        return self._position_analytics_service.analyze_positions(account.portfolio_id)

    def get_cash_balance(self, account: PaperAccount) -> float:
        return self._portfolio_service.get_cash_balance(account.portfolio_id)

    def get_total_value(self, account: PaperAccount) -> float:
        return self._portfolio_service.get_total_value(account.portfolio_id)

    def get_realized_pnl(self, account: PaperAccount) -> float:
        return self._portfolio_service.get_realized_pnl(account.portfolio_id)

    def get_unrealized_pnl(self, account: PaperAccount) -> float:
        return self._portfolio_service.get_unrealized_pnl(account.portfolio_id)
