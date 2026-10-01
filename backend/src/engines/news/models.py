"""
OptiTrade News Engine — domain models.

Mirrors the shape established in `engines/fundamental/models.py` /
`engines/technical/models.py` (rich native analysis result +
execution metadata) — kept as its own independent definitions rather
than importing across engine packages, since each voting engine is
required to be standalone.

The pipeline stage models (`RawArticle`, `NormalizedArticle`,
`AssetResolution`) exist so each stage
(providers -> normalizer -> deduplicator -> asset_resolver -> ... ->
aggregator) has a stable, typed handoff shape, independent of the
underlying `core.news_analyzer` dataclass shapes it reuses.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from pydantic import BaseModel, Field, field_validator

from decision_engine.models import Prediction


class RawArticle(BaseModel):
    """One article exactly as fetched from a news provider, before any
    normalization."""

    title: str
    summary: str = ""
    published_at: datetime
    source: str = "Unknown"


class NormalizedArticle(BaseModel):
    """A `RawArticle` after whitespace cleanup, timezone normalization,
    and combined-text derivation. The unit every later pipeline stage
    (deduplication, resolution, scoring) operates on."""

    title: str
    summary: str = ""
    published_at: datetime
    source: str
    text: str

    @field_validator("title")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value


class AssetResolution(BaseModel):
    """Whether/how strongly one normalized article is actually about the
    requested symbol (vs. only loosely associated by the provider)."""

    symbol: str
    is_relevant: bool
    confidence: float = Field(..., ge=0.0, le=1.0)


class NewsEvidence(BaseModel):
    """One article's fully-scored contribution to the aggregated
    signal. Every field required by the News Engine specification:
    source, timestamp, title, summary, sentiment, relevance, impact,
    confidence."""

    source: str
    timestamp: datetime
    title: str
    summary: str
    sentiment: float = Field(..., ge=-1.0, le=1.0)
    relevance: float = Field(..., ge=0.0, le=1.0)
    impact: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)


class AggregatedNewsSignal(BaseModel):
    """The aggregator's output: one time-decay-weighted composite signal
    across every (deduplicated, resolved, scored) article, plus the
    structured evidence behind it."""

    signal: float = Field(..., ge=-1.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    relevance: float = Field(..., ge=0.0, le=1.0)
    impact: float = Field(..., ge=0.0, le=1.0)
    article_count: int = Field(..., ge=0)
    raw_article_count: int = Field(..., ge=0)
    articles_after_dedup: int = Field(..., ge=0)
    evidence: List[NewsEvidence] = Field(default_factory=list)


class NewsExecutionMetadata(BaseModel):
    """The engine's own internal telemetry for one `analyze()` call."""

    total_duration_ms: float
    raw_article_count: int = Field(..., ge=0)
    articles_after_dedup: int = Field(..., ge=0)
    articles_in_aggregation: int = Field(..., ge=0)


class NewsAnalysisResult(BaseModel):
    """The News Engine's full, native output for one symbol."""

    symbol: str
    prediction: Prediction
    confidence: float = Field(..., ge=0.0, le=1.0)
    expected_return: float
    expected_volatility: float
    evidence: List[str] = Field(default_factory=list)
    structured_evidence: List[NewsEvidence] = Field(default_factory=list)
    relevance: float = Field(..., ge=0.0, le=1.0)
    impact: float = Field(..., ge=0.0, le=1.0)
    article_count: int = Field(..., ge=0)
    execution_metadata: NewsExecutionMetadata
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
