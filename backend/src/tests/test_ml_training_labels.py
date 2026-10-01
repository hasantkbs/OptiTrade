"""Tests for ml_training/labels/generator.py."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from decision_engine.models import Prediction
from engines.technical.config import FEATURE_RESISTANCE_PROXIMITY, FEATURE_SUPPORT_PROXIMITY, FEATURE_TREND_STRENGTH
from ml_training.config import MLTrainingConfig
from ml_training.labels.generator import generate_labels

_AS_OF = datetime.now(timezone.utc) - timedelta(days=20)


def _rising(symbol, start, end):
    dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
    return pd.DataFrame({"Close": [100 + i * 0.5 for i in range(len(dates))]}, index=dates)


def _falling(symbol, start, end):
    dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
    return pd.DataFrame({"Close": [100 - i * 0.5 for i in range(len(dates))]}, index=dates)


def _flat(symbol, start, end):
    dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
    return pd.DataFrame({"Close": [100.0] * len(dates)}, index=dates)


def _no_data(symbol, start, end):
    return None


def test_returns_none_when_no_price_data():
    result = generate_labels("AAPL", _AS_OF, 5, {}, price_fetcher=_no_data)
    assert result is None


def test_direction_buy_for_rising_price():
    result = generate_labels("AAPL", _AS_OF, 5, {}, price_fetcher=_rising)
    assert result.direction == Prediction.BUY
    assert result.expected_return > 0


def test_direction_sell_for_falling_price():
    result = generate_labels("AAPL", _AS_OF, 5, {}, price_fetcher=_falling)
    assert result.direction == Prediction.SELL
    assert result.expected_return < 0


def test_direction_hold_for_flat_price():
    result = generate_labels("AAPL", _AS_OF, 5, {}, price_fetcher=_flat)
    assert result.direction == Prediction.HOLD
    assert result.expected_return == pytest.approx(0.0)


def test_expected_volatility_is_nonnegative():
    result = generate_labels("AAPL", _AS_OF, 5, {}, price_fetcher=_rising)
    assert result.expected_volatility >= 0.0


def test_trend_continuation_true_when_uptrend_continues():
    snapshot = {FEATURE_TREND_STRENGTH: 5.0}
    result = generate_labels("AAPL", _AS_OF, 5, snapshot, price_fetcher=_rising)
    assert result.trend_continuation is True
    assert result.trend_reversal is False


def test_trend_reversal_true_when_uptrend_reverses():
    snapshot = {FEATURE_TREND_STRENGTH: 5.0}
    result = generate_labels("AAPL", _AS_OF, 5, snapshot, price_fetcher=_falling)
    assert result.trend_reversal is True
    assert result.trend_continuation is False


def test_trend_labels_default_false_without_trend_feature():
    result = generate_labels("AAPL", _AS_OF, 5, {}, price_fetcher=_rising)
    assert result.trend_continuation is False
    assert result.trend_reversal is False


def test_breakout_true_when_price_breaks_above_resistance():
    config = MLTrainingConfig(breakout_min_move_pct=1.0)
    snapshot = {FEATURE_RESISTANCE_PROXIMITY: 1.0}
    result = generate_labels("AAPL", _AS_OF, 5, snapshot, config=config, price_fetcher=_rising)
    assert result.breakout is True


def test_rejection_true_when_price_falls_back_from_resistance():
    snapshot = {FEATURE_RESISTANCE_PROXIMITY: 1.0}
    result = generate_labels("AAPL", _AS_OF, 5, snapshot, price_fetcher=_falling)
    assert result.rejection is True
    assert result.breakout is False


def test_rejection_true_when_price_bounces_from_support():
    snapshot = {FEATURE_SUPPORT_PROXIMITY: 1.0}
    result = generate_labels("AAPL", _AS_OF, 5, snapshot, price_fetcher=_rising)
    assert result.rejection is True


def test_structure_labels_default_false_without_proximity_features():
    result = generate_labels("AAPL", _AS_OF, 5, {}, price_fetcher=_rising)
    assert result.breakout is False
    assert result.rejection is False


def test_returns_none_when_start_price_is_zero():
    def zero_price_fetcher(symbol, start, end):
        dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
        prices = [100.0, 0.0] + [100.0] * (len(dates) - 2)
        return pd.DataFrame({"Close": prices}, index=dates)

    result = generate_labels("AAPL", _AS_OF, 5, {}, price_fetcher=zero_price_fetcher)
    assert result is None


def test_real_price_history_for_a_real_company():
    result = generate_labels("AAPL", _AS_OF, 5, {})
    assert result is not None
    assert result.direction in (Prediction.BUY, Prediction.HOLD, Prediction.SELL)
