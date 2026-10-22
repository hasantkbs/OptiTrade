"""OptiTrade — second, independent held-out window for the BTC chart
model (CNN+LSTM, ml/chart_model.py).

Usage (from backend/src):
  python -m research.validate_chart_model_window2

`train_chart_model.py::train()` reports its headline test accuracy on
the chronologically LAST 15% of BTC-USD's full history - everything
else (first 70% + middle 15%) is already spent as that run's own
train/val. To check whether the result replicates (same approach used
for attempt 7's News features in the ml-accuracy research: a second,
non-overlapping held-out window, not a re-read of the same split),
this script:

  1. Rebuilds the exact same full sequence array `train()` builds.
  2. Reuses `train()`'s own train/val/test boundaries to identify
     window 1's test block (the last 15%) and never touches it.
  3. Trains a FRESH model on window 1's former TRAIN block only (the
     first 70%), with its own inner validation split carved from the
     tail of that block for early stopping (never seen as a reported
     metric).
  4. Evaluates that fresh model on window 1's former VAL block (the
     middle 15%) as window 2's test set - zero overlap with window 1's
     test block, and never used in window 2's own training.

Deliberately does not touch MODEL_PATH/SCALER_PATH/the meta file -
this is a validation-only run, not a replacement for the already
trained-and-saved model.
"""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

import json
import logging
import os

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def validate(
    symbol: str = "BTC-USD",
    epochs: int = 50,
    batch_size: int = 64,
    test_split: float = 0.15,
    val_split: float = 0.15,
    inner_val_split: float = 0.15,
    period: str = "max",
    use_class_weights: bool = True,
) -> dict:
    import yfinance as yf
    from sklearn.metrics import classification_report, confusion_matrix
    from sklearn.preprocessing import StandardScaler
    from sklearn.utils.class_weight import compute_class_weight
    from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau

    from ml.chart_model import (
        FORWARD_DAYS, N_FEATURES, WINDOW,
        _build_features, _create_sequences, _label_data, build_model,
        meta_path_for,
    )

    logger.info(f"Veri çekiliyor: {symbol} ({period})")
    hist = yf.Ticker(symbol).history(period=period)
    if hist.empty or len(hist) < WINDOW + 100:
        raise ValueError(f"{symbol} için yetersiz veri (period={period}).")

    X_raw = _build_features(hist)
    if X_raw is None:
        raise ValueError(f"{symbol} için özellik çıkarımı başarısız.")
    y_raw = _label_data(hist["Close"].iloc[: len(X_raw)])
    X_seq, y_seq = _create_sequences(X_raw, y_raw)

    # Window 1's own boundaries (must match train_chart_model.py::train()
    # exactly, or "window 1's test block" below would be wrong).
    n = len(X_seq)
    n_test1 = int(n * test_split)
    n_val1 = int(n * val_split)
    n_train1 = n - n_test1 - n_val1

    print("=" * 65)
    print(f"BTC chart model - second window validation ({symbol}, {n} toplam örnek)")
    print(f"Window 1's test block (untouched here): son {n_test1} örnek")
    print(f"Window 2 train: ilk {n_train1} örnek | Window 2 test: ortadaki {n_val1} örnek "
          f"(window 1'in val bloğu - window 1'in test bloğuyla sıfır örtüşme)")
    print("=" * 65)

    # ── Window 2's own train/inner-val/test split ────────────────────────
    window2_test_start = n_train1 + FORWARD_DAYS
    X_test2, y_test2 = X_seq[window2_test_start:n_train1 + n_val1], y_seq[window2_test_start:n_train1 + n_val1]

    n_inner_val = int(n_train1 * inner_val_split)
    n_inner_train = n_train1 - n_inner_val
    X_train2, y_train2 = X_seq[:n_inner_train], y_seq[:n_inner_train]
    inner_val_start = n_inner_train + FORWARD_DAYS
    X_val2, y_val2 = X_seq[inner_val_start:n_train1], y_seq[inner_val_start:n_train1]

    # ── Scaler fit ONLY on window 2's own training data ──────────────────
    scaler = StandardScaler()
    scaler.fit(X_train2.reshape(-1, N_FEATURES))

    def scale(X):
        return scaler.transform(X.reshape(-1, N_FEATURES)).reshape(X.shape)

    X_train2, X_val2, X_test2 = scale(X_train2), scale(X_val2), scale(X_test2)

    cw = None
    if use_class_weights:
        weights = compute_class_weight("balanced", classes=np.array([0, 1, 2]), y=y_train2)
        cw = {0: weights[0], 1: weights[1], 2: weights[2]}

    model = build_model()
    callbacks = [
        EarlyStopping(patience=8, restore_best_weights=True, verbose=1),
        ReduceLROnPlateau(factor=0.5, patience=4, verbose=1),
    ]
    model.fit(
        X_train2, y_train2,
        validation_data=(X_val2, y_val2),
        epochs=epochs,
        batch_size=batch_size,
        class_weight=cw,
        callbacks=callbacks,
        verbose=1,
    )

    test_loss2, test_acc2 = model.evaluate(X_test2, y_test2, verbose=0)
    y_pred2 = np.argmax(model.predict(X_test2, verbose=0), axis=1)
    label_names = ["SELL", "NEUTRAL", "BUY"]
    report2 = classification_report(y_test2, y_pred2, target_names=label_names, output_dict=True)
    cm2 = confusion_matrix(y_test2, y_pred2).tolist()
    _, counts2 = np.unique(y_test2, return_counts=True)
    majority2 = max(counts2) / len(y_test2)

    print(f"\n--- Window 2 sonucu ---")
    print(f"Test accuracy : {test_acc2:.4f} | Majority baseline: {majority2:.4f}")
    print(f"Test loss     : {test_loss2:.4f}")
    print(f"\n{classification_report(y_test2, y_pred2, target_names=label_names)}")
    print(f"Confusion matrix:\n{np.array(cm2)}")

    meta_path = meta_path_for(symbol)
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            meta1 = json.load(f)
        n_test1_actual = meta1["n_test"]
        test_acc1 = meta1["test_accuracy"]
        support1 = meta1["classification_report"]["SELL"]["support"] + \
            meta1["classification_report"]["NEUTRAL"]["support"] + \
            meta1["classification_report"]["BUY"]["support"]
        majority1 = max(
            meta1["classification_report"]["SELL"]["support"],
            meta1["classification_report"]["NEUTRAL"]["support"],
            meta1["classification_report"]["BUY"]["support"],
        ) / support1
        print(f"\n--- Window 1 (önceden eğitilmiş, karşılaştırma için) ---")
        print(f"Test accuracy : {test_acc1:.4f} | Majority baseline: {majority1:.4f}")
        print(f"\n--- Karşılaştırma ---")
        print(f"Window 1: accuracy {test_acc1:.4f} vs baseline {majority1:.4f} "
              f"(gap {test_acc1 - majority1:+.4f})")
        print(f"Window 2: accuracy {test_acc2:.4f} vs baseline {majority2:.4f} "
              f"(gap {test_acc2 - majority2:+.4f})")

    return {
        "window2_test_accuracy": round(float(test_acc2), 4),
        "window2_majority_baseline": round(float(majority2), 4),
        "window2_classification_report": report2,
        "window2_confusion_matrix": cm2,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="BTC chart model - second window validation")
    parser.add_argument("--symbol", default="BTC-USD", help="Varlık sembolü")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--period", default="max", help="yfinance period: max/5y/2y")
    args = parser.parse_args()

    validate(symbol=args.symbol, epochs=args.epochs, batch_size=args.batch_size, period=args.period)
