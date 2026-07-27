"""
OptiTrade Fundamental Engine — valuation analyzer.

Reads only already-resolved Feature Store values (pe_ratio,
forward_pe_ratio, peg_ratio, price_to_sales, price_to_book,
ev_to_ebitda). Lower multiples are treated as bullish (cheaper relative
to fundamentals) and higher multiples as bearish, using standard,
widely-used screening tiers (e.g. PEG < 1 = undervalued relative to
growth, PEG > 2 = overvalued).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from engines.fundamental.config import (
    FEATURE_EV_TO_EBITDA,
    FEATURE_FORWARD_PE,
    FEATURE_PE,
    FEATURE_PEG,
    FEATURE_PRICE_TO_BOOK,
    FEATURE_PRICE_TO_SALES,
)
from engines.fundamental.models import AnalyzerResult

ANALYZER_NAME = "valuation"


def _tiered_component(value: float, cheap: float, mild_cheap: float, expensive: float, mild_expensive: float) -> float:
    if value < cheap:
        return 0.6
    if value < mild_cheap:
        return 0.2
    if value > expensive:
        return -0.6
    if value > mild_expensive:
        return -0.2
    return 0.0


_TIERS = {
    FEATURE_PE: (15.0, 25.0, 40.0, 25.0, "P/E"),
    FEATURE_FORWARD_PE: (15.0, 25.0, 40.0, 25.0, "Forward P/E"),
    FEATURE_PEG: (1.0, 1.5, 2.0, 1.5, "PEG ratio"),
    FEATURE_PRICE_TO_SALES: (1.0, 3.0, 10.0, 5.0, "Price/Sales"),
    FEATURE_PRICE_TO_BOOK: (1.0, 3.0, 10.0, 5.0, "Price/Book"),
    FEATURE_EV_TO_EBITDA: (8.0, 15.0, 25.0, 15.0, "EV/EBITDA"),
}


def analyze(features: Dict[str, float]) -> AnalyzerResult:
    components: List[float] = []
    evidence: List[str] = []
    features_used: List[str] = []

    for feature_name, (cheap, mild_cheap, expensive, mild_expensive, label) in _TIERS.items():
        if feature_name not in features:
            continue
        value = features[feature_name]
        component = _tiered_component(value, cheap, mild_cheap, expensive, mild_expensive)
        components.append(component)
        features_used.append(feature_name)
        if component > 0:
            evidence.append(f"{label} of {value:.1f} suggests an attractive valuation")
        elif component < 0:
            evidence.append(f"{label} of {value:.1f} suggests an expensive valuation")

    if not components:
        return AnalyzerResult(analyzer_name=ANALYZER_NAME, signal=0.0, confidence=0.0)

    signal = max(-1.0, min(1.0, sum(components) / len(components)))
    confidence = min(1.0, sum(abs(c) for c in components) / len(components))

    return AnalyzerResult(
        analyzer_name=ANALYZER_NAME, signal=signal, confidence=confidence,
        evidence=evidence, features_used=features_used,
    )
