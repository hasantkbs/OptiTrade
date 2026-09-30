"""Tests for engines/news/asset_resolver.py."""
from datetime import datetime, timezone

from engines.news import asset_resolver
from engines.news.models import NormalizedArticle


def _article(text: str) -> NormalizedArticle:
    return NormalizedArticle(
        title=text, summary="", published_at=datetime.now(timezone.utc), source="Reuters", text=text,
    )


def test_resolve_high_confidence_when_symbol_mentioned():
    resolution = asset_resolver.resolve("AAPL", _article("Apple (AAPL) beats earnings"))
    assert resolution.is_relevant is True
    assert resolution.confidence == 1.0


def test_resolve_lower_confidence_when_symbol_not_mentioned():
    resolution = asset_resolver.resolve("AAPL", _article("Tech sector rallies broadly"))
    assert resolution.is_relevant is True
    assert resolution.confidence == 0.7


def test_resolve_recognizes_cashtag_form():
    resolution = asset_resolver.resolve("AAPL", _article("Traders bullish on $AAPL today"))
    assert resolution.confidence == 1.0


def test_resolve_strips_market_suffix_before_matching():
    resolution = asset_resolver.resolve("GARAN.IS", _article("GARAN shares rise on strong results"))
    assert resolution.confidence == 1.0


def test_resolve_is_case_insensitive():
    resolution = asset_resolver.resolve("AAPL", _article("aapl surges after earnings beat"))
    assert resolution.confidence == 1.0
