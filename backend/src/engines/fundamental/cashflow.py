"""
OptiTrade Fundamental Engine — cash flow analyzer.

Reads only already-resolved Feature Store values
(operating_cash_flow_margin_pct, free_cash_flow_margin_pct,
cash_conversion_ratio).
"""
from __future__ import annotations

from typing import Dict, List

from engines.fundamental.config import FEATURE_CASH_CONVERSION, FEATURE_FCF_MARGIN, FEATURE_OCF_MARGIN
from engines.fundamental.models import AnalyzerResult

ANALYZER_NAME = "cashflow"


def _margin_component(value: float, strong: float, mild: float, weak: float, bad: float) -> float:
    if value > strong:
        return 0.4
    if value > mild:
        return 0.15
    if value < bad:
        return -0.4
    if value < weak:
        return -0.15
    return 0.0


def analyze(features: Dict[str, float]) -> AnalyzerResult:
    components: List[float] = []
    evidence: List[str] = []
    features_used: List[str] = []

    if FEATURE_OCF_MARGIN in features:
        value = features[FEATURE_OCF_MARGIN]
        component = _margin_component(value, 20.0, 10.0, 5.0, 0.0)
        components.append(component)
        features_used.append(FEATURE_OCF_MARGIN)
        if component > 0:
            evidence.append(f"Operating cash flow margin of {value:.1f}% - strong cash generation")
        elif component < 0:
            evidence.append(f"Operating cash flow margin of {value:.1f}% - weak cash generation")

    if FEATURE_FCF_MARGIN in features:
        value = features[FEATURE_FCF_MARGIN]
        component = _margin_component(value, 15.0, 5.0, 2.0, 0.0)
        components.append(component)
        features_used.append(FEATURE_FCF_MARGIN)
        if component > 0:
            evidence.append(f"Free cash flow margin of {value:.1f}% - healthy free cash generation")
        elif component < 0:
            evidence.append(f"Free cash flow margin of {value:.1f}% - limited free cash generation")

    if FEATURE_CASH_CONVERSION in features:
        value = features[FEATURE_CASH_CONVERSION]
        component = _margin_component(value * 100, 120.0, 80.0, 60.0, 30.0)
        components.append(component)
        features_used.append(FEATURE_CASH_CONVERSION)
        if component > 0:
            evidence.append(f"Cash conversion of {value:.2f}x - earnings backed by real cash")
        elif component < 0:
            evidence.append(f"Cash conversion of {value:.2f}x - earnings quality concern")

    if not components:
        return AnalyzerResult(analyzer_name=ANALYZER_NAME, signal=0.0, confidence=0.0)

    signal = max(-1.0, min(1.0, sum(components) / len(components)))
    confidence = min(1.0, sum(abs(c) for c in components) / len(components))

    return AnalyzerResult(
        analyzer_name=ANALYZER_NAME, signal=signal, confidence=confidence,
        evidence=evidence, features_used=features_used,
    )
