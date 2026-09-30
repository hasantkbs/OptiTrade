"""Tests for engines/technical/oscillator.py."""
import pytest

from engines.technical import oscillator
from engines.technical.config import FEATURE_RSI


def test_no_features_returns_neutral():
    result = oscillator.analyze({})
    assert result.signal == 0.0
    assert result.confidence == 0.0


def test_extremely_overbought():
    result = oscillator.analyze({FEATURE_RSI: 85.0})
    assert result.signal == pytest.approx(-1.0)
    assert result.confidence == pytest.approx(1.0)
    assert any("extremely overbought" in e for e in result.evidence)


def test_overbought():
    result = oscillator.analyze({FEATURE_RSI: 75.0})
    assert result.signal == pytest.approx(-0.6)


def test_extremely_oversold():
    result = oscillator.analyze({FEATURE_RSI: 15.0})
    assert result.signal == pytest.approx(1.0)
    assert any("extremely oversold" in e for e in result.evidence)


def test_oversold():
    result = oscillator.analyze({FEATURE_RSI: 25.0})
    assert result.signal == pytest.approx(0.6)


def test_mildly_oversold():
    result = oscillator.analyze({FEATURE_RSI: 35.0})
    assert result.signal == pytest.approx(0.2)


def test_mildly_overbought():
    result = oscillator.analyze({FEATURE_RSI: 65.0})
    assert result.signal == pytest.approx(-0.2)


def test_neutral_middle_zone():
    result = oscillator.analyze({FEATURE_RSI: 50.0})
    assert result.signal == 0.0
    assert result.evidence == []


def test_confidence_equals_absolute_signal():
    result = oscillator.analyze({FEATURE_RSI: 15.0})
    assert result.confidence == abs(result.signal)
