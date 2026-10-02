"""OptiTrade — point-in-time accuracy evaluation for the legacy XGBoost
models, plus a current-state sanity check for decision_engine.

Usage (from backend/src):
  python scripts/evaluate_model_accuracy.py

Methodology:
- xgb_signal_model.joblib / v2_xgb_model.joblib: true walk-forward
  evaluation. For each symbol in SYMBOL_BASKET, fetches daily OHLCV,
  computes the SAME feature vector each model was trained on at every
  historical bar i (using only data up to and including bar i -
  point-in-time safe), predicts, and compares the prediction's implied
  direction against the REALIZED return from bar i to bar i+FORWARD_DAYS.
  Reports accuracy/precision/recall against a naive "always predict the
  majority class" baseline.

  If the loaded model package has a recorded `train_end_date` (written
  by `research/ml_trainer.py --train-end-date ...`), evaluation is
  restricted to bars strictly AFTER that date - genuine out-of-sample,
  not in-sample. If `train_end_date` is absent (None - the default for
  any model trained without that flag, including both legacy artifacts
  shipped before this capability existed), evaluation falls back to the
  most recent 1 year and the report explicitly labels the result
  "in-sample / methodology unknown" rather than implying it's held-out.
- decision_engine: NOT walk-forward (decision_engine.decide(symbol) has
  no point-in-time parameter - it always reads the Feature Store's
  current/live state, a real limitation of this evaluation, not
  something this script can route around without decision_engine
  itself gaining historical replay support, which is out of scope for
  this change). Reports today's live decide() output across the same
  symbol basket as a distribution/sanity check only - NOT an accuracy
  number, and the report says so explicitly.
"""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import joblib
import numpy as np
import yfinance as yf

from data.fetcher import fetch_history
from decision_engine.service import get_default_decision_engine
# extract_features/EMA_SIGNAL_ENC/FEATURE_NAMES are reused deliberately
# here rather than reimplemented: this script's OOS accuracy number is
# only meaningful if it feeds the model byte-identical features to what
# it was trained on. A hand-copied duplicate already silently drifted
# once (the duplicate used `or` for its None-substitutions, which also
# fires on a legitimate exact 0.0 from calculate_rsi/percent_b - a bug
# ml_trainer's `is None` checks don't have). Same reuse-over-duplication
# choice scripts/train_ml_candidate.py already made for
# ml_training.service._samples_to_arrays, for the same reason: duplicated
# logic risks the two copies silently drifting.
from research.ml_trainer import extract_features

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


def walk_forward_evaluate(model_path: str, model_name: str) -> dict:
    package = joblib.load(model_path)
    model = package["model"]
    train_end_date_str: Optional[str] = package.get("train_end_date")
    train_end_date: Optional[date] = (
        datetime.strptime(train_end_date_str, "%Y-%m-%d").date() if train_end_date_str else None
    )
    is_out_of_sample = train_end_date is not None

    y_true, y_pred = [], []
    for symbol in SYMBOL_BASKET:
        try:
            if train_end_date is not None:
                # fetch_history's period-only interface can't express a
                # historical cutoff, so this branch (and only this one)
                # bypasses it for a direct, date-bounded yfinance call.
                # LOOKBACK days of buffer BEFORE train_end_date so the
                # first post-cutoff bar still has a full feature window -
                # only bars whose own date is strictly after
                # train_end_date are ever used as a prediction target
                # below, so the model is never evaluated on a bar it
                # could have trained on.
                hist = yf.Ticker(symbol).history(
                    start=(train_end_date - timedelta(days=LOOKBACK * 2)).isoformat()
                )
            else:
                # No cutoff to express - keep using fetch_history (and
                # therefore HybridProvider's per-asset-class routing,
                # e.g. crypto symbols via Binance) exactly as before this
                # capability was added, rather than silently switching
                # every symbol to a direct yfinance call.
                hist = fetch_history(symbol, period="1y")
        except Exception as exc:
            logger.warning("%s: fetch failed, skipping: %s", symbol, exc)
            continue
        if hist is None or len(hist) < LOOKBACK + FORWARD_DAYS + 10:
            logger.warning("%s: insufficient history, skipping", symbol)
            continue
        for i in range(LOOKBACK, len(hist) - FORWARD_DAYS):
            if train_end_date is not None and hist.index[i].date() <= train_end_date:
                continue  # this bar (or an earlier one the model could have trained on) - skip
            window = hist.iloc[i - LOOKBACK: i + 1]
            feats = extract_features(window)
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
        "is_out_of_sample": is_out_of_sample, "train_end_date": train_end_date_str,
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
    oos_path = "../model_artifacts/xgb_signal_model_oos_test.joblib"
    if os.path.exists(oos_path):
        model_specs.append((oos_path, "xgb_signal_model_oos_test"))
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
        "Rows with a `train_end_date` evaluate ONLY on bars strictly after that "
        "date - genuine out-of-sample. Rows without one (both legacy artifacts, "
        "trained before this capability existed) fall back to the most recent "
        "1 year and may overlap the model's own training window - treat as "
        "in-sample / methodology unknown, not held-out performance.", "",
        "| Model | Samples | Accuracy | Majority baseline | Precision | Recall | Out-of-sample? | Train end date |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        if "error" in r:
            lines.append(f"| {r['model']} | {r['n_samples']} | ERROR | - | - | {r['error']} | - | - |")
        else:
            lines.append(
                f"| {r['model']} | {r['n_samples']} | {r['accuracy']:.3f} | "
                f"{r['majority_baseline']:.3f} | {r['precision']:.3f} | {r['recall']:.3f} | "
                f"{'yes' if r['is_out_of_sample'] else 'no (in-sample/unknown)'} | {r['train_end_date'] or '-'} |"
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
