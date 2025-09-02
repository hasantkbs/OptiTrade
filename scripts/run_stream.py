

import asyncio
import logging
import sys
import os

# Proje kök dizinini Python yoluna ekle
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.optitrade.realtime.binance_stream_handler import BinanceStreamHandler

# --- Yapılandırma ---
# Binance Futures için anlık Mark Price (saniyede 1 güncelleme)
STREAM_NAME = "btcusdt@markPrice@1s"


async def handle_message(data: dict):
    """
    WebSocket'ten gelen her mesaj için çağrılacak callback fonksiyonu.
    Sadece 'markPriceUpdate' olaylarını işler.
    """
    event_type = data.get('e')
    if event_type == 'markPriceUpdate':
        symbol = data.get('s')
        mark_price = data.get('p')
        
        if symbol and mark_price:
            # Ekrana daha temiz bir çıktı için aynı satıra yazdır (carriage return \r kullanarak)
            print(f"---> SEMBOL: {symbol}, ANLIK FIYAT (MARK): {float(mark_price):.2f}", end="\r")


async def main():
    """
    Gerçek zamanlı veri akışını başlatır ve yönetir.
    """
    # Temel loglama yapılandırması
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        stream=sys.stdout
    )
    
    logger = logging.getLogger(__name__)
    logger.info(f"Binance Futures Gerçek Zamanlı Veri Akışı Başlatılıyor...")
    logger.info(f"Stream: {STREAM_NAME}")

    # Stream handler'ı başlat
    handler = BinanceStreamHandler(
        on_message_callback=handle_message
    )
    
    # Veri akışını başlat ve sonsuza kadar çalıştır
    # Kullanıcı CTRL+C ile çıkana kadar çalışmaya devam edecek
    await handler.start(stream_name=STREAM_NAME)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nVeri akışı kullanıcı tarafından durduruldu.")

