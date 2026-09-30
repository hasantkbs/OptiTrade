"""
OptiTrade News Engine — deduplicator.

`core.news_analyzer` never deduplicates - the same story frequently
appears from multiple wire syndication sources with near-identical
titles, which would otherwise let one real-world event cast multiple
votes in the aggregation. This is genuinely new capability (not
duplicating any existing function): near-duplicate titles are detected
via `difflib.SequenceMatcher` and only the first (earliest-listed)
occurrence of each is kept.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import List

from engines.news.models import NormalizedArticle


def _is_near_duplicate(title_a: str, title_b: str, threshold: float) -> bool:
    return SequenceMatcher(None, title_a, title_b).ratio() >= threshold


def deduplicate(
    articles: List[NormalizedArticle], similarity_threshold: float = 0.9
) -> List[NormalizedArticle]:
    seen_titles: List[str] = []
    unique: List[NormalizedArticle] = []
    for article in articles:
        title_lower = article.title.lower()
        if any(_is_near_duplicate(title_lower, seen, similarity_threshold) for seen in seen_titles):
            continue
        seen_titles.append(title_lower)
        unique.append(article)
    return unique
