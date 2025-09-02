import pandas as pd
import xgboost as xgb
import logging
import os
from typing import Dict, Any

from .base_model import BaseModel
from ..utils.data_fetcher import DataFetcher
from .model_utils import create_features, _get_scaling_factor # _get_scaling_factor'ı da import et

# Loglama yapılandırması
logger = logging.getLogger(__name__)

class MachineLearningModel(BaseModel):
    """
    Önceden eğitilmiş bir XGBoost modelini kullanarak fiyat yönü tahmini yapar ve detaylı bilgi döndürür.
    """
    def __init__(self, data_fetcher: DataFetcher):
        super().__init__(data_fetcher)
        self.model_path_template = "src/optitrade/models/trained_models/xgb_price_predictor_{}.json" # Model yolu şablonu
        self.model = None # Model başlangıçta yüklenmeyecek
        self.features = [
            'feature_price_change_1d', 'feature_price_change_3d', 'feature_price_change_7d',
            'feature_volatility_7d', 'feature_volatility_30d', 'feature_rsi_14d',
            'feature_macd', 'feature_macd_signal', 'feature_macd_diff',
            'feature_sma_50', 'feature_sma_200', 'feature_price_vs_sma50'
        ]
        self.base_required_data_points = 200 + 5

    def _load_model(self, interval: str) -> xgb.XGBClassifier:
        model_path = self.model_path_template.format(interval) # Interval'e göre model yolunu oluştur
        if not os.path.exists(model_path):
            logger.error(f"Eğitilmiş model dosyası bulunamadı: {model_path}")
            logger.error("Lütfen önce `scripts/train_model.py` betiğini bu aralık için çalıştırın.")
            return None
        
        logger.info(f"Eğitilmiş model '{model_path}' dosyasından yükleniyor...")
        model = xgb.XGBClassifier()
        model.load_model(model_path)
        logger.info("Model başarıyla yüklendi.")
        return model

    def predict(self, symbol: str, interval: str = "1d", **kwargs) -> Dict[str, Any]:
        # Modeli predict çağrısında yükle (interval'e göre doğru modeli yüklemek için)
        self.model = self._load_model(interval)

        if not self.model:
            logger.warning(f"'{self.name}': Model yüklenemediği için tahmin atlanıyor.")
            return {"score": 0.0, "details": "Model yüklenemedi."}

        logger.info(f"'{self.name}' modeli '{symbol}' için '{interval}' aralığında çalıştırılıyor...")
        
        # Gerekli veri noktasını interval'e göre ölçeklendir
        scaling_factor = _get_scaling_factor(interval)
        required_data_points = int(self.base_required_data_points * scaling_factor)

        period_map = {"15m": "60d", "4h": "730d", "1d": "5y"}
        fetch_period = period_map.get(interval, "5y")

        data = self.data_fetcher.get_market_data(symbol, period=fetch_period, interval=interval)

        if data.empty or len(data) < required_data_points:
            logger.warning(f"'{self.name}': Tahmin için yeterli veri yok.")
            return {"score": 0.0, "details": "Yetersiz veri"}

        # Özellikleri hesapla (interval parametresini ilet)
        data_with_features = create_features(data, interval=interval)
        latest_features = data_with_features[self.features].iloc[-1:]
        
        if latest_features.isnull().values.any():
            logger.warning(f"'{self.name}': En son veri için özellikler hesaplanamadı (NaN değerler var).")
            return {"score": 0.0, "details": "Özellikler hesaplanamadı."}

        prediction_proba = self.model.predict_proba(latest_features)
        probability_of_increase = prediction_proba[0][1]
        predicted_class = self.model.predict(latest_features)[0]

        score = (probability_of_increase - 0.5) * 2

        details = f"Tahmin: {'Yükseliş' if predicted_class == 1 else 'Düşüş/Sabit'} (Olasılık: {probability_of_increase:.2f})"
        logger.info(f"'{self.name}' modeli sonucu: Yükseliş Olasılığı={probability_of_increase:.4f}, Skor={score:.4f}, Detay: {details}")
        return {"score": float(score), "details": details}

# Örnek Kullanım
if __name__ == '__main__':
    logger.info("--- MachineLearningModel Test Başlatıldı ---")
    try:
        fetcher = DataFetcher()
        model = MachineLearningModel(data_fetcher=fetcher)
        # Test için önce modeli eğitmeniz gerekebilir
        # python scripts/train_model.py --interval 1d
        prediction = model.predict(symbol="BTC-USD", interval="1d")
        print("--- Test Sonucu ---")
        print(f"Model Adı: {model.name}")
        print(f"Tahmin: {prediction}")
    except Exception as e:
        logger.error(f"Test sırasında bir hata oluştu: {e}", exc_info=True)
    logger.info("--- MachineLearningModel Test Tamamlandı ---")