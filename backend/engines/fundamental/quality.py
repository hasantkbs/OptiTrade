"""
OptiTrade Fundamental Engine — business quality analyzer.

Reads only already-resolved Feature Store values
(earnings_consistency_score, margin_stability_score,
capital_efficiency_pct, balance_sheet_quality_score) — all four are
already normalized (0-1, or a percentage of comparable scale) by
`feature_adapter.py` from multi-year statement data.
"""
from __future__ import annotations

from typing import Dict, List

from engines.fundamental.config import (
    FEATURE_BALANCE_SHEET_QUALITY,
    FEATURE_CAPITAL_EFFICIENCY,
    FEATURE_EARNINGS_CONSISTENCY,
    FEATURE_MARGIN_STABILITY,
)
from engines.fundamental.models import AnalyzerResult

ANALYZER_NAME = "quality"


def _score_component(value: float, strong: float, mild: float, weak: float, bad: float) -> float:
    if value > strong:
        return 0.3
    if value > mild:
        return 0.1
    if value < bad:
        return -0.3
    if value < weak:
        return -0.1
    return 0.0


def analyze(features: Dict[str, float]) -> AnalyzerResult:
    components: List[float] = []
    evidence: List[str] = []
    features_used: List[str] = []

    if FEATURE_EARNINGS_CONSISTENCY in features:
        value = features[FEATURE_EARNINGS_CONSISTENCY]
        component = _score_component(value, 0.9, 0.7, 0.5, 0.3)
        components.append(component)
        features_used.append(FEATURE_EARNINGS_CONSISTENCY)
        if component > 0:
            evidence.append(f"Earnings consistency {value:.0%} of years profitable")
        elif component < 0:
            evidence.append(f"Earnings consistency only {value:.0%} of years profitable")

    if FEATURE_MARGIN_STABILITY in features:
        value = features[FEATURE_MARGIN_STABILITY]
        component = _score_component(value, 0.8, 0.6, 0.4, 0.2)
        components.append(component)
        features_used.append(FEATURE_MARGIN_STABILITY)
        if component > 0:
            evidence.append("Net margins have been stable across recent years")
        elif component < 0:
            evidence.append("Net margins have swung significantly across recent years")

    if FEATURE_CAPITAL_EFFICIENCY in features:
        value = features[FEATURE_CAPITAL_EFFICIENCY]
        component = _score_component(value, 100.0, 50.0, 35.0, 20.0)
        components.append(component)
        features_used.append(FEATURE_CAPITAL_EFFICIENCY)
        if component > 0:
            evidence.append(f"Asset turnover of {value:.0f}% - efficient use of assets")
        elif component < 0:
            evidence.append(f"Asset turnover of {value:.0f}% - inefficient use of assets")

    if FEATURE_BALANCE_SHEET_QUALITY in features:
        value = features[FEATURE_BALANCE_SHEET_QUALITY]
        component = _score_component(value, 0.7, 0.5, 0.35, 0.2)
        components.append(component)
        features_used.append(FEATURE_BALANCE_SHEET_QUALITY)
        if component > 0:
            evidence.append("Balance sheet is lightly leveraged relative to assets")
        elif component < 0:
            evidence.append("Balance sheet carries heavy debt relative to assets")

    if not components:
        return AnalyzerResult(analyzer_name=ANALYZER_NAME, signal=0.0, confidence=0.0)

    signal = max(-1.0, min(1.0, sum(components) / len(components)))
    confidence = min(1.0, sum(abs(c) for c in components) / len(components))

    return AnalyzerResult(
        analyzer_name=ANALYZER_NAME, signal=signal, confidence=confidence,
        evidence=evidence, features_used=features_used,
    )
