"""
Impact stage — estimates how much a news item could move the target
symbol's price.

Runs before Event Classification in the approved pipeline order, so it
deliberately does not depend on the event type/severity — only on
relevance, recency, and how concretely the item is tied to a tradeable
symbol.  Recency reuses core.news_analyzer._age_weight(), the existing
age-decay curve, rather than redefining thresholds.
"""
from __future__ import annotations

from core.news_analyzer import _age_weight
from news.models import NewsItemContext


class ImpactScorer:
    def score(self, item: NewsItemContext) -> float:
        recency = _age_weight(item.raw.published_at)
        specificity = (
            1.0 if item.mentions_target else
            0.6 if item.resolved_symbols else
            0.3
        )
        impact = item.relevance_score * recency * specificity
        return round(min(1.0, max(0.0, impact)), 4)
