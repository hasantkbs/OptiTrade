"""
OptiTrade Analytics & Dashboard Platform — Portfolio dashboard.

`portfolio.dashboard.PortfolioDashboardService` already assembles
allocation (incl. sector/currency exposure), pnl, drawdown, and risk in
one call - this module reuses it verbatim (no duplicated calculations,
matching that platform's own stated policy) and adds only the one
metric it doesn't already compute: a realized Sharpe ratio, from the
account's own snapshot history.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from dashboard.metrics import compute_sharpe_ratio, returns_from_equity_curve
from dashboard.models import PortfolioDashboardExtended
from portfolio.dashboard import PortfolioDashboardService
from portfolio.service import PortfolioService

logger = logging.getLogger(__name__)
_MODULE = "dashboard.portfolio_dashboard"
_COMPONENT = "dashboard"


class DashboardPortfolioService:
    def __init__(
        self,
        portfolio_dashboard_service: Optional[PortfolioDashboardService] = None,
        portfolio_service: Optional[PortfolioService] = None,
    ) -> None:
        self._portfolio_dashboard_service = portfolio_dashboard_service or PortfolioDashboardService()
        self._portfolio_service = portfolio_service or self._portfolio_dashboard_service.portfolio_service

    def build(self, portfolio_id: int, snapshot_limit: int = 100) -> PortfolioDashboardExtended:
        started_at = time.perf_counter()
        dashboard = self._portfolio_dashboard_service.build(portfolio_id)

        snapshots = self._portfolio_service.get_history(portfolio_id, limit=snapshot_limit)
        equity_curve = [snapshot.total_value for snapshot in sorted(snapshots, key=lambda s: s.as_of)]
        sharpe_ratio = compute_sharpe_ratio(returns_from_equity_curve(equity_curve))

        view = PortfolioDashboardExtended(dashboard=dashboard, sharpe_ratio=sharpe_ratio)
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="build", status=STATUS_SUCCESS,
            execution_time_ms=(time.perf_counter() - started_at) * 1000, portfolio_id=portfolio_id,
        )
        return view
