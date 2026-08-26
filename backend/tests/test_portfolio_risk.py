"""Tests for portfolio/risk.py (Risk Analytics, requirement 3). Real
PostgreSQL; deterministic fake price/history fetchers (seeded per
symbol) so volatility/correlation/VaR/etc. are reproducible."""
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from portfolio.analytics import PositionAnalyticsService
from portfolio.config import PortfolioConfig
from portfolio.exceptions import InsufficientPriceDataError
from portfolio.prices import PriceService
from portfolio.repository import PortfolioRepository
from portfolio.risk import RiskAnalyticsService
from portfolio.service import PortfolioService

_OWNER_PREFIX = "risk-test-owner"
_CURRENT_PRICES = {"AAPL": 200.0, "MSFT": 350.0, "^GSPC": 5000.0}


def _fake_current_price_fetcher(symbol, period="5d"):
    price = _CURRENT_PRICES.get(symbol)
    if price is None:
        return pd.DataFrame()
    dates = pd.date_range(end=datetime.now(timezone.utc), periods=5, freq="D", tz="UTC")
    return pd.DataFrame({"Close": [price] * 5}, index=dates)


def _fake_history_fetcher(symbol, start, end):
    base_price = _CURRENT_PRICES.get(symbol, 100.0)
    dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
    seed = sum(ord(character) for character in symbol) % (2 ** 31)
    rng = np.random.RandomState(seed)
    daily_returns = rng.normal(0.0004, 0.015, size=len(dates))
    prices = base_price * np.cumprod(1 + daily_returns)
    return pd.DataFrame({"Close": prices}, index=dates)


@pytest.fixture
def repository():
    repo = PortfolioRepository()
    yield repo
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM portfolio_transactions WHERE portfolio_id IN "
                "(SELECT id FROM portfolio_portfolios WHERE owner LIKE %s)", (f"{_OWNER_PREFIX}%",),
            )
            cur.execute("DELETE FROM portfolio_portfolios WHERE owner LIKE %s", (f"{_OWNER_PREFIX}%",))
    finally:
        repo._pool.putconn(conn)


@pytest.fixture
def price_service():
    config = PortfolioConfig(
        redis_host="localhost", redis_port=6379, redis_db=15, price_cache_ttl_seconds=60, lookback_days=120,
    )
    service = PriceService(
        config=config, current_price_fetcher=_fake_current_price_fetcher, history_fetcher=_fake_history_fetcher,
    )
    service._client.flushdb()
    yield service
    service._client.flushdb()


@pytest.fixture
def portfolio_service(repository, price_service):
    return PortfolioService(repository=repository, price_service=price_service)


@pytest.fixture
def analytics_service(portfolio_service):
    return PositionAnalyticsService(portfolio_service=portfolio_service)


@pytest.fixture
def risk_service(analytics_service):
    return RiskAnalyticsService(position_analytics_service=analytics_service)


def test_analyze_raises_for_a_portfolio_with_no_positions(portfolio_service, risk_service):
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-empty", name="Empty")
    with pytest.raises(InsufficientPriceDataError):
        risk_service.analyze(portfolio.id)


def test_single_position_has_zero_diversification_and_full_concentration(portfolio_service, risk_service, analytics_service):
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-single", name="Single")
    portfolio_service.deposit(portfolio.id, 10000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 10, 150.0)

    positions = analytics_service.analyze_positions(portfolio.id)
    risk = risk_service.analyze(portfolio.id, positions)

    assert risk.diversification_score == 0.0
    assert risk.concentration_risk == pytest.approx(1.0)
    assert risk.correlation_matrix == {"AAPL": {"AAPL": 1.0}}
    assert risk.volatility_pct >= 0.0
    assert risk.max_drawdown_pct <= 0.0
    assert risk.downside_risk_pct >= 0.0


def test_two_equal_positions_have_hhi_near_half(portfolio_service, risk_service, analytics_service):
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-two", name="Two")
    portfolio_service.deposit(portfolio.id, 20000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 10, 150.0)   # 1500
    portfolio_service.buy(portfolio.id, "MSFT", 6, 250.0)    # 1500 (roughly equal dollar amounts)

    positions = analytics_service.analyze_positions(portfolio.id)
    risk = risk_service.analyze(portfolio.id, positions)

    assert 0.3 < risk.concentration_risk < 0.7
    assert set(risk.correlation_matrix.keys()) == {"AAPL", "MSFT"}
    assert risk.correlation_matrix["AAPL"]["AAPL"] == pytest.approx(1.0)


def test_beta_is_none_when_benchmark_has_no_data(portfolio_service, analytics_service):
    config = PortfolioConfig(
        redis_host="localhost", redis_port=6379, redis_db=15, price_cache_ttl_seconds=60, lookback_days=120,
        benchmark_symbol="NO-SUCH-BENCHMARK",
    )
    price_service_no_benchmark = PriceService(
        config=config, current_price_fetcher=_fake_current_price_fetcher, history_fetcher=_fake_history_fetcher,
    )
    risk_service_no_benchmark = RiskAnalyticsService(
        position_analytics_service=analytics_service, price_service=price_service_no_benchmark, config=config,
    )
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-nobench", name="NoBenchmark")
    portfolio_service.deposit(portfolio.id, 10000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 5, 150.0)
    positions = analytics_service.analyze_positions(portfolio.id)
    risk = risk_service_no_benchmark.analyze(portfolio.id, positions)
    assert risk.beta is None


def test_service_defaults_to_real_dependencies():
    service = RiskAnalyticsService()
    assert isinstance(service.position_analytics_service, PositionAnalyticsService)
