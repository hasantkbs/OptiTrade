"""
OptiTrade News Engine — sentiment scoring.

Reuses `core.news_analyzer.analyze_sentiment` unchanged - the financial
lexicon, negation/intensifier handling, and tanh normalization it
implements are the same proven algorithm `core/news_analyzer.py` already
uses in production; this module never reimplements or duplicates that
scoring.
"""
from __future__ import annotations

from typing import List, Tuple

from core.news_analyzer import analyze_sentiment as _core_analyze_sentiment
from engines.news.models import NormalizedArticle


def score_sentiment(article: NormalizedArticle) -> Tuple[float, List[str]]:
    """Returns `(sentiment_score [-1, +1], matched_keywords)` for one
    normalized article's combined title+summary text."""
    return _core_analyze_sentiment(article.text)
