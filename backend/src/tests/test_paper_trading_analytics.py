"""Tests for paper_trading/analytics.py. Real PostgreSQL throughout."""
from datetime import datetime, timedelta, timezone

import pytest

from paper_trading.analytics import (
    AnalyticsService,
    build_equity_curve,
    compute_max_drawdown,
    compute_profit_factor,
    compute_sharpe_ratio,
    compute_sortino_ratio,
    match_closed_trades,
    monthly_performance,
    summarize,
)
from paper_trading.models import Fill, Order, OrderSide, OrderStatus, OrderType, PaperAccount
from paper_trading.repository import PaperTradingRepository

_USER_ID_BASE = 9_500_000


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


def _account(repo, offset: int, starting_balance: float = 10000.0) -> PaperAccount:
    account_id = repo.save_account(
        PaperAccount(user_id=_USER_ID_BASE + offset, portfolio_id=1, name="Test", starting_balance=starting_balance)
    )
    return repo.get_account(account_id)


def _fill(repo, account, symbol, side, quantity, price, when, commission=0.0, tax=0.0):
    order_id = repo.save_order(
        Order(account_id=account.id, symbol=symbol, side=side, order_type=OrderType.MARKET, quantity=quantity,
              status=OrderStatus.FILLED, filled_quantity=quantity, average_fill_price=price)
    )
    repo.save_fill(Fill(order_id=order_id, account_id=account.id, symbol=symbol, side=side, quantity=quantity, price=price, commission=commission, tax=tax, executed_at=when))


def test_match_closed_trades_simple_round_trip(repo):
    account = _account(repo, 1)
    now = datetime.now(timezone.utc)
    _fill(repo, account, "AAPL", OrderSide.BUY, 10, 100.0, now - timedelta(days=2))
    _fill(repo, account, "AAPL", OrderSide.SELL, 10, 110.0, now - timedelta(days=1))

    fills = repo.list_fills(account.id)
    closed = match_closed_trades(account, fills)
    assert len(closed) == 1
    assert closed[0].net_pnl == pytest.approx(100.0)
    assert closed[0].quantity == 10


def test_match_closed_trades_fifo_across_two_lots(repo):
    account = _account(repo, 2)
    now = datetime.now(timezone.utc)
    _fill(repo, account, "GOOG", OrderSide.BUY, 10, 50.0, now - timedelta(days=10))
    _fill(repo, account, "GOOG", OrderSide.BUY, 10, 52.0, now - timedelta(days=9))
    _fill(repo, account, "GOOG", OrderSide.SELL, 15, 55.0, now - timedelta(days=1))

    closed = match_closed_trades(account, repo.list_fills(account.id))
    assert len(closed) == 2
    assert closed[0].quantity == 10 and closed[0].entry_price == 50.0
    assert closed[1].quantity == 5 and closed[1].entry_price == 52.0


def test_match_closed_trades_ignores_open_positions(repo):
    account = _account(repo, 3)
    now = datetime.now(timezone.utc)
    _fill(repo, account, "AAPL", OrderSide.BUY, 10, 100.0, now)
    closed = match_closed_trades(account, repo.list_fills(account.id))
    assert closed == []


def test_build_equity_curve_starts_at_account_balance(repo):
    account = _account(repo, 4, starting_balance=5000.0)
    now = datetime.now(timezone.utc)
    _fill(repo, account, "AAPL", OrderSide.BUY, 10, 100.0, now - timedelta(days=2))
    _fill(repo, account, "AAPL", OrderSide.SELL, 10, 110.0, now - timedelta(days=1))

    closed = match_closed_trades(account, repo.list_fills(account.id))
    curve = build_equity_curve(account, closed)
    assert curve[0].equity == 5000.0
    assert curve[-1].equity == pytest.approx(5100.0)


def test_compute_max_drawdown():
    from paper_trading.models import EquityPoint
    now = datetime.now(timezone.utc)
    curve = [
        EquityPoint(as_of=now, equity=1000.0),
        EquityPoint(as_of=now, equity=1200.0),
        EquityPoint(as_of=now, equity=900.0),
        EquityPoint(as_of=now, equity=1100.0),
    ]
    assert compute_max_drawdown(curve) == pytest.approx((1200.0 - 900.0) / 1200.0)


def test_compute_max_drawdown_empty():
    assert compute_max_drawdown([]) == 0.0


def test_compute_profit_factor_no_losses_returns_none():
    from paper_trading.models import ClosedTrade
    now = datetime.now(timezone.utc)
    trade = ClosedTrade(
        account_id=1, symbol="AAPL", side=OrderSide.SELL, quantity=1, entry_price=100, exit_price=110,
        entry_time=now, exit_time=now, commission=0, tax=0, gross_pnl=10, net_pnl=10, holding_seconds=1,
    )
    assert compute_profit_factor([trade]) is None


def test_sharpe_and_sortino_none_with_insufficient_data():
    assert compute_sharpe_ratio([]) is None
    assert compute_sortino_ratio([]) is None


def test_summarize_empty_trades(repo):
    account = _account(repo, 5)
    summary = summarize(account, [])
    assert summary.total_trades == 0
    assert summary.win_rate == 0.0


def test_summarize_win_rate_and_best_worst(repo):
    account = _account(repo, 6)
    now = datetime.now(timezone.utc)
    _fill(repo, account, "AAPL", OrderSide.BUY, 10, 100.0, now - timedelta(days=5))
    _fill(repo, account, "AAPL", OrderSide.SELL, 10, 110.0, now - timedelta(days=4))
    _fill(repo, account, "MSFT", OrderSide.BUY, 5, 300.0, now - timedelta(days=3))
    _fill(repo, account, "MSFT", OrderSide.SELL, 5, 290.0, now - timedelta(days=2))

    closed = match_closed_trades(account, repo.list_fills(account.id))
    summary = summarize(account, closed)
    assert summary.total_trades == 2
    assert summary.win_rate == 0.5
    assert summary.best_trade.symbol == "AAPL"
    assert summary.worst_trade.symbol == "MSFT"
    assert summary.expectancy == pytest.approx((100.0 - 50.0) / 2)


def test_monthly_performance_groups_by_month(repo):
    account = _account(repo, 7)
    now = datetime.now(timezone.utc)
    _fill(repo, account, "AAPL", OrderSide.BUY, 10, 100.0, now - timedelta(days=2))
    _fill(repo, account, "AAPL", OrderSide.SELL, 10, 110.0, now - timedelta(days=1))

    closed = match_closed_trades(account, repo.list_fills(account.id))
    performance = monthly_performance(closed)
    assert len(performance) == 1
    assert performance[0].trades == 1
    assert performance[0].net_pnl == pytest.approx(100.0)


def test_analytics_service_facade(repo):
    account = _account(repo, 8)
    now = datetime.now(timezone.utc)
    _fill(repo, account, "AAPL", OrderSide.BUY, 10, 100.0, now - timedelta(days=2))
    _fill(repo, account, "AAPL", OrderSide.SELL, 10, 110.0, now - timedelta(days=1))

    service = AnalyticsService(repo)
    assert len(service.get_closed_trades(account)) == 1
    assert service.get_summary(account).total_trades == 1
    assert len(service.get_equity_curve(account)) == 2
    assert len(service.get_monthly_performance(account)) == 1


def test_analytics_service_filters_by_symbol(repo):
    account = _account(repo, 9)
    now = datetime.now(timezone.utc)
    _fill(repo, account, "AAPL", OrderSide.BUY, 10, 100.0, now - timedelta(days=2))
    _fill(repo, account, "AAPL", OrderSide.SELL, 10, 110.0, now - timedelta(days=1))
    _fill(repo, account, "MSFT", OrderSide.BUY, 5, 300.0, now - timedelta(days=2))
    _fill(repo, account, "MSFT", OrderSide.SELL, 5, 310.0, now - timedelta(days=1))

    service = AnalyticsService(repo)
    assert len(service.get_closed_trades(account, symbol="AAPL")) == 1
    assert len(service.get_closed_trades(account)) == 2
