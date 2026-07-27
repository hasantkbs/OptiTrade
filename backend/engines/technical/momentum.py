"""
OptiTrade Technical Engine — momentum analyzer.

Reads only already-resolved Feature Store values (macd_line,
macd_signal_line, macd_histogram, roc_10_pct). Thresholds reuse
`core/scoring.py`'s existing MACD crossover/histogram-momentum logic and
ROC tiers (>15/>5 strong/mild, symmetric on the downside).
"""
from __future__ import annotations

from typing import Dict, List

from engines.technical.config import (
    FEATURE_MACD_HISTOGRAM,
    FEATURE_MACD_LINE,
    FEATURE_MACD_SIGNAL,
    FEATURE_ROC,
)
from engines.technical.models import AnalyzerResult

ANALYZER_NAME = "momentum"


def _roc_component(value: float) -> float:
    if value > 15:
        return 1.0
    if value > 5:
        return 0.5
    if value < -15:
        return -1.0
    if value < -5:
        return -0.5
    return 0.0


def analyze(features: Dict[str, float]) -> AnalyzerResult:
    components: List[float] = []
    evidence: List[str] = []
    features_used: List[str] = []

    if FEATURE_MACD_LINE in features and FEATURE_MACD_SIGNAL in features:
        macd_line = features[FEATURE_MACD_LINE]
        macd_signal = features[FEATURE_MACD_SIGNAL]
        features_used.extend([FEATURE_MACD_LINE, FEATURE_MACD_SIGNAL])
        crossover_component = 0.6 if macd_line > macd_signal else -0.6
        components.append(crossover_component)
        evidence.append(
            "MACD above signal line - bullish momentum" if macd_line > macd_signal
            else "MACD below signal line - bearish momentum"
        )

        if FEATURE_MACD_HISTOGRAM in features:
            macd_hist = features[FEATURE_MACD_HISTOGRAM]
            features_used.append(FEATURE_MACD_HISTOGRAM)
            threshold = 0.05 * abs(macd_line if macd_line else 0.001)
            if macd_hist > threshold:
                components.append(0.3)
                evidence.append("MACD histogram accelerating upward")
            elif macd_hist < -threshold:
                components.append(-0.3)
                evidence.append("MACD histogram accelerating downward")

    if FEATURE_ROC in features:
        roc = features[FEATURE_ROC]
        component = _roc_component(roc)
        components.append(component)
        features_used.append(FEATURE_ROC)
        if component > 0:
            evidence.append(f"Rate of change +{roc:.1f}% - strong upward momentum")
        elif component < 0:
            evidence.append(f"Rate of change {roc:.1f}% - strong downward momentum")

    if not components:
        return AnalyzerResult(analyzer_name=ANALYZER_NAME, signal=0.0, confidence=0.0)

    signal = max(-1.0, min(1.0, sum(components) / len(components)))
    confidence = min(1.0, sum(abs(c) for c in components) / len(components))

    return AnalyzerResult(
        analyzer_name=ANALYZER_NAME, signal=signal, confidence=confidence,
        evidence=evidence, features_used=features_used,
    )
