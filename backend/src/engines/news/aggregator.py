"""
OptiTrade News Engine — aggregator.

Combines every deduplicated, resolved article into one time-decay
weighted composite signal. Reuses `core.news_analyzer._age_weight`
unchanged for the actual decay curve (< 6h -> 1.0, < 24h -> 0.8,
< 3d -> 0.5, < 7d -> 0.3, > 7d -> 0.1) rather than reimplementing decay
math - the same bucketed curve already used in production by
`analyze_news`.

Per-article aggregation weight is `impact * relevance * age_weight`:
impact and age_weight are independent factors (see `impact.py`'s
docstring), so their product means a recent, high-impact article always
outweighs an old, low-impact one - satisfying the requirement that
"recent high-impact news must influence the prediction more than older
low-impact news" and that "older news must decay automatically."
Articles older than `config.max_age_days` are excluded entirely (mirrors
`analyze_news`'s own `max_age_days` cutoff).

Fully deterministic: no randomness, no LLM calls - the same article set
always produces the same composite signal.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from core.news_analyzer import _age_weight as _core_age_weight
from engines.news import asset_resolver, impact, relevance, sentiment
from engines.news.config import NewsEngineConfig
from engines.news.models import AggregatedNewsSignal, NewsEvidence, NormalizedArticle

_MIN_CONFIDENCE_FLOOR = 0.3


def aggregate(
    symbol: str,
    articles: List[NormalizedArticle],
    config: NewsEngineConfig,
    raw_article_count: int,
    articles_after_dedup: int,
) -> AggregatedNewsSignal:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=config.max_age_days)

    evidence: List[NewsEvidence] = []
    weighted_sentiments: List[float] = []
    weights: List[float] = []
    relevances: List[float] = []
    impacts: List[float] = []

    for article in articles:
        if article.published_at < cutoff:
            continue

        resolution = asset_resolver.resolve(symbol, article)
        sentiment_score, _keywords = sentiment.score_sentiment(article)
        age_weight = _core_age_weight(article.published_at, now)
        article_relevance = relevance.score_relevance(symbol, article, resolution)
        article_impact = impact.score_impact(sentiment_score)
        article_confidence = max(
            0.0, min(1.0, article_relevance * (_MIN_CONFIDENCE_FLOOR + (1 - _MIN_CONFIDENCE_FLOOR) * age_weight))
        )

        weight = article_impact * article_relevance * age_weight
        weighted_sentiments.append(sentiment_score * weight)
        weights.append(weight)
        relevances.append(article_relevance)
        impacts.append(article_impact)

        evidence.append(
            NewsEvidence(
                source=article.source, timestamp=article.published_at, title=article.title,
                summary=article.summary, sentiment=sentiment_score, relevance=article_relevance,
                impact=article_impact, confidence=article_confidence,
            )
        )

    if not evidence:
        return AggregatedNewsSignal(
            signal=0.0, confidence=0.0, relevance=0.0, impact=0.0, article_count=0,
            raw_article_count=raw_article_count, articles_after_dedup=articles_after_dedup, evidence=[],
        )

    total_weight = sum(weights)
    signal = (sum(weighted_sentiments) / total_weight) if total_weight > 0 else 0.0
    signal = max(-1.0, min(1.0, signal))

    avg_relevance = sum(relevances) / len(relevances)
    avg_impact = sum(impacts) / len(impacts)
    sufficiency = min(1.0, len(evidence) / config.min_articles_for_full_confidence)
    confidence = max(0.0, min(1.0, avg_relevance * sufficiency))

    return AggregatedNewsSignal(
        signal=signal, confidence=confidence, relevance=avg_relevance, impact=avg_impact,
        article_count=len(evidence), raw_article_count=raw_article_count,
        articles_after_dedup=articles_after_dedup, evidence=evidence,
    )
