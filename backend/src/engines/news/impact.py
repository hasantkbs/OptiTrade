"""
OptiTrade News Engine — impact scoring.

`core.news_adapter.NewsSentimentAdapter._classify_impact` already
derives a categorical HIGH/MEDIUM/LOW impact level from sentiment
magnitude for LLM-prompt use; this module reuses that same classifier
for a human-readable label, but additionally exposes a continuous
`[0, 1]` impact score - not available anywhere in the existing
codebase - since the aggregator needs a continuous multiplier (not a
3-bucket label) to weight recent, high-impact articles above old,
low-impact ones.

Impact is deliberately derived from sentiment magnitude ALONE
(independent of relevance/recency) so it can be combined multiplicatively
with relevance and age-decay in `aggregator.py` without double-counting
either factor.
"""
from __future__ import annotations

from core.news_adapter import NewsSentimentAdapter


def score_impact(sentiment_score: float) -> float:
    """Continuous `[0, 1]` impact magnitude derived purely from sentiment
    strength."""
    return max(0.0, min(1.0, abs(sentiment_score)))


def impact_label(sentiment_score: float) -> str:
    """Categorical HIGH/MEDIUM/LOW label, reusing the existing
    classifier unchanged."""
    return NewsSentimentAdapter._classify_impact(sentiment_score)
