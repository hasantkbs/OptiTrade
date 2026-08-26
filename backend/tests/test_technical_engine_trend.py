"""Tests for engines/technical/trend.py."""
import pytest

from engines.technical import trend
from engines.technical.config import FEATURE_EMA_CROSSOVER, FEATURE_TREND_STRENGTH


def test_no_features_returns_neutral():
    result = trend.analyze({})
    assert result.signal == 0.0
    assert result.confidence == 0.0
    assert result.evidence == []


def test_strong_bullish_trend_strength():
    result = trend.analyze({FEATURE_TREND_STRENGTH: 10.0})
    assert result.signal == pytest.approx(1.0)
    assert result.confidence == pytest.approx(1.0)
    assert any("above its EMA20" in e for e in result.evidence)


def test_mild_bullish_trend_strength():
    result = trend.analyze({FEATURE_TREND_STRENGTH: 5.0})
    assert result.signal == pytest.approx(0.5)


def test_strong_bearish_trend_strength():
    result = trend.analyze({FEATURE_TREND_STRENGTH: -10.0})
    assert result.signal == pytest.approx(-1.0)
    assert any("below its EMA20" in e for e in result.evidence)


def test_mild_bearish_trend_strength():
    result = trend.analyze({FEATURE_TREND_STRENGTH: -5.0})
    assert result.signal == pytest.approx(-0.5)


def test_neutral_trend_strength_in_dead_zone():
    result = trend.analyze({FEATURE_TREND_STRENGTH: 1.0})
    assert result.signal == 0.0
    assert result.confidence == 0.0


def test_golden_cross_is_fully_bullish():
    result = trend.analyze({FEATURE_EMA_CROSSOVER: 2.0})
    assert result.signal == pytest.approx(1.0)
    assert any("golden cross" in e for e in result.evidence)


def test_death_cross_is_fully_bearish():
    result = trend.analyze({FEATURE_EMA_CROSSOVER: -2.0})
    assert result.signal == pytest.approx(-1.0)
    assert any("death cross" in e for e in result.evidence)


def test_bullish_bias_ema():
    result = trend.analyze({FEATURE_EMA_CROSSOVER: 1.0})
    assert result.signal == pytest.approx(0.5)


def test_bearish_bias_ema():
    result = trend.analyze({FEATURE_EMA_CROSSOVER: -1.0})
    assert result.signal == pytest.approx(-0.5)


def test_no_crossover_is_neutral():
    result = trend.analyze({FEATURE_EMA_CROSSOVER: 0.0})
    assert result.signal == 0.0


def test_both_features_combine_by_average():
    # trend_strength=10 -> component 1.0; ema_crossover=1.0 (BULLISH) -> component 0.5
    # combined signal = (1.0 + 0.5) / 2 = 0.75
    result = trend.analyze({FEATURE_TREND_STRENGTH: 10.0, FEATURE_EMA_CROSSOVER: 1.0})
    assert result.signal == pytest.approx(0.75)
    assert set(result.features_used) == {FEATURE_TREND_STRENGTH, FEATURE_EMA_CROSSOVER}


def test_conflicting_signals_partially_cancel():
    # trend_strength=-10 -> component -1.0; ema_crossover=2.0 (GOLDEN_CROSS) -> component 1.0
    # combined = (-1.0 + 1.0)/2 = 0.0
    result = trend.analyze({FEATURE_TREND_STRENGTH: -10.0, FEATURE_EMA_CROSSOVER: 2.0})
    assert result.signal == pytest.approx(0.0)
