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

    def generate_score(self, data: pd.DataFrame, **kwargs) -> pd.Series: # Changed return type
        """
        Analyzes the market condition and returns a Series of regime classifications.
        """
        logger.info(f"Running '{self.name}' model...")
        
        # Update parameters if provided in kwargs
        self.adx_window = kwargs.get('adx_window', self.adx_window)
        self.adx_threshold = kwargs.get('adx_threshold', self.adx_threshold)

        if data.empty or len(data) < self.required_data_points:
            logger.warning(f"'{self.name}': Not enough data. Returning 'Unknown' regimes.")
            return pd.Series("Unknown", index=data.index) # Return a Series of "Unknown"

        try:
            # ADX and +/-DI indicators
            adx_indicator = ta.trend.ADXIndicator(
                high=data['High'],
                low=data['Low'],
                close=data['Close'],
                window=self.adx_window
            )
            adx = adx_indicator.adx()
            di_pos = adx_indicator.adx_pos()
            di_neg = adx_indicator.adx_neg()

            # Initialize a Series for regimes
            regimes = pd.Series("Unknown", index=data.index)

            # Vectorized classification
            strong_trend_condition = adx > self.adx_threshold
            bull_trend_condition = di_pos > di_neg

            regimes[strong_trend_condition & bull_trend_condition] = "Strong Bull Trend"
            regimes[strong_trend_condition & ~bull_trend_condition] = "Strong Bear Trend"
            regimes[~strong_trend_condition & bull_trend_condition] = "Weak Bull Trend"
            regimes[~strong_trend_condition & ~bull_trend_condition] = "Weak Bear Trend"

            # Handle NaN values that might result from indicator calculations
            regimes = regimes.fillna("Unknown")

            logger.info(f"'{self.name}' result: Regimes generated for {len(regimes)} data points.")
            
            return regimes

        except Exception as e:
            logger.error(f"An error occurred while running '{self.name}': {e}", exc_info=True)
            return pd.Series("Unknown", index=data.index) # Return a Series of "Unknown" on error
