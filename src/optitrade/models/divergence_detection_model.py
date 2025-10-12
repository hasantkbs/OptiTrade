
import pandas as pd
import numpy as np
import ta.momentum
from scipy.signal import argrelextrema
import logging
from typing import Dict, List, Any, Tuple

from .base_model import BaseModel
from .. import config
from ..utils.data_fetcher import DataFetcher

# Loglama yapılandırması
logger = logging.getLogger(__name__)

class DivergenceDetectionModel(BaseModel):
    """
    Finds divergences between price and RSI indicator to generate a score.
    """
    def __init__(self, **kwargs):
        super().__init__()
        self.rsi_window = kwargs.get('rsi_window', config.DIVERGENCE_INDICATOR_WINDOW)
        self.extrema_order = kwargs.get('extrema_order', config.DIVERGENCE_EXTREMA_ORDER)
        self.lookback_period = kwargs.get('lookback_period', config.DIVERGENCE_LOOKBACK_PERIOD)
        self.required_data_points = self.lookback_period + 5

    def predict(self, symbol: str, interval: str = "1d", **kwargs) -> Dict[str, Any]:
        logger.info(f"Running '{self.name}' model for {symbol} {interval}...")

        data = kwargs.get('data')
        if not isinstance(data, pd.DataFrame) or data.empty:
            raise ValueError("DivergenceDetectionModel requires a non-empty pandas DataFrame in 'data' kwarg.")

        # Update parameters if provided in kwargs
        self.rsi_window = kwargs.get('rsi_window', self.rsi_window)
        self.extrema_order = kwargs.get('extrema_order', self.extrema_order)
        self.lookback_period = kwargs.get('lookback_period', self.lookback_period)
        self.required_data_points = self.lookback_period + 5 # Ensure enough data for TA indicators

        if len(data) < self.required_data_points:
            logger.warning(f"'{self.name}': Not enough data ({len(data)}/{self.required_data_points}). Returning neutral score.")
            return {'score': 0.0, 'details': f"Not enough data. Need {self.required_data_points} data points, but got {len(data)}."}

        score, details = self._detect_rsi_divergence(data['close'], self.rsi_window, self.extrema_order, self.lookback_period)
        logger.info(f"'{self.name}' model result for {symbol} {interval}: Score={score:.4f}")
        return {'score': score, 'details': details}

    def _find_extrema(self, series: pd.Series, is_max: bool, order: int) -> pd.Series:
        comparator = np.greater if is_max else np.less
        indices = argrelextrema(series.values, comparator, order=order)[0]
        return series.iloc[indices]

    def _detect_rsi_divergence(self, prices: pd.Series, rsi_window: int, extrema_order: int, lookback_period: int) -> Tuple[float, str]:
        if len(prices) < lookback_period:
            return 0.0, "Not enough data."

        prices_slice = prices.iloc[-lookback_period:]
        rsi = ta.momentum.rsi(prices, window=rsi_window).iloc[-lookback_period:]

        if rsi.isnull().all():
            return 0.0, "Could not calculate RSI."

        price_highs = self._find_extrema(prices_slice, is_max=True, order=extrema_order)
        price_lows = self._find_extrema(prices_slice, is_max=False, order=extrema_order)
        rsi_highs = self._find_extrema(rsi, is_max=True, order=extrema_order)
        rsi_lows = self._find_extrema(rsi, is_max=False, order=extrema_order)

        score = 0.0
        details = "No divergence detected."

        # Bearish Divergence: Price -> Higher High, RSI -> Lower High
        if len(price_highs) >= 2 and len(rsi_highs) >= 2:
            if price_highs.iloc[-1] > price_highs.iloc[-2]:
                corresponding_rsi_high1 = rsi.get(price_highs.index[-2])
                corresponding_rsi_high2 = rsi.get(price_highs.index[-1])
                if corresponding_rsi_high1 is not None and corresponding_rsi_high2 is not None:
                    if corresponding_rsi_high2 < corresponding_rsi_high1:
                        score = -0.75
                        details = "Bearish Divergence (Price Higher High, RSI Lower High)"

        # Bullish Divergence: Price -> Lower Low, RSI -> Higher Low
        if score == 0.0 and len(price_lows) >= 2 and len(rsi_lows) >= 2:
            if price_lows.iloc[-1] < price_lows.iloc[-2]:
                corresponding_rsi_low1 = rsi.get(price_lows.index[-2])
                corresponding_rsi_low2 = rsi.get(price_lows.index[-1])
                if corresponding_rsi_low1 is not None and corresponding_rsi_low2 is not None:
                    if corresponding_rsi_low2 > corresponding_rsi_low1:
                        score = 0.75
                        details = "Bullish Divergence (Price Lower Low, RSI Higher Low)"

        return score, details