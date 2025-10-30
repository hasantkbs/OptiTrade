
import logging
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
import ta
from typing import Dict, Any

from .base_model import BaseModel
from .. import config

logger = logging.getLogger(__name__)

class DivergenceDetectionModel(BaseModel):
    """
    Detects bullish and bearish divergences between price and an indicator (e.g., RSI, MACD).
    """
    def __init__(self, **kwargs):
        super().__init__()
        self.indicator_window = kwargs.get('indicator_window', config.DIVERGENCE_INDICATOR_WINDOW)
        self.extrema_order = kwargs.get('extrema_order', config.DIVERGENCE_EXTREMA_ORDER)

    def predict(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        logger.info(f"Running '{self.name}' model...")

        if data.empty or len(data) < self.indicator_window + self.extrema_order:
            return {'score': 0.0, 'details': 'Not enough data for divergence detection.'}

        # Calculate RSI
        rsi = ta.momentum.rsi(data['Close'], window=self.indicator_window)

        # Find price and RSI extrema
        price_lows = argrelextrema(data['Low'].values, np.less, order=self.extrema_order)[0]
        price_highs = argrelextrema(data['High'].values, np.greater, order=self.extrema_order)[0]
        rsi_lows = argrelextrema(rsi.values, np.less, order=self.extrema_order)[0]
        rsi_highs = argrelextrema(rsi.values, np.greater, order=self.extrema_order)[0]

        score = 0.0
        details = "No divergence detected."

        # Bullish Divergence Check (lower low in price, higher low in RSI)
        if len(price_lows) >= 2 and len(rsi_lows) >= 2:
            if data['Low'][price_lows[-1]] < data['Low'][price_lows[-2]] and rsi[rsi_lows[-1]] > rsi[rsi_lows[-2]]:
                score = 0.7
                details = "Bullish divergence detected (Price: LL, RSI: HL)."

        # Bearish Divergence Check (higher high in price, lower high in RSI)
        if len(price_highs) >= 2 and len(rsi_highs) >= 2:
            if data['High'][price_highs[-1]] > data['High'][price_highs[-2]] and rsi[rsi_highs[-1]] < rsi[rsi_highs[-2]]:
                score = -0.7
                details = "Bearish divergence detected (Price: HH, RSI: LH)."

        logger.info(f"'{self.name}' model result: {details}")
        return {'score': score, 'details': details}