
import asyncio
import logging
import sys
import os
import argparse

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.optitrade.realtime.binance_stream_handler import BinanceStreamHandler
from src.optitrade.realtime.stock_stream_handler import StockStreamHandler
from src.optitrade.realtime.processor import RealtimeProcessor

async def main():
    """
    Starts and manages the real-time data stream and analysis.
    """
    parser = argparse.ArgumentParser(description='Run real-time analysis for stocks or crypto.')
    parser.add_argument('--source', type=str, choices=['crypto', 'stock'], required=True, help='The data source to use ('crypto' or 'stock').')
    parser.add_argument('--symbol', type=str, required=True, help='The symbol to analyze (e.g., 'btcusdt@markPrice@1s' for crypto, 'IBM' for stock).')
    args = parser.parse_args()

    # Basic logging configuration
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        stream=sys.stdout
    )
    
    logger = logging.getLogger(__name__)
    logger.info(f"Starting real-time analysis for {args.source} using symbol {args.symbol}...")

    # Choose the stream handler based on the source
    if args.source == 'crypto':
        stream_handler = BinanceStreamHandler(on_message_callback=None) # The processor will set the callback
    elif args.source == 'stock':
        stream_handler = StockStreamHandler(on_message_callback=None) # The processor will set the callback
    else:
        logger.error(f"Invalid source: {args.source}")
        return

    # Initialize the real-time processor
    processor = RealtimeProcessor(
        stream_handler=stream_handler,
        model_lookback_bars=200 # This should be configured based on the models' requirements
    )

    # Start the real-time processing
    await processor.start(stream_name=args.symbol)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nReal-time analysis stopped by user.")
