"""Tests for ml_training/features/derived_builder.py. Uses the real
PostgreSQL/Redis-backed Feature Store, matching test_ml_training_features
.py's and test_ml_training_datasets.py's established convention."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from engines.technical.config import FEATURE_ATR_PCT, FEATURE_RSI, FEATURE_TREND_STRENGTH
from feature_store.models import FeatureRecord
from feature_store.service import FeatureStoreService
from ml_training.features.derived_builder import DerivedFeatureBuilder

_SYMBOL = "MLDERIVTEST"
_PEER = "MLDERIVPEER"
_NOW = datetime.now(timezone.utc)


def _seed(fs, symbol, feature_name, values, start):
    for i, v in enumerate(values):
        ts = start + timedelta(days=i)
        fs.offline_store.insert(
            FeatureRecord(
                symbol=symbol, feature_name=feature_name, value=v,
                event_timestamp=ts, ingestion_timestamp=ts,
            )
        )


@pytest.fixture
def feature_store():
    fs = FeatureStoreService()
    yield fs
    conn = fs.offline_store._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM feature_store_records WHERE symbol IN (%s, %s)", (_SYMBOL, _PEER),
            )
    finally:
        fs.offline_store._pool.putconn(conn)


def _oscillating_ohlcv(symbol, start, end):
    """Oscillating, not monotonic - see the identical note on
    `_weekly_ohlcv` in test_ml_training_derived_features.py: a
    monotonically rising series makes `calculate_rsi` divide by a
    zero average loss, returning `None` even with plenty of history."""
    import math
    dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
    return pd.DataFrame(
        {"Close": [100.0 + 5.0 * math.sin(i / 3.0) for i in range(len(dates))]}, index=dates,
    )


def test_compute_merges_lag_rolling_and_volregime_keys(feature_store):
    start = _NOW - timedelta(days=29)
    _seed(feature_store, _SYMBOL, FEATURE_RSI, [float(i) for i in range(30)], start)
    _seed(feature_store, _SYMBOL, FEATURE_ATR_PCT, [1.0] * 29 + [5.0], start)

    builder = DerivedFeatureBuilder(feature_store=feature_store, price_fetcher=_oscillating_ohlcv)
    result = builder.compute(_SYMBOL, _NOW, day_snapshot={})

    assert "derived_lag1_rsi_14" in result
    assert "derived_roll5_mean_rsi_14" in result
    assert "derived_volregime_atr_pct" in result


def test_compute_includes_weekly_multi_timeframe_keys_with_a_price_fetcher(feature_store):
    builder = DerivedFeatureBuilder(feature_store=feature_store, price_fetcher=_oscillating_ohlcv)
    result = builder.compute(_SYMBOL, _NOW, day_snapshot={})
    assert "derived_weekly_rsi_14" in result
    assert "derived_weekly_trend_strength_pct" in result


def test_compute_omits_multi_timeframe_keys_with_no_price_fetcher(feature_store):
    builder = DerivedFeatureBuilder(feature_store=feature_store, price_fetcher=None)
    result = builder.compute(_SYMBOL, _NOW, day_snapshot={})
    assert "derived_weekly_rsi_14" not in result
    assert "derived_weekly_trend_strength_pct" not in result


def test_compute_cross_sectional_uses_day_snapshot(feature_store):
    day_snapshot = {
        _SYMBOL: {FEATURE_RSI: 50.0},
        _PEER: {FEATURE_RSI: 60.0},
        "MLDERIVPEER2": {FEATURE_RSI: 70.0},
    }
    builder = DerivedFeatureBuilder(feature_store=feature_store, price_fetcher=None)
    result = builder.compute(_SYMBOL, _NOW, day_snapshot=day_snapshot)
    assert result["derived_rank_rsi_14"] == pytest.approx(1 / 3)


def test_compute_tolerates_a_symbol_with_only_one_feature_ever_written(feature_store):
    """A symbol with only trend_strength_pct seeded (the other 4 lag/
    rolling names and 2 volregime names have zero history) must not
    raise - every per-feature-name loop must tolerate an empty history
    list for the features that were never written."""
    _seed(feature_store, _SYMBOL, FEATURE_TREND_STRENGTH, [1.0, 2.0, 3.0], _NOW - timedelta(days=2))
    builder = DerivedFeatureBuilder(feature_store=feature_store, price_fetcher=None)
    result = builder.compute(_SYMBOL, _NOW, day_snapshot={})
    assert "derived_roll5_mean_trend_strength_pct" in result
    assert "derived_roll5_mean_rsi_14" not in result


def test_builder_defaults_to_real_feature_store():
    builder = DerivedFeatureBuilder()
    assert isinstance(builder.feature_store, FeatureStoreService)
