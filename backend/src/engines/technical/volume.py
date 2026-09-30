"""
OptiTrade Technical Engine — volume analyzer (volume ratio + VWAP).

Reads only already-resolved Feature Store values (volume_ratio,
vwap_diff_pct). Thresholds reuse `core/scoring.py`'s existing volume
ratio and VWAP-distance tiers.
"""
from __future__ import annotations

from typing import Dict, List

from engines.technical.config import FEATURE_VOLUME_RATIO, FEATURE_VWAP_DIFF
from engines.technical.models import AnalyzerResult

ANALYZER_NAME = "volume"


def _volume_ratio_component(ratio: float) -> float:
    if ratio > 2.0:
        return 0.5
    if ratio > 1.3:
        return 0.3
    if ratio < 0.4:
        return -0.3
    return 0.0


def _vwap_diff_component(diff_pct: float) -> float:
    if diff_pct > 3:
        return -0.4
    if diff_pct < -3:
        return 0.4
    return 0.0


def analyze(features: Dict[str, float]) -> AnalyzerResult:
    components: List[float] = []
    evidence: List[str] = []
    features_used: List[str] = []

    if FEATURE_VOLUME_RATIO in features:
        ratio = features[FEATURE_VOLUME_RATIO]
        component = _volume_ratio_component(ratio)
        components.append(component)
        features_used.append(FEATURE_VOLUME_RATIO)
        if ratio > 1.3:
            evidence.append(f"Volume {ratio:.1f}x average - strong participation")
        elif ratio < 0.4:
            evidence.append(f"Volume {ratio:.1f}x average - weak, trend unconfirmed")

    if FEATURE_VWAP_DIFF in features:
        diff_pct = features[FEATURE_VWAP_DIFF]
        component = _vwap_diff_component(diff_pct)
        components.append(component)
        features_used.append(FEATURE_VWAP_DIFF)
        if component > 0:
            evidence.append(f"Price {abs(diff_pct):.1f}% below VWAP - support zone")
        elif component < 0:
            evidence.append(f"Price {diff_pct:.1f}% above VWAP - mean-reversion risk")

    if not components:
        return AnalyzerResult(analyzer_name=ANALYZER_NAME, signal=0.0, confidence=0.0)

    signal = max(-1.0, min(1.0, sum(components) / len(components)))
    confidence = min(1.0, sum(abs(c) for c in components) / len(components))

    return AnalyzerResult(
        analyzer_name=ANALYZER_NAME, signal=signal, confidence=confidence,
        evidence=evidence, features_used=features_used,
    )
