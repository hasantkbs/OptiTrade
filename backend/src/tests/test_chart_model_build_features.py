"""Regression test for ml/chart_model.py::_build_features's ADX
calculation. `pd.Series(plus_dm)`/`pd.Series(minus_dm)` used to be
built with a default RangeIndex while `atr` kept the OHLCV frame's
original DatetimeIndex - dividing the two made pandas align by index
(the union of both, roughly double length, mostly NaN) instead of
elementwise by position, so every `np.column_stack` call downstream
raised a dimension-mismatch error. This made `train()` fail on every
real symbol (BTC-USD's own history included) - the chart model was
never actually trainable until this was fixed."""
import numpy as np
import pandas as pd

from ml.chart_model import N_FEATURES, WINDOW, _build_features


def _synthetic_business_day_ohlcv(n: int = 130) -> pd.DataFrame:
    """Same shape as _synthetic_ohlcv but Monday-Friday only - models a
    5-day trading week (BIST/US equities), unlike crypto's 7-day week."""
    index = pd.bdate_range("2024-01-01", periods=n)
    rng = np.random.default_rng(1)
    close = 100 + np.cumsum(rng.normal(0, 1, size=n))
    high = close + rng.uniform(0, 2, size=n)
    low = close - rng.uniform(0, 2, size=n)
    open_ = close + rng.normal(0, 0.5, size=n)
    volume = rng.uniform(1_000, 10_000, size=n)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=index,
    )


def _synthetic_ohlcv(n: int = 120) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=n, freq="D")
    rng = np.random.default_rng(0)
    close = 100 + np.cumsum(rng.normal(0, 1, size=n))
    high = close + rng.uniform(0, 2, size=n)
    low = close - rng.uniform(0, 2, size=n)
    open_ = close + rng.normal(0, 0.5, size=n)
    volume = rng.uniform(1_000, 10_000, size=n)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=index,
    )


def test_build_features_does_not_raise_on_a_realistic_datetime_indexed_frame():
    features = _build_features(_synthetic_ohlcv())
    assert features is not None


def test_build_features_returns_the_declared_feature_count():
    features = _build_features(_synthetic_ohlcv())
    assert features.shape[1] == N_FEATURES


def test_build_features_rows_match_the_input_length_minus_the_warmup_period():
    n = 120
    features = _build_features(_synthetic_ohlcv(n))
    # _build_features drops the first 30 rows (rolling-window warmup).
    assert features.shape[0] == n - 30


def test_three_months_of_business_days_does_not_clear_the_window_requirement():
    """Reproduces the real bug: main.py used to fetch `period="3mo"` for
    predict_chart_signal()'s live history pull. For a 5-day trading
    week (BIST/US equities, unlike crypto's 7-day week), ~3 calendar
    months of business days is NOT enough to produce WINDOW (60) valid
    feature rows after the 30-row warmup - predict_chart_signal()
    silently returned "Yetersiz veri" for THYAO.IS in production."""
    three_months_of_business_days = 65  # ~13 weeks * 5 days
    features = _build_features(_synthetic_business_day_ohlcv(three_months_of_business_days))
    assert len(features) < WINDOW


def test_six_months_of_business_days_clears_the_window_requirement():
    """The fix: main.py now fetches `period="6mo"` instead - confirms
    that's actually enough margin for a 5-day trading week market."""
    six_months_of_business_days = 130  # ~26 weeks * 5 days
    features = _build_features(_synthetic_business_day_ohlcv(six_months_of_business_days))
    assert len(features) >= WINDOW
