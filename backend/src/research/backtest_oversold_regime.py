"""OptiTrade — ground-truth backtest of the "oversold implies a bounce"
assumption, and of the chart AI model's skill specifically in that
regime, per market.

Usage (from backend/src):
  python -m research.backtest_oversold_regime --market BIST   # default
  python -m research.backtest_oversold_regime --market US
  python -m research.backtest_oversold_regime --market CRYPTO

Context: decision_engine's rule-based TechnicalEngine treats an
oversold reading (RSI<30, or price at/below the lower Bollinger band)
as evidence a bounce is coming - e.g. it voted BUY on SISE.IS while
its own evidence showed "bearish trend... MACD below signal...
oversold... potential bounce zone". A live scan of 26 BIST symbols
first found decision_engine (or the chart AI model) disagreeing with
that assumption far more often than agreeing (16 SELL vs 4 BUY out of
26 - see docs/btc-chart-model-training-2026-10-22.md). This script
checks whether that disagreement is backed by real history, not just
one day's live snapshot, and whether the same pattern holds in US and
CRYPTO too - using ONLY each symbol's own held-out test split (chart
AI's own `train()` used the exact same boundaries; this script never
re-trains, only re-evaluates), so the ground-truth labels and the
model's own predictions are both on data the model never trained on.

Method: for each symbol in the requested market's currently-live
chart-AI set (`symbols_for_market()`, read fresh from
`get_supported_symbols()`), rebuilds the same 60-day feature sequences
`train()` builds, takes the same chronological test split (last 15%,
with the same `FORWARD_DAYS` leakage gap), flags samples where the
LAST day of that 60-day window is "oversold" (raw RSI<30 or raw
Bollinger %B<0.02 - using the raw, pre-scaling feature values, since
scaled values lose their absolute RSI/Bollinger meaning), then pools
across every symbol in that market and reports:

  1. The GROUND-TRUTH label distribution in that pooled oversold
     subset - what actually happened 5 trading days later, regardless
     of what any model predicted. This is the real test of "does
     oversold actually predict a bounce" on this basket.
  2. The already-live chart AI model's own prediction accuracy on
     that same pooled subset, checked with
     `ml.chart_model.check_window_significance` against the subset's
     own majority baseline.
"""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

import json
import logging
from typing import List

import numpy as np
import yfinance as yf

from ml.chart_model import (
    FORWARD_DAYS, N_FEATURES, WINDOW,
    _build_features, _create_sequences, _label_data,
    check_window_significance, get_supported_symbols, load_model,
)

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

LABEL_NAMES = {0: "SELL", 1: "NEUTRAL", 2: "BUY"}


def _market_of(symbol: str) -> str:
    """Matches core.market_config.get_market_for_symbol's own suffix
    convention, without importing it (that function expects symbols
    already in one of its three static tables - every live chart-AI
    symbol already is, but keeping this standalone avoids a dependency
    this module otherwise has no reason to carry)."""
    if symbol.endswith(".IS"):
        return "BIST"
    if symbol.endswith("-USD"):
        return "CRYPTO"
    return "US"


def symbols_for_market(market: str) -> List[str]:
    """Every currently-LIVE chart-AI symbol in `market` (BIST/US/CRYPTO),
    read fresh from get_supported_symbols() - not a frozen list, so this
    always matches whatever's actually live, including after a future
    weekly retrain promotes or demotes a symbol."""
    market = market.upper()
    return [s for s in get_supported_symbols() if _market_of(s) == market]


def _symbol_oversold_test_labels(symbol: str) -> "tuple[np.ndarray, np.ndarray] | None":
    """Returns (true_labels, predicted_labels) for `symbol`'s own
    held-out test split, restricted to windows whose last day is
    oversold - or None if there's not enough data or no trained model."""
    hist = yf.Ticker(symbol).history(period="max")
    if hist.empty or len(hist) < WINDOW + 100:
        logger.warning(f"{symbol}: yetersiz veri")
        return None
    X_raw = _build_features(hist)
    if X_raw is None:
        return None
    y_raw = _label_data(hist["Close"].iloc[: len(X_raw)])
    X_seq, y_seq = _create_sequences(X_raw, y_raw)

    n = len(X_seq)
    n_test = int(n * 0.15)
    n_val = int(n * 0.15)
    n_train = n - n_test - n_val
    start = n_train + n_val + FORWARD_DAYS
    X_test_raw = X_seq[start:]
    y_test = y_seq[start:]
    if len(X_test_raw) < 10:
        return None

    model, scaler = load_model(symbol)
    if model is None:
        logger.warning(f"{symbol}: canlı model yok")
        return None

    # Oversold flag uses the RAW (pre-scaling) feature values of the
    # window's last day - bb_pb is clip(0,1)'d in _build_features, so
    # "at/below the lower band" shows up near 0.0, never negative.
    last_row = X_test_raw[:, -1, :]
    rsi_raw = last_row[:, 5] * 100
    bb_pb_raw = last_row[:, 7]
    oversold_mask = (rsi_raw < 30) | (bb_pb_raw < 0.02)
    if oversold_mask.sum() == 0:
        return None

    X_test_scaled = (
        scaler.transform(X_test_raw.reshape(-1, N_FEATURES)).reshape(X_test_raw.shape)
        if scaler is not None else X_test_raw
    )
    y_pred = np.argmax(model.predict(X_test_scaled, verbose=0), axis=1)

    print(f"{symbol}: {len(y_test)} test örnek, {int(oversold_mask.sum())} oversold")
    return y_test[oversold_mask], y_pred[oversold_mask]


def _symbol_oversold_window2_labels(symbol: str) -> "tuple[np.ndarray, np.ndarray] | None":
    """Same idea as _symbol_oversold_test_labels, but on window 2 - a
    SEPARATE model trained only on window 1's former TRAIN block,
    evaluated on window 1's former VAL block (the middle 15%, zero
    overlap with window 1's own test block). Mirrors
    validate_chart_model_window2.py::validate()'s exact split/train
    logic, trading a few minutes of CPU per symbol for roughly double
    the pooled oversold sample - the point for a market like CRYPTO
    whose symbols have far less price history than BIST/US, so window
    1's test split alone gives a thin oversold subset per symbol."""
    import yfinance as yf
    from sklearn.preprocessing import StandardScaler
    from sklearn.utils.class_weight import compute_class_weight
    from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau

    from ml.chart_model import build_model

    hist = yf.Ticker(symbol).history(period="max")
    if hist.empty or len(hist) < WINDOW + 100:
        return None
    X_raw = _build_features(hist)
    if X_raw is None:
        return None
    y_raw = _label_data(hist["Close"].iloc[: len(X_raw)])
    X_seq, y_seq = _create_sequences(X_raw, y_raw)

    n = len(X_seq)
    n_test1 = int(n * 0.15)
    n_val1 = int(n * 0.15)
    n_train1 = n - n_test1 - n_val1

    window2_test_start = n_train1 + FORWARD_DAYS
    X_test2_raw = X_seq[window2_test_start:n_train1 + n_val1]
    y_test2 = y_seq[window2_test_start:n_train1 + n_val1]
    if len(X_test2_raw) < 10:
        return None

    n_inner_val = int(n_train1 * 0.15)
    n_inner_train = n_train1 - n_inner_val
    X_train2, y_train2 = X_seq[:n_inner_train], y_seq[:n_inner_train]
    inner_val_start = n_inner_train + FORWARD_DAYS
    X_val2, y_val2 = X_seq[inner_val_start:n_train1], y_seq[inner_val_start:n_train1]

    scaler = StandardScaler()
    scaler.fit(X_train2.reshape(-1, N_FEATURES))

    def scale(X):
        return scaler.transform(X.reshape(-1, N_FEATURES)).reshape(X.shape)

    X_train2_s, X_val2_s = scale(X_train2), scale(X_val2)
    weights = compute_class_weight("balanced", classes=np.array([0, 1, 2]), y=y_train2)
    cw = {0: weights[0], 1: weights[1], 2: weights[2]}

    model = build_model()
    model.fit(
        X_train2_s, y_train2,
        validation_data=(X_val2_s, y_val2),
        epochs=50, batch_size=64, class_weight=cw,
        callbacks=[
            EarlyStopping(patience=8, restore_best_weights=True, verbose=0),
            ReduceLROnPlateau(factor=0.5, patience=4, verbose=0),
        ],
        verbose=0,
    )

    last_row = X_test2_raw[:, -1, :]
    rsi_raw = last_row[:, 5] * 100
    bb_pb_raw = last_row[:, 7]
    oversold_mask = (rsi_raw < 30) | (bb_pb_raw < 0.02)
    if oversold_mask.sum() == 0:
        return None

    X_test2_s = scale(X_test2_raw)
    y_pred2 = np.argmax(model.predict(X_test2_s, verbose=0), axis=1)

    print(f"{symbol} (window2): {len(y_test2)} test örnek, {int(oversold_mask.sum())} oversold")
    return y_test2[oversold_mask], y_pred2[oversold_mask]


def main(symbols: List[str] = None, market: str = "BIST", include_window2: bool = False) -> None:
    symbols = symbols if symbols is not None else symbols_for_market(market)
    print(f"=== {market.upper()} - {len(symbols)} canlı chart-AI sembolü ===")
    pooled_true: List[int] = []
    pooled_pred: List[int] = []

    for symbol in symbols:
        try:
            result = _symbol_oversold_test_labels(symbol)
        except Exception as exc:
            logger.error(f"{symbol} (window1): {exc}")
            result = None
        if result is not None:
            true_labels, pred_labels = result
            pooled_true.extend(true_labels.tolist())
            pooled_pred.extend(pred_labels.tolist())

        if include_window2:
            try:
                result2 = _symbol_oversold_window2_labels(symbol)
            except Exception as exc:
                logger.error(f"{symbol} (window2): {exc}")
                result2 = None
            if result2 is not None:
                true_labels2, pred_labels2 = result2
                pooled_true.extend(true_labels2.tolist())
                pooled_pred.extend(pred_labels2.tolist())

    pooled_true_arr = np.array(pooled_true)
    pooled_pred_arr = np.array(pooled_pred)
    n = len(pooled_true_arr)

    print(f"\nTOPLAM havuzlanmış oversold test örneği: {n}")
    unique, counts = np.unique(pooled_true_arr, return_counts=True)
    true_dist = {LABEL_NAMES[int(k)]: int(v) for k, v in zip(unique, counts)}
    print(f"GERÇEK (ground truth) etiket dağılımı: {true_dist}")

    accuracy = float((pooled_true_arr == pooled_pred_arr).mean())
    majority_label = max(true_dist, key=true_dist.get)
    majority_baseline = true_dist[majority_label] / n
    passes, p_value = check_window_significance(n=n, baseline=majority_baseline, accuracy=accuracy)

    print(f"Model accuracy (oversold alt-kümede): {accuracy:.4f}")
    print(f"Majority baseline: {majority_baseline:.4f} ({majority_label})")
    print(f"Binom testi: passes={passes}, p={p_value:.2e}")

    sell_rate = true_dist.get("SELL", 0) / n
    neutral_rate = true_dist.get("NEUTRAL", 0) / n
    buy_rate = true_dist.get("BUY", 0) / n
    print(f"\nOversold anlarda GERÇEKTE 5 gün sonra: SELL={sell_rate:.1%}  NEUTRAL={neutral_rate:.1%}  BUY={buy_rate:.1%}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Oversold-regime ground-truth backtest")
    parser.add_argument("--market", default="BIST", choices=["BIST", "US", "CRYPTO"])
    parser.add_argument(
        "--include-window2", action="store_true",
        help="Also train+evaluate a second-window model per symbol (roughly doubles the "
             "pooled sample at the cost of a few minutes of CPU per symbol) - meant for "
             "markets like CRYPTO whose symbols have too little history for window 1 "
             "alone to give a robust oversold subset.",
    )
    args = parser.parse_args()

    main(market=args.market, include_window2=args.include_window2)
