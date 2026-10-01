"""
OptiTrade Technical Engine — volatility analyzer (Bollinger Bands + ATR).

Reads only already-resolved Feature Store values (bollinger_percent_b,
bollinger_bandwidth_pct, atr_pct). Bollinger %B drives *directional*
signal (reusing `core/scoring.py`'s exact thresholds); bandwidth (a
squeeze indicator) and ATR% are magnitude-only and never move the
direction — `engine.py` reads `atr_pct` directly for
`expected_volatility`, not through this analyzer's signal.
"""
from __future__ import annotations

from typing import Dict, List

from engines.technical.config import FEATURE_ATR_PCT, FEATURE_BB_BANDWIDTH, FEATURE_BB_PERCENT_B
from engines.technical.models import AnalyzerResult

ANALYZER_NAME = "volatility"


def _percent_b_component(pb: float) -> float:
    if pb < -0.05:
        return 1.0
    if pb < 0.15:
        return 0.4
    if pb > 1.05:
        return -1.0
    if pb > 0.85:
        return -0.4
    return 0.0


def analyze(features: Dict[str, float]) -> AnalyzerResult:
    components: List[float] = []
    evidence: List[str] = []
    features_used: List[str] = []

    if FEATURE_BB_PERCENT_B in features:
        pb = features[FEATURE_BB_PERCENT_B]
        component = _percent_b_component(pb)
        components.append(component)
        features_used.append(FEATURE_BB_PERCENT_B)
        if component > 0:
            evidence.append(f"Price below Bollinger lower band (%B={pb:.2f}) - oversold")
        elif component < 0:
            evidence.append(f"Price above Bollinger upper band (%B={pb:.2f}) - overbought")

    if FEATURE_BB_BANDWIDTH in features:
        bandwidth = features[FEATURE_BB_BANDWIDTH]
        features_used.append(FEATURE_BB_BANDWIDTH)
        if bandwidth < 5.0:
            evidence.append(f"Bollinger squeeze (bandwidth {bandwidth:.1f}%) - breakout likely")

    if FEATURE_ATR_PCT in features:
        features_used.append(FEATURE_ATR_PCT)
        evidence.append(f"ATR {features[FEATURE_ATR_PCT]:.2f}% of price")

    if not components:
        return AnalyzerResult(
            analyzer_name=ANALYZER_NAME, signal=0.0, confidence=0.0,
            evidence=evidence, features_used=features_used,
        )

    signal = max(-1.0, min(1.0, sum(components) / len(components)))
    confidence = min(1.0, sum(abs(c) for c in components) / len(components))

    return AnalyzerResult(
        analyzer_name=ANALYZER_NAME, signal=signal, confidence=confidence,
        evidence=evidence, features_used=features_used,
    )
