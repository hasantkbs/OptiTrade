"""
News Intelligence Pipeline — orchestrates all stages in the approved order:

    Provider -> Normalizer -> Deduplicator -> Entity Extraction
        -> Asset Resolver -> Relevance -> Impact -> Event Classification
        -> Sentiment

Produces a List[NewsItemContext], fully enriched, ready for
signals.news.NewsSignalEngine to convert into Signal objects.

This pipeline is entirely separate from core.news_analyzer.analyze_news(),
which remains the source of the iOS-facing `news_analysis` response and is
untouched by this module.
"""
from __future__ import annotations

from typing import List, Optional

from news.asset_resolver import AssetResolver, SymbolAssetResolver
from news.deduplicator import NewsDeduplicator
from news.entity_extraction import DeterministicEntityExtractor, EntityExtractor
from news.event_classification import EventClassifier
from news.impact import ImpactScorer
from news.models import NewsItemContext
from news.normalizer import NewsNormalizer
from news.provider import NewsProvider, YFinanceNewsProvider
from news.relevance import RelevanceScorer
from news.sentiment import LexiconSentimentAnalyzer


class NewsPipeline:
    """
    Wires all pipeline stages together.  Provider, entity extractor, and
    asset resolver are injectable (Protocols) so tests and future data
    sources can swap them without changing this orchestrator.
    """

    def __init__(
        self,
        provider: Optional[NewsProvider] = None,
        entity_extractor: Optional[EntityExtractor] = None,
        asset_resolver: Optional[AssetResolver] = None,
    ) -> None:
        self._provider          = provider or YFinanceNewsProvider()
        self._normalizer        = NewsNormalizer()
        self._deduplicator      = NewsDeduplicator()
        self._entity_extractor  = entity_extractor or DeterministicEntityExtractor()
        self._asset_resolver    = asset_resolver or SymbolAssetResolver()
        self._relevance         = RelevanceScorer()
        self._impact            = ImpactScorer()
        self._event_classifier  = EventClassifier()
        self._sentiment         = LexiconSentimentAnalyzer()

    def run(self, symbol: str, max_items: int = 15) -> List[NewsItemContext]:
        raw_items = self._provider.fetch(symbol, max_items=max_items)

        items = [self._normalizer.normalize(raw) for raw in raw_items]
        items = self._deduplicator.deduplicate(items)

        target_upper = symbol.upper()
        results: List[NewsItemContext] = []

        for item in items:
            if item.is_duplicate:
                continue

            item.entities = self._entity_extractor.extract(item.text)
            item.resolved_symbols = self._asset_resolver.resolve(item.entities, symbol)
            item.mentions_target = target_upper in {s.upper() for s in item.resolved_symbols}

            item.relevance_score = self._relevance.score(item, symbol)
            item.impact_score    = self._impact.score(item)
            item.event           = self._event_classifier.classify(item.text)

            item.sentiment_score, item.sentiment_keywords = self._sentiment.analyze(item.text)

            results.append(item)

        return results
