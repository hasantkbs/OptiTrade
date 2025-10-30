
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

    def predict(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        logger.info(f"Running '{self.name}' model...")

        # Parametreleri kwargs'tan veya config'den al
        rsi_window = kwargs.get('rsi_window', config.PRICE_TREND_RSI_WINDOW)
        macd_fast = kwargs.get('macd_fast', config.PRICE_TREND_MACD_FAST_WINDOW)
        macd_slow = kwargs.get('macd_slow', config.PRICE_TREND_MACD_SLOW_WINDOW)
        macd_sign = kwargs.get('macd_sign', config.PRICE_TREND_MACD_SIGNAL_WINDOW)
        sma_short = kwargs.get('sma_short', config.PRICE_TREND_SMA_SHORT_WINDOW)
        sma_long = kwargs.get('sma_long', config.PRICE_TREND_SMA_LONG_WINDOW)
        bollinger_window = kwargs.get('bollinger_window', config.PRICE_TREND_BOLLINGER_WINDOW)
        bollinger_std = kwargs.get('bollinger_std', config.PRICE_TREND_BOLLINGER_STD)
        adx_window = kwargs.get('adx_window', config.PRICE_TREND_ADX_WINDOW)

        required_data_points = max(rsi_window, macd_slow, sma_long, bollinger_window, adx_window) + 5

        if len(data) < required_data_points:
            logger.warning(f"'{self.name}': Not enough data ({len(data)}/{required_data_points}). Returning neutral scores.")
            return {'score': 0.0, 'details': 'Not enough data.'}

        scores = self._calculate_score(data, rsi_window, macd_fast, macd_slow, macd_sign, sma_short, sma_long, bollinger_window, bollinger_std, adx_window, **kwargs)
        score = scores.iloc[-1]
        logger.info(f"'{self.name}' model result: Score is {score:.4f}.")
        return {'score': score, 'details': f'Price trend score: {score:.2f}'}

    def _calculate_score(self, data: pd.DataFrame, rsi_window: int, macd_fast: int, macd_slow: int, macd_sign: int, sma_short: int, sma_long: int, bollinger_window: int, bollinger_std: float, adx_window: int, **kwargs) -> pd.Series:
        data = data.copy()
        scores = pd.Series(0.0, index=data.index) # Initialize scores Series

        # Calculate indicators
        rsi = ta.momentum.rsi(data['Close'], window=rsi_window)
        macd_diff = ta.trend.macd_diff(data['Close'], window_fast=macd_fast, window_slow=macd_slow, window_sign=macd_sign)
        sma_short_val = ta.trend.sma_indicator(data['Close'], window=sma_short)
        sma_long_val = ta.trend.sma_indicator(data['Close'], window=sma_long)
        adx = ta.trend.adx(data['High'], data['Low'], data['Close'], window=adx_window)
        adx_pos = ta.trend.adx_pos(data['High'], data['Low'], data['Close'], window=adx_window)
        adx_neg = ta.trend.adx_neg(data['High'], data['Low'], data['Close'], window=adx_window)

        # Define weights for each indicator's contribution
        weights = kwargs.get('indicator_weights', config.PRICE_TREND_INDICATOR_WEIGHTS)

        # --- Scoring Logic (Vectorized) ---

        # RSI
        scores -= ((rsi > 70) * (rsi - 70) / 30 * weights.get('rsi_overbought', 0.5)).fillna(0)
        scores += ((rsi < 30) * (30 - rsi) / 30 * weights.get('rsi_oversold', 0.5)).fillna(0)

        # MACD
        scores += (macd_diff / data['Close'] * weights.get('macd_momentum', 5.0)).fillna(0)

        # SMA
        scores += ((sma_short_val > sma_long_val) * weights.get('sma_golden_cross', 0.15)).fillna(0)
        scores -= ((sma_short_val <= sma_long_val) * weights.get('sma_death_cross', 0.15)).fillna(0)

        # ADX
        adx_strong_uptrend = (adx > 25) & (adx_pos > adx_neg)
        adx_strong_downtrend = (adx > 25) & (adx_neg > adx_pos)
        scores += (adx_strong_uptrend * weights.get('adx_uptrend', 0.15)).fillna(0)
        scores -= (adx_strong_downtrend * weights.get('adx_downtrend', 0.15)).fillna(0)

        # Normalize scores using tanh
        final_scores = np.tanh(scores)

        return final_scores
