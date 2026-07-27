"""
OptiTrade News Engine — orchestrator.

Runs the full pipeline (via `feature_adapter.py`) against live news
data, converts the resulting `AggregatedNewsSignal` into both the
engine's own rich `NewsAnalysisResult` and a
`decision_engine.models.EngineVote` (satisfying
`decision_engine.interfaces.VotingEngineProtocol`).

Fully deterministic and statistical - this engine never calls an LLM
and never lets one influence `prediction`/`confidence`/`expected_return`/
`expected_volatility`. Any future LLM-based explanation of this engine's
output belongs entirely outside this package (see
`decision_engine/models.py`'s module docstring: LLMs are explanation
engines only, they never vote).

Self-registers a lazy instance into `engine_registry.registry.
default_registry` on import (see `engines/news/__init__.py`).
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from core.structured_logging import STATUS_SUCCESS, log_event
from decision_engine.models import EngineVote, Prediction
from engines.news.config import NewsEngineConfig
from engines.news.feature_adapter import NewsFeatureAdapter
from engines.news.models import AggregatedNewsSignal, NewsAnalysisResult, NewsEvidence, NewsExecutionMetadata

logger = logging.getLogger(__name__)


class NewsEngine:
    """Standalone News voting engine. Satisfies
    `decision_engine.interfaces.VotingEngineProtocol` via `vote()`."""

    def __init__(
        self,
        feature_adapter: Optional[NewsFeatureAdapter] = None,
        config: Optional[NewsEngineConfig] = None,
    ) -> None:
        self.config = config or NewsEngineConfig.from_env()
        self.engine_name = "NewsEngine"
        self.engine_version = self.config.engine_version
        self._feature_adapter = feature_adapter

    @property
    def feature_adapter(self) -> NewsFeatureAdapter:
        if self._feature_adapter is None:
            self._feature_adapter = NewsFeatureAdapter(config=self.config)
        return self._feature_adapter

    def analyze(self, symbol: str) -> NewsAnalysisResult:
        started_at = time.perf_counter()
        result = self.feature_adapter.get_analysis(symbol)

        prediction = self._predict(result.signal)
        expected_return = result.signal * self.config.expected_return_scale_pct
        expected_volatility = self._expected_volatility(result)
        evidence_strings = [
            self._evidence_to_string(item) for item in result.evidence[: self.config.max_evidence_strings]
        ]

        execution_metadata = NewsExecutionMetadata(
            total_duration_ms=(time.perf_counter() - started_at) * 1000,
            raw_article_count=result.raw_article_count,
            articles_after_dedup=result.articles_after_dedup,
            articles_in_aggregation=result.article_count,
        )

        analysis = NewsAnalysisResult(
            symbol=symbol,
            prediction=prediction,
            confidence=result.confidence,
            expected_return=expected_return,
            expected_volatility=expected_volatility,
            evidence=evidence_strings,
            structured_evidence=result.evidence,
            relevance=result.relevance,
            impact=result.impact,
            article_count=result.article_count,
            execution_metadata=execution_metadata,
        )
        log_event(
            logger, component="news_engine", module="engines.news.engine",
            operation="analyze", status=STATUS_SUCCESS, symbol=symbol,
            prediction=prediction.value, confidence=result.confidence,
            execution_time_ms=execution_metadata.total_duration_ms,
        )
        return analysis

    def vote(self, symbol: str) -> EngineVote:
        analysis = self.analyze(symbol)
        return EngineVote(
            engine_name=self.engine_name,
            engine_version=self.engine_version,
            prediction=analysis.prediction,
            confidence=analysis.confidence,
            expected_return=analysis.expected_return,
            volatility=analysis.expected_volatility,
            evidence=analysis.evidence,
            timestamp=analysis.timestamp,
        )

    def _predict(self, signal: float) -> Prediction:
        if signal > self.config.decision_threshold:
            return Prediction.BUY
        if signal < -self.config.decision_threshold:
            return Prediction.SELL
        return Prediction.HOLD

    def _expected_volatility(self, result: AggregatedNewsSignal) -> float:
        """No news at all means no article-driven volatility signal, so
        the configured baseline default is used; otherwise volatility
        scales with impact - high-impact news implies a larger expected
        price swing regardless of direction."""
        if result.article_count == 0:
            return self.config.default_expected_volatility_pct
        return max(
            self.config.min_expected_volatility_pct,
            result.impact * self.config.max_expected_volatility_pct,
        )

    @staticmethod
    def _evidence_to_string(evidence: NewsEvidence) -> str:
        return (
            f"[{evidence.source}] \"{evidence.title[:80]}\" - sentiment {evidence.sentiment:+.2f}, "
            f"impact {evidence.impact:.2f}, relevance {evidence.relevance:.2f} "
            f"({evidence.timestamp.date().isoformat()})"
        )
