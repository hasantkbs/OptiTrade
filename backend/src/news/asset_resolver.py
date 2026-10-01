"""
Asset Resolver stage — maps extracted entities to concrete tradeable
symbols, so Relevance/Impact can reason about whether a news item concerns
the symbol currently being analyzed.

AssetResolver is a Protocol so a smarter resolver (e.g. disambiguating
"Apple" the company from "apple" the fruit via context, or resolving ADRs
/ multiple share classes) can replace this one later without touching the
pipeline.
"""
from __future__ import annotations

from typing import List, Protocol, runtime_checkable

from news.models import Entity, EntityType


@runtime_checkable
class AssetResolver(Protocol):
    def resolve(self, entities: List[Entity], target_symbol: str) -> List[str]:
        ...


class SymbolAssetResolver:
    """Resolves TICKER/COMPANY entities into a flat, deduplicated symbol list."""

    def resolve(self, entities: List[Entity], target_symbol: str) -> List[str]:
        symbols = {
            e.symbol for e in entities
            if e.symbol and e.entity_type in (EntityType.TICKER, EntityType.COMPANY)
        }
        return sorted(symbols)
