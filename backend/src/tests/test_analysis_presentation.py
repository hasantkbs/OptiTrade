from datetime import datetime, timezone

import pytest

from core.analysis_presentation import to_analysis_decision, to_directional_score, to_trade_signal
from core.ai_trader_persona import TradeSignal
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
    assert score == 90


def test_to_analysis_decision_maps_plain_sell():
    decision_text, decision_code, score = to_analysis_decision(_decision_output(Prediction.SELL, 0.5))
    assert decision_code == "SELL"
    assert decision_text == "SAT"
    assert score == 50


def test_to_analysis_decision_maps_hold_to_neutral():
    decision_text, decision_code, score = to_analysis_decision(_decision_output(Prediction.HOLD, 0.2))
    assert decision_code == "NEUTRAL"
    assert decision_text == "NOTR / IZLE"
    assert score == 20
