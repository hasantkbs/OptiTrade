"""Tests for engines/news/deduplicator.py."""
from datetime import datetime, timezone

from engines.news import deduplicator
from engines.news.models import NormalizedArticle


def _article(title: str, source: str = "Reuters") -> NormalizedArticle:
    return NormalizedArticle(
        title=title, summary="", published_at=datetime.now(timezone.utc), source=source, text=title,
    )


def test_deduplicate_keeps_all_when_titles_distinct():
    articles = [_article("Apple beats earnings"), _article("Tesla stock falls")]
    result = deduplicator.deduplicate(articles)
    assert len(result) == 2


def test_deduplicate_removes_exact_duplicate_titles():
    articles = [_article("Apple beats earnings", "Reuters"), _article("Apple beats earnings", "Bloomberg")]
    result = deduplicator.deduplicate(articles)
    assert len(result) == 1
    assert result[0].source == "Reuters"


def test_deduplicate_removes_near_duplicate_titles():
    articles = [
        _article("Apple beats earnings expectations this quarter"),
        _article("Apple beats earnings expectations this quarter!!"),
    ]
    result = deduplicator.deduplicate(articles, similarity_threshold=0.9)
    assert len(result) == 1


def test_deduplicate_keeps_dissimilar_titles_below_threshold():
    articles = [_article("Apple beats earnings"), _article("Apple faces lawsuit over patents")]
    result = deduplicator.deduplicate(articles, similarity_threshold=0.9)
    assert len(result) == 2


def test_deduplicate_empty_input():
    assert deduplicator.deduplicate([]) == []


def test_deduplicate_is_case_insensitive():
    articles = [_article("Apple Beats Earnings"), _article("apple beats earnings")]
    result = deduplicator.deduplicate(articles)
    assert len(result) == 1
