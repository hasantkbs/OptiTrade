"""Tests for paper_trading/repository.py. Real PostgreSQL throughout."""
import pytest

from decision_engine.models import Prediction
from paper_trading.models import (
    EngineVoteSnapshot,
    Fill,
    MarketRegime,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    PaperAccount,
    ScreenshotMetadata,
    TradeJournalEntry,
)
from paper_trading.repository import PaperTradingRepository

_USER_ID_BASE = 9_000_000


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


def _user_id(offset: int) -> int:
    return _USER_ID_BASE + offset


def test_save_and_get_account(repo):
    account_id = repo.save_account(PaperAccount(user_id=_user_id(1), portfolio_id=1, name="Test", starting_balance=1000.0))
    account = repo.get_account(account_id)
    assert account.name == "Test"
    assert account.starting_balance == 1000.0


def test_get_account_returns_none_for_unknown_id(repo):
    assert repo.get_account(999999999) is None


def test_list_accounts_scoped_to_user(repo):
    repo.save_account(PaperAccount(user_id=_user_id(2), portfolio_id=1, name="A", starting_balance=1000.0))
    repo.save_account(PaperAccount(user_id=_user_id(2), portfolio_id=2, name="B", starting_balance=1000.0))
    repo.save_account(PaperAccount(user_id=_user_id(3), portfolio_id=3, name="C", starting_balance=1000.0))
    assert len(repo.list_accounts(_user_id(2))) == 2
    assert len(repo.list_accounts(_user_id(3))) == 1


def test_save_and_get_order(repo):
    account_id = repo.save_account(PaperAccount(user_id=_user_id(4), portfolio_id=1, name="Test", starting_balance=1000.0))
    order = Order(account_id=account_id, symbol="aapl", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10)
    order_id = repo.save_order(order)
    fetched = repo.get_order(order_id)
    assert fetched.symbol == "AAPL"
    assert fetched.status == OrderStatus.PENDING


def test_get_order_returns_none_for_unknown_id(repo):
    assert repo.get_order(999999999) is None


def test_update_order(repo):
    account_id = repo.save_account(PaperAccount(user_id=_user_id(5), portfolio_id=1, name="Test", starting_balance=1000.0))
    order_id = repo.save_order(
        Order(account_id=account_id, symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10)
    )
    order = repo.get_order(order_id)
    order.status = OrderStatus.FILLED
    order.filled_quantity = 10
    order.average_fill_price = 150.5
    repo.update_order(order)
    updated = repo.get_order(order_id)
    assert updated.status == OrderStatus.FILLED
    assert updated.average_fill_price == 150.5


def test_list_orders_filters_by_status(repo):
    account_id = repo.save_account(PaperAccount(user_id=_user_id(6), portfolio_id=1, name="Test", starting_balance=1000.0))
    o1 = repo.save_order(Order(account_id=account_id, symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1))
    o2 = repo.get_order(
        repo.save_order(Order(account_id=account_id, symbol="MSFT", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1))
    )
    o2.status = OrderStatus.FILLED
    repo.update_order(o2)

    assert len(repo.list_orders(account_id)) == 2
    assert len(repo.list_orders(account_id, status=OrderStatus.FILLED)) == 1
    assert len(repo.list_orders(account_id, status=OrderStatus.PENDING)) == 1


def test_list_open_orders_across_accounts(repo):
    account_id = repo.save_account(PaperAccount(user_id=_user_id(7), portfolio_id=1, name="Test", starting_balance=1000.0))
    repo.save_order(Order(account_id=account_id, symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=1, limit_price=100.0))
    filled = repo.get_order(
        repo.save_order(Order(account_id=account_id, symbol="MSFT", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1))
    )
    filled.status = OrderStatus.FILLED
    repo.update_order(filled)

    open_orders = [o for o in repo.list_open_orders() if o.account_id == account_id]
    assert len(open_orders) == 1
    assert open_orders[0].symbol == "AAPL"


def test_save_and_list_fills(repo):
    account_id = repo.save_account(PaperAccount(user_id=_user_id(8), portfolio_id=1, name="Test", starting_balance=1000.0))
    order_id = repo.save_order(Order(account_id=account_id, symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10))
    fill_id = repo.save_fill(Fill(order_id=order_id, account_id=account_id, symbol="AAPL", side=OrderSide.BUY, quantity=10, price=150.0, commission=1.0))
    fills = repo.list_fills(account_id)
    assert len(fills) == 1 and fills[0].id == fill_id
    assert len(repo.list_fills(account_id, symbol="AAPL")) == 1
    assert len(repo.list_fills(account_id, symbol="MSFT")) == 0
    assert len(repo.list_fills_for_order(order_id)) == 1


def test_journal_entry_lifecycle(repo):
    account_id = repo.save_account(PaperAccount(user_id=_user_id(9), portfolio_id=1, name="Test", starting_balance=1000.0))
    order_id = repo.save_order(Order(account_id=account_id, symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10))

    entry = TradeJournalEntry(
        order_id=order_id, account_id=account_id, symbol="AAPL", decision=Prediction.BUY, confidence=0.8,
        expected_return=2.0, expected_volatility=10.0, risk_level="MEDIUM", data_sufficiency=0.9,
        evidence=["evidence1"],
        engine_votes=[
            EngineVoteSnapshot(
                engine_name="Tech", engine_version="v1", prediction=Prediction.BUY, confidence=0.8,
                expected_return=2.0, volatility=10.0, evidence=["x"],
            )
        ],
        explanation_text="bullish", market_regime=MarketRegime.TRENDING_BULLISH, feature_snapshot={"rsi": 55.0},
        notes="note", tags=["a", "b"],
    )
    entry_id = repo.save_journal_entry(entry)
    fetched = repo.get_journal_entry(entry_id)
    assert fetched.symbol == "AAPL"
    assert fetched.engine_votes[0].engine_name == "Tech"
    assert repo.get_journal_entry_by_order(order_id).id == entry_id
    assert len(repo.list_journal_entries(account_id)) == 1

    fetched.notes = "updated"
    fetched.tags = ["c"]
    repo.update_journal_entry(fetched)
    assert repo.get_journal_entry(entry_id).notes == "updated"
    assert repo.get_journal_entry(entry_id).tags == ["c"]


def test_journal_entry_without_decision_round_trips(repo):
    account_id = repo.save_account(PaperAccount(user_id=_user_id(10), portfolio_id=1, name="Test", starting_balance=1000.0))
    order_id = repo.save_order(Order(account_id=account_id, symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10))
    entry = TradeJournalEntry(order_id=order_id, account_id=account_id, symbol="AAPL")
    entry_id = repo.save_journal_entry(entry)
    fetched = repo.get_journal_entry(entry_id)
    assert fetched.decision is None
    assert fetched.engine_votes == []


def test_get_journal_entry_returns_none_for_unknown_id(repo):
    assert repo.get_journal_entry(999999999) is None
    assert repo.get_journal_entry_by_order(999999999) is None


def test_screenshots(repo):
    account_id = repo.save_account(PaperAccount(user_id=_user_id(11), portfolio_id=1, name="Test", starting_balance=1000.0))
    order_id = repo.save_order(Order(account_id=account_id, symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10))
    entry_id = repo.save_journal_entry(TradeJournalEntry(order_id=order_id, account_id=account_id, symbol="AAPL"))

    shot_id = repo.save_screenshot(ScreenshotMetadata(journal_entry_id=entry_id, url="https://x/y.png", caption="chart"))
    shots = repo.list_screenshots(entry_id)
    assert len(shots) == 1 and shots[0].id == shot_id

    fetched_entry = repo.get_journal_entry(entry_id)
    assert len(fetched_entry.screenshots) == 1


def test_ping(repo):
    assert repo.ping() is True
