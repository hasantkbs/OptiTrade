"""
OptiTrade Fundamental Engine — growth analyzer.

Reads only already-resolved Feature Store values (revenue_growth_pct,
eps_growth_pct, operating_income_growth_pct, fcf_growth_pct). Same
symmetric tiers applied to all four (>15%/>5% strong/mild growth,
<-15%/<-5% strong/mild contraction).
"""
from __future__ import annotations

from typing import Dict, List

from engines.fundamental.config import (
    FEATURE_EPS_GROWTH,
    FEATURE_FCF_GROWTH,
    FEATURE_OPERATING_INCOME_GROWTH,
    FEATURE_REVENUE_GROWTH,
)
from engines.fundamental.models import AnalyzerResult

ANALYZER_NAME = "growth"

_FEATURE_LABELS = {
    FEATURE_REVENUE_GROWTH: "Revenue growth",
    FEATURE_EPS_GROWTH: "EPS growth",
    FEATURE_OPERATING_INCOME_GROWTH: "Operating income growth",
    FEATURE_FCF_GROWTH: "Free cash flow growth",
}


def _growth_component(value: float) -> float:
    if value > 15:
        return 0.8
    if value > 5:
        return 0.3
    if value < -15:
        return -0.8
    if value < -5:
        return -0.3
    return 0.0


def analyze(features: Dict[str, float]) -> AnalyzerResult:
    components: List[float] = []
    evidence: List[str] = []
    features_used: List[str] = []

    for feature_name, label in _FEATURE_LABELS.items():
        if feature_name not in features:
            continue
        value = features[feature_name]
        component = _growth_component(value)
        components.append(component)
        features_used.append(feature_name)
        if component > 0:
            evidence.append(f"{label} of {value:.1f}% - expanding business")
        elif component < 0:
            evidence.append(f"{label} of {value:.1f}% - contracting business")

    if not components:
        return AnalyzerResult(analyzer_name=ANALYZER_NAME, signal=0.0, confidence=0.0)

    signal = max(-1.0, min(1.0, sum(components) / len(components)))
    confidence = min(1.0, sum(abs(c) for c in components) / len(components))

    return AnalyzerResult(
        analyzer_name=ANALYZER_NAME, signal=signal, confidence=confidence,
        evidence=evidence, features_used=features_used,
    )
