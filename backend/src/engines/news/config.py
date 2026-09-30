"""
OptiTrade News Engine — configuration.

Centralizes the Feature Store feature names this engine writes, and the
runtime tuning parameters every pipeline module (providers, aggregator,
engine) shares.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

FEATURE_NEWS_SENTIMENT = "news_sentiment_score"
FEATURE_NEWS_RELEVANCE = "news_relevance_score"
FEATURE_NEWS_IMPACT = "news_impact_score"
FEATURE_NEWS_CONFIDENCE = "news_confidence_score"
FEATURE_NEWS_ARTICLE_COUNT = "news_article_count"

ALL_FEATURE_NAMES = [
    FEATURE_NEWS_SENTIMENT, FEATURE_NEWS_RELEVANCE, FEATURE_NEWS_IMPACT,
    FEATURE_NEWS_CONFIDENCE, FEATURE_NEWS_ARTICLE_COUNT,
]


@dataclass(frozen=True)
class NewsEngineConfig:
    """Runtime settings for the whole News Engine pipeline.

    Unlike the Technical/Fundamental engines, this engine does NOT use
    the Feature Store as a read-through freshness cache: an article's
    effective weight (`age_weight`, see `core.news_analyzer._age_weight`)
    decays continuously with elapsed time, so a scalar cached an hour
    ago is already stale in a way a cached RSI value is not. The Feature
    Store here is write-only persistence for downstream consumers and
    historical tracking; every `analyze()`/`vote()` call always
    recomputes the live, decay-adjusted aggregate.
    """

    max_articles: int = 15
    max_age_days: int = 7
    decision_threshold: float = 0.2
    expected_return_scale_pct: float = 8.0
    default_expected_volatility_pct: float = 20.0
    max_expected_volatility_pct: float = 35.0
    min_expected_volatility_pct: float = 10.0
    min_articles_for_full_confidence: int = 5
    dedup_similarity_threshold: float = 0.9
    max_evidence_strings: int = 8
    engine_version: str = "v1"

    @classmethod
    def from_env(cls) -> "NewsEngineConfig":
        load_dotenv()
        return cls(
            max_articles=int(os.getenv("NEWS_ENGINE_MAX_ARTICLES", "15")),
            max_age_days=int(os.getenv("NEWS_ENGINE_MAX_AGE_DAYS", "7")),
            decision_threshold=float(os.getenv("NEWS_ENGINE_DECISION_THRESHOLD", "0.2")),
            expected_return_scale_pct=float(os.getenv("NEWS_ENGINE_EXPECTED_RETURN_SCALE_PCT", "8.0")),
            default_expected_volatility_pct=float(
                os.getenv("NEWS_ENGINE_DEFAULT_EXPECTED_VOLATILITY_PCT", "20.0")
            ),
            max_expected_volatility_pct=float(
                os.getenv("NEWS_ENGINE_MAX_EXPECTED_VOLATILITY_PCT", "35.0")
            ),
            min_expected_volatility_pct=float(
                os.getenv("NEWS_ENGINE_MIN_EXPECTED_VOLATILITY_PCT", "10.0")
            ),
            min_articles_for_full_confidence=int(
                os.getenv("NEWS_ENGINE_MIN_ARTICLES_FOR_FULL_CONFIDENCE", "5")
            ),
            dedup_similarity_threshold=float(
                os.getenv("NEWS_ENGINE_DEDUP_SIMILARITY_THRESHOLD", "0.9")
            ),
            max_evidence_strings=int(os.getenv("NEWS_ENGINE_MAX_EVIDENCE_STRINGS", "8")),
            engine_version=os.getenv("NEWS_ENGINE_VERSION", "v1"),
        )
