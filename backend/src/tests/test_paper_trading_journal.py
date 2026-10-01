"""Tests for paper_trading/journal.py. A fake PipelineService/FeatureStoreService
give fast, deterministic coverage of the journal orchestration itself;
real PostgreSQL for persistence. `classify_market_regime` is pure and
tested directly against real inputs, no infra needed."""
import pytest

from decision_engine.models import Prediction
from paper_trading.exceptions import JournalEntryNotFoundError
from paper_trading.journal import JournalService, classify_market_regime
from paper_trading.models import MarketRegime, OrderSide, OrderType, PaperAccount, Order
from paper_trading.repository import PaperTradingRepository
from pipeline.models import EngineBreakdownItem, EngineExecutionStatus, PipelineMetadata, PipelineResponse, RiskAssessment

_USER_ID_BASE = 9_400_000


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
            cur.execute("DELETE FROM paper_trading_orders WHERE account_id = ANY(%s)", (account_ids,))
            cur.execute("DELETE FROM paper_trading_accounts WHERE id = ANY(%s)", (account_ids,))


def _account_id(repo, offset: int) -> int:
    return repo.save_account(PaperAccount(user_id=_USER_ID_BASE + offset, portfolio_id=1, name="Test", starting_balance=1000.0))


def _pipeline_response(symbol: str, decision=Prediction.BUY) -> PipelineResponse:
    return PipelineResponse(
        symbol=symbol, decision=decision, confidence=0.8, expected_return=2.5, expected_volatility=12.0,
        engine_breakdown=[
            EngineBreakdownItem(
                engine_name="Technical", engine_version="v1", status=EngineExecutionStatus.SUCCESS,
                prediction=decision, confidence=0.8, expected_return=2.5, volatility=12.0, evidence=["bullish"],
            ),
            EngineBreakdownItem(
                engine_name="Broken", engine_version="v1", status=EngineExecutionStatus.FAILED,
            ),
        ],
        evidence=["Technical: bullish"], risk=RiskAssessment(risk_level="MEDIUM", expected_volatility=12.0, data_sufficiency=0.9),
        explanation="Looks bullish based on technical evidence.",
        metadata=PipelineMetadata(pipeline_version="v1", total_duration_ms=10.0, engines_available=2, engines_succeeded=1, degraded=False),
    )


class _FakePipelineService:
    def __init__(self, response=None, should_fail=False):
        self._response = response
        self.should_fail = should_fail
        self.calls = []

    def run(self, symbol):
        self.calls.append(symbol)
        if self.should_fail:
            raise RuntimeError("pipeline unavailable")
        return self._response or _pipeline_response(symbol)


class _FakeFeatureStoreService:
    def __init__(self, features=None, should_fail=False):
        self._features = features or {}
        self.should_fail = should_fail

    def get_latest_features(self, symbol, feature_names):
        if self.should_fail:
            raise RuntimeError("feature store unavailable")
        return self._features


# ── classify_market_regime ───────────────────────────────────────────────

def test_classify_market_regime_unknown_without_signals():
    assert classify_market_regime({}) == MarketRegime.UNKNOWN


def test_classify_market_regime_high_volatility_takes_priority():
    assert classify_market_regime({"volume_ratio": 3.0}) == MarketRegime.HIGH_VOLATILITY


def test_classify_market_regime_trending_bullish():
    assert classify_market_regime({"trend_strength": 0.8, "rsi": 60}) == MarketRegime.TRENDING_BULLISH


def test_classify_market_regime_trending_bearish_via_negative_trend():
    assert classify_market_regime({"trend_strength": -0.8}) == MarketRegime.TRENDING_BEARISH


def test_classify_market_regime_trending_bearish_via_low_rsi():
    assert classify_market_regime({"trend_strength": 0.8, "rsi": 30}) == MarketRegime.TRENDING_BEARISH


def test_classify_market_regime_ranging():
    assert classify_market_regime({"trend_strength": 0.1}) == MarketRegime.RANGING


# ── JournalService ───────────────────────────────────────────────────────

def test_record_trade_decision_persists_full_context(repo):
    account_id = _account_id(repo, 1)
    order = Order(account_id=account_id, symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1)
    order.id = repo.save_order(order)

    pipeline = _FakePipelineService()
    feature_store = _FakeFeatureStoreService(features={"trend_strength": 0.8, "rsi": 65.0})
    journal = JournalService(repo, pipeline, feature_store_service=feature_store)

    entry = journal.record_trade_decision(order)
    assert entry is not None
    assert entry.decision == Prediction.BUY
    assert entry.confidence == 0.8
    assert entry.risk_level == "MEDIUM"
    assert entry.market_regime == MarketRegime.TRENDING_BULLISH
    assert len(entry.engine_votes) == 1  # the FAILED engine is excluded
    assert entry.engine_votes[0].engine_name == "Technical"
    assert entry.explanation_text == "Looks bullish based on technical evidence."
    assert entry.feature_snapshot == {"trend_strength": 0.8, "rsi": 65.0}


def test_record_trade_decision_returns_none_when_pipeline_fails(repo):
    account_id = _account_id(repo, 2)
    order = Order(account_id=account_id, symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1)
    order.id = repo.save_order(order)

    pipeline = _FakePipelineService(should_fail=True)
    journal = JournalService(repo, pipeline)
    entry = journal.record_trade_decision(order)
    assert entry is None


def test_record_trade_decision_survives_feature_store_failure(repo):
    account_id = _account_id(repo, 3)
    order = Order(account_id=account_id, symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1)
    order.id = repo.save_order(order)

    pipeline = _FakePipelineService()
    feature_store = _FakeFeatureStoreService(should_fail=True)
    journal = JournalService(repo, pipeline, feature_store_service=feature_store)
    entry = journal.record_trade_decision(order)
    assert entry is not None
    assert entry.feature_snapshot == {}
    assert entry.market_regime == MarketRegime.UNKNOWN


def test_record_trade_decision_without_feature_store(repo):
    account_id = _account_id(repo, 4)
    order = Order(account_id=account_id, symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1)
    order.id = repo.save_order(order)

    journal = JournalService(repo, _FakePipelineService())
    entry = journal.record_trade_decision(order)
    assert entry is not None
    assert entry.feature_snapshot == {}


def test_get_entry_raises_for_unknown_id(repo):
    journal = JournalService(repo, _FakePipelineService())
    with pytest.raises(JournalEntryNotFoundError):
        journal.get_entry(999999999)


def test_get_entry_by_order_returns_none_when_absent(repo):
    journal = JournalService(repo, _FakePipelineService())
    assert journal.get_entry_by_order(999999999) is None


def test_update_notes(repo):
    account_id = _account_id(repo, 5)
    order = Order(account_id=account_id, symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1)
    order.id = repo.save_order(order)
    journal = JournalService(repo, _FakePipelineService())
    entry = journal.record_trade_decision(order)

    updated = journal.update_notes(entry.id, "great trade")
    assert updated.notes == "great trade"


def test_set_and_add_tags_deduplicate(repo):
    account_id = _account_id(repo, 6)
    order = Order(account_id=account_id, symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1)
    order.id = repo.save_order(order)
    journal = JournalService(repo, _FakePipelineService())
    entry = journal.record_trade_decision(order)

    tagged = journal.set_tags(entry.id, ["b", "a", "a"])
    assert tagged.tags == ["a", "b"]
    tagged2 = journal.add_tags(entry.id, ["c", "a"])
    assert tagged2.tags == ["a", "b", "c"]


def test_add_screenshot(repo):
    account_id = _account_id(repo, 7)
    order = Order(account_id=account_id, symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1)
    order.id = repo.save_order(order)
    journal = JournalService(repo, _FakePipelineService())
    entry = journal.record_trade_decision(order)

    screenshot = journal.add_screenshot(entry.id, "https://x/y.png", caption="chart")
    assert screenshot.id is not None
    assert journal.get_entry(entry.id).screenshots[0].url == "https://x/y.png"


def test_list_entries_scoped_to_account(repo):
    account_id = _account_id(repo, 8)
    other_account_id = _account_id(repo, 9)
    journal = JournalService(repo, _FakePipelineService())

    order1 = Order(account_id=account_id, symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1)
    order1.id = repo.save_order(order1)
    journal.record_trade_decision(order1)

    order2 = Order(account_id=other_account_id, symbol="MSFT", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1)
    order2.id = repo.save_order(order2)
    journal.record_trade_decision(order2)

    assert len(journal.list_entries(account_id)) == 1
    assert len(journal.list_entries(other_account_id)) == 1
