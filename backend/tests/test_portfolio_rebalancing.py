"""Tests for portfolio/rebalancing.py (requirement 5). Real PostgreSQL;
deterministic fake current-price fetcher."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from portfolio.analytics import PositionAnalyticsService
from portfolio.config import PortfolioConfig
from portfolio.models import RebalanceAction, RebalanceTrigger
from portfolio.prices import PriceService
from portfolio.rebalancing import RebalancingService
from portfolio.repository import PortfolioRepository
from portfolio.service import PortfolioService

_OWNER_PREFIX = "rebal-test-owner"
_CURRENT_PRICES = {"AAPL": 200.0, "MSFT": 400.0, "GOOGL": 150.0}


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


@pytest.fixture
def rebalancing_service(analytics_service):
    return RebalancingService(position_analytics_service=analytics_service)


def test_manual_plan_generates_trades_for_any_drift(portfolio_service, rebalancing_service):
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-manual", name="Manual")
    portfolio_service.deposit(portfolio.id, 10000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 10, 150.0)  # 2000 current value / 10000 total = 20%

    plan = rebalancing_service.build_plan(portfolio.id, {"AAPL": 50.0}, trigger=RebalanceTrigger.MANUAL)
    assert plan.needs_rebalancing is True
    assert len(plan.trades) == 1
    trade = plan.trades[0]
    assert trade.symbol == "AAPL"
    assert trade.action == RebalanceAction.BUY
    assert trade.target_weight_pct == 50.0


def test_threshold_trigger_ignores_drift_within_tolerance(portfolio_service, rebalancing_service):
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-threshold", name="Threshold")
    portfolio_service.deposit(portfolio.id, 10000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 10, 150.0)  # weight ~20%

    plan = rebalancing_service.build_plan(
        portfolio.id, {"AAPL": 22.0}, trigger=RebalanceTrigger.THRESHOLD, threshold_pct=5.0,
    )
    assert plan.needs_rebalancing is False
    assert plan.trades == []


def test_threshold_trigger_generates_trades_when_drift_exceeds_threshold(portfolio_service, rebalancing_service):
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-threshold-exceed", name="ThresholdExceed")
    portfolio_service.deposit(portfolio.id, 10000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 10, 150.0)  # weight ~20%

    plan = rebalancing_service.build_plan(
        portfolio.id, {"AAPL": 60.0}, trigger=RebalanceTrigger.THRESHOLD, threshold_pct=5.0,
    )
    assert plan.needs_rebalancing is True
    assert plan.trades[0].action == RebalanceAction.BUY


def test_target_symbol_not_currently_held_produces_a_buy(portfolio_service, rebalancing_service):
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-new-symbol", name="NewSymbol")
    portfolio_service.deposit(portfolio.id, 10000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 10, 150.0)

    plan = rebalancing_service.build_plan(portfolio.id, {"AAPL": 20.0, "GOOGL": 20.0}, trigger=RebalanceTrigger.MANUAL)
    googl_trade = next(trade for trade in plan.trades if trade.symbol == "GOOGL")
    assert googl_trade.action == RebalanceAction.BUY
    assert googl_trade.current_weight_pct == 0.0


def test_overweight_target_produces_a_sell(portfolio_service, rebalancing_service):
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-sell", name="Sell")
    portfolio_service.deposit(portfolio.id, 10000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 40, 150.0)  # 6000/10000 = 60%

    plan = rebalancing_service.build_plan(portfolio.id, {"AAPL": 10.0}, trigger=RebalanceTrigger.MANUAL)
    assert plan.trades[0].action == RebalanceAction.SELL


def test_total_estimated_fees_matches_sum_of_trade_fees(portfolio_service, rebalancing_service):
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-fees", name="Fees")
    portfolio_service.deposit(portfolio.id, 10000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 10, 150.0)

    plan = rebalancing_service.build_plan(
        portfolio.id, {"AAPL": 50.0}, trigger=RebalanceTrigger.MANUAL, fee_rate_pct=1.0,
    )
    assert plan.total_estimated_fees == pytest.approx(sum(trade.estimated_fee for trade in plan.trades))


def test_is_scheduled_rebalance_due_when_never_rebalanced(rebalancing_service):
    assert rebalancing_service.is_scheduled_rebalance_due(None) is True


def test_is_scheduled_rebalance_due_respects_interval(rebalancing_service):
    recent = datetime.now(timezone.utc) - timedelta(days=1)
    old = datetime.now(timezone.utc) - timedelta(days=60)
    assert rebalancing_service.is_scheduled_rebalance_due(recent, interval_days=30) is False
    assert rebalancing_service.is_scheduled_rebalance_due(old, interval_days=30) is True


def test_service_defaults_to_real_dependencies():
    service = RebalancingService()
    assert isinstance(service.position_analytics_service, PositionAnalyticsService)
