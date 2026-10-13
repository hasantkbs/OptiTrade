"""OptiTrade — ML candidate training on the EXPECTED_VOLATILITY label.

Usage (from backend/src):
  python scripts/train_ml_candidate_volatility.py

Prerequisite: scripts/backfill_feature_store.py must already have been
run for the same date range (shared with train_ml_candidate.py).

Three prior candidates (docs/ml-candidate-report-2026-10-01.md,
-2026-10-03.md, -2026-10-03-derived-features.md) all trained on the
DIRECTION label and converged on ROC-AUC ~0.50 regardless of algorithm
(xgboost/random_forest) or feature-set size (17 vs 49 features) - a
data/label problem, not a model-choice problem, per those reports' own
conclusions. This script tests a different hypothesis instead of
retrying the same one: that pure technical/price-volume features,
while carrying no detectable 5-day DIRECTION signal, may still predict
the MAGNITUDE of the forward move (volatility clustering - today's
realized volatility predicting tomorrow's - is one of the most robust,
well-documented patterns in markets, unlike short-horizon direction).

Reuses ml_training.labels.generator.generate_labels' own
`expected_volatility` field (already computed on every training sample
via the exact OutcomeEvaluator._realized_volatility formula Continuous
Learning uses for live outcomes - LabelName.EXPECTED_VOLATILITY auto-
resolves to TaskType.REGRESSION via task_type_for_label, so every
downstream step - trainer selection, calibration skip, evaluation
metrics - already branches correctly with zero ml_training package
changes). Same 22-symbol basket, same 17 base features (no derived
features - isolating the label-change effect cleanly, matching report
3's methodology rather than report 4's), same horizon_days=5 and
train/held-out window convention as every prior report, for a clean,
comparable result.

"Majority baseline" doesn't apply to a regression target - the natural
baseline for volatility forecasting is PERSISTENCE: today's trailing
realized volatility predicting tomorrow's (the standard naive
benchmark in volatility-forecasting literature, e.g. what GARCH models
are themselves benchmarked against). Computed here with the identical
_realized_volatility formula, over the trailing window ending at each
held-out sample's `as_of` instead of the forward window - deliberately
NOT core/analyzer.py's `atr_pct` (also exposed as the live Technical
engine's own `expected_volatility` field), which is a different,
un-annualized single-snapshot ATR% measure and would make the
comparison an apples-to-oranges scale mismatch.
"""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import r2_score

from engines.technical.config import FEATURE_TREND_STRENGTH
from feature_store.service import get_default_feature_store_service
from learning.evaluator import OutcomeEvaluator
from ml_training.config import MLTrainingConfig
from ml_training.datasets.builder import DatasetBuilder
from ml_training.datasets.service import DatasetService
from ml_training.evaluation.evaluator import ModelEvaluator
from ml_training.features.extractor import FeatureExtractor
from ml_training.models import DatasetType, LabelName, ModelAlgorithm
from ml_training.service import MLTrainingService, _samples_to_arrays
from ml_training.training.service import create_trainer
from research.ml_trainer import SYMBOLS
from scripts.train_ml_candidate import CachingPriceFetcher, _earliest_feature_date

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

_AUTHOR = "train_ml_candidate_volatility_script"
HORIZON_DAYS = 5  # matches train_ml_candidate.py - fair comparison
REPORT_FILENAME_SUFFIX = os.getenv("TRAIN_ML_CANDIDATE_REPORT_SUFFIX", "")


def _naive_trailing_volatility(
    price_fetcher: CachingPriceFetcher, symbol: str, as_of: datetime, horizon_days: int,
) -> Optional[float]:
    """The persistence baseline's own prediction for one sample: the
    SAME realized-volatility formula the label itself uses, computed
    over the trailing `horizon_days` window ending at `as_of` instead
    of the forward window - "today's volatility predicts tomorrow's"."""
    history = price_fetcher(symbol, as_of - timedelta(days=horizon_days + 1), as_of)
    if history is None or history.empty:
        return None
    return OutcomeEvaluator._realized_volatility(history, as_of - timedelta(days=horizon_days), as_of)


def main() -> None:
    config = MLTrainingConfig.from_env()
    now = datetime.now(timezone.utc)
    train_end_date = now - timedelta(days=180)
    train_start = train_end_date - timedelta(days=730)

    print("=" * 65)
    print("OptiTrade - ML Candidate Training (expected_volatility label)")
    print(f"Train: [{train_start.date().isoformat()}, {train_end_date.date().isoformat()}] | "
          f"Held-out eval: ({train_end_date.date().isoformat()}, {now.date().isoformat()}]")
    print(f"Symbols: {len(SYMBOLS)} | horizon_days={HORIZON_DAYS} | algorithm=xgboost | label=expected_volatility")
    print("=" * 65)

    earliest_available = _earliest_feature_date(SYMBOLS)
    if earliest_available is not None and earliest_available.date() > train_start.date():
        print(
            f"UYARI: Feature Store coverage starts {earliest_available.date().isoformat()}, "
            f"after the computed train_start {train_start.date().isoformat()} - "
            f"the real training window is narrower than nominally computed."
        )

    price_fetcher = CachingPriceFetcher(SYMBOLS, train_start, now)

    dataset_service = DatasetService(
        builder=DatasetBuilder(feature_extractor=FeatureExtractor(), config=config, price_fetcher=price_fetcher),
        config=config,
    )
    service = MLTrainingService(datasets=dataset_service, config=config)

    print("\nEğitim çalıştırılıyor (bu birkaç dakika sürebilir)...")
    result = service.run_training_job(
        author=_AUTHOR, symbols=SYMBOLS, dataset_type=DatasetType.TRADER,
        label_name=LabelName.EXPECTED_VOLATILITY, horizon_days=HORIZON_DAYS,
        algorithm=ModelAlgorithm.XGBOOST, start=train_start, end=train_end_date,
    )
    print(f"CANDIDATE kaydedildi: model_id={result.registry_entry.model_id}")
    print(f"In-training MAE/RMSE: mae={result.metrics.mae:.3f} rmse={result.metrics.rmse:.3f}")
    print(f"Hipotez sonucu: {result.hypothesis_outcome.value}")

    print("\nGerçek out-of-sample değerlendirme çalıştırılıyor...")
    held_out_start = train_end_date + timedelta(days=1)
    held_out_builder = DatasetBuilder(feature_extractor=FeatureExtractor(), config=config, price_fetcher=price_fetcher)
    held_out_samples, held_out_version = held_out_builder.build(
        SYMBOLS, DatasetType.TRADER, start=held_out_start, end=now, horizons_days=[HORIZON_DAYS],
    )

    trainer = create_trainer(
        ModelAlgorithm.XGBOOST, result.training_run.task_type, result.registry_entry.feature_list, config=config,
    )
    trainer.load(result.registry_entry.artifact_path)

    X_oos, y_oos, returns_oos = _samples_to_arrays(
        held_out_samples, result.registry_entry.feature_list, LabelName.EXPECTED_VOLATILITY,
    )
    evaluator = ModelEvaluator(config=config)
    oos_metrics = evaluator.evaluate(trainer, X_oos, y_oos, actual_returns=returns_oos)
    y_pred = trainer.predict(X_oos)
    model_r2 = r2_score(y_oos, y_pred)
    model_corr = spearmanr(y_oos, y_pred).statistic

    naive_preds: List[Optional[float]] = [
        _naive_trailing_volatility(price_fetcher, sample.symbol, sample.as_of, HORIZON_DAYS)
        for sample in held_out_samples
    ]
    naive_mask = np.array([p is not None for p in naive_preds])
    y_naive_true = y_oos[naive_mask]
    y_naive_pred = np.array([p for p in naive_preds if p is not None])
    naive_mae = float(np.mean(np.abs(y_naive_true - y_naive_pred)))
    naive_rmse = float(np.sqrt(np.mean((y_naive_true - y_naive_pred) ** 2)))
    naive_r2 = r2_score(y_naive_true, y_naive_pred)
    naive_corr = spearmanr(y_naive_true, y_naive_pred).statistic

    # sklearn's r2_score is DEFINED relative to a constant-mean predictor
    # (R²=0 means "exactly as good as guessing the held-out period's own
    # mean expected_volatility, in retrospect"; negative means worse) -
    # computed explicitly here (cheaply, from y_oos already in memory)
    # so the report states this reference point rather than leaving a
    # negative R² to be misread as "no useful baseline exists at all".
    constant_pred = float(np.mean(y_oos))
    constant_mae = float(np.mean(np.abs(y_oos - constant_pred)))
    constant_rmse = float(np.sqrt(np.mean((y_oos - constant_pred) ** 2)))

    beats_naive = oos_metrics.mae < naive_mae and oos_metrics.rmse < naive_rmse
    beats_constant_mean = oos_metrics.mae < constant_mae and oos_metrics.rmse < constant_rmse

    lines = [
        f"# ML Candidate Report — {now.date().isoformat()} (expected_volatility)", "",
        f"Model: `{result.registry_entry.model_id}` (algorithm=xgboost, label=expected_volatility, horizon_days={HORIZON_DAYS})",
        f"Promotion state: `{result.registry_entry.promotion_state.value}` (CANDIDATE only - no SHADOW/ACTIVE in this run)",
        "",
        "## Held-out out-of-sample evaluation",
        "",
        f"Train window: [{train_start.date().isoformat()}, {train_end_date.date().isoformat()}]",
        f"Held-out window (strictly after train_end_date): [{held_out_start.date().isoformat()}, {now.date().isoformat()}]",
        f"Held-out samples: {len(held_out_samples)} (naive baseline computable for {int(naive_mask.sum())} - "
        f"the rest lack enough trailing price history)",
        "",
        "Naive baseline = trailing realized volatility over the same horizon, predicting the forward realized "
        "volatility (the standard persistence benchmark in volatility forecasting).",
        "",
        "| Metric | Model | Naive baseline (persistence) | Constant-mean baseline |",
        "|---|---|---|---|",
        f"| MAE | {oos_metrics.mae:.3f} | {naive_mae:.3f} | {constant_mae:.3f} |",
        f"| RMSE | {oos_metrics.rmse:.3f} | {naive_rmse:.3f} | {constant_rmse:.3f} |",
        f"| R² | {model_r2:.3f} | {naive_r2:.3f} | 0.000 (by definition) |",
        f"| Spearman rank correlation | {model_corr:.3f} | {naive_corr:.3f} | 0.000 (by definition) |",
        "",
        "Constant-mean baseline predicts the held-out period's own mean expected_volatility for every sample - "
        "not a deployable strategy (that mean isn't known in advance), but it is exactly what R²=0 represents, "
        "so a negative R² above means worse than this reference point, not \"no baseline beaten at all\".",
        "",
        f"**Beats naive (persistence) baseline (lower MAE AND lower RMSE): {beats_naive}**",
        f"**Beats constant-mean baseline (lower MAE AND lower RMSE): {beats_constant_mean}**",
        "",
        "## In-training metrics (for reference, NOT the out-of-sample result above)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| MAE | {result.metrics.mae:.3f} |",
        f"| RMSE | {result.metrics.rmse:.3f} |",
        f"| Hypothesis outcome | {result.hypothesis_outcome.value} |",
    ]
    report = "\n".join(lines)
    print("\n" + report)
    report_path = f"../../docs/ml-candidate-report-{now.date().isoformat()}-volatility{REPORT_FILENAME_SUFFIX}.md"
    with open(report_path, "w") as f:
        f.write(report + "\n")


if __name__ == "__main__":
    main()
