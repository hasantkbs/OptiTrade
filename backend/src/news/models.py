"""
Data models for the OptiTrade News Intelligence Pipeline.

NewsItemContext is threaded through every stage.  Each stage reads the
fields it needs and fills in the fields it owns; nothing is recomputed by
a later stage.  This keeps every stage independently testable: construct
a context with only the upstream fields populated, run one stage, assert
on the fields it added.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


@dataclass
class RawNewsItem:
    """Unprocessed news item exactly as returned by a provider."""
    title:        str
    summary:      str
    published_at: datetime
    source:       str
    url:          Optional[str] = None


class EntityType(str, Enum):
    TICKER  = "TICKER"
    COMPANY = "COMPANY"
    SECTOR  = "SECTOR"
    MACRO   = "MACRO"


@dataclass(frozen=True)
class Entity:
    """A single entity recognized in a news item's text."""
    text:        str
    entity_type: EntityType
    symbol:      Optional[str] = None  # resolved ticker, for TICKER/COMPANY
    sector:      Optional[str] = None  # sector code, for SECTOR/MACRO


class EventType(str, Enum):
    """
    Financial event taxonomy.  Deliberately source-agnostic: SEC filings,
    Reddit, X, earnings calendars, and economic calendars should all be
    able to classify into this same set.
    """
    EARNINGS_BEAT     = "EARNINGS_BEAT"
    EARNINGS_MISS     = "EARNINGS_MISS"
    MERGER            = "MERGER"
    ACQUISITION       = "ACQUISITION"
    BANKRUPTCY        = "BANKRUPTCY"
    DIVIDEND          = "DIVIDEND"
    RATE_DECISION     = "RATE_DECISION"
    PRODUCT_RELEASE   = "PRODUCT_RELEASE"
    REGULATION        = "REGULATION"
    SEC_INVESTIGATION = "SEC_INVESTIGATION"
    HACK              = "HACK"
    TOKEN_UNLOCK      = "TOKEN_UNLOCK"
    ETF_APPROVAL      = "ETF_APPROVAL"
    UNCLASSIFIED      = "UNCLASSIFIED"


@dataclass(frozen=True)
class FinancialEvent:
    """
    Lightweight, source-agnostic event classification.

    Kept minimal on purpose so future data sources (SEC filings, Reddit,
    X, earnings/economic calendars) can produce the same shape without
    depending on any news-specific field.
    """
    event_type:       EventType
    confidence:       float                       # [0, 1]
    matched_keywords: List[str] = field(default_factory=list)
    severity:         float = 0.3                  # [0, 1]


@dataclass
class NewsItemContext:
    """Threaded state for one news item as it moves through the pipeline."""
    raw: RawNewsItem

    # Normalizer
    text:         str = ""
    content_hash: str = ""

    # Deduplicator
    is_duplicate: bool = False

    # Entity Extraction
    entities: List[Entity] = field(default_factory=list)

    # Asset Resolver
    resolved_symbols: List[str] = field(default_factory=list)
    mentions_target:  bool = False

    # Relevance
    relevance_score: float = 0.0   # [0, 1]

    # Impact
    impact_score: float = 0.0      # [0, 1]

    # Event Classification
    event: Optional[FinancialEvent] = None

    # Sentiment
    sentiment_score:    float = 0.0    # [-1, 1]
    sentiment_keywords: List[str] = field(default_factory=list)
