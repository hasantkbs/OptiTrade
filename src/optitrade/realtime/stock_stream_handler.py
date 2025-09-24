
import asyncio
import os
import logging
from alpha_vantage.timeseries import TimeSeries
from typing import Callable, Awaitable

from src.optitrade.realtime.stream_handler_base import StreamHandlerBase

logger = logging.getLogger(__name__)

class StockStreamHandler(StreamHandlerBase):
    """
    Connects to the Alpha Vantage API and polls for real-time stock data.
    """
    def __init__(self, on_message_callback: Callable[[dict], Awaitable[None]]):
        """
        Initializes the handler.

        Args:
            on_message_callback (Callable): Asynchronous function to be called for each incoming data message.
        """
        super().__init__(on_message_callback)
        # IMPORTANT: You need to set the ALPHA_VANTAGE_API_KEY environment variable.
        self.api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
        if not self.api_key:
            raise ValueError("ALPHA_VANTAGE_API_KEY environment variable not set.")
        self.ts = TimeSeries(key=self.api_key, output_format='pandas')
        self.is_running = False
        self.polling_interval = 15  # seconds

    async def start(self, stream_name: str):
        """
        Starts polling for stock data.

        Args:
            stream_name (str): The stock symbol to poll for (e.g., 'IBM').
        """
        self.is_running = True
        logger.info(f"Starting polling for {stream_name} every {self.polling_interval} seconds.")
        while self.is_running:
            try:
                data, meta_data = self.ts.get_intraday(symbol=stream_name, interval='1min', outputsize='compact')
                if not data.empty:
                    # Convert the latest data point to a dictionary and call the callback
                    latest_data = data.iloc[-1].to_dict()
                    await self.on_message_callback(latest_data)
            except Exception as e:
                logger.error(f"An error occurred while polling for stock data: {e}", exc_info=True)
            await asyncio.sleep(self.polling_interval)

    def stop(self):
        """
        Stops the polling loop.
        """
        self.is_running = False
        logger.info("Stopping stock data polling...")
