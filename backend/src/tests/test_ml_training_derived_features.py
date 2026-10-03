from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from feature_store.models import FeatureRecord
from ml_training.features.derived import (
    cross_sectional_features,
    lag_rolling_features,
    multi_timeframe_features,
    volatility_regime_features,
)

_NOW = datetime(2026, 10, 3, tzinfo=timezone.utc)


def _records(values, name="rsi_14", start=_NOW - timedelta(days=9)):
    """Ascending by event_timestamp, one record per day, matching the
    real FeatureStoreService.get_feature_history contract (ascending,
    oldest first)."""
    return [
        FeatureRecord(
            symbol="X", feature_name=name, value=v,
            event_timestamp=start + timedelta(days=i),
            ingestion_timestamp=_NOW,
        )
        for i, v in enumerate(values)
    ]


def test_lag_rolling_below_floor_of_3_returns_empty():
    history = _records([10.0, 20.0])  # only 2 records
    assert lag_rolling_features(history, "rsi_14") == {}


def test_lag_rolling_computes_lag1_lag3_lag5_when_available():
    # 6 records: today (index 5) plus lag1..lag5 all available
    history = _records([10.0, 20.0, 30.0, 40.0, 50.0, 60.0])
    result = lag_rolling_features(history, "rsi_14")
    assert result["derived_lag1_rsi_14"] == 50.0
    assert result["derived_lag3_rsi_14"] == 30.0
    assert result["derived_lag5_rsi_14"] == 10.0


def test_lag_rolling_omits_a_lag_key_when_not_enough_history():
    # 4 records: lag1/lag3 available, lag5 is not (needs 6)
    history = _records([10.0, 20.0, 30.0, 40.0])
    result = lag_rolling_features(history, "rsi_14")
    assert result["derived_lag1_rsi_14"] == 30.0
    assert result["derived_lag3_rsi_14"] == 10.0
    assert "derived_lag5_rsi_14" not in result


def test_lag_rolling_roll5_mean_and_std_with_exactly_5_records():
    history = _records([10.0, 20.0, 30.0, 40.0, 50.0])
    result = lag_rolling_features(history, "rsi_14")
    assert result["derived_roll5_mean_rsi_14"] == 30.0
    assert result["derived_roll5_std_rsi_14"] == pytest.approx(14.142135, rel=1e-5)


def test_lag_rolling_roll5_uses_fewer_than_5_down_to_floor_of_3():
    history = _records([10.0, 20.0, 30.0])  # exactly floor of 3
    result = lag_rolling_features(history, "rsi_14")
    assert result["derived_roll5_mean_rsi_14"] == 20.0


def test_lag_rolling_uses_feature_name_in_every_key():
    history = _records([10.0, 20.0, 30.0], name="atr_pct")
    result = lag_rolling_features(history, "atr_pct")
    assert "derived_roll5_mean_atr_pct" in result
    assert "derived_roll5_mean_rsi_14" not in result


def _weekly_ohlcv(num_weeks, start=_NOW - timedelta(weeks=35)):
    """Oscillating, not monotonic: `calculate_rsi` divides by the
    average loss, so an always-rising series has zero losses -> a
    zero avg_loss -> NaN -> `calculate_rsi` returns `None` even with
    plenty of history. A sine-wave pattern guarantees both gains and
    losses so RSI is actually computable."""
    import math
    dates = pd.date_range(start=start, periods=num_weeks * 7, freq="D", tz="UTC")
    closes = [100.0 + 5.0 * math.sin(i / 3.0) for i in range(len(dates))]
    return pd.DataFrame({"Close": closes}, index=dates)


def test_multi_timeframe_below_floor_of_20_weekly_closes_returns_empty():
    ohlcv = _weekly_ohlcv(num_weeks=10)  # 10 weeks < 20 floor
    assert multi_timeframe_features(ohlcv) == {}


def test_multi_timeframe_none_ohlcv_returns_empty():
    assert multi_timeframe_features(None) == {}


def test_multi_timeframe_empty_ohlcv_returns_empty():
    assert multi_timeframe_features(pd.DataFrame()) == {}


def test_multi_timeframe_computes_both_keys_with_enough_history():
    ohlcv = _weekly_ohlcv(num_weeks=30)  # well above the 20-week floor
    result = multi_timeframe_features(ohlcv)
    assert "derived_weekly_rsi_14" in result
    assert "derived_weekly_trend_strength_pct" in result
    assert isinstance(result["derived_weekly_rsi_14"], float)


def test_cross_sectional_below_floor_of_3_peers_returns_empty():
    assert cross_sectional_features(50.0, [50.0, 60.0], "rsi_14") == {}


def test_cross_sectional_none_symbol_value_returns_empty():
    assert cross_sectional_features(None, [50.0, 60.0, 70.0], "rsi_14") == {}


def test_cross_sectional_computes_percentile_rank():
    # symbol_value=50 is the lowest of 4 values including itself -> rank 0.25
    result = cross_sectional_features(50.0, [50.0, 60.0, 70.0, 80.0], "rsi_14")
    assert result == {"derived_rank_rsi_14": 0.25}


def test_cross_sectional_highest_value_gets_rank_1():
    result = cross_sectional_features(80.0, [50.0, 60.0, 70.0, 80.0], "rsi_14")
    assert result["derived_rank_rsi_14"] == 1.0


def test_volregime_below_floor_of_10_returns_empty():
    history = _records([1.0] * 9, name="atr_pct")
    assert volatility_regime_features(history, "atr_pct") == {}


def test_volregime_zero_std_returns_empty():
    history = _records([5.0] * 10, name="atr_pct")  # constant -> std == 0
    assert volatility_regime_features(history, "atr_pct") == {}


def test_volregime_computes_zscore_of_latest_value():
    # 9 values of 1.0, then a final value of 10.0 - a clear positive z-score
    history = _records([1.0] * 9 + [10.0], name="atr_pct")
    result = volatility_regime_features(history, "atr_pct")
    assert result["derived_volregime_atr_pct"] > 2.0
