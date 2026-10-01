"""Tests for paper_trading/orders.py. Real PostgreSQL throughout."""
from datetime import datetime, timezone

import pytest

from paper_trading.exceptions import AccountNotFoundError, InvalidOrderError, MarketClosedError, OrderNotFoundError, OrderNotOpenError
from paper_trading.execution import ExecutionEngine
from paper_trading.models import OrderSide, OrderStatus, OrderType, PaperAccount
from paper_trading.orders import OrderService
from paper_trading.repository import PaperTradingRepository

_USER_ID_BASE = 9_100_000
_WEEKDAY_OPEN = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def repo():
    repository = PaperTradingRepository()
    yield repository
    with repository._connection() as conn, conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM paper_trading_accounts WHERE user_id >= %s AND user_id < %s",
            (_USER_ID_BASE, _USER_ID_BASE + 100_000),
        )
        account_ids = [row[0] for row in cur.fetchall()]
        if account_ids:
            cur.execute("DELETE FROM paper_trading_fills WHERE account_id = ANY(%s)", (account_ids,))
            cur.execute("DELETE FROM paper_trading_orders WHERE account_id = ANY(%s)", (account_ids,))
            cur.execute("DELETE FROM paper_trading_accounts WHERE id = ANY(%s)", (account_ids,))


@pytest.fixture
def service(repo):
    return OrderService(repo, ExecutionEngine())


def _account_id(repo, offset: int) -> int:
    return repo.save_account(PaperAccount(user_id=_USER_ID_BASE + offset, portfolio_id=1, name="Test", starting_balance=1000.0))


def test_create_market_order(service, repo):
    account_id = _account_id(repo, 1)
    order = service.create_order(account_id, "btc-usd", OrderSide.BUY, OrderType.MARKET, 1.0)
    assert order.symbol == "BTC-USD"
    assert order.status == OrderStatus.PENDING


def test_create_order_raises_for_unknown_account(service):
    with pytest.raises(AccountNotFoundError):
        service.create_order(999999999, "BTC-USD", OrderSide.BUY, OrderType.MARKET, 1.0)


def test_create_limit_order_requires_limit_price(service, repo):
    account_id = _account_id(repo, 2)
    with pytest.raises(InvalidOrderError):
        service.create_order(account_id, "BTC-USD", OrderSide.BUY, OrderType.LIMIT, 1.0)


def test_create_stop_order_requires_stop_price(service, repo):
    account_id = _account_id(repo, 3)
    with pytest.raises(InvalidOrderError):
        service.create_order(account_id, "BTC-USD", OrderSide.SELL, OrderType.STOP, 1.0)


def test_create_market_order_rejected_outside_market_hours(service, repo):
    account_id = _account_id(repo, 4)
    closed = datetime(2026, 7, 29, 22, 0, tzinfo=timezone.utc)
    with pytest.raises(MarketClosedError):
        service.create_order(account_id, "AAPL", OrderSide.BUY, OrderType.MARKET, 1.0, now=closed)


def test_create_limit_order_allowed_outside_market_hours(service, repo):
    account_id = _account_id(repo, 5)
    closed = datetime(2026, 7, 29, 22, 0, tzinfo=timezone.utc)
    order = service.create_order(account_id, "AAPL", OrderSide.BUY, OrderType.LIMIT, 1.0, limit_price=100.0, now=closed)
    assert order.status == OrderStatus.PENDING


def test_get_order(service, repo):
    account_id = _account_id(repo, 6)
    order = service.create_order(account_id, "BTC-USD", OrderSide.BUY, OrderType.MARKET, 1.0)
    assert service.get_order(order.id).id == order.id


def test_get_order_raises_for_unknown_id(service):
    with pytest.raises(OrderNotFoundError):
        service.get_order(999999999)


def test_list_orders(service, repo):
    account_id = _account_id(repo, 7)
    service.create_order(account_id, "BTC-USD", OrderSide.BUY, OrderType.MARKET, 1.0)
    service.create_order(account_id, "ETH-USD", OrderSide.BUY, OrderType.MARKET, 1.0)
    assert len(service.list_orders(account_id)) == 2


def test_cancel_order(service, repo):
    account_id = _account_id(repo, 8)
    order = service.create_order(account_id, "BTC-USD", OrderSide.BUY, OrderType.LIMIT, 1.0, limit_price=100.0)
    cancelled = service.cancel_order(order.id)
    assert cancelled.status == OrderStatus.CANCELLED
    assert cancelled.cancelled_at is not None


def test_cancel_order_twice_raises(service, repo):
    account_id = _account_id(repo, 9)
    order = service.create_order(account_id, "BTC-USD", OrderSide.BUY, OrderType.LIMIT, 1.0, limit_price=100.0)
    service.cancel_order(order.id)
    with pytest.raises(OrderNotOpenError):
        service.cancel_order(order.id)


def test_modify_order_updates_price_and_quantity(service, repo):
    account_id = _account_id(repo, 10)
    order = service.create_order(account_id, "BTC-USD", OrderSide.BUY, OrderType.LIMIT, 1.0, limit_price=100.0)
    modified = service.modify_order(order.id, quantity=2.0, limit_price=90.0)
    assert modified.quantity == 2.0
    assert modified.limit_price == 90.0


def test_modify_order_raises_for_cancelled_order(service, repo):
    account_id = _account_id(repo, 11)
    order = service.create_order(account_id, "BTC-USD", OrderSide.BUY, OrderType.LIMIT, 1.0, limit_price=100.0)
    service.cancel_order(order.id)
    with pytest.raises(OrderNotOpenError):
        service.modify_order(order.id, quantity=5.0)


def test_modify_order_raises_after_partial_fill(service, repo):
    account_id = _account_id(repo, 12)
    order = service.create_order(account_id, "BTC-USD", OrderSide.BUY, OrderType.LIMIT, 10.0, limit_price=100.0)
    order.filled_quantity = 5.0
    order.status = OrderStatus.PARTIALLY_FILLED
    repo.update_order(order)
    with pytest.raises(OrderNotOpenError):
        service.modify_order(order.id, quantity=20.0)


def test_modify_order_rejects_non_positive_quantity(service, repo):
    account_id = _account_id(repo, 13)
    order = service.create_order(account_id, "BTC-USD", OrderSide.BUY, OrderType.LIMIT, 1.0, limit_price=100.0)
    with pytest.raises(InvalidOrderError):
        service.modify_order(order.id, quantity=-5.0)
