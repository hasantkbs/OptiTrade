"""
OptiTrade Technical Engine — Feature Store adapter.

The ONLY module in this engine allowed to fetch raw price data or run
indicator math. Every analyzer module (trend.py, momentum.py,
oscillator.py, volatility.py, volume.py, market_structure.py) consumes
only the `Dict[str, float]` this returns — never raw OHLCV, never
`core.indicators`/`pandas_ta`/`core.pattern_scanner` directly.

Reuses existing calculation logic rather than reimplementing it:
`core/indicators.py`'s pure functions (unchanged), `pandas_ta.atr` (the
same ATR call `core/pattern_scanner.py` already uses), and
`core/pattern_scanner.PatternScanner` (unchanged) for candlestick
patterns and support/resistance proximity. `data/fetcher.fetch_history`
(unchanged) supplies the underlying OHLCV.

Feature Store is checked first for each feature name; only missing or
stale (older than `TechnicalEngineConfig.max_feature_age_seconds`)
features trigger a fresh computation, which is then written back to the
Feature Store so subsequent reads are pure cache hits until the next
staleness window.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import numpy as np

if not hasattr(np, "NaN"):
    # Same pandas_ta/numpy compatibility shim already used in
    # core/mtf_analyzer.py and core/pattern_scanner.py.
    np.NaN = np.nan  # type: ignore[attr-defined]

import pandas_ta as ta

from core.indicators import (
    calculate_bollinger_bands,
    calculate_ema_crossover,
    calculate_macd,
    calculate_roc,
    calculate_rsi,
    calculate_trend_strength,
    calculate_volume_ratio,
    calculate_vwap,
)
from core.pattern_scanner import PatternScanner
from core.structured_logging import STATUS_SUCCESS, log_event
from data.fetcher import fetch_history
from engines.technical.config import (
    ALL_FEATURE_NAMES,
    BEARISH_PATTERNS,
    BULLISH_PATTERNS,
    EMA_CROSSOVER_ENCODING,
    FEATURE_ATR,
    FEATURE_ATR_PCT,
    FEATURE_BB_BANDWIDTH,
    FEATURE_BB_PERCENT_B,
    FEATURE_BEARISH_PATTERN_COUNT,
    FEATURE_BULLISH_PATTERN_COUNT,
    FEATURE_EMA_CROSSOVER,
    FEATURE_MACD_HISTOGRAM,
    FEATURE_MACD_LINE,
    FEATURE_MACD_SIGNAL,
    FEATURE_RESISTANCE_PROXIMITY,
    FEATURE_ROC,
    FEATURE_RSI,
    FEATURE_SUPPORT_PROXIMITY,
    FEATURE_TREND_STRENGTH,
    FEATURE_VOLUME_RATIO,
    FEATURE_VWAP_DIFF,
    TechnicalEngineConfig,
)
from feature_store.models import FeatureValue
from feature_store.service import FeatureStoreService

logger = logging.getLogger(__name__)


@dataclass
class FeatureResolution:
    """The resolved features plus which were served from cache vs.
    computed fresh this call — feeds `TechnicalExecutionMetadata`."""

    values: Dict[str, float] = field(default_factory=dict)
    from_cache: List[str] = field(default_factory=list)
    computed_fresh: List[str] = field(default_factory=list)


class TechnicalFeatureAdapter:
    """Bridges the Feature Store with the underlying (reused) indicator
    calculations. Constructed lazily by `engine.py::TechnicalEngine` so
    that merely importing/registering the engine never opens a database
    connection."""

    def __init__(
        self,
        feature_store: Optional[FeatureStoreService] = None,
        config: Optional[TechnicalEngineConfig] = None,
    ) -> None:
        self.feature_store = feature_store or FeatureStoreService()
        self.config = config or TechnicalEngineConfig.from_env()

    def get_features(self, symbol: str) -> FeatureResolution:
        resolution = FeatureResolution()
        missing: List[str] = []
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.config.max_feature_age_seconds)

        for name in ALL_FEATURE_NAMES:
            record = self.feature_store.get_latest_feature(symbol, name)
            if record is not None and record.event_timestamp >= cutoff:
                resolution.values[name] = record.value
                resolution.from_cache.append(name)
            else:
                missing.append(name)

        if missing:
            fresh = self._compute_all(symbol)
            for name in missing:
                if name in fresh:
                    resolution.values[name] = fresh[name]
                    resolution.computed_fresh.append(name)

        log_event(
            logger, component="technical_engine", module="engines.technical.feature_adapter",
            operation="get_features", status=STATUS_SUCCESS, symbol=symbol,
            features_from_cache=len(resolution.from_cache),
            features_computed_fresh=len(resolution.computed_fresh),
        )
        return resolution

    def _compute_all(self, symbol: str) -> Dict[str, float]:
        started_at = time.perf_counter()
        hist = fetch_history(symbol, period=self.config.price_period)
        if hist is None or hist.empty:
            return {}

        prices = hist["Close"]
        high, low, close, volume = hist["High"], hist["Low"], hist["Close"], hist["Volume"]
        current_price = float(prices.iloc[-1])

        values: Dict[str, float] = {}

        trend_strength = calculate_trend_strength(prices)
        if trend_strength is not None:
            values[FEATURE_TREND_STRENGTH] = trend_strength

        ema_crossover = calculate_ema_crossover(prices)
        values[FEATURE_EMA_CROSSOVER] = EMA_CROSSOVER_ENCODING.get(ema_crossover, 0.0)

        macd_line, macd_signal, macd_hist = calculate_macd(prices)
        if macd_line is not None:
            values[FEATURE_MACD_LINE] = macd_line
            values[FEATURE_MACD_SIGNAL] = macd_signal
            values[FEATURE_MACD_HISTOGRAM] = macd_hist

        roc = calculate_roc(prices)
        if roc is not None:
            values[FEATURE_ROC] = roc

        rsi = calculate_rsi(prices)
        if rsi is not None:
            values[FEATURE_RSI] = rsi

        bollinger = calculate_bollinger_bands(prices)
        if bollinger.get("percent_b") is not None:
            values[FEATURE_BB_PERCENT_B] = bollinger["percent_b"]
        if bollinger.get("bandwidth") is not None:
            values[FEATURE_BB_BANDWIDTH] = bollinger["bandwidth"]

        atr_series = ta.atr(high, low, close, length=14)
        if atr_series is not None and not atr_series.empty and not bool(np.isnan(atr_series.iloc[-1])):
            atr_value = float(atr_series.iloc[-1])
            values[FEATURE_ATR] = atr_value
            if current_price > 0:
                values[FEATURE_ATR_PCT] = atr_value / current_price * 100

        current_volume = float(volume.iloc[-1])
        avg_volume = float(volume.tail(self.config.volume_average_window).mean())
        values[FEATURE_VOLUME_RATIO] = calculate_volume_ratio(current_volume, avg_volume)

        vwap = calculate_vwap(high, low, close, volume)
        if vwap is not None and vwap > 0:
            values[FEATURE_VWAP_DIFF] = (current_price - vwap) / vwap * 100

        scanner = PatternScanner(
            support_resistance_lookback_days=self.config.support_resistance_lookback_days
        )
        scan = scanner.scan(daily_df=hist, hourly_df=None)
        if scan.get("support_proximity_pct") is not None:
            values[FEATURE_SUPPORT_PROXIMITY] = scan["support_proximity_pct"]
        if scan.get("resistance_proximity_pct") is not None:
            values[FEATURE_RESISTANCE_PROXIMITY] = scan["resistance_proximity_pct"]

        active_patterns = scan.get("active_patterns", [])
        values[FEATURE_BULLISH_PATTERN_COUNT] = float(
            sum(1 for p in active_patterns if any(p.startswith(bp) for bp in BULLISH_PATTERNS))
        )
        values[FEATURE_BEARISH_PATTERN_COUNT] = float(
            sum(1 for p in active_patterns if any(p.startswith(bp) for bp in BEARISH_PATTERNS))
        )

        for name, value in values.items():
            self.feature_store.write_feature(FeatureValue(symbol=symbol, feature_name=name, value=value))

        log_event(
            logger, component="technical_engine", module="engines.technical.feature_adapter",
            operation="compute_all", status=STATUS_SUCCESS, symbol=symbol,
            features_computed=len(values),
            execution_time_ms=(time.perf_counter() - started_at) * 1000,
        )
        return values
