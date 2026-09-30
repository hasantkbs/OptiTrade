"""
OptiTrade Technical Engine — configuration.

Centralizes the Feature Store feature names this engine reads/writes and
the runtime thresholds every analyzer applies, so both `feature_adapter`
and the analyzer modules share one source of truth for names and tuning.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

# ── Feature Store feature names this engine owns ──────────────────────────────
FEATURE_TREND_STRENGTH = "trend_strength_pct"
FEATURE_EMA_CROSSOVER = "ema_crossover_signal"
FEATURE_MACD_LINE = "macd_line"
FEATURE_MACD_SIGNAL = "macd_signal_line"
FEATURE_MACD_HISTOGRAM = "macd_histogram"
FEATURE_ROC = "roc_10_pct"
FEATURE_RSI = "rsi_14"
FEATURE_BB_PERCENT_B = "bollinger_percent_b"
FEATURE_BB_BANDWIDTH = "bollinger_bandwidth_pct"
FEATURE_ATR = "atr_14"
FEATURE_ATR_PCT = "atr_pct"
FEATURE_VOLUME_RATIO = "volume_ratio"
FEATURE_VWAP_DIFF = "vwap_diff_pct"
FEATURE_SUPPORT_PROXIMITY = "support_proximity_pct"
FEATURE_RESISTANCE_PROXIMITY = "resistance_proximity_pct"
FEATURE_BULLISH_PATTERN_COUNT = "bullish_pattern_count"
FEATURE_BEARISH_PATTERN_COUNT = "bearish_pattern_count"

ALL_FEATURE_NAMES: List[str] = [
    FEATURE_TREND_STRENGTH, FEATURE_EMA_CROSSOVER,
    FEATURE_MACD_LINE, FEATURE_MACD_SIGNAL, FEATURE_MACD_HISTOGRAM, FEATURE_ROC,
    FEATURE_RSI,
    FEATURE_BB_PERCENT_B, FEATURE_BB_BANDWIDTH, FEATURE_ATR, FEATURE_ATR_PCT,
    FEATURE_VOLUME_RATIO, FEATURE_VWAP_DIFF,
    FEATURE_SUPPORT_PROXIMITY, FEATURE_RESISTANCE_PROXIMITY,
    FEATURE_BULLISH_PATTERN_COUNT, FEATURE_BEARISH_PATTERN_COUNT,
]

# EMA crossover string -> numeric encoding, reusing the exact convention
# already established in core/ml_predictor.py's EMA_SIGNAL_ENC.
EMA_CROSSOVER_ENCODING = {
    "GOLDEN_CROSS": 2.0,
    "BULLISH": 1.0,
    "BEARISH": -1.0,
    "DEATH_CROSS": -2.0,
    None: 0.0,
}

# Candlestick patterns core.pattern_scanner.PatternScanner can report,
# classified by directional bias (Doji is deliberately excluded from
# both - it signals indecision, not a bullish or bearish lean).
BULLISH_PATTERNS = {"Hammer", "Bullish Engulfing"}
BEARISH_PATTERNS = {"Shooting Star", "Bearish Engulfing"}


@dataclass(frozen=True)
class TechnicalEngineConfig:
    """Runtime settings: price-history window, feature freshness, and the
    BUY/SELL decision threshold applied to the combined signal."""

    price_period: str = "6mo"
    max_feature_age_seconds: int = 3600  # 1 hour
    decision_threshold: float = 0.2  # |combined signal| must exceed this for BUY/SELL
    expected_return_scale: float = 1.0  # expected_return = signal * atr_pct * this
    volume_average_window: int = 20
    support_resistance_lookback_days: int = 30
    engine_version: str = "v1"

    @classmethod
    def from_env(cls) -> "TechnicalEngineConfig":
        load_dotenv()
        return cls(
            price_period=os.getenv("TECHNICAL_ENGINE_PRICE_PERIOD", "6mo"),
            max_feature_age_seconds=int(
                os.getenv("TECHNICAL_ENGINE_MAX_FEATURE_AGE_SECONDS", "3600")
            ),
            decision_threshold=float(
                os.getenv("TECHNICAL_ENGINE_DECISION_THRESHOLD", "0.2")
            ),
            expected_return_scale=float(
                os.getenv("TECHNICAL_ENGINE_EXPECTED_RETURN_SCALE", "1.0")
            ),
            volume_average_window=int(
                os.getenv("TECHNICAL_ENGINE_VOLUME_AVERAGE_WINDOW", "20")
            ),
            support_resistance_lookback_days=int(
                os.getenv("TECHNICAL_ENGINE_SUPPORT_RESISTANCE_LOOKBACK_DAYS", "30")
            ),
            engine_version=os.getenv("TECHNICAL_ENGINE_VERSION", "v1"),
        )
