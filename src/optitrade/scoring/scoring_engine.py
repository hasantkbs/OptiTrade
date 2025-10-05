
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
from ..models.base_model import BaseModel
from ..utils.data_fetcher import DataFetcher
from ..risk.risk_manager import calculate_position_size
from ..alerting.alert_system import AlertSystem
from ..database.database_handler import DatabaseHandler
# MarketConditionClassifier modelini özel olarak içe aktar
from ..models.market_condition_classifier import MarketConditionClassifier

logger = logging.getLogger(__name__)

class ScoringEngine:
    """
    Piyasa rejimini tespit eder, dinamik olarak model ağırlıklarını seçer,
    tüm modelleri çalıştırır ve nihai bir skor üretir.
    """
    def __init__(self, data_fetcher: DataFetcher, db_handler: DatabaseHandler):
        self.data_fetcher = data_fetcher
        self.db_handler = db_handler
        # Varlık tipine göre tüm ağırlık profillerini yükle
        self.weight_profiles = {
            "crypto": {
                "DEFAULT": config.MODEL_WEIGHTS_DEFAULT,
                "STRONG_TREND": config.MODEL_WEIGHTS_STRONG_TREND,
                "RANGING": config.MODEL_WEIGHTS_RANGING
            },
            "stock": {
                "DEFAULT": config.MODEL_WEIGHTS_STOCK_DEFAULT,
                "STRONG_TREND": config.MODEL_WEIGHTS_STOCK_STRONG_TREND,
                "RANGING": config.MODEL_WEIGHTS_STOCK_RANGING
            }
        }
        self.models = self._load_models()
        self.alert_system = AlertSystem()
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
        # Tüm ağırlık profillerindeki tüm benzersiz model adlarını topla
        all_model_names = set()
        for asset_profiles in self.weight_profiles.values():
            for profile in asset_profiles.values():
                all_model_names.update(profile.keys())

        for _, name, _ in pkgutil.iter_modules(models.__path__):
            try:
                module = __import__(f"{models.__name__}.{name}", fromlist=["*"])
                for member_name, member_obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(member_obj, BaseModel) and member_obj is not BaseModel and not inspect.isabstract(member_obj):
                        if member_name in all_model_names:
                            logger.info(f"'{member_name}' modeli başlatılıyor...")
                            try:
                                # Modelin __init__ metodunun 'data_fetcher' argümanı alıp almadığını kontrol et
                                init_signature = inspect.signature(member_obj.__init__)
                                if 'data_fetcher' in init_signature.parameters:
                                    loaded_models[member_name] = member_obj(self.data_fetcher)
                                else:
                                    loaded_models[member_name] = member_obj()
                            except Exception as e:
                                logger.error(f"'{member_name}' modeli başlatılırken bir hata oluştu: {e}")
            except Exception as e:
                logger.error(f"'{name}' modülü yüklenirken hata oluştu: {e}")
        logger.info(f"{len(loaded_models)} adet model başarıyla yüklendi: {list(loaded_models.keys())}")
        return loaded_models

    def _select_weights(self, regime: str, asset_type: str) -> Dict[str, float]:
        """Piyasa rejimine ve varlık tipine göre uygun ağırlık profilini seçer."""
        asset_profiles = self.weight_profiles.get(asset_type, self.weight_profiles["crypto"]) # Varlık tipi yoksa kripto varsay
        
        selected_weights = {}
        if "Strong" in regime:
            logger.info(f"Varlık Tipi '{asset_type}', Rejim '{regime}' -> GÜÇLÜ TREND ağırlıkları seçildi.")
            selected_weights = asset_profiles["STRONG_TREND"]
        elif "Weak" in regime:
            logger.info(f"Varlık Tipi '{asset_type}', Rejim '{regime}' -> YATAY PİYASA ağırlıkları seçildi.")
            selected_weights = asset_profiles["RANGING"]
        else: # Unknown veya diğer durumlar için
            logger.info(f"Varlık Tipi '{asset_type}', Rejim '{regime}' -> VARSAYILAN ağırlıklar seçildi.")
            selected_weights = asset_profiles["DEFAULT"]

        # Kripto varlıklar için FinancialRatioModel ağırlığını 0 yap
        if asset_type == "crypto" and "FinancialRatioModel" in selected_weights:
            selected_weights["FinancialRatioModel"] = 0.0
            logger.info("Kripto varlıklar için 'FinancialRatioModel' ağırlığı 0 olarak ayarlandı.")

        return selected_weights

    def run_engine(self, all_model_scores_df: pd.DataFrame, asset_type: str, symbol: str, interval: str = "1d") -> pd.Series:
        """
        Verilen tüm model skorlarını birleştirerek nihai bir skor serisi üretir.
        asset_type: Varlık tipi (crypto veya stock).
        all_model_scores_df: Her sütunun bir modelin skorlarını içeren DataFrame.
        """
        if all_model_scores_df.empty:
            return pd.Series(0.0, index=[])

        # Optimized parameters are applied to models during initialization or before calling generate_score.
        # This run_engine now only combines pre-calculated scores.

        # MarketConditionClassifier'ın skorunu al (eğer varsa)
        market_regime_scores = all_model_scores_df.get('market_condition_classifier_score')
        # Şimdilik, en son rejimi alalım veya varsayılanı kullanalım.
        # Daha sonra, her zaman noktası için dinamik rejim seçimi yapılabilir.
        market_regime = "Unknown"
        if market_regime_scores is not None and not market_regime_scores.empty:
            # Assuming MarketConditionClassifier.generate_score returns a dict with 'regime' for each row
            # This needs to be adapted if MarketConditionClassifier also returns a Series of regimes.
            # For now, let's just take the last one.
            # This is a simplification and needs further refinement for full backtesting.
            # The current MarketConditionClassifier.generate_score returns a dict with 'regime' for the latest data.
            # This needs to be changed to return a Series of regimes.
            # For now, let's just use a placeholder.
            market_regime = "Unknown" # Placeholder, will be dynamic later.

        logger.info(f"Piyasa Rejimi Belirlendi: {market_regime}")

        # Rejime ve Varlık Tipine Göre Ağırlıkları Seç ve Normalize Et
        active_weights = self._select_weights(market_regime, asset_type)
        normalized_weights = self._normalize_weights(active_weights)
        logger.info(f"Aktif Ağırlıklar ({market_regime}): {json.dumps(normalized_weights, indent=2)}")

        final_scores = pd.Series(0.0, index=all_model_scores_df.index)

        logger.info(f"Scoring Engine, '{symbol}' ('{asset_type}') için '{market_regime}' rejiminde çalıştırılıyor...")
        for model_score_column, weight in normalized_weights.items():
            if model_score_column in all_model_scores_df.columns:
                final_scores += all_model_scores_df[model_score_column] * weight
            else:
                logger.warning(f"Model skoru sütunu '{model_score_column}' DataFrame'de bulunamadı. Ağırlık uygulanmayacak.")

        final_scores = np.tanh(final_scores)

        logger.info(f"Scoring Engine tamamlandı. Nihai Skor Serisi oluşturuldu.")
        return final_scores
