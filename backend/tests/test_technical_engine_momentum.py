"""Tests for engines/technical/momentum.py."""
import pytest

from engines.technical import momentum
from engines.technical.config import (
    FEATURE_MACD_HISTOGRAM,
    FEATURE_MACD_LINE,
    FEATURE_MACD_SIGNAL,
    FEATURE_ROC,
)


def test_no_features_returns_neutral():
    result = momentum.analyze({})
    assert result.signal == 0.0
    assert result.confidence == 0.0


def test_macd_above_signal_is_bullish():
    result = momentum.analyze({FEATURE_MACD_LINE: 0.5, FEATURE_MACD_SIGNAL: 0.2})
    assert result.signal == pytest.approx(0.6)
    assert any("bullish momentum" in e for e in result.evidence)


def test_macd_below_signal_is_bearish():
    result = momentum.analyze({FEATURE_MACD_LINE: 0.2, FEATURE_MACD_SIGNAL: 0.5})
    assert result.signal == pytest.approx(-0.6)
    assert any("bearish momentum" in e for e in result.evidence)


def test_macd_equal_to_signal_is_bearish_else_branch():
    # Mirrors core/scoring.py's characterized behavior: an exact tie falls
    # into the bearish `else` branch, not neutral.
    result = momentum.analyze({FEATURE_MACD_LINE: 0.3, FEATURE_MACD_SIGNAL: 0.3})
    assert result.signal == pytest.approx(-0.6)


def test_macd_histogram_accelerating_upward_adds_to_bullish_crossover():
    # crossover component 0.6, histogram component 0.3 -> avg 0.45
    result = momentum.analyze({
        FEATURE_MACD_LINE: 0.5, FEATURE_MACD_SIGNAL: 0.2, FEATURE_MACD_HISTOGRAM: 1.0,
    })
    assert result.signal == pytest.approx(0.45)
    assert any("accelerating upward" in e for e in result.evidence)


def test_macd_histogram_accelerating_downward():
    result = momentum.analyze({
        FEATURE_MACD_LINE: 0.2, FEATURE_MACD_SIGNAL: 0.5, FEATURE_MACD_HISTOGRAM: -1.0,
    })
    assert result.signal == pytest.approx(-0.45)
    assert any("accelerating downward" in e for e in result.evidence)


def test_roc_strong_bullish():
    result = momentum.analyze({FEATURE_ROC: 20.0})
    assert result.signal == pytest.approx(1.0)


def test_roc_mild_bullish():
    result = momentum.analyze({FEATURE_ROC: 10.0})
    assert result.signal == pytest.approx(0.5)


def test_roc_strong_bearish():
    result = momentum.analyze({FEATURE_ROC: -20.0})
    assert result.signal == pytest.approx(-1.0)


def test_roc_mild_bearish():
    result = momentum.analyze({FEATURE_ROC: -10.0})
    assert result.signal == pytest.approx(-0.5)


def test_roc_neutral_zone():
    result = momentum.analyze({FEATURE_ROC: 0.0})
    assert result.signal == 0.0


def test_macd_and_roc_combine():
    # crossover 0.6 (bullish) + roc strong bullish 1.0 -> avg 0.8
    result = momentum.analyze({
        FEATURE_MACD_LINE: 0.5, FEATURE_MACD_SIGNAL: 0.2, FEATURE_ROC: 20.0,
    })
    assert result.signal == pytest.approx(0.8)
    assert set(result.features_used) == {FEATURE_MACD_LINE, FEATURE_MACD_SIGNAL, FEATURE_ROC}
