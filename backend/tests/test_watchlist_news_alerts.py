"""Tests for watchlist/news_alerts.py. A fake `NewsEngine` stands in for
`engines.news.engine.NewsEngine` (which hits live news providers) for
fast, deterministic unit coverage - the real integration is exercised
separately by manual verification against live data. Real Redis (an
isolated logical DB, matching `tests/test_feature_store_online_store.py`'s
own convention) for the analysis cache this evaluator now owns."""
from datetime import datetime, timedelta, timezone

import pytest
import redis

from decision_engine.models import Prediction
from engines.news.models import NewsAnalysisResult, NewsEvidence, NewsExecutionMetadata
from watchlist.config import WatchlistConfig
from watchlist.exceptions import InsufficientAlertDataError, InvalidAlertError
from watchlist.models import Alert, AlertCategory, AlertType
from watchlist.news_alerts import NewsAlertEvaluator


def _analysis(symbol: str, impact: float, article_count: int, evidence=None) -> NewsAnalysisResult:
    return NewsAnalysisResult(
        symbol=symbol, prediction=Prediction.HOLD, confidence=0.5, expected_return=0.0, expected_volatility=10.0,
        evidence=["e"], structured_evidence=evidence or [], relevance=0.8, impact=impact, article_count=article_count,
        execution_metadata=NewsExecutionMetadata(
            total_duration_ms=1.0, raw_article_count=article_count, articles_after_dedup=article_count,
            articles_in_aggregation=article_count,
        ),
    )


def _news_item(title: str, timestamp: datetime, impact: float = 0.5, sentiment: float = 0.3) -> NewsEvidence:
    return NewsEvidence(
        source="test", timestamp=timestamp, title=title, summary="summary", sentiment=sentiment,
        relevance=0.8, impact=impact, confidence=0.7,
    )


class _FakeNewsEngine:
    def __init__(self, analyses):
        self._analyses = analyses
        self.call_count = 0

    def analyze(self, symbol):
        self.call_count += 1
        if symbol not in self._analyses:
            raise RuntimeError(f"no fake analysis configured for {symbol!r}")
        return self._analyses[symbol]


def _alert(alert_type, symbol="AAPL", parameters=None):
    alert = Alert(owner="wl-news-test", symbol=symbol, category=AlertCategory.NEWS, alert_type=alert_type,
                  parameters=parameters or {})
    alert.id = 1
    return alert


@pytest.fixture
def redis_client():
    client = redis.Redis(host="localhost", port=6379, db=15, decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()


def _evaluator(redis_client, engine, sector_symbols_provider=None):
    config = WatchlistConfig(redis_host="localhost", redis_port=6379, redis_db=15)
    return NewsAlertEvaluator(
        news_engine=engine, sector_symbols_provider=sector_symbols_provider, redis_client=redis_client, config=config,
    )


def test_high_impact_triggers_above_threshold(redis_client):
    engine = _FakeNewsEngine({"AAPL": _analysis("AAPL", impact=0.8, article_count=5)})
    evaluator = _evaluator(redis_client, engine)
    event, state = evaluator.evaluate(_alert(AlertType.NEWS_HIGH_IMPACT, parameters={"threshold": 0.6}))
    assert event is not None
    assert state["impact"] == 0.8


def test_high_impact_does_not_trigger_with_no_articles(redis_client):
    engine = _FakeNewsEngine({"AAPL": _analysis("AAPL", impact=0.9, article_count=0)})
    evaluator = _evaluator(redis_client, engine)
    event, _ = evaluator.evaluate(_alert(AlertType.NEWS_HIGH_IMPACT, parameters={"threshold": 0.6}))
    assert event is None


def test_high_impact_does_not_trigger_below_threshold(redis_client):
    engine = _FakeNewsEngine({"AAPL": _analysis("AAPL", impact=0.3, article_count=5)})
    evaluator = _evaluator(redis_client, engine)
    event, _ = evaluator.evaluate(_alert(AlertType.NEWS_HIGH_IMPACT, parameters={"threshold": 0.6}))
    assert event is None


def test_analysis_is_cached_across_evaluations(redis_client):
    engine = _FakeNewsEngine({"AAPL": _analysis("AAPL", impact=0.8, article_count=5)})
    evaluator = _evaluator(redis_client, engine)
    evaluator.evaluate(_alert(AlertType.NEWS_HIGH_IMPACT, parameters={"threshold": 0.6}))
    evaluator.evaluate(_alert(AlertType.NEWS_HIGH_IMPACT, parameters={"threshold": 0.6}))
    assert engine.call_count == 1  # second call served from the Redis cache


def test_breaking_triggers_for_recent_article(redis_client):
    now = datetime.now(timezone.utc)
    engine = _FakeNewsEngine({
        "AAPL": _analysis("AAPL", impact=0.5, article_count=1, evidence=[_news_item("Breaking!", now)]),
    })
    evaluator = _evaluator(redis_client, engine)
    event, state = evaluator.evaluate(_alert(AlertType.NEWS_BREAKING, parameters={"max_age_minutes": 60}))
    assert event is not None
    assert "Breaking!" in event.message
    assert state["recent_article_count"] == 1.0


def test_breaking_does_not_trigger_for_old_article(redis_client):
    old = datetime.now(timezone.utc) - timedelta(days=5)
    engine = _FakeNewsEngine({
        "AAPL": _analysis("AAPL", impact=0.5, article_count=1, evidence=[_news_item("Old news", old)]),
    })
    evaluator = _evaluator(redis_client, engine)
    event, state = evaluator.evaluate(_alert(AlertType.NEWS_BREAKING, parameters={"max_age_minutes": 60}))
    assert event is None
    assert state["recent_article_count"] == 0.0


def test_sector_check_averages_impact_across_sector_symbols(redis_client):
    engine = _FakeNewsEngine({
        "GARAN.IS": _analysis("GARAN.IS", impact=0.8, article_count=3),
        "AKBNK.IS": _analysis("AKBNK.IS", impact=0.6, article_count=2),
    })
    evaluator = _evaluator(redis_client, engine, sector_symbols_provider=lambda sector: ["GARAN.IS", "AKBNK.IS"])
    event, state = evaluator.evaluate(
        _alert(AlertType.NEWS_SECTOR, symbol="GARAN.IS", parameters={"threshold": 0.5}),
    )
    assert event is not None
    assert state["sector_impact"] == pytest.approx(0.7)


def test_sector_check_ignores_symbols_with_no_articles(redis_client):
    engine = _FakeNewsEngine({
        "GARAN.IS": _analysis("GARAN.IS", impact=0.9, article_count=3),
        "AKBNK.IS": _analysis("AKBNK.IS", impact=0.9, article_count=0),
    })
    evaluator = _evaluator(redis_client, engine, sector_symbols_provider=lambda sector: ["GARAN.IS", "AKBNK.IS"])
    event, state = evaluator.evaluate(
        _alert(AlertType.NEWS_SECTOR, symbol="GARAN.IS", parameters={"threshold": 0.5}),
    )
    assert event is not None
    assert state["sector_impact"] == pytest.approx(0.9)


def test_sector_check_skips_a_symbol_whose_analysis_fails_and_logs_it(redis_client, caplog):
    """Production audit MEDIUM #9: a per-symbol News Engine failure
    inside `_sector_check` used to be a bare `except Exception:
    continue` with zero logging - indistinguishable from "checked and
    found nothing," and a whole-sector outage would silently report
    sector_impact=0.0 with no way to diagnose it. GARAN.IS is
    intentionally left out of the fake engine's configured analyses so
    `.analyze()` raises for it, exactly like a real News Engine
    failure would."""
    engine = _FakeNewsEngine({
        "AKBNK.IS": _analysis("AKBNK.IS", impact=0.9, article_count=3),
    })
    evaluator = _evaluator(redis_client, engine, sector_symbols_provider=lambda sector: ["GARAN.IS", "AKBNK.IS"])

    import logging
    with caplog.at_level(logging.WARNING, logger="watchlist.news_alerts"):
        event, state = evaluator.evaluate(
            _alert(AlertType.NEWS_SECTOR, symbol="GARAN.IS", parameters={"threshold": 0.5}),
        )

    # The failing symbol is excluded, not fatal - the sector average is
    # computed from whatever symbols DID succeed.
    assert event is not None
    assert state["sector_impact"] == pytest.approx(0.9)
    assert any("GARAN.IS" in record.message for record in caplog.records)


def test_sector_check_raises_for_an_unknown_sector(redis_client):
    evaluator = _evaluator(redis_client, _FakeNewsEngine({}), sector_symbols_provider=lambda sector: [])
    with pytest.raises(InsufficientAlertDataError):
        evaluator.evaluate(_alert(AlertType.NEWS_SECTOR, symbol="GARAN.IS"))


def test_raises_without_symbol(redis_client):
    evaluator = _evaluator(redis_client, _FakeNewsEngine({}))
    alert = _alert(AlertType.NEWS_HIGH_IMPACT)
    alert.symbol = None
    with pytest.raises(InvalidAlertError):
        evaluator.evaluate(alert)


def test_raises_for_wrong_category(redis_client):
    evaluator = _evaluator(redis_client, _FakeNewsEngine({}))
    alert = _alert(AlertType.NEWS_HIGH_IMPACT)
    alert.category = AlertCategory.PRICE
    with pytest.raises(InvalidAlertError):
        evaluator.evaluate(alert)


def test_service_defaults_to_real_dependencies():
    from engines.news.engine import NewsEngine
    evaluator = NewsAlertEvaluator()
    assert isinstance(evaluator.news_engine, NewsEngine)
