
import asyncio
import json
import logging
import websockets
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

class BinanceStreamHandler:
    """
    Binance Futures WebSocket API'sine bağlanır ve canlı veri akışını yönetir.
    Otomatik ping/pong ve yeniden bağlanma özelliklerine sahiptir.
    """
    def __init__(self, on_message_callback: Callable[[dict], Awaitable[None]]):
        """
        Handler'ı başlatır.

        Args:
            on_message_callback (Callable): Gelen her veri mesajı için çağrılacak asenkron fonksiyon.
        """
        self.base_url = "wss://fstream.binance.com/ws"
        self.on_message_callback = on_message_callback
        self.ws_connection = None
        self.is_running = False

    async def _listen_forever(self):
        """
        WebSocket üzerinden gelen mesajları sürekli dinler.
        """
        logger.info("Mesajlar dinleniyor...")
        while self.is_running:
            try:
                message = await self.ws_connection.recv()
                data = json.loads(message)
                
                # Gelen veriyi doğrudan callback fonksiyonuna ilet
                await self.on_message_callback(data)

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"WebSocket bağlantısı kapandı: {e}. Yeniden bağlanılıyor...")
                break # Döngüden çıkıp yeniden bağlanmayı tetikle
            except Exception as e:
                logger.error(f"Mesaj işlenirken bir hata oluştu: {e}", exc_info=True)

    async def start(self, stream_name: str):
        """
        WebSocket bağlantısını başlatır ve belirtilen akışa bağlanır.
        Bağlantı koparsa otomatik olarak yeniden bağlanır.
        """
        self.is_running = True
        url = f"{self.base_url}/{stream_name.lower()}"
        
        while self.is_running:
            try:
                async with websockets.connect(url) as ws:
                    self.ws_connection = ws
                    logger.info(f"'{url}' adresine başarıyla bağlanıldı.")
                    await self._listen_forever()
            except Exception as e:
                logger.error(f"WebSocket bağlantı hatası: {e}. 5 saniye içinde yeniden denenecek.")
                await asyncio.sleep(5)

    def stop(self):
        """
        WebSocket bağlantısını ve dinleme döngüsünü durdurur.
        """
        self.is_running = False
        logger.info("WebSocket stream durduruluyor...")
