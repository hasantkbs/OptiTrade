import logging
import pandas as pd
import ta
from typing import Dict, Any

from .base_model import BaseModel
from ..utils.data_fetcher import DataFetcher

logger = logging.getLogger(__name__)

class MarketConditionClassifier(BaseModel):
    """
    ADX ve +/-DI göstergelerini kullanarak mevcut piyasa rejimini sınıflandırır.
    Bu model bir al/sat 'skoru' üretmez, bunun yerine bir 'rejim' tanımı döndürür.
    """
    def __init__(self, data_fetcher: DataFetcher, adx_window: int = 14, adx_threshold: int = 25):
        super().__init__(data_fetcher)
        self.adx_window = adx_window
        self.adx_threshold = adx_threshold
        # Modelin çalışması için gereken minimum veri noktası sayısı
        self.required_data_points = self.adx_window * 2

    def predict(self, symbol: str, interval: str = "1d", **kwargs) -> Dict[str, Any]:
        """
        Piyasa koşulunu analiz eder ve bir rejim sınıflandırması döndürür.
        """
        logger.info(f"'{self.name}' modeli '{symbol}' için çalıştırılıyor...")
        
        try:
            # Gerekli veriyi çek
            period_map = {"15m": "60d", "4h": "730d", "1d": "5y"}
            fetch_period = period_map.get(interval, "5y")
            data = self.data_fetcher.get_market_data(symbol, period=fetch_period, interval=interval)

            if data.empty or len(data) < self.required_data_points:
                logger.warning(f"'{self.name}': Yeterli veri yok.")
                return {"regime": "Unknown", "details": "Yetersiz veri"}

            # ADX ve +/-DI göstergelerini hesapla
            adx_indicator = ta.trend.ADXIndicator(
                high=data['High'],
                low=data['Low'],
                close=data['Close'],
                window=self.adx_window
            )
            data['adx'] = adx_indicator.adx()
            data['di_pos'] = adx_indicator.adx_pos()
            data['di_neg'] = adx_indicator.adx_neg()

            # En son değerleri al
            latest_adx = data['adx'].iloc[-1]
            latest_di_pos = data['di_pos'].iloc[-1]
            latest_di_neg = data['di_neg'].iloc[-1]

            # Rejimi sınıflandır
            regime = ""
            if latest_adx > self.adx_threshold:
                # Güçlü Trend
                if latest_di_pos > latest_di_neg:
                    regime = "Strong Bull Trend"
                    details = f"Güçlü yükseliş trendi tespit edildi (ADX: {latest_adx:.2f})"
                else:
                    regime = "Strong Bear Trend"
                    details = f"Güçlü düşüş trendi tespit edildi (ADX: {latest_adx:.2f})"
            else:
                # Zayıf Trend veya Yatay Piyasa
                if latest_di_pos > latest_di_neg:
                    regime = "Weak Bull Trend"
                    details = f"Zayıf yükseliş trendi veya yatay piyasa (ADX: {latest_adx:.2f})"
                else:
                    regime = "Weak Bear Trend"
                    details = f"Zayıf düşüş trendi veya yatay piyasa (ADX: {latest_adx:.2f})"

            logger.info(f"'{self.name}' sonucu: Rejim={regime}, Detay: {details}")
            
            # Bu modelin çıktısı, standart bir skor yerine rejim bilgisidir
            return {
                "score": 0.0, # Bu model skor üretmez
                "details": details,
                "regime": regime
            }

        except Exception as e:
            logger.error(f"'{self.name}' çalışırken hata oluştu: {e}", exc_info=True)
            return {"regime": "Unknown", "details": "Model çalışırken hata oluştu."}
