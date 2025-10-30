
import logging
import pandas as pd
from typing import Dict, Any

from .base_model import BaseModel

logger = logging.getLogger(__name__)

class FibonacciModel(BaseModel):
    """
    Fibonacci düzeltme seviyelerini hesaplayarak bir ticaret sinyali üretir.
    """
    def __init__(self, **kwargs):
        super().__init__()

    def predict(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """
        Verilen fiyat verilerine dayanarak Fibonacci düzeltme seviyelerini hesaplar.
        """
        logger.info(f"Running '{self.name}' model...")

        try:
            # Gerekli veri miktarını kontrol et
            if data.empty or len(data) < 2:
                logger.warning(f"'{self.name}': Yetersiz veri.")
                return {"levels": {}, "details": "Yetersiz veri."}

            # Son 100 periyotluk veriyi kullan
            historical_data = data.tail(100)

            # En yüksek ve en düşük fiyatları bul
            high_price = historical_data['High'].max()
            low_price = historical_data['Low'].min()
            price_range = high_price - low_price

            if price_range == 0:
                return {"levels": {}, "details": "Fiyat aralığı sıfır."}

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

            return {"score": 0.0, "levels": levels, "details": details}

        except Exception as e:
            logger.error(f"'{self.name}' skoru hesaplanırken hata oluştu: {e}", exc_info=True)
            return {"levels": {}, "details": "Model çalışırken hata oluştu."}
