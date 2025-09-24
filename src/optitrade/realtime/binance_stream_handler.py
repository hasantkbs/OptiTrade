
import asyncio
import json
import logging
import websockets
from typing import Callable, Awaitable

from src.optitrade.realtime.stream_handler_base import StreamHandlerBase

logger = logging.getLogger(__name__)

class BinanceStreamHandler(StreamHandlerBase):
    """
    Connects to the Binance Futures WebSocket API and manages the live data stream.
    Features automatic ping/pong and reconnection.
    """
    def __init__(self, on_message_callback: Callable[[dict], Awaitable[None]]):
        """
        Initializes the handler.

        Args:
            on_message_callback (Callable): Asynchronous function to be called for each incoming data message.
        """
        super().__init__(on_message_callback)
        self.base_url = "wss://fstream.binance.com/ws"
        self.ws_connection = None
        self.is_running = False

    async def _listen_forever(self):
        """
        Continuously listens for messages from the WebSocket.
        """
        logger.info("Listening for messages...")
        while self.is_running:
            try:
                message = await self.ws_connection.recv()
                data = json.loads(message)
                
                # Pass the data directly to the callback function
                await self.on_message_callback(data)

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"WebSocket connection closed: {e}. Reconnecting...")
                break # Exit the loop to trigger reconnection
            except Exception as e:
                logger.error(f"An error occurred while processing a message: {e}", exc_info=True)

    async def start(self, stream_name: str):
        """
        Starts the WebSocket connection and subscribes to the specified stream.
        Automatically reconnects if the connection is lost.
        """
        self.is_running = True
        url = f"{self.base_url}/{stream_name.lower()}"
        
        while self.is_running:
            try:
                async with websockets.connect(url) as ws:
                    self.ws_connection = ws
                    logger.info(f"Successfully connected to '{url}'.")
                    await self._listen_forever()
            except Exception as e:
                logger.error(f"WebSocket connection error: {e}. Retrying in 5 seconds.")
                await asyncio.sleep(5)

    def stop(self):
        """
        Stops the WebSocket connection and the listening loop.
        """
        self.is_running = False
        logger.info("Stopping WebSocket stream...")
