"""
OptiTrade ML Training Platform — derived feature engineering.

Pure, stateless functions only — every one takes already-fetched data
(FeatureRecord history, OHLCV, a basket snapshot) and returns a dict of
new named features. Never fetches anything itself;
`ml_training.features.derived_builder.DerivedFeatureBuilder` owns all
I/O. Every returned key is prefixed `derived_` so it can never collide
with a base Feature Store feature name in the same flat dict.

Missing data stays missing: every function below has its own minimum-
data floor (named per-function) below which it omits the affected keys
(or returns {} entirely) rather than fabricating a value - matching the
project-wide "never fabricate" convention `ml_training.features
.extractor.FeatureExtractor`/`ml_training.labels.generator
.generate_labels` already use.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from core.indicators import calculate_rsi, calculate_trend_strength
from feature_store.models import FeatureRecord

_LAG_DAYS = (1, 3, 5)
_ROLL_WINDOW = 5
_MIN_ROLL_SAMPLES = 3
_MIN_WEEKLY_CLOSES = 20
_WEEKLY_RSI_PERIOD = 14
_WEEKLY_TREND_PERIOD = 20
_MIN_CROSS_SECTIONAL_PEERS = 3
_MIN_VOLREGIME_SAMPLES = 10


def lag_rolling_features(history: List[FeatureRecord], feature_name: str) -> Dict[str, float]:
    """`history` must be ascending by `event_timestamp`, every record's
    `event_timestamp` at-or-before the sample's own `as_of` (the caller's
    responsibility - see `DerivedFeatureBuilder`). `history[-1]` is the
    most recent record at-or-before `as_of` (the "today" value already
    present in the base feature vector); `derived_lag1_<name>` is
    `history[-2]`, `derived_lag3_<name>` is `history[-4]`, etc. Below
    `_MIN_ROLL_SAMPLES` (3) total records, returns `{}` entirely -
    matches the project's "missing stays missing" convention."""
    if len(history) < _MIN_ROLL_SAMPLES:
        return {}

    result: Dict[str, float] = {}
    for lag in _LAG_DAYS:
        index = len(history) - 1 - lag
        if index >= 0:
            result[f"derived_lag{lag}_{feature_name}"] = history[index].value

    window = history[-_ROLL_WINDOW:]
    values = [record.value for record in window]
    result[f"derived_roll5_mean_{feature_name}"] = float(np.mean(values))
    result[f"derived_roll5_std_{feature_name}"] = float(np.std(values))

    return result


def multi_timeframe_features(ohlcv: Optional[pd.DataFrame]) -> Dict[str, float]:
    """`ohlcv` must have a 'Close' column and be pre-filtered by the
    caller to rows at-or-before the sample's own `as_of` (see
    `DerivedFeatureBuilder`). Resamples to weekly closes
    (`resample("W").last()`) and calls the real production indicator
    functions on that weekly series - reusing the exact math
    `engines.technical.feature_adapter.TechnicalFeatureAdapter
    ._compute_all` already uses for the daily versions, not a
    reimplementation. `calculate_rsi` needs `len(prices) >= period + 1`
    (15 at the default `period=14`); `calculate_trend_strength` needs
    `len(prices) >= period` (20 at the default `period=20`) - 20 is the
    binding floor. Below `_MIN_WEEKLY_CLOSES` (20) weekly closes after
    resampling, returns `{}` entirely rather than calling either
    function on too short a series. The two indicators are checked for
    `None` independently since one can floor out before the other on a
    series just above 20 weekly points."""
    if ohlcv is None or ohlcv.empty or "Close" not in ohlcv.columns:
        return {}

    weekly = ohlcv["Close"].resample("W").last().dropna()
    if len(weekly) < _MIN_WEEKLY_CLOSES:
        return {}

    result: Dict[str, float] = {}
    rsi = calculate_rsi(weekly, period=_WEEKLY_RSI_PERIOD)
    if rsi is not None:
        result["derived_weekly_rsi_14"] = rsi
    trend = calculate_trend_strength(weekly, period=_WEEKLY_TREND_PERIOD)
    if trend is not None:
        result["derived_weekly_trend_strength_pct"] = trend
    return result


def cross_sectional_features(
    symbol_value: Optional[float], basket_values: List[float], feature_name: str,
) -> Dict[str, float]:
    """`basket_values` must include `symbol_value` itself when available
    (the caller passes the whole day's basket snapshot including this
    symbol - see `DerivedFeatureBuilder`). Returns this symbol's
    percentile rank (0.0-1.0, 1.0 = highest) among every peer with a
    value for `feature_name` on this day. Below
    `_MIN_CROSS_SECTIONAL_PEERS` (3) symbols total (including this one),
    or when `symbol_value` is `None`, returns `{}` - a rank against 1-2
    peers is not a meaningful cross-sectional signal."""
    if symbol_value is None or len(basket_values) < _MIN_CROSS_SECTIONAL_PEERS:
        return {}
    rank = sum(1 for v in basket_values if v <= symbol_value) / len(basket_values)
    return {f"derived_rank_{feature_name}": rank}


def volatility_regime_features(history: List[FeatureRecord], feature_name: str) -> Dict[str, float]:
    """`history` must be ascending by `event_timestamp`, every record's
    `event_timestamp` at-or-before the sample's own `as_of` - same
    contract as `lag_rolling_features`. Returns `derived_volregime_
    <name>`: the z-score of the most recent value (`history[-1]`,
    included in its own window) against the trailing window's own
    mean/std. Below `_MIN_VOLREGIME_SAMPLES` (10) records, or when the
    trailing std is exactly 0.0 (a constant series - a real
    division-by-zero guard, not expected in practice), returns `{}`."""
    if len(history) < _MIN_VOLREGIME_SAMPLES:
        return {}
    values = [record.value for record in history]
    mean = float(np.mean(values))
    std = float(np.std(values))
    if std == 0.0:
        return {}
    latest = values[-1]
    return {f"derived_volregime_{feature_name}": (latest - mean) / std}
