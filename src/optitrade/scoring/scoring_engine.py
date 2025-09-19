
import logging
import pkgutil
import inspect
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
                    if issubclass(member_obj, BaseModel) and member_obj is not BaseModel:
                        if member_name in all_model_names:
                            logger.info(f"'{member_name}' modeli başlatılıyor...")
                            loaded_models[member_name] = member_obj(self.data_fetcher)
            except Exception as e:
                logger.error(f"'{name}' modülü yüklenirken hata oluştu: {e}")
        logger.info(f"{len(loaded_models)} adet model başarıyla yüklendi: {list(loaded_models.keys())}")
        return loaded_models

    def _select_weights(self, regime: str, asset_type: str) -> Dict[str, float]:
        """Piyasa rejimine ve varlık tipine göre uygun ağırlık profilini seçer."""
        asset_profiles = self.weight_profiles.get(asset_type, self.weight_profiles["crypto"]) # Varlık tipi yoksa kripto varsay
        
        if "Strong" in regime:
            logger.info(f"Varlık Tipi '{asset_type}', Rejim '{regime}' -> GÜÇLÜ TREND ağırlıkları seçildi.")
            return asset_profiles["STRONG_TREND"]
        elif "Weak" in regime:
            logger.info(f"Varlık Tipi '{asset_type}', Rejim '{regime}' -> YATAY PİYASA ağırlıkları seçildi.")
            return asset_profiles["RANGING"]
        else: # Unknown veya diğer durumlar için
            logger.info(f"Varlık Tipi '{asset_type}', Rejim '{regime}' -> VARSAYILAN ağırlıklar seçildi.")
            return asset_profiles["DEFAULT"]

    def run_engine(self, asset_type: str, symbol: str, interval: str = "1d", model_params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Yüklenen tüm modelleri çalıştırır, nihai bir skor üretir ve risk analizi yapar.
        asset_type: Varlık tipi (crypto veya stock).
        model_params: Her model için özel parametreleri içeren bir sözlük (örn: {"PriceTrendModel": {"rsi_window": 20}})
        """
        if model_params is None:
            model_params = {}

        # 1. Piyasa Rejimini Belirle
        regime_model = self.models.get("MarketConditionClassifier")
        regime_model_specific_params = model_params.get("MarketConditionClassifier", {})
        regime_result = regime_model.predict(symbol=symbol, interval=interval, **regime_model_specific_params) if regime_model else {"regime": "Unknown", "details": "Rejim modeli yüklenemedi."}
        market_regime = regime_result.get("regime", "Unknown")

        # 2. Rejime ve Varlık Tipine Göre Ağırlıkları Seç ve Normalize Et
        active_weights = self._select_weights(market_regime, asset_type)
        normalized_weights = self._normalize_weights(active_weights)

        # 3. Anlık piyasa fiyatını ve ATR'yi çek/hesapla
        period_map = {"15m": "60d", "4h": "730d", "1d": "5y"}
        fetch_period = period_map.get(interval, "5y")
        latest_data = self.data_fetcher.get_market_data(asset_type=asset_type, symbol=symbol, period=fetch_period, interval=interval)
        current_price = None
        atr = None
        if not latest_data.empty:
            current_price = latest_data['Close'].iloc[-1]
            try:
                atr = ta.volatility.AverageTrueRange(
                    high=latest_data['High'],
                    low=latest_data['Low'],
                    close=latest_data['Close'],
                    window=14
                ).average_true_range().iloc[-1]
                logger.info(f"Hesaplanan ATR değeri: {atr:.4f}")
            except Exception as e:
                logger.warning(f"ATR hesaplanırken hata oluştu: {e}")

        # 4. Diğer tüm modelleri çalıştır ve skorları topla
        final_score = 0.0
        model_outputs = {"MarketConditionClassifier": regime_result} # Rejim bilgisini de çıktılara ekle
        support_resistance_levels = {}

        logger.info(f"Scoring Engine, '{symbol}' ('{asset_type}') için '{market_regime}' rejiminde çalıştırılıyor...")
        for model_name, model_instance in self.models.items():
            if model_name == "MarketConditionClassifier":
                continue # Zaten çalıştırdık
            
            weight = normalized_weights.get(model_name, 0.0)
            if weight == 0:
                logger.debug(f"Model '{model_name}' atlanıyor (ağırlık: 0).")
                continue

            try:
                model_specific_params = model_params.get(model_name, {})
                # Her modele asset_type bilgisini de gönder
                prediction = model_instance.predict(symbol=symbol, interval=interval, asset_type=asset_type, **model_specific_params)
                score = prediction.get('score', 0.0)
                final_score += score * weight
                model_outputs[model_name] = prediction

                if model_name == 'SupportResistanceModel':
                    support_resistance_levels['support'] = prediction.get('closest_support')
                    support_resistance_levels['resistance'] = prediction.get('closest_resistance')

            except Exception as e:
                logger.error(f"'{model_name}' modeli çalıştırılırken hata oluştu: {e}")
                model_outputs[model_name] = {'score': 0.0, 'details': 'Model çalışırken hata oluştu.'}
        
        final_score = np.tanh(final_score)

        # 5. Hedef fiyat ve dinamik zarar durdurma seviyelerini belirle
        estimated_target_price, stop_loss_price = None, None
        if final_score > config.SIGNAL_THRESHOLD:  # Yükseliş sinyali
            estimated_target_price = support_resistance_levels.get('resistance')
            structure_stop = support_resistance_levels.get('support')
            # Volatilite bazlı stop-loss hesapla
            if current_price and atr:
                volatility_stop = current_price - (atr * config.RISK_ATR_MULTIPLIER)
                # İki stop seviyesinden hangisi fiyata daha yakınsa (daha güvenli ise) onu kullan
                if structure_stop:
                    stop_loss_price = max(structure_stop, volatility_stop)
                else:
                    stop_loss_price = volatility_stop
            else:
                stop_loss_price = structure_stop

        elif final_score < -config.SIGNAL_THRESHOLD:  # Düşüş sinyali
            estimated_target_price = support_resistance_levels.get('support')
            structure_stop = support_resistance_levels.get('resistance')
            # Volatilite bazlı stop-loss hesapla
            if current_price and atr:
                volatility_stop = current_price + (atr * config.RISK_ATR_MULTIPLIER)
                # İki stop seviyesinden hangisi fiyata daha yakınsa (daha güvenli ise) onu kullan
                if structure_stop:
                    stop_loss_price = min(structure_stop, volatility_stop)
                else:
                    stop_loss_price = volatility_stop
            else:
                stop_loss_price = structure_stop

        # 6. Pozisyon büyüklüğünü hesapla
        position_sizing = calculate_position_size(final_score, current_price, estimated_target_price, stop_loss_price)

        # 7. Nihai sonucu birleştir
        result = {
            "market_regime": market_regime,
            "final_score": float(final_score),
            "current_market_price": float(current_price) if current_price is not None else None,
            "estimated_target_price": estimated_target_price,
            "position_sizing": position_sizing,
            "model_outputs": model_outputs
        }
        
        # 8. Uyarıları kontrol et ve gönder
        self.alert_system.check_and_dispatch_alert(symbol, result)

        # 9. Sinyali veritabanına kaydet
        self.db_handler.save_signal(result, symbol, interval)

        logger.info(f"Scoring Engine tamamlandı. Nihai Skor: {final_score:.4f}")
        return result
