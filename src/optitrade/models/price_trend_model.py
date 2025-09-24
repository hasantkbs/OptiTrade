
import pandas as pd
import numpy as np
import ta
import logging
from typing import Dict, Any, Tuple

from .base_model import BaseModel
from .. import config

# Loglama yapılandırması
logger = logging.getLogger(__name__)

class PriceTrendModel(BaseModel):
    """
    Generates a price trend score using technical analysis indicators.
    """
    def __init__(self):
        super().__init__()

    def generate_score(self, data: pd.DataFrame) -> float:
        logger.info(f"Running '{self.name}' model...")
        
        # Get parameters from config
        rsi_window = config.PRICE_TREND_RSI_WINDOW
        macd_fast = config.PRICE_TREND_MACD_FAST_WINDOW
        macd_slow = config.PRICE_TREND_MACD_SLOW_WINDOW
        macd_sign = config.PRICE_TREND_MACD_SIGNAL_WINDOW
        sma_short = config.PRICE_TREND_SMA_SHORT_WINDOW
        sma_long = config.PRICE_TREND_SMA_LONG_WINDOW
        bollinger_window = config.PRICE_TREND_BOLLINGER_WINDOW
        bollinger_std = config.PRICE_TREND_BOLLINGER_STD
        adx_window = config.PRICE_TREND_ADX_WINDOW

        required_data_points = max(rsi_window, macd_slow, sma_long, bollinger_window, adx_window) + 5

        if data.empty or len(data) < required_data_points:
            logger.warning(f"'{self.name}': Not enough data ({len(data)}/{required_data_points}). Returning neutral score (0.0).")
            return 0.0

        try:
            score, _ = self._calculate_score(data, rsi_window, macd_fast, macd_slow, macd_sign, sma_short, sma_long, bollinger_window, bollinger_std, adx_window)
            logger.info(f"'{self.name}' model result: Score={score:.4f}")
            return score
        except Exception as e:
            logger.error(f"An error occurred while running the '{self.name}' model: {e}", exc_info=True)
            return 0.0

    def _calculate_score(self, data: pd.DataFrame, rsi_window: int, macd_fast: int, macd_slow: int, macd_sign: int, sma_short: int, sma_long: int, bollinger_window: int, bollinger_std: float, adx_window: int) -> Tuple[float, str]:
        data = data.copy()
        details = []
        score = 0.0

        # Calculate indicators
        rsi = ta.momentum.rsi(data['Close'], window=rsi_window)
        macd_diff = ta.trend.macd_diff(data['Close'], window_fast=macd_fast, window_slow=macd_slow, window_sign=macd_sign)
        sma_short_val = ta.trend.sma_indicator(data['Close'], window=sma_short)
        sma_long_val = ta.trend.sma_indicator(data['Close'], window=sma_long)
        adx = ta.trend.adx(data['High'], data['Low'], data['Close'], window=adx_window)
        adx_pos = ta.trend.adx_pos(data['High'], data['Low'], data['Close'], window=adx_window)
        adx_neg = ta.trend.adx_neg(data['High'], data['Low'], data['Close'], window=adx_window)

        # --- Scoring Logic ---
        last_rsi = rsi.iloc[-1]
        if not pd.isna(last_rsi):
            if last_rsi > 70: 
                score -= (last_rsi - 70) / 30 * 0.5
                details.append(f"RSI Overbought ({last_rsi:.2f})")
            elif last_rsi < 30: 
                score += (30 - last_rsi) / 30 * 0.5
                details.append(f"RSI Oversold ({last_rsi:.2f})")

        last_macd_diff = macd_diff.iloc[-1]
        if not pd.isna(last_macd_diff):
            score += (last_macd_diff / data['Close'].iloc[-1]) * 5
            if last_macd_diff > 0: details.append("MACD Positive Momentum")
            else: details.append("MACD Negative Momentum")

        last_sma_short = sma_short_val.iloc[-1]
        last_sma_long = sma_long_val.iloc[-1]
        if not pd.isna(last_sma_short) and not pd.isna(last_sma_long):
            if last_sma_short > last_sma_long: 
                score += 0.15
                details.append("SMA Golden Cross")
            else: 
                score -= 0.15
                details.append("SMA Death Cross")

        last_adx = adx.iloc[-1]
        if not pd.isna(last_adx) and last_adx > 25:
            last_adx_pos = adx_pos.iloc[-1]
            last_adx_neg = adx_neg.iloc[-1]
            if not pd.isna(last_adx_pos) and not pd.isna(last_adx_neg):
                if last_adx_pos > last_adx_neg: 
                    score += 0.15
                    details.append(f"ADX Strong Uptrend ({last_adx:.2f})")
                else: 
                    score -= 0.15
                    details.append(f"ADX Strong Downtrend ({last_adx:.2f})")
        
        final_score = float(np.tanh(score))
        final_details = ", ".join(details) if details else "Neutral trend signal."
        return final_score, final_details
