"""
OptiTrade Portfolio Intelligence Platform — Scenario Analysis
(requirement 6).

Reuses `PositionAnalyticsService.analyze_positions`/
`PriceService.get_returns` - never re-derives current values or
historical returns. The Monte Carlo simulation applies the same
geometric Brownian motion technique `core.advanced_analysis.
run_monte_carlo` already uses for a single symbol, but to the
portfolio's own weighted daily return series (mean/volatility derived
from actual current holdings) rather than one symbol at a time - a
distinct, portfolio-level computation, not a duplicate of that
function's single-series interface.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from portfolio.analytics import PositionAnalyticsService
from portfolio.config import PortfolioConfig
from portfolio.exceptions import InsufficientPriceDataError
from portfolio.models import PositionAnalytics, ScenarioResult, ScenarioType
from portfolio.prices import PriceService

# Rough per-sector interest-rate sensitivity (% price impact per 1%/100bps
# rate change) - growth/high-duration sectors (TECH) are hurt most by
# rising rates, financials (which earn more on rising net interest
# margins) are the only sector that benefits.
_SECTOR_RATE_SENSITIVITY: Dict[str, float] = {
    "TECH": -1.5, "FINANCE": 0.5, "HEALTH": -0.3, "INDUSTRIAL": -0.7,
    "CONSUMER": -0.6, "AVIATION": -0.9, "MATERIALS": -0.8, "AGRICULTURE": -0.4,
    "HOLDING": -0.6, "ENERGY": -0.5, "OTHER": -0.6,
}


class ScenarioAnalysisService:
    def __init__(
        self,
        position_analytics_service: Optional[PositionAnalyticsService] = None,
        price_service: Optional[PriceService] = None,
        config: Optional[PortfolioConfig] = None,
    ) -> None:
        self.config = config or PortfolioConfig.from_env()
        self.position_analytics_service = position_analytics_service or PositionAnalyticsService(config=self.config)
        self.price_service = price_service or self.position_analytics_service.price_service

    def market_crash(
        self, portfolio_id: int, drop_pct: float = 30.0, position_analytics: Optional[List[PositionAnalytics]] = None,
    ) -> ScenarioResult:
        """Applies a uniform `drop_pct` crash to every held position;
        cash is unaffected."""
        positions, cash_balance = self._positions_and_cash(portfolio_id, position_analytics)
        value_before = sum(position.current_value for position in positions) + cash_balance

        per_position_impact: Dict[str, float] = {}
        value_after = cash_balance
        for position in positions:
            impact_pct = -drop_pct
            per_position_impact[position.symbol] = impact_pct
            value_after += position.current_value * (1 + impact_pct / 100.0)

        return self._result(ScenarioType.MARKET_CRASH, value_before, value_after, per_position_impact, {"drop_pct": drop_pct})

    def volatility_shock(
        self, portfolio_id: int, volatility_multiplier: float = 2.0,
        position_analytics: Optional[List[PositionAnalytics]] = None,
    ) -> ScenarioResult:
        """A one-day move at `volatility_multiplier` times the
        portfolio's own recent daily volatility, applied uniformly to
        every held position."""
        positions, cash_balance = self._positions_and_cash(portfolio_id, position_analytics)
        portfolio_returns, _ = self._weighted_returns(positions)
        base_daily_vol = float(np.std(portfolio_returns))
        shocked_daily_vol = base_daily_vol * volatility_multiplier
        shock_pct = -shocked_daily_vol * 100.0

        value_before = sum(position.current_value for position in positions) + cash_balance
        per_position_impact = {position.symbol: shock_pct for position in positions}
        value_after = cash_balance + sum(
            position.current_value * (1 + shock_pct / 100.0) for position in positions
        )

        return self._result(
            ScenarioType.VOLATILITY_SHOCK, value_before, value_after, per_position_impact,
            {
                "volatility_multiplier": volatility_multiplier, "base_daily_volatility_pct": base_daily_vol * 100.0,
                "shocked_daily_volatility_pct": shocked_daily_vol * 100.0,
            },
        )

    def interest_rate_shock(
        self, portfolio_id: int, rate_change_bps: float = 100.0,
        position_analytics: Optional[List[PositionAnalytics]] = None,
    ) -> ScenarioResult:
        """Applies each position's sector-level interest-rate
        sensitivity, scaled to `rate_change_bps` (100bps = 1%)."""
        positions, cash_balance = self._positions_and_cash(portfolio_id, position_analytics)
        value_before = sum(position.current_value for position in positions) + cash_balance

        per_position_impact: Dict[str, float] = {}
        value_after = cash_balance
        for position in positions:
            sensitivity = _SECTOR_RATE_SENSITIVITY.get(position.sector, _SECTOR_RATE_SENSITIVITY["OTHER"])
            impact_pct = sensitivity * (rate_change_bps / 100.0)
            per_position_impact[position.symbol] = impact_pct
            value_after += position.current_value * (1 + impact_pct / 100.0)

        return self._result(
            ScenarioType.INTEREST_RATE_SHOCK, value_before, value_after, per_position_impact,
            {"rate_change_bps": rate_change_bps},
        )

    def monte_carlo_simulation(
        self, portfolio_id: int, n_simulations: Optional[int] = None, horizon_days: Optional[int] = None,
        position_analytics: Optional[List[PositionAnalytics]] = None,
    ) -> ScenarioResult:
        """Geometric Brownian motion over the portfolio's own weighted
        daily return series (mean/volatility), simulated `horizon_days`
        forward - cash is carried flat, only the equity portion is
        simulated."""
        n_simulations = n_simulations or self.config.monte_carlo_simulations
        horizon_days = horizon_days or self.config.monte_carlo_horizon_days

        positions, cash_balance = self._positions_and_cash(portfolio_id, position_analytics)
        portfolio_returns, equity_value = self._weighted_returns(positions)
        mu = float(np.mean(portfolio_returns))
        sigma = float(np.std(portfolio_returns))
        value_before = equity_value + cash_balance

        rng = np.random.default_rng(42)
        shocks = rng.standard_normal((n_simulations, horizon_days))
        daily_factors = np.exp((mu - 0.5 * sigma ** 2) + sigma * shocks)
        cumulative_factors = np.prod(daily_factors, axis=1)
        final_total_values = cash_balance + equity_value * cumulative_factors

        value_after = float(np.mean(final_total_values))
        total_returns = (final_total_values - value_before) / value_before if value_before > 0 else final_total_values * 0
        confidence = self.config.var_confidence_level
        var_pct = float(np.percentile(total_returns, (1.0 - confidence) * 100) * 100)
        tail = total_returns[total_returns <= var_pct / 100]
        cvar_pct = float(tail.mean() * 100) if len(tail) > 0 else var_pct
        prob_profit_pct = float(np.mean(final_total_values > value_before) * 100)

        return self._result(
            ScenarioType.MONTE_CARLO, value_before, value_after, {},
            {
                "var_95_pct": var_pct, "cvar_95_pct": cvar_pct, "prob_profit_pct": prob_profit_pct,
                "n_simulations": float(n_simulations), "horizon_days": float(horizon_days),
            },
        )

    def _positions_and_cash(
        self, portfolio_id: int, position_analytics: Optional[List[PositionAnalytics]],
    ) -> tuple:
        positions = (
            position_analytics if position_analytics is not None
            else self.position_analytics_service.analyze_positions(portfolio_id)
        )
        if not positions:
            raise InsufficientPriceDataError(
                f"portfolio {portfolio_id}: cannot run a scenario with no open positions"
            )
        cash_balance = self.position_analytics_service.portfolio_service.get_cash_balance(portfolio_id)
        return positions, cash_balance

    def _weighted_returns(self, positions: List[PositionAnalytics]) -> tuple:
        symbols = [position.symbol for position in positions]
        values_by_symbol = {position.symbol: position.current_value for position in positions}
        equity_value = sum(values_by_symbol.values())

        returns = self.price_service.get_returns(symbols, lookback_days=self.config.lookback_days)
        available_symbols = [symbol for symbol in symbols if symbol in returns.columns]
        if not available_symbols:
            raise InsufficientPriceDataError("no historical return data available for any held symbol")

        weights = np.array([values_by_symbol[symbol] / equity_value for symbol in available_symbols])
        portfolio_returns = returns[available_symbols].to_numpy() @ weights
        return portfolio_returns, equity_value

    @staticmethod
    def _result(
        scenario_type: ScenarioType, value_before: float, value_after: float,
        per_position_impact_pct: Dict[str, float], details: Dict[str, float],
    ) -> ScenarioResult:
        pnl = value_after - value_before
        pnl_pct = (pnl / value_before * 100.0) if value_before > 0 else 0.0
        return ScenarioResult(
            scenario_type=scenario_type, portfolio_value_before=value_before, portfolio_value_after=value_after,
            pnl=pnl, pnl_pct=pnl_pct, per_position_impact_pct=per_position_impact_pct, details=details,
        )
