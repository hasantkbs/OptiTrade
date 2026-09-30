"""
OptiTrade News Engine — Feature Store adapter.

The ONLY module in this engine allowed to run the raw provider fetch.
Unlike `engines/technical/feature_adapter.py` and
`engines/fundamental/feature_adapter.py`, this adapter does NOT use the
Feature Store as a read-through freshness cache before computing - see
`NewsEngineConfig`'s docstring: an article's `age_weight` decays
continuously, so a scalar written even a few minutes ago is already
stale in a way a cached technical indicator is not. Every call always
runs the live pipeline (fetch -> normalize -> dedupe -> aggregate), then
persists the derived scalars to the Feature Store afterwards for
downstream consumers and historical tracking.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from engines.news import aggregator, deduplicator, normalizer, providers
from engines.news.config import (
    FEATURE_NEWS_ARTICLE_COUNT,
    FEATURE_NEWS_CONFIDENCE,
    FEATURE_NEWS_IMPACT,
    FEATURE_NEWS_RELEVANCE,
    FEATURE_NEWS_SENTIMENT,
    NewsEngineConfig,
)
from engines.news.models import AggregatedNewsSignal
from feature_store.models import FeatureValue
from feature_store.service import FeatureStoreService, get_default_feature_store_service

logger = logging.getLogger(__name__)


class NewsFeatureAdapter:
    """Bridges the Feature Store with the News Engine pipeline.
    Constructed lazily by `engine.py::NewsEngine` so merely
    importing/registering the engine never opens a database
    connection."""

    def __init__(
        self,
        feature_store: Optional[FeatureStoreService] = None,
        config: Optional[NewsEngineConfig] = None,
    ) -> None:
        self.feature_store = feature_store or get_default_feature_store_service()
        self.config = config or NewsEngineConfig.from_env()

    def get_analysis(self, symbol: str) -> AggregatedNewsSignal:
        started_at = time.perf_counter()

        raw_articles = providers.fetch_raw_articles(symbol, max_articles=self.config.max_articles)
        normalized = normalizer.normalize_all(raw_articles)
        deduped = deduplicator.deduplicate(normalized, self.config.dedup_similarity_threshold)

        result = aggregator.aggregate(
            symbol, deduped, self.config,
            raw_article_count=len(raw_articles), articles_after_dedup=len(deduped),
        )
        self._persist(symbol, result)

        log_event(
            logger, component="news_engine", module="engines.news.feature_adapter",
            operation="get_analysis", status=STATUS_SUCCESS, symbol=symbol,
            raw_article_count=len(raw_articles), articles_after_dedup=len(deduped),
            articles_in_aggregation=result.article_count,
            execution_time_ms=(time.perf_counter() - started_at) * 1000,
        )
        return result

    def _persist(self, symbol: str, result: AggregatedNewsSignal) -> None:
        values = {
            FEATURE_NEWS_SENTIMENT: result.signal,
            FEATURE_NEWS_RELEVANCE: result.relevance,
            FEATURE_NEWS_IMPACT: result.impact,
            FEATURE_NEWS_CONFIDENCE: result.confidence,
            FEATURE_NEWS_ARTICLE_COUNT: float(result.article_count),
        }
        for name, value in values.items():
            self.feature_store.write_feature(FeatureValue(symbol=symbol, feature_name=name, value=value))
