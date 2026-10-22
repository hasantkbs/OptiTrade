"""
OptiTrade — CNN + LSTM Hibrit Model
=====================================
Kullanım:
  from ml.chart_model import load_model, predict_chart_signal

Model Mimarisi:
  1. Conv1D (×2) — yerel fiyat pattern tanıma
  2. MaxPool1D
  3. Bidirectional LSTM — zaman-serisi bağımlılıkları
  4. Dropout
  5. Dense softmax (3 sınıf: SELL / NEUTRAL / BUY)
"""
from __future__ import annotations
import os
import logging
from typing import Optional, Dict, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Sabitler ──────────────────────────────────────────────────────────────────
# Her sembolün kendi scaler/ağırlıkları var (model_path_for vb.), ama canlı
# entegrasyon (main.py) yalnızca burada açıkça listelenen, eğitilmiş VE
# ikinci pencerede doğrulanmış sembollerde çalışmalı. Yeni bir sembol
# eğitilip doğrulanınca buraya eklenmeli - dosyanın var olması tek başına
# yeterli değil (kasıtlı: canlıya alma hâlâ açık bir kod değişikliği
# gerektirsin, sessizce "dosya var, o yüzden aktif" olmasın).
MODEL_SYMBOL = "BTC-USD"  # geriye dönük uyumluluk için - ilk eğitilen/varsayılan sembol
# SOL-USD de eğitildi ama BURADA YOK: window 1'de baseline'ın altında kaldı
# (0.355 vs 0.388, p=0.90 - anlamlı değil) - tutarlı bir sonuç değil, canlıya
# alınmadı. Dosyası model_artifacts/sol_chart_model.keras'ta duruyor, ileride
# daha fazla veriyle (SOL-USD'nin yfinance geçmişi diğerlerinden daha kısa,
# 2292 vs ~3175 sequence) yeniden denenebilir.
SUPPORTED_SYMBOLS = ("BTC-USD", "ETH-USD", "BNB-USD", "XRP-USD", "THYAO.IS")
WINDOW      = 60       # Sliding window (gün)
FORWARD_DAYS = 5       # Kaç gün sonrası tahmin
BUY_THRESH  = 0.03     # %3 üstü yükseliş → BUY
SELL_THRESH = -0.02    # %-2 altı → SELL
N_CLASSES   = 3        # SELL=0, NEUTRAL=1, BUY=2
N_FEATURES  = 11        # OHLCV_norm(5) + RSI + MACD + BB_pb + volume_ratio + ATR + ADX

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
MODEL_DIR   = os.path.join(BACKEND_DIR, "model_artifacts")


def _symbol_slug(symbol: str) -> str:
    """'BTC-USD' -> 'btc', 'ETH-USD' -> 'eth' - matches the existing
    btc_chart_model.keras naming convention, generalized so each
    symbol gets its own model/scaler/meta files instead of silently
    overwriting another symbol's already-trained-and-validated model."""
    return symbol.split("-")[0].lower()


def model_path_for(symbol: str) -> str:
    return os.path.join(MODEL_DIR, f"{_symbol_slug(symbol)}_chart_model.keras")


def scaler_path_for(symbol: str) -> str:
    return os.path.join(MODEL_DIR, f"{_symbol_slug(symbol)}_chart_scaler.joblib")


def meta_path_for(symbol: str) -> str:
    return os.path.join(MODEL_DIR, f"{_symbol_slug(symbol)}_chart_model_meta.json")


# Kept as flat attributes for existing callers/tests that only ever cared
# about MODEL_SYMBOL (BTC) - every function below defaults its `symbol`
# parameter to MODEL_SYMBOL, so a zero-arg call behaves exactly as before.
MODEL_PATH  = model_path_for(MODEL_SYMBOL)
SCALER_PATH = scaler_path_for(MODEL_SYMBOL)

# ── Model Cache (sembol başına) ──────────────────────────────────────────────
_model_cache: Dict[str, object] = {}
_scaler_cache: Dict[str, object] = {}


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Model Tanımı
# ─────────────────────────────────────────────────────────────────────────────

def build_model():
    from tensorflow import keras
    from tensorflow.keras import layers

    inputs = keras.Input(shape=(WINDOW, N_FEATURES))

    # CNN bloğu — yerel pattern tanıma
    x = layers.Conv1D(64, kernel_size=3, padding="causal", activation="relu")(inputs)
    x = layers.BatchNormalization()(x)
    x = layers.Conv1D(128, kernel_size=3, padding="causal", activation="relu")(x)
    x = layers.BatchNormalization()(x)
    x = layers.MaxPooling1D(pool_size=2)(x)
    x = layers.Dropout(0.25)(x)

    # LSTM bloğu — zaman bağımlılıkları
    x = layers.Bidirectional(layers.LSTM(128, return_sequences=True))(x)
    x = layers.Dropout(0.25)(x)
    x = layers.Bidirectional(layers.LSTM(64))(x)
    x = layers.Dropout(0.30)(x)

    # Çıktı katmanı
    x = layers.Dense(64, activation="relu")(x)
    x = layers.Dense(32, activation="relu")(x)
    outputs = layers.Dense(N_CLASSES, activation="softmax")(x)

    model = keras.Model(inputs, outputs)
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=0.001),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Feature Engineering
# ─────────────────────────────────────────────────────────────────────────────

def _build_features(hist: pd.DataFrame) -> Optional[np.ndarray]:
    """
    DataFrame'den 11 özellik çıkar:
      [0-3] OHLC normalize (price / ma20)
      [4]   volume_norm   — hacim / 20 günlük ort. hacim
      [5]   rsi_14        — [0, 1] normalize
      [6]   macd_norm     — MACD / fiyat
      [7]   bb_pb         — Bollinger %B  [0, 1]
      [8]   price_vel     — 5 günlük momentum / fiyat
      [9]   atr_norm      — ATR / fiyat (volatilite)
      [10]  adx_norm      — ADX / 100 (trend gücü)
    """
    try:
        close  = hist["Close"].astype(float)
        open_  = hist["Open"].astype(float)
        high   = hist["High"].astype(float)
        low    = hist["Low"].astype(float)
        volume = hist["Volume"].astype(float)

        ma20  = close.rolling(20).mean()
        vstd  = volume.rolling(20).mean().replace(0, np.nan)

        # RSI
        delta = close.diff()
        gain  = delta.clip(lower=0)
        loss  = (-delta).clip(lower=0)
        avg_gain = gain.ewm(com=13, min_periods=14).mean()
        avg_loss = loss.ewm(com=13, min_periods=14).mean()
        rs    = avg_gain / avg_loss.replace(0, np.nan)
        rsi   = (100 - 100 / (1 + rs)).fillna(50)

        # MACD
        ema12 = close.ewm(span=12, min_periods=12).mean()
        ema26 = close.ewm(span=26, min_periods=26).mean()
        macd  = (ema12 - ema26) / close.replace(0, np.nan)

        # Bollinger %B
        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_pb  = ((close - (bb_mid - 2 * bb_std)) /
                  (4 * bb_std).replace(0, np.nan)).clip(0, 1)

        # ATR (Simple version)
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
        atr_norm = (atr / close).fillna(0).clip(0, 0.1) / 0.1

        # ADX (Directional Movement)
        up_move   = high.diff()
        down_move = low.diff()
        plus_dm   = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm  = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        
        alpha = 1/14
        # `index=high.index` is required here: without it, pd.Series() gets a
        # default RangeIndex while `atr` keeps the original DatetimeIndex, so
        # the division below aligns by index (producing the union of both -
        # roughly double length, mostly NaN) instead of elementwise by
        # position, and every downstream column_stack call fails.
        plus_di  = 100 * (pd.Series(plus_dm, index=high.index).ewm(alpha=alpha).mean() / atr.replace(0, np.nan)).fillna(0)
        minus_di = 100 * (pd.Series(minus_dm, index=high.index).ewm(alpha=alpha).mean() / atr.replace(0, np.nan)).fillna(0)
        dx  = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        adx = dx.ewm(alpha=alpha).mean().fillna(0)

        # Price velocity
        pvel = close.pct_change(5).fillna(0).clip(-0.2, 0.2) / 0.2

        X = np.column_stack([
            (close  / ma20.replace(0, np.nan)).fillna(1).values,
            (open_  / ma20.replace(0, np.nan)).fillna(1).values,
            (high   / ma20.replace(0, np.nan)).fillna(1).values,
            (low    / ma20.replace(0, np.nan)).fillna(1).values,
            (volume / vstd).fillna(1).clip(0, 10).values,
            (rsi / 100).values,
            macd.fillna(0).clip(-0.1, 0.1).values / 0.1,
            bb_pb.fillna(0.5).values,
            pvel.values,
            atr_norm.values,
            (adx / 100).values,
        ])

        # İlk 30 satır NaN olabilir
        valid_start = 30
        X = X[valid_start:]
        return X.astype(np.float32)
    except Exception as e:
        logger.error(f"Feature engineering hatası: {e}")
        return None


def _label_data(close: pd.Series) -> np.ndarray:
    """FORWARD_DAYS sonraki getiriye göre 0/1/2 etiket üret."""
    fwd_return = close.pct_change(FORWARD_DAYS).shift(-FORWARD_DAYS)
    labels = np.where(fwd_return > BUY_THRESH, 2,
              np.where(fwd_return < SELL_THRESH, 0, 1)).astype(np.int32)
    return labels


def _create_sequences(
    X: np.ndarray, y: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    """60 günlük sliding-window sequence dizisi oluştur."""
    n = len(X)
    valid = n - FORWARD_DAYS  # Son FORWARD_DAYS satırın etiketi yoktur

    xs, ys = [], []
    for i in range(WINDOW, valid):
        xs.append(X[i - WINDOW: i])
        ys.append(y[i])
    return np.array(xs, dtype=np.float32), np.array(ys, dtype=np.int32)


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Inference (Runtime)
# ─────────────────────────────────────────────────────────────────────────────

def load_model(symbol: str = MODEL_SYMBOL):
    """`symbol`'e ait model ve scaler'ı yükle (sembol başına önbellek)."""
    if symbol in _model_cache:
        return _model_cache[symbol], _scaler_cache.get(symbol)
    model_path = model_path_for(symbol)
    if not os.path.exists(model_path):
        return None, None
    try:
        import joblib
        from tensorflow import keras
        model = keras.models.load_model(model_path)
        scaler_path = scaler_path_for(symbol)
        scaler = joblib.load(scaler_path) if os.path.exists(scaler_path) else None
        _model_cache[symbol] = model
        _scaler_cache[symbol] = scaler
        logger.info(f"Chart AI modeli yüklendi ({symbol}): {model_path}")
        return model, scaler
    except Exception as e:
        logger.warning(f"Chart AI modeli yüklenemedi ({symbol}): {e}")
        return None, None


def predict_chart_signal(
    hist: pd.DataFrame,
    symbol: str = MODEL_SYMBOL,
) -> Optional[Dict]:
    """
    Son 60 günlük OHLCV verisinden sinyal üret.

    Döndürür:
      signal      : "BUY" | "NEUTRAL" | "SELL"
      confidence  : 0.0 – 1.0
      probabilities: {sell, neutral, buy}
      model_available: bool
    """
    model, scaler = load_model(symbol)
    if model is None:
        return {
            "signal": None,
            "confidence": None,
            "probabilities": None,
            "model_available": False,
        }

    try:
        X = _build_features(hist)
        if X is None or len(X) < WINDOW:
            return {"signal": None, "confidence": None,
                    "probabilities": None, "model_available": True,
                    "error": "Yetersiz veri"}

        seq = X[-WINDOW:].reshape(1, WINDOW, N_FEATURES)

        if scaler is not None:
            flat = seq.reshape(-1, N_FEATURES)
            seq  = scaler.transform(flat).reshape(1, WINDOW, N_FEATURES)

        probs = model.predict(seq, verbose=0)[0]
        idx   = int(np.argmax(probs))
        label_map = {0: "SELL", 1: "NEUTRAL", 2: "BUY"}

        return {
            "signal":     label_map[idx],
            "confidence": round(float(probs[idx]), 4),
            "probabilities": {
                "sell":    round(float(probs[0]), 4),
                "neutral": round(float(probs[1]), 4),
                "buy":     round(float(probs[2]), 4),
            },
            "model_available": True,
        }
    except Exception as e:
        logger.error(f"Predict hatası: {e}")
        return {"signal": None, "confidence": None,
                "probabilities": None, "model_available": True,
                "error": str(e)}


def is_model_available(symbol: str = MODEL_SYMBOL) -> bool:
    return os.path.exists(model_path_for(symbol))


def get_model_meta(symbol: str = MODEL_SYMBOL) -> Dict:
    import json
    meta_path = meta_path_for(symbol)
    if not os.path.exists(meta_path):
        return {"available": False}
    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        meta["available"] = True
        return meta
    except Exception:
        return {"available": False}
