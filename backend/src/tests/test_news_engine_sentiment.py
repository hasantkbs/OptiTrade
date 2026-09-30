"""Tests for engines/news/sentiment.py."""
from datetime import datetime, timezone

from engines.news import sentiment
from engines.news.models import NormalizedArticle


def _article(text: str) -> NormalizedArticle:
    return NormalizedArticle(
        title=text, summary="", published_at=datetime.now(timezone.utc), source="Reuters", text=text,
    )


def test_score_sentiment_positive_text():
    score, keywords = sentiment.score_sentiment(_article("Company shares surge to record high on blowout earnings"))
    assert score > 0
    assert keywords


def test_score_sentiment_negative_text():
    score, keywords = sentiment.score_sentiment(_article("Company shares crash amid fraud investigation"))
    assert score < 0
    assert keywords


def test_score_sentiment_neutral_text_with_no_keywords():
    score, keywords = sentiment.score_sentiment(_article("The company held its annual meeting"))
    assert score == 0.0
    assert keywords == []


def test_score_sentiment_matches_core_news_analyzer_directly():
    from core.news_analyzer import analyze_sentiment

    text = "Stock soars after record earnings beat"
    article = _article(text)
    assert sentiment.score_sentiment(article) == analyze_sentiment(text)
