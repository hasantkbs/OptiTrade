"""Tests for engines/fundamental/quality.py."""
import pytest

from engines.fundamental import quality
from engines.fundamental.config import (
    FEATURE_BALANCE_SHEET_QUALITY,
    FEATURE_CAPITAL_EFFICIENCY,
    FEATURE_EARNINGS_CONSISTENCY,
    FEATURE_MARGIN_STABILITY,
)


def test_no_features_returns_neutral():
    result = quality.analyze({})
    assert result.signal == 0.0


def test_high_earnings_consistency():
    result = quality.analyze({FEATURE_EARNINGS_CONSISTENCY: 1.0})
    assert result.signal == pytest.approx(0.3)
    assert any("profitable" in e for e in result.evidence)


def test_low_earnings_consistency():
    result = quality.analyze({FEATURE_EARNINGS_CONSISTENCY: 0.1})
    assert result.signal == pytest.approx(-0.3)


def test_mildly_good_earnings_consistency():
    result = quality.analyze({FEATURE_EARNINGS_CONSISTENCY: 0.8})  # >mild(0.7), not >strong(0.9)
    assert result.signal == pytest.approx(0.1)


def test_mildly_weak_earnings_consistency():
    result = quality.analyze({FEATURE_EARNINGS_CONSISTENCY: 0.4})  # <weak(0.5), not <bad(0.3)
    assert result.signal == pytest.approx(-0.1)


def test_neutral_earnings_consistency_dead_zone():
    result = quality.analyze({FEATURE_EARNINGS_CONSISTENCY: 0.6})  # between weak(0.5) and mild(0.7)
    assert result.signal == 0.0


def test_high_margin_stability():
    result = quality.analyze({FEATURE_MARGIN_STABILITY: 0.9})
    assert result.signal == pytest.approx(0.3)
    assert any("stable" in e for e in result.evidence)


def test_low_margin_stability():
    result = quality.analyze({FEATURE_MARGIN_STABILITY: 0.1})
    assert result.signal == pytest.approx(-0.3)
    assert any("swung significantly" in e for e in result.evidence)


def test_high_capital_efficiency():
    result = quality.analyze({FEATURE_CAPITAL_EFFICIENCY: 150.0})
    assert result.signal == pytest.approx(0.3)


def test_low_capital_efficiency():
    result = quality.analyze({FEATURE_CAPITAL_EFFICIENCY: 10.0})
    assert result.signal == pytest.approx(-0.3)


def test_high_balance_sheet_quality():
    result = quality.analyze({FEATURE_BALANCE_SHEET_QUALITY: 0.8})
    assert result.signal == pytest.approx(0.3)
    assert any("lightly leveraged" in e for e in result.evidence)


def test_low_balance_sheet_quality():
    result = quality.analyze({FEATURE_BALANCE_SHEET_QUALITY: 0.1})
    assert result.signal == pytest.approx(-0.3)
    assert any("heavy debt" in e for e in result.evidence)


def test_all_four_combine():
    values = {
        FEATURE_EARNINGS_CONSISTENCY: 1.0, FEATURE_MARGIN_STABILITY: 0.9,
        FEATURE_CAPITAL_EFFICIENCY: 150.0, FEATURE_BALANCE_SHEET_QUALITY: 0.8,
    }
    result = quality.analyze(values)
    assert result.signal == pytest.approx(0.3)
    assert len(result.features_used) == 4
