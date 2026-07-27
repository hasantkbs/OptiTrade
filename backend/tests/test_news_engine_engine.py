"""Tests for engines/news/engine.py (NewsEngine orchestrator)."""
from datetime import datetime, timezone

import pytest

from decision_engine.interfaces import VotingEngineProtocol
from decision_engine.models import Prediction
from decision_engine.registry import VotingEngineRegistry
from decision_engine.validation import validate_vote
from engine_registry.registry import default_registry
from engines.news import NewsEngine
from engines.news.config import NewsEngineConfig
from engines.news.models import AggregatedNewsSignal, NewsEvidence


def _evidence(sentiment: float, source: str = "Reuters") -> NewsEvidence:
    return NewsEvidence(
        source=source, timestamp=datetime.now(timezone.utc), title="A headline about the company",
        summary="A short summary.", sentiment=sentiment, relevance=0.8, impact=abs(sentiment), confidence=0.9,
    )


class FakeFeatureAdapter:
    def __init__(self, result: AggregatedNewsSignal):
        self._result = result

    def get_analysis(self, symbol: str) -> AggregatedNewsSignal:
        return self._result


def _engine(result: AggregatedNewsSignal) -> NewsEngine:
    return NewsEngine(feature_adapter=FakeFeatureAdapter(result), config=NewsEngineConfig())


def _signal(signal: float, confidence: float = 0.8, article_count: int = 1, impact: float = 0.5) -> AggregatedNewsSignal:
    evidence = [_evidence(signal)] if article_count else []
    return AggregatedNewsSignal(
        signal=signal, confidence=confidence, relevance=0.8, impact=impact,
        article_count=article_count, raw_article_count=article_count, articles_after_dedup=article_count,
        evidence=evidence,
    )


def test_no_news_produces_neutral_hold():
    result = _engine(_signal(0.0, confidence=0.0, article_count=0, impact=0.0)).analyze("AAPL")
    assert result.prediction == Prediction.HOLD
    assert result.confidence == 0.0
    assert result.expected_return == 0.0
    assert result.article_count == 0


def test_strongly_positive_signal_produces_buy():
    result = _engine(_signal(0.8, confidence=0.9, impact=0.8)).analyze("AAPL")
    assert result.prediction == Prediction.BUY
    assert result.expected_return > 0
    assert result.confidence == 0.9


def test_strongly_negative_signal_produces_sell():
    result = _engine(_signal(-0.8, confidence=0.9, impact=0.8)).analyze("AAPL")
    assert result.prediction == Prediction.SELL
    assert result.expected_return < 0


def test_signal_within_dead_zone_produces_hold():
    result = _engine(_signal(0.05, confidence=0.5, impact=0.05)).analyze("AAPL")
    assert result.prediction == Prediction.HOLD


def test_expected_volatility_scales_with_impact_when_news_present():
    config = NewsEngineConfig()
    low_impact = _engine(_signal(0.3, impact=0.1)).analyze("AAPL").expected_volatility
    high_impact = _engine(_signal(0.3, impact=0.9)).analyze("AAPL").expected_volatility
    assert high_impact > low_impact
    assert low_impact >= config.min_expected_volatility_pct


def test_expected_volatility_defaults_when_no_articles():
    config = NewsEngineConfig()
    result = _engine(_signal(0.0, confidence=0.0, article_count=0, impact=0.0)).analyze("AAPL")
    assert result.expected_volatility == pytest.approx(config.default_expected_volatility_pct)


def test_structured_evidence_preserved_on_analysis_result():
    result = _engine(_signal(0.5)).analyze("AAPL")
    assert len(result.structured_evidence) == 1
    assert isinstance(result.structured_evidence[0], NewsEvidence)


def test_evidence_strings_are_human_readable_and_capped():
    config = NewsEngineConfig(max_evidence_strings=2)
    signal = AggregatedNewsSignal(
        signal=0.5, confidence=0.8, relevance=0.8, impact=0.5, article_count=3,
        raw_article_count=3, articles_after_dedup=3,
        evidence=[_evidence(0.5, source=f"Source{i}") for i in range(3)],
    )
    engine = NewsEngine(feature_adapter=FakeFeatureAdapter(signal), config=config)
    result = engine.analyze("AAPL")
    assert len(result.evidence) == 2
    assert all(isinstance(e, str) for e in result.evidence)
    assert "Source0" in result.evidence[0]


def test_execution_metadata_reports_pipeline_counts():
    signal = _signal(0.3)
    result = _engine(signal).analyze("AAPL")
    assert result.execution_metadata.raw_article_count == 1
    assert result.execution_metadata.articles_after_dedup == 1
    assert result.execution_metadata.articles_in_aggregation == 1


def test_vote_adapts_analysis_into_a_valid_engine_vote():
    engine = _engine(_signal(0.8, impact=0.8))
    vote = engine.vote("AAPL")
    assert vote.engine_name == "NewsEngine"
    assert vote.engine_version == "v1"
    assert vote.prediction == Prediction.BUY
    assert validate_vote(vote).is_valid is True


def test_feature_adapter_property_is_lazy_and_cached():
    engine = NewsEngine()
    assert engine._feature_adapter is None
    first = engine.feature_adapter
    second = engine.feature_adapter
    assert first is second


# ─────────────────────────────────────────────────────────────────────────
# Decision Engine contract + Engine Registry integration
# ─────────────────────────────────────────────────────────────────────────

def test_news_engine_satisfies_voting_engine_protocol():
    assert isinstance(NewsEngine(), VotingEngineProtocol)


def test_news_engine_self_registered_into_the_default_engine_registry():
    registered = default_registry.get("NewsEngine", "v1")
    assert isinstance(registered, NewsEngine)


def test_reimporting_the_package_does_not_raise_on_duplicate_registration():
    from engine_registry.exceptions import DuplicateEngineError

    with pytest.raises(DuplicateEngineError):
        default_registry.register(NewsEngine())

    import importlib

    import engines.news as news_package

    importlib.reload(news_package)


# ─────────────────────────────────────────────────────────────────────────
# Real, live end-to-end (network + Feature Store + Decision Engine)
# ─────────────────────────────────────────────────────────────────────────

def test_real_end_to_end_vote_for_a_real_company():
    engine = NewsEngine()
    vote = engine.vote("AAPL")
    assert vote.engine_name == "NewsEngine"
    assert validate_vote(vote).is_valid is True
    _cleanup_aapl(engine)


def test_real_end_to_end_through_the_decision_engine():
    from decision_engine.config import DecisionEngineConfig
    from decision_engine.repository import PostgresExecutionRepository
    from decision_engine.service import DecisionEngine
    from feature_store.config import FeatureStoreConfig

    news_engine = NewsEngine()
    registry = VotingEngineRegistry()
    registry.register(news_engine)

    repository = PostgresExecutionRepository(config=FeatureStoreConfig.from_env())
    decision_engine = DecisionEngine(
        registry=registry, feature_store=news_engine.feature_adapter.feature_store,
        execution_repository=repository, config=DecisionEngineConfig(),
    )

    output = decision_engine.decide("AAPL")
    assert output.symbol == "AAPL"
    assert len(output.engine_results) == 1
    assert output.engine_results[0].engine_name == "NewsEngine"

    conn = repository._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM decision_engine_executions WHERE symbol = %s", ("AAPL",))
    finally:
        repository._pool.putconn(conn)
    repository.close()
    _cleanup_aapl(news_engine)


def _cleanup_aapl(engine: NewsEngine) -> None:
    from engines.news.config import ALL_FEATURE_NAMES

    conn = engine.feature_adapter.feature_store.offline_store._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", ("AAPL",))
    finally:
        engine.feature_adapter.feature_store.offline_store._pool.putconn(conn)
    for name in ALL_FEATURE_NAMES:
        engine.feature_adapter.feature_store.online_store._client.delete(f"feature_store:AAPL:{name}")
