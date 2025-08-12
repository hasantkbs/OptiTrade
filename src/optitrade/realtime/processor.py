import asyncio
import logging
import pandas as pd

from src.optitrade.data.stream_manager import BinanceStreamManager
from src.optitrade.models.price_trend_model import PriceTrendModel

logger = logging.getLogger(__name__)

class RealtimeProcessor:
    """
    Processes real-time OHLCV bars and feeds them to the PriceTrendModel.
    """
    def __init__(self, stream_url: str, bar_interval_minutes: int, model_lookback_bars: int, historical_data: pd.DataFrame = None):
        self.model_lookback_bars = model_lookback_bars
        self.price_trend_model = PriceTrendModel() # Initialize the model
        
        if historical_data is not None and not historical_data.empty:
            self.historical_bars = historical_data.copy()
            logger.info(f"RealtimeProcessor initialized with {len(self.historical_bars)} historical bars.")
        else:
            self.historical_bars = pd.DataFrame() # To store bars for the model
        
        # Initialize the stream manager, passing our callback method
        self.stream_manager = BinanceStreamManager(
            stream_url=stream_url,
            bar_interval_minutes=bar_interval_minutes,
            on_bar_close_callback=self._on_bar_close
        )
        logger.info("RealtimeProcessor initialized.")

    async def _on_bar_close(self, new_bar_df: pd.DataFrame):
        """
        Callback function called by BarAggregator when a new bar is closed.
        """
        logger.info(f"Processor received new bar: {new_bar_df.index[0]} - C:{new_bar_df['Close'].iloc[0]:.2f}")
        
        # To prevent InvalidIndexError, we first remove any existing bar with the same timestamp.
        # This handles cases where a bar is closed by timeout and then again by a new trade.
        self.historical_bars = self.historical_bars.drop(new_bar_df.index, errors='ignore')
        
        # Append the new bar to our historical data
        self.historical_bars = pd.concat([self.historical_bars, new_bar_df])
        
        # Keep only the required number of lookback bars
        if len(self.historical_bars) > self.model_lookback_bars:
            self.historical_bars = self.historical_bars.iloc[-self.model_lookback_bars:]

        # Ensure the index is sorted (important for some TA calculations)
        self.historical_bars = self.historical_bars.sort_index()

        # Check if we have enough data to run the model
        if len(self.historical_bars) >= self.model_lookback_bars:
            logger.info(f"Running PriceTrendModel with {len(self.historical_bars)} bars...")
            # Pass the entire DataFrame to the model
            trend_score = self.price_trend_model.generate_score(self.historical_bars)
            logger.info(f"Real-time Price Trend Score: {trend_score:.4f}")
        else:
            logger.info(f"Not enough bars ({len(self.historical_bars)}/{self.model_lookback_bars}) to run the model yet.")

    async def start(self):
        """
        Starts the real-time data streaming and processing.
        """
        logger.info("Starting real-time data stream...")
        # Start streaming for a specific symbol (e.g., btcusdt@trade)
        await self.stream_manager.start_streaming(streams=["btcusdt@trade"])
