"""
OptiTrade XGBoost Sinyal Sınıflandırıcı Eğitim Scripti
------------------------------------------------------
Çalıştırmak için:
  cd backend
  python research/ml_trainer.py

Gereksinimler:
  pip install xgboost scikit-learn joblib
"""

import sys
import os
import shutil
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import yfinance as yf
from typing import List, Tuple, Optional
import logging

logging.basicConfig(level=logging.WARNING)

from core.indicators import (
    calculate_rsi,
    calculate_macd,
    calculate_bollinger_bands,
    calculate_ema_crossover,
    calculate_trend_strength,
    calculate_price_velocity,
    calculate_volume_ratio,
)

LOOKBACK = 60
FORWARD_DAYS = 5
THRESHOLD_UP = 1.0

# A freshly retrained model is only allowed to replace the live model
# if its cross-validated accuracy isn't more than this many percentage
# points worse than the model it would replace - retraining on noisy
# daily data must never silently ship a regression to production (see
# _deploy_if_not_regressed below).
MAX_ACCURACY_REGRESSION = 0.01

SYMBOLS = [
    "THYAO.IS", "GARAN.IS", "ASELS.IS", "KCHOL.IS", "EREGL.IS",
    "AKBNK.IS", "TUPRS.IS", "FROTO.IS", "SAHOL.IS", "PGSUS.IS",
    "ISCTR.IS", "SISE.IS",  "BIMAS.IS", "YKBNK.IS", "TOASO.IS",
    "BTC-USD",  "ETH-USD",  "BNB-USD",  "SOL-USD",  "AVAX-USD",
    "XRP-USD",  "DOGE-USD",
]

FEATURE_NAMES = [
    "rsi",
    "macd_diff",
    "bollinger_pb",
    "ema_signal_enc",
    "trend_strength",
    "price_velocity",
    "volume_ratio",
]

EMA_SIGNAL_ENC = {
    "GOLDEN_CROSS": 2,
    "BULLISH": 1,
    "BEARISH": -1,
    "DEATH_CROSS": -2,
    None: 0,
}


def extract_features(window: pd.DataFrame) -> Optional[List[float]]:
    try:
        prices = window["Close"]
        current = float(prices.iloc[-1])
        open_p  = float(window["Open"].iloc[-1])
        vol     = float(window["Volume"].iloc[-1])
        avg_vol = float(window["Volume"].mean())

        rsi = calculate_rsi(prices)
        if rsi is None:
            rsi = 50.0

        macd, macd_sig, _ = calculate_macd(prices)
        macd_diff = (macd - macd_sig) if (macd is not None and macd_sig is not None) else 0.0

        boll = calculate_bollinger_bands(prices)
        pb = boll.get("percent_b") if boll else None
        if pb is None:
            pb = 0.5

        ema  = calculate_ema_crossover(prices)
        ema_enc = EMA_SIGNAL_ENC.get(ema, 0)

        trend = calculate_trend_strength(prices) or 0.0
        vel   = calculate_price_velocity(current, open_p)
        vol_r = calculate_volume_ratio(vol, avg_vol)

        return [rsi, macd_diff, pb, ema_enc, trend, vel, vol_r]
    except Exception:
        return None


def build_dataset(symbol: str) -> Tuple[np.ndarray, np.ndarray]:
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="2y")
    if hist is None or len(hist) < LOOKBACK + FORWARD_DAYS + 10:
        return np.array([]), np.array([])

    X, y = [], []
    for i in range(LOOKBACK, len(hist) - FORWARD_DAYS):
        window = hist.iloc[i - LOOKBACK : i + 1]
        feats = extract_features(window)
        if feats is None:
            continue

        current_p = float(hist["Close"].iloc[i])
        future_p  = float(hist["Close"].iloc[i + FORWARD_DAYS])
        label = 1 if ((future_p - current_p) / current_p) * 100 > THRESHOLD_UP else 0

        X.append(feats)
        y.append(label)

    return np.array(X, dtype=np.float32), np.array(y, dtype=np.int32)


def _deploy_if_not_regressed(model_path: str, package: dict, joblib_module) -> bool:
    """Replaces the live-served model file at `model_path` with `package`
    only if doing so can't ship a silent accuracy regression, and does
    so without ever leaving a partially-written/corrupt file behind.

    - Compares `package["cv_accuracy_mean"]` against whatever model is
      currently live (if any) and refuses to deploy if the new model is
      worse by more than MAX_ACCURACY_REGRESSION.
    - Keeps a `<model_path>.bak` copy of the previous live model before
      swapping, so a bad deploy can be manually rolled back by copying
      the backup over `model_path`.
    - Writes the new model to a temp file first and `os.replace()`s it
      into place - `os.replace` is atomic on the same filesystem, so a
      reader never observes a half-written file.

    Returns True if the new model was deployed, False if it was
    rejected for regressing.
    """
    if os.path.exists(model_path):
        try:
            previous = joblib_module.load(model_path)
            previous_accuracy = previous.get("cv_accuracy_mean")
        except Exception:
            previous_accuracy = None

        if previous_accuracy is not None:
            new_accuracy = package["cv_accuracy_mean"]
            if new_accuracy < previous_accuracy - MAX_ACCURACY_REGRESSION:
                print(
                    f"[ATLANDI] Yeni model canli modelden daha kotu "
                    f"({new_accuracy*100:.1f}% < {previous_accuracy*100:.1f}% - "
                    f"{MAX_ACCURACY_REGRESSION*100:.0f}pp tolerans) - dagitim iptal edildi."
                )
                return False

        shutil.copy2(model_path, model_path + ".bak")

    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(model_path) or ".", suffix=".joblib.tmp")
    os.close(fd)
    try:
        joblib_module.dump(package, tmp_path)
        os.replace(tmp_path, model_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
    return True


def train():
    try:
        from xgboost import XGBClassifier
    except ImportError:
        print("[HATA] XGBoost yüklü değil. Çalıştırın: pip install xgboost scikit-learn joblib")
        return

    try:
        from sklearn.model_selection import cross_val_score, StratifiedKFold, train_test_split
        from sklearn.metrics import classification_report, confusion_matrix
        import joblib
    except ImportError:
        print("[HATA] scikit-learn / joblib yüklü değil. Çalıştırın: pip install scikit-learn joblib")
        return

    print("=" * 65)
    print("OptiTrade - XGBoost Sinyal Sınıflandırıcı Eğitimi")
    print(f"Lookback: {LOOKBACK} gün | Forward: {FORWARD_DAYS} gün | Eşik: +%{THRESHOLD_UP}")
    print("=" * 65)

    all_X, all_y = [], []
    for sym in SYMBOLS:
        print(f"  Veri çekiliyor: {sym}...", end=" ", flush=True)
        X, y = build_dataset(sym)
        if len(X) > 0:
            all_X.append(X)
            all_y.append(y)
            print(f"{len(X)} örnek (pozitif: {y.sum()}, {y.mean()*100:.0f}%)")
        else:
            print("yetersiz veri - atlandı")

    if not all_X:
        print("[HATA] Hiç veri toplanamadı!")
        return

    X_all = np.vstack(all_X)
    y_all = np.concatenate(all_y)

    pos_rate = y_all.mean() * 100
    print(f"\nToplam veri seti: {len(X_all)} örnek | "
          f"Pozitif (AL): {y_all.sum()} ({pos_rate:.1f}%)")

    X_train, X_test, y_train, y_test = train_test_split(
        X_all, y_all, test_size=0.2, random_state=42, stratify=y_all
    )

    model = XGBClassifier(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        gamma=0.1,
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
    )

    print("\nModel eğitiliyor (5-katlı çapraz doğrulama)...")
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_val_score(
        model, X_train, y_train, cv=cv, scoring="accuracy", n_jobs=-1
    )
    print(f"Cross-val doğruluk: {cv_scores.mean()*100:.1f}% ± {cv_scores.std()*100:.1f}%")

    model.fit(X_train, y_train, verbose=False)

    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    print("\nTest seti sınıflandırma raporu:")
    print(classification_report(y_test, y_pred, target_names=["DÜŞÜŞ/NÖTR", "YUKARI"]))

    print("Karmaşıklık matrisi:")
    cm = confusion_matrix(y_test, y_pred)
    print(f"  TN={cm[0,0]:4d}  FP={cm[0,1]:4d}")
    print(f"  FN={cm[1,0]:4d}  TP={cm[1,1]:4d}")

    print("\nÖzellik önemleri:")
    for name, imp in sorted(zip(FEATURE_NAMES, model.feature_importances_), key=lambda x: -x[1]):
        bar = "█" * int(imp * 40)
        print(f"  {name:18s}: {bar} ({imp:.3f})")

    os.makedirs("models", exist_ok=True)
    model_path = os.path.join("models", "xgb_signal_model.joblib")
    package = {
        "model": model,
        "feature_names": FEATURE_NAMES,
        "lookback": LOOKBACK,
        "forward_days": FORWARD_DAYS,
        "threshold": THRESHOLD_UP,
        "cv_accuracy_mean": float(cv_scores.mean()),
        "cv_accuracy_std": float(cv_scores.std()),
        "train_samples": len(X_train),
        "test_samples": len(X_test),
    }
    if _deploy_if_not_regressed(model_path, package, joblib):
        print(f"\nModel kaydedildi: {model_path}")
    print("=" * 65)


if __name__ == "__main__":
    train()
