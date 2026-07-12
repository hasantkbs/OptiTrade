"""
Sentiment stage — thin adapter around core.news_analyzer.analyze_sentiment(),
the existing financial-lexicon sentiment engine identified as reusable.
Kept as its own stage so it can be swapped for a model-based sentiment
engine later without touching the rest of the pipeline.
"""
from __future__ import annotations

from typing import List, Tuple

from core.news_analyzer import analyze_sentiment


class LexiconSentimentAnalyzer:
    def analyze(self, text: str) -> Tuple[float, List[str]]:
        return analyze_sentiment(text)
