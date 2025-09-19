
import pandas as pd
import numpy as np
import ta
import logging
from typing import Dict, Any, Tuple

from .base_model import BaseModel
from ..utils.data_fetcher import DataFetcher
from .. import config

# Loglama yapılandırması
logger = logging.getLogger(__name__)

class PriceTrendModel(BaseModel):
    """
    Teknik analiz göstergelerini kullanarak bir fiyat trendi skoru üretir ve detaylı bilgi döndürür.
    """
    def __init__(self, data_fetcher: DataFetcher):
        super().__init__(data_fetcher)

    def predict(self, symbol: str, interval: str = "1d", **kwargs) -> Dict[str, Any]:
        logger.info(f"'{self.name}' modeli '{symbol}' için '{interval}' aralığında çalıştırılıyor...")
        
        # Parametreleri kwargs'tan al, yoksa config'den varsayılanları kullan
        rsi_window = kwargs.get('rsi_window', config.PRICE_TREND_RSI_WINDOW)
        macd_fast = kwargs.get('macd_fast', config.PRICE_TREND_MACD_FAST_WINDOW)
        macd_slow = kwargs.get('macd_slow', config.PRICE_TREND_MACD_SLOW_WINDOW)
        macd_sign = kwargs.get('macd_sign', config.PRICE_TREND_MACD_SIGNAL_WINDOW)
        sma_short = kwargs.get('sma_short', config.PRICE_TREND_SMA_SHORT_WINDOW)
        sma_long = kwargs.get('sma_long', config.PRICE_TREND_SMA_LONG_WINDOW)
        bollinger_window = kwargs.get('bollinger_window', config.PRICE_TREND_BOLLINGER_WINDOW)
        bollinger_std = kwargs.get('bollinger_std', config.PRICE_TREND_BOLLINGER_STD)
        adx_window = kwargs.get('adx_window', config.PRICE_TREND_ADX_WINDOW)

        # Interval'e göre pencere boyutlarını ölçeklendir
        scaling_factor = self._get_scaling_factor(interval)
        rsi_window = int(rsi_window * scaling_factor)
        macd_fast = int(macd_fast * scaling_factor)
        macd_slow = int(macd_slow * scaling_factor)
        macd_sign = int(macd_sign * scaling_factor)
        sma_short = int(sma_short * scaling_factor)
        sma_long = int(sma_long * scaling_factor)
        bollinger_window = int(bollinger_window * scaling_factor)
        adx_window = int(adx_window * scaling_factor)

        # Ölçeklendirilmiş pencere boyutlarına göre gerekli veri noktasını hesapla
        required_data_points = max(rsi_window, macd_slow, sma_long, bollinger_window, adx_window) + 5

        # Interval'e göre veri çekme periyodunu ayarla
        period_map = {"15m": "60d", "4h": "730d", "1d": "5y"}
        fetch_period = period_map.get(interval, "5y")

        data = self.data_fetcher.get_market_data(symbol, period=fetch_period, interval=interval)

        if data.empty or len(data) < required_data_points:
            logger.warning(f"'{self.name}': Yeterli veri yok ({len(data)}/{required_data_points}). Nötr skor (0.0) döndürülüyor.")
            return {"score": 0.0, "details": "Yetersiz veri"}

        try:
            score, details = self._calculate_score(data, rsi_window, macd_fast, macd_slow, macd_sign, sma_short, sma_long, bollinger_window, bollinger_std, adx_window)
            logger.info(f"'{self.name}' modeli sonucu: Skor={score:.4f}, Detay: {details}")
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

    def _calculate_score(self, data: pd.DataFrame, rsi_window: int, macd_fast: int, macd_slow: int, macd_sign: int, sma_short: int, sma_long: int, bollinger_window: int, bollinger_std: float, adx_window: int) -> Tuple[float, str]:
        data = data.copy()
        details = []
        score = 0.0

        # Göstergeleri hesapla (ölçeklendirilmiş pencerelerle)
        rsi = ta.momentum.rsi(data['Close'], window=rsi_window)
        macd_diff = ta.trend.macd_diff(data['Close'], window_fast=macd_fast, window_slow=macd_slow, window_sign=macd_sign)
        sma_short_val = ta.trend.sma_indicator(data['Close'], window=sma_short)
        sma_long_val = ta.trend.sma_indicator(data['Close'], window=sma_long)
        adx = ta.trend.adx(data['High'], data['Low'], data['Close'], window=adx_window)
        adx_pos = ta.trend.adx_pos(data['High'], data['Low'], data['Close'], window=adx_window)
        adx_neg = ta.trend.adx_neg(data['High'], data['Low'], data['Close'], window=adx_window)

        # --- Skorlama Mantığı ve Detaylar ---
        last_rsi = rsi.iloc[-1]
        if not pd.isna(last_rsi):
            if last_rsi > 70: 
                score -= (last_rsi - 70) / 30 * 0.5
                details.append(f"RSI Aşırı Alım ({last_rsi:.2f})")
            elif last_rsi < 30: 
                score += (30 - last_rsi) / 30 * 0.5
                details.append(f"RSI Aşırı Satım ({last_rsi:.2f})")

        last_macd_diff = macd_diff.iloc[-1]
        if not pd.isna(last_macd_diff):
            score += (last_macd_diff / data['Close'].iloc[-1]) * 5
            if last_macd_diff > 0: details.append("MACD Pozitif Momentum")
            else: details.append("MACD Negatif Momentum")

        last_sma_short = sma_short_val.iloc[-1]
        last_sma_long = sma_long_val.iloc[-1]
        if not pd.isna(last_sma_short) and not pd.isna(last_sma_long):
            if last_sma_short > last_sma_long: 
                score += 0.15
                details.append("SMA Altın Kesişim")
            else: 
                score -= 0.15
                details.append("SMA Ölüm Kesişimi")

        last_adx = adx.iloc[-1]
        if not pd.isna(last_adx) and last_adx > 25:
            last_adx_pos = adx_pos.iloc[-1]
            last_adx_neg = adx_neg.iloc[-1]
            if not pd.isna(last_adx_pos) and not pd.isna(last_adx_neg):
                if last_adx_pos > last_adx_neg: 
                    score += 0.15
                    details.append(f"ADX Güçlü Yükseliş Trendi ({last_adx:.2f})")
                else: 
                    score -= 0.15
                    details.append(f"ADX Güçlü Düşüş Trendi ({last_adx:.2f})")
        
        final_score = float(np.tanh(score))
        final_details = ", ".join(details) if details else "Nötr trend sinyali."
        return final_score, final_details

# Örnek Kullanım
if __name__ == '__main__':
    logger.info("--- PriceTrendModel Test Başlatıldı ---")
    try:
        fetcher = DataFetcher()
        model = PriceTrendModel(data_fetcher=fetcher)
        prediction = model.predict(symbol="BTC-USD", interval="1d")
        
        print("--- Test Sonucu ---")
        print(f"Model Adı: {model.name}")
        print(f"Tahmin: {prediction}")
    except Exception as e:
        logger.error(f"Test sırasında bir hata oluştu: {e}", exc_info=True)
    logger.info("--- PriceTrendModel Test Tamamlandı ---")
