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

    def generate_score(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """
        Analyzes the market condition and returns a regime classification.
        This model does not produce a trading score, so the score is always 0.
        """
        logger.info(f"Running '{self.name}' model...")
        
        # Update parameters if provided in kwargs
        self.adx_window = kwargs.get('adx_window', self.adx_window)
        self.adx_threshold = kwargs.get('adx_threshold', self.adx_threshold)

        if data.empty or len(data) < self.required_data_points:
            logger.warning(f"'{self.name}': Not enough data.")
            return {"score": 0.0, "details": "Not enough data", "regime": "Unknown"}

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

            latest_adx = adx.iloc[-1]
            latest_di_pos = di_pos.iloc[-1]
            latest_di_neg = di_neg.iloc[-1]

            # Classify the regime
            regime = ""
            if latest_adx > self.adx_threshold:
                if latest_di_pos > latest_di_neg:
                    regime = "Strong Bull Trend"
                    details = f"Strong uptrend detected (ADX: {latest_adx:.2f})"
                else:
                    regime = "Strong Bear Trend"
                    details = f"Strong downtrend detected (ADX: {latest_adx:.2f})"
            else:
                if latest_di_pos > latest_di_neg:
                    regime = "Weak Bull Trend"
                    details = f"Weak uptrend or ranging market (ADX: {latest_adx:.2f})"
                else:
                    regime = "Weak Bear Trend"
                    details = f"Weak downtrend or ranging market (ADX: {latest_adx:.2f})"

            logger.info(f"'{self.name}' result: Regime={regime}, Details: {details}")
            
            return {
                "score": 0.0, # This model does not produce a trading score
                "details": details,
                "regime": regime
            }

        except Exception as e:
            logger.error(f"An error occurred while running '{self.name}': {e}", exc_info=True)
            return {"score": 0.0, "details": f"Error during model execution: {e}", "regime": "Unknown"}
