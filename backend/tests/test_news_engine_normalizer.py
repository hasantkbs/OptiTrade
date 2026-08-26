"""Tests for engines/news/normalizer.py."""
from datetime import datetime, timezone

from engines.news import normalizer
from engines.news.models import RawArticle


def test_normalize_strips_whitespace():
    article = RawArticle(title="  Title  ", summary="  Summary  ", published_at=datetime.now(timezone.utc), source="  Reuters  ")
    normalized = normalizer.normalize(article)
    assert normalized.title == "Title"
    assert normalized.summary == "Summary"
    assert normalized.source == "Reuters"


def test_normalize_combines_title_and_summary_into_text():
    article = RawArticle(title="Title", summary="Summary", published_at=datetime.now(timezone.utc), source="Reuters")
    normalized = normalizer.normalize(article)
    assert normalized.text == "Title. Summary"


def test_normalize_text_is_just_title_when_no_summary():
    article = RawArticle(title="Title", summary="", published_at=datetime.now(timezone.utc), source="Reuters")
    normalized = normalizer.normalize(article)
    assert normalized.text == "Title"


def test_normalize_adds_utc_timezone_when_naive():
    naive = datetime(2026, 1, 1, 12, 0, 0)
    article = RawArticle(title="Title", published_at=naive, source="Reuters")
    normalized = normalizer.normalize(article)
    assert normalized.published_at.tzinfo is not None


def test_normalize_defaults_blank_source_to_unknown():
    article = RawArticle(title="Title", published_at=datetime.now(timezone.utc), source="   ")
    normalized = normalizer.normalize(article)
    assert normalized.source == "Unknown"


def test_normalize_all_drops_blank_titles():
    articles = [
        RawArticle(title="Real Title", published_at=datetime.now(timezone.utc), source="Reuters"),
        RawArticle(title="   ", published_at=datetime.now(timezone.utc), source="Reuters"),
    ]
    normalized = normalizer.normalize_all(articles)
    assert len(normalized) == 1
    assert normalized[0].title == "Real Title"


def test_normalize_all_empty_input():
    assert normalizer.normalize_all([]) == []
