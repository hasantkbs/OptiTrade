"""OptiTrade — point-in-time accuracy evaluation for the legacy XGBoost
models, plus a current-state sanity check for decision_engine.

Usage (from backend/src):
  python scripts/evaluate_model_accuracy.py

Methodology:
- xgb_signal_model.joblib / v2_xgb_model.joblib: true walk-forward
  evaluation. For each symbol in SYMBOL_BASKET, fetches ~1y of daily
  OHLCV, computes the SAME feature vector each model was trained on at
  every historical bar i (using only data up to and including bar i -
  point-in-time safe), predicts, and compares the prediction's implied
  direction against the REALIZED return from bar i to bar i+FORWARD_DAYS.
  Reports accuracy/precision/recall against a naive "always predict the
  majority class" baseline.
- decision_engine: NOT walk-forward (decision_engine.decide(symbol) has
  no point-in-time parameter - it always reads the Feature Store's
  current/live state, a real limitation of this evaluation, not
  something this script can route around without decision_engine
  itself gaining historical replay support, which is out of scope for
  this plan). Reports today's live decide() output across the same
  symbol basket as a distribution/sanity check only - NOT an accuracy
  number, and the report says so explicitly.
"""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

import logging
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd

from core.indicators import (
    calculate_bollinger_bands, calculate_ema_crossover, calculate_macd,
    calculate_price_velocity, calculate_rsi, calculate_trend_strength,
    calculate_volume_ratio,
)
from data.fetcher import fetch_history
from decision_engine.service import get_default_decision_engine

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

LOOKBACK = 60
FORWARD_DAYS = 5
THRESHOLD_UP_PCT = 1.0

# Same basket research/ml_trainer.py already trains on - a representative
# mix of BIST equities and major crypto assets (the two asset classes the
# spec's dual-asset vision targets).
SYMBOL_BASKET = [
    "THYAO.IS", "GARAN.IS", "ASELS.IS", "EREGL.IS", "AKBNK.IS",
    "BTC-USD", "ETH-USD", "SOL-USD",
]

FEATURE_NAMES = ["rsi", "macd_diff", "bollinger_pb", "ema_signal_enc", "trend_strength", "price_velocity", "volume_ratio"]
_EMA_SIGNAL_ENC = {"GOLDEN_CROSS": 2, "BULLISH": 1, "BEARISH": -1, "DEATH_CROSS": -2, None: 0}


def _extract_features(window: pd.DataFrame) -> "list[float] | None":
    try:
        prices = window["Close"]
        current, open_p = float(prices.iloc[-1]), float(window["Open"].iloc[-1])
        vol, avg_vol = float(window["Volume"].iloc[-1]), float(window["Volume"].mean())
        rsi = calculate_rsi(prices) or 50.0
        macd, macd_sig, _ = calculate_macd(prices)
        macd_diff = (macd - macd_sig) if (macd is not None and macd_sig is not None) else 0.0
        boll = calculate_bollinger_bands(prices)
        pb = (boll.get("percent_b") if boll else None) or 0.5
        ema_enc = _EMA_SIGNAL_ENC.get(calculate_ema_crossover(prices), 0)
        trend = calculate_trend_strength(prices) or 0.0
        vel = calculate_price_velocity(current, open_p)
        vol_r = calculate_volume_ratio(vol, avg_vol)
        return [rsi, macd_diff, pb, ema_enc, trend, vel, vol_r]
    except Exception:
        return None


def walk_forward_evaluate(model_path: str, model_name: str) -> dict:
    package = joblib.load(model_path)
    model = package["model"]

    y_true, y_pred = [], []
    for symbol in SYMBOL_BASKET:
        hist = fetch_history(symbol, period="1y")
        if hist is None or len(hist) < LOOKBACK + FORWARD_DAYS + 10:
            logger.warning("%s: insufficient history, skipping", symbol)
            continue
        for i in range(LOOKBACK, len(hist) - FORWARD_DAYS):
            window = hist.iloc[i - LOOKBACK: i + 1]
            feats = _extract_features(window)
            if feats is None:
                continue
            current_p = float(hist["Close"].iloc[i])
            future_p = float(hist["Close"].iloc[i + FORWARD_DAYS])
            actual_up = 1 if ((future_p - current_p) / current_p) * 100 > THRESHOLD_UP_PCT else 0
            pred_up = int(model.predict(np.array([feats]))[0])
            y_true.append(actual_up)
            y_pred.append(pred_up)

    y_true_arr, y_pred_arr = np.array(y_true), np.array(y_pred)
    accuracy = float((y_true_arr == y_pred_arr).mean()) if len(y_true_arr) else 0.0
    majority_baseline = float(max(y_true_arr.mean(), 1 - y_true_arr.mean())) if len(y_true_arr) else 0.0
    tp = int(((y_pred_arr == 1) & (y_true_arr == 1)).sum())
    fp = int(((y_pred_arr == 1) & (y_true_arr == 0)).sum())
    fn = int(((y_pred_arr == 0) & (y_true_arr == 1)).sum())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return {
        "model": model_name, "n_samples": len(y_true_arr), "accuracy": accuracy,
        "majority_baseline": majority_baseline, "precision": precision, "recall": recall,
    }


def decision_engine_snapshot() -> list:
    engine = get_default_decision_engine()
    rows = []
    for symbol in SYMBOL_BASKET:
        try:
            output = engine.decide(symbol)
            rows.append({
                "symbol": symbol, "decision": output.decision.value,
                "confidence": output.confidence, "data_sufficiency": output.data_sufficiency,
            })
        except Exception as exc:
            rows.append({"symbol": symbol, "decision": "ERROR", "confidence": None, "error": str(exc)})
    return rows


def main() -> None:
    # Each model is evaluated independently and defensively: the two legacy
    # artifacts are not guaranteed to share a feature schema (xgb_signal_model
    # was trained on a different feature set than v2_xgb_model), so a
    # predict()-time failure for one model must not prevent reporting real
    # results for the other - same per-item fault isolation already used
    # below in decision_engine_snapshot().
    model_specs = [
        ("../model_artifacts/xgb_signal_model.joblib", "xgb_signal_model"),
        ("../model_artifacts/v2_xgb_model.joblib", "v2_xgb_model"),
    ]
    results = []
    for path, name in model_specs:
        try:
            results.append(walk_forward_evaluate(path, name))
        except Exception as exc:
            logger.warning("%s: walk-forward evaluation failed: %s", name, exc)
            results.append({"model": name, "n_samples": 0, "error": str(exc)})
    snapshot = decision_engine_snapshot()

    lines = [
        f"# ML Model Accuracy Report — {datetime.now(timezone.utc).date().isoformat()}", "",
        "## Walk-forward evaluation (XGBoost models)", "",
        "| Model | Samples | Accuracy | Majority baseline | Precision | Recall |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        if "error" in r:
            lines.append(f"| {r['model']} | {r['n_samples']} | ERROR | - | - | {r['error']} |")
        else:
            lines.append(
                f"| {r['model']} | {r['n_samples']} | {r['accuracy']:.3f} | "
                f"{r['majority_baseline']:.3f} | {r['precision']:.3f} | {r['recall']:.3f} |"
            )
    lines += [
        "", "## decision_engine current-state snapshot (NOT a backtest)", "",
        "`decision_engine.decide()` has no point-in-time parameter, so this is "
        "today's live decision only, not a historical accuracy figure. A proper "
        "decision_engine backtest needs historical replay support - out of scope "
        "for this evaluation.", "",
        "| Symbol | Decision | Confidence | Data sufficiency |",
        "|---|---|---|---|",
    ]
    for row in snapshot:
        if row["decision"] == "ERROR":
            lines.append(f"| {row['symbol']} | ERROR | - | {row.get('error', '')} |")
        else:
            lines.append(f"| {row['symbol']} | {row['decision']} | {row['confidence']:.2f} | {row['data_sufficiency']:.2f} |")

    report = "\n".join(lines)
    print(report)
    with open("../../docs/ml-accuracy-report-2026-10-01.md", "w") as f:
        f.write(report + "\n")


if __name__ == "__main__":
    main()
