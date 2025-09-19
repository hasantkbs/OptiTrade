import logging
import pandas as pd
from typing import Dict, Any

from .base_model import BaseModel
from ..utils.data_fetcher import DataFetcher

# Loglama yapılandırması
logger = logging.getLogger(__name__)

class OnChainModel(BaseModel):
    """
    Zincir üstü verileri (örn: işlem sayısı) analiz ederek bir ticaret sinyali üretir.
    """
    def __init__(self, data_fetcher: DataFetcher, short_window: int = 14, long_window: int = 50):
        super().__init__(data_fetcher)
        self.short_window = short_window
        self.long_window = long_window

    def predict(self, symbol: str, interval: str = "1d", **kwargs) -> Dict[str, Any]:
        """
        Günlük işlem sayısının hareketli ortalamalarını analiz eder.
        """
        # Bu model BTC'ye özgüdür, bu yüzden sembolü kontrol edebiliriz.
        if 'BTC' not in symbol.upper():
            return {"score": 0.0, "details": "Bu model sadece BTC için geçerlidir."}

        logger.info(f"'{self.name}' modeli çalıştırılıyor...")
        
        try:
            # Zincir üstü veriyi çek (son 1 yıl yeterli olacaktır)
            onchain_data = self.data_fetcher.get_btc_transaction_data(timespan="1year")

            if not onchain_data or "values" not in onchain_data or len(onchain_data["values"]) < self.long_window:
                logger.warning(f"'{self.name}': Yeterli zincir üstü veri bulunamadı.")
                return {"score": 0.0, "details": "Yetersiz zincir üstü veri."}

            # Veriyi pandas Series'e dönüştür
            values = [item['y'] for item in onchain_data["values"]]
            tx_series = pd.Series(values)

            # Hareketli ortalamaları hesapla
            short_sma = tx_series.rolling(window=self.short_window).mean()
            long_sma = tx_series.rolling(window=self.long_window).mean()

            if short_sma.empty or long_sma.empty:
                 return {"score": 0.0, "details": "Hareketli ortalamalar hesaplanamadı."}

            # En son SMA değerlerini karşılaştır
            latest_short_sma = short_sma.iloc[-1]
            latest_long_sma = long_sma.iloc[-1]

            if latest_short_sma > latest_long_sma:
                score = 0.7
                details = f"Pozitif on-chain momentum: Kısa vadeli işlem ortalaması ({self.short_window} gün), uzun vadelinin ({self.long_window} gün) üzerinde."
            else:
                score = -0.7
                details = f"Negatif on-chain momentum: Kısa vadeli işlem ortalaması ({self.short_window} gün), uzun vadelinin ({self.long_window} gün) altında."
            
            logger.info(f"'{self.name}' modeli sonucu: Skor={score:.4f}")
            return {"score": score, "details": details}

        except Exception as e:
            logger.error(f"'{self.name}' skoru hesaplanırken hata oluştu: {e}", exc_info=True)
            return {"score": 0.0, "details": "Model çalışırken hata oluştu."}
