
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
import logging
from typing import Dict, List, Any, Tuple

from .base_model import BaseModel
from ..utils.data_fetcher import DataFetcher
from .. import config

# Loglama yapılandırması
logger = logging.getLogger(__name__)

class SupportResistanceModel(BaseModel):
    """
    Fiyat verilerindeki destek ve direnç seviyelerini analiz ederek bir skor üretir ve detaylı bilgi döndürür.
    """
    def __init__(self, data_fetcher: DataFetcher):
        super().__init__(data_fetcher)
        self.base_order = config.SUPPORT_RESISTANCE_FRACTAL_WINDOW
        self.tolerance = 0.01 # %1
        self.base_required_data_points = self.base_order * 2 + 5

    def predict(self, symbol: str, interval: str = "1d", **kwargs) -> Dict[str, Any]:
        logger.info(f"'{self.name}' modeli '{symbol}' için '{interval}' aralığında çalıştırılıyor...")
        
        # Interval'e göre pencere boyutlarını ölçeklendir
        scaling_factor = self._get_scaling_factor(interval)
        order = int(self.base_order * scaling_factor)

        # Ölçeklendirilmiş pencere boyutlarına göre gerekli veri noktasını hesapla
        required_data_points = order * 2 + 5

        period_map = {"15m": "60d", "4h": "730d", "1d": "5y"}
        fetch_period = period_map.get(interval, "5y")

        data = self.data_fetcher.get_market_data(symbol, period=fetch_period, interval=interval)

        if data.empty or len(data) < required_data_points:
            logger.warning(f"'{self.name}': Yeterli veri yok.")
            return {"score": 0.0, "details": "Yetersiz veri"}

        try:
            score, details = self._calculate_score(data['Close'], order)
            logger.info(f"'{self.name}' modeli sonucu: Skor={score:.4f}, Detay: {details}")
            return {"score": score, "details": details}
        except Exception as e:
            logger.error(f"'{self.name}' skoru hesaplanırken hata oluştu: {e}", exc_info=True)
            return {"score": 0.0, "details": "Model çalışırken hata oluştu."}

    def _get_scaling_factor(self, interval: str) -> float:
        """
        Farklı zaman aralıkları için ölçeklendirme faktörünü döndürür.
        Varsayım: Temel aralık 1d (günlük) veridir.
        """
        if interval == "1d": return 1.0
        if interval == "4h": return 6.0  # 1 gün = 6 * 4 saat
        if interval == "15m": return 96.0 # 1 gün = 96 * 15 dakika
        return 1.0 # Bilinmeyen aralıklar için varsayılan

    def _find_levels(self, price_series: pd.Series, order: int) -> Tuple[List[float], List[float]]:
        local_min_indices = argrelextrema(price_series.values, np.less_equal, order=order)[0]
        local_max_indices = argrelextrema(price_series.values, np.greater_equal, order=order)[0]
        
        supports = price_series.iloc[local_min_indices].tolist()
        resistances = price_series.iloc[local_max_indices].tolist()
        return supports, resistances

    def _calculate_score(self, price_series: pd.Series, order: int) -> Tuple[float, str]:
        current_price = price_series.iloc[-1]
        supports, resistances = self._find_levels(price_series, order)

        if not supports and not resistances:
            return 0.0, "Destek/Direnç seviyesi bulunamadı."

        closest_support = min(supports, key=lambda x: abs(x - current_price)) if supports else None
        closest_resistance = min(resistances, key=lambda x: abs(x - current_price)) if resistances else None

        support_score = 0.0
        resistance_score = 0.0
        details = []

        if closest_support:
            distance_to_support = abs(current_price - closest_support) / current_price
            if distance_to_support < self.tolerance:
                support_score = (1 - (distance_to_support / self.tolerance)) * 0.9
                details.append(f"Destek seviyesine yakın ({closest_support:.2f})")

        if closest_resistance:
            distance_to_resistance = abs(current_price - closest_resistance) / current_price
            if distance_to_resistance < self.tolerance:
                resistance_score = -(1 - (distance_to_resistance / self.tolerance)) * 0.9
                details.append(f"Direnç seviyesine yakın ({closest_resistance:.2f})")

        final_score = support_score + resistance_score
        final_details = ", ".join(details) if details else "Nötr destek/direnç sinyali."
        
        return final_score, final_details

# Örnek Kullanım
if __name__ == '__main__':
    logger.info("--- SupportResistanceModel Test Başlatıldı ---")
    try:
        fetcher = DataFetcher()
        model = SupportResistanceModel(data_fetcher=fetcher)
        prediction = model.predict(symbol="BTC-USD", interval="1d")
        
        print("--- Test Sonucu ---")
        print(f"Model Adı: {model.name}")
        print(f"Tahmin: {prediction}")
    except Exception as e:
        logger.error(f"Test sırasında bir hata oluştu: {e}", exc_info=True)
    logger.info("--- SupportResistanceModel Test Tamamlandı ---")
