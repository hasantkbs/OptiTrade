"""
OptiTrade Technical Engine — orchestrator.

Runs all six analyzer modules (trend, momentum, oscillator, volatility,
volume, market_structure) against Feature Store-resolved values only,
combines their confidence-weighted signals into one prediction, and
produces both the engine's own rich `TechnicalAnalysisResult` and a
`decision_engine.models.EngineVote` (satisfying
`decision_engine.interfaces.VotingEngineProtocol` for Decision Engine
consumption).

Self-registers a lazy instance into `engine_registry.registry.
default_registry` on import (see `engines/technical/__init__.py`) — the
instance defers constructing a `TechnicalFeatureAdapter`/
`FeatureStoreService` (and thus any real database connection) until
`analyze()`/`vote()` is actually called, so importing this module never
opens a network connection as a side effect.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Tuple

from core.structured_logging import STATUS_SUCCESS, log_event
from decision_engine.models import EngineVote, Prediction
from engines.technical import market_structure, momentum, oscillator, trend, volatility, volume
from engines.technical.config import FEATURE_ATR_PCT, TechnicalEngineConfig
from engines.technical.feature_adapter import TechnicalFeatureAdapter
from engines.technical.models import AnalyzerResult, TechnicalAnalysisResult, TechnicalExecutionMetadata

logger = logging.getLogger(__name__)

_ANALYZER_MODULES = [trend, momentum, oscillator, volatility, volume, market_structure]


class TechnicalEngine:
    """Standalone Technical voting engine. Satisfies
    `decision_engine.interfaces.VotingEngineProtocol` via `vote()`."""

    def __init__(
        self,
        feature_adapter: Optional[TechnicalFeatureAdapter] = None,
        config: Optional[TechnicalEngineConfig] = None,
    ) -> None:
        self.config = config or TechnicalEngineConfig.from_env()
        self.engine_name = "TechnicalEngine"
        self.engine_version = self.config.engine_version
        self._feature_adapter = feature_adapter

    @property
    def feature_adapter(self) -> TechnicalFeatureAdapter:
        if self._feature_adapter is None:
            self._feature_adapter = TechnicalFeatureAdapter(config=self.config)
        return self._feature_adapter

    def analyze(self, symbol: str) -> TechnicalAnalysisResult:
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
        atr_pct = features.get(FEATURE_ATR_PCT, 0.0)
        net_signal = self._net_signal(results)
        expected_return = net_signal * atr_pct * self.config.expected_return_scale
        expected_volatility = atr_pct

        evidence = [item for result in results for item in result.evidence]
        feature_importance = self._feature_importance(results)

        execution_metadata = TechnicalExecutionMetadata(
            total_duration_ms=(time.perf_counter() - started_at) * 1000,
            analyzer_durations_ms=analyzer_durations_ms,
            features_from_cache=resolution.from_cache,
            features_computed_fresh=resolution.computed_fresh,
        )

        analysis = TechnicalAnalysisResult(
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
            logger, component="technical_engine", module="engines.technical.engine",
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

    def _feature_importance(self, results: List[AnalyzerResult]) -> Dict[str, float]:
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
