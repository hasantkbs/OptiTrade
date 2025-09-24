import pandas as pd
import yfinance as yf
import logging
from typing import Dict, Any

from .base_model import BaseModel

logger = logging.getLogger(__name__)

class FinancialRatioModel(BaseModel):
    """
    Calculates financial ratios for a given stock and generates a score.
    """
    def __init__(self):
        super().__init__()

    def generate_score(self, data: pd.DataFrame, symbol: str) -> float:
        logger.info(f"Running '{self.name}' model for {symbol}...")

        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            pe_ratio = info.get('trailingPE')
            pb_ratio = info.get('priceToBook')
            de_ratio = info.get('debtToEquity')

            if pe_ratio is None or pb_ratio is None or de_ratio is None:
                logger.warning(f"Could not retrieve all financial ratios for {symbol}.")
                return 0.0

            # This is a very simple scoring logic. A more sophisticated model would use a more robust scoring method.
            score = 0.0
            if pe_ratio < 15:
                score += 0.3
            if pb_ratio < 1.5:
                score += 0.3
            if de_ratio < 1.0:
                score += 0.4

            return score
        except Exception as e:
            logger.error(f"An error occurred while running the '{self.name}' model for {symbol}: {e}", exc_info=True)
            return 0.0

    def get_ratios(self, symbol: str) -> Dict[str, Any]:
        """Gets all financial ratios for a given stock."""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            return {
                'pe_ratio': info.get('trailingPE'),
                'pb_ratio': info.get('priceToBook'),
                'de_ratio': info.get('debtToEquity'),
            }
        except Exception as e:
            logger.error(f"An error occurred while fetching financial ratios for {symbol}: {e}", exc_info=True)
            return {}