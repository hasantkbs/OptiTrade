"""Tests for paper_trading/fills.py. Real PostgreSQL throughout."""
import pytest

from paper_trading.config import PaperTradingConfig
from paper_trading.exceptions import OrderNotOpenError
from paper_trading.execution import ExecutionEngine
from paper_trading.fills import FillService
from paper_trading.models import OrderSide, OrderStatus, OrderType, PaperAccount
from paper_trading.orders import OrderService
from paper_trading.repository import PaperTradingRepository

_USER_ID_BASE = 9_200_000


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
def execution():
    return ExecutionEngine(config=PaperTradingConfig(slippage_bps=0.0, spread_bps=0.0, commission_rate=0.001, commission_min=1.0, tax_rate=0.2))


@pytest.fixture
def order_service(repo, execution):
    return OrderService(repo, execution)


@pytest.fixture
def fill_service(repo, execution):
    return FillService(repo, execution)


def _account_id(repo, offset: int) -> int:
    return repo.save_account(PaperAccount(user_id=_USER_ID_BASE + offset, portfolio_id=1, name="Test", starting_balance=100000.0))


def test_full_fill_updates_order_status(repo, order_service, fill_service):
    account_id = _account_id(repo, 1)
    order = order_service.create_order(account_id, "BTC-USD", OrderSide.BUY, OrderType.MARKET, 1.0)
    fill = fill_service.record_fill(order, reference_price=100.0)
    assert fill.quantity == 1.0
    assert fill.price == 100.0  # zero slippage/spread config

    updated = order_service.get_order(order.id)
    assert updated.status == OrderStatus.FILLED
    assert updated.filled_quantity == 1.0
    assert updated.average_fill_price == 100.0


def test_partial_then_full_fill(repo, order_service, fill_service):
    account_id = _account_id(repo, 2)
    order = order_service.create_order(account_id, "BTC-USD", OrderSide.BUY, OrderType.MARKET, 10.0)

    fill1 = fill_service.record_fill(order, reference_price=100.0, quantity=4.0)
    assert fill1.quantity == 4.0
    order = order_service.get_order(order.id)
    assert order.status == OrderStatus.PARTIALLY_FILLED
    assert order.filled_quantity == 4.0

    fill2 = fill_service.record_fill(order, reference_price=110.0, quantity=6.0)
    assert fill2.quantity == 6.0
    order = order_service.get_order(order.id)
    assert order.status == OrderStatus.FILLED
    assert order.filled_quantity == 10.0
    expected_avg = (4.0 * 100.0 + 6.0 * 110.0) / 10.0
    assert order.average_fill_price == pytest.approx(expected_avg)


def test_fill_quantity_capped_at_remaining(repo, order_service, fill_service):
    account_id = _account_id(repo, 3)
    order = order_service.create_order(account_id, "BTC-USD", OrderSide.BUY, OrderType.MARKET, 5.0)
    fill = fill_service.record_fill(order, reference_price=100.0, quantity=999.0)
    assert fill.quantity == 5.0


def test_cannot_fill_already_filled_order(repo, order_service, fill_service):
    account_id = _account_id(repo, 4)
    order = order_service.create_order(account_id, "BTC-USD", OrderSide.BUY, OrderType.MARKET, 1.0)
    fill_service.record_fill(order, reference_price=100.0)
    order = order_service.get_order(order.id)
    with pytest.raises(OrderNotOpenError):
        fill_service.record_fill(order, reference_price=100.0)


def test_cannot_fill_cancelled_order(repo, order_service, fill_service):
    account_id = _account_id(repo, 5)
    order = order_service.create_order(account_id, "BTC-USD", OrderSide.BUY, OrderType.LIMIT, 1.0, limit_price=100.0)
    order_service.cancel_order(order.id)
    cancelled = order_service.get_order(order.id)
    with pytest.raises(OrderNotOpenError):
        fill_service.record_fill(cancelled, reference_price=100.0)


def test_sell_fill_computes_tax_on_realized_gain(repo, order_service, fill_service):
    account_id = _account_id(repo, 6)
    order = order_service.create_order(account_id, "BTC-USD", OrderSide.SELL, OrderType.MARKET, 1.0)
    fill = fill_service.record_fill(order, reference_price=150.0, average_cost=100.0)
    # gain = (150-100)*1 = 50, tax_rate=0.2 -> tax=10
    assert fill.tax == pytest.approx(10.0)


def test_sell_fill_no_tax_on_realized_loss(repo, order_service, fill_service):
    account_id = _account_id(repo, 7)
    order = order_service.create_order(account_id, "BTC-USD", OrderSide.SELL, OrderType.MARKET, 1.0)
    fill = fill_service.record_fill(order, reference_price=80.0, average_cost=100.0)
    assert fill.tax == 0.0


def test_sell_fill_no_tax_without_average_cost(repo, order_service, fill_service):
    account_id = _account_id(repo, 8)
    order = order_service.create_order(account_id, "BTC-USD", OrderSide.SELL, OrderType.MARKET, 1.0)
    fill = fill_service.record_fill(order, reference_price=150.0)
    assert fill.tax == 0.0


def test_commission_recorded_on_order(repo, order_service, fill_service):
    account_id = _account_id(repo, 9)
    order = order_service.create_order(account_id, "BTC-USD", OrderSide.BUY, OrderType.MARKET, 10.0)
    fill_service.record_fill(order, reference_price=100.0)
    updated = order_service.get_order(order.id)
    assert updated.commission_paid > 0
    assert updated.commission_paid == pytest.approx(fill_service._execution.compute_commission(1000.0))
