"""Tests for engines/technical/market_structure.py."""
import pytest

from engines.technical import market_structure
from engines.technical.config import (
    FEATURE_BEARISH_PATTERN_COUNT,
    FEATURE_BULLISH_PATTERN_COUNT,
    FEATURE_RESISTANCE_PROXIMITY,
    FEATURE_SUPPORT_PROXIMITY,
)


def test_no_features_returns_neutral():
    result = market_structure.analyze({})
    assert result.signal == 0.0
    assert result.confidence == 0.0


def test_close_to_support_is_bullish():
    result = market_structure.analyze({
        FEATURE_SUPPORT_PROXIMITY: 1.0, FEATURE_RESISTANCE_PROXIMITY: 5.0,
    })
    assert result.signal == pytest.approx(0.6)
    assert any("bounce zone" in e for e in result.evidence)


def test_close_to_resistance_is_bearish():
    result = market_structure.analyze({
        FEATURE_SUPPORT_PROXIMITY: 5.0, FEATURE_RESISTANCE_PROXIMITY: 1.0,
    })
    assert result.signal == pytest.approx(-0.6)
    assert any("rejection zone" in e for e in result.evidence)


def test_far_from_both_levels_is_neutral():
    result = market_structure.analyze({
        FEATURE_SUPPORT_PROXIMITY: 8.0, FEATURE_RESISTANCE_PROXIMITY: 9.0,
    })
    assert result.signal == 0.0


def test_bullish_patterns_dominate():
    result = market_structure.analyze({
        FEATURE_BULLISH_PATTERN_COUNT: 2.0, FEATURE_BEARISH_PATTERN_COUNT: 0.0,
    })
    assert result.signal == pytest.approx(0.8)  # min(1.0, 0.4*2)
    assert any("bullish candlestick" in e for e in result.evidence)


def test_bearish_patterns_dominate():
    result = market_structure.analyze({
        FEATURE_BULLISH_PATTERN_COUNT: 0.0, FEATURE_BEARISH_PATTERN_COUNT: 2.0,
    })
    assert result.signal == pytest.approx(-0.8)
    assert any("bearish candlestick" in e for e in result.evidence)


def test_pattern_signal_clamped_at_one():
    result = market_structure.analyze({
        FEATURE_BULLISH_PATTERN_COUNT: 5.0, FEATURE_BEARISH_PATTERN_COUNT: 0.0,
    })
    assert result.signal == pytest.approx(1.0)


def test_equal_pattern_counts_produce_no_component():
    result = market_structure.analyze({
        FEATURE_BULLISH_PATTERN_COUNT: 1.0, FEATURE_BEARISH_PATTERN_COUNT: 1.0,
    })
    assert result.signal == 0.0


def test_proximity_and_patterns_combine():
    # support component 0.6, bullish pattern component 0.8 -> avg 0.7
    result = market_structure.analyze({
        FEATURE_SUPPORT_PROXIMITY: 1.0, FEATURE_RESISTANCE_PROXIMITY: 5.0,
        FEATURE_BULLISH_PATTERN_COUNT: 2.0, FEATURE_BEARISH_PATTERN_COUNT: 0.0,
    })
    assert result.signal == pytest.approx(0.7)
