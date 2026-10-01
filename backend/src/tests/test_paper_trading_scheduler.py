"""Tests for paper_trading/scheduler.py. Real PostgreSQL + real portfolio/
watchlist infra for portfolio_sync; a fake price service gives fast,
deterministic control over trigger conditions."""
import pytest

from paper_trading.execution import ExecutionEngine
from paper_trading.fills import FillService
from paper_trading.models import OrderSide, OrderStatus, OrderType, PaperAccount
from paper_trading.orders import OrderService
from paper_trading.portfolio_sync import PortfolioSyncService
from paper_trading.repository import PaperTradingRepository
from paper_trading.scheduler import PaperTradingScheduler
from portfolio.repository import PortfolioRepository
from portfolio.service import PortfolioService

_EMAIL_PREFIX = "pt-scheduler-test"
_USER_ID_BASE = 9_700_000


class _FakePriceService:
    def __init__(self, prices):
        self._prices = prices
        self.calls = []

    def get_current_price(self, symbol):
        self.calls.append(symbol)
        if symbol not in self._prices:
            raise RuntimeError(f"no price for {symbol}")
        return self._prices[symbol]


@pytest.fixture
def repo():
    repository = PaperTradingRepository()
    yield repository
    with repository._connection() as conn, conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, portfolio_id FROM paper_trading_accounts WHERE user_id >= %s AND user_id < %s",
            (_USER_ID_BASE, _USER_ID_BASE + 100_000),
        )
        rows = cur.fetchall()
        account_ids = [row[0] for row in rows]
        portfolio_ids = [row[1] for row in rows]
        if account_ids:
            cur.execute("DELETE FROM paper_trading_fills WHERE account_id = ANY(%s)", (account_ids,))
            cur.execute("DELETE FROM paper_trading_orders WHERE account_id = ANY(%s)", (account_ids,))
            cur.execute("DELETE FROM paper_trading_accounts WHERE id = ANY(%s)", (account_ids,))
    with PortfolioRepository()._connection() as conn, conn, conn.cursor() as cur:
        if portfolio_ids:
            cur.execute("DELETE FROM portfolio_transactions WHERE portfolio_id = ANY(%s)", (portfolio_ids,))
            cur.execute("DELETE FROM portfolio_portfolios WHERE id = ANY(%s)", (portfolio_ids,))


@pytest.fixture
def portfolio_service():
    return PortfolioService(repository=PortfolioRepository())


@pytest.fixture
def sync(repo, portfolio_service):
    return PortfolioSyncService(repo, portfolio_service)


@pytest.fixture
def order_service(repo):
    return OrderService(repo, ExecutionEngine())


def _email(name: str) -> str:
    return f"{_EMAIL_PREFIX}-{name}@example.com"


def _account(sync, offset: int, starting_balance: float = 100000.0) -> PaperAccount:
    return sync.ensure_account(_USER_ID_BASE + offset, _email(f"acc{offset}"), starting_balance=starting_balance)


def test_scan_pending_orders_ignores_market_orders(repo, sync, order_service):
    account = _account(sync, 1)
    order_service.create_order(account.id, "BTC-USD", OrderSide.BUY, OrderType.MARKET, 1.0)
    scheduler = PaperTradingScheduler(repo, sync, price_service=_FakePriceService({}))
    fills = scheduler.scan_pending_orders()
    assert fills == []


def test_scan_pending_orders_triggers_limit_buy(repo, sync, order_service):
    account = _account(sync, 2)
    order_service.create_order(account.id, "BTC-USD", OrderSide.BUY, OrderType.LIMIT, 0.1, limit_price=100.0)
    scheduler = PaperTradingScheduler(repo, sync, price_service=_FakePriceService({"BTC-USD": 90.0}))
    fills = scheduler.scan_pending_orders()
    assert len(fills) == 1
    assert fills[0].symbol == "BTC-USD"


def test_scan_pending_orders_fills_a_triggered_limit_order_at_the_market_price_not_the_limit_price(
    repo, sync, order_service,
):
    """Production audit LOW batch finding #3 ("can a client-supplied
    price override the simulated execution model?"): confirmed NOT a
    bug, but was previously unverified by an explicit assertion - every
    existing trigger test checked only that a fill happened, never
    what price it filled at. A BUY LIMIT at 100.0 with the real market
    at 90.0 must fill near 90.0 (market price + simulated slippage/
    spread), never at or near the client's 100.0 limit_price - the
    limit_price is only ever a trigger threshold (see
    ExecutionEngine.is_triggered), never the execution price itself
    (see ExecutionEngine.simulate_execution_price)."""
    account = _account(sync, 20)
    order_service.create_order(account.id, "BTC-USD", OrderSide.BUY, OrderType.LIMIT, 0.1, limit_price=100.0)
    scheduler = PaperTradingScheduler(repo, sync, price_service=_FakePriceService({"BTC-USD": 90.0}))
    fills = scheduler.scan_pending_orders()

    assert len(fills) == 1
    fill_price = fills[0].price
    # Default slippage_bps=5.0 + spread_bps/2=5.0 = 10bps adverse move
    # against the trader on a BUY: 90.0 * 1.001 = 90.09.
    assert fill_price == pytest.approx(90.09, abs=0.5)
    assert fill_price < 95.0  # nowhere near the 100.0 client-supplied limit_price


def test_scan_pending_orders_does_not_trigger_when_condition_not_met(repo, sync, order_service):
    account = _account(sync, 3)
    order_service.create_order(account.id, "BTC-USD", OrderSide.BUY, OrderType.LIMIT, 0.1, limit_price=100.0)
    scheduler = PaperTradingScheduler(repo, sync, price_service=_FakePriceService({"BTC-USD": 150.0}))
    fills = scheduler.scan_pending_orders()
    assert fills == []
    order = order_service.get_order(order_service.list_orders(account.id)[0].id)
    assert order.status == OrderStatus.PENDING


def test_scan_pending_orders_skips_symbol_with_price_error(repo, sync, order_service):
    account = _account(sync, 4)
    order_service.create_order(account.id, "BTC-USD", OrderSide.BUY, OrderType.LIMIT, 0.1, limit_price=100.0)
    order_service.create_order(account.id, "ETH-USD", OrderSide.BUY, OrderType.LIMIT, 1.0, limit_price=100.0)
    scheduler = PaperTradingScheduler(repo, sync, price_service=_FakePriceService({"ETH-USD": 50.0}))
    fills = scheduler.scan_pending_orders()
    assert len(fills) == 1
    assert fills[0].symbol == "ETH-USD"


def test_scan_pending_orders_fetches_price_once_per_symbol(repo, sync, order_service):
    account = _account(sync, 5)
    order_service.create_order(account.id, "BTC-USD", OrderSide.BUY, OrderType.LIMIT, 0.1, limit_price=100.0)
    order_service.create_order(account.id, "BTC-USD", OrderSide.BUY, OrderType.LIMIT, 0.1, limit_price=200.0)
    price_service = _FakePriceService({"BTC-USD": 90.0})
    scheduler = PaperTradingScheduler(repo, sync, price_service=price_service)
    fills = scheduler.scan_pending_orders()
    assert len(fills) == 2
    assert price_service.calls.count("BTC-USD") == 1


def test_scan_pending_orders_syncs_fill_into_real_portfolio(repo, sync, order_service, portfolio_service):
    account = _account(sync, 6, starting_balance=100000.0)
    order_service.create_order(account.id, "BTC-USD", OrderSide.BUY, OrderType.LIMIT, 0.5, limit_price=100.0)
    scheduler = PaperTradingScheduler(repo, sync, price_service=_FakePriceService({"BTC-USD": 90.0}))
    scheduler.scan_pending_orders()

    positions = portfolio_service.get_positions(account.portfolio_id)
    assert len(positions) == 1
    assert positions[0].symbol == "BTC-USD"


def test_scan_pending_orders_triggers_stop_sell(repo, sync, order_service, portfolio_service):
    account = _account(sync, 7)
    portfolio_service.buy(account.portfolio_id, "BTC-USD", 1.0, 100.0)
    order_service.create_order(account.id, "BTC-USD", OrderSide.SELL, OrderType.STOP, 1.0, stop_price=90.0)

    scheduler = PaperTradingScheduler(repo, sync, price_service=_FakePriceService({"BTC-USD": 85.0}))
    fills = scheduler.scan_pending_orders()
    assert len(fills) == 1
    assert fills[0].side == OrderSide.SELL


def test_scan_pending_orders_no_open_orders_returns_empty(repo, sync):
    scheduler = PaperTradingScheduler(repo, sync, price_service=_FakePriceService({}))
    assert scheduler.scan_pending_orders() == []
