"""Tests for dashboard/portfolio_dashboard.py. Real PostgreSQL/Redis throughout."""
import pytest

from dashboard.portfolio_dashboard import DashboardPortfolioService
from portfolio.dashboard import PortfolioDashboardService
from portfolio.repository import PortfolioRepository
from portfolio.service import PortfolioService

_OWNER_PREFIX = "dash-portfolio-test-owner"


@pytest.fixture
def portfolio_repo():
    repository = PortfolioRepository()
    yield repository
    conn = repository._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM portfolio_snapshots WHERE portfolio_id IN (SELECT id FROM portfolio_portfolios WHERE owner LIKE %s)", (f"{_OWNER_PREFIX}%",))
            cur.execute("DELETE FROM portfolio_transactions WHERE portfolio_id IN (SELECT id FROM portfolio_portfolios WHERE owner LIKE %s)", (f"{_OWNER_PREFIX}%",))
            cur.execute("DELETE FROM portfolio_portfolios WHERE owner LIKE %s", (f"{_OWNER_PREFIX}%",))
    finally:
        repository._pool.putconn(conn)


@pytest.fixture
def portfolio_service(portfolio_repo):
    return PortfolioService(repository=portfolio_repo)


@pytest.fixture
def service(portfolio_service):
    return DashboardPortfolioService(
        portfolio_dashboard_service=PortfolioDashboardService(portfolio_service=portfolio_service),
        portfolio_service=portfolio_service,
    )


def _owner(name: str) -> str:
    return f"{_OWNER_PREFIX}-{name}"


def test_build_includes_dashboard_and_sharpe(service, portfolio_service):
    portfolio = portfolio_service.create_portfolio(_owner("basic"), "Test Portfolio")
    portfolio_service.deposit(portfolio.id, 10000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 5, 150.0)

    view = service.build(portfolio.id)
    assert view.dashboard.portfolio_id == portfolio.id
    assert view.dashboard.total_value > 0
    assert view.sharpe_ratio is None  # fewer than 2 snapshots


def test_sharpe_computed_with_multiple_snapshots(service, portfolio_service):
    portfolio = portfolio_service.create_portfolio(_owner("sharpe"), "Sharpe Test")
    portfolio_service.deposit(portfolio.id, 10000.0)
    portfolio_service.buy(portfolio.id, "AAPL", 5, 150.0)
    portfolio_service.take_snapshot(portfolio.id)
    portfolio_service.buy(portfolio.id, "AAPL", 5, 155.0)
    portfolio_service.take_snapshot(portfolio.id)
    portfolio_service.buy(portfolio.id, "AAPL", 5, 145.0)
    portfolio_service.take_snapshot(portfolio.id)

    view = service.build(portfolio.id)
    assert view.sharpe_ratio is not None
