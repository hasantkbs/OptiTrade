import logging
import pandas as pd
import ta
from typing import Dict, Any

from .base_model import BaseModel
from ..utils.data_fetcher import DataFetcher

logger = logging.getLogger(__name__)

class MarketConditionClassifier(BaseModel):
    """
    ADX ve +/-DI göstergelerini kullanarak mevcut piyasa rejimini sınıflandırır.
    Bu model bir al/sat 'skoru' üretmez, bunun yerine bir 'rejim' tanımı döndürür.
    """
    def __init__(self, **kwargs):
        super().__init__()
        self.adx_window = kwargs.get('adx_window', 14)
        self.adx_threshold = kwargs.get('adx_threshold', 25)
        self.required_data_points = self.adx_window * 2

    def predict(self, symbol: str, interval: str = "1d", **kwargs) -> Dict[str, Any]:
        """
        Analyzes the market condition and returns a Series of regime classifications.
        """
        logger.info(f"Running '{self.name}' model...")
        
        # Update parameters if provided in kwargs
        self.adx_window = kwargs.get('adx_window', self.adx_window)
        self.adx_threshold = kwargs.get('adx_threshold', self.adx_threshold)

        try:
            data = self.data_fetcher.get_historical_data(symbol, interval, limit=self.required_data_points)
            if data.empty or len(data) < self.required_data_points:
                logger.warning(f"'{self.name}': Not enough data. Returning 'Unknown' regimes.")
                return {"regime": "Unknown"}

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
            
            return {"regime": regime}

        except Exception as e:
            logger.error(f"An error occurred while running '{self.name}': {e}", exc_info=True)
            return {"regime": "Unknown"}
