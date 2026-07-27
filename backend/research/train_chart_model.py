"""
OptiTrade — BTC Chart AI Training Pipeline
===========================================
Çalıştır:
  cd backend
  python -m research.train_chart_model [--symbol BTC-USD] [--epochs 50]

Adımlar:
  1. yfinance'dan maksimum BTC verisi çek
  2. Feature engineering (9 özellik, 60 günlük pencere)
  3. CNN+LSTM modeli eğit
  4. Test seti değerlendirmesi + confusion matrix
  5. Modeli kaydet (models/btc_chart_model.keras)
  6. Transfer learning için ağırlıkları dondurma desteği
"""
from __future__ import annotations
import os
import sys
import argparse
import logging
import numpy as np
import json
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Backend root'u path'e ekle
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def train(
    symbol: str = "BTC-USD",
    epochs: int = 50,
    batch_size: int = 64,
    test_split: float = 0.15,
    val_split: float = 0.15,
    period: str = "max",
    use_class_weights: bool = True,
    freeze_cnn_for_transfer: bool = False,
) -> dict:
    import yfinance as yf
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import classification_report, confusion_matrix
    from sklearn.utils.class_weight import compute_class_weight
    import joblib
    from tensorflow import keras
    from tensorflow.keras.callbacks import (
        EarlyStopping, ReduceLROnPlateau, ModelCheckpoint
    )
    from ml.chart_model import (
        _build_features, _label_data, _create_sequences,
        build_model, MODEL_DIR, MODEL_PATH, SCALER_PATH,
        WINDOW, N_FEATURES, N_CLASSES, FORWARD_DAYS,
    )

    os.makedirs(MODEL_DIR, exist_ok=True)

    # ── 1. Veri çekme (Global Pazar Odaklı) ──────────────────────────────────
    MARKET_BENCHMARKS = ["^GSPC", "XU100.IS", "^N225", "BTC-USD"]
    
    SYMBOLS = [
        "BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", # Crypto
        "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",    # US Tech
        "THYAO.IS", "GARAN.IS", "EREGL.IS", "ASELS.IS", "KCHOL.IS", # BIST
        "7203.T", "9984.T", "8035.T", # Nikkei (Toyota, Softbank, Tokyo Electron)
        "^GSPC", "^IXIC", "XU100.IS", "^N225" # Indices
    ]
    
    all_X, all_y = [], []
    
    # Sürekli eğitim için: Eğer mevcut bir model varsa onu yükle ve üzerine eğit (Transfer Learning)
    from ml.chart_model import is_model_available, MODEL_PATH
    base_model = None
    if is_model_available():
        try:
            from tensorflow import keras
            base_model = keras.models.load_model(MODEL_PATH)
            logger.info("Mevcut model bulundu, incremental eğitim yapılacak.")
        except: pass

    for sym in SYMBOLS:
        # ... (sembol işleme mantığı - önceki adımla aynı)
        logger.info(f"Veri çekiliyor: {sym} ({period})")
        try:
            ticker = yf.Ticker(sym)
            hist   = ticker.history(period=period)
            if hist.empty or len(hist) < WINDOW + 100:
                logger.warning(f"  {sym} için yetersiz veri, atlanıyor.")
                continue
                
            X_raw = _build_features(hist)
            y_raw = _label_data(hist["Close"].iloc[: len(X_raw)])
            
            if X_raw is not None:
                X_s, y_s = _create_sequences(X_raw, y_raw)
                all_X.append(X_s)
                all_y.append(y_s)
                logger.info(f"  {sym}: {len(X_s)} örnek eklendi.")
        except Exception as e:
            logger.error(f"  {sym} işlenirken hata: {e}")

    if not all_X:
        raise ValueError("Hiç veri toplanamadı.")

    X_seq = np.concatenate(all_X)
    y_seq = np.concatenate(all_y)
    logger.info(f"\nToplam Veri Seti: {len(X_seq)} örnek, {WINDOW} günlük pencere, {N_FEATURES} özellik")

    # Sınıf dağılımı
    unique, counts = np.unique(y_seq, return_counts=True)
    dist = dict(zip(["SELL","NEUTRAL","BUY"], counts.tolist()))
    logger.info(f"  Sınıf dağılımı: {dist}")

    # ── 4. Train / Val / Test bölme ──────────────────────────────────────────
    n = len(X_seq)
    n_test = int(n * test_split)
    n_val  = int(n * val_split)
    n_train = n - n_test - n_val

    X_train, y_train = X_seq[:n_train],           y_seq[:n_train]
    X_val,   y_val   = X_seq[n_train:n_train+n_val], y_seq[n_train:n_train+n_val]
    X_test,  y_test  = X_seq[n_train+n_val:],     y_seq[n_train+n_val:]

    # ── 5. Scaler ─────────────────────────────────────────────────────────────
    scaler = StandardScaler()
    X_train_flat = X_train.reshape(-1, N_FEATURES)
    scaler.fit(X_train_flat)
    joblib.dump(scaler, SCALER_PATH)
    logger.info(f"  Scaler kaydedildi: {SCALER_PATH}")

    def scale(X):
        orig_shape = X.shape
        return scaler.transform(X.reshape(-1, N_FEATURES)).reshape(orig_shape)

    X_train = scale(X_train)
    X_val   = scale(X_val)
    X_test  = scale(X_test)

    # ── 6. Sınıf ağırlıkları ─────────────────────────────────────────────────
    cw = None
    if use_class_weights:
        weights = compute_class_weight("balanced", classes=np.array([0,1,2]), y=y_train)
        cw = {0: weights[0], 1: weights[1], 2: weights[2]}
        logger.info(f"  Sınıf ağırlıkları: {cw}")

    # ── 7. Model ──────────────────────────────────────────────────────────────
    model = build_model()
    model.summary(print_fn=lambda x: logger.info("  " + x))

    if freeze_cnn_for_transfer:
        for layer in model.layers[:5]:
            layer.trainable = False
        logger.info("  CNN katmanları donduruldu (transfer learning)")

    # ── 8. Eğitim ─────────────────────────────────────────────────────────────
    logger.info(f"Eğitim başlıyor — {epochs} epoch, batch={batch_size}")
    callbacks = [
        EarlyStopping(patience=8, restore_best_weights=True, verbose=1),
        ReduceLROnPlateau(factor=0.5, patience=4, verbose=1),
        ModelCheckpoint(MODEL_PATH, save_best_only=True, verbose=0),
    ]

    history = model.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=epochs,
        batch_size=batch_size,
        class_weight=cw,
        callbacks=callbacks,
        verbose=1,
    )

    # ── 9. Test değerlendirmesi ───────────────────────────────────────────────
    test_loss, test_acc = model.evaluate(X_test, y_test, verbose=0)
    y_pred = np.argmax(model.predict(X_test, verbose=0), axis=1)

    label_names = ["SELL", "NEUTRAL", "BUY"]
    report = classification_report(y_test, y_pred, target_names=label_names, output_dict=True)
    cm = confusion_matrix(y_test, y_pred).tolist()

    logger.info(f"\nTest Accuracy : {test_acc:.4f}")
    logger.info(f"Test Loss     : {test_loss:.4f}")
    logger.info(f"\n{classification_report(y_test, y_pred, target_names=label_names)}")
    logger.info(f"Confusion Matrix:\n{np.array(cm)}")

    # ── 10. Meta kaydet ───────────────────────────────────────────────────────
    meta = {
        "trained_on":    symbol,
        "training_date": datetime.now().isoformat(),
        "period":        period,
        "n_train":       int(n_train),
        "n_val":         int(n_val),
        "n_test":        int(n_test),
        "window":        WINDOW,
        "n_features":    N_FEATURES,
        "forward_days":  FORWARD_DAYS,
        "test_accuracy": round(float(test_acc), 4),
        "test_loss":     round(float(test_loss), 4),
        "classification_report": report,
        "confusion_matrix":      cm,
        "class_distribution":    {k: int(v) for k, v in dist.items()},
        "best_epoch": len(history.history["val_accuracy"]),
    }
    meta_path = os.path.join(MODEL_DIR, "btc_chart_model_meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    logger.info(f"\nMeta kaydedildi: {meta_path}")
    logger.info(f"Model kaydedildi: {MODEL_PATH}")
    logger.info(f"\n✅ Eğitim tamamlandı — Test Accuracy: {test_acc:.2%}")
    return meta


def transfer_train(
    symbol: str,
    epochs: int = 20,
    batch_size: int = 32,
) -> dict:
    """
    BTC modeli üzerine başka bir varlık için transfer learning.
    CNN katmanları dondurulur, sadece LSTM+Dense güncellenir.
    """
    logger.info(f"Transfer learning: {symbol} için BTC modeli baz alınıyor")
    return train(
        symbol=symbol,
        epochs=epochs,
        batch_size=batch_size,
        freeze_cnn_for_transfer=True,
        period="2y",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OptiTrade BTC Chart AI Eğitimi")
    parser.add_argument("--symbol",     default="BTC-USD",  help="Varlık sembolü")
    parser.add_argument("--epochs",     type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--period",     default="max",       help="yfinance period: max/5y/2y")
    parser.add_argument("--transfer",   action="store_true", help="Transfer learning modu")
    args = parser.parse_args()

    if args.transfer and args.symbol != "BTC-USD":
        transfer_train(symbol=args.symbol, epochs=args.epochs, batch_size=args.batch_size)
    else:
        train(
            symbol=args.symbol,
            epochs=args.epochs,
            batch_size=args.batch_size,
            period=args.period,
        )
