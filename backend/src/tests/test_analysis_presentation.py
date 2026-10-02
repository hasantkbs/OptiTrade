import pytest

from core.analysis_presentation import (
    is_data_sufficient,
    to_analysis_decision,
    to_directional_score,
    to_trade_signal,
)
from core.ai_trader_persona import TradeSignal
from core.scoring import get_decision
from decision_engine.models import DecisionOutput, Prediction


def _decision_output(decision: Prediction, confidence: float) -> DecisionOutput:
    return DecisionOutput(
        symbol="TEST", decision=decision, confidence=confidence,
        expected_return=0.0, expected_volatility=0.1,
        aggregation_strategy_version="test", data_sufficiency=1.0,
    )


def test_to_directional_score_buy_is_positive():
    score, confidence = to_directional_score(_decision_output(Prediction.BUY, 0.8))
    assert score == pytest.approx(0.8)
    assert confidence == pytest.approx(0.8)


def test_to_directional_score_sell_is_negative():
    score, confidence = to_directional_score(_decision_output(Prediction.SELL, 0.6))
    assert score == pytest.approx(-0.6)
    assert confidence == pytest.approx(0.6)


def test_to_directional_score_hold_is_zero():
    score, confidence = to_directional_score(_decision_output(Prediction.HOLD, 0.9))
    assert score == 0.0
    assert confidence == pytest.approx(0.9)


def test_to_trade_signal_strong_buy_above_threshold():
    signal, confidence_score = to_trade_signal(_decision_output(Prediction.BUY, 0.9))
    assert signal == TradeSignal.STRONG_BUY
    assert confidence_score == 90


def test_to_trade_signal_plain_buy_below_threshold():
    signal, confidence_score = to_trade_signal(_decision_output(Prediction.BUY, 0.5))
    assert signal == TradeSignal.BUY
    assert confidence_score == 50


def test_to_trade_signal_strong_sell_above_threshold():
    signal, confidence_score = to_trade_signal(_decision_output(Prediction.SELL, 0.85))
    assert signal == TradeSignal.STRONG_SELL
    assert confidence_score == 85


def test_to_trade_signal_hold_is_neutral():
    signal, confidence_score = to_trade_signal(_decision_output(Prediction.HOLD, 0.3))
    assert signal == TradeSignal.NEUTRAL
    assert confidence_score == 30


def test_to_analysis_decision_maps_strong_buy():
    decision_text, decision_code, score = to_analysis_decision(_decision_output(Prediction.BUY, 0.9))
    assert decision_code == "STRONG_BUY"
    assert decision_text == "GUCLU AL (LONG)"
    # score is scaled WITHIN the STRONG_BUY band (78-100), using the
    # fraction of confidence WITHIN the strong tier's sub-range
    # [threshold, 1.0] (see Fix: continuity across the strong-signal
    # threshold) - threshold=0.75, fraction=(0.9-0.75)/0.25=0.6,
    # 78 + round(0.6 * 22) == 91.
    assert score == 91


def test_to_analysis_decision_maps_plain_sell():
    decision_text, decision_code, score = to_analysis_decision(_decision_output(Prediction.SELL, 0.5))
    assert decision_code == "SELL"
    assert decision_text == "SAT"
    # score is scaled WITHIN the SELL band (23-37), but in the REVERSE
    # direction from BUY: SELL's band sits ABOVE STRONG_SELL's on the
    # bullishness scale, so higher SELL-tier confidence (more bearish
    # conviction) moves the score DOWN toward STRONG_SELL's boundary
    # (23), not up - fraction=0.5/0.75=0.6667, 37 - round(0.6667*14) == 28.
    assert score == 28


def test_to_analysis_decision_maps_hold_to_neutral():
    decision_text, decision_code, score = to_analysis_decision(_decision_output(Prediction.HOLD, 0.2))
    assert decision_code == "NEUTRAL"
    assert decision_text == "NOTR / IZLE"
    # score is now scaled WITHIN the NEUTRAL band (38-62): 38 + round(0.2 * 24) == 43.
    assert score == 43


@pytest.mark.parametrize("confidence", [0.0, 0.1, 0.5, 0.74, 0.75, 0.76, 0.9, 1.0])
@pytest.mark.parametrize("decision", [Prediction.BUY, Prediction.HOLD, Prediction.SELL])
def test_to_analysis_decision_score_is_consistent_with_get_decision(decision, confidence):
    """score must always fall in get_decision()'s band for decision_code -
    this is the actual bug the Critical finding was about (score became a
    direction-free confidence magnitude, producing e.g. decision_code=
    STRONG_SELL with recommendation.action_code=BUY downstream)."""
    _, decision_code, score = to_analysis_decision(_decision_output(decision, confidence))
    assert get_decision(score)[1] == decision_code


# ─────────────────────────────────────────────────────────────────────────
# Finding 1 fix: score must be CONTINUOUS across the strong-signal
# threshold, not jump by the full gap between the two bands for an
# infinitesimal confidence change (the actual bug: this score feeds
# core.advanced_analysis.compute_recommendation's score_norm, 40% of a
# composite that drives action_code and a half-Kelly
# suggested_position_pct on a live trading path).
# ─────────────────────────────────────────────────────────────────────────

def test_to_analysis_decision_buy_side_is_continuous_across_strong_threshold():
    _, decision_code_below, score_below = to_analysis_decision(_decision_output(Prediction.BUY, 0.7499))
    _, decision_code_above, score_above = to_analysis_decision(_decision_output(Prediction.BUY, 0.75))

    assert decision_code_below == "BUY"
    assert decision_code_above == "STRONG_BUY"
    # Before the fix this jumped by ~21 points (e.g. 77 -> 95) for an
    # infinitesimal confidence change; now it's a small, bounded step.
    assert abs(score_above - score_below) <= 2


def test_to_analysis_decision_sell_side_is_continuous_across_strong_threshold():
    """Symmetric case for SELL/STRONG_SELL. Note SELL's band (23-37)
    sits ABOVE STRONG_SELL's (0-22) on the bullishness scale - the
    mirror image of BUY/STRONG_BUY - so naively applying the same
    "fraction increases with confidence -> score increases" direction
    to SELL actually widens this jump (verified empirically: it would
    go from 37 to 0, i.e. worse than the unfixed ~17-point jump) instead
    of closing it. The implementation accounts for this by applying the
    SELL-side fraction in reverse."""
    _, decision_code_below, score_below = to_analysis_decision(_decision_output(Prediction.SELL, 0.7499))
    _, decision_code_above, score_above = to_analysis_decision(_decision_output(Prediction.SELL, 0.75))

    assert decision_code_below == "SELL"
    assert decision_code_above == "STRONG_SELL"
    assert abs(score_above - score_below) <= 2


# ─────────────────────────────────────────────────────────────────────────
# Finding 3 fix: is_data_sufficient() quality gate
# ─────────────────────────────────────────────────────────────────────────

def test_is_data_sufficient_true_at_and_above_threshold():
    assert is_data_sufficient(_decision_output(Prediction.BUY, 0.8).model_copy(update={"data_sufficiency": 0.34}))
    assert is_data_sufficient(_decision_output(Prediction.BUY, 0.8).model_copy(update={"data_sufficiency": 1.0}))


def test_is_data_sufficient_false_below_threshold():
    low = _decision_output(Prediction.BUY, 0.8).model_copy(update={"data_sufficiency": 0.2})
    assert is_data_sufficient(low) is False
