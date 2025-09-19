import logging
from typing import Dict, Any

from .base_model import BaseModel
from ..utils.data_fetcher import DataFetcher

# Loglama yapılandırması
logger = logging.getLogger(__name__)

class MacroEconomicModel(BaseModel):
    """
    Makroekonomik verileri (örn: faiz oranları) analiz ederek bir ticaret sinyali üretir.
    """
    def __init__(self, data_fetcher: DataFetcher):
        super().__init__(data_fetcher)

    def predict(self, symbol: str, interval: str = "1d", **kwargs) -> Dict[str, Any]:
        """
        En son faiz oranı değişikliklerini analiz eder ve bir skor üretir.
        """
        logger.info(f"'{self.name}' modeli çalıştırılıyor...")
        
        try:
            # Federal Fon Oranı verilerini çek
            fed_rate_data = self.data_fetcher.get_federal_fund_rate()

            if not fed_rate_data or "data" not in fed_rate_data or len(fed_rate_data["data"]) < 2:
                logger.warning(f"'{self.name}': Yeterli faiz oranı verisi bulunamadı.")
                return {"score": 0.0, "details": "Yetersiz makroekonomik veri."}

            # En son iki veri noktasını al
            latest_rate_entry = fed_rate_data["data"][0]
            previous_rate_entry = fed_rate_data["data"][1]

            latest_rate = float(latest_rate_entry['value'])
            previous_rate = float(previous_rate_entry['value'])

            # Değişimi analiz et
            if latest_rate < previous_rate:
                score = 0.8
                details = f"Faiz indirimi tespit edildi (Önceki: {previous_rate}%, Yeni: {latest_rate}%). Piyasa için potansiyel pozitif."
            elif latest_rate > previous_rate:
                score = -0.8
                details = f"Faiz artırımı tespit edildi (Önceki: {previous_rate}%, Yeni: {latest_rate}%). Piyasa için potansiyel negatif."
            else:
                score = 0.0
                details = f"Faiz oranlarında değişiklik yok (Mevcut: {latest_rate}%). Nötr etki."
            
            logger.info(f"'{self.name}' modeli sonucu: Skor={score:.4f}, Detay: {details}")
            return {"score": score, "details": details}

        except Exception as e:
            logger.error(f"'{self.name}' skoru hesaplanırken hata oluştu: {e}", exc_info=True)
            return {"score": 0.0, "details": "Model çalışırken hata oluştu."}
