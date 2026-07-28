"""
OptiTrade Portfolio Intelligence Platform — Dashboard composition
(requirement 9).

Computes each piece (positions, allocation, risk, recommendations)
exactly once and threads the already-computed result into the next
step - "no duplicated calculations".
"""
from __future__ import annotations

from typing import Dict, Optional

from portfolio.analytics import PositionAnalyticsService
from portfolio.config import PortfolioConfig
from portfolio.exceptions import InsufficientPriceDataError
from portfolio.models import PortfolioDashboard
from portfolio.recommendations import RecommendationEngine
from portfolio.risk import RiskAnalyticsService
from portfolio.service import PortfolioService


class PortfolioDashboardService:
    def __init__(
        self,
        portfolio_service: Optional[PortfolioService] = None,
        position_analytics_service: Optional[PositionAnalyticsService] = None,
        risk_analytics_service: Optional[RiskAnalyticsService] = None,
        recommendation_engine: Optional[RecommendationEngine] = None,
        config: Optional[PortfolioConfig] = None,
    ) -> None:
        self.config = config or PortfolioConfig.from_env()
        self.position_analytics_service = position_analytics_service or PositionAnalyticsService(config=self.config)
        self.portfolio_service = portfolio_service or self.position_analytics_service.portfolio_service
        self.risk_analytics_service = risk_analytics_service or RiskAnalyticsService(
            position_analytics_service=self.position_analytics_service, config=self.config,
        )
        self.recommendation_engine = recommendation_engine or RecommendationEngine(
            position_analytics_service=self.position_analytics_service,
            risk_analytics_service=self.risk_analytics_service, config=self.config,
        )

    def build(self, portfolio_id: int, target_weights_pct: Optional[Dict[str, float]] = None) -> PortfolioDashboard:
        positions = self.position_analytics_service.analyze_positions(portfolio_id)
        allocation = self.position_analytics_service.allocation_breakdown(portfolio_id, positions)
        cash_balance = self.portfolio_service.get_cash_balance(portfolio_id)
        realized_pnl = self.portfolio_service.get_realized_pnl(portfolio_id)
        unrealized_pnl = sum(position.unrealized_pnl for position in positions)
        total_value = cash_balance + sum(position.current_value for position in positions)

        risk = None
        if positions:
            try:
                risk = self.risk_analytics_service.analyze(portfolio_id, positions)
            except InsufficientPriceDataError:
                risk = None

        recommendations = self.recommendation_engine.generate(
            portfolio_id, target_weights_pct=target_weights_pct, position_analytics=positions, risk_analytics=risk,
        )

        return PortfolioDashboard(
            portfolio_id=portfolio_id, cash_balance=cash_balance, total_value=total_value,
            realized_pnl=realized_pnl, unrealized_pnl=unrealized_pnl, positions=positions, allocation=allocation,
            risk=risk, recommendations=recommendations,
        )
