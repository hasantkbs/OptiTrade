import asyncio
import logging
import sys
import os

# Add the project root to the Python path to allow for absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.optitrade.realtime.processor import RealtimeProcessor

# --- Configuration ---
BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"
BAR_INTERVAL_MINUTES = 1 # Aggregate trades into 1-minute bars
MODEL_LOOKBACK_BARS = 50 # Number of bars needed for the PriceTrendModel (e.g., for SMA_LONG_WINDOW)

async def main():
    """
    Initializes and runs the real-time data processing pipeline.
    """
    # Configure basic logging to see output from the processor
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        stream=sys.stdout
    )
    
    logger = logging.getLogger(__name__)
    logger.info(f"Starting RealtimeProcessor for {BAR_INTERVAL_MINUTES}-minute bars...")

    # Create and run the real-time processor
    processor = RealtimeProcessor(
        stream_url=BINANCE_WS_URL,
        bar_interval_minutes=BAR_INTERVAL_MINUTES,
        model_lookback_bars=MODEL_LOOKBACK_BARS
    )
    await processor.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nReal-time processor manually stopped.")

