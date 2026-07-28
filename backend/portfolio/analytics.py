"""
OptiTrade Portfolio Intelligence Platform — Position Analytics
(requirement 2).

Reuses `PortfolioService.get_positions`/`get_cash_balance` (never
re-derives them from raw transactions a second time) and
`portfolio.classification` for sector/country/currency - this module's
only new computation is turning a `Position` + a current price into the
richer, presentation-ready `PositionAnalytics`/`AllocationBreakdown`
shapes.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from portfolio.classification import country_for_symbol, currency_for_symbol, sector_for_symbol
from portfolio.config import PortfolioConfig
from portfolio.models import AllocationBreakdown, PositionAnalytics
from portfolio.prices import PriceService
from portfolio.service import PortfolioService


class PositionAnalyticsService:
    def __init__(
        self,
        portfolio_service: Optional[PortfolioService] = None,
        price_service: Optional[PriceService] = None,
        config: Optional[PortfolioConfig] = None,
    ) -> None:
        self.config = config or PortfolioConfig.from_env()
        self.portfolio_service = portfolio_service or PortfolioService(config=self.config)
        self.price_service = price_service or self.portfolio_service.price_service

    def analyze_positions(self, portfolio_id: int) -> List[PositionAnalytics]:
        positions = self.portfolio_service.get_positions(portfolio_id)
        if not positions:
            return []

        cash_balance = self.portfolio_service.get_cash_balance(portfolio_id)
        current_prices = {
            position.symbol: self.price_service.get_current_price(position.symbol) for position in positions
        }
        positions_value = sum(position.quantity * current_prices[position.symbol] for position in positions)
        total_value = positions_value + cash_balance

        results: List[PositionAnalytics] = []
        for position in positions:
            current_price = current_prices[position.symbol]
            current_value = position.quantity * current_price
            cost_basis = position.quantity * position.average_cost
            unrealized_pnl = current_value - cost_basis
            unrealized_pnl_pct = (unrealized_pnl / cost_basis * 100) if cost_basis > 0 else 0.0
            weight_pct = (current_value / total_value * 100) if total_value > 0 else 0.0

            results.append(
                PositionAnalytics(
                    symbol=position.symbol, quantity=position.quantity, average_cost=position.average_cost,
                    current_price=current_price, cost_basis=cost_basis, current_value=current_value,
                    unrealized_pnl=unrealized_pnl, unrealized_pnl_pct=unrealized_pnl_pct,
                    realized_pnl=position.realized_pnl, weight_pct=weight_pct,
                    sector=sector_for_symbol(position.symbol), country=country_for_symbol(position.symbol),
                    currency=currency_for_symbol(position.symbol),
                )
            )
        return results

    def allocation_breakdown(
        self, portfolio_id: int, position_analytics: Optional[List[PositionAnalytics]] = None,
    ) -> AllocationBreakdown:
        """Pass an already-computed `position_analytics` list (e.g. from
        `analyze_positions`) to avoid recomputing it - the "no
        duplicated calculations" guarantee `dashboard.py` relies on."""
        positions = position_analytics if position_analytics is not None else self.analyze_positions(portfolio_id)
        cash_balance = self.portfolio_service.get_cash_balance(portfolio_id)
        positions_value = sum(position.current_value for position in positions)
        total_value = positions_value + cash_balance

        by_symbol: Dict[str, float] = {}
        by_sector: Dict[str, float] = {}
        by_country: Dict[str, float] = {}
        by_currency: Dict[str, float] = {}
        for position in positions:
            by_symbol[position.symbol] = by_symbol.get(position.symbol, 0.0) + position.weight_pct
            by_sector[position.sector] = by_sector.get(position.sector, 0.0) + position.weight_pct
            by_country[position.country] = by_country.get(position.country, 0.0) + position.weight_pct
            by_currency[position.currency] = by_currency.get(position.currency, 0.0) + position.weight_pct

        cash_weight_pct = (cash_balance / total_value * 100) if total_value > 0 else 100.0
        return AllocationBreakdown(
            by_symbol_pct=by_symbol, by_sector_pct=by_sector, by_country_pct=by_country,
            by_currency_pct=by_currency, cash_weight_pct=cash_weight_pct,
        )
