"""Tests for portfolio/scenarios.py (Scenario Analysis, requirement 6).
Real PostgreSQL; deterministic fake price/history fetchers."""
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from portfolio.analytics import PositionAnalyticsService
from portfolio.config import PortfolioConfig
from portfolio.exceptions import InsufficientPriceDataError
from portfolio.models import ScenarioType
from portfolio.prices import PriceService
from portfolio.repository import PortfolioRepository
from portfolio.scenarios import ScenarioAnalysisService
from portfolio.service import PortfolioService

_OWNER_PREFIX = "scenario-test-owner"
_CURRENT_PRICES = {"AAPL": 200.0, "GARAN.IS": 60.0}


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
        monte_carlo_simulations=500,
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
def scenario_service(analytics_service, price_service):
    return ScenarioAnalysisService(position_analytics_service=analytics_service, config=price_service.config)


@pytest.fixture
def funded_portfolio(portfolio_service):
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-funded", name="Funded")
    portfolio_service.deposit(portfolio.id, 10000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 10, 150.0)
    return portfolio


def test_scenario_raises_for_a_portfolio_with_no_positions(portfolio_service, scenario_service):
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-empty", name="Empty")
    with pytest.raises(InsufficientPriceDataError):
        scenario_service.market_crash(portfolio.id)


def test_market_crash_applies_uniform_drop_to_equity_only(portfolio_service, scenario_service, funded_portfolio):
    cash = portfolio_service.get_cash_balance(funded_portfolio.id)
    result = scenario_service.market_crash(funded_portfolio.id, drop_pct=30.0)
    assert result.scenario_type == ScenarioType.MARKET_CRASH
    assert result.per_position_impact_pct["AAPL"] == pytest.approx(-30.0)
    equity_value = 10 * 200.0
    expected_after = cash + equity_value * 0.7
    assert result.portfolio_value_after == pytest.approx(expected_after)
    assert result.pnl < 0


def test_volatility_shock_scales_with_multiplier(portfolio_service, scenario_service, funded_portfolio):
    baseline = scenario_service.volatility_shock(funded_portfolio.id, volatility_multiplier=1.0)
    doubled = scenario_service.volatility_shock(funded_portfolio.id, volatility_multiplier=2.0)
    assert doubled.details["shocked_daily_volatility_pct"] == pytest.approx(
        2 * baseline.details["shocked_daily_volatility_pct"]
    )
    assert doubled.pnl_pct <= baseline.pnl_pct  # a bigger shock is a bigger (more negative) loss


def test_interest_rate_shock_hurts_tech_more_than_finance(portfolio_service, scenario_service):
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-rate", name="RateShock")
    portfolio_service.deposit(portfolio.id, 20000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 10, 150.0)       # TECH
    portfolio_service.buy(portfolio.id, "GARAN.IS", 50, 40.0)    # FINANCE

    result = scenario_service.interest_rate_shock(portfolio.id, rate_change_bps=100.0)
    assert result.per_position_impact_pct["AAPL"] < result.per_position_impact_pct["GARAN.IS"]


def test_monte_carlo_simulation_reports_var_cvar_and_prob_profit(scenario_service, funded_portfolio):
    result = scenario_service.monte_carlo_simulation(funded_portfolio.id, n_simulations=500, horizon_days=20)
    assert result.scenario_type == ScenarioType.MONTE_CARLO
    assert result.details["n_simulations"] == 500
    assert result.details["horizon_days"] == 20
    assert result.details["var_95_pct"] <= 0.0
    assert result.details["cvar_95_pct"] <= result.details["var_95_pct"] + 1e-6
    assert 0.0 <= result.details["prob_profit_pct"] <= 100.0


def test_service_defaults_to_real_dependencies():
    service = ScenarioAnalysisService()
    assert isinstance(service.position_analytics_service, PositionAnalyticsService)
