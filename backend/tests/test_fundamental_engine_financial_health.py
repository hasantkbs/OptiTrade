"""Tests for engines/fundamental/financial_health.py."""
import pytest

from engines.fundamental import financial_health
from engines.fundamental.config import (
    FEATURE_ALTMAN_Z,
    FEATURE_CURRENT_RATIO,
    FEATURE_DEBT_TO_EQUITY,
    FEATURE_INTEREST_COVERAGE,
    FEATURE_QUICK_RATIO,
)


def test_no_features_returns_neutral():
    result = financial_health.analyze({})
    assert result.signal == 0.0


def test_low_debt_to_equity_is_bullish():
    result = financial_health.analyze({FEATURE_DEBT_TO_EQUITY: 30.0})
    assert result.signal == pytest.approx(0.4)
    assert any("conservatively financed" in e for e in result.evidence)


def test_high_debt_to_equity_is_bearish():
    result = financial_health.analyze({FEATURE_DEBT_TO_EQUITY: 250.0})
    assert result.signal == pytest.approx(-0.4)
    assert any("heavily leveraged" in e for e in result.evidence)


def test_strong_current_ratio():
    result = financial_health.analyze({FEATURE_CURRENT_RATIO: 3.0})
    assert result.signal == pytest.approx(0.4)


def test_mildly_good_current_ratio():
    result = financial_health.analyze({FEATURE_CURRENT_RATIO: 1.5})  # >mild(1.2), not >strong(2.0)
    assert result.signal == pytest.approx(0.15)


def test_weak_current_ratio():
    result = financial_health.analyze({FEATURE_CURRENT_RATIO: 0.5})
    assert result.signal == pytest.approx(-0.4)


def test_mildly_weak_current_ratio():
    result = financial_health.analyze({FEATURE_CURRENT_RATIO: 0.9})  # <weak(1.0), not <bad(0.8)
    assert result.signal == pytest.approx(-0.15)


def test_mildly_high_debt_to_equity():
    result = financial_health.analyze({FEATURE_DEBT_TO_EQUITY: 170.0})  # >150, not >200
    assert result.signal == pytest.approx(-0.15)


def test_neutral_debt_to_equity_dead_zone():
    result = financial_health.analyze({FEATURE_DEBT_TO_EQUITY: 120.0})  # between 100 and 150
    assert result.signal == 0.0


def test_weak_quick_ratio():
    result = financial_health.analyze({FEATURE_QUICK_RATIO: 0.3})
    assert result.signal == pytest.approx(-0.4)


def test_low_interest_coverage_is_bearish_with_evidence():
    result = financial_health.analyze({FEATURE_INTEREST_COVERAGE: 0.5})
    assert result.signal == pytest.approx(-0.4)
    assert any("difficulty servicing debt" in e for e in result.evidence)


def test_altman_z_safe_zone():
    result = financial_health.analyze({FEATURE_ALTMAN_Z: 3.5})
    assert result.signal == pytest.approx(0.5)
    assert any("safe zone" in e for e in result.evidence)


def test_altman_z_distress_zone():
    result = financial_health.analyze({FEATURE_ALTMAN_Z: 1.0})
    assert result.signal == pytest.approx(-0.5)
    assert any("distress zone" in e for e in result.evidence)


def test_altman_z_grey_zone_contributes_zero_but_still_used():
    result = financial_health.analyze({FEATURE_ALTMAN_Z: 2.5})
    assert result.signal == 0.0
    assert FEATURE_ALTMAN_Z in result.features_used


def test_all_five_combine():
    values = {
        FEATURE_DEBT_TO_EQUITY: 30.0, FEATURE_CURRENT_RATIO: 3.0, FEATURE_QUICK_RATIO: 2.0,
        FEATURE_INTEREST_COVERAGE: 15.0, FEATURE_ALTMAN_Z: 3.5,
    }
    result = financial_health.analyze(values)
    assert result.signal == pytest.approx(0.42)  # (0.4+0.4+0.4+0.4+0.5)/5
    assert len(result.features_used) == 5
