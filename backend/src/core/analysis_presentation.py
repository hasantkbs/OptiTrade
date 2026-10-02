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

# Same quality gate intelligence/opportunity.py:60 already applies via
# IntelligenceConfig.min_data_sufficiency_for_classification (default
# 0.34, i.e. "at least 1 of 3 engines voted") - duplicated here as its
# own env-driven constant for the same reason
# _STRONG_SIGNAL_CONFIDENCE_THRESHOLD above is duplicated rather than
# imported from intelligence.config: this module has no other
# dependency on `intelligence`, and the two thresholds are independent
# product decisions that happen to share a starting value today. Used
# by `is_data_sufficient()` below to gate the 4 call sites that
# override a locally/LLM-computed value with `decision_engine`'s
# output - without this gate, a `decide(strict=True)` call that
# returns normally but with only 1 of 5 engines voting
# (data_sufficiency=0.2) would silently override a fully-computed
# value with a low-confidence-input decision.
_MIN_DATA_SUFFICIENCY_THRESHOLD = float(
    os.getenv("INTELLIGENCE_MIN_DATA_SUFFICIENCY_FOR_CLASSIFICATION", "0.34")
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


# core.scoring.get_decision()'s exact score bands - duplicated here (not
# imported) because this module has no other dependency on core.scoring
# and the bands are a stable, long-established public contract
# (AnalysisResult.decision_code's documented 5-way vocabulary), not
# scoring internals likely to change independently of this mapping.
_DECISION_CODE_SCORE_BAND = {
    "STRONG_BUY": (78, 100),
    "BUY": (63, 77),
    "NEUTRAL": (38, 62),
    "SELL": (23, 37),
    "STRONG_SELL": (0, 22),
}


def to_analysis_decision(decision_output: DecisionOutput) -> Tuple[str, str, int]:
    """Maps the Decision Engine's output onto `models.schemas.
    AnalysisResult`'s three headline fields: `(decision, decision_code,
    score)`. `score` MUST stay a directional 0-100 bullishness scale
    (core.scoring.get_decision()'s exact bands) because three live
    consumers still read it that way: core.advanced_analysis.
    compute_recommendation (score/100.0, feeds action_code/
    suggested_position_pct), core.session_analysis.compute_session_score,
    and main.py's categorize() (sorts scan results by score, high=
    bullish). A plain confidence magnitude (always 0-100 regardless of
    direction) would make those three produce a BUY recommendation for
    a STRONG_SELL decision - this maps `decision_code` to its matching
    band and scales a fraction-within-band WITHIN that band, so
    `get_decision(score)[1] == decision_code` holds unconditionally, by
    construction - see
    test_to_analysis_decision_score_is_consistent_with_get_decision in
    test_analysis_presentation.py.

    That fraction is computed relative to the confidence sub-range of
    whichever tier (strong vs. non-strong) `decision_code` actually
    falls in, NOT from the raw 0-100 `confidence_score` `to_trade_signal`
    returns. Using the raw confidence_score directly used to produce a
    real discontinuity: `to_trade_signal` already splits BUY into
    BUY/STRONG_BUY (and SELL into SELL/STRONG_SELL) at
    `_STRONG_SIGNAL_CONFIDENCE_THRESHOLD`, so confidence=0.749999 (BUY,
    band 63-77) scored ~77 while confidence=0.75 (STRONG_BUY, band
    78-100) scored ~95 - a ~21-point jump for an infinitesimal
    confidence change, feeding directly into
    core.advanced_analysis.compute_recommendation's half-Kelly
    `suggested_position_pct` on a live trading path. Rescaling the
    fraction per-tier (BUY/SELL: confidence in [0, threshold) scaled to
    [0, 1]; STRONG_BUY/STRONG_SELL: confidence in [threshold, 1.0]
    scaled to [0, 1]; NEUTRAL: no sub-threshold split, full [0, 1] range
    used as-is) makes the score continuous across the threshold boundary
    instead. The fraction is still clamped to [0, 1] and `score` still
    always lands in `[low, high]`, so the `get_decision(score)[1] ==
    decision_code` invariant above is unaffected by this change.

    One more wrinkle, specific to the SELL side: `_DECISION_CODE_SCORE_
    BAND` orders STRONG_SELL (0-22) BELOW SELL (23-37) on the
    bullishness scale - the mirror image of STRONG_BUY (78-100) sitting
    ABOVE BUY (63-77). So "fraction increases with confidence" must map
    to "score increases toward the shared boundary" for BUY/STRONG_BUY
    (low confidence -> low end 63, near NEUTRAL; threshold -> high end
    77, adjacent to STRONG_BUY's 78) but to "score DECREASES toward the
    shared boundary" for SELL/STRONG_SELL (low confidence -> HIGH end
    37, near NEUTRAL; threshold -> LOW end 23, adjacent to
    STRONG_SELL's 22). Applying the same `low + fraction * (high - low)`
    direction to both sides (verified empirically before relying on it
    - see test_to_analysis_decision_sell_side_is_continuous_across_
    strong_threshold) actually widens the SELL/STRONG_SELL jump instead
    of closing it (37 -> 0, worse than the ~17-point jump the unfixed
    code already had), so the SELL-side fraction is applied in reverse
    (`high - fraction * (high - low)`) to land on the same
    correctly-continuous shape BUY/STRONG_BUY gets from the forward
    direction."""
    signal, confidence_score = to_trade_signal(decision_output)
    decision_code = signal.value
    low, high = _DECISION_CODE_SCORE_BAND[decision_code]
    confidence = decision_output.confidence
    threshold = _STRONG_SIGNAL_CONFIDENCE_THRESHOLD
    if decision_code in ("STRONG_BUY", "STRONG_SELL"):
        # confidence sits in [threshold, 1.0] for this tier - rescale
        # relative to that sub-range so the score is continuous across
        # the threshold boundary with the non-strong tier below,
        # instead of jumping by the full gap between the two bands for
        # an infinitesimal confidence change (see the finding this
        # fixes: score feeds compute_recommendation's position sizing).
        fraction = (confidence - threshold) / (1.0 - threshold) if threshold < 1.0 else 1.0
    elif decision_code in ("BUY", "SELL"):
        # confidence sits in [0.0, threshold) for this tier.
        fraction = confidence / threshold if threshold > 0.0 else 0.0
    else:  # NEUTRAL (HOLD) - no sub-threshold split, full confidence range
        fraction = confidence
    fraction = max(0.0, min(1.0, fraction))
    if decision_code in ("SELL", "STRONG_SELL"):
        # Reversed direction - see the SELL-side docstring note above.
        score = high - round(fraction * (high - low))
    else:
        score = low + round(fraction * (high - low))
    return _DECISION_CODE_TEXT[decision_code], decision_code, score


def is_data_sufficient(decision_output: DecisionOutput) -> bool:
    """Quality gate for the 4 call sites that override a locally/LLM-
    computed decision with `decision_engine`'s output
    (core/analyzer.py, core/hybrid_engine.py's two override sites,
    v2/core/engine.py). `decide(strict=True)` can return normally with
    very few engines actually voting (e.g. data_sufficiency=0.2 means
    only 1 of 5 engines voted) - in that case the output is too
    low-confidence-input to trust over an already-computed value, even
    though no exception was raised. Mirrors the exact precedent
    `intelligence/opportunity.py:60` already established for this same
    situation ("data sufficiency too low to trust anything stronger ->
    WATCH"), using the same threshold value (see
    `_MIN_DATA_SUFFICIENCY_THRESHOLD` above). Callers should treat a
    `False` result the same as the existing exception-fallback path:
    log it and keep the prior local/legacy value instead of
    overriding."""
    return decision_output.data_sufficiency >= _MIN_DATA_SUFFICIENCY_THRESHOLD
