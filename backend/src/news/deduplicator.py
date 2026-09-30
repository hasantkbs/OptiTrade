"""
Deduplicator stage — marks near-duplicate items (same normalized-title
hash, e.g. the same story re-published by multiple sources) so downstream
stages can skip them cheaply.
"""
from __future__ import annotations

from typing import List, Set

from news.models import NewsItemContext


class NewsDeduplicator:
    def deduplicate(self, items: List[NewsItemContext]) -> List[NewsItemContext]:
        seen: Set[str] = set()
        for item in items:
            if item.content_hash in seen:
                item.is_duplicate = True
            else:
                seen.add(item.content_hash)
        return items
