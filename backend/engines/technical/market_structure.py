"""
OptiTrade Technical Engine — market structure analyzer (support/
resistance proximity + candlestick patterns).

Reads only already-resolved Feature Store values
(support_proximity_pct, resistance_proximity_pct, bullish_pattern_count,
bearish_pattern_count) — the underlying candlestick-pattern and
support/resistance detection itself is `core/pattern_scanner.
PatternScanner`, run once by `feature_adapter.py`.
"""
from __future__ import annotations

from typing import Dict, List

from engines.technical.config import (
    FEATURE_BEARISH_PATTERN_COUNT,
    FEATURE_BULLISH_PATTERN_COUNT,
    FEATURE_RESISTANCE_PROXIMITY,
    FEATURE_SUPPORT_PROXIMITY,
)
from engines.technical.models import AnalyzerResult

ANALYZER_NAME = "market_structure"

_PROXIMITY_THRESHOLD_PCT = 2.0  # within 2% of support/resistance is "close"


def analyze(features: Dict[str, float]) -> AnalyzerResult:
    components: List[float] = []
    evidence: List[str] = []
    features_used: List[str] = []

    support = features.get(FEATURE_SUPPORT_PROXIMITY)
    resistance = features.get(FEATURE_RESISTANCE_PROXIMITY)
    if support is not None and resistance is not None:
        features_used.extend([FEATURE_SUPPORT_PROXIMITY, FEATURE_RESISTANCE_PROXIMITY])
        # Closer to support than resistance, and genuinely close (within
        # threshold), is bullish (a bounce zone); the symmetric case near
        # resistance is bearish.
        if support < resistance and support <= _PROXIMITY_THRESHOLD_PCT:
            components.append(0.6)
            evidence.append(f"Price is {support:.1f}% above support - potential bounce zone")
        elif resistance < support and resistance <= _PROXIMITY_THRESHOLD_PCT:
            components.append(-0.6)
            evidence.append(f"Price is {resistance:.1f}% below resistance - potential rejection zone")

    bullish_count = features.get(FEATURE_BULLISH_PATTERN_COUNT)
    bearish_count = features.get(FEATURE_BEARISH_PATTERN_COUNT)
    if bullish_count is not None and bearish_count is not None:
        features_used.extend([FEATURE_BULLISH_PATTERN_COUNT, FEATURE_BEARISH_PATTERN_COUNT])
        if bullish_count > bearish_count:
            components.append(min(1.0, 0.4 * bullish_count))
            evidence.append(f"{int(bullish_count)} bullish candlestick pattern(s) detected")
        elif bearish_count > bullish_count:
            components.append(-min(1.0, 0.4 * bearish_count))
            evidence.append(f"{int(bearish_count)} bearish candlestick pattern(s) detected")

    if not components:
        return AnalyzerResult(
            analyzer_name=ANALYZER_NAME, signal=0.0, confidence=0.0,
            features_used=features_used,
        )

    signal = max(-1.0, min(1.0, sum(components) / len(components)))
    confidence = min(1.0, sum(abs(c) for c in components) / len(components))

    return AnalyzerResult(
        analyzer_name=ANALYZER_NAME, signal=signal, confidence=confidence,
        evidence=evidence, features_used=features_used,
    )
