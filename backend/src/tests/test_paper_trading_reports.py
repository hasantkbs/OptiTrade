"""Tests for paper_trading/reports.py. Real PostgreSQL throughout."""
from datetime import datetime, timedelta, timezone

import pytest

from paper_trading.analytics import AnalyticsService
from paper_trading.models import Fill, Order, OrderSide, OrderStatus, OrderType, PaperAccount, ReportPeriod
from paper_trading.repository import PaperTradingRepository
from paper_trading.reports import ReportService

_USER_ID_BASE = 9_600_000


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
def report_service(repo):
    return ReportService(AnalyticsService(repo))


def _account(repo, offset: int) -> PaperAccount:
    account_id = repo.save_account(
        PaperAccount(user_id=_USER_ID_BASE + offset, portfolio_id=1, name="Test", starting_balance=10000.0)
    )
    return repo.get_account(account_id)


def _fill(repo, account, symbol, side, quantity, price, when):
    order_id = repo.save_order(
        Order(account_id=account.id, symbol=symbol, side=side, order_type=OrderType.MARKET, quantity=quantity,
              status=OrderStatus.FILLED, filled_quantity=quantity, average_fill_price=price)
    )
    repo.save_fill(Fill(order_id=order_id, account_id=account.id, symbol=symbol, side=side, quantity=quantity, price=price, executed_at=when))


def test_daily_report_includes_only_todays_trades(repo, report_service):
    account = _account(repo, 1)
    now = datetime.now(timezone.utc)
    _fill(repo, account, "AAPL", OrderSide.BUY, 10, 100.0, now - timedelta(hours=2))
    _fill(repo, account, "AAPL", OrderSide.SELL, 10, 110.0, now - timedelta(hours=1))
    _fill(repo, account, "MSFT", OrderSide.BUY, 5, 300.0, now - timedelta(days=5))
    _fill(repo, account, "MSFT", OrderSide.SELL, 5, 310.0, now - timedelta(days=5, hours=-1))

    report = report_service.generate(account, ReportPeriod.DAILY, reference=now)
    assert report.total_trades == 1
    assert report.net_pnl == pytest.approx(100.0)


def test_weekly_report(repo, report_service):
    account = _account(repo, 2)
    now = datetime.now(timezone.utc)
    _fill(repo, account, "AAPL", OrderSide.BUY, 10, 100.0, now - timedelta(days=1))
    _fill(repo, account, "AAPL", OrderSide.SELL, 10, 110.0, now)
    report = report_service.generate(account, ReportPeriod.WEEKLY, reference=now)
    assert report.total_trades == 1


def test_monthly_report(repo, report_service):
    account = _account(repo, 3)
    now = datetime.now(timezone.utc)
    _fill(repo, account, "AAPL", OrderSide.BUY, 10, 100.0, now - timedelta(days=10))
    _fill(repo, account, "AAPL", OrderSide.SELL, 10, 110.0, now - timedelta(days=9))
    report = report_service.generate(account, ReportPeriod.MONTHLY, reference=now)
    assert report.total_trades == 1


def test_yearly_report(repo, report_service):
    account = _account(repo, 4)
    now = datetime.now(timezone.utc)
    _fill(repo, account, "AAPL", OrderSide.BUY, 10, 100.0, now - timedelta(days=100))
    _fill(repo, account, "AAPL", OrderSide.SELL, 10, 110.0, now - timedelta(days=99))
    report = report_service.generate(account, ReportPeriod.YEARLY, reference=now)
    assert report.total_trades == 1


def test_report_with_no_trades_in_period(repo, report_service):
    account = _account(repo, 5)
    now = datetime.now(timezone.utc)
    report = report_service.generate(account, ReportPeriod.DAILY, reference=now)
    assert report.total_trades == 0
    assert report.net_pnl == 0.0
    assert report.win_rate == 0.0
    assert report.profit_factor is None
    assert report.best_trade is None
    assert report.worst_trade is None


def test_report_period_boundaries_are_exclusive_of_next_period(repo, report_service):
    account = _account(repo, 6)
    reference = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
    _fill(repo, account, "AAPL", OrderSide.BUY, 10, 100.0, datetime(2026, 6, 30, 23, 0, tzinfo=timezone.utc))
    _fill(repo, account, "AAPL", OrderSide.SELL, 10, 110.0, datetime(2026, 7, 1, 1, 0, tzinfo=timezone.utc))
    report = report_service.generate(account, ReportPeriod.MONTHLY, reference=reference)
    assert report.total_trades == 1
    assert report.period_start == datetime(2026, 7, 1, tzinfo=timezone.utc)
    assert report.period_end == datetime(2026, 8, 1, tzinfo=timezone.utc)


def test_unknown_period_raises():
    # production audit MEDIUM #2: paper_trading/reports.py's _period_bounds
    # now delegates to the shared core.report_periods.period_bounds -
    # this proves the re-exported alias still raises exactly as before.
    from paper_trading.reports import _period_bounds
    with pytest.raises(ValueError):
        _period_bounds("not-a-period", datetime.now(timezone.utc))
