import pandas as pd
import numpy as np
import yfinance as yf
import logging
from typing import Dict, Any

from .base_model import BaseModel

logger = logging.getLogger(__name__)

class DCFModel(BaseModel):
    """
    Implements the Dividend Discount Model (DDM) for stock valuation.
    """
    def __init__(self):
        super().__init__()
        # Risk-free rate (e.g., 10-year US Treasury yield). This should be updated periodically.
        self.risk_free_rate = 0.02
        # Market return (e.g., historical average return of the S&P 500).
        self.market_return = 0.10

    def generate_score(self, data: pd.DataFrame, symbol: str) -> float:
        logger.info(f"Running '{self.name}' model for {symbol}...")

        try:
            ticker = yf.Ticker(symbol)
            
            # Get the most recent dividend
            dividends = ticker.dividends
            if dividends.empty:
                logger.warning(f"No dividend data found for {symbol}. DDM not applicable.")
                return 0.0
            latest_dividend = dividends.iloc[-1]

            # Get historical dividends to calculate growth rate
            historical_dividends = dividends[dividends.index > (pd.Timestamp.now() - pd.DateOffset(years=5))]
            if len(historical_dividends) < 2:
                logger.warning(f"Not enough historical dividend data to calculate growth rate for {symbol}.")
                # Use a default growth rate if not enough data
                dividend_growth_rate = 0.02
            else:
                # Calculate the compound annual growth rate (CAGR)
                cagr = (historical_dividends.iloc[-1] / historical_dividends.iloc[0]) ** (1 / (len(historical_dividends) / 4)) - 1
                dividend_growth_rate = max(0, cagr) # Ensure growth rate is not negative

            # Get beta for CAPM
            beta = ticker.info.get('beta')
            if not beta:
                logger.warning(f"Beta not available for {symbol}. Using default beta of 1.")
                beta = 1.0

            # Calculate the required rate of return (cost of equity) using CAPM
            required_rate_of_return = self.risk_free_rate + beta * (self.market_return - self.risk_free_rate)

            if required_rate_of_return <= dividend_growth_rate:
                logger.warning(f"Required rate of return ({required_rate_of_return:.4f}) is not greater than the dividend growth rate ({dividend_growth_rate:.4f}). DDM not applicable.")
                return 0.0

            # Calculate the intrinsic value using the Gordon Growth Model (a form of DDM)
            intrinsic_value = (latest_dividend * (1 + dividend_growth_rate)) / (required_rate_of_return - dividend_growth_rate)

            # Get the current stock price
            current_price = data['Close'].iloc[-1]

            # Generate a score based on the difference between the intrinsic value and the current price
            # A positive score indicates the stock is undervalued, and a negative score indicates it is overvalued.
            score = (intrinsic_value - current_price) / current_price
            
            # Normalize the score to be between -1 and 1
            score = np.tanh(score)

            logger.info(f"'{self.name}' model result for {symbol}: Intrinsic Value={intrinsic_value:.2f}, Current Price={current_price:.2f}, Score={score:.4f}")
            return score

        except Exception as e:
            logger.error(f"An error occurred while running the '{self.name}' model for {symbol}: {e}", exc_info=True)
            return 0.0