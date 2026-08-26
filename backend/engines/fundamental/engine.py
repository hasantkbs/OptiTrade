"""
OptiTrade Fundamental Engine — orchestrator.

Runs all six analyzer modules (valuation, growth, profitability,
financial_health, cashflow, quality) against Feature Store-resolved
values only, combines their confidence-weighted signals into one
prediction, and produces both the engine's own rich
`FundamentalAnalysisResult` and a `decision_engine.models.EngineVote`
(satisfying `decision_engine.interfaces.VotingEngineProtocol`).

Self-registers a lazy instance into `engine_registry.registry.
default_registry` on import (see `engines/fundamental/__init__.py`).
"""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Tuple

from core.structured_logging import STATUS_SUCCESS, log_event
from decision_engine.models import EngineVote, Prediction
from engines.fundamental import cashflow, financial_health, growth, profitability, quality, valuation
from engines.fundamental.config import FEATURE_MARGIN_STABILITY, FundamentalEngineConfig
from engines.fundamental.feature_adapter import FundamentalFeatureAdapter
from engines.fundamental.models import AnalyzerResult, FundamentalAnalysisResult, FundamentalExecutionMetadata

logger = logging.getLogger(__name__)

_ANALYZER_MODULES = [valuation, growth, profitability, financial_health, cashflow, quality]

_DEFAULT_EXPECTED_VOLATILITY_PCT = 15.0
_MAX_VOLATILITY_FROM_INSTABILITY_PCT = 20.0


class FundamentalEngine:
    """Standalone Fundamental voting engine. Satisfies
    `decision_engine.interfaces.VotingEngineProtocol` via `vote()`."""

    def __init__(
        self,
        feature_adapter: Optional[FundamentalFeatureAdapter] = None,
        config: Optional[FundamentalEngineConfig] = None,
    ) -> None:
        self.config = config or FundamentalEngineConfig.from_env()
        self.engine_name = "FundamentalEngine"
        self.engine_version = self.config.engine_version
        self._feature_adapter = feature_adapter

    @property
    def feature_adapter(self) -> FundamentalFeatureAdapter:
        if self._feature_adapter is None:
            self._feature_adapter = FundamentalFeatureAdapter(config=self.config)
        return self._feature_adapter

    def analyze(self, symbol: str) -> FundamentalAnalysisResult:
        started_at = time.perf_counter()
        resolution = self.feature_adapter.get_features(symbol)
        features = resolution.values

        results: List[AnalyzerResult] = []
        analyzer_durations_ms: Dict[str, float] = {}
        for module in _ANALYZER_MODULES:
            analyzer_started_at = time.perf_counter()
            result = module.analyze(features)
            analyzer_durations_ms[result.analyzer_name] = (time.perf_counter() - analyzer_started_at) * 1000
            results.append(result)

        prediction, confidence = self._combine(results)
        net_signal = self._net_signal(results)
        expected_return = net_signal * self.config.expected_return_scale_pct
        expected_volatility = self._expected_volatility(features)

        evidence = [item for result in results for item in result.evidence]
        feature_importance = self._feature_importance(results)

        execution_metadata = FundamentalExecutionMetadata(
            total_duration_ms=(time.perf_counter() - started_at) * 1000,
            analyzer_durations_ms=analyzer_durations_ms,
            features_from_cache=resolution.from_cache,
            features_computed_fresh=resolution.computed_fresh,
        )

        analysis = FundamentalAnalysisResult(
            symbol=symbol,
            prediction=prediction,
            confidence=confidence,
            expected_return=expected_return,
            expected_volatility=expected_volatility,
            evidence=evidence,
            feature_importance=feature_importance,
            execution_metadata=execution_metadata,
        )
        log_event(
            logger, component="fundamental_engine", module="engines.fundamental.engine",
            operation="analyze", status=STATUS_SUCCESS, symbol=symbol,
            prediction=prediction.value, confidence=confidence,
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

    def _net_signal(self, results: List[AnalyzerResult]) -> float:
        total_confidence = sum(result.confidence for result in results)
        if total_confidence == 0:
            return 0.0
        weighted_sum = sum(result.signal * result.confidence for result in results)
        return max(-1.0, min(1.0, weighted_sum / total_confidence))

    def _combine(self, results: List[AnalyzerResult]) -> Tuple[Prediction, float]:
        net_signal = self._net_signal(results)
        overall_confidence = (
            min(1.0, sum(result.confidence for result in results) / len(results)) if results else 0.0
        )
        if net_signal > self.config.decision_threshold:
            prediction = Prediction.BUY
        elif net_signal < -self.config.decision_threshold:
            prediction = Prediction.SELL
        else:
            prediction = Prediction.HOLD
        return prediction, overall_confidence

    @staticmethod
    def _expected_volatility(features: Dict[str, float]) -> float:
        """Fundamentals have no natural per-period volatility measure the
        way price ATR does for the Technical Engine - margin stability
        (how much net margins have swung across recent years) is used as
        a real, data-derived proxy when available; otherwise a
        configured baseline is used."""
        stability = features.get(FEATURE_MARGIN_STABILITY)
        if stability is None:
            return _DEFAULT_EXPECTED_VOLATILITY_PCT
        return (1.0 - stability) * _MAX_VOLATILITY_FROM_INSTABILITY_PCT

    @staticmethod
    def _feature_importance(results: List[AnalyzerResult]) -> Dict[str, float]:
        raw: Dict[str, float] = {}
        for result in results:
            if not result.features_used:
                continue
            magnitude = abs(result.signal) * result.confidence
            if magnitude == 0:
                continue
            share = magnitude / len(result.features_used)
            for feature_name in result.features_used:
                raw[feature_name] = raw.get(feature_name, 0.0) + share

        total = sum(raw.values())
        if total == 0:
            return raw
        return {name: value / total for name, value in raw.items()}
