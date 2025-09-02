import pandas as pd
import numpy as np
import ta.momentum
from scipy.signal import argrelextrema
import logging
from typing import Dict, List, Any, Tuple

from .base_model import BaseModel
from ..utils.data_fetcher import DataFetcher
from .. import config

# Loglama yapılandırması
logger = logging.getLogger(__name__)

class DivergenceDetectionModel(BaseModel):
    """
    Fiyat ve RSI göstergesi arasındaki uyumsuzlukları bularak bir skor üretir ve detaylı bilgi döndürür.
    """
    def __init__(self, data_fetcher: DataFetcher):
        super().__init__(data_fetcher)
        self.base_rsi_window = config.DIVERGENCE_INDICATOR_WINDOW
        self.base_extrema_order = config.DIVERGENCE_EXTREMA_ORDER
        self.base_lookback_period = config.DIVERGENCE_LOOKBACK_PERIOD
        self.base_required_data_points = self.base_lookback_period + 5

    def predict(self, symbol: str, interval: str = "1d", **kwargs) -> Dict[str, Any]:
        logger.info(f"'{self.name}' modeli '{symbol}' için '{interval}' aralığında çalıştırılıyor...")
        
        # Interval'e göre pencere boyutlarını ölçeklendir
        scaling_factor = self._get_scaling_factor(interval)
        rsi_window = int(self.base_rsi_window * scaling_factor)
        extrema_order = int(self.base_extrema_order * scaling_factor)
        lookback_period = int(self.base_lookback_period * scaling_factor)

        # Ölçeklendirilmiş pencere boyutlarına göre gerekli veri noktasını hesapla
        required_data_points = lookback_period + 5

        period_map = {"15m": "60d", "4h": "730d", "1d": "5y"}
        fetch_period = period_map.get(interval, "5y")

        data = self.data_fetcher.get_market_data(symbol, period=fetch_period, interval=interval)

        if data.empty or len(data) < required_data_points:
            logger.warning(f"'{self.name}': Yeterli veri yok.")
            return {"score": 0.0, "details": "Yetersiz veri"}

        try:
            score, details = self._detect_rsi_divergence(data['Close'], rsi_window, extrema_order, lookback_period)
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

    def _find_extrema(self, series: pd.Series, is_max: bool, order: int) -> pd.Series:
        comparator = np.greater if is_max else np.less
        indices = argrelextrema(series.values, comparator, order=order)[0]
        return series.iloc[indices]

    def _detect_rsi_divergence(self, prices: pd.Series, rsi_window: int, extrema_order: int, lookback_period: int) -> Tuple[float, str]:
        if len(prices) < lookback_period:
            return 0.0, "Yetersiz veri."

        prices_slice = prices.iloc[-lookback_period:]
        rsi = ta.momentum.rsi(prices, window=rsi_window).iloc[-lookback_period:]

        if rsi.isnull().all():
            return 0.0, "RSI verisi hesaplanamadı."

        price_highs = self._find_extrema(prices_slice, is_max=True, order=extrema_order)
        price_lows = self._find_extrema(prices_slice, is_max=False, order=extrema_order)
        rsi_highs = self._find_extrema(rsi, is_max=True, order=extrema_order)
        rsi_lows = self._find_extrema(rsi, is_max=False, order=extrema_order)

        score = 0.0
        details = "Uyumsuzluk tespit edilmedi."

        # Ayı Uyumsuzluğu (Bearish Divergence): Fiyat -> Yüksek Tepe, RSI -> Düşük Tepe
        if len(price_highs) >= 2 and len(rsi_highs) >= 2:
            if price_highs.iloc[-1] > price_highs.iloc[-2]:
                corresponding_rsi_high1 = rsi.get(price_highs.index[-2])
                corresponding_rsi_high2 = rsi.get(price_highs.index[-1])
                if corresponding_rsi_high1 is not None and corresponding_rsi_high2 is not None:
                    if corresponding_rsi_high2 < corresponding_rsi_high1:
                        score = -0.75
                        details = "Ayı Uyumsuzluğu (Fiyat Yüksek Tepe, RSI Düşük Tepe)"

        # Boğa Uyumsuzluğu (Bullish Divergence): Fiyat -> Düşük Dip, RSI -> Yüksek Dip
        if score == 0.0 and len(price_lows) >= 2 and len(rsi_lows) >= 2:
            if price_lows.iloc[-1] < price_lows.iloc[-2]:
                corresponding_rsi_low1 = rsi.get(price_lows.index[-2])
                corresponding_rsi_low2 = rsi.get(price_lows.index[-1])
                if corresponding_rsi_low1 is not None and corresponding_rsi_low2 is not None:
                    if corresponding_rsi_low2 > corresponding_rsi_low1:
                        score = 0.75
                        details = "Boğa Uyumsuzluğu (Fiyat Düşük Dip, RSI Yüksek Dip)"

        return score, details

# Örnek Kullanım
if __name__ == '__main__':
    logger.info("--- DivergenceDetectionModel Test Başlatıldı ---")
    try:
        fetcher = DataFetcher()
        model = DivergenceDetectionModel(data_fetcher=fetcher)
        prediction = model.predict(symbol="BTC-USD", interval="1d")
        
        print("--- Test Sonucu ---")
        print(f"Model Adı: {model.name}")
        print(f"Tahmin: {prediction}")
    except Exception as e:
        logger.error(f"Test sırasında bir hata oluştu: {e}", exc_info=True)
    logger.info("--- DivergenceDetectionModel Test Tamamlandı ---")