"""
OptiTrade ML Training Platform — derived feature orchestration.

Owns the FeatureStoreService + PriceFetcher dependencies; fetches
exactly what each pure function in `ml_training.features.derived`
needs and merges their output into one `derived_*`-prefixed dict. The
only component in this package that both fetches AND computes -
deliberately kept separate from `ml_training.features.extractor
.FeatureExtractor` (which only ever fetches, never computes) so that
boundary stays honest.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Optional

from engines.technical.config import (
    FEATURE_ATR_PCT,
    FEATURE_BB_BANDWIDTH,
    FEATURE_MACD_HISTOGRAM,
    FEATURE_RSI,
    FEATURE_TREND_STRENGTH,
    FEATURE_VOLUME_RATIO,
)
from feature_store.service import FeatureStoreService, get_default_feature_store_service
from ml_training.features.derived import (
    cross_sectional_features,
    lag_rolling_features,
    multi_timeframe_features,
    volatility_regime_features,
)
from ml_training.labels.generator import PriceFetcher

_LAG_ROLLING_FEATURE_NAMES = [
    FEATURE_RSI, FEATURE_MACD_HISTOGRAM, FEATURE_VOLUME_RATIO, FEATURE_ATR_PCT, FEATURE_TREND_STRENGTH,
]
_VOLREGIME_FEATURE_NAMES = [FEATURE_ATR_PCT, FEATURE_BB_BANDWIDTH]
_CROSS_SECTIONAL_FEATURE_NAMES = [FEATURE_RSI, FEATURE_VOLUME_RATIO, FEATURE_TREND_STRENGTH]

_LAG_ROLLING_LOOKBACK_DAYS = 10
_VOLREGIME_LOOKBACK_DAYS = 30
_MULTI_TIMEFRAME_LOOKBACK_WEEKS = 30


class DerivedFeatureBuilder:
    """`price_fetcher` is `Optional` so this class can be constructed and
    used (for every category except multi-timeframe) without one - the
    multi-timeframe keys are simply omitted when no `price_fetcher` is
    given, following the same "missing stays missing" convention as
    every other category."""

    def __init__(
        self,
        feature_store: Optional[FeatureStoreService] = None,
        price_fetcher: Optional[PriceFetcher] = None,
    ) -> None:
        self.feature_store = feature_store or get_default_feature_store_service()
        self.price_fetcher = price_fetcher

    def compute(
        self, symbol: str, as_of: datetime, day_snapshot: Dict[str, Dict[str, float]],
    ) -> Dict[str, float]:
        result: Dict[str, float] = {}

        for name in _LAG_ROLLING_FEATURE_NAMES:
            history = self.feature_store.get_feature_history(
                symbol, name, as_of - timedelta(days=_LAG_ROLLING_LOOKBACK_DAYS), as_of,
            )
            result.update(lag_rolling_features(history, name))

        for name in _VOLREGIME_FEATURE_NAMES:
            history = self.feature_store.get_feature_history(
                symbol, name, as_of - timedelta(days=_VOLREGIME_LOOKBACK_DAYS), as_of,
            )
            result.update(volatility_regime_features(history, name))

        for name in _CROSS_SECTIONAL_FEATURE_NAMES:
            symbol_value = day_snapshot.get(symbol, {}).get(name)
            basket_values = [values[name] for values in day_snapshot.values() if name in values]
            result.update(cross_sectional_features(symbol_value, basket_values, name))

        if self.price_fetcher is not None:
            ohlcv = self.price_fetcher(
                symbol, as_of - timedelta(weeks=_MULTI_TIMEFRAME_LOOKBACK_WEEKS), as_of,
            )
            result.update(multi_timeframe_features(ohlcv))

        return result
