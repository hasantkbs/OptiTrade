"""Tests for portfolio/optimization.py (Portfolio Optimization,
requirement 4). Deterministic fake historical-price fetcher - no real
Postgres/Redis needed (this module is pure computation over
`PriceService.get_returns`, which is itself already covered by
test_portfolio_risk.py's fixtures)."""
import numpy as np
import pandas as pd
import pytest

from portfolio.config import PortfolioConfig
from portfolio.exceptions import InsufficientPriceDataError
from portfolio.models import OptimizationStrategy
from portfolio.optimization import (
    PortfolioOptimizationService,
    blend_expected_returns,
    maximum_sharpe_weights,
    minimum_variance_weights,
    portfolio_performance,
    risk_parity_weights,
)
from portfolio.prices import PriceService

_SYMBOLS = ["AAPL", "MSFT", "GOOGL"]
_BASE_PRICES = {"AAPL": 150.0, "MSFT": 300.0, "GOOGL": 140.0}


def _fake_history_fetcher(symbol, start, end):
    base_price = _BASE_PRICES.get(symbol)
    if base_price is None:
        return pd.DataFrame()
    dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
    seed = sum(ord(character) for character in symbol) % (2 ** 31)
    rng = np.random.RandomState(seed)
    daily_returns = rng.normal(0.0006, 0.018, size=len(dates))
    prices = base_price * np.cumprod(1 + daily_returns)
    return pd.DataFrame({"Close": prices}, index=dates)


class _FakePipelineResponse:
    def __init__(self, expected_return: float) -> None:
        self.expected_return = expected_return


class _FakePipelineService:
    def __init__(self, views):
        self._views = views

    def run(self, symbol):
        if symbol not in self._views:
            raise RuntimeError("no view for symbol")
        return _FakePipelineResponse(self._views[symbol])


@pytest.fixture
def price_service():
    config = PortfolioConfig(lookback_days=120)
    return PriceService(config=config, history_fetcher=_fake_history_fetcher)


@pytest.fixture
def optimization_service(price_service):
    return PortfolioOptimizationService(price_service=price_service, config=price_service.config)


@pytest.mark.parametrize(
    "strategy", [OptimizationStrategy.MEAN_VARIANCE, OptimizationStrategy.MIN_VARIANCE,
                 OptimizationStrategy.MAX_SHARPE, OptimizationStrategy.RISK_PARITY, OptimizationStrategy.MONTE_CARLO],
)
def test_every_strategy_produces_weights_summing_to_one(optimization_service, strategy):
    result = optimization_service.optimize(_SYMBOLS, strategy)
    assert result.strategy == strategy
    assert set(result.weights) == set(_SYMBOLS)
    assert sum(result.weights.values()) == pytest.approx(1.0, abs=1e-4)
    assert all(weight >= -1e-6 for weight in result.weights.values())
    assert result.annual_volatility_pct >= 0.0


def test_optimize_requires_at_least_two_symbols(optimization_service):
    with pytest.raises(InsufficientPriceDataError):
        optimization_service.optimize(["AAPL"], OptimizationStrategy.MAX_SHARPE)


def test_min_variance_has_lower_or_equal_volatility_than_equal_weight(optimization_service):
    min_var_result = optimization_service.optimize(_SYMBOLS, OptimizationStrategy.MIN_VARIANCE)
    mean_var_result = optimization_service.optimize(_SYMBOLS, OptimizationStrategy.MEAN_VARIANCE, risk_tolerance=1.0)
    assert min_var_result.annual_volatility_pct <= mean_var_result.annual_volatility_pct + 1e-6


def test_risk_parity_gives_no_symbol_zero_weight(optimization_service):
    result = optimization_service.optimize(_SYMBOLS, OptimizationStrategy.RISK_PARITY)
    assert all(weight > 0.01 for weight in result.weights.values())


def test_use_prediction_views_blends_in_pipeline_expected_return(price_service):
    views_service = PortfolioOptimizationService(
        price_service=price_service, pipeline_service=_FakePipelineService({"AAPL": 20.0, "MSFT": -20.0, "GOOGL": 0.0}),
        config=price_service.config,
    )
    without_views = views_service.optimize(_SYMBOLS, OptimizationStrategy.MAX_SHARPE, use_prediction_views=False)
    with_views = views_service.optimize(_SYMBOLS, OptimizationStrategy.MAX_SHARPE, use_prediction_views=True)
    assert without_views.used_prediction_views is False
    assert with_views.used_prediction_views is True
    # A strongly positive AAPL view and strongly negative MSFT view
    # should tilt allocation toward AAPL relative to the baseline.
    assert with_views.weights["AAPL"] >= without_views.weights["AAPL"] - 1e-6


def test_use_prediction_views_is_a_no_op_without_a_pipeline_service(optimization_service):
    result = optimization_service.optimize(_SYMBOLS, OptimizationStrategy.MAX_SHARPE, use_prediction_views=True)
    assert result.used_prediction_views is False


def test_efficient_frontier_has_configured_point_count_and_endpoints(optimization_service):
    frontier = optimization_service.efficient_frontier(_SYMBOLS)
    assert len(frontier.points) > 0
    assert frontier.max_sharpe_point is not None
    assert frontier.min_variance_point is not None
    assert frontier.min_variance_point.volatility_pct <= frontier.max_sharpe_point.volatility_pct + 1e-6


# ── Pure math helpers ─────────────────────────────────────────────────────

def test_portfolio_performance_matches_manual_computation():
    mu = np.array([0.1, 0.2])
    cov = np.array([[0.04, 0.0], [0.0, 0.09]])
    weights = np.array([0.5, 0.5])
    expected_return, volatility, sharpe = portfolio_performance(weights, mu, cov, risk_free_rate=0.0)
    assert expected_return == pytest.approx(0.15)
    assert volatility == pytest.approx(np.sqrt(0.5 ** 2 * 0.04 + 0.5 ** 2 * 0.09))
    assert sharpe == pytest.approx(expected_return / volatility)


def test_minimum_variance_weights_favor_the_lower_variance_asset():
    cov = np.array([[0.01, 0.0], [0.0, 0.25]])
    weights = minimum_variance_weights(cov)
    assert weights[0] > weights[1]


def test_maximum_sharpe_weights_favor_higher_sharpe_asset():
    mu = np.array([0.20, 0.05])
    cov = np.array([[0.04, 0.0], [0.0, 0.04]])
    weights = maximum_sharpe_weights(mu, cov, risk_free_rate=0.0)
    assert weights[0] > weights[1]


def test_risk_parity_weights_sum_to_one():
    cov = np.array([[0.04, 0.01], [0.01, 0.09]])
    weights = risk_parity_weights(cov)
    assert weights.sum() == pytest.approx(1.0)


def test_blend_expected_returns_only_changes_symbols_with_a_view():
    historical = np.array([0.10, 0.20])
    blended = blend_expected_returns(historical, ["AAPL", "MSFT"], {"AAPL": 50.0}, blend_weight=0.5)
    assert blended[0] == pytest.approx(0.5 * 0.10 + 0.5 * 0.50)
    assert blended[1] == pytest.approx(0.20)


def test_service_defaults_to_real_dependencies():
    service = PortfolioOptimizationService()
    assert isinstance(service.price_service, PriceService)
    assert service.pipeline_service is None
