"""
OptiTrade Analytics & Dashboard Platform — top-level facade.

Composes every sub-dashboard into the single entry point FastAPI
endpoints (and `scheduler.py`) should use. Each sub-service can still be
constructed and tested independently - this class only wires the
defaults together and exposes one thin method per dashboard.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from dashboard.alert_dashboard import AlertDashboardService
from dashboard.engine_dashboard import EngineDashboardService
from dashboard.learning_dashboard import LearningDashboardService
from dashboard.market_dashboard import MarketDashboardService
from dashboard.model_dashboard import ModelDashboardService
from dashboard.models import (
    AlertDashboardView,
    DashboardReport,
    EngineDashboardView,
    LearningDashboardView,
    MarketDashboardView,
    MLDashboardView,
    OverviewMetrics,
    PaperTradingDashboardView,
    PortfolioDashboardExtended,
    ReportPeriod,
    WatchlistDashboardView,
)
from dashboard.overview import OverviewDashboardService
from dashboard.paper_trading_dashboard import PaperTradingDashboardService
from dashboard.portfolio_dashboard import DashboardPortfolioService
from dashboard.repository import DashboardRepository
from dashboard.reports import ReportService
from dashboard.watchlist_dashboard import WatchlistDashboardService
from learning.models import RollingWindow


class DashboardService:
    def __init__(
        self,
        repository: DashboardRepository,
        overview_service: Optional[OverviewDashboardService] = None,
        engine_dashboard_service: Optional[EngineDashboardService] = None,
        model_dashboard_service: Optional[ModelDashboardService] = None,
        portfolio_dashboard_service: Optional[DashboardPortfolioService] = None,
        watchlist_dashboard_service: Optional[WatchlistDashboardService] = None,
        paper_trading_dashboard_service: Optional[PaperTradingDashboardService] = None,
        learning_dashboard_service: Optional[LearningDashboardService] = None,
        alert_dashboard_service: Optional[AlertDashboardService] = None,
        market_dashboard_service: Optional[MarketDashboardService] = None,
        report_service: Optional[ReportService] = None,
    ) -> None:
        self._repository = repository
        self.overview_service = overview_service or OverviewDashboardService(repository)
        self.engine_dashboard_service = engine_dashboard_service or EngineDashboardService(repository)
        self.model_dashboard_service = model_dashboard_service or ModelDashboardService(repository)
        self.portfolio_dashboard_service = portfolio_dashboard_service or DashboardPortfolioService()
        self.watchlist_dashboard_service = watchlist_dashboard_service or WatchlistDashboardService()
        self.paper_trading_dashboard_service = paper_trading_dashboard_service or PaperTradingDashboardService()
        self.learning_dashboard_service = learning_dashboard_service or LearningDashboardService(repository)
        self.alert_dashboard_service = alert_dashboard_service or AlertDashboardService(repository)
        self.market_dashboard_service = market_dashboard_service or MarketDashboardService()
        self.report_service = report_service or ReportService(repository, self.overview_service)

    def get_overview(self) -> OverviewMetrics:
        return self.overview_service.build()

    def get_engine_dashboard(self, symbol: Optional[str] = None, regime_symbols: Optional[List[str]] = None) -> EngineDashboardView:
        return self.engine_dashboard_service.build(symbol=symbol, regime_symbols=regime_symbols)

    def get_model_dashboard(self, feature_importance_model_ids: Optional[List[str]] = None) -> MLDashboardView:
        return self.model_dashboard_service.build(feature_importance_model_ids=feature_importance_model_ids)

    def get_portfolio_dashboard(self, portfolio_id: int) -> PortfolioDashboardExtended:
        return self.portfolio_dashboard_service.build(portfolio_id)

    def get_watchlist_dashboard(self, owner: str) -> WatchlistDashboardView:
        return self.watchlist_dashboard_service.build(owner)

    def get_paper_trading_dashboard(self, account_id: int) -> PaperTradingDashboardView:
        return self.paper_trading_dashboard_service.build(account_id)

    def get_learning_dashboard(self, window: RollingWindow = RollingWindow.THIRTY_DAY) -> LearningDashboardView:
        return self.learning_dashboard_service.build(ranking_window=window)

    def get_alert_dashboard(self, owner: Optional[str] = None) -> AlertDashboardView:
        return self.alert_dashboard_service.build(owner=owner)

    def get_market_dashboard(self, symbols: Optional[List[str]] = None, market: str = "US") -> MarketDashboardView:
        return self.market_dashboard_service.build(symbols=symbols, market=market)

    def generate_report(self, period: ReportPeriod, reference: Optional[datetime] = None) -> DashboardReport:
        return self.report_service.generate(period, reference=reference)
