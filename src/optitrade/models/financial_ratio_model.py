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

    def generate_score(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        symbol = kwargs.get('symbol')
        if not symbol:
            logger.warning(f"'{self.name}': Symbol not provided. Returning neutral score.")
            return {'score': 0.0, 'details': "Symbol not provided."}

        logger.info(f"Running '{self.name}' model for {symbol}...")

        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            pe_ratio = info.get('trailingPE')
            pb_ratio = info.get('priceToBook')
            de_ratio = info.get('debtToEquity')

            ratios = {
                'P/E Ratio': pe_ratio,
                'P/B Ratio': pb_ratio,
                'Debt/Equity Ratio': de_ratio
            }

            if pe_ratio is None or pb_ratio is None or de_ratio is None:
                logger.warning(f"Could not retrieve all financial ratios for {symbol}.")
                return {'score': 0.0, 'details': "Could not retrieve all financial ratios.", 'ratios': ratios}

            # This is a very simple scoring logic. A more sophisticated model would use a more robust scoring method.
            score = 0.0
            details = []
            if pe_ratio < 15:
                score += 0.3
                details.append(f"P/E ({pe_ratio:.2f}) is attractive.")
            elif pe_ratio > 30:
                score -= 0.2
                details.append(f"P/E ({pe_ratio:.2f}) is high.")

            if pb_ratio < 1.5:
                score += 0.3
                details.append(f"P/B ({pb_ratio:.2f}) is attractive.")
            elif pb_ratio > 3:
                score -= 0.2
                details.append(f"P/B ({pb_ratio:.2f}) is high.")

            if de_ratio < 1.0:
                score += 0.4
                details.append(f"D/E ({de_ratio:.2f}) is low.")
            elif de_ratio > 2.0:
                score -= 0.3
                details.append(f"D/E ({de_ratio:.2f}) is high.")

            return {'score': score, 'details': ", ".join(details), 'ratios': ratios}
        except Exception as e:
            logger.error(f"An error occurred while running the '{self.name}' model for {symbol}: {e}", exc_info=True)
            return {'score': 0.0, 'details': f"Error during model execution: {e}"}

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