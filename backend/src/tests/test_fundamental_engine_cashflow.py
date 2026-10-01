"""Tests for engines/fundamental/cashflow.py."""
import pytest

from engines.fundamental import cashflow
from engines.fundamental.config import FEATURE_CASH_CONVERSION, FEATURE_FCF_MARGIN, FEATURE_OCF_MARGIN


def test_no_features_returns_neutral():
    result = cashflow.analyze({})
    assert result.signal == 0.0


def test_strong_ocf_margin():
    result = cashflow.analyze({FEATURE_OCF_MARGIN: 25.0})
    assert result.signal == pytest.approx(0.4)
    assert any("strong cash generation" in e for e in result.evidence)


def test_weak_ocf_margin():
    result = cashflow.analyze({FEATURE_OCF_MARGIN: -5.0})
    assert result.signal == pytest.approx(-0.4)
    assert any("weak cash generation" in e for e in result.evidence)


def test_strong_fcf_margin():
    result = cashflow.analyze({FEATURE_FCF_MARGIN: 20.0})
    assert result.signal == pytest.approx(0.4)


def test_weak_fcf_margin():
    result = cashflow.analyze({FEATURE_FCF_MARGIN: -5.0})
    assert result.signal == pytest.approx(-0.4)


def test_strong_cash_conversion():
    result = cashflow.analyze({FEATURE_CASH_CONVERSION: 1.5})
    assert result.signal == pytest.approx(0.4)
    assert any("backed by real cash" in e for e in result.evidence)


def test_poor_cash_conversion():
    result = cashflow.analyze({FEATURE_CASH_CONVERSION: 0.2})
    assert result.signal == pytest.approx(-0.4)
    assert any("earnings quality concern" in e for e in result.evidence)


def test_mildly_weak_ocf_margin():
    result = cashflow.analyze({FEATURE_OCF_MARGIN: 3.0})  # <weak(5), not <bad(0)
    assert result.signal == pytest.approx(-0.15)


def test_neutral_ocf_margin_dead_zone():
    result = cashflow.analyze({FEATURE_OCF_MARGIN: 7.0})  # between weak(5) and mild(10)
    assert result.signal == 0.0


def test_all_three_combine():
    values = {FEATURE_OCF_MARGIN: 25.0, FEATURE_FCF_MARGIN: 20.0, FEATURE_CASH_CONVERSION: 1.5}
    result = cashflow.analyze(values)
    assert result.signal == pytest.approx(0.4)
    assert len(result.features_used) == 3
