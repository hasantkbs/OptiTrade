
from abc import ABC, abstractmethod
from typing import Callable, Awaitable

class StreamHandlerBase(ABC):
    """
    Abstract base class for real-time stream handlers.
    Defines the common interface for all stream handlers.
    """
    def __init__(self, on_message_callback: Callable[[dict], Awaitable[None]]):
        """
        Initializes the stream handler.

        Args:
            on_message_callback (Callable): Asynchronous function to be called for each incoming data message.
        """
        self.on_message_callback = on_message_callback

    @abstractmethod
    async def start(self, stream_name: str):
        """
        Starts the WebSocket connection and subscribes to the specified stream.
        """
        pass

    @abstractmethod
    def stop(self):
        """
        Stops the WebSocket connection and the listening loop.
        """
        pass
