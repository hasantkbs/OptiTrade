"""Tests for engines/fundamental/growth.py."""
import pytest

from engines.fundamental import growth
from engines.fundamental.config import (
    FEATURE_EPS_GROWTH,
    FEATURE_FCF_GROWTH,
    FEATURE_OPERATING_INCOME_GROWTH,
    FEATURE_REVENUE_GROWTH,
)


def test_no_features_returns_neutral():
    result = growth.analyze({})
    assert result.signal == 0.0
    assert result.confidence == 0.0


def test_strong_revenue_growth():
    result = growth.analyze({FEATURE_REVENUE_GROWTH: 20.0})
    assert result.signal == pytest.approx(0.8)
    assert any("expanding" in e for e in result.evidence)


def test_mild_revenue_growth():
    result = growth.analyze({FEATURE_REVENUE_GROWTH: 8.0})
    assert result.signal == pytest.approx(0.3)


def test_strong_contraction():
    result = growth.analyze({FEATURE_REVENUE_GROWTH: -20.0})
    assert result.signal == pytest.approx(-0.8)
    assert any("contracting" in e for e in result.evidence)


def test_mild_contraction():
    result = growth.analyze({FEATURE_REVENUE_GROWTH: -8.0})
    assert result.signal == pytest.approx(-0.3)


def test_flat_growth_is_neutral():
    result = growth.analyze({FEATURE_REVENUE_GROWTH: 0.0})
    assert result.signal == 0.0


def test_eps_growth_uses_same_tiers():
    result = growth.analyze({FEATURE_EPS_GROWTH: 20.0})
    assert result.signal == pytest.approx(0.8)


def test_operating_income_growth_uses_same_tiers():
    result = growth.analyze({FEATURE_OPERATING_INCOME_GROWTH: -20.0})
    assert result.signal == pytest.approx(-0.8)


def test_fcf_growth_uses_same_tiers():
    result = growth.analyze({FEATURE_FCF_GROWTH: 8.0})
    assert result.signal == pytest.approx(0.3)


def test_all_four_combine():
    result = growth.analyze({
        FEATURE_REVENUE_GROWTH: 20.0, FEATURE_EPS_GROWTH: 20.0,
        FEATURE_OPERATING_INCOME_GROWTH: 20.0, FEATURE_FCF_GROWTH: 20.0,
    })
    assert result.signal == pytest.approx(0.8)
    assert len(result.features_used) == 4
