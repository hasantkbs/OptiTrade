"""Tests for engines/news/providers.py."""
from datetime import datetime, timezone

from engines.news import providers


def test_fetch_raw_articles_maps_yfinance_shape(monkeypatch):
    fake_items = [
        {"title": "Title 1", "summary": "Summary 1", "published_at": datetime.now(timezone.utc), "source": "Reuters"},
        {"title": "Title 2", "summary": "", "published_at": datetime.now(timezone.utc), "source": "Yahoo Finance"},
    ]
    monkeypatch.setattr(
        "engines.news.providers._fetch_yfinance_news",
        lambda symbol, max_news=15: fake_items,
    )
    articles = providers.fetch_raw_articles("AAPL", max_articles=15)
    assert len(articles) == 2
    assert articles[0].title == "Title 1"
    assert articles[0].source == "Reuters"
    assert articles[1].summary == ""


def test_fetch_raw_articles_returns_empty_list_when_no_news(monkeypatch):
    monkeypatch.setattr("engines.news.providers._fetch_yfinance_news", lambda symbol, max_news=15: [])
    assert providers.fetch_raw_articles("AAPL") == []


def test_fetch_raw_articles_passes_max_articles_through(monkeypatch):
    captured = {}

    def fake_fetch(symbol, max_news=15):
        captured["max_news"] = max_news
        return []

    monkeypatch.setattr("engines.news.providers._fetch_yfinance_news", fake_fetch)
    providers.fetch_raw_articles("AAPL", max_articles=5)
    assert captured["max_news"] == 5


def test_real_fetch_raw_articles_for_a_real_company():
    articles = providers.fetch_raw_articles("AAPL", max_articles=5)
    assert isinstance(articles, list)
    for article in articles:
        assert article.title
