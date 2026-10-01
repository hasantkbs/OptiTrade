"""Tests for dashboard/service.py (top-level facade). Real Postgres/
Redis/portfolio/watchlist/paper_trading infra throughout."""
import pytest

from dashboard.models import ReportPeriod
from dashboard.repository import DashboardRepository
from dashboard.service import DashboardService
from paper_trading.exceptions import AccountNotFoundError
from paper_trading.models import PaperAccount
from paper_trading.repository import PaperTradingRepository
from portfolio.exceptions import PortfolioNotFoundError
from portfolio.repository import PortfolioRepository
from portfolio.service import PortfolioService
from watchlist.repository import WatchlistRepository
from watchlist.watchlist_service import WatchlistService

_OWNER_PREFIX = "dash-svc-test-owner"
_USER_ID_BASE = 9_990_000


@pytest.fixture
def repo():
    repository = DashboardRepository()
    yield repository
    repository.close()


@pytest.fixture
def service(repo):
    return DashboardService(repo)


def test_get_overview(service):
    metrics = service.get_overview()
    assert metrics.total_users >= 0


def test_get_engine_dashboard(service):
    view = service.get_engine_dashboard()
    assert isinstance(view.engines, list)


def test_get_model_dashboard(service):
    view = service.get_model_dashboard()
    assert isinstance(view.registry_entries, list)


def test_get_watchlist_dashboard(service):
    view = service.get_watchlist_dashboard("nobody@example.com")
    assert view.total_watchlists == 0


def test_get_learning_dashboard(service):
    view = service.get_learning_dashboard()
    assert isinstance(view.engine_rankings, list)


def test_get_alert_dashboard(service):
    view = service.get_alert_dashboard()
    assert view.active_alerts >= 0


def test_get_market_dashboard(service):
    view = service.get_market_dashboard(symbols=["AAPL"])
    assert isinstance(view.regime_distribution, dict)


def test_generate_report(service):
    report = service.generate_report(ReportPeriod.DAILY)
    assert report.period == ReportPeriod.DAILY


def test_get_portfolio_dashboard_real_portfolio(service):
    port_repo = PortfolioRepository()
    port_svc = PortfolioService(repository=port_repo)
    owner = f"{_OWNER_PREFIX}@example.com"
    portfolio = port_svc.create_portfolio(owner, "Facade Test Portfolio")
    port_svc.deposit(portfolio.id, 5000.0)

    dashboard_service = DashboardService(DashboardRepository())
    from dashboard.portfolio_dashboard import DashboardPortfolioService
    dashboard_service.portfolio_dashboard_service = DashboardPortfolioService(portfolio_service=port_svc)

    view = dashboard_service.get_portfolio_dashboard(portfolio.id)
    assert view.dashboard.portfolio_id == portfolio.id

    with pytest.raises(PortfolioNotFoundError):
        dashboard_service.get_portfolio_dashboard(999999999)

    conn = port_repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM portfolio_transactions WHERE portfolio_id = %s", (portfolio.id,))
            cur.execute("DELETE FROM portfolio_portfolios WHERE id = %s", (portfolio.id,))
    finally:
        port_repo._pool.putconn(conn)


def test_get_paper_trading_dashboard_real_account(service):
    pt_repo = PaperTradingRepository()
    account_id = pt_repo.save_account(PaperAccount(user_id=_USER_ID_BASE, portfolio_id=1, name="Facade PT", starting_balance=1000.0))

    dashboard_service = DashboardService(DashboardRepository())
    from dashboard.paper_trading_dashboard import PaperTradingDashboardService
    dashboard_service.paper_trading_dashboard_service = PaperTradingDashboardService(paper_trading_repository=pt_repo)

    view = dashboard_service.get_paper_trading_dashboard(account_id)
    assert view.account_id == account_id

    with pytest.raises(AccountNotFoundError):
        dashboard_service.get_paper_trading_dashboard(999999999)

    with pt_repo._connection() as conn, conn, conn.cursor() as cur:
        cur.execute("DELETE FROM paper_trading_accounts WHERE id = %s", (account_id,))
