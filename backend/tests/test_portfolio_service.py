"""Tests for portfolio/service.py (Portfolio Service, requirement 1).
Real PostgreSQL throughout; a deterministic fake price fetcher is
injected into `PriceService` so unrealized-P&L/snapshot assertions
don't depend on live market data."""
import threading
from datetime import datetime, timezone

import pandas as pd
import pytest

from portfolio.config import PortfolioConfig
from portfolio.exceptions import (
    InsufficientCashError,
    InsufficientPositionError,
    InvalidTransactionError,
    PortfolioNotFoundError,
)
from portfolio.models import TransactionType
from portfolio.prices import PriceService
from portfolio.repository import PortfolioRepository
from portfolio.service import PortfolioService

_OWNER_PREFIX = "svc-test-owner"
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
                "DELETE FROM portfolio_snapshots WHERE portfolio_id IN "
                "(SELECT id FROM portfolio_portfolios WHERE owner LIKE %s)", (f"{_OWNER_PREFIX}%",),
            )
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
def service(repository, price_service):
    return PortfolioService(repository=repository, price_service=price_service)


def _owner(name: str) -> str:
    return f"{_OWNER_PREFIX}-{name}"


# ── Portfolios ───────────────────────────────────────────────────────────

def test_create_and_get_portfolio(service):
    portfolio = service.create_portfolio(owner=_owner("create"), name="Main")
    assert portfolio.id is not None
    fetched = service.get_portfolio(portfolio.id)
    assert fetched.owner == _owner("create")
    assert fetched.base_currency == "USD"


def test_create_portfolio_uses_config_default_currency():
    config = PortfolioConfig(default_base_currency="EUR")
    service_with_config = PortfolioService(config=config)
    portfolio = service_with_config.create_portfolio(owner=_owner("currency"), name="EUR portfolio")
    assert portfolio.base_currency == "EUR"
    conn = service_with_config.repository._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM portfolio_portfolios WHERE id = %s", (portfolio.id,))
    finally:
        service_with_config.repository._pool.putconn(conn)


def test_get_portfolio_raises_for_unknown_id(service):
    with pytest.raises(PortfolioNotFoundError):
        service.get_portfolio(999999999)


def test_list_portfolios_returns_only_that_owners_portfolios(service):
    service.create_portfolio(owner=_owner("list-a"), name="A1")
    service.create_portfolio(owner=_owner("list-a"), name="A2")
    service.create_portfolio(owner=_owner("list-b"), name="B1")
    assert len(service.list_portfolios(_owner("list-a"))) == 2
    assert len(service.list_portfolios(_owner("list-b"))) == 1


# ── Cash ─────────────────────────────────────────────────────────────────

def test_deposit_increases_cash_balance(service):
    portfolio = service.create_portfolio(owner=_owner("deposit"), name="Cash")
    service.deposit(portfolio.id, 5000.0)
    assert service.get_cash_balance(portfolio.id) == 5000.0


def test_withdraw_decreases_cash_balance(service):
    portfolio = service.create_portfolio(owner=_owner("withdraw"), name="Cash")
    service.deposit(portfolio.id, 5000.0)
    service.withdraw(portfolio.id, 2000.0)
    assert service.get_cash_balance(portfolio.id) == 3000.0


def test_withdraw_raises_when_exceeding_cash_balance(service):
    portfolio = service.create_portfolio(owner=_owner("overdraw"), name="Cash")
    service.deposit(portfolio.id, 100.0)
    with pytest.raises(InsufficientCashError):
        service.withdraw(portfolio.id, 200.0)


# ── Trades ───────────────────────────────────────────────────────────────

def test_buy_reduces_cash_and_creates_a_position(service):
    portfolio = service.create_portfolio(owner=_owner("buy"), name="Trading")
    service.deposit(portfolio.id, 10000.0)
    service.buy(portfolio.id, "AAPL", 10, 150.0, fee=1.0)
    assert service.get_cash_balance(portfolio.id) == pytest.approx(10000.0 - 1501.0)
    position = service.get_position(portfolio.id, "AAPL")
    assert position.quantity == 10.0
    assert position.average_cost == pytest.approx(150.1)


def test_buy_raises_when_exceeding_cash_balance(service):
    portfolio = service.create_portfolio(owner=_owner("buy-overdraw"), name="Trading")
    service.deposit(portfolio.id, 100.0)
    with pytest.raises(InsufficientCashError):
        service.buy(portfolio.id, "AAPL", 10, 150.0)


def test_buy_rejects_non_positive_quantity_or_price(service):
    portfolio = service.create_portfolio(owner=_owner("buy-invalid"), name="Trading")
    service.deposit(portfolio.id, 10000.0)
    with pytest.raises(InvalidTransactionError):
        service.buy(portfolio.id, "AAPL", -1, 150.0)
    with pytest.raises(InvalidTransactionError):
        service.buy(portfolio.id, "AAPL", 1, 0.0)


def test_second_buy_blends_average_cost(service):
    portfolio = service.create_portfolio(owner=_owner("blend"), name="Trading")
    service.deposit(portfolio.id, 20000.0)
    service.buy(portfolio.id, "AAPL", 10, 150.0)
    service.buy(portfolio.id, "AAPL", 5, 165.0)
    position = service.get_position(portfolio.id, "AAPL")
    assert position.quantity == 15.0
    assert position.average_cost == pytest.approx((150.0 * 10 + 165.0 * 5) / 15)


def test_sell_computes_realized_pnl_and_reduces_quantity(service):
    portfolio = service.create_portfolio(owner=_owner("sell"), name="Trading")
    service.deposit(portfolio.id, 20000.0)
    service.buy(portfolio.id, "AAPL", 10, 150.0)
    service.sell(portfolio.id, "AAPL", 4, 180.0, fee=2.0)
    position = service.get_position(portfolio.id, "AAPL")
    assert position.quantity == 6.0
    assert position.realized_pnl == pytest.approx((180.0 - 150.0) * 4 - 2.0)
    assert service.get_realized_pnl(portfolio.id) == pytest.approx((180.0 - 150.0) * 4 - 2.0)


def test_sell_raises_when_exceeding_held_quantity(service):
    portfolio = service.create_portfolio(owner=_owner("oversell"), name="Trading")
    service.deposit(portfolio.id, 20000.0)
    service.buy(portfolio.id, "AAPL", 10, 150.0)
    with pytest.raises(InsufficientPositionError):
        service.sell(portfolio.id, "AAPL", 11, 150.0)


def test_selling_entire_position_removes_it_from_get_positions_but_keeps_realized_pnl(service):
    portfolio = service.create_portfolio(owner=_owner("close-out"), name="Trading")
    service.deposit(portfolio.id, 20000.0)
    service.buy(portfolio.id, "AAPL", 10, 150.0)
    service.sell(portfolio.id, "AAPL", 10, 160.0)
    assert service.get_positions(portfolio.id) == []
    assert service.get_realized_pnl(portfolio.id) == pytest.approx((160.0 - 150.0) * 10)


def test_get_position_for_never_traded_symbol_is_a_zero_position(service):
    portfolio = service.create_portfolio(owner=_owner("never-traded"), name="Trading")
    position = service.get_position(portfolio.id, "MSFT")
    assert position.quantity == 0.0
    assert position.average_cost == 0.0
    assert position.realized_pnl == 0.0


# ── Dividends / fees / taxes ──────────────────────────────────────────────

def test_record_dividend_increases_cash_net_of_tax(service):
    portfolio = service.create_portfolio(owner=_owner("dividend"), name="Income")
    service.deposit(portfolio.id, 1000.0)
    service.record_dividend(portfolio.id, "AAPL", amount=50.0, tax=5.0)
    assert service.get_cash_balance(portfolio.id) == pytest.approx(1045.0)


def test_record_fee_and_tax_reduce_cash(service):
    portfolio = service.create_portfolio(owner=_owner("fees"), name="Fees")
    service.deposit(portfolio.id, 1000.0)
    service.record_fee(portfolio.id, amount=10.0)
    service.record_tax(portfolio.id, amount=20.0)
    assert service.get_cash_balance(portfolio.id) == pytest.approx(970.0)


# ── Unrealized P&L / total value / history ───────────────────────────────

def test_get_unrealized_pnl_uses_current_price(service):
    portfolio = service.create_portfolio(owner=_owner("unrealized"), name="Trading")
    service.deposit(portfolio.id, 10000.0)
    service.buy(portfolio.id, "AAPL", 10, 150.0)
    assert service.get_unrealized_pnl(portfolio.id) == pytest.approx((200.0 - 150.0) * 10)


def test_get_total_value_combines_cash_and_positions(service):
    portfolio = service.create_portfolio(owner=_owner("total-value"), name="Trading")
    service.deposit(portfolio.id, 10000.0)
    service.buy(portfolio.id, "AAPL", 10, 150.0)
    assert service.get_total_value(portfolio.id) == pytest.approx(8500.0 + 10 * 200.0)


def test_take_snapshot_and_get_history(service):
    portfolio = service.create_portfolio(owner=_owner("history"), name="Trading")
    service.deposit(portfolio.id, 10000.0)
    service.buy(portfolio.id, "AAPL", 10, 150.0)
    snapshot = service.take_snapshot(portfolio.id)
    assert snapshot.id is not None
    assert snapshot.total_value == pytest.approx(service.get_total_value(portfolio.id))

    history = service.get_history(portfolio.id)
    assert len(history) == 1
    assert history[0].id == snapshot.id


def test_service_defaults_to_real_dependencies():
    service = PortfolioService()
    assert isinstance(service.repository, PortfolioRepository)
    assert isinstance(service.price_service, PriceService)


# ── Concurrency (money-path race-condition regression) ───────────────────
#
# buy()/sell()/withdraw() replay the transaction history to check a
# precondition (enough cash, enough position) and then append a new
# transaction. Without locking, N concurrent callers on the SAME
# portfolio can all replay the same pre-transaction state, all pass the
# check, and all commit - overspending cash or overselling a position.
# `PortfolioRepository.locked_portfolio` closes this with a per-portfolio
# `SELECT ... FOR UPDATE` row lock (see repository.py) so these threads
# serialize against each other while a *different* portfolio_id would
# not be blocked at all.

_CONCURRENT_THREADS = 10


@pytest.fixture
def concurrent_repository():
    # A dedicated, larger pool: each of the threads below holds a
    # connection for the duration of its locked transaction, so the
    # default pool (maxconn=5) would spuriously exhaust under this
    # fixture's own concurrency rather than exercising the lock itself.
    repo = PortfolioRepository(maxconn=_CONCURRENT_THREADS + 2)
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
        repo.close()


@pytest.fixture
def concurrent_service(concurrent_repository, price_service):
    return PortfolioService(repository=concurrent_repository, price_service=price_service)


def _run_concurrently(fn, count):
    results = []
    lock = threading.Lock()

    def _wrapped():
        try:
            fn()
            with lock:
                results.append("OK")
        except (InsufficientCashError, InsufficientPositionError):
            with lock:
                results.append("REJECTED")

    threads = [threading.Thread(target=_wrapped) for _ in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def test_concurrent_buys_on_same_portfolio_cannot_double_spend_cash(concurrent_service):
    portfolio = concurrent_service.create_portfolio(owner=_owner("race-buy"), name="Race")
    # Enough cash for exactly one of the N concurrent buys below.
    concurrent_service.deposit(portfolio.id, 1000.0)

    results = _run_concurrently(
        lambda: concurrent_service.buy(portfolio.id, "AAPL", 10, 100.0), _CONCURRENT_THREADS,
    )

    assert results.count("OK") == 1
    assert results.count("REJECTED") == _CONCURRENT_THREADS - 1
    assert concurrent_service.get_cash_balance(portfolio.id) == pytest.approx(0.0)
    assert concurrent_service.get_position(portfolio.id, "AAPL").quantity == 10.0


def test_concurrent_sells_on_same_portfolio_cannot_oversell_position(concurrent_service):
    portfolio = concurrent_service.create_portfolio(owner=_owner("race-sell"), name="Race")
    concurrent_service.deposit(portfolio.id, 100000.0)
    # Enough shares held for exactly one of the N concurrent full sells below.
    concurrent_service.buy(portfolio.id, "AAPL", 10, 100.0)

    results = _run_concurrently(
        lambda: concurrent_service.sell(portfolio.id, "AAPL", 10, 100.0), _CONCURRENT_THREADS,
    )

    assert results.count("OK") == 1
    assert results.count("REJECTED") == _CONCURRENT_THREADS - 1
    assert concurrent_service.get_position(portfolio.id, "AAPL").quantity == 0.0


def test_concurrent_withdrawals_on_same_portfolio_cannot_double_spend_cash(concurrent_service):
    portfolio = concurrent_service.create_portfolio(owner=_owner("race-withdraw"), name="Race")
    # Enough cash for exactly one of the N concurrent withdrawals below.
    concurrent_service.deposit(portfolio.id, 1000.0)

    results = _run_concurrently(
        lambda: concurrent_service.withdraw(portfolio.id, 1000.0), _CONCURRENT_THREADS,
    )

    assert results.count("OK") == 1
    assert results.count("REJECTED") == _CONCURRENT_THREADS - 1
    assert concurrent_service.get_cash_balance(portfolio.id) == pytest.approx(0.0)


def test_concurrent_operations_on_different_portfolios_are_not_serialized_against_each_other(concurrent_service):
    # locked_portfolio() takes a row lock scoped to ONE portfolio_id, not
    # a table-wide or global lock - two different portfolios must be able
    # to complete concurrent buys without either blocking on the other's
    # transaction. Each buy sleeps (via a slow price lookup substitute is
    # unnecessary - real work is fast) so we instead just prove both
    # complete correctly when launched at the same time; a global lock
    # would still pass this functionally, so the real "no global lock"
    # guarantee is architectural (see repository.py:locked_portfolio
    # docstring) - this test guards the functional outcome.
    portfolio_a = concurrent_service.create_portfolio(owner=_owner("race-independent-a"), name="A")
    portfolio_b = concurrent_service.create_portfolio(owner=_owner("race-independent-b"), name="B")
    concurrent_service.deposit(portfolio_a.id, 10000.0)
    concurrent_service.deposit(portfolio_b.id, 10000.0)

    errors = []

    def _buy(portfolio_id):
        try:
            concurrent_service.buy(portfolio_id, "AAPL", 10, 100.0)
        except Exception as exc:  # pragma: no cover - failure path only
            errors.append(exc)

    threads = [
        threading.Thread(target=_buy, args=(portfolio_a.id,)),
        threading.Thread(target=_buy, args=(portfolio_b.id,)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert concurrent_service.get_position(portfolio_a.id, "AAPL").quantity == 10.0
    assert concurrent_service.get_position(portfolio_b.id, "AAPL").quantity == 10.0
