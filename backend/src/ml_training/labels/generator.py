"""
OptiTrade ML Training Platform — label generation.

Ground-truth labels derived purely from realized forward price action -
never from a live prediction. Reuses:

  - `data.fetcher.fetch_price_history_range` (already used by
    `learning/evaluator.py`) for the raw forward price series.
  - `learning.evaluator.OutcomeEvaluator._price_on_or_after`/
    `_realized_volatility` (the exact same formulas Continuous Learning
    already uses to score a *live* decision's actual outcome) - reused
    directly here to score a *training label*'s actual outcome, so both
    contexts define "actual return"/"actual volatility" identically.
  - `engines.technical.market_structure`'s support/resistance proximity
    methodology (the same 2.0%-of-price closeness threshold the live
    Technical Engine uses to call a zone a "bounce"/"rejection" zone)
    for the breakout/rejection labels, via
    `ml_training.config.MLTrainingConfig.proximity_threshold_pct`.

trend_continuation/trend_reversal/breakout/rejection all require
Technical Engine features (trend_strength_pct, support/resistance
proximity) to already be present in the feature snapshot passed in -
if they aren't (e.g. a symbol with no Technical Engine history yet),
those labels default to `False` rather than being fabricated.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable, Dict, Optional, Tuple

import pandas as pd

from data.fetcher import fetch_price_history_range
from decision_engine.models import Prediction
from engines.technical.config import (
    FEATURE_RESISTANCE_PROXIMITY,
    FEATURE_SUPPORT_PROXIMITY,
    FEATURE_TREND_STRENGTH,
)
from learning.evaluator import OutcomeEvaluator
from ml_training.config import MLTrainingConfig
from ml_training.models import LabelSet

PriceFetcher = Callable[[str, datetime, datetime], Optional[pd.DataFrame]]

_LOOKAHEAD_BUFFER_DAYS = 5


def generate_labels(
    symbol: str,
    as_of: datetime,
    horizon_days: int,
    feature_snapshot: Dict[str, float],
    config: Optional[MLTrainingConfig] = None,
    price_fetcher: Optional[PriceFetcher] = None,
) -> Optional[LabelSet]:
    """Returns `None` (never a fabricated label) when no real price
    history is available for the requested window."""
    config = config or MLTrainingConfig()
    price_fetcher = price_fetcher or fetch_price_history_range

    horizon_end = as_of + timedelta(days=horizon_days)
    fetch_start = as_of - timedelta(days=1)
    fetch_end = horizon_end + timedelta(days=_LOOKAHEAD_BUFFER_DAYS)

    history = price_fetcher(symbol, fetch_start, fetch_end)
    if history is None or history.empty:
        return None

    start_price = OutcomeEvaluator._price_on_or_after(history, as_of)
    end_price = OutcomeEvaluator._price_on_or_after(history, horizon_end)
    if start_price is None or end_price is None or start_price == 0:
        return None

    actual_return = (end_price - start_price) / start_price * 100
    actual_volatility = OutcomeEvaluator._realized_volatility(history, as_of, horizon_end)

    direction = _direction_from_return(actual_return, config.direction_band_pct)
    trend_continuation, trend_reversal = _trend_labels(feature_snapshot, actual_return, config)
    breakout, rejection = _structure_labels(feature_snapshot, actual_return, config)

    return LabelSet(
        symbol=symbol, as_of=as_of, horizon_days=horizon_days, direction=direction,
        expected_return=actual_return, expected_volatility=actual_volatility,
        trend_continuation=trend_continuation, trend_reversal=trend_reversal,
        breakout=breakout, rejection=rejection,
    )


def _direction_from_return(actual_return: float, band_pct: float) -> Prediction:
    half_band = band_pct / 2
    if actual_return > half_band:
        return Prediction.BUY
    if actual_return < -half_band:
        return Prediction.SELL
    return Prediction.HOLD


def _trend_labels(
    feature_snapshot: Dict[str, float], actual_return: float, config: MLTrainingConfig,
) -> Tuple[bool, bool]:
    trend_strength = feature_snapshot.get(FEATURE_TREND_STRENGTH)
    if trend_strength is None:
        return False, False

    was_uptrend = trend_strength > 0
    min_move = config.trend_reversal_min_move_pct

    trend_continuation = (was_uptrend and actual_return > min_move) or (
        not was_uptrend and actual_return < -min_move
    )
    trend_reversal = (was_uptrend and actual_return < -min_move) or (
        not was_uptrend and actual_return > min_move
    )
    return trend_continuation, trend_reversal


def _structure_labels(
    feature_snapshot: Dict[str, float], actual_return: float, config: MLTrainingConfig,
) -> Tuple[bool, bool]:
    resistance_proximity = feature_snapshot.get(FEATURE_RESISTANCE_PROXIMITY)
    support_proximity = feature_snapshot.get(FEATURE_SUPPORT_PROXIMITY)

    near_resistance = resistance_proximity is not None and resistance_proximity <= config.proximity_threshold_pct
    near_support = support_proximity is not None and support_proximity <= config.proximity_threshold_pct

    breakout = (near_resistance and actual_return > config.breakout_min_move_pct) or (
        near_support and actual_return < -config.breakout_min_move_pct
    )
    rejection = (near_resistance and actual_return < 0) or (near_support and actual_return > 0)
    return breakout, rejection
