"""Tests for engines/technical/volatility.py."""
import pytest

from engines.technical import volatility
from engines.technical.config import FEATURE_ATR_PCT, FEATURE_BB_BANDWIDTH, FEATURE_BB_PERCENT_B


def test_no_features_returns_neutral():
    result = volatility.analyze({})
    assert result.signal == 0.0
    assert result.confidence == 0.0


def test_strong_below_lower_band_is_bullish():
    result = volatility.analyze({FEATURE_BB_PERCENT_B: -0.10})
    assert result.signal == pytest.approx(1.0)
    assert any("oversold" in e for e in result.evidence)


def test_weak_below_lower_band_is_weakly_bullish():
    result = volatility.analyze({FEATURE_BB_PERCENT_B: 0.05})
    assert result.signal == pytest.approx(0.4)


def test_strong_above_upper_band_is_bearish():
    result = volatility.analyze({FEATURE_BB_PERCENT_B: 1.10})
    assert result.signal == pytest.approx(-1.0)
    assert any("overbought" in e for e in result.evidence)


def test_weak_above_upper_band_is_weakly_bearish():
    result = volatility.analyze({FEATURE_BB_PERCENT_B: 0.95})
    assert result.signal == pytest.approx(-0.4)


def test_mid_band_is_neutral():
    result = volatility.analyze({FEATURE_BB_PERCENT_B: 0.5})
    assert result.signal == 0.0


def test_squeeze_adds_evidence_but_not_a_signal_component():
    result = volatility.analyze({FEATURE_BB_PERCENT_B: 0.5, FEATURE_BB_BANDWIDTH: 3.0})
    assert result.signal == 0.0  # bandwidth never changes direction
    assert any("squeeze" in e for e in result.evidence)


def test_wide_bandwidth_does_not_mention_squeeze():
    result = volatility.analyze({FEATURE_BB_PERCENT_B: 0.5, FEATURE_BB_BANDWIDTH: 20.0})
    assert not any("squeeze" in e for e in result.evidence)


def test_atr_pct_is_reported_as_evidence_only():
    result = volatility.analyze({FEATURE_ATR_PCT: 2.5})
    assert result.signal == 0.0  # ATR alone carries no direction
    assert any("ATR 2.50%" in e for e in result.evidence)
    assert FEATURE_ATR_PCT in result.features_used
