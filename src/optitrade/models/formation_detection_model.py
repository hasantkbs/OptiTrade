import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
import logging
from typing import Dict, List, Tuple, Any

from .base_model import BaseModel
from ..utils.data_fetcher import DataFetcher
from .. import config

# Loglama yapılandırması
logger = logging.getLogger(__name__)

class FormationDetectionModel(BaseModel):
    """
    Fiyat verilerindeki grafik formasyonlarını tespit eder ve detaylı bilgi döndürür.
    """
    def __init__(self, data_fetcher: DataFetcher):
        super().__init__(data_fetcher)
        self.extrema_order = 10
        self.tolerance = 0.03
        self.required_data_points = 150

    def predict(self, symbol: str, **kwargs) -> Dict[str, Any]:
        logger.info(f"'{self.name}' modeli '{symbol}' için çalıştırılıyor...")
        period = f"{self.required_data_points + 20}d"
        data = self.data_fetcher.get_market_data(symbol, period=period, interval="1d")

        if data.empty or len(data) < self.required_data_points:
            logger.warning(f"'{self.name}': Yeterli veri yok.")
            return {"score": 0.0, "details": "Yetersiz veri"}

        try:
            prices = data['Close']
            # Formasyonları öncelik sırasına göre tespit et
            score, details = self._detect_head_and_shoulders(prices)
            if score == 0.0:
                score, details = self._detect_triangles(prices)
            if score == 0.0:
                score, details = self._detect_double_top_bottom(prices)
            
            logger.info(f"'{self.name}' modeli sonucu: Skor={score:.2f}, Detay: {details}")
            return {"score": score, "details": details}
        except Exception as e:
            logger.error(f"'{self.name}' skoru hesaplanırken hata oluştu: {e}", exc_info=True)
            return {"score": 0.0, "details": "Model çalışırken hata oluştu."}

    def _get_extrema(self, prices: pd.Series) -> Tuple[pd.Series, pd.Series]:
        highs = prices.iloc[argrelextrema(prices.values, np.greater_equal, order=self.extrema_order)[0]]
        lows = prices.iloc[argrelextrema(prices.values, np.less_equal, order=self.extrema_order)[0]]
        return highs, lows

    def _detect_triangles(self, prices: pd.Series) -> Tuple[float, str]:
        highs, lows = self._get_extrema(prices.tail(90))
        if len(lows) < 2 or len(highs) < 2:
            return 0.0, "Formasyon bulunamadı"

        lows_x = np.arange(len(lows))
        lows_slope, _ = np.polyfit(lows_x, lows.values, 1)
        highs_x = np.arange(len(highs))
        highs_slope, _ = np.polyfit(highs_x, highs.values, 1)
        current_price = prices.iloc[-1]

        if lows_slope > 0.05 and abs(highs_slope) < 0.05:
            resistance_level = highs.mean()
            if current_price > resistance_level:
                return 0.8, f"Yükselen Üçgen kırılımı ({resistance_level:.2f}) teyit edildi."

        if highs_slope < -0.05 and abs(lows_slope) < 0.05:
            support_level = lows.mean()
            if current_price < support_level:
                return -0.8, f"Alçalan Üçgen kırılımı ({support_level:.2f}) teyit edildi."

        return 0.0, "Formasyon bulunamadı"

    def _detect_head_and_shoulders(self, prices: pd.Series) -> Tuple[float, str]:
        highs, lows = self._get_extrema(prices)
        if len(highs) >= 3 and len(lows) >= 2:
            last_highs = highs.tail(3)
            shoulders_and_head_indices = last_highs.index
            relevant_lows = lows[(lows.index > shoulders_and_head_indices[0]) & (lows.index < shoulders_and_head_indices[2])]
            if len(relevant_lows) >= 2:
                left_shoulder, head, right_shoulder = last_highs.iloc[0], last_highs.iloc[1], last_highs.iloc[2]
                if (head > left_shoulder and head > right_shoulder and abs(left_shoulder - right_shoulder) / left_shoulder < 0.05):
                    neckline_break = min(relevant_lows.iloc[0], relevant_lows.iloc[1])
                    if prices.iloc[-1] < neckline_break:
                        return -0.9, f"Omuz-Baş-Omuz (OBO) formasyonu ({neckline_break:.2f} altında) teyit edildi."
        if len(lows) >= 3 and len(highs) >= 2:
            last_lows = lows.tail(3)
            shoulders_and_head_indices = last_lows.index
            relevant_highs = highs[(highs.index > shoulders_and_head_indices[0]) & (highs.index < shoulders_and_head_indices[2])]
            if len(relevant_highs) >= 2:
                left_shoulder, head, right_shoulder = last_lows.iloc[0], last_lows.iloc[1], last_lows.iloc[2]
                if (head < left_shoulder and head < right_shoulder and abs(left_shoulder - right_shoulder) / left_shoulder < 0.05):
                    neckline_break = max(relevant_highs.iloc[0], relevant_highs.iloc[1])
                    if prices.iloc[-1] > neckline_break:
                        return 0.9, f"Ters Omuz-Baş-Omuz (TOBO) formasyonu ({neckline_break:.2f} üstünde) teyit edildi."
        return 0.0, "Formasyon bulunamadı"

    def _detect_double_top_bottom(self, prices: pd.Series) -> Tuple[float, str]:
        highs, lows = self._get_extrema(prices)
        if len(highs) >= 2:
            last_two_highs = highs.tail(2)
            price1, price2 = last_two_highs.iloc[0], last_two_highs.iloc[1]
            if abs(price1 - price2) / price1 <= self.tolerance:
                trough = prices[last_two_highs.index[0]:last_two_highs.index[1]].min()
                if prices.iloc[-1] < trough:
                    return -0.75, f"İkili Tepe formasyonu ({trough:.2f} altında) teyit edildi."
        if len(lows) >= 2:
            last_two_lows = lows.tail(2)
            price1, price2 = last_two_lows.iloc[0], last_two_lows.iloc[1]
            if abs(price1 - price2) / price1 <= self.tolerance:
                peak = prices[last_two_lows.index[0]:last_two_lows.index[1]].max()
                if prices.iloc[-1] > peak:
                    return 0.75, f"İkili Dip formasyonu ({peak:.2f} üstünde) teyit edildi."
        return 0.0, "Formasyon bulunamadı"

# Örnek Kullanım
if __name__ == '__main__':
    logger.info("--- FormationDetectionModel Test Başlatıldı ---")
    try:
        fetcher = DataFetcher()
        model = FormationDetectionModel(data_fetcher=fetcher)
        prediction = model.predict(symbol="BTC-USD")
        print("--- Test Sonucu ---")
        print(f"Model Adı: {model.name}")
        print(f"Tahmin: {prediction}")
    except Exception as e:
        logger.error(f"Test sırasında bir hata oluştu: {e}", exc_info=True)
    logger.info("--- FormationDetectionModel Test Tamamlandı ---")