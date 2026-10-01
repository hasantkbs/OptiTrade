"""
OptiTrade News Engine — normalizer.

Cleans up a `RawArticle` into a `NormalizedArticle`: strips whitespace,
guarantees a timezone-aware `published_at` (mirrors the exact tz-aware
check `core.news_analyzer.analyze_news` performs inline on each item),
and derives the combined `title. summary` text every downstream scoring
stage (sentiment, relevance) reads.
"""
from __future__ import annotations

from datetime import timezone
from typing import List

from engines.news.models import NormalizedArticle, RawArticle


def normalize(article: RawArticle) -> NormalizedArticle:
    published_at = article.published_at
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)

    title = article.title.strip()
    summary = (article.summary or "").strip()
    source = (article.source or "").strip() or "Unknown"
    text = f"{title}. {summary}" if summary else title

    return NormalizedArticle(
        title=title, summary=summary, published_at=published_at, source=source, text=text,
    )


def normalize_all(articles: List[RawArticle]) -> List[NormalizedArticle]:
    """Normalizes every article, silently dropping any with a blank
    title (no usable text to score)."""
    normalized = []
    for article in articles:
        if not article.title or not article.title.strip():
            continue
        normalized.append(normalize(article))
    return normalized
