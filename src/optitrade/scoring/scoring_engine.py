
import logging
import pkgutil
import inspect
from typing import Dict, Any

import numpy as np

from .. import config
from .. import models
from ..models.base_model import BaseModel
from ..utils.data_fetcher import DataFetcher

# Loglama yapılandırması
logger = logging.getLogger(__name__)

class ScoringEngine:
    """
    Tüm modelleri dinamik olarak yükler, çalıştırır ve skorlarını ağırlıklı olarak birleştirir.
    """
    def __init__(self, data_fetcher: DataFetcher):
        self.data_fetcher = data_fetcher
        self.weights = config.MODEL_WEIGHTS
        self.models = self._load_models()

        total_weight = sum(self.weights.values())
        if total_weight > 0:
            self.weights = {name: w / total_weight for name, w in self.weights.items()}

    def _load_models(self) -> Dict[str, BaseModel]:
        logger.info("Modeller yükleniyor...")
        loaded_models = {}
        for _, name, _ in pkgutil.iter_modules(models.__path__):
            try:
                module = __import__(f"{models.__name__}.{name}", fromlist=["*"])
                for member_name, member_obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(member_obj, BaseModel) and member_obj is not BaseModel:
                        if member_name in self.weights and self.weights[member_name] > 0:
                            logger.info(f"'{member_name}' modeli başlatılıyor...")
                            loaded_models[member_name] = member_obj(self.data_fetcher)
            except Exception as e:
                logger.error(f"'{name}' modülü yüklenirken hata oluştu: {e}")
        logger.info(f"{len(loaded_models)} adet model başarıyla yüklendi: {list(loaded_models.keys())}")
        return loaded_models

    def run_engine(self, symbol: str, interval: str = "1d") -> Dict[str, Any]:
        """
        Yüklenen tüm modelleri çalıştırır ve nihai bir skor ve detaylı çıktılar üretir.

        Args:
            symbol (str): Tahmin yapılacak finansal varlık sembolü (örn: "BTC-USD").
            interval (str): Analiz aralığı (örn: "15m", "4h", "1d").

        Returns:
            Dict[str, Any]: Nihai skoru ve her modelin bireysel skorunu içeren bir sözlük.
        """
        if not self.models:
            logger.warning("Çalıştırılacak model bulunamadı.")
            return {"final_score": 0.0, "model_outputs": {}}

        final_score = 0.0
        model_outputs = {}

        logger.info(f"Scoring Engine, '{symbol}' sembolü için '{interval}' aralığında çalıştırılıyor...")
        for model_name, model_instance in self.models.items():
            try:
                # Modellerin predict metoduna interval parametresini ilet
                prediction = model_instance.predict(symbol=symbol, interval=interval)
                score = prediction.get('score', 0.0)
                weight = self.weights.get(model_name, 0.0)
                
                final_score += score * weight
                model_outputs[model_name] = {
                    'score': score,
                    'details': prediction.get('details', 'Detay mevcut değil.')
                }
                logger.debug(f"Model '{model_name}' -> Skor: {score:.4f}, Ağırlık: {weight:.2f}")
            except Exception as e:
                logger.error(f"'{model_name}' modeli çalıştırılırken hata oluştu: {e}")
                model_outputs[model_name] = {'score': 0.0, 'details': 'Model çalışırken hata oluştu.'}
        
        final_score = np.tanh(final_score)

        result = {
            "final_score": float(final_score),
            "model_outputs": model_outputs
        }
        logger.info(f"Scoring Engine tamamlandı. Nihai Skor: {final_score:.4f}")
        return result

# Örnek Kullanım
if __name__ == '__main__':
    logger.info("--- ScoringEngine Test Başlatıldı ---")
    try:
        fetcher = DataFetcher()
        engine = ScoringEngine(data_fetcher=fetcher)
        if engine.models:
            final_result = engine.run_engine(symbol="BTC-USD", interval="1d") # interval parametresini ekle
            print("--- Test Sonucu ---")
            print(f"Nihai Ağırlıklı Skor: {final_result['final_score']:.4f}")
            print("--- Bireysel Model Çıktıları ---")
            for model_name, output in final_result['model_outputs'].items():
                print(f"- {model_name}: Skor={output['score']:.4f}, Detay: {output['details']}")
    except Exception as e:
        logger.error(f"Test sırasında bir hata oluştu: {e}", exc_info=True)
    logger.info("--- ScoringEngine Test Tamamlandı ---")
