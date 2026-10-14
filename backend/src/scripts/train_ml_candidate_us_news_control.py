"""OptiTrade — same-split control for attempt 7 (Technical + SEC + News).

Usage (from backend/src):
  python scripts/train_ml_candidate_us_news_control.py

Attempt 7 (train_ml_candidate_us_news.py) was the first of 7 attempts
to beat its baseline (0.460 vs 0.445, ROC-AUC 0.537) - but on a
notably smaller held-out sample (2352) than prior attempts, over a
different, shorter window than attempt 6 (Technical + SEC only, no
News). Before concluding News is responsible for the improvement
rather than "this particular 3-month window happened to be easier for
unrelated reasons," this trains TWO models on the IDENTICAL
chronological train/held-out split - one with News features, one
without - isolating News' own marginal contribution rather than
re-running on a different window (which attempt 6 already was).

Deliberately skips model registry/experiment/calibration/SHAP
bookkeeping (unlike every other script here) - this is a diagnostic
A/B comparison, not a candidate for promotion.
"""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

import logging
from datetime import datetime, timedelta, timezone
from typing import List

import pandas as pd

from core.market_config import US_SYMBOLS
from ml_training.config import MLTrainingConfig
from ml_training.datasets.builder import DatasetBuilder
from ml_training.evaluation.evaluator import ModelEvaluator
from ml_training.features.extractor import FeatureExtractor
from ml_training.models import DatasetType, LabelName, ModelAlgorithm, TaskType
from ml_training.service import _samples_to_arrays
from ml_training.training.service import create_trainer
from scripts.train_ml_candidate import CachingPriceFetcher

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

HORIZON_DAYS = 5
SYMBOLS = list(US_SYMBOLS.keys())
_NEWS_COVERAGE_START = datetime(2025, 10, 29, tzinfo=timezone.utc)


def _report_one(label: str, feature_names: List[str], train_samples, held_out_samples, config) -> None:
    X_train, y_train, _ = _samples_to_arrays(train_samples, feature_names, LabelName.DIRECTION)
    X_oos, y_oos, returns_oos = _samples_to_arrays(held_out_samples, feature_names, LabelName.DIRECTION)

    trainer = create_trainer(ModelAlgorithm.XGBOOST, TaskType.CLASSIFICATION, feature_names, config=config)
    trainer.fit(X_train, y_train)  # no val split for this diagnostic comparison - no early stopping either side

    evaluator = ModelEvaluator(config=config)
    metrics = evaluator.evaluate(trainer, X_oos, y_oos, actual_returns=returns_oos)
    counts = pd.Series(y_oos).value_counts().tolist()
    majority_baseline = max(counts) / len(y_oos) if len(y_oos) else 0.0

    print(f"\n--- {label} ({len(feature_names)} features) ---")
    print(f"Accuracy: {metrics.accuracy:.3f} | Majority baseline: {majority_baseline:.3f}")
    print(f"Precision: {metrics.precision:.3f} | Recall: {metrics.recall:.3f}")
    print(f"ROC AUC: {metrics.roc_auc}")


def main() -> None:
    config = MLTrainingConfig.from_env()
    now = datetime.now(timezone.utc)
    train_start = _NEWS_COVERAGE_START
    held_out_start = now - timedelta(days=90)
    train_end_date = held_out_start - timedelta(days=1)

    print("=" * 65)
    print("Attempt 7 control: same split, News features in vs. out")
    print(f"Train: [{train_start.date().isoformat()}, {train_end_date.date().isoformat()}] | "
          f"Held-out: [{held_out_start.date().isoformat()}, {now.date().isoformat()}]")
    print("=" * 65)

    price_fetcher = CachingPriceFetcher(SYMBOLS, train_start, now)
    builder = DatasetBuilder(feature_extractor=FeatureExtractor(), config=config, price_fetcher=price_fetcher)

    print("\nBuilding train samples...")
    train_samples, _ = builder.build(SYMBOLS, DatasetType.TRADER, train_start, train_end_date, horizons_days=[HORIZON_DAYS])
    print(f"{len(train_samples)} train samples built.")

    print("Building held-out samples...")
    held_out_samples, _ = builder.build(SYMBOLS, DatasetType.TRADER, held_out_start, now, horizons_days=[HORIZON_DAYS])
    print(f"{len(held_out_samples)} held-out samples built.")

    all_features = sorted({name for sample in train_samples for name in sample.features})
    news_features = [n for n in all_features if n.startswith("news_")]
    restricted_features = [n for n in all_features if n not in news_features]

    print(f"\nFull feature set: {len(all_features)} ({len(news_features)} News)")
    print(f"Restricted (no News): {len(restricted_features)}")

    _report_one("WITH News", all_features, train_samples, held_out_samples, config)
    _report_one("WITHOUT News", restricted_features, train_samples, held_out_samples, config)


if __name__ == "__main__":
    main()
