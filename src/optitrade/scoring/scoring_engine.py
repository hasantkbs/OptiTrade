
import logging
import pkgutil
import inspect
import json
import os
from typing import Dict, Any

import numpy as np
import ta

from .. import config
from .. import models
from ..models.registry import MODEL_REGISTRY
from ..models.base_model import BaseModel
from ..utils.data_fetcher import DataFetcher



# MarketConditionClassifier modelini özel olarak içe aktar
from ..models.market_condition_classifier import MarketConditionClassifier

logger = logging.getLogger(__name__)

class ScoringEngine:
    """
    Piyasa rejimini tespit eder, dinamik olarak model ağırlıklarını seçer,
    tüm modelleri çalıştırır ve nihai bir skor üretir.
    """
    def __init__(self, data_fetcher: DataFetcher):
        self.data_fetcher = data_fetcher

        # Varlık tipine göre tüm ağırlık profillerini yükle
        self.weight_profiles = {
            "crypto": {
                "DEFAULT": config.MODEL_WEIGHTS_DEFAULT,
                "STRONG_TREND": config.MODEL_WEIGHTS_STRONG_TREND,
                "RANGING": config.MODEL_WEIGHTS_RANGING
            }
        }
        self.models = self._load_models()

        self.optimized_parameters = self._load_optimized_parameters()

    def _load_optimized_parameters(self) -> Dict[str, Any]:
        """Loads optimized parameters from JSON files."""
        optimized_params = {}
        for filename in os.listdir("."):
            if filename.startswith("optimized_parameters_") and filename.endswith(".json"):
                try:
                    with open(filename, "r") as f:
                        parts = filename.replace("optimized_parameters_", "").replace(".json", "").split("_")
                        model_name = parts[0]
                        symbol = parts[1]
                        interval = parts[2]
                        if model_name not in optimized_params:
                            optimized_params[model_name] = {}
                        if symbol not in optimized_params[model_name]:
                            optimized_params[model_name][symbol] = {}
                        optimized_params[model_name][symbol][interval] = json.load(f)
                except Exception as e:
                    logger.error(f"Error loading optimized parameters from {filename}: {e}")
        return optimized_params

    def _normalize_weights(self, weights: Dict[str, float]) -> Dict[str, float]:
        """Verilen ağırlık setinin toplamını 1'e normalize eder."""
        total_weight = sum(weights.values())
        if total_weight > 0:
            return {name: w / total_weight for name, w in weights.items()}
        return weights

    def _load_models(self) -> Dict[str, BaseModel]:
        logger.info("Modeller yükleniyor...")
        loaded_models = {}
        
        for model_name, model_class in MODEL_REGISTRY.items():
            if issubclass(model_class, BaseModel) and model_class is not BaseModel and not inspect.isabstract(model_class):
                logger.info(f"'{model_name}' modeli başlatılıyor...")
                try:
                    # Modelin __init__ metodunun 'data_fetcher' argümanı alıp almadığını kontrol et
                    init_signature = inspect.signature(model_class.__init__)
                    if 'data_fetcher' in init_signature.parameters:
                        loaded_models[model_name] = model_class(data_fetcher=self.data_fetcher)
                    else:
                        loaded_models[model_name] = model_class()
                except Exception as e:
                    logger.error(f"'{model_name}' modeli başlatılırken bir hata oluştu: {e}")
        logger.info(f"{len(loaded_models)} adet model başarıyla yüklendi: {list(loaded_models.keys())}")
        return loaded_models

    def _select_weights(self, regime: str) -> Dict[str, float]:
        """Piyasa rejimine göre uygun ağırlık profilini seçer."""
        asset_profiles = self.weight_profiles["crypto"] # Varlık tipi yoksa kripto varsay
        
        selected_weights = {}
        if "Strong" in regime:
            logger.info(f"Rejim '{regime}' -> GÜÇLÜ TREND ağırlıkları seçildi.")
            selected_weights = asset_profiles["STRONG_TREND"]
        elif "Weak" in regime:
            logger.info(f"Rejim '{regime}' -> YATAY PİYASA ağırlıkları seçildi.")
            selected_weights = asset_profiles["RANGING"]
        else: # Unknown veya diğer durumlar için
            logger.info(f"Rejim '{regime}' -> VARSAYILAN ağırlıklar seçildi.")
            selected_weights = asset_profiles["DEFAULT"]

        return selected_weights

    def run_engine(self, symbol: str, interval: str = "1d") -> Dict[str, Any]:
        """
        Tüm modelleri çalıştırır ve nihai bir skor ve diğer analiz sonuçlarını üretir.
        """
        market_regime = self.models["MarketConditionClassifier"].predict(symbol, interval)['regime']
        logger.info(f"Piyasa Rejimi Belirlendi: {market_regime}")

        active_weights = self._select_weights(market_regime)
        normalized_weights = self._normalize_weights(active_weights)
        logger.info(f"Aktif Ağırlıklar ({market_regime}): {json.dumps(normalized_weights, indent=2)}")

        final_score = 0.0
        all_results = {}

        logger.info(f"Scoring Engine, '{symbol}' için '{market_regime}' rejiminde çalıştırılıyor...")
        for model_name, weight in normalized_weights.items():
            if model_name in self.models:
                try:
                    model_result = self.models[model_name].predict(symbol, interval)
                    all_results[model_name] = model_result
                    final_score += model_result.get('score', 0.0) * weight
                except Exception as e:
                    logger.error(f"'{model_name}' modeli çalıştırılırken hata oluştu: {e}", exc_info=True)
            else:
                logger.warning(f"Model '{model_name}' bulunamadı. Ağırlık uygulanmayacak.")

        final_score = np.tanh(final_score)
        all_results['final_score'] = final_score

        logger.info(f"Scoring Engine tamamlandı. Nihai Skor: {final_score:.4f}")
        return all_results
