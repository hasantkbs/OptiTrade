
import asyncio
import json
import logging
import websockets
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

class BybitStreamHandler:
    """
    ByBit V5 WebSocket API'sine bağlanır, halka açık kanallara abone olur ve gelen verileri işler.
    """
    def __init__(self, stream_url: str, on_message_callback: Callable[[dict], Awaitable[None]]):
        """
        Handler'ı başlatır.

        Args:
            stream_url (str): Bağlanılacak WebSocket URL'si.
            on_message_callback (Callable): Gelen her mesaj için çağrılacak asenkron fonksiyon.
        """
        self.stream_url = stream_url
        self.on_message_callback = on_message_callback
        self.ws_connection = None
        self.is_running = False

    async def _subscribe(self, topics: list[str]):
        """
        Belirtilen konulara (topics) abone olmak için bir mesaj gönderir.
        """
        if not self.ws_connection:
            logger.error("WebSocket bağlantısı mevcut değil.")
            return

        subscription_message = {
            "op": "subscribe",
            "args": topics
        }
        await self.ws_connection.send(json.dumps(subscription_message))
        logger.info(f"Abonelik isteği gönderildi: {topics}")

    async def _listen_forever(self):
        """
        WebSocket üzerinden gelen mesajları sürekli dinler.
        """
        logger.info("Mesajlar dinleniyor...")
        while self.is_running:
            try:
                message = await self.ws_connection.recv()
                data = json.loads(message)
                
                # Ping/pong ve abonelik yanıtlarını işle
                if "op" in data and data["op"] == "subscribe":
                    if data.get("success", False):
                        logger.info(f"Başarıyla abone olundu: {data['ret_msg']}")
                    else:
                        logger.error(f"Abonelik başarısız: {data.get('ret_msg', 'Bilinmeyen hata')}")
                    continue

                # Gelen ticker verisini işle
                if "topic" in data and "tickers" in data["topic"]:
                    await self.on_message_callback(data['data'])

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"WebSocket bağlantısı kapandı: {e}. Yeniden bağlanmaya çalışılıyor...")
                break # Döngüden çıkıp yeniden bağlanmayı tetikle
            except Exception as e:
                logger.error(f"Mesaj işlenirken bir hata oluştu: {e}", exc_info=True)

    async def start(self, topics: list[str]):
        """
        WebSocket bağlantısını başlatır ve belirtilen konulara abone olur.
        Bağlantı koparsa otomatik olarak yeniden bağlanır.
        """
        self.is_running = True
        while self.is_running:
            try:
                async with websockets.connect(self.stream_url) as ws:
                    self.ws_connection = ws
                    logger.info(f"'{self.stream_url}' adresine başarıyla bağlanıldı.")
                    await self._subscribe(topics)
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
