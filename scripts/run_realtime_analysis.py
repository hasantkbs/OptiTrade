import asyncio
import os
from dotenv import load_dotenv
import pandas as pd
import traceback
import logging

# Configure root logger to show all messages to console
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Configuration for Analysis Results Log ---
ANALYSIS_LOG_FILE = "analysis_results.log"

# Create a dedicated logger for analysis results
analysis_logger = logging.getLogger("analysis_results")
analysis_logger.setLevel(logging.INFO) # Set level for analysis results

# Create a file handler for analysis results
analysis_file_handler = logging.FileHandler(ANALYSIS_LOG_FILE)
analysis_file_handler.setLevel(logging.INFO)

# Create a formatter and add it to the file handler
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
analysis_file_handler.setFormatter(formatter)

# Add the file handler to the analysis logger
analysis_logger.addHandler(analysis_file_handler)

# Prevent analysis_logger messages from propagating to the root logger (and thus to console twice)
analysis_logger.propagate = False

from src.optitrade.realtime.binance_stream_handler import BinanceStreamHandler
from src.optitrade.realtime.processor import Processor

# Import models
from src.optitrade.models.scalping_model import ScalpingModel
from src.optitrade.models.divergence_detection_model import DivergenceDetectionModel
from src.optitrade.models.support_resistance_model import SupportResistanceModel
from src.optitrade.models.price_trend_model import PriceTrendModel
from src.optitrade.models.market_condition_classifier import MarketConditionClassifier

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
# Replace with your actual API key and secret, or load from environment variables
API_KEY = os.getenv("BINANCE_API_KEY", "YOUR_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET", "YOUR_API_SECRET")

# Define the symbols and intervals for streaming
SYMBOLS_TO_STREAM = ['BTCUSDT', 'ETHUSDT'] # Example symbols

# Short-term intervals
SHORT_TERM_INTERVALS = ['1m', '15m']

# Long-term intervals
LONG_TERM_INTERVALS = ['4h', '1w', '1M'] # 1M for 1 month

# Combine all unique intervals for the stream handler
ALL_INTERVALS = list(set(SHORT_TERM_INTERVALS + LONG_TERM_INTERVALS + ['4h'])) # Ensure 4h is included for both

# --- Model Instances (initialized once) ---
# Short-term models
scalping_model = ScalpingModel()
divergence_model = DivergenceDetectionModel()
support_resistance_model = SupportResistanceModel()

# Long-term models
price_trend_model = PriceTrendModel()
market_condition_classifier = MarketConditionClassifier()

# --- Analysis Pipelines ---
async def short_term_analysis_pipeline(kline_history_df: pd.DataFrame):
    """Runs short-term analysis models on the kline history."""
    if kline_history_df.empty:
        return

    latest_kline = kline_history_df.iloc[-1]
    symbol = latest_kline['symbol']
    interval = latest_kline['interval']

    analysis_logger.info(f"\n--- SHORT-TERM ANALYSIS for {symbol} {interval} ---")

    # Scalping Model
    try:
        scalping_result = scalping_model.predict(symbol=symbol, interval=interval, data=kline_history_df)
        analysis_logger.info(f"  Scalping Model: Score={scalping_result.get('score')}, Details={scalping_result.get('details')}")
    except Exception as e:
        analysis_logger.error(f"  Error running Scalping Model: {e}\n{traceback.format_exc()}")

    # Divergence Detection Model
    try:
        divergence_result = divergence_model.predict(symbol=symbol, interval=interval, data=kline_history_df)
        analysis_logger.info(f"  Divergence Model: Score={divergence_result.get('score')}, Details={divergence_result.get('details')}")
    except Exception as e:
        analysis_logger.error(f"  Error running Divergence Detection Model: {e}\n{traceback.format_exc()}")

    # Support/Resistance Model
    try:
        sr_result = support_resistance_model.predict(symbol=symbol, interval=interval, data=kline_history_df)
        analysis_logger.info(f"  Support/Resistance Model: Score={sr_result.get('score')}, Details={sr_result.get('details')}")
    except Exception as e:
        analysis_logger.error(f"  Error running Support/Resistance Model: {e}\n{traceback.format_exc()}")

async def long_term_analysis_pipeline(kline_history_df: pd.DataFrame):
    """Runs long-term analysis models on the kline history."""
    if kline_history_df.empty:
        return

    latest_kline = kline_history_df.iloc[-1]
    symbol = latest_kline['symbol']
    interval = latest_kline['interval']

    analysis_logger.info(f"\n--- LONG-TERM ANALYSIS for {symbol} {interval} ---")

    # Price Trend Model
    try:
        price_trend_result = price_trend_model.predict(symbol=symbol, interval=interval, data=kline_history_df)
        analysis_logger.info(f"  Price Trend Model: Score={price_trend_result.get('score')}, Details={price_trend_result.get('details')}")
    except Exception as e:
        analysis_logger.error(f"  Error running Price Trend Model: {e}\n{traceback.format_exc()}")

    # Market Condition Classifier
    try:
        mcc_result = market_condition_classifier.predict(symbol=symbol, interval=interval, data=kline_history_df)
        analysis_logger.info(f"  Market Condition Classifier: Score={mcc_result.get('score')}, Details={mcc_result.get('details')}")
    except Exception as e:
        analysis_logger.error(f"  Error running Market Condition Classifier: {e}\n{traceback.format_exc()}")

# --- Main Orchestration Logic ---
async def main():
    if API_KEY == "YOUR_API_KEY" or API_SECRET == "YOUR_API_SECRET":
        logging.warning("Binance API keys are not set. Please set BINANCE_API_KEY and BINANCE_API_SECRET environment variables or replace placeholders.")
        logging.warning("Running with dummy API keys, connection to Binance will likely fail.")

    stream_handler = BinanceStreamHandler(API_KEY, API_SECRET, SYMBOLS_TO_STREAM, ALL_INTERVALS)
    processor = Processor()

    # Register model pipelines with the processor
    for interval in SHORT_TERM_INTERVALS:
        processor.register_model_pipeline("short_term", interval, short_term_analysis_pipeline)
    
    # Special handling for 4h as it's both short and long term
    processor.register_model_pipeline("short_term", '4h', short_term_analysis_pipeline)
    processor.register_model_pipeline("long_term", '4h', long_term_analysis_pipeline)

    for interval in LONG_TERM_INTERVALS:
        if interval != '4h': # 4h already handled
            processor.register_model_pipeline("long_term", interval, long_term_analysis_pipeline)

    # Register the processor's method as a callback for all intervals from the stream handler
    for interval in ALL_INTERVALS:
        stream_handler.register_kline_callback(interval, processor.process_kline_data)

    try:
        logging.info("Starting real-time analysis...")
        await stream_handler.start_kline_streams()
        # Keep the main task running to allow streams to operate
        while True:
            await asyncio.sleep(1) # Sleep to prevent CPU hogging
    except KeyboardInterrupt:
        logging.info("Stopping real-time analysis...")
    finally:
        await stream_handler.stop_kline_streams()

if __name__ == '__main__':
    # To run this script:
    # 1. Install dependencies: pip install python-binance python-dotenv
    # 2. Set your Binance API_KEY and API_SECRET in a .env file or directly in the script.
    # 3. Run: python scripts/run_realtime_analysis.py
    asyncio.run(main())
