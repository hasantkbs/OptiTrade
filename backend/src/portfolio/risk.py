"""
OptiTrade Portfolio Intelligence Platform — Risk Analytics
(requirement 3).

Every metric here is computed from one weighted daily portfolio return
series (position weights - already computed by `analytics.py`, never
re-derived - applied to each symbol's historical daily returns from
`PriceService.get_returns`), so a single portfolio replay directly
feeds every metric below with no duplicated calculation.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from portfolio.analytics import PositionAnalyticsService
from portfolio.config import PortfolioConfig
from portfolio.exceptions import InsufficientPriceDataError
from portfolio.models import PositionAnalytics, RiskAnalytics
from portfolio.prices import PriceService


def _diversification_score(
    correlation: pd.DataFrame, weights_by_symbol: Dict[str, float], symbols: List[str],
) -> float:
    """1 minus the position-weighted average absolute pairwise
    correlation among held symbols - 1.0 means held symbols move
    independently of each other (well diversified), 0.0 means they move
    in lockstep (no diversification benefit). A single-position
    portfolio has no pair to average, so it scores 0.0 - concentration
    in one asset is definitionally undiversified."""
    if len(symbols) < 2:
        return 0.0

    weighted_corr_sum = 0.0
    weight_pair_sum = 0.0
    for i, symbol_a in enumerate(symbols):
        for symbol_b in symbols[i + 1:]:
            pair_weight = weights_by_symbol[symbol_a] * weights_by_symbol[symbol_b]
            weighted_corr_sum += pair_weight * abs(float(correlation.loc[symbol_a, symbol_b]))
            weight_pair_sum += pair_weight

    if weight_pair_sum <= 0:
        return 0.0
    average_correlation = weighted_corr_sum / weight_pair_sum
    return max(0.0, min(1.0, 1.0 - average_correlation))


def _concentration_risk(weights_by_symbol: Dict[str, float]) -> float:
    """Herfindahl-Hirschman Index over position weights (cash excluded,
    then renormalized among positions) - 1/n for n equally-weighted
    positions, up to 1.0 for a single position."""
    total_weight = sum(weights_by_symbol.values())
    if total_weight <= 0:
        return 0.0
    normalized = [weight / total_weight for weight in weights_by_symbol.values()]
    return float(sum(weight ** 2 for weight in normalized))


class RiskAnalyticsService:
    def __init__(
        self,
        position_analytics_service: Optional[PositionAnalyticsService] = None,
        price_service: Optional[PriceService] = None,
        config: Optional[PortfolioConfig] = None,
    ) -> None:
        self.config = config or PortfolioConfig.from_env()
        self.position_analytics_service = position_analytics_service or PositionAnalyticsService(config=self.config)
        self.price_service = price_service or self.position_analytics_service.price_service

    def analyze(
        self, portfolio_id: int, position_analytics: Optional[List[PositionAnalytics]] = None,
    ) -> RiskAnalytics:
        """Pass an already-computed `position_analytics` list to avoid
        recomputing it (the "no duplicated calculations" guarantee
        `dashboard.py` relies on)."""
        positions = (
            position_analytics if position_analytics is not None
            else self.position_analytics_service.analyze_positions(portfolio_id)
        )
        if not positions:
            raise InsufficientPriceDataError(
                f"portfolio {portfolio_id}: cannot compute risk analytics with no open positions"
            )

        weights_by_symbol = {position.symbol: position.weight_pct / 100.0 for position in positions}
        symbols = list(weights_by_symbol.keys())

        returns = self.price_service.get_returns(symbols, lookback_days=self.config.lookback_days)
        available_symbols = [symbol for symbol in symbols if symbol in returns.columns]
        if not available_symbols:
            raise InsufficientPriceDataError(
                f"portfolio {portfolio_id}: no historical return data available for any held symbol"
            )

        weight_vector = np.array([weights_by_symbol[symbol] for symbol in available_symbols])
        portfolio_returns = returns[available_symbols].to_numpy() @ weight_vector
        trading_days = self.config.trading_days_per_year

        volatility_pct = float(np.std(portfolio_returns) * np.sqrt(trading_days) * 100)
        beta = self._beta(portfolio_returns, returns.index)

        correlation = returns[available_symbols].corr()
        correlation_matrix = {
            row: {col: float(correlation.loc[row, col]) for col in correlation.columns}
            for row in correlation.index
        }
        diversification_score = _diversification_score(correlation, weights_by_symbol, available_symbols)

        confidence = self.config.var_confidence_level
        var_pct = float(np.percentile(portfolio_returns, (1.0 - confidence) * 100) * 100)
        tail_losses = portfolio_returns[portfolio_returns <= var_pct / 100]
        cvar_pct = float(tail_losses.mean() * 100) if len(tail_losses) > 0 else var_pct

        cumulative = np.cumprod(1 + portfolio_returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdown_series = (cumulative - running_max) / running_max
        max_drawdown_pct = float(drawdown_series.min() * 100)
        negative_drawdowns = drawdown_series[drawdown_series < 0]
        expected_drawdown_pct = float(negative_drawdowns.mean() * 100) if len(negative_drawdowns) > 0 else 0.0

        negative_returns = portfolio_returns[portfolio_returns < 0]
        downside_risk_pct = (
            float(np.std(negative_returns) * np.sqrt(trading_days) * 100) if len(negative_returns) > 1 else 0.0
        )

        concentration_risk = _concentration_risk(weights_by_symbol)

        return RiskAnalytics(
            volatility_pct=volatility_pct, beta=beta, correlation_matrix=correlation_matrix,
            diversification_score=diversification_score, var_95_pct=var_pct, cvar_95_pct=cvar_pct,
            max_drawdown_pct=max_drawdown_pct, expected_drawdown_pct=expected_drawdown_pct,
            downside_risk_pct=downside_risk_pct, concentration_risk=concentration_risk,
        )

    def _beta(self, portfolio_returns: np.ndarray, dates: pd.Index) -> Optional[float]:
        try:
            benchmark_returns = self.price_service.get_returns(
                [self.config.benchmark_symbol], lookback_days=self.config.lookback_days,
            )
        except InsufficientPriceDataError:
            return None

        benchmark_symbol = self.config.benchmark_symbol.upper()
        if benchmark_symbol not in benchmark_returns.columns:
            return None

        combined = pd.DataFrame(
            {"portfolio": pd.Series(portfolio_returns, index=dates), "benchmark": benchmark_returns[benchmark_symbol]}
        ).dropna()
        if len(combined) < 2:
            return None

        variance = float(combined["benchmark"].var())
        if variance <= 0:
            return None
        covariance = float(combined["portfolio"].cov(combined["benchmark"]))
        return covariance / variance
