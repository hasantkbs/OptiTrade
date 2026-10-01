"""Tests for engines/technical/volume.py."""
import pytest

from engines.technical import volume
from engines.technical.config import FEATURE_VOLUME_RATIO, FEATURE_VWAP_DIFF


def test_no_features_returns_neutral():
    result = volume.analyze({})
    assert result.signal == 0.0
    assert result.confidence == 0.0


def test_high_volume_ratio_is_bullish():
    result = volume.analyze({FEATURE_VOLUME_RATIO: 2.5})
    assert result.signal == pytest.approx(0.5)
    assert any("strong participation" in e for e in result.evidence)


def test_moderately_high_volume_ratio():
    result = volume.analyze({FEATURE_VOLUME_RATIO: 1.5})
    assert result.signal == pytest.approx(0.3)


def test_low_volume_ratio_is_bearish():
    result = volume.analyze({FEATURE_VOLUME_RATIO: 0.3})
    assert result.signal == pytest.approx(-0.3)
    assert any("weak, trend unconfirmed" in e for e in result.evidence)


def test_neutral_volume_ratio():
    result = volume.analyze({FEATURE_VOLUME_RATIO: 1.0})
    assert result.signal == 0.0


def test_price_below_vwap_is_bullish():
    result = volume.analyze({FEATURE_VWAP_DIFF: -4.0})
    assert result.signal == pytest.approx(0.4)
    assert any("support zone" in e for e in result.evidence)


def test_price_above_vwap_is_bearish():
    result = volume.analyze({FEATURE_VWAP_DIFF: 4.0})
    assert result.signal == pytest.approx(-0.4)
    assert any("mean-reversion risk" in e for e in result.evidence)


def test_vwap_within_neutral_band():
    result = volume.analyze({FEATURE_VWAP_DIFF: 1.0})
    assert result.signal == 0.0


def test_both_features_combine():
    # volume_ratio=2.5 -> 0.5, vwap_diff=-4.0 -> 0.4 -> avg 0.45
    result = volume.analyze({FEATURE_VOLUME_RATIO: 2.5, FEATURE_VWAP_DIFF: -4.0})
    assert result.signal == pytest.approx(0.45)
