"""Tests for portfolio/analytics.py (Position Analytics, requirement 2).
Real PostgreSQL; a deterministic fake current-price fetcher for
reproducible value/weight/P&L assertions."""
from datetime import datetime, timezone

import pandas as pd
import pytest

from portfolio.analytics import PositionAnalyticsService
from portfolio.config import PortfolioConfig
from portfolio.prices import PriceService
from portfolio.repository import PortfolioRepository
from portfolio.service import PortfolioService

_OWNER_PREFIX = "analytics-test-owner"
_CURRENT_PRICES = {"AAPL": 200.0, "GARAN.IS": 60.0}


def _fake_current_price_fetcher(symbol, period="5d"):
    price = _CURRENT_PRICES.get(symbol)
    if price is None:
        return pd.DataFrame()
    dates = pd.date_range(end=datetime.now(timezone.utc), periods=5, freq="D", tz="UTC")
    return pd.DataFrame({"Close": [price] * 5}, index=dates)


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
    config = PortfolioConfig(redis_host="localhost", redis_port=6379, redis_db=15, price_cache_ttl_seconds=60)
    service = PriceService(config=config, current_price_fetcher=_fake_current_price_fetcher)
    service._client.flushdb()
    yield service
    service._client.flushdb()


@pytest.fixture
def portfolio_service(repository, price_service):
    return PortfolioService(repository=repository, price_service=price_service)


@pytest.fixture
def analytics_service(portfolio_service):
    return PositionAnalyticsService(portfolio_service=portfolio_service)


def test_analyze_positions_is_empty_for_a_portfolio_with_no_holdings(portfolio_service, analytics_service):
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-empty", name="Empty")
    assert analytics_service.analyze_positions(portfolio.id) == []


def test_analyze_positions_computes_value_pnl_and_classification(portfolio_service, analytics_service):
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-basic", name="Basic")
    portfolio_service.deposit(portfolio.id, 10000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 10, 150.0)

    positions = analytics_service.analyze_positions(portfolio.id)
    assert len(positions) == 1
    position = positions[0]
    assert position.symbol == "AAPL"
    assert position.average_cost == 150.0
    assert position.current_price == 200.0
    assert position.cost_basis == pytest.approx(1500.0)
    assert position.current_value == pytest.approx(2000.0)
    assert position.unrealized_pnl == pytest.approx(500.0)
    assert position.unrealized_pnl_pct == pytest.approx(500.0 / 1500.0 * 100)
    assert position.sector == "TECH"
    assert position.country == "US"
    assert position.currency == "USD"
    # weight relative to TOTAL portfolio value (positions + remaining cash)
    total_value = (10000.0 - 1500.0) + 2000.0
    assert position.weight_pct == pytest.approx(2000.0 / total_value * 100)


def test_allocation_breakdown_aggregates_by_sector_country_currency(portfolio_service, analytics_service):
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-alloc", name="Alloc")
    portfolio_service.deposit(portfolio.id, 20000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 10, 150.0)
    portfolio_service.buy(portfolio.id, "GARAN.IS", 50, 40.0)

    positions = analytics_service.analyze_positions(portfolio.id)
    allocation = analytics_service.allocation_breakdown(portfolio.id, positions)

    assert set(allocation.by_symbol_pct) == {"AAPL", "GARAN.IS"}
    assert set(allocation.by_sector_pct) == {"TECH", "FINANCE"}
    assert set(allocation.by_country_pct) == {"US", "TR"}
    assert set(allocation.by_currency_pct) == {"USD", "TRY"}
    total_weight = sum(allocation.by_symbol_pct.values()) + allocation.cash_weight_pct
    assert total_weight == pytest.approx(100.0, abs=0.01)


def test_allocation_breakdown_recomputes_when_position_analytics_not_supplied(portfolio_service, analytics_service):
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-recompute", name="Recompute")
    portfolio_service.deposit(portfolio.id, 10000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 5, 150.0)
    allocation = analytics_service.allocation_breakdown(portfolio.id)
    assert "AAPL" in allocation.by_symbol_pct


def test_service_defaults_to_real_dependencies():
    service = PositionAnalyticsService()
    assert isinstance(service.portfolio_service, PortfolioService)
