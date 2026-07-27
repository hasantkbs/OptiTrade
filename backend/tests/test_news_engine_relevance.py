"""Tests for engines/news/relevance.py."""
from datetime import datetime, timezone

from engines.news import relevance
from engines.news.models import AssetResolution, NormalizedArticle


def _article(text: str) -> NormalizedArticle:
    return NormalizedArticle(
        title=text, summary="", published_at=datetime.now(timezone.utc), source="Reuters", text=text,
    )


def test_score_relevance_is_bounded_between_zero_and_one():
    resolution = AssetResolution(symbol="AAPL", is_relevant=True, confidence=1.0)
    score = relevance.score_relevance("AAPL", _article("AI breakthrough boosts chip demand"), resolution)
    assert 0.0 <= score <= 1.0


def test_score_relevance_higher_with_sector_keywords_than_without():
    resolution = AssetResolution(symbol="AAPL", is_relevant=True, confidence=0.7)
    on_topic = relevance.score_relevance(
        "AAPL", _article("AI breakthrough boosts chip demand and semiconductor shortage eases"), resolution,
    )
    off_topic = relevance.score_relevance("AAPL", _article("Local weather forecast for tomorrow"), resolution)
    assert on_topic > off_topic


def test_score_relevance_higher_with_higher_asset_resolution_confidence():
    article = _article("Local weather forecast for tomorrow")
    low_confidence = relevance.score_relevance("AAPL", article, AssetResolution(symbol="AAPL", is_relevant=True, confidence=0.0))
    high_confidence = relevance.score_relevance("AAPL", article, AssetResolution(symbol="AAPL", is_relevant=True, confidence=1.0))
    assert high_confidence > low_confidence


def test_keyword_universe_includes_macro_and_geopolitical_terms():
    all_pos, all_neg = relevance._keyword_universe("AAPL")
    assert any("fed" in kw or "rate" in kw for kw in all_pos + all_neg)
