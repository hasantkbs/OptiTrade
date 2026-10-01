"""Tests for engines/fundamental/profitability.py."""
import pytest

from engines.fundamental import profitability
from engines.fundamental.config import (
    FEATURE_GROSS_MARGIN,
    FEATURE_NET_MARGIN,
    FEATURE_OPERATING_MARGIN,
    FEATURE_ROA,
    FEATURE_ROE,
    FEATURE_ROIC,
)


def test_no_features_returns_neutral():
    result = profitability.analyze({})
    assert result.signal == 0.0


def test_strong_gross_margin():
    result = profitability.analyze({FEATURE_GROSS_MARGIN: 60.0})
    assert result.signal == pytest.approx(0.5)
    assert any("strong profitability" in e for e in result.evidence)


def test_weak_gross_margin():
    result = profitability.analyze({FEATURE_GROSS_MARGIN: 5.0})
    assert result.signal == pytest.approx(-0.5)
    assert any("weak profitability" in e for e in result.evidence)


def test_negative_net_margin_is_bearish():
    result = profitability.analyze({FEATURE_NET_MARGIN: -10.0})
    assert result.signal == pytest.approx(-0.5)


def test_strong_roe():
    result = profitability.analyze({FEATURE_ROE: 25.0})
    assert result.signal == pytest.approx(0.5)


def test_negative_roa_is_bearish():
    result = profitability.analyze({FEATURE_ROA: -1.0})
    assert result.signal == pytest.approx(-0.5)


def test_strong_roic():
    result = profitability.analyze({FEATURE_ROIC: 20.0})
    assert result.signal == pytest.approx(0.5)


def test_operating_margin_mid_tier():
    result = profitability.analyze({FEATURE_OPERATING_MARGIN: 12.0})
    assert result.signal == pytest.approx(0.2)


def test_gross_margin_mildly_weak():
    result = profitability.analyze({FEATURE_GROSS_MARGIN: 15.0})  # <weak(20), not <bad(10)
    assert result.signal == pytest.approx(-0.2)


def test_gross_margin_neutral_dead_zone():
    result = profitability.analyze({FEATURE_GROSS_MARGIN: 25.0})  # between weak(20) and mild(30)
    assert result.signal == 0.0


def test_all_six_combine():
    values = {
        FEATURE_GROSS_MARGIN: 60.0, FEATURE_OPERATING_MARGIN: 25.0, FEATURE_NET_MARGIN: 20.0,
        FEATURE_ROE: 25.0, FEATURE_ROA: 15.0, FEATURE_ROIC: 20.0,
    }
    result = profitability.analyze(values)
    assert result.signal == pytest.approx(0.5)
    assert len(result.features_used) == 6
