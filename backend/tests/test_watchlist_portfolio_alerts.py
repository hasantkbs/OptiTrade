"""Tests for watchlist/portfolio_alerts.py. Real PostgreSQL (portfolio
persistence); a deterministic fake current-price fetcher for
reproducible allocation/risk assertions."""
from datetime import datetime, timezone

import pandas as pd
import pytest

from portfolio.analytics import PositionAnalyticsService
from portfolio.config import PortfolioConfig
from portfolio.prices import PriceService
from portfolio.repository import PortfolioRepository
from portfolio.risk import RiskAnalyticsService
from portfolio.service import PortfolioService
from watchlist.exceptions import InsufficientAlertDataError, InvalidAlertError
from watchlist.models import Alert, AlertCategory, AlertType
from watchlist.portfolio_alerts import PortfolioAlertEvaluator

_OWNER_PREFIX = "wl-portfolio-alert-owner"
_CURRENT_PRICES = {"AAPL": 200.0, "MSFT": 350.0}


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
def evaluator(analytics_service):
    return PortfolioAlertEvaluator(
        position_analytics_service=analytics_service,
        risk_analytics_service=RiskAnalyticsService(position_analytics_service=analytics_service),
    )


def _alert(alert_type, portfolio_id, parameters=None, symbol=None):
    alert = Alert(
        owner="wl-portfolio-alert-owner", portfolio_id=portfolio_id, symbol=symbol,
        category=AlertCategory.PORTFOLIO, alert_type=alert_type, parameters=parameters or {},
    )
    alert.id = 1
    return alert


def test_allocation_exceeded_triggers_for_overweight_position(portfolio_service, evaluator):
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-alloc", name="Alloc")
    portfolio_service.deposit(portfolio.id, 10000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 40, 150.0)  # 6000/10000 = 60%

    event, state = evaluator.evaluate(_alert(AlertType.PORTFOLIO_ALLOCATION_EXCEEDED, portfolio.id))
    assert event is not None
    assert event.symbol == "AAPL"
    # cash after buy = 10000 - 6000 = 4000; position value = 40 * 200 = 8000; total = 12000
    assert state["max_weight_pct"] == pytest.approx(8000 / 12000 * 100)


def test_allocation_not_exceeded_for_balanced_portfolio(portfolio_service, evaluator):
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-balanced", name="Balanced")
    portfolio_service.deposit(portfolio.id, 100000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 5, 150.0)  # tiny weight

    event, _ = evaluator.evaluate(_alert(AlertType.PORTFOLIO_ALLOCATION_EXCEEDED, portfolio.id))
    assert event is None


def test_allocation_check_scoped_to_a_specific_symbol(portfolio_service, evaluator):
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-symbol-scoped", name="Scoped")
    portfolio_service.deposit(portfolio.id, 10000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 40, 150.0)
    portfolio_service.buy(portfolio.id, "MSFT", 1, 100.0)

    event, _ = evaluator.evaluate(_alert(AlertType.PORTFOLIO_ALLOCATION_EXCEEDED, portfolio.id, symbol="MSFT"))
    assert event is None  # MSFT itself is a tiny position, even though AAPL is overweight


def test_concentration_alert_triggers_for_single_position_portfolio(portfolio_service, evaluator):
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-concentration", name="Concentration")
    portfolio_service.deposit(portfolio.id, 10000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 10, 150.0)

    event, state = evaluator.evaluate(_alert(AlertType.PORTFOLIO_CONCENTRATION, portfolio.id))
    assert event is not None
    assert state["concentration_risk"] == pytest.approx(1.0)


def test_var_exceeded_uses_negative_threshold_convention(portfolio_service, evaluator):
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-var", name="VaR")
    portfolio_service.deposit(portfolio.id, 10000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 10, 150.0)

    # An absurdly loose (very negative) threshold should never be breached.
    event, state = evaluator.evaluate(
        _alert(AlertType.PORTFOLIO_VAR_EXCEEDED, portfolio.id, parameters={"threshold": -1000.0})
    )
    assert event is None
    assert "var_95_pct" in state


def test_raises_for_portfolio_with_no_positions(portfolio_service, evaluator):
    portfolio = portfolio_service.create_portfolio(owner=f"{_OWNER_PREFIX}-empty", name="Empty")
    with pytest.raises(InsufficientAlertDataError):
        evaluator.evaluate(_alert(AlertType.PORTFOLIO_ALLOCATION_EXCEEDED, portfolio.id))


def test_raises_without_portfolio_id():
    evaluator = PortfolioAlertEvaluator()
    alert = Alert(owner="x", category=AlertCategory.PORTFOLIO, alert_type=AlertType.PORTFOLIO_ALLOCATION_EXCEEDED)
    alert.id = 1
    with pytest.raises(InvalidAlertError):
        evaluator.evaluate(alert)


def test_raises_for_wrong_category(evaluator):
    alert = _alert(AlertType.PORTFOLIO_ALLOCATION_EXCEEDED, 1)
    alert.category = AlertCategory.PRICE
    with pytest.raises(InvalidAlertError):
        evaluator.evaluate(alert)


def test_service_defaults_to_real_dependencies():
    evaluator = PortfolioAlertEvaluator()
    assert isinstance(evaluator.position_analytics_service, PositionAnalyticsService)
