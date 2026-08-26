"""
OptiTrade Technical Engine — trend analyzer.

Reads only already-resolved Feature Store values (trend_strength_pct,
ema_crossover_signal) — never touches price data or `core.indicators`
directly; `feature_adapter.py` is the only place that does that.
Thresholds reuse the exact tiers already established in
`core/scoring.py` (>8/>3 strong/mild trend strength; GOLDEN_CROSS/
DEATH_CROSS vs. BULLISH/BEARISH for EMA crossover), just re-expressed as
a normalized [-1, +1] signal instead of raw score deltas.
"""
from __future__ import annotations

from typing import Dict, List

from engines.technical.config import FEATURE_EMA_CROSSOVER, FEATURE_TREND_STRENGTH
from engines.technical.models import AnalyzerResult

ANALYZER_NAME = "trend"


def _trend_strength_component(value: float) -> float:
    if value > 8:
        return 1.0
    if value > 3:
        return 0.5
    if value < -8:
        return -1.0
    if value < -3:
        return -0.5
    return 0.0


def analyze(features: Dict[str, float]) -> AnalyzerResult:
    components: List[float] = []
    evidence: List[str] = []
    features_used: List[str] = []

    if FEATURE_TREND_STRENGTH in features:
        trend_strength = features[FEATURE_TREND_STRENGTH]
        component = _trend_strength_component(trend_strength)
        components.append(component)
        features_used.append(FEATURE_TREND_STRENGTH)
        if component > 0:
            evidence.append(f"Price is {trend_strength:.1f}% above its EMA20 - bullish trend")
        elif component < 0:
            evidence.append(f"Price is {abs(trend_strength):.1f}% below its EMA20 - bearish trend")

    if FEATURE_EMA_CROSSOVER in features:
        encoded = features[FEATURE_EMA_CROSSOVER]
        component = encoded / 2.0
        components.append(component)
        features_used.append(FEATURE_EMA_CROSSOVER)
        if encoded == 2.0:
            evidence.append("EMA 20/50 golden cross - strong bullish signal")
        elif encoded == 1.0:
            evidence.append("EMA fast above slow - bullish bias")
        elif encoded == -1.0:
            evidence.append("EMA fast below slow - bearish bias")
        elif encoded == -2.0:
            evidence.append("EMA 20/50 death cross - strong bearish signal")

    if not components:
        return AnalyzerResult(analyzer_name=ANALYZER_NAME, signal=0.0, confidence=0.0)

    signal = max(-1.0, min(1.0, sum(components) / len(components)))
    confidence = min(1.0, sum(abs(c) for c in components) / len(components))

    return AnalyzerResult(
        analyzer_name=ANALYZER_NAME, signal=signal, confidence=confidence,
        evidence=evidence, features_used=features_used,
    )
