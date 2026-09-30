"""Tests for dashboard/paper_trading_dashboard.py. Real PostgreSQL throughout."""
from datetime import datetime, timedelta, timezone

import pytest

from dashboard.paper_trading_dashboard import PaperTradingDashboardService
from decision_engine.models import Prediction
from paper_trading.exceptions import AccountNotFoundError
from paper_trading.models import Fill, MarketRegime, Order, OrderSide, OrderStatus, OrderType, PaperAccount, TradeJournalEntry
from paper_trading.repository import PaperTradingRepository

_USER_ID_BASE = 9_900_000


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
            cur.execute(
                "DELETE FROM paper_trading_screenshots WHERE journal_entry_id IN "
                "(SELECT id FROM paper_trading_journal_entries WHERE account_id = ANY(%s))", (account_ids,),
            )
            cur.execute("DELETE FROM paper_trading_journal_entries WHERE account_id = ANY(%s)", (account_ids,))
            cur.execute("DELETE FROM paper_trading_fills WHERE account_id = ANY(%s)", (account_ids,))
            cur.execute("DELETE FROM paper_trading_orders WHERE account_id = ANY(%s)", (account_ids,))
            cur.execute("DELETE FROM paper_trading_accounts WHERE id = ANY(%s)", (account_ids,))


@pytest.fixture
def service(repo):
    return PaperTradingDashboardService(repo)


def _account(repo, offset: int) -> PaperAccount:
    account_id = repo.save_account(
        PaperAccount(user_id=_USER_ID_BASE + offset, portfolio_id=1, name="Test", starting_balance=10000.0)
    )
    return repo.get_account(account_id)


def test_build_raises_for_unknown_account(service):
    with pytest.raises(AccountNotFoundError):
        service.build(999999999)


def test_build_empty_account(service, repo):
    account = _account(repo, 1)
    view = service.build(account.id)
    assert view.win_rate == 0.0
    assert view.journal_statistics.total_entries == 0


def test_build_with_closed_trade_and_journal_entries(service, repo):
    account = _account(repo, 2)
    now = datetime.now(timezone.utc)

    order1 = repo.save_order(Order(account_id=account.id, symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10, status=OrderStatus.FILLED, filled_quantity=10, average_fill_price=100.0))
    repo.save_fill(Fill(order_id=order1, account_id=account.id, symbol="AAPL", side=OrderSide.BUY, quantity=10, price=100.0, executed_at=now - timedelta(days=2)))
    order2 = repo.save_order(Order(account_id=account.id, symbol="AAPL", side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=10, status=OrderStatus.FILLED, filled_quantity=10, average_fill_price=110.0))
    repo.save_fill(Fill(order_id=order2, account_id=account.id, symbol="AAPL", side=OrderSide.SELL, quantity=10, price=110.0, executed_at=now - timedelta(days=1)))

    repo.save_journal_entry(TradeJournalEntry(
        order_id=order1, account_id=account.id, symbol="AAPL", decision=Prediction.BUY, confidence=0.8,
        market_regime=MarketRegime.TRENDING_BULLISH, tags=["swing", "breakout"],
    ))
    repo.save_journal_entry(TradeJournalEntry(
        order_id=order2, account_id=account.id, symbol="AAPL", decision=Prediction.SELL, confidence=0.6,
        market_regime=MarketRegime.RANGING, tags=["swing"],
    ))

    view = service.build(account.id)
    assert view.win_rate == 1.0
    assert view.expectancy > 0
    assert len(view.equity_curve) == 2
    assert view.journal_statistics.total_entries == 2
    assert view.journal_statistics.entries_by_decision == {"BUY": 1, "SELL": 1}
    assert view.journal_statistics.entries_by_regime == {"trending_bullish": 1, "ranging": 1}
    assert view.journal_statistics.average_confidence == pytest.approx(0.7)
    assert view.journal_statistics.most_common_tags[0] == "swing"
