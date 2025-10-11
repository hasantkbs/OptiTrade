
import logging
import pandas as pd
from typing import Dict, Any

from .base_model import BaseModel
from ..utils.data_fetcher import DataFetcher

logger = logging.getLogger(__name__)

class FibonacciModel(BaseModel):
    """
    Fibonacci düzeltme seviyelerini hesaplayarak bir ticaret sinyali üretir.
    """
    def __init__(self, data_fetcher: DataFetcher):
        super().__init__(data_fetcher)

    def predict(self, symbol: str, interval: str = "1d", **kwargs) -> Dict[str, Any]:
        """
        Tarihsel fiyat verilerine dayanarak Fibonacci düzeltme seviyelerini hesaplar.
        """
        logger.info(f"'{self.name}' modeli çalıştırılıyor...")

        try:
            # Tarihsel verileri al
            historical_data = self.data_fetcher.get_historical_data(symbol, interval, limit=100)
            if historical_data.empty:
                logger.warning(f"'{self.name}': '{symbol}' için tarihsel veri bulunamadı.")
                return {"levels": {}, "details": "Tarihsel veri yok."}

            # En yüksek ve en düşük fiyatları bul
            high_price = historical_data['High'].max()
            low_price = historical_data['Low'].min()
            price_range = high_price - low_price

            # Fibonacci Seviyeleri
            levels = {
                "level_0": high_price,
                "level_23.6": high_price - (price_range * 0.236),
                "level_38.2": high_price - (price_range * 0.382),
                "level_50.0": high_price - (price_range * 0.5),
                "level_61.8": high_price - (price_range * 0.618),
                "level_100": low_price,
            }

            details = f"Fibonacci seviyeleri {low_price:.2f} (düşük) ve {high_price:.2f} (yüksek) aralığına göre hesaplandı."
            logger.info(f"'{self.name}' modeli sonucu: {details}")

            return {"levels": levels, "details": details}

        except Exception as e:
            logger.error(f"'{self.name}' skoru hesaplanırken hata oluştu: {e}", exc_info=True)
            return {"levels": {}, "details": "Model çalışırken hata oluştu."}
