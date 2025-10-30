import logging
import pandas as pd
import ta
from typing import Dict, Any

from .base_model import BaseModel
from .. import config

logger = logging.getLogger(__name__)

class MarketConditionClassifier(BaseModel):
    """
    ADX ve +/-DI göstergelerini kullanarak mevcut piyasa rejimini sınıflandırır.
    """
    def __init__(self, **kwargs):
        super().__init__()
        self.adx_window = kwargs.get('adx_window', config.MARKET_CLASSIFIER_ADX_WINDOW)
        self.adx_threshold = kwargs.get('adx_threshold', config.MARKET_CLASSIFIER_ADX_THRESHOLD)
        self.required_data_points = self.adx_window * 2

    def predict(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """
        Analyzes the market condition and returns a Series of regime classifications.
        """
        logger.info(f"Running '{self.name}' model...")
        
        if data.empty or len(data) < self.required_data_points:
            logger.warning(f"'{self.name}': Not enough data ({len(data)}/{self.required_data_points}). Returning 'Unknown'.")
            return {'score': 0.0, "regime": "Unknown", "details": "Not enough data"}

        # ADX and +/-DI indicators
        adx_indicator = ta.trend.ADXIndicator(
            high=data['High'],
            low=data['Low'],
            close=data['Close'],
            window=self.adx_window
        )
        adx = adx_indicator.adx().iloc[-1]
        di_pos = adx_indicator.adx_pos().iloc[-1]
        di_neg = adx_indicator.adx_neg().iloc[-1]

        regime = "Unknown"
        if adx > self.adx_threshold:
            if di_pos > di_neg:
                regime = "Strong Bull Trend"
            else:
                regime = "Strong Bear Trend"
        else:
            if di_pos > di_neg:
                regime = "Weak Bull Trend"
            else:
                regime = "Weak Bear Trend"

        logger.info(f"'{self.name}' result: Regime is {regime}.")
        
        return {'score': 0.0, "regime": regime, "details": f"Regime: {regime}"}
