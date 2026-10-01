"""OptiTrade — Decision Engine presentation layer.

Pure functions that convert `decision_engine.models.DecisionOutput` (the
single canonical decision authority — see docs/architecture/gap-
analysis.md section 2) into each legacy route's own historical response
shape. Every HTTP route keeps its own request/response contract exactly
as-is; only which computation is authoritative for the headline decision
fields changes. No route, request schema, or response schema changes
because of this module — see docs/superpowers/specs/2026-10-01-
decision-path-consolidation-design.md.

This module has no state and no I/O - every function here is a pure
mapping from one Pydantic model to a tuple of plain values, so it is
trivially unit-testable without a database, Feature Store, or live
decision_engine connection.
"""
from __future__ import annotations

import os
from typing import Tuple

from core.ai_trader_persona import TradeSignal
from decision_engine.models import DecisionOutput, Prediction

# Same "strong" confidence bar intelligence/config.py's
# INTELLIGENCE_STRONG_BUY_CONFIDENCE_THRESHOLD uses (default 0.75),
# applied symmetrically to SELL too - duplicated as its own env-driven
# constant rather than importing intelligence.config here, matching the
# precedent this constant is moved from (core/hybrid_engine.py).
_STRONG_SIGNAL_CONFIDENCE_THRESHOLD = float(
    os.getenv("INTELLIGENCE_STRONG_BUY_CONFIDENCE_THRESHOLD", "0.75")
)

_DECISION_CODE_TEXT = {
    "STRONG_BUY": "GUCLU AL (LONG)",
    "BUY": "AL",
    "NEUTRAL": "NOTR / IZLE",
    "SELL": "SAT",
    "STRONG_SELL": "GUCLU SAT (SHORT)",
}


def to_directional_score(decision_output: DecisionOutput) -> Tuple[float, float]:
    """Encodes the Decision Engine's discrete decision+confidence into
    a signed-magnitude scale: BUY/SELL set the sign, confidence
    (already 0..1) sets the magnitude, HOLD is exactly 0.0. Matches
    `v2.models.schemas.IndicatorOutput.score`'s own [-1, 1] bound and
    the shape `v2.core.engine.SignalFusion.aggregate()` already
    produces (a confidence-weighted signed score) - so `EngineResult`'s
    contract is unchanged, only which computation is authoritative for
    it. Moved here from `v2.core.engine._to_directional_score` (Task 1
    of docs/superpowers/plans/2026-10-01-decision-path-consolidation.md)."""
    sign = {Prediction.BUY: 1.0, Prediction.HOLD: 0.0, Prediction.SELL: -1.0}[decision_output.decision]
    return sign * decision_output.confidence, decision_output.confidence


def to_trade_signal(decision_output: DecisionOutput) -> Tuple[TradeSignal, int]:
    """Maps the Decision Engine's discrete (decision, confidence) onto
    the five-way `TradeSignal` vocabulary. `Prediction` is only
    BUY/HOLD/SELL - STRONG_BUY/STRONG_SELL are derived here from
    confidence crossing the same bar `intelligence.opportunity.
    classify_opportunity` uses for STRONG_BUY_BIAS, applied to both
    directions since a trade signal (unlike that product-facing
    "opportunity" label) needs to be symmetric. Moved here from
    `core.hybrid_engine._to_trade_signal` (Task 1 of
    docs/superpowers/plans/2026-10-01-decision-path-consolidation.md) -
    used directly by three callers: the trader profile's
    `TradeRecommendation`, the investor profile's 1-week `HorizonView`
    override (both in `core.hybrid_engine`), and `to_analysis_decision`
    below."""
    confidence_score = round(decision_output.confidence * 100)
    if decision_output.decision == Prediction.HOLD:
        return TradeSignal.NEUTRAL, confidence_score
    is_strong = decision_output.confidence >= _STRONG_SIGNAL_CONFIDENCE_THRESHOLD
    if decision_output.decision == Prediction.BUY:
        return (TradeSignal.STRONG_BUY if is_strong else TradeSignal.BUY), confidence_score
    return (TradeSignal.STRONG_SELL if is_strong else TradeSignal.SELL), confidence_score


def to_analysis_decision(decision_output: DecisionOutput) -> Tuple[str, str, int]:
    """Maps the Decision Engine's output onto `models.schemas.
    AnalysisResult`'s three headline fields: `(decision, decision_code,
    score)`. Reuses `to_trade_signal`'s exact BUY/SELL/HOLD→five-way
    mapping (the `TradeSignal` enum's values are byte-identical to
    `AnalysisResult.decision_code`'s documented vocabulary: STRONG_BUY|
    BUY|NEUTRAL|SELL|STRONG_SELL - see core.scoring.get_decision, which
    this supersedes as the authoritative source for `core.analyzer.
    analyze()`'s decision fields, keeping that function's own
    `get_decision(score)` call only as its error-fallback)."""
    signal, confidence_score = to_trade_signal(decision_output)
    decision_code = signal.value
    return _DECISION_CODE_TEXT[decision_code], decision_code, confidence_score
