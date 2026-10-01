"""Tests for paper_trading/service.py (top-level facade). Real Postgres/
portfolio/watchlist infra; a fake PipelineService for fast, deterministic
journal coverage (the pipeline itself is exercised for real in
tests/test_paper_trading_journal.py) and a fake PriceService for
deterministic market-order fill prices."""
import pytest

from decision_engine.models import Prediction
from paper_trading.exceptions import AccountNotFoundError
from paper_trading.journal import JournalService
from paper_trading.models import OrderSide, OrderType, ReportPeriod
from paper_trading.portfolio_sync import PortfolioSyncService
from paper_trading.positions import PositionService
from paper_trading.repository import PaperTradingRepository
from paper_trading.service import PaperTradingService
from pipeline.models import EngineBreakdownItem, EngineExecutionStatus, PipelineMetadata, PipelineResponse, RiskAssessment
from portfolio.repository import PortfolioRepository
from portfolio.service import PortfolioService
from watchlist.repository import WatchlistRepository
from watchlist.watchlist_service import WatchlistService

_EMAIL_PREFIX = "pt-svc-test"
_USER_ID_BASE = 9_800_000


class _FakePipelineService:
    def run(self, symbol):
        return PipelineResponse(
            symbol=symbol, decision=Prediction.BUY, confidence=0.75, expected_return=1.5, expected_volatility=8.0,
            engine_breakdown=[
                EngineBreakdownItem(
                    engine_name="Technical", engine_version="v1", status=EngineExecutionStatus.SUCCESS,
                    prediction=Prediction.BUY, confidence=0.75, expected_return=1.5, volatility=8.0, evidence=["x"],
                ),
            ],
            evidence=["Technical: x"], risk=RiskAssessment(risk_level="LOW", expected_volatility=8.0, data_sufficiency=0.9),
            explanation="Fake explanation.",
            metadata=PipelineMetadata(pipeline_version="v1", total_duration_ms=1.0, engines_available=1, engines_succeeded=1, degraded=False),
        )


class _FakePriceService:
    def __init__(self, prices):
        self._prices = prices

    def get_current_price(self, symbol):
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
            cur.execute(
                "DELETE FROM paper_trading_screenshots WHERE journal_entry_id IN "
                "(SELECT id FROM paper_trading_journal_entries WHERE account_id = ANY(%s))", (account_ids,),
            )
            cur.execute("DELETE FROM paper_trading_journal_entries WHERE account_id = ANY(%s)", (account_ids,))
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
def service(repo, portfolio_service, watchlist_service):
    sync = PortfolioSyncService(
        repo, portfolio_service, watchlist_service=watchlist_service, watchlist_repository=watchlist_service.repository,
    )
    positions = PositionService(portfolio_service)
    journal = JournalService(repo, _FakePipelineService())
    return PaperTradingService(
        repo, sync, positions, journal, price_service=_FakePriceService({"BTC-USD": 100.0, "AAPL": 150.0}),
    )


def _email(name: str) -> str:
    return f"{_EMAIL_PREFIX}-{name}@example.com"


def test_ensure_account_and_get_account(service):
    account = service.ensure_account(_USER_ID_BASE + 1, _email("acc1"), starting_balance=50000.0)
    fetched = service.get_account(account.id)
    assert fetched.id == account.id


def test_get_account_raises_for_unknown_id(service):
    with pytest.raises(AccountNotFoundError):
        service.get_account(999999999)


def test_list_accounts(service):
    service.ensure_account(_USER_ID_BASE + 2, _email("acc2"), starting_balance=1000.0)
    assert len(service.list_accounts(_USER_ID_BASE + 2)) == 1


def test_place_market_order_executes_immediately_and_journals(service):
    account = service.ensure_account(_USER_ID_BASE + 3, _email("acc3"), starting_balance=50000.0)
    order = service.place_order(account.id, _email("acc3"), "BTC-USD", OrderSide.BUY, OrderType.MARKET, 1.0)
    assert order.status.value == "filled"

    entry = service.get_journal_entry_by_order(order.id)
    assert entry is not None
    assert entry.decision == Prediction.BUY

    positions = service.get_positions(account.id)
    assert len(positions) == 1 and positions[0].symbol == "BTC-USD"


def test_place_limit_order_stays_pending_and_syncs_watchlist(service, watchlist_service):
    account = service.ensure_account(_USER_ID_BASE + 4, _email("acc4"), starting_balance=50000.0)
    order = service.place_order(account.id, _email("acc4"), "AAPL", OrderSide.BUY, OrderType.LIMIT, 1.0, limit_price=100.0)
    assert order.status.value == "pending"

    watchlists = watchlist_service.list_watchlists(_email("acc4"))
    assert any(w.name == "Paper Trading" for w in watchlists)


def test_cancel_and_modify_order(service):
    account = service.ensure_account(_USER_ID_BASE + 5, _email("acc5"), starting_balance=50000.0)
    order = service.place_order(account.id, _email("acc5"), "AAPL", OrderSide.BUY, OrderType.LIMIT, 1.0, limit_price=100.0)
    modified = service.modify_order(order.id, limit_price=90.0)
    assert modified.limit_price == 90.0
    cancelled = service.cancel_order(order.id)
    assert cancelled.status.value == "cancelled"


def test_list_orders(service):
    account = service.ensure_account(_USER_ID_BASE + 6, _email("acc6"), starting_balance=50000.0)
    service.place_order(account.id, _email("acc6"), "BTC-USD", OrderSide.BUY, OrderType.MARKET, 0.1)
    service.place_order(account.id, _email("acc6"), "AAPL", OrderSide.BUY, OrderType.LIMIT, 1.0, limit_price=100.0)
    assert len(service.list_orders(account.id)) == 2


def test_cash_and_total_value(service):
    account = service.ensure_account(_USER_ID_BASE + 7, _email("acc7"), starting_balance=50000.0)
    service.place_order(account.id, _email("acc7"), "BTC-USD", OrderSide.BUY, OrderType.MARKET, 1.0)
    assert service.get_cash_balance(account.id) < 50000.0
    assert service.get_total_value(account.id) > 0


def test_journal_notes_tags_screenshot_via_facade(service):
    account = service.ensure_account(_USER_ID_BASE + 8, _email("acc8"), starting_balance=50000.0)
    order = service.place_order(account.id, _email("acc8"), "BTC-USD", OrderSide.BUY, OrderType.MARKET, 1.0)
    entry = service.get_journal_entry_by_order(order.id)

    updated = service.update_journal_notes(entry.id, "solid entry")
    assert updated.notes == "solid entry"
    tagged = service.add_journal_tags(entry.id, ["momentum"])
    assert "momentum" in tagged.tags
    shot = service.add_journal_screenshot(entry.id, "https://x/y.png")
    assert shot.id is not None


def test_analytics_and_reports_after_round_trip(service):
    account = service.ensure_account(_USER_ID_BASE + 9, _email("acc9"), starting_balance=50000.0)
    service.place_order(account.id, _email("acc9"), "BTC-USD", OrderSide.BUY, OrderType.MARKET, 1.0)
    service.place_order(account.id, _email("acc9"), "BTC-USD", OrderSide.SELL, OrderType.MARKET, 1.0)

    summary = service.get_analytics_summary(account.id)
    assert summary.total_trades == 1

    trades = service.get_closed_trades(account.id)
    assert len(trades) == 1

    curve = service.get_equity_curve(account.id)
    assert len(curve) == 2

    monthly = service.get_monthly_performance(account.id)
    assert len(monthly) == 1

    report = service.generate_report(account.id, ReportPeriod.MONTHLY)
    assert report.total_trades == 1
