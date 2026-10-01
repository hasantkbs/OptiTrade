"""Tests for paper_trading/positions.py. Real PostgreSQL throughout."""
import pytest

from paper_trading.models import PaperAccount
from paper_trading.positions import PositionService
from portfolio.repository import PortfolioRepository
from portfolio.service import PortfolioService

_OWNER_PREFIX = "pt-positions-test"


@pytest.fixture
def portfolio_repo():
    repository = PortfolioRepository()
    yield repository
    conn = repository._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM portfolio_transactions WHERE portfolio_id IN (SELECT id FROM portfolio_portfolios WHERE owner LIKE %s)", (f"{_OWNER_PREFIX}%",))
            cur.execute("DELETE FROM portfolio_portfolios WHERE owner LIKE %s", (f"{_OWNER_PREFIX}%",))
    finally:
        repository._pool.putconn(conn)


@pytest.fixture
def portfolio_service(portfolio_repo):
    return PortfolioService(repository=portfolio_repo)


@pytest.fixture
def positions(portfolio_service):
    return PositionService(portfolio_service)


def _owner(name: str) -> str:
    return f"{_OWNER_PREFIX}-{name}"


def _account_for(portfolio_service, name: str, starting_balance: float = 10000.0) -> PaperAccount:
    portfolio = portfolio_service.create_portfolio(_owner(name), "Test Portfolio")
    portfolio_service.deposit(portfolio.id, starting_balance)
    return PaperAccount(id=1, user_id=1, portfolio_id=portfolio.id, name="Test", starting_balance=starting_balance)


def test_get_cash_balance(portfolio_service, positions):
    account = _account_for(portfolio_service, "cash", starting_balance=5000.0)
    assert positions.get_cash_balance(account) == 5000.0


def test_get_positions_empty_when_no_trades(portfolio_service, positions):
    account = _account_for(portfolio_service, "empty")
    assert positions.get_positions(account) == []


def test_get_positions_after_buy(portfolio_service, positions):
    account = _account_for(portfolio_service, "buy")
    portfolio_service.buy(account.portfolio_id, "AAPL", 10, 100.0)
    position_list = positions.get_positions(account)
    assert len(position_list) == 1
    assert position_list[0].symbol == "AAPL"
    assert position_list[0].quantity == 10


def test_get_total_value_includes_cash_and_positions(portfolio_service, positions):
    account = _account_for(portfolio_service, "totalvalue", starting_balance=10000.0)
    portfolio_service.buy(account.portfolio_id, "AAPL", 10, 100.0)
    total_value = positions.get_total_value(account)
    assert total_value > 0


def test_get_realized_and_unrealized_pnl(portfolio_service, positions):
    account = _account_for(portfolio_service, "pnl", starting_balance=10000.0)
    portfolio_service.buy(account.portfolio_id, "AAPL", 10, 100.0)
    portfolio_service.sell(account.portfolio_id, "AAPL", 5, 110.0)
    assert positions.get_realized_pnl(account) == pytest.approx(50.0)
    assert isinstance(positions.get_unrealized_pnl(account), float)
