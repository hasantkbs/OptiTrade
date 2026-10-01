"""Tests for engines/news/feature_adapter.py."""
from datetime import datetime, timezone

from engines.news.config import (
    ALL_FEATURE_NAMES,
    FEATURE_NEWS_ARTICLE_COUNT,
    FEATURE_NEWS_CONFIDENCE,
    FEATURE_NEWS_IMPACT,
    FEATURE_NEWS_RELEVANCE,
    FEATURE_NEWS_SENTIMENT,
    NewsEngineConfig,
)
from engines.news.feature_adapter import NewsFeatureAdapter
from engines.news.models import RawArticle
from feature_store.service import FeatureStoreService


def _cleanup(feature_store: FeatureStoreService, symbol: str) -> None:
    conn = feature_store.offline_store._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", (symbol,))
    finally:
        feature_store.offline_store._pool.putconn(conn)
    for name in ALL_FEATURE_NAMES:
        feature_store.online_store._client.delete(f"feature_store:{symbol}:{name}")


def test_get_analysis_runs_full_pipeline_and_persists_features(monkeypatch):
    fake_articles = [
        RawArticle(
            title="Apple (AAPL) surges to record high on blowout earnings",
            summary="Shares soared after strong quarterly results.",
            published_at=datetime.now(timezone.utc), source="Reuters",
        ),
    ]
    monkeypatch.setattr("engines.news.feature_adapter.providers.fetch_raw_articles", lambda symbol, max_articles: fake_articles)

    feature_store = FeatureStoreService()
    adapter = NewsFeatureAdapter(feature_store=feature_store, config=NewsEngineConfig())
    try:
        result = adapter.get_analysis("AAPL")
        assert result.article_count == 1
        assert result.signal > 0

        persisted_sentiment = feature_store.get_latest_feature("AAPL", FEATURE_NEWS_SENTIMENT)
        assert persisted_sentiment is not None
        assert persisted_sentiment.value == result.signal

        persisted_count = feature_store.get_latest_feature("AAPL", FEATURE_NEWS_ARTICLE_COUNT)
        assert persisted_count.value == 1.0
    finally:
        _cleanup(feature_store, "AAPL")


def test_get_analysis_persists_all_five_features(monkeypatch):
    monkeypatch.setattr("engines.news.feature_adapter.providers.fetch_raw_articles", lambda symbol, max_articles: [])
    feature_store = FeatureStoreService()
    adapter = NewsFeatureAdapter(feature_store=feature_store, config=NewsEngineConfig())
    try:
        adapter.get_analysis("AAPL")
        for name in [
            FEATURE_NEWS_SENTIMENT, FEATURE_NEWS_RELEVANCE, FEATURE_NEWS_IMPACT,
            FEATURE_NEWS_CONFIDENCE, FEATURE_NEWS_ARTICLE_COUNT,
        ]:
            assert feature_store.get_latest_feature("AAPL", name) is not None
    finally:
        _cleanup(feature_store, "AAPL")


def test_get_analysis_always_refetches_even_when_recently_persisted(monkeypatch):
    """The News Engine deliberately never gates fresh computation on
    Feature Store freshness (see NewsEngineConfig's docstring) -
    calling get_analysis twice in a row must call the provider twice."""
    call_count = {"n": 0}

    def fake_fetch(symbol, max_articles):
        call_count["n"] += 1
        return []

    monkeypatch.setattr("engines.news.feature_adapter.providers.fetch_raw_articles", fake_fetch)
    feature_store = FeatureStoreService()
    adapter = NewsFeatureAdapter(feature_store=feature_store, config=NewsEngineConfig())
    try:
        adapter.get_analysis("AAPL")
        adapter.get_analysis("AAPL")
        assert call_count["n"] == 2
    finally:
        _cleanup(feature_store, "AAPL")


def test_feature_adapter_defaults_to_real_feature_store_and_config():
    adapter = NewsFeatureAdapter()
    assert isinstance(adapter.feature_store, FeatureStoreService)
    assert isinstance(adapter.config, NewsEngineConfig)
