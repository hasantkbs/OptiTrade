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

from ml.chart_model import N_FEATURES, _build_features


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
