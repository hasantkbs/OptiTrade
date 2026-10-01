"""
Entity Extraction stage — identifies tickers, companies, sectors, and
macro/geopolitical topics mentioned in a news item's text.

Sits between the Deduplicator and the Asset Resolver:
    Deduplicator -> [Entity Extraction] -> Asset Resolver

Interface
---------
EntityExtractor is a Protocol so this deterministic keyword implementation
can be replaced later by an NLP/LLM-backed extractor without touching any
caller — the Asset Resolver only depends on the List[Entity] shape, never
on how it was produced.
"""
from __future__ import annotations

import re
from typing import Dict, List, Protocol, runtime_checkable

from core.market_config import BIST_SYMBOLS, CRYPTO_SYMBOLS, US_SYMBOLS
from core.sector_mapper import SECTOR_KEYWORDS
from news.models import Entity, EntityType


@runtime_checkable
class EntityExtractor(Protocol):
    def extract(self, text: str) -> List[Entity]:
        ...


def _build_gazetteers() -> tuple[Dict[str, str], Dict[str, str]]:
    """Return (ticker -> symbol [case-sensitive], company name -> symbol)."""
    ticker_map: Dict[str, str] = {}
    company_map: Dict[str, str] = {}
    for table in (US_SYMBOLS, BIST_SYMBOLS, CRYPTO_SYMBOLS):
        for symbol, name in table.items():
            ticker_map[symbol] = symbol
            company_map[name.lower()] = symbol
    return ticker_map, company_map


_TICKER_MAP, _COMPANY_MAP = _build_gazetteers()

# sector/macro keyword phrase (lowercase) -> sector code
_SECTOR_KEYWORD_INDEX: Dict[str, str] = {
    kw.lower(): sector
    for sector, data in SECTOR_KEYWORDS.items()
    for bucket in ("positive", "negative")
    for kw in data.get(bucket, [])
}

_MACRO_SECTORS = {"MACRO", "GEOPOLITICAL"}


class DeterministicEntityExtractor:
    """
    Keyword/gazetteer-based entity extraction — no external NLP dependency.

    Recognizes:
      TICKER/COMPANY : known symbols and company names (core.market_config)
      SECTOR/MACRO    : sector-defining keyword phrases (core.sector_mapper)

    Tickers are matched case-sensitively against the original text (e.g.
    "GE", "V", "MA") to avoid false positives against common lowercase
    words; company names and keyword phrases are matched case-insensitively.
    """

    def extract(self, text: str) -> List[Entity]:
        if not text:
            return []

        entities: List[Entity] = []
        seen_symbols: set = set()

        for symbol in _TICKER_MAP:
            if symbol in seen_symbols:
                continue
            if re.search(rf"\b{re.escape(symbol)}\b", text):
                seen_symbols.add(symbol)
                entities.append(Entity(text=symbol, entity_type=EntityType.TICKER, symbol=symbol))

        lower = text.lower()
        for name, symbol in _COMPANY_MAP.items():
            if symbol in seen_symbols:
                continue
            if re.search(rf"\b{re.escape(name)}\b", lower):
                seen_symbols.add(symbol)
                entities.append(Entity(text=name, entity_type=EntityType.COMPANY, symbol=symbol))

        for phrase, sector in _SECTOR_KEYWORD_INDEX.items():
            if phrase in lower:
                entity_type = EntityType.MACRO if sector in _MACRO_SECTORS else EntityType.SECTOR
                entities.append(Entity(text=phrase, entity_type=entity_type, sector=sector))

        return entities
