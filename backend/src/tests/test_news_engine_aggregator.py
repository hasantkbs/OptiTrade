"""Tests for engines/news/aggregator.py."""
from datetime import datetime, timedelta, timezone

import pytest

from engines.news import aggregator
from engines.news.config import NewsEngineConfig
from engines.news.models import NormalizedArticle


def _article(text: str, hours_ago: float = 1.0, source: str = "Reuters") -> NormalizedArticle:
    published_at = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return NormalizedArticle(title=text, summary="", published_at=published_at, source=source, text=text)


def test_aggregate_with_no_articles_returns_neutral():
    result = aggregator.aggregate("AAPL", [], NewsEngineConfig(), raw_article_count=0, articles_after_dedup=0)
    assert result.signal == 0.0
    assert result.confidence == 0.0
    assert result.article_count == 0
    assert result.evidence == []


def test_aggregate_positive_article_produces_positive_signal():
    articles = [_article("Apple (AAPL) surges to record high on blowout earnings beat")]
    result = aggregator.aggregate("AAPL", articles, NewsEngineConfig(), raw_article_count=1, articles_after_dedup=1)
    assert result.signal > 0
    assert result.article_count == 1
    assert len(result.evidence) == 1


def test_aggregate_negative_article_produces_negative_signal():
    articles = [_article("Apple (AAPL) shares crash amid fraud investigation and lawsuit")]
    result = aggregator.aggregate("AAPL", articles, NewsEngineConfig(), raw_article_count=1, articles_after_dedup=1)
    assert result.signal < 0


def test_aggregate_excludes_articles_older_than_max_age_days():
    config = NewsEngineConfig(max_age_days=7)
    old_article = _article("Apple (AAPL) surges to record high on blowout earnings", hours_ago=24 * 30)
    result = aggregator.aggregate("AAPL", [old_article], config, raw_article_count=1, articles_after_dedup=1)
    assert result.article_count == 0
    assert result.signal == 0.0


def test_aggregate_recent_high_impact_outweighs_older_low_impact():
    config = NewsEngineConfig()
    recent_strong_positive = _article(
        "Apple (AAPL) stock soars to all-time high on record blowout earnings beat", hours_ago=1,
    )
    old_weak_negative = _article("Apple (AAPL) shares dip slightly amid mixed investor sentiment", hours_ago=24 * 6)
    result = aggregator.aggregate(
        "AAPL", [recent_strong_positive, old_weak_negative], config, raw_article_count=2, articles_after_dedup=2,
    )
    assert result.signal > 0


def test_aggregate_all_neutral_articles_gives_zero_signal_but_nonzero_evidence():
    articles = [_article("The company held its annual shareholder meeting today")]
    result = aggregator.aggregate("AAPL", articles, NewsEngineConfig(), raw_article_count=1, articles_after_dedup=1)
    assert result.signal == 0.0
    assert result.article_count == 1


def test_aggregate_confidence_increases_with_more_articles():
    config = NewsEngineConfig(min_articles_for_full_confidence=5)
    one_article = [_article("Apple (AAPL) surges on record earnings beat")]
    five_articles = [_article(f"Apple (AAPL) surges on record earnings beat number {i}") for i in range(5)]
    result_one = aggregator.aggregate("AAPL", one_article, config, raw_article_count=1, articles_after_dedup=1)
    result_five = aggregator.aggregate("AAPL", five_articles, config, raw_article_count=5, articles_after_dedup=5)
    assert result_five.confidence >= result_one.confidence


def test_aggregate_signal_is_clamped_to_valid_range():
    articles = [_article("Apple (AAPL) surges to record high on blowout earnings beat")] * 3
    result = aggregator.aggregate("AAPL", articles, NewsEngineConfig(), raw_article_count=3, articles_after_dedup=3)
    assert -1.0 <= result.signal <= 1.0


def test_aggregate_preserves_raw_and_dedup_counts_for_telemetry():
    articles = [_article("Apple (AAPL) surges on record earnings beat")]
    result = aggregator.aggregate("AAPL", articles, NewsEngineConfig(), raw_article_count=10, articles_after_dedup=1)
    assert result.raw_article_count == 10
    assert result.articles_after_dedup == 1


# ── as_of (point-in-time backfill support) ──────────────────────────────

def test_aggregate_as_of_scores_relative_to_the_given_moment_not_real_now():
    """A historical backfill's article - old relative to real "now",
    but fresh relative to the historical as_of it's being scored for -
    must not be excluded just because real wall-clock time has moved
    on. See scripts/backfill_news_features.py, this parameter's only
    other caller."""
    historical_as_of = datetime.now(timezone.utc) - timedelta(days=200)
    article = NormalizedArticle(
        title="Apple (AAPL) surges to record high on blowout earnings beat",
        summary="", published_at=historical_as_of - timedelta(hours=1), source="Reuters",
        text="Apple (AAPL) surges to record high on blowout earnings beat",
    )
    result = aggregator.aggregate(
        "AAPL", [article], NewsEngineConfig(), raw_article_count=1, articles_after_dedup=1,
        as_of=historical_as_of,
    )
    assert result.article_count == 1
    assert result.signal > 0


def test_aggregate_as_of_still_excludes_articles_older_than_max_age_days_relative_to_as_of():
    historical_as_of = datetime.now(timezone.utc) - timedelta(days=200)
    config = NewsEngineConfig(max_age_days=7)
    article = NormalizedArticle(
        title="Apple (AAPL) surges to record high on blowout earnings beat",
        summary="", published_at=historical_as_of - timedelta(days=30), source="Reuters",
        text="Apple (AAPL) surges to record high on blowout earnings beat",
    )
    result = aggregator.aggregate(
        "AAPL", [article], config, raw_article_count=1, articles_after_dedup=1, as_of=historical_as_of,
    )
    assert result.article_count == 0


def test_aggregate_defaults_as_of_to_real_now_when_omitted():
    """Zero behavior change for the live caller (engines/news/
    feature_adapter.py), which never passes as_of."""
    recent_article = _article("Apple (AAPL) surges to record high on blowout earnings beat", hours_ago=1)
    result = aggregator.aggregate(
        "AAPL", [recent_article], NewsEngineConfig(), raw_article_count=1, articles_after_dedup=1,
    )
    assert result.article_count == 1
