"""OptiTrade - second, independent held-out window for attempt 7
(Technical + SEC + News).

Usage (from backend/src):
  python scripts/train_ml_candidate_us_news_window2.py

The original control run (`train_ml_candidate_us_news_control.py`) used
train=[2025-10-29, 2026-07-15] / held-out=[2026-07-16, 2026-10-14] - the
most recent 90 days available, bounded by Finnhub's free-tier ~1-year
News history (coverage starts 2025-10-29). This script tests the SAME
News-in vs News-out comparison on the window immediately BEFORE that one,
non-overlapping with it, still within genuine News coverage:

  train      = [2025-10-29, 2026-04-16]  (~170 days)
  held-out   = [2026-04-17, 2026-07-15]  (~90 days, ends the day before
               the original window's held-out period starts)

A smaller training window is the unavoidable cost of staying inside
News' real backfilled coverage rather than defaulting missing News to
0.0 for an earlier period. If the News effect replicates here - same
direction, comparable size, on a held-out set that shares zero days
with the original - that is real corroboration rather than a result
specific to Jul-Oct 2026.

Deliberately reuses every helper from the control script (significance
tests, per-class/discordant-case diagnostics) rather than duplicating
them - only the date window differs.
"""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

import logging
from datetime import datetime, timedelta, timezone

import numpy as np

from core.market_config import US_SYMBOLS
from ml_training.config import MLTrainingConfig
from ml_training.datasets.builder import DatasetBuilder
from ml_training.features.extractor import FeatureExtractor
from ml_training.models import DatasetType
from scripts.train_ml_candidate import CachingPriceFetcher
from scripts.train_ml_candidate_us_news_control import (
    HORIZON_DAYS,
    _NEWS_COVERAGE_START,
    _bootstrap_gap,
    _confidence_stratified_accuracy,
    _diagnose_discordant_cases,
    _fit_and_predict,
    _mcnemar_test,
    _per_class_breakdown,
)

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

SYMBOLS = list(US_SYMBOLS.keys())


def main() -> None:
    config = MLTrainingConfig.from_env()
    now = datetime.now(timezone.utc)

    # Anchored to the ORIGINAL control run's held-out start (now - 90d),
    # not to "now" directly, so this window always sits immediately
    # before the original one regardless of which day this script runs.
    original_held_out_start = now - timedelta(days=90)
    held_out_end = original_held_out_start - timedelta(days=1)
    held_out_start = held_out_end - timedelta(days=89)
    train_end_date = held_out_start - timedelta(days=1)
    train_start = _NEWS_COVERAGE_START

    print("=" * 65)
    print("Attempt 7, second window: News in vs. out, non-overlapping held-out")
    print(f"Train: [{train_start.date().isoformat()}, {train_end_date.date().isoformat()}] | "
          f"Held-out: [{held_out_start.date().isoformat()}, {held_out_end.date().isoformat()}]")
    print(f"(Original window's held-out started {original_held_out_start.date().isoformat()} - "
          f"zero overlap with this window's held-out period)")
    print("=" * 65)

    price_fetcher = CachingPriceFetcher(SYMBOLS, train_start, held_out_end)
    builder = DatasetBuilder(feature_extractor=FeatureExtractor(), config=config, price_fetcher=price_fetcher)

    print("\nBuilding train samples...")
    train_samples, _ = builder.build(SYMBOLS, DatasetType.TRADER, train_start, train_end_date, horizons_days=[HORIZON_DAYS])
    print(f"{len(train_samples)} train samples built.")

    print("Building held-out samples...")
    held_out_samples, _ = builder.build(SYMBOLS, DatasetType.TRADER, held_out_start, held_out_end, horizons_days=[HORIZON_DAYS])
    print(f"{len(held_out_samples)} held-out samples built.")

    all_features = sorted({name for sample in train_samples for name in sample.features})
    news_features = [n for n in all_features if n.startswith("news_")]
    restricted_features = [n for n in all_features if n not in news_features]

    print(f"\nFull feature set: {len(all_features)} ({len(news_features)} News)")
    print(f"Restricted (no News): {len(restricted_features)}")

    y_true_with, pred_with, proba_with, classes_with = _fit_and_predict(
        "WITH News", all_features, train_samples, held_out_samples, config,
    )
    y_true_without, pred_without, proba_without, classes_without = _fit_and_predict(
        "WITHOUT News", restricted_features, train_samples, held_out_samples, config,
    )
    assert np.array_equal(y_true_with, y_true_without), "held-out label order diverged between the two arms"
    assert np.array_equal(classes_with, classes_without), "label encoder class order diverged between the two arms"
    y_true = y_true_with
    classes = classes_with

    b, c, statistic, p_value = _mcnemar_test(y_true, pred_with, pred_without)
    print(f"\n--- McNemar's test (accuracy, paired) ---")
    print(f"With-right/Without-wrong: {b} | Without-right/With-wrong: {c}")
    print(f"Statistic: {statistic:.4f} | p-value: {p_value:.4f}")

    _bootstrap_gap(y_true, pred_with, proba_with, pred_without, proba_without)

    print("\n" + "=" * 65)
    print("Diagnostics (same breakdown as the original window)")
    print("=" * 65)
    _per_class_breakdown("WITH News", y_true, pred_with, proba_with, classes)
    _per_class_breakdown("WITHOUT News", y_true, pred_without, proba_without, classes)
    _confidence_stratified_accuracy("WITH News", y_true, pred_with, proba_with)
    _confidence_stratified_accuracy("WITHOUT News", y_true, pred_without, proba_without)
    _diagnose_discordant_cases(y_true, pred_with, proba_with, pred_without, proba_without, classes)


if __name__ == "__main__":
    main()
