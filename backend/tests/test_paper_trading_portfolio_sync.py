"""Tests for paper_trading/portfolio_sync.py. Real PostgreSQL throughout
(paper_trading, portfolio, and watchlist tables)."""
import pytest

from paper_trading.models import Fill, Order, OrderSide, OrderStatus, OrderType
from paper_trading.portfolio_sync import PortfolioSyncService
from paper_trading.repository import PaperTradingRepository
from portfolio.repository import PortfolioRepository
from portfolio.service import PortfolioService
from watchlist.repository import WatchlistRepository
from watchlist.watchlist_service import WatchlistService

_EMAIL_PREFIX = "pt-sync-test"
_USER_ID_BASE = 9_300_000


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
    with WatchlistRepository()._connection() as conn, conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM watchlist_watchlists WHERE owner LIKE %s", (f"{_EMAIL_PREFIX}%",))
        wl_ids = [row[0] for row in cur.fetchall()]
        for wl_id in wl_ids:
            cur.execute("DELETE FROM watchlist_items WHERE watchlist_id = %s", (wl_id,))
        cur.execute("DELETE FROM watchlist_watchlists WHERE owner LIKE %s", (f"{_EMAIL_PREFIX}%",))
        cur.execute("DELETE FROM watchlist_alerts WHERE owner LIKE %s", (f"{_EMAIL_PREFIX}%",))


@pytest.fixture
def portfolio_service():
    return PortfolioService(repository=PortfolioRepository())


@pytest.fixture
def watchlist_service():
    return WatchlistService(repository=WatchlistRepository())


@pytest.fixture
def sync(repo, portfolio_service, watchlist_service):
    return PortfolioSyncService(
        repo, portfolio_service, watchlist_service=watchlist_service,
        watchlist_repository=watchlist_service.repository,
    )


def _email(name: str) -> str:
    return f"{_EMAIL_PREFIX}-{name}@example.com"


def test_ensure_account_creates_real_portfolio(sync, portfolio_service):
    account = sync.ensure_account(_USER_ID_BASE + 1, _email("create"), starting_balance=50000.0)
    assert account.portfolio_id is not None
    portfolio = portfolio_service.get_portfolio(account.portfolio_id)
    assert portfolio.owner == _email("create")
    assert portfolio_service.get_cash_balance(account.portfolio_id) == 50000.0


def test_ensure_account_is_idempotent(sync):
    account1 = sync.ensure_account(_USER_ID_BASE + 2, _email("idempotent"), starting_balance=1000.0)
    account2 = sync.ensure_account(_USER_ID_BASE + 2, _email("idempotent"), starting_balance=1000.0)
    assert account1.id == account2.id


def test_sync_fill_buy_records_real_transaction(sync, portfolio_service):
    account = sync.ensure_account(_USER_ID_BASE + 3, _email("buy"), starting_balance=10000.0)
    fill = Fill(id=1, order_id=1, account_id=account.id, symbol="AAPL", side=OrderSide.BUY, quantity=10, price=100.0, commission=1.0)
    txn = sync.sync_fill(account, fill)
    assert txn.transaction_type.value == "buy"
    assert portfolio_service.get_cash_balance(account.portfolio_id) == pytest.approx(10000.0 - 1000.0 - 1.0)


def test_sync_fill_sell_records_real_transaction(sync, portfolio_service):
    account = sync.ensure_account(_USER_ID_BASE + 4, _email("sell"), starting_balance=10000.0)
    buy_fill = Fill(id=1, order_id=1, account_id=account.id, symbol="AAPL", side=OrderSide.BUY, quantity=10, price=100.0)
    sync.sync_fill(account, buy_fill)
    sell_fill = Fill(id=2, order_id=2, account_id=account.id, symbol="AAPL", side=OrderSide.SELL, quantity=5, price=110.0)
    txn = sync.sync_fill(account, sell_fill)
    assert txn.transaction_type.value == "sell"
    positions = portfolio_service.get_positions(account.portfolio_id)
    assert positions[0].quantity == 5


def test_get_average_cost(sync, portfolio_service):
    account = sync.ensure_account(_USER_ID_BASE + 5, _email("avgcost"), starting_balance=10000.0)
    assert sync.get_average_cost(account, "AAPL") is None
    fill = Fill(id=1, order_id=1, account_id=account.id, symbol="AAPL", side=OrderSide.BUY, quantity=10, price=100.0)
    sync.sync_fill(account, fill)
    assert sync.get_average_cost(account, "AAPL") == pytest.approx(100.0)


def test_sync_watchlist_creates_and_reuses_paper_watchlist(sync, watchlist_service):
    account = sync.ensure_account(_USER_ID_BASE + 6, _email("watchlist"), starting_balance=1000.0)
    sync.sync_watchlist(account, _email("watchlist"), "AAPL")
    sync.sync_watchlist(account, _email("watchlist"), "MSFT")
    sync.sync_watchlist(account, _email("watchlist"), "AAPL")  # idempotent

    watchlists = watchlist_service.list_watchlists(_email("watchlist"))
    paper_watchlists = [w for w in watchlists if w.name == "Paper Trading"]
    assert len(paper_watchlists) == 1
    items = watchlist_service.list_items(paper_watchlists[0].id)
    assert {item.symbol for item in items} == {"AAPL", "MSFT"}


def test_sync_watchlist_noop_without_service(repo, portfolio_service):
    sync_no_watchlist = PortfolioSyncService(repo, portfolio_service)
    account = sync_no_watchlist.ensure_account(_USER_ID_BASE + 7, _email("nowatchlist"), starting_balance=1000.0)
    sync_no_watchlist.sync_watchlist(account, _email("nowatchlist"), "AAPL")  # must not raise


def test_sync_stop_alert_for_sell_stop_loss(sync, watchlist_service):
    account = sync.ensure_account(_USER_ID_BASE + 8, _email("stoploss"), starting_balance=1000.0)
    order = Order(id=1, account_id=account.id, symbol="AAPL", side=OrderSide.SELL, order_type=OrderType.STOP, quantity=1, stop_price=90.0)
    alert_id = sync.sync_stop_take_profit_alert(account, _email("stoploss"), order)
    assert alert_id is not None
    alert = watchlist_service.repository.get_alert(alert_id)
    assert alert.alert_type.value == "price_below"
    assert alert.parameters["threshold"] == 90.0


def test_sync_take_profit_alert_for_sell(sync, watchlist_service):
    account = sync.ensure_account(_USER_ID_BASE + 9, _email("takeprofit"), starting_balance=1000.0)
    order = Order(id=2, account_id=account.id, symbol="AAPL", side=OrderSide.SELL, order_type=OrderType.TAKE_PROFIT, quantity=1, stop_price=120.0)
    alert_id = sync.sync_stop_take_profit_alert(account, _email("takeprofit"), order)
    alert = watchlist_service.repository.get_alert(alert_id)
    assert alert.alert_type.value == "price_above"


def test_sync_stop_alert_for_buy_stop_entry(sync, watchlist_service):
    account = sync.ensure_account(_USER_ID_BASE + 10, _email("buystop"), starting_balance=1000.0)
    order = Order(id=3, account_id=account.id, symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.STOP, quantity=1, stop_price=120.0)
    alert_id = sync.sync_stop_take_profit_alert(account, _email("buystop"), order)
    alert = watchlist_service.repository.get_alert(alert_id)
    assert alert.alert_type.value == "price_above"


def test_no_alert_for_market_or_limit_orders(sync):
    account = sync.ensure_account(_USER_ID_BASE + 11, _email("noalert"), starting_balance=1000.0)
    market_order = Order(id=4, account_id=account.id, symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1)
    limit_order = Order(id=5, account_id=account.id, symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=1, limit_price=100.0)
    assert sync.sync_stop_take_profit_alert(account, _email("noalert"), market_order) is None
    assert sync.sync_stop_take_profit_alert(account, _email("noalert"), limit_order) is None
