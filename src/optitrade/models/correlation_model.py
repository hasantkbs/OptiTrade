import logging
import pandas as pd
from typing import Dict, Any, List

from .base_model import BaseModel
from ..utils.data_fetcher import DataFetcher

logger = logging.getLogger(__name__)

class CorrelationModel(BaseModel):
    """
    Bir varlığın diğer büyük piyasalarla olan korelasyonunu analiz eder.
    Bu model bilgilendirici bir metin üretir, doğrudan bir skor değil.
    """
    def __init__(self, data_fetcher: DataFetcher, window: int = 30, assets: List[str] = ['SPY', 'GLD']):
        super().__init__(data_fetcher)
        self.correlation_window = window
        self.correlation_assets = assets
        self.required_data_points = self.correlation_window + 10

    def predict(self, symbol: str, interval: str = "1d", **kwargs) -> Dict[str, Any]:
        """
        Varlığın belirtilen diğer varlıklarla olan korelasyonunu hesaplar.
        """
        # Bu model sadece günlük verilerle anlamlıdır
        if interval != '1d':
            return {"score": 0.0, "details": "Korelasyon analizi sadece günlük (1d) periyotta çalışır."}

        logger.info(f"'{self.name}' modeli '{symbol}' için çalıştırılıyor...")
        
        try:
            # Ana varlık ve korelasyon varlıklarının verilerini çek
            all_symbols = [symbol] + self.correlation_assets
            market_data = {}
            for s in all_symbols:
                # Veri periyodunu gerekli veri noktasına göre ayarla
                period = f"{self.required_data_points * 2}d" # Biraz daha fazla veri çekelim
                data = self.data_fetcher.get_market_data(s, period=period, interval=interval)
                if data.empty or len(data) < self.required_data_points:
                    logger.warning(f"'{self.name}': '{s}' için yeterli veri yok.")
                    return {"score": 0.0, "details": f'{s} için yeterli veri bulunamadı.'}
                market_data[s] = data['Close']

            # Tüm kapanış fiyatlarını tek bir DataFrame'de birleştir
            combined_df = pd.DataFrame(market_data).ffill().dropna()

            # Günlük getirileri hesapla
            returns = combined_df.pct_change()

            # Korelasyonları hesapla ve detayları oluştur
            details = []
            for asset in self.correlation_assets:
                # Rolling correlation hesapla
                rolling_corr = returns[symbol].rolling(window=self.correlation_window).corr(returns[asset])
                latest_corr = rolling_corr.iloc[-1]
                details.append(f"{symbol} vs {asset}: {latest_corr:.2f}")
            
            final_details = f"Son {self.correlation_window} günlük korelasyonlar: " + ", ".join(details)
            logger.info(f"'{self.name}' sonucu: {final_details}")
            
            return {
                "score": 0.0, # Bu model doğrudan skor üretmez
                "details": final_details
            }

        except Exception as e:
            logger.error(f"'{self.name}' çalışırken hata oluştu: {e}", exc_info=True)
            return {"score": 0.0, "details": "Model çalışırken hata oluştu."}
