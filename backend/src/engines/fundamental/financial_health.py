"""
OptiTrade Fundamental Engine — financial health analyzer.

Reads only already-resolved Feature Store values (debt_to_equity_pct,
current_ratio, quick_ratio, interest_coverage_ratio, altman_z_score).
Altman Z-Score uses the standard, well-established zones (safe / grey /
distress) rather than an invented threshold; it is only present in the
features dict at all when the underlying multi-year statement data was
sufficient to compute it (see `feature_adapter.py`).
"""
from __future__ import annotations

from typing import Dict, List

from engines.fundamental.config import (
    FEATURE_ALTMAN_Z,
    FEATURE_CURRENT_RATIO,
    FEATURE_DEBT_TO_EQUITY,
    FEATURE_INTEREST_COVERAGE,
    FEATURE_QUICK_RATIO,
)
from engines.fundamental.models import AnalyzerResult

ANALYZER_NAME = "financial_health"


def _higher_is_better_component(value: float, strong: float, mild: float, weak: float, bad: float) -> float:
    if value > strong:
        return 0.4
    if value > mild:
        return 0.15
    if value < bad:
        return -0.4
    if value < weak:
        return -0.15
    return 0.0


def _debt_to_equity_component(value: float) -> float:
    # Lower leverage is healthier - tiers are inverted relative to the
    # other ratios here.
    if value < 50:
        return 0.4
    if value < 100:
        return 0.15
    if value > 200:
        return -0.4
    if value > 150:
        return -0.15
    return 0.0


def _altman_z_component(z: float) -> str:
    # Standard Altman Z-Score zones (Altman, 1968).
    if z > 2.99:
        return "safe"
    if z < 1.81:
        return "distress"
    return "grey"


def analyze(features: Dict[str, float]) -> AnalyzerResult:
    components: List[float] = []
    evidence: List[str] = []
    features_used: List[str] = []

    if FEATURE_DEBT_TO_EQUITY in features:
        value = features[FEATURE_DEBT_TO_EQUITY]
        component = _debt_to_equity_component(value)
        components.append(component)
        features_used.append(FEATURE_DEBT_TO_EQUITY)
        if component > 0:
            evidence.append(f"Debt/Equity of {value:.1f}% - conservatively financed")
        elif component < 0:
            evidence.append(f"Debt/Equity of {value:.1f}% - heavily leveraged")

    if FEATURE_CURRENT_RATIO in features:
        value = features[FEATURE_CURRENT_RATIO]
        component = _higher_is_better_component(value, 2.0, 1.2, 1.0, 0.8)
        components.append(component)
        features_used.append(FEATURE_CURRENT_RATIO)
        if component > 0:
            evidence.append(f"Current ratio of {value:.2f} - strong short-term liquidity")
        elif component < 0:
            evidence.append(f"Current ratio of {value:.2f} - weak short-term liquidity")

    if FEATURE_QUICK_RATIO in features:
        value = features[FEATURE_QUICK_RATIO]
        component = _higher_is_better_component(value, 1.5, 1.0, 0.8, 0.5)
        components.append(component)
        features_used.append(FEATURE_QUICK_RATIO)

    if FEATURE_INTEREST_COVERAGE in features:
        value = features[FEATURE_INTEREST_COVERAGE]
        component = _higher_is_better_component(value, 10.0, 3.0, 2.0, 1.0)
        components.append(component)
        features_used.append(FEATURE_INTEREST_COVERAGE)
        if component < 0:
            evidence.append(f"Interest coverage of {value:.1f}x - difficulty servicing debt")

    if FEATURE_ALTMAN_Z in features:
        z = features[FEATURE_ALTMAN_Z]
        zone = _altman_z_component(z)
        features_used.append(FEATURE_ALTMAN_Z)
        if zone == "safe":
            components.append(0.5)
            evidence.append(f"Altman Z-Score of {z:.2f} - safe zone, low bankruptcy risk")
        elif zone == "distress":
            components.append(-0.5)
            evidence.append(f"Altman Z-Score of {z:.2f} - distress zone, elevated bankruptcy risk")
        else:
            components.append(0.0)

    if not components:
        return AnalyzerResult(analyzer_name=ANALYZER_NAME, signal=0.0, confidence=0.0)

    signal = max(-1.0, min(1.0, sum(components) / len(components)))
    confidence = min(1.0, sum(abs(c) for c in components) / len(components))

    return AnalyzerResult(
        analyzer_name=ANALYZER_NAME, signal=signal, confidence=confidence,
        evidence=evidence, features_used=features_used,
    )
