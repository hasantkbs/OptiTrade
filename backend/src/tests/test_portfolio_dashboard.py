"""Tests for portfolio/dashboard.py (requirement 9). Real PostgreSQL;
deterministic fake price/history fetchers."""
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from portfolio.analytics import PositionAnalyticsService
from portfolio.config import PortfolioConfig
from portfolio.dashboard import PortfolioDashboardService
from portfolio.prices import PriceService
from portfolio.repository import PortfolioRepository
from portfolio.service import PortfolioService

_OWNER_PREFIX = "dash-test-owner"
_CURRENT_PRICES = {"AAPL": 200.0}


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
    config = PortfolioConfig(redis_host="localhost", redis_port=6379, redis_db=15, price_cache_ttl_seconds=60, lookback_days=120)
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
def dashboard_service(portfolio_service):
    analytics_service = PositionAnalyticsService(portfolio_service=portfolio_service)
    return PortfolioDashboardService(portfolio_service=portfolio_service, position_analytics_service=analytics_service)


def test_dashboard_for_a_cash_only_portfolio_has_no_positions_or_risk(portfolio_service, dashboard_service):
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-cash-only", name="CashOnly")
    portfolio_service.deposit(portfolio.id, 5000.0)

    dashboard = dashboard_service.build(portfolio.id)
    assert dashboard.cash_balance == 5000.0
    assert dashboard.total_value == 5000.0
    assert dashboard.positions == []
    assert dashboard.risk is None
    assert dashboard.allocation.cash_weight_pct == 100.0


def test_dashboard_assembles_positions_allocation_risk_and_recommendations(portfolio_service, dashboard_service):
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-full", name="Full")
    portfolio_service.deposit(portfolio.id, 10000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 40, 150.0)  # overweight on purpose

    dashboard = dashboard_service.build(portfolio.id, target_weights_pct={"AAPL": 20.0})
    assert len(dashboard.positions) == 1
    assert dashboard.positions[0].symbol == "AAPL"
    assert "AAPL" in dashboard.allocation.by_symbol_pct
    assert dashboard.risk is not None
    assert dashboard.risk.concentration_risk == pytest.approx(1.0)
    assert len(dashboard.recommendations) > 0
    assert dashboard.unrealized_pnl == pytest.approx(dashboard.positions[0].unrealized_pnl)
    assert dashboard.total_value == pytest.approx(
        portfolio_service.get_cash_balance(portfolio.id) + dashboard.positions[0].current_value
    )


def test_service_defaults_to_real_dependencies():
    service = PortfolioDashboardService()
    assert isinstance(service.portfolio_service, PortfolioService)
