import pandas as pd
import numpy as np
import ta
import argparse
import logging
from .. import config

# Logging configuration
logging.basicConfig(
    level=config.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class PriceTrendModel:
    """
    Generates a score from price data using technical analysis indicators.
    """
    def __init__(self, rsi_window: int = config.PRICE_TREND_RSI_WINDOW, **kwargs):
        """
        Initializes the model and sets indicator parameters.
        """
        self.rsi_window = rsi_window
        self.macd_fast_window = config.PRICE_TREND_MACD_FAST_WINDOW
        self.macd_slow_window = config.PRICE_TREND_MACD_SLOW_WINDOW
        self.macd_signal_window = config.PRICE_TREND_MACD_SIGNAL_WINDOW
        self.sma_short_window = config.PRICE_TREND_SMA_SHORT_WINDOW
        self.sma_long_window = config.PRICE_TREND_SMA_LONG_WINDOW
        self.bollinger_window = config.PRICE_TREND_BOLLINGER_WINDOW
        self.bollinger_std = config.PRICE_TREND_BOLLINGER_STD
        self.adx_window = config.PRICE_TREND_ADX_WINDOW

    def generate_score(self, data: pd.DataFrame) -> float:
        """
        Calculates a trend score based on a dataframe of historical price data.
        The dataframe must contain 'Open', 'High', 'Low', 'Close' columns.
        """
        logger.debug(f"PriceTrendModel: generate_score called.")
        logger.debug(f"Input data shape: {data.shape}")

        if data.empty or len(data) < self.sma_long_window:
            logger.warning("PriceTrendModel: Not enough data to generate a score. Returning neutral score.")
            return 0.0

        # Work on a copy to avoid side effects
        data = data.copy()

        # Ensure column names are lowercase for consistency
        data.columns = [col.lower() for col in data.columns]
        logger.debug(f"Data columns after lowercasing: {data.columns.tolist()}")
        logger.debug(f"Shape of data['close']: {data['close'].shape if 'close' in data.columns else 'N/A'}")
        logger.debug(f"Shape of data['high']: {data['high'].shape if 'high' in data.columns else 'N/A'}")
        logger.debug(f"Shape of data['low']: {data['low'].shape if 'low' in data.columns else 'N/A'}")

        # Calculate indicators
        rsi = ta.momentum.rsi(data['close'], window=self.rsi_window)
        macd_diff = ta.trend.macd_diff(data['close'], window_fast=self.macd_fast_window, window_slow=self.macd_slow_window, window_sign=self.macd_signal_window)
        sma_short = ta.trend.sma_indicator(data['close'], window=self.sma_short_window)
        sma_long = ta.trend.sma_indicator(data['close'], window=self.sma_long_window)
        bollinger_hband = ta.volatility.bollinger_hband(data['close'], window=self.bollinger_window, window_dev=self.bollinger_std)
        bollinger_lband = ta.volatility.bollinger_lband(data['close'], window=self.bollinger_window, window_dev=self.bollinger_std)
        adx = ta.trend.adx(data['high'], data['low'], data['close'], window=self.adx_window)
        adx_pos = ta.trend.adx_pos(data['high'], data['low'], data['close'], window=self.adx_window)
        adx_neg = ta.trend.adx_neg(data['high'], data['low'], data['close'], window=self.adx_window)

        # --- Scoring Logic ---
        score = 0.0
        # RSI Score
        last_rsi = rsi.iloc[-1]
        if not pd.isna(last_rsi):
            if last_rsi > 70: score -= (last_rsi - 70) / 30 * 0.5
            elif last_rsi < 30: score += (30 - last_rsi) / 30 * 0.5

        # MACD Score
        if not macd_diff.empty and not pd.isna(macd_diff.iloc[-1]) and not pd.isna(macd_diff.iloc[-2]):
            if macd_diff.iloc[-1] > 0 and macd_diff.iloc[-2] <= 0: score += 0.4
            elif macd_diff.iloc[-1] < 0 and macd_diff.iloc[-2] >= 0: score -= 0.4

        # Moving Average Score
        if not sma_short.empty and not pd.isna(sma_short.iloc[-1]) and not sma_long.empty and not pd.isna(sma_long.iloc[-1]):
            if sma_short.iloc[-1] > sma_long.iloc[-1]: score += 0.1
            else: score -= 0.1

        # Bollinger Bands Score
        if not pd.isna(bollinger_hband.iloc[-1]) and not pd.isna(bollinger_lband.iloc[-1]):
            if data['close'].iloc[-1] > bollinger_hband.iloc[-1]: score -= 0.2
            elif data['close'].iloc[-1] < bollinger_lband.iloc[-1]: score += 0.2

        # ADX Score
        if not pd.isna(adx.iloc[-1]) and not pd.isna(adx_pos.iloc[-1]) and not pd.isna(adx_neg.iloc[-1]):
            if adx.iloc[-1] > 25:
                if adx_pos.iloc[-1] > adx_neg.iloc[-1]: score += 0.2
                else: score -= 0.2

        # Normalize the final score to be between -1.0 and 1.0
        normalized_score = np.tanh(score)
        logger.debug(f"PriceTrendModel: generated score = {normalized_score:.4f}")
        return float(normalized_score)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Calculate the price trend score from a CSV file.')
    parser.add_argument(
        "--filepath", 
        type=str, 
        required=True, 
        help='Path to the historical data CSV file (e.g., data/BTC-USD_1h.csv).'
    )
    args = parser.parse_args()

    logger.info(f"--- Calculating Price Trend Score for {args.filepath} ---")

    if not os.path.exists(args.filepath):
        logger.error(f"Error: File not found at {args.filepath}")
    else:
        try:
            # Load data from the CSV file
            data_df = pd.read_csv(args.filepath, index_col='Date', parse_dates=True)
            
            # Instantiate the model and generate the score
            model = PriceTrendModel()
            trend_score = model.generate_score(data_df)
            logger.info(f"Calculated Price Trend Score: {trend_score:.4f}")

        except Exception as e:
            logger.error(f"An error occurred during score calculation: {e}")
