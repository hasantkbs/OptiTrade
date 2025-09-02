
import pandas as pd
import numpy as np
import ta.volume
import ta.volatility
import logging
from typing import Dict, Any, Tuple

from .base_model import BaseModel
from ..utils.data_fetcher import DataFetcher
from .. import config

# Loglama yapılandırması
logger = logging.getLogger(__name__)

class VolumeSurgeModel(BaseModel):
    """
    Hacim anomalilerini ve fiyat etkisini analiz ederek bir skor üretir ve detaylı bilgi döndürür.
    """
    def __init__(self, data_fetcher: DataFetcher):
        super().__init__(data_fetcher)
        self.base_volume_ma_window = config.VOLUME_SURGE_MA_WINDOW
        self.deviation_scale = config.VOLUME_SURGE_DEVIATION_SCALE
        self.obv_influence = config.VOLUME_SURGE_OBV_INFLUENCE
        self.base_required_data_points = self.base_volume_ma_window + 5

    def predict(self, symbol: str, interval: str = "1d", **kwargs) -> Dict[str, Any]:
        logger.info(f"'{self.name}' modeli '{symbol}' için '{interval}' aralığında çalıştırılıyor...")
        
        # Interval'e göre pencere boyutlarını ölçeklendir
        scaling_factor = self._get_scaling_factor(interval)
        volume_ma_window = int(self.base_volume_ma_window * scaling_factor)

        # Ölçeklendirilmiş pencere boyutlarına göre gerekli veri noktasını hesapla
        required_data_points = volume_ma_window + 5

        period_map = {"15m": "60d", "4h": "730d", "1d": "5y"}
        fetch_period = period_map.get(interval, "5y")

        data = self.data_fetcher.get_market_data(symbol, period=fetch_period, interval=interval)

        if data.empty or len(data) < required_data_points:
            logger.warning(f"'{self.name}': Yeterli veri yok.")
            return {"score": 0.0, "details": "Yetersiz veri"}

        try:
            score, details = self._calculate_score(data, volume_ma_window)
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

    def _calculate_score(self, data: pd.DataFrame, volume_ma_window: int) -> Tuple[float, str]:
        data = data.copy()
        details = []
        
        required_columns = ['Close', 'Volume']
        if not all(col in data.columns for col in required_columns):
            return 0.0, "Gerekli sütunlar eksik."

        # --- Hacim Sapma Skoru ---
        volume_ma = data['Volume'].rolling(window=volume_ma_window).mean()
        last_volume = data['Volume'].iloc[-1]
        last_volume_ma = volume_ma.iloc[-1]
        
        volume_deviation = 0.0
        if last_volume_ma > 0:
            volume_deviation = (last_volume - last_volume_ma) / last_volume_ma
        
        volume_deviation_score = np.tanh(volume_deviation * self.deviation_scale)
        if volume_deviation > 0.2: details.append(f"Hacim Artışı ({volume_deviation:.2f})")
        elif volume_deviation < -0.2: details.append(f"Hacim Düşüşü ({volume_deviation:.2f})")

        # --- OBV (On-Balance Volume) Skoru ---
        obv = ta.volume.on_balance_volume(data['Close'], data['Volume'])
        obv_score = 0.0
        if len(obv) > 1:
            obv_change = np.sign(obv.iloc[-1] - obv.iloc[-2])
            obv_score = obv_change * self.obv_influence
            if obv_change > 0: details.append("OBV Yükseliş Trendi")
            elif obv_change < 0: details.append("OBV Düşüş Trendi")

        # --- Fiyat Değişim Skoru ---
        price_change_score = 0.0
        if len(data['Close']) > 1:
            price_change = (data['Close'].iloc[-1] - data['Close'].iloc[-2]) / data['Close'].iloc[-2]
            price_change_score = np.tanh(price_change * 10)

        # --- Nihai Skor ---
        final_score = (volume_deviation_score * 0.5) + (obv_score * 0.5)
        if np.sign(final_score) == np.sign(price_change_score):
            final_score = (final_score + price_change_score) / 2
        
        final_score = float(np.tanh(final_score))
        final_details = ", ".join(details) if details else "Nötr hacim sinyali."
        return final_score, final_details

# Örnek Kullanım
if __name__ == '__main__':
    logger.info("--- VolumeSurgeModel Test Başlatıldı ---")
    try:
        fetcher = DataFetcher()
        model = VolumeSurgeModel(data_fetcher=fetcher)
        prediction = model.predict(symbol="BTC-USD", interval="1d")
        
        print("--- Test Sonucu ---")
        print(f"Model Adı: {model.name}")
        print(f"Tahmin: {prediction}")
    except Exception as e:
        logger.error(f"Test sırasında bir hata oluştu: {e}", exc_info=True)
    logger.info("--- VolumeSurgeModel Test Tamamlandı ---")
