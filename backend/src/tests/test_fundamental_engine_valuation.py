"""Tests for engines/fundamental/valuation.py."""
import pytest

from engines.fundamental import valuation
from engines.fundamental.config import (
    FEATURE_EV_TO_EBITDA,
    FEATURE_FORWARD_PE,
    FEATURE_PE,
    FEATURE_PEG,
    FEATURE_PRICE_TO_BOOK,
    FEATURE_PRICE_TO_SALES,
)


def test_no_features_returns_neutral():
    result = valuation.analyze({})
    assert result.signal == 0.0
    assert result.confidence == 0.0


def test_cheap_pe_is_bullish():
    result = valuation.analyze({FEATURE_PE: 10.0})
    assert result.signal == pytest.approx(0.6)
    assert any("attractive" in e for e in result.evidence)


def test_moderate_pe_is_mildly_bullish():
    result = valuation.analyze({FEATURE_PE: 20.0})
    assert result.signal == pytest.approx(0.2)


def test_expensive_pe_is_bearish():
    result = valuation.analyze({FEATURE_PE: 45.0})
    assert result.signal == pytest.approx(-0.6)
    assert any("expensive" in e for e in result.evidence)


def test_mildly_expensive_pe():
    result = valuation.analyze({FEATURE_PE: 30.0})
    assert result.signal == pytest.approx(-0.2)


def test_pe_in_dead_zone():
    result = valuation.analyze({FEATURE_PE: 25.0})
    assert result.signal == 0.0


def test_peg_below_one_is_bullish():
    result = valuation.analyze({FEATURE_PEG: 0.8})
    assert result.signal == pytest.approx(0.6)


def test_peg_above_two_is_bearish():
    result = valuation.analyze({FEATURE_PEG: 2.5})
    assert result.signal == pytest.approx(-0.6)


def test_forward_pe_same_tiers_as_pe():
    result = valuation.analyze({FEATURE_FORWARD_PE: 10.0})
    assert result.signal == pytest.approx(0.6)


def test_price_to_sales_cheap():
    result = valuation.analyze({FEATURE_PRICE_TO_SALES: 0.5})
    assert result.signal == pytest.approx(0.6)


def test_price_to_book_expensive():
    result = valuation.analyze({FEATURE_PRICE_TO_BOOK: 15.0})
    assert result.signal == pytest.approx(-0.6)


def test_ev_to_ebitda_cheap():
    result = valuation.analyze({FEATURE_EV_TO_EBITDA: 6.0})
    assert result.signal == pytest.approx(0.6)


def test_all_metrics_combine():
    # PE cheap (0.6) + PEG cheap (0.6) -> avg 0.6
    result = valuation.analyze({FEATURE_PE: 10.0, FEATURE_PEG: 0.8})
    assert result.signal == pytest.approx(0.6)
    assert set(result.features_used) == {FEATURE_PE, FEATURE_PEG}
