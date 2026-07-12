"""
Relevance stage — scores how relevant a news item is to the target symbol,
combining a direct symbol/company mention with sector and macro/
geopolitical keyword overlap (reusing core.sector_mapper's sector
definitions rather than redefining them).
"""
from __future__ import annotations

from core.sector_mapper import get_sector
from news.models import EntityType, NewsItemContext


class RelevanceScorer:
    def score(self, item: NewsItemContext, target_symbol: str) -> float:
        if item.mentions_target:
            return 1.0

        target_sector = get_sector(target_symbol)
        matching_sector_hit = any(
            e.entity_type == EntityType.SECTOR and e.sector == target_sector
            for e in item.entities
        )
        other_sector_hit = any(
            e.entity_type == EntityType.SECTOR and e.sector != target_sector
            for e in item.entities
        )
        macro_hit = any(e.entity_type == EntityType.MACRO for e in item.entities)
        other_symbol_hit = bool(item.resolved_symbols)

        if matching_sector_hit:
            return 0.7
        if macro_hit:
            return 0.4
        if other_symbol_hit or other_sector_hit:
            return 0.15
        return 0.05
