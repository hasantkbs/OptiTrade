"""
OptiTrade Fundamental Engine — profitability analyzer.

Reads only already-resolved Feature Store values (gross_margin_pct,
operating_margin_pct, net_margin_pct, roe_pct, roa_pct, roic_pct).
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from engines.fundamental.config import (
    FEATURE_GROSS_MARGIN,
    FEATURE_NET_MARGIN,
    FEATURE_OPERATING_MARGIN,
    FEATURE_ROA,
    FEATURE_ROE,
    FEATURE_ROIC,
)
from engines.fundamental.models import AnalyzerResult

ANALYZER_NAME = "profitability"

# feature_name -> (strong, mild, weak, bad, label)
_TIERS: Dict[str, Tuple[float, float, float, float, str]] = {
    FEATURE_GROSS_MARGIN: (50.0, 30.0, 20.0, 10.0, "Gross margin"),
    FEATURE_OPERATING_MARGIN: (20.0, 10.0, 5.0, 0.0, "Operating margin"),
    FEATURE_NET_MARGIN: (15.0, 5.0, 0.0, -5.0, "Net margin"),
    FEATURE_ROE: (20.0, 10.0, 5.0, 0.0, "Return on equity"),
    FEATURE_ROA: (10.0, 5.0, 2.0, 0.0, "Return on assets"),
    FEATURE_ROIC: (15.0, 8.0, 5.0, 0.0, "Return on invested capital"),
}


def _component(value: float, strong: float, mild: float, weak: float, bad: float) -> float:
    if value > strong:
        return 0.5
    if value > mild:
        return 0.2
    if value < bad:
        return -0.5
    if value < weak:
        return -0.2
    return 0.0


def analyze(features: Dict[str, float]) -> AnalyzerResult:
    components: List[float] = []
    evidence: List[str] = []
    features_used: List[str] = []

    for feature_name, (strong, mild, weak, bad, label) in _TIERS.items():
        if feature_name not in features:
            continue
        value = features[feature_name]
        component = _component(value, strong, mild, weak, bad)
        components.append(component)
        features_used.append(feature_name)
        if component > 0:
            evidence.append(f"{label} of {value:.1f}% - strong profitability")
        elif component < 0:
            evidence.append(f"{label} of {value:.1f}% - weak profitability")

    if not components:
        return AnalyzerResult(analyzer_name=ANALYZER_NAME, signal=0.0, confidence=0.0)

    signal = max(-1.0, min(1.0, sum(components) / len(components)))
    confidence = min(1.0, sum(abs(c) for c in components) / len(components))

    return AnalyzerResult(
        analyzer_name=ANALYZER_NAME, signal=signal, confidence=confidence,
        evidence=evidence, features_used=features_used,
    )
