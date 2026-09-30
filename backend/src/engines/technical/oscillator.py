"""
OptiTrade Technical Engine — oscillator analyzer (RSI).

Reads only the already-resolved `rsi_14` Feature Store value. Thresholds
reuse `core/scoring.py`'s exact RSI tiers (>80/>70 overbought,
<20/<30 oversold, mild zones at <40/>60).
"""
from __future__ import annotations

from typing import Dict

from engines.technical.config import FEATURE_RSI
from engines.technical.models import AnalyzerResult

ANALYZER_NAME = "oscillator"


def _rsi_component_and_evidence(rsi: float):
    if rsi > 80:
        return -1.0, f"RSI extremely overbought ({rsi:.1f}) - strong sell signal"
    if rsi > 70:
        return -0.6, f"RSI overbought ({rsi:.1f})"
    if rsi < 20:
        return 1.0, f"RSI extremely oversold ({rsi:.1f}) - strong buy signal"
    if rsi < 30:
        return 0.6, f"RSI oversold ({rsi:.1f})"
    if rsi < 40:
        return 0.2, f"RSI mildly oversold ({rsi:.1f})"
    if rsi > 60:
        return -0.2, f"RSI mildly overbought ({rsi:.1f})"
    return 0.0, None


def analyze(features: Dict[str, float]) -> AnalyzerResult:
    if FEATURE_RSI not in features:
        return AnalyzerResult(analyzer_name=ANALYZER_NAME, signal=0.0, confidence=0.0)

    rsi = features[FEATURE_RSI]
    signal, evidence_text = _rsi_component_and_evidence(rsi)

    return AnalyzerResult(
        analyzer_name=ANALYZER_NAME, signal=signal, confidence=abs(signal),
        evidence=[evidence_text] if evidence_text else [],
        features_used=[FEATURE_RSI],
    )
