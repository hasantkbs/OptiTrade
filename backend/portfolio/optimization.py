"""
OptiTrade Portfolio Intelligence Platform — Portfolio Optimization
(requirement 4).

Every strategy operates on the same annualized (mu, covariance) pair
derived once from `PriceService.get_returns` - no duplicated
return/covariance computation across strategies. "Reuse existing
Prediction Pipeline outputs": `use_prediction_views=True` tilts the
historical mean return per symbol toward `pipeline.service.
PipelineService.run(symbol).expected_return` - the Decision Engine's
own already-computed, ML-model-inclusive forward view (see
`pipeline.service.PipelineService`) - rather than deriving a second,
competing forecast.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from core.structured_logging import STATUS_ERROR, log_event
from portfolio.config import PortfolioConfig
from portfolio.exceptions import InsufficientPriceDataError
from portfolio.models import EfficientFrontier, EfficientFrontierPoint, OptimizationResult, OptimizationStrategy
from portfolio.prices import PriceService

logger = logging.getLogger(__name__)


def _annualize(returns: pd.DataFrame, trading_days_per_year: int) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    symbols = list(returns.columns)
    mu = returns.mean().to_numpy() * trading_days_per_year
    cov = returns.cov().to_numpy() * trading_days_per_year
    return mu, cov, symbols


def blend_expected_returns(
    historical_mu: np.ndarray, symbols: List[str], prediction_views: Dict[str, float], blend_weight: float,
) -> np.ndarray:
    """`prediction_views[symbol]` is a Decision Engine/Pipeline
    `expected_return` (a percentage directional-strength score, not a
    strictly-annualized forecast) - blended in as a fractional tilt
    rather than treated as a rigorously equivalent replacement for the
    historical annualized mean."""
    blended = historical_mu.copy()
    for index, symbol in enumerate(symbols):
        if symbol in prediction_views:
            view_as_fraction = prediction_views[symbol] / 100.0
            blended[index] = (1.0 - blend_weight) * historical_mu[index] + blend_weight * view_as_fraction
    return blended


def portfolio_performance(
    weights: np.ndarray, mu: np.ndarray, cov: np.ndarray, risk_free_rate: float,
) -> Tuple[float, float, float]:
    expected_return = float(weights @ mu)
    volatility = float(np.sqrt(max(0.0, weights @ cov @ weights)))
    sharpe = (expected_return - risk_free_rate) / volatility if volatility > 0 else 0.0
    return expected_return, volatility, sharpe


def _equal_weights(n: int) -> np.ndarray:
    return np.ones(n) / n


def minimum_variance_weights(cov: np.ndarray) -> np.ndarray:
    n = cov.shape[0]
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    bounds = [(0.0, 1.0)] * n
    result = minimize(
        lambda w: float(w @ cov @ w), x0=_equal_weights(n), method="SLSQP", bounds=bounds, constraints=constraints,
    )
    return result.x if result.success else _equal_weights(n)


def maximum_sharpe_weights(mu: np.ndarray, cov: np.ndarray, risk_free_rate: float) -> np.ndarray:
    n = len(mu)

    def negative_sharpe(w: np.ndarray) -> float:
        expected_return = float(w @ mu)
        volatility = float(np.sqrt(max(1e-12, w @ cov @ w)))
        return -(expected_return - risk_free_rate) / volatility

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    bounds = [(0.0, 1.0)] * n
    result = minimize(negative_sharpe, x0=_equal_weights(n), method="SLSQP", bounds=bounds, constraints=constraints)
    return result.x if result.success else _equal_weights(n)


def risk_parity_weights(cov: np.ndarray) -> np.ndarray:
    """Equal risk contribution: each asset contributes the same share
    of total portfolio variance, rather than the same capital weight."""
    n = cov.shape[0]

    def risk_contribution_error(w: np.ndarray) -> float:
        portfolio_variance = float(w @ cov @ w)
        marginal_contribution = cov @ w
        contribution = w * marginal_contribution
        target = portfolio_variance / n
        return float(np.sum((contribution - target) ** 2))

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    bounds = [(1e-6, 1.0)] * n
    result = minimize(
        risk_contribution_error, x0=_equal_weights(n), method="SLSQP", bounds=bounds, constraints=constraints,
    )
    weights = result.x if result.success else _equal_weights(n)
    return weights / weights.sum()


def mean_variance_weights(mu: np.ndarray, cov: np.ndarray, risk_tolerance: float) -> np.ndarray:
    """Classic Markowitz utility maximization: `risk_tolerance` in
    (0, 1] trades off expected return against variance - 1.0 behaves
    like maximum-Sharpe-seeking, values near 0 behave like minimum-
    variance."""
    n = len(mu)
    risk_aversion = 1.0 / max(risk_tolerance, 1e-6)

    def negative_utility(w: np.ndarray) -> float:
        expected_return = float(w @ mu)
        variance = float(w @ cov @ w)
        return -(expected_return - 0.5 * risk_aversion * variance)

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    bounds = [(0.0, 1.0)] * n
    result = minimize(negative_utility, x0=_equal_weights(n), method="SLSQP", bounds=bounds, constraints=constraints)
    return result.x if result.success else _equal_weights(n)


def monte_carlo_allocation_weights(
    mu: np.ndarray, cov: np.ndarray, risk_free_rate: float, n_simulations: int, seed: int = 42,
) -> np.ndarray:
    """Random-search allocation: samples `n_simulations` Dirichlet
    weight vectors and keeps the best-Sharpe one - a genuinely
    different (stochastic, not gradient-based) allocation method from
    the scipy.optimize-based strategies above, matching this
    requirement's own distinct "Monte Carlo Allocation" bullet."""
    n = len(mu)
    rng = np.random.default_rng(seed)
    best_weights = _equal_weights(n)
    best_sharpe = -np.inf
    for _ in range(n_simulations):
        candidate = rng.dirichlet(np.ones(n))
        _, _, sharpe = portfolio_performance(candidate, mu, cov, risk_free_rate)
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_weights = candidate
    return best_weights


_STRATEGY_FUNCS = {
    OptimizationStrategy.MIN_VARIANCE: lambda mu, cov, cfg: minimum_variance_weights(cov),
    OptimizationStrategy.MAX_SHARPE: lambda mu, cov, cfg: maximum_sharpe_weights(mu, cov, cfg.risk_free_rate),
    OptimizationStrategy.RISK_PARITY: lambda mu, cov, cfg: risk_parity_weights(cov),
    OptimizationStrategy.MONTE_CARLO: lambda mu, cov, cfg: monte_carlo_allocation_weights(
        mu, cov, cfg.risk_free_rate, cfg.monte_carlo_simulations,
    ),
}


class PortfolioOptimizationService:
    def __init__(
        self,
        price_service: Optional[PriceService] = None,
        pipeline_service=None,
        config: Optional[PortfolioConfig] = None,
    ) -> None:
        self.config = config or PortfolioConfig.from_env()
        self.price_service = price_service or PriceService(config=self.config)
        # Optional[pipeline.service.PipelineService] - not imported by
        # type here to avoid constructing one (expensive: it self-
        # registers/wires the whole production Pipeline) merely to type-
        # hint an optional dependency nobody may ever supply.
        self.pipeline_service = pipeline_service

    def optimize(
        self, symbols: List[str], strategy: OptimizationStrategy, risk_tolerance: float = 0.5,
        use_prediction_views: bool = False,
    ) -> OptimizationResult:
        mu, cov, available_symbols = self._mu_and_cov(symbols)
        used_views = False
        if use_prediction_views:
            views = self._prediction_views(available_symbols)
            if views:
                mu = blend_expected_returns(mu, available_symbols, views, self.config.prediction_view_blend_weight)
                used_views = True

        if strategy == OptimizationStrategy.MEAN_VARIANCE:
            weights = mean_variance_weights(mu, cov, risk_tolerance)
        else:
            weights = _STRATEGY_FUNCS[strategy](mu, cov, self.config)

        expected_return, volatility, sharpe = portfolio_performance(weights, mu, cov, self.config.risk_free_rate)
        return OptimizationResult(
            strategy=strategy, symbols=available_symbols,
            weights={symbol: float(weight) for symbol, weight in zip(available_symbols, weights)},
            expected_annual_return_pct=expected_return * 100, annual_volatility_pct=volatility * 100,
            sharpe_ratio=sharpe, used_prediction_views=used_views,
        )

    def efficient_frontier(self, symbols: List[str], use_prediction_views: bool = False) -> EfficientFrontier:
        mu, cov, available_symbols = self._mu_and_cov(symbols)
        if use_prediction_views:
            views = self._prediction_views(available_symbols)
            if views:
                mu = blend_expected_returns(mu, available_symbols, views, self.config.prediction_view_blend_weight)

        min_var_weights = minimum_variance_weights(cov)
        min_ret, _, _ = portfolio_performance(min_var_weights, mu, cov, self.config.risk_free_rate)
        max_ret = float(mu.max())

        points: List[EfficientFrontierPoint] = []
        n = len(mu)
        for target_return in np.linspace(min_ret, max(max_ret, min_ret), self.config.efficient_frontier_points):
            constraints = [
                {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
                {"type": "eq", "fun": lambda w, target=target_return: float(w @ mu) - target},
            ]
            result = minimize(
                lambda w: float(w @ cov @ w), x0=_equal_weights(n), method="SLSQP",
                bounds=[(0.0, 1.0)] * n, constraints=constraints,
            )
            if not result.success:
                continue
            expected_return, volatility, _ = portfolio_performance(result.x, mu, cov, self.config.risk_free_rate)
            points.append(
                EfficientFrontierPoint(
                    volatility_pct=volatility * 100, expected_return_pct=expected_return * 100,
                    weights={symbol: float(weight) for symbol, weight in zip(available_symbols, result.x)},
                )
            )

        max_sharpe_weights_vec = maximum_sharpe_weights(mu, cov, self.config.risk_free_rate)
        max_sharpe_return, max_sharpe_vol, _ = portfolio_performance(
            max_sharpe_weights_vec, mu, cov, self.config.risk_free_rate,
        )
        min_var_return, min_var_vol, _ = portfolio_performance(min_var_weights, mu, cov, self.config.risk_free_rate)

        return EfficientFrontier(
            symbols=available_symbols, points=points,
            max_sharpe_point=EfficientFrontierPoint(
                volatility_pct=max_sharpe_vol * 100, expected_return_pct=max_sharpe_return * 100,
                weights={symbol: float(weight) for symbol, weight in zip(available_symbols, max_sharpe_weights_vec)},
            ),
            min_variance_point=EfficientFrontierPoint(
                volatility_pct=min_var_vol * 100, expected_return_pct=min_var_return * 100,
                weights={symbol: float(weight) for symbol, weight in zip(available_symbols, min_var_weights)},
            ),
        )

    def _mu_and_cov(self, symbols: List[str]) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        if len(symbols) < 2:
            raise InsufficientPriceDataError("portfolio optimization requires at least 2 symbols")
        returns = self.price_service.get_returns(symbols, lookback_days=self.config.lookback_days)
        return _annualize(returns, self.config.trading_days_per_year)

    def _prediction_views(self, symbols: List[str]) -> Dict[str, float]:
        if self.pipeline_service is None:
            return {}
        views: Dict[str, float] = {}
        for symbol in symbols:
            try:
                response = self.pipeline_service.run(symbol)
                views[symbol] = response.expected_return
            except Exception as exc:
                log_event(
                    logger, component="portfolio", module="portfolio.optimization", operation="prediction_views",
                    status=STATUS_ERROR, symbol=symbol, error_type=type(exc).__name__, level=logging.WARNING,
                )
                continue
        return views
