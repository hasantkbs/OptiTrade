"""
OptiTrade ML Tahmin Modülü
--------------------------
Eğitilmiş XGBoost modelini yükler ve sinyal güven skoru döndürür.
Model yoksa sessizce None döndürür (sistem yeniden çalışmaya devam eder).
"""

import os
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)

_MODEL_CACHE = None
_MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "xgb_signal_model.joblib")

EMA_SIGNAL_ENC = {
    "GOLDEN_CROSS": 2,
    "BULLISH": 1,
    "BEARISH": -1,
    "DEATH_CROSS": -2,
    None: 0,
}


def _load_model():
    global _MODEL_CACHE
    if _MODEL_CACHE is not None:
        return _MODEL_CACHE
    path = os.path.normpath(_MODEL_PATH)
    if not os.path.exists(path):
        return None
    try:
        import joblib
        _MODEL_CACHE = joblib.load(path)
        logger.info(f"ML modeli yüklendi: {path}")
        return _MODEL_CACHE
    except Exception as e:
        logger.warning(f"ML modeli yüklenemedi: {e}")
        return None


def get_ml_confidence(
    rsi: Optional[float],
    macd: Optional[float],
    macd_signal: Optional[float],
    bollinger_pb: Optional[float],
    ema_crossover: Optional[str],
    trend_strength: Optional[float],
    volume_ratio: float,
    price_velocity: float,
) -> Optional[float]:
    """
    XGBoost modeliyle yükseliş olasılığını tahmin eder.
    Döndürür: 0.0 - 1.0 arası olasılık, ya da model yoksa None.
    """
    package = _load_model()
    if package is None:
        return None

    try:
        import numpy as np

        macd_diff = (macd - macd_signal) if (macd is not None and macd_signal is not None) else 0.0
        features = [
            rsi if rsi is not None else 50.0,
            macd_diff,
            bollinger_pb if bollinger_pb is not None else 0.5,
            EMA_SIGNAL_ENC.get(ema_crossover, 0),
            trend_strength if trend_strength is not None else 0.0,
            price_velocity,
            volume_ratio,
        ]

        model = package["model"]
        X = np.array([features], dtype=np.float32)
        prob = model.predict_proba(X)[0][1]
        return float(prob)
    except Exception as e:
        logger.debug(f"ML tahmin hatası: {e}")
        return None


def is_model_available() -> bool:
    return _load_model() is not None


def get_model_info() -> dict:
    package = _load_model()
    if package is None:
        return {"available": False}
    return {
        "available": True,
        "cv_accuracy": round(package.get("cv_accuracy_mean", 0) * 100, 1),
        "cv_std": round(package.get("cv_accuracy_std", 0) * 100, 1),
        "train_samples": package.get("train_samples", 0),
        "forward_days": package.get("forward_days", 5),
        "features": package.get("feature_names", []),
    }
